"""Daily poll of each channel's RSS feed. Reports videos not seen before.

First run: every video currently in the feeds is recorded as seen, but only the
ones published in the last 24 hours are reported, so today's uploads are not
lost and the older back catalogue is not sent. Use --backfill to report all of
them on the first run instead.

Later runs: each new video goes into data/digest-YYYY-MM-DD.md, marked "in index"
or "not in index" depending on whether its ID appears in malfoid-index/works.yaml.
A channel whose feed fails is reported and retried next run.
"""
import argparse
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

from common import DATA, FEED_URL, SEEN, USER_AGENT, WORKS, atomic_write, load_channels

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def fetch_feed(channel_id: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(FEED_URL.format(channel_id), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_feed(body: bytes, fallback_name: str = "") -> list[dict]:
    root = ET.fromstring(body)
    author = root.findtext("a:author/a:name", namespaces=NS) or fallback_name
    out = []
    for e in root.findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        if not vid:
            continue
        out.append({
            "video_id": vid,
            "channel_id": e.findtext("yt:channelId", namespaces=NS),
            "channel": author,
            "title": e.findtext("a:title", namespaces=NS) or "",
            "published": e.findtext("a:published", namespaces=NS) or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
        })
    return out


RECENT = timedelta(hours=24)


def is_recent(published: str, now: datetime) -> bool:
    try:
        when = datetime.fromisoformat(published.replace("Z", "+00:00"))
    except ValueError:
        return False
    return now - when <= RECENT


def poll(channels: list[dict], fetch, seen: dict, first_run: bool, backfill: bool, today: str,
         now: datetime | None = None) -> dict:
    """Return {"new": [...], "errors": [...], "seen": updated_seen}. Does not touch the disk."""
    now = now or datetime.now(timezone.utc)
    errors, found = [], []
    for c in channels:
        try:
            found.extend(parse_feed(fetch(c["channel_id"]), c.get("name", "")))
        except Exception as exc:  # one bad channel must not stop the others
            errors.append({"channel": c.get("name") or c["channel_id"], "error": str(exc)[:160]})

    unique = {}
    for e in found:
        unique.setdefault(e["video_id"], e)

    updated = dict(seen)
    if first_run and not backfill:
        new = [e for vid, e in unique.items() if is_recent(e["published"], now)]
    else:
        new = [e for vid, e in unique.items() if vid not in seen]
    for vid, e in unique.items():
        if vid not in updated:
            updated[vid] = {"first_seen": today, "channel_id": e["channel_id"]}
    return {"new": new, "errors": errors, "seen": updated}


def digest_text(new: list[dict], errors: list[dict], works_text: str, today: str) -> str:
    lines = [f"# YouTube feed digest, {today}", ""]
    if new:
        lines.append("## New uploads")
        for e in new:
            status = "in index" if e["video_id"] in works_text else "not in index"
            lines.append(f"- [{e['title']}]({e['url']}) — {e['channel']}, {e['published']} — {status}")
        lines.append("")
    if errors:
        lines.append("## Feeds that failed (retried next run)")
        for err in errors:
            lines.append(f"- {err['channel']}: {err['error']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="on the first run, report existing feed videos")
    args = ap.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)
    first_run = not SEEN.exists()
    seen = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.exists() else {}
    today = date.today().isoformat()

    result = poll(load_channels(), fetch_feed, seen, first_run, args.backfill, today)
    if result["new"] or result["errors"]:
        digest = DATA / f"digest-{today}.md"
        atomic_write(digest, digest_text(result["new"], result["errors"], WORKS.read_text(encoding="utf-8"), today))
        print(f"wrote {digest}: {len(result['new'])} new, {len(result['errors'])} failed feeds")
    else:
        print("nothing new")
    atomic_write(SEEN, json.dumps(result["seen"], ensure_ascii=False, indent=0) + "\n")
    if first_run and not args.backfill:
        print(f"first run: recorded {len(result['seen'])} videos as seen; reported only those from the last 24 hours")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
