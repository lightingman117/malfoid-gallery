"""Sort YouTube search results for Malfoid into new, known, possible duplicate and blocked.

Input: a JSON list of results gathered from a YouTube search page, one object per video:
    {"id": "VIDEO_ID", "title": "...", "channel": "Name", "channel_url": "https://www.youtube.com/@handle",
     "age": "3 hours ago", "duration": "12:04"}

Output: a markdown report (scripts/yt_search/data/yt-search-YYYY-MM-DD.md) and a summary on stdout.
Read only: it never edits works.yaml or the feed data.

Usage:
    python3 scripts/yt_search/dedupe.py results.json [--date YYYY-MM-DD]
"""
import argparse
import datetime
import difflib
import json
import os
import re
import sys
import tempfile
import urllib.parse

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORKS = os.path.join(ROOT, "malfoid-index", "works.yaml")
GREYLIST = os.path.join(ROOT, "malfoid-index", "greylist.yaml")
BUILD = os.path.join(ROOT, "scripts", "build_site.py")
SEEN = os.path.join(ROOT, "scripts", "yt_feeds", "data", "seen.json")
DATA = os.path.join(ROOT, "scripts", "yt_search", "data")

VIDEO_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtube\.com/shorts/|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{6,20})")
HANDLE_RE = re.compile(r"(?:youtube\.com)?/@([^/?#\s]+)", re.I)  # also matches the relative /@handle of a search result
CHANNEL_RE = re.compile(r"youtube\.com/channel/(UC[A-Za-z0-9_-]+)", re.I)
SIMILAR = 0.85  # title similarity above this counts as a possible duplicate


def blocked_accounts():
    """The BLOCKED_ACCOUNTS set in build_site.py, read as text so the build module is not imported."""
    text = open(BUILD, encoding="utf-8").read()
    m = re.search(r"BLOCKED_ACCOUNTS = \{(.*?)\n\}", text, re.S)
    return {h.lower() for h in re.findall(r'"([^"]+)"', m.group(1))} if m else set()


def handle_of(text):
    """The channel handle in a URL or a relative /@handle, decoded and lower-cased."""
    m = HANDLE_RE.search(text or "")
    return urllib.parse.unquote(m.group(1)).lower() if m else ""


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def index_maps(works):
    """Video ids, channel handles and channel ids, and index titles, each mapped to the entry id."""
    video_ids, channels, titles = {}, {}, []

    def scan_urls(entry_id, urls):
        for u in urls:
            for m in VIDEO_RE.finditer(str(u or "")):
                video_ids.setdefault(m.group(1), entry_id)
            h = handle_of(str(u or ""))
            if h:
                channels.setdefault(h, entry_id)
            m = CHANNEL_RE.search(str(u or ""))
            if m:
                channels.setdefault(m.group(1), entry_id)

    for w in works:
        wid = w.get("id", "?")
        titles.append((norm(w.get("title")), wid))
        urls = [w.get("url"), w.get("embed")] + (w.get("also") or [])
        for v in w.get("videos") or []:
            if isinstance(v, dict):
                urls += [v.get("url"), v.get("embed")] + (v.get("also") or [])
                titles.append((norm(v.get("label")), wid))
            else:
                urls.append(v)
        for it in w.get("items") or []:
            urls += [it.get("url")] + (it.get("also") or [])
        scan_urls(wid, urls)
    return video_ids, channels, titles


def seen_ids():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return set(json.load(f).keys())
    except (OSError, ValueError):
        return set()


def classify(result, video_ids, channels, titles, blocked, seen):
    vid = result["id"]
    handle = handle_of(result.get("channel_url"))
    chan_id = CHANNEL_RE.search(result.get("channel_url") or "")
    chan_id = chan_id.group(1) if chan_id else ""
    if vid in video_ids:
        return "known", video_ids[vid], ""
    if handle in blocked or (result.get("channel") or "").lower() in blocked:
        return "blocked", "", f"channel @{handle or result.get('channel')} is on the blocklist"
    t = norm(result.get("title"))
    best, best_id = 0.0, ""
    for label, wid in titles:
        if not label:
            continue
        r = difflib.SequenceMatcher(None, t, label).ratio()
        if r > best:
            best, best_id = r, wid
    if best >= SIMILAR:
        return "possible duplicate", best_id, f"title is {best:.0%} similar to an index title"
    chan_entry = channels.get(handle) or channels.get(chan_id) or ""
    if chan_entry:
        return "new upload from indexed creator", chan_entry, "creator already in the index"
    if vid in seen:
        return "seen in feed", "", "already reported by the RSS poll"
    return "new", "", ""


def write_report(path, rows, date):
    lines = [f"# YouTube search check, {date}", ""]
    groups = {}
    for row in rows:
        groups.setdefault(row["status"], []).append(row)
    order = ["new", "new upload from indexed creator", "possible duplicate", "blocked", "seen in feed", "known"]
    for status in order:
        items = groups.get(status, [])
        if not items:
            continue
        lines.append(f"## {status} ({len(items)})")
        for r in items:
            note = f" - {r['note']}" if r["note"] else ""
            ref = f" [index: {r['match']}]" if r["match"] else ""
            lines.append(f"- [{r['title']}](https://www.youtube.com/watch?v={r['id']}) - {r['channel']}, {r['age']}, {r['duration']}{ref}{note}")
        lines.append("")
    lines.append("Read only. Nothing in works.yaml or the feed data was changed.")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", help="JSON file of search results")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args(argv)
    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)
    works = yaml.safe_load(open(WORKS, encoding="utf-8"))["works"]
    works += yaml.safe_load(open(GREYLIST, encoding="utf-8")).get("works") or []
    video_ids, channels, titles = index_maps(works)
    blocked, seen = blocked_accounts(), seen_ids()
    rows = []
    for r in results:
        status, match, note = classify(r, video_ids, channels, titles, blocked, seen)
        rows.append({**r, "status": status, "match": match, "note": note,
                     "title": r.get("title", ""), "channel": r.get("channel", ""),
                     "age": r.get("age", ""), "duration": r.get("duration", "")})
    out = os.path.join(DATA, f"yt-search-{args.date}.md")
    write_report(out, rows, args.date)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"{len(rows)} results: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
