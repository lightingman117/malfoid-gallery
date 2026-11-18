"""Rebuild channels.json from the YouTube channel links in works.yaml.

Each handle or legacy URL is resolved to its UC... channel ID by reading the
channel page. If a channel cannot be resolved now, its entry from the previous
channels.json is kept and a warning is printed.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import CHANNELS, USER_AGENT, WORKS, atomic_write, load_channels

URL_RE = re.compile(r"""https?://(?:www\.|m\.)?youtube\.com/([^"\s,}\]'<>]*)""")
NOT_CHANNELS = {"watch", "shorts", "playlist", "embed", "feeds", "results"}
CANONICAL_RE = re.compile(r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"')
ANY_CHANNEL_RE = re.compile(r"youtube\.com/channel/(UC[\w-]{22})")
TITLE_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')
# Channels linked from the index that no longer exist. Skipped so the daily poll stays clean.
# Papallax (creator-papallax): account deleted; its videos are being sought elsewhere.
EXCLUDED = {"channel/uc_ys3lsi6f63bil1tnepn0w"}


def extract_targets(text: str) -> list[str]:
    """Return the distinct channel keys linked from the index text, in order.

    Keys are "@handle", "legacy" custom names, "channel/UC..." or "c/..." / "user/...".
    Video, Shorts and playlist links are skipped.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in URL_RE.finditer(text):
        path = m.group(1).split("?")[0].split("#")[0]
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        if parts[0].startswith("@"):
            key = parts[0]
        elif parts[0] == "channel" and len(parts) > 1 and parts[1].startswith("UC"):
            key = f"channel/{parts[1]}"
        elif parts[0] in ("c", "user") and len(parts) > 1:
            key = f"{parts[0]}/{parts[1]}"
        elif len(parts) == 1 and parts[0] not in NOT_CHANNELS:
            key = parts[0]
        else:
            continue
        key = urllib.parse.unquote(key)
        if key.lower() not in seen:
            seen.add(key.lower())
            out.append(key)
    return out


def fetch_html(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def resolve(key: str, fetch=fetch_html) -> dict:
    """Return {handle, channel_id, name}. Raises ValueError if no channel ID is found."""
    html = fetch("https://www.youtube.com/" + urllib.parse.quote(key))
    m = CANONICAL_RE.search(html) or ANY_CHANNEL_RE.search(html)
    if not m:
        raise ValueError(f"no channel ID on the page for {key}")
    t = TITLE_RE.search(html)
    return {"handle": key, "channel_id": m.group(1), "name": t.group(1) if t else key}


def build(text: str, previous: list[dict], fetch=fetch_html) -> tuple[list[dict], list[str]]:
    """Return (channels, warnings). Previous entries are kept for channels that fail to resolve."""
    targets = [k for k in extract_targets(text) if k.lower() not in EXCLUDED]
    prev_by_handle = {c["handle"].lower(): c for c in previous}
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda k: _safe_resolve(k, fetch), targets))
    channels, warnings = [], []
    for key, (ok, value) in zip(targets, results):
        if ok:
            channels.append(value)
        elif key.lower() in prev_by_handle:
            channels.append(prev_by_handle[key.lower()])
            warnings.append(f"kept previous entry for {key}: {value}")
        else:
            warnings.append(f"skipped {key}: {value}")
    unique: dict[str, dict] = {}
    for c in channels:
        unique.setdefault(c["channel_id"], c)
    ordered = sorted(unique.values(), key=lambda c: c["name"].lower())
    return ordered, warnings


def _safe_resolve(key: str, fetch):
    try:
        return True, resolve(key, fetch)
    except Exception as exc:  # network errors, odd pages: report, don't crash
        return False, str(exc)[:120]


def main() -> int:
    text = WORKS.read_text(encoding="utf-8")
    previous = load_channels() if CHANNELS.exists() else []
    channels, warnings = build(text, previous)
    doc = {
        "_note": "YouTube channels linked from malfoid-index/works.yaml. Rebuilt by build_channels.py.",
        "channels": channels,
    }
    atomic_write(CHANNELS, json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(channels)} channels written to {CHANNELS}")
    for w in warnings:
        print("warning:", w)
    return 1 if any(w.startswith("skipped") for w in warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
