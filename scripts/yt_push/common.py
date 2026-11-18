"""Shared paths and settings for the YouTube push-notification tools."""
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = Path(os.environ.get("YT_PUSH_DATA", HERE / "data"))
QUEUE = DATA / "queue.jsonl"
PROCESSED = DATA / "processed.json"
CHANNELS = HERE / "channels.json"
WORKS = REPO / "malfoid-index" / "works.yaml"
HUB = "https://pubsubhubbub.appspot.com/subscribe"
LEASE_SECONDS = 432000  # 5 days; subscribe.py must run again before this lapses


def topic_for(channel_id: str) -> str:
    return f"https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}"


def load_channels() -> list[dict]:
    import json
    return json.loads(CHANNELS.read_text(encoding="utf-8"))["channels"]
