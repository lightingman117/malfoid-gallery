"""Daily processor: reads the queue, skips videos already handled, and writes a digest.

It does not edit works.yaml. Each new video is marked "in index" when its
video ID already appears in malfoid-index/works.yaml, otherwise "not in index",
so you can decide what to add by hand.
"""
import json
from datetime import date

from common import DATA, PROCESSED, QUEUE, WORKS, load_channels


def key(e: dict) -> str:
    return f"{e['kind']}:{e['video_id']}"


def load_processed() -> set[str]:
    if PROCESSED.exists():
        return set(json.loads(PROCESSED.read_text(encoding="utf-8")))
    return set()


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    if not QUEUE.exists():
        print("queue is empty")
        return
    seen = load_processed()
    works_text = WORKS.read_text(encoding="utf-8")
    names = {c["channel_id"]: c["name"] for c in load_channels()}

    events = [json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
    fresh = [e for e in events if key(e) not in seen]
    if not fresh:
        print("nothing new since the last run")
        return

    new_items, deleted = [], []
    for e in fresh:
        if e["kind"] == "deleted":
            deleted.append(e)
        elif e["video_id"] not in {x["video_id"] for x in new_items}:
            new_items.append(e)

    today = date.today().isoformat()
    lines = [f"# YouTube push digest, {today}", ""]
    if new_items:
        lines.append("## New uploads")
        for e in new_items:
            status = "in index" if e["video_id"] in works_text else "not in index"
            channel = names.get(e["channel_id"], e["channel_id"])
            lines.append(f"- [{e['title']}]({e['url']}) — {channel}, {e['published']} — {status}")
        lines.append("")
    if deleted:
        lines.append("## Deleted or private")
        for e in deleted:
            lines.append(f"- {e['url']} — removed {e['published']}")
        lines.append("")
    digest = DATA / f"digest-{today}.md"
    digest.write_text("\n".join(lines), encoding="utf-8")

    done = seen | {key(e) for e in fresh}
    PROCESSED.write_text(json.dumps(sorted(done)), encoding="utf-8")
    print(f"wrote {digest} ({len(new_items)} new, {len(deleted)} deleted)")


if __name__ == "__main__":
    main()
