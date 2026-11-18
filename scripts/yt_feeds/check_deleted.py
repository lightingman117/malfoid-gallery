"""Daily check for YouTube videos linked from the index that may have been deleted.

For every YouTube video ID in malfoid-index/works.yaml:
  1. oEmbed. HTTP 200 means the video is fine.
  2. If oEmbed fails, read the watch page. oEmbed has given false "not found"
     results for working Shorts, so the page's playabilityStatus decides.
     "OK" means fine; anything else is reported as unavailable with its reason.
  3. A network error is reported as "check failed", never as unavailable.

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
WORKERS = 4
PAUSE = 0.2


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


def http_get(url: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""


def classify(oembed_status: int, watch_html_fn) -> dict:
    """Return {"status": "ok" | "unavailable" | "check failed", "reason": str}."""
    if oembed_status == 200:
        return {"status": "ok", "reason": ""}
    html = watch_html_fn()
    if html is None:
        return {"status": "check failed", "reason": f"oEmbed HTTP {oembed_status}, watch page unreadable"}
    m = PLAYABILITY_RE.search(html)
    if not m:
        return {"status": "unavailable", "reason": f"oEmbed HTTP {oembed_status}, no playability status on the page"}
    if m.group(1) == "OK":
        return {"status": "ok", "reason": f"oEmbed HTTP {oembed_status} but the page says OK"}
    return {"status": "unavailable", "reason": f"{m.group(1)}: {m.group(2) or 'no reason given'}"}


def check_video(vid: str) -> dict:
    time.sleep(PAUSE)
    watch = f"https://www.youtube.com/watch?v={vid}"
    try:
        oembed_status, _ = http_get("https://www.youtube.com/oembed?url=" + urllib.parse.quote(watch, safe="") + "&format=json")
    except Exception as exc:
        return {"status": "check failed", "reason": str(exc)[:120]}

    def watch_html():
        try:
            code, html = http_get(watch)
            return html if code == 200 else None
        except Exception:
            return None

    result = classify(oembed_status, watch_html)
    result["checked"] = date.today().isoformat()
    return result


def report_text(today: str, unavailable: list[dict], newly: set[str], recovered: list[str], failed: list[str]) -> str:
    lines = [f"# Deleted-video check, {today}", ""]
    lines.append(f"## Unavailable ({len(unavailable)}). Verify each one by hand before editing the index")
    for u in unavailable:
        flag = " (new)" if u["video_id"] in newly else ""
        lines.append(f"- {u['video_id']}{flag}: {u['reason']} — since {u['since']}")
        for r in u["refs"]:
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
        if res["status"] == "unavailable":
            since = prev.get("since") if prev.get("status") == "unavailable" else today
            if since == today and prev.get("status") != "unavailable":
                newly.add(vid)
            status[vid] = {"status": "unavailable", "reason": res["reason"], "since": since, "checked": today}
        elif res["status"] == "check failed":
            failed.append(vid)
            if prev:
                status[vid] = prev  # keep the last known state
        else:
            if prev.get("status") == "unavailable":
                recovered.append(vid)
            status[vid] = {"status": "ok", "checked": today}

    unavailable = [
        {"video_id": vid, "reason": s["reason"], "since": s["since"], "refs": refs.get(vid, [])}
        for vid, s in status.items() if s.get("status") == "unavailable"
    ]
    unavailable.sort(key=lambda u: (u["since"], u["video_id"]))

    atomic_write(STATUS_FILE, json.dumps(status, ensure_ascii=False, indent=1) + "\n")
    if unavailable or recovered or failed:
        atomic_write(DATA / f"deleted-report-{today}.md", report_text(today, unavailable, newly, recovered, failed))
    print(f"checked {len(results)} videos: {len(unavailable)} unavailable ({len(newly)} new), "
          f"{len(recovered)} recovered, {len(failed)} could not be checked")
    return 1 if (newly or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
