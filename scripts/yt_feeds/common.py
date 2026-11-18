"""Shared paths and helpers for the daily YouTube RSS poll."""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = Path(os.environ.get("YT_FEEDS_DATA", HERE / "data"))
CHANNELS = HERE / "channels.json"
WORKS = REPO / "malfoid-index" / "works.yaml"
SEEN = DATA / "seen.json"
FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
USER_AGENT = "malfoid-index-feed-poll/1.0 (local script)"


def load_channels(path: Path = CHANNELS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["channels"]


def atomic_write(path: Path, text: str) -> None:
    """Write via a temp file so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
