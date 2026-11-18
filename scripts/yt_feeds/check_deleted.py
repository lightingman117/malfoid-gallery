"""Daily check for YouTube videos linked from the index that may have been deleted.

For every YouTube video ID in malfoid-index/works.yaml, it reads the watch page
(playabilityStatus) and oEmbed, then reports:
  - unavailable: the watch page says it is not playable, or returns 404.
  - suspect: the page says playable but oEmbed does not. Check in a browser.
  - check failed: a network or page error. Never counted as unavailable.
Limit: a public check can miss a removed video (the page and oEmbed can both look
fine). The report is a prompt to verify, not proof.

Nothing in the index is changed. The report lists every video that is currently
unavailable, marks the ones that are new since the last run, and lists the ones
that came back. Verify each one by hand before editing the index.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import yaml

from common import DATA, USER_AGENT, WORKS, atomic_write

STATUS_FILE = DATA / "video_status.json"
ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")
PLAYABILITY_RE = re.compile(r'"playabilityStatus":\{"status":"([A-Z_]+)"(?:,"reason":"([^"]{0,200})")?')
WORKERS = 2
PAUSE = 1.0  # YouTube answers HTTP 429 (rate limit) to fast watch-page requests


def video_refs(works: list[dict]) -> dict[str, list[dict]]:
    """Map each video ID to the index entries and labels that use it."""
    refs: dict[str, list[dict]] = {}

    def walk(node, entry_id, title):
        if isinstance(node, str):
            for vid in ID_RE.findall(node):
                if "videoseries" in node:
                    continue
                refs.setdefault(vid, [])
                if not any(r["entry"] == entry_id for r in refs[vid]):
                    refs[vid].append({"entry": entry_id, "title": title, "url": node})
        elif isinstance(node, dict):
            for v in node.values():
                walk(v, entry_id, title)
        elif isinstance(node, list):
            for v in node:
                walk(v, entry_id, title)

    for w in works:
        walk(w, w.get("id", "?"), w.get("title", ""))
    return refs


def http_get(url: str, timeout: int = 20, retries: int = 2) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                time.sleep(15 * (attempt + 1))  # back off, then try again
                continue
            return e.code, ""
    return 429, ""


def classify(oembed_status: int, page_status: int | None, page_html: str | None) -> dict:
    """Combine the two public signals into one verdict.

    ok          oEmbed 200 and the watch page says playable.
    unavailable the watch page says it is not playable, or returns 404.
    suspect     the page says playable but oEmbed does not, so a person should look.
    check failed the page could not be read, or has no playability status.
    """
    if page_status is None or page_html is None:
        return {"status": "check failed", "reason": "watch page unreadable"}
    if page_status == 404:
        return {"status": "unavailable", "reason": "watch page HTTP 404"}
    m = PLAYABILITY_RE.search(page_html)
    if not m:
        return {"status": "check failed", "reason": "no playability status on the page"}
    if m.group(1) != "OK":
        return {"status": "unavailable", "reason": f"{m.group(1)}: {m.group(2) or 'no reason given'}"}
    if oembed_status == 200:
        return {"status": "ok", "reason": ""}
    return {"status": "suspect", "reason": f"page says OK but oEmbed returned HTTP {oembed_status}"}


def check_video(vid: str) -> dict:
    time.sleep(PAUSE)
    watch = f"https://www.youtube.com/watch?v={vid}"
    try:
        oembed_status, _ = http_get("https://www.youtube.com/oembed?url=" + urllib.parse.quote(watch, safe="") + "&format=json")
    except Exception:
        oembed_status = None
    try:
        page_status, page_html = http_get(watch)
    except Exception:
        page_status, page_html = None, None
    result = classify(oembed_status, page_status, page_html)
    result["checked"] = date.today().isoformat()
    return result


def report_text(today: str, unavailable: list[dict], newly: set[str], recovered: list[str], failed: list[str], suspects: list[dict] | None = None) -> str:
    lines = [f"# Deleted-video check, {today}", ""]
    lines.append(f"## Unavailable ({len(unavailable)}). Verify each one by hand before editing the index")
    for u in unavailable:
        flag = " (new)" if u["video_id"] in newly else ""
        lines.append(f"- {u['video_id']}{flag}: {u['reason']} — since {u['since']}")
        for r in u["refs"]:
            lines.append(f"    - entry `{r['entry']}` ({r['title']}), label/URL: {r['url']}")
    if suspects:
        lines += ["", f"## Suspect ({len(suspects)}). Public signals disagree; check in a browser"]
        for s in suspects:
            lines.append(f"- {s['video_id']}: {s['reason']}")
            for r in s["refs"]:
                lines.append(f"    - entry `{r['entry']}` ({r['title']}), label/URL: {r['url']}")
    if recovered:
        lines += ["", "## Back online since the last run"] + [f"- {v}" for v in recovered]
    if failed:
        lines += ["", "## Could not check (retried next run)"] + [f"- {v}" for v in failed]
    return "\n".join(lines) + "\n"


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    works = yaml.safe_load(WORKS.read_text(encoding="utf-8"))["works"]
    refs = video_refs(works)
    previous = json.loads(STATUS_FILE.read_text(encoding="utf-8")) if STATUS_FILE.exists() else {}
    today = date.today().isoformat()

    with ThreadPoolExecutor(WORKERS) as ex:
        results = dict(zip(refs, ex.map(check_video, refs)))

    status = {}
    newly, recovered, failed = set(), [], []
    for vid, res in results.items():
        prev = previous.get(vid, {})
        if res["status"] in ("unavailable", "suspect"):
            since = prev.get("since") if prev.get("status") == res["status"] else today
            if since == today and prev.get("status") != res["status"]:
                newly.add(vid)
            status[vid] = {"status": res["status"], "reason": res["reason"], "since": since, "checked": today}
        elif res["status"] == "check failed":
            failed.append(vid)
            if prev:
                status[vid] = prev  # keep the last known state
        else:
            if prev.get("status") == "unavailable":
                recovered.append(vid)
            status[vid] = {"status": "ok", "checked": today}

    def entry(vid, s):
        return {"video_id": vid, "reason": s["reason"], "since": s["since"], "refs": refs.get(vid, [])}

    unavailable = sorted((entry(v, s) for v, s in status.items() if s["status"] == "unavailable"), key=lambda u: (u["since"], u["video_id"]))
    suspects = sorted((entry(v, s) for v, s in status.items() if s["status"] == "suspect"), key=lambda u: (u["since"], u["video_id"]))
    status = {v: s for v, s in status.items() if v in refs}  # forget videos no longer in the index

    atomic_write(STATUS_FILE, json.dumps(status, ensure_ascii=False, indent=1) + "\n")
    if unavailable or suspects or recovered or failed:
        atomic_write(DATA / f"deleted-report-{today}.md", report_text(today, unavailable, newly, recovered, failed, suspects))
    print(f"checked {len(results)} videos: {len(unavailable)} unavailable, {len(suspects)} suspect "
          f"({len(newly)} new), {len(recovered)} recovered, {len(failed)} could not be checked")
    return 1 if (newly or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
