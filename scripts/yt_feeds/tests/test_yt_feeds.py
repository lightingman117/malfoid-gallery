"""Offline tests for the feed poll and the channel extraction. Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_channels  # noqa: E402
import poll_feeds  # noqa: E402

FEED_A = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
<author><name>Channel A</name></author>
<entry><yt:videoId>AAAAAAAAAAA</yt:videoId><yt:channelId>UCAAAAAAAAAAAAAAAAAAAAAA</yt:channelId>
<title>Old video</title><published>2026-11-01T10:00:00+00:00</published></entry>
<entry><yt:videoId>BBBBBBBBBBB</yt:videoId><yt:channelId>UCAAAAAAAAAAAAAAAAAAAAAA</yt:channelId>
<title>New video</title><published>2026-11-18T10:00:00+00:00</published></entry>
</feed>"""

FEED_B = FEED_A.replace(b"AAAAAAAAAAA", b"CCCCCCCCCCC").replace(b"BBBBBBBBBBB", b"DDDDDDDDDDD").replace(b"Channel A", b"Channel B")

CHANNELS = [
    {"name": "Channel A", "handle": "@a", "channel_id": "UCAAAAAAAAAAAAAAAAAAAAAA"},
    {"name": "Channel B", "handle": "@b", "channel_id": "UCBBBBBBBBBBBBBBBBBBBBBB"},
]


def fetch_ok(channel_id):
    return FEED_A if channel_id.startswith("UCA") else FEED_B


class ParseTests(unittest.TestCase):
    def test_parse_feed_reads_ids_titles_and_channel(self):
        entries = poll_feeds.parse_feed(FEED_A)
        self.assertEqual([e["video_id"] for e in entries], ["AAAAAAAAAAA", "BBBBBBBBBBB"])
        self.assertEqual(entries[1]["title"], "New video")
        self.assertEqual(entries[1]["channel"], "Channel A")
        self.assertTrue(entries[1]["url"].endswith("v=BBBBBBBBBBB"))


class PollTests(unittest.TestCase):
    def test_first_run_seeds_seen_without_new_items(self):
        from datetime import datetime, timezone
        much_later = datetime(2030, 1, 1, tzinfo=timezone.utc)  # every fixture entry is now older than 24 hours
        r = poll_feeds.poll(CHANNELS, fetch_ok, {}, first_run=True, backfill=False, today="2026-11-18", now=much_later)
        self.assertEqual(r["new"], [])
        self.assertEqual(r["errors"], [])
        self.assertEqual(set(r["seen"]), {"AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC", "DDDDDDDDDDD"})

    def test_first_run_reports_only_last_24_hours(self):
        from datetime import datetime, timezone
        now = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
        r = poll_feeds.poll(CHANNELS, fetch_ok, {}, first_run=True, backfill=False, today="2026-11-18", now=now)
        # FEED_A's "BBBBBBBBBBB" is published 2026-11-18T10:00 (recent); "AAAAAAAAAAA" is 2026-11-01 (old)
        self.assertEqual({e["video_id"] for e in r["new"]}, {"BBBBBBBBBBB", "DDDDDDDDDDD"})
        self.assertEqual(len(r["seen"]), 4)

    def test_backfill_reports_existing_on_first_run(self):
        r = poll_feeds.poll(CHANNELS, fetch_ok, {}, first_run=True, backfill=True, today="2026-11-18")
        self.assertEqual(len(r["new"]), 4)

    def test_later_run_reports_only_unseen_videos(self):
        seen = {"AAAAAAAAAAA": {}, "BBBBBBBBBBB": {}, "CCCCCCCCCCC": {}}
        r = poll_feeds.poll(CHANNELS, fetch_ok, seen, first_run=False, backfill=False, today="2026-11-19")
        self.assertEqual([e["video_id"] for e in r["new"]], ["DDDDDDDDDDD"])
        self.assertIn("DDDDDDDDDDD", r["seen"])

    def test_failing_channel_is_reported_and_not_marked_seen(self):
        def fetch(channel_id):
            if channel_id.startswith("UCB"):
                raise OSError("timeout")
            return FEED_A
        seen = {"AAAAAAAAAAA": {}, "BBBBBBBBBBB": {}}
        r = poll_feeds.poll(CHANNELS, fetch, seen, first_run=False, backfill=False, today="2026-11-19")
        self.assertEqual(r["new"], [])
        self.assertEqual([e["channel"] for e in r["errors"]], ["Channel B"])
        self.assertNotIn("CCCCCCCCCCC", r["seen"])

    def test_digest_marks_index_membership(self):
        new = [{"video_id": "BBBBBBBBBBB", "channel": "Channel A", "published": "x", "title": "T", "url": "u"}]
        text = poll_feeds.digest_text(new, [], "something BBBBBBBBBBB here", "2026-11-18")
        self.assertIn("in index", text)
        text2 = poll_feeds.digest_text(new, [], "nothing", "2026-11-18")
        self.assertIn("not in index", text2)


class ChannelExtractionTests(unittest.TestCase):
    def test_extracts_handles_legacy_and_channel_urls_and_skips_videos(self):
        text = (
            'url: "https://www.youtube.com/@Zandran2/videos"\n'
            'x: "https://youtube.com/watch?v=abcdefghijk"\n'
            'y: "https://www.youtube.com/@zandran2"\n'
            'z: "https://www.youtube.com/thelorelounge"\n'
            'w: "https://www.youtube.com/channel/UC_Ys3Lsi6F63BiL1TNEpn0w"\n'
            'v: "https://www.youtube.com/playlist?list=PL123"\n'
            'u: "https://www.youtube.com/%EC%BA%A3%EC%A5%90-n4l"\n'
        )
        keys = build_channels.extract_targets(text)
        self.assertEqual(keys, ["@Zandran2", "thelorelounge", "channel/UC_Ys3Lsi6F63BiL1TNEpn0w", "캣쥐-n4l"])

    def test_build_keeps_previous_entry_when_resolve_fails(self):
        previous = [{"name": "Old name", "handle": "@gone", "channel_id": "UCGONEGONEGONEGONEGONEGO"}]
        def fetch(url):
            raise OSError("network down")
        channels, warnings = build_channels.build('"https://www.youtube.com/@gone"', previous, fetch=fetch)
        self.assertEqual(channels, previous)
        self.assertTrue(any("kept previous entry" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
