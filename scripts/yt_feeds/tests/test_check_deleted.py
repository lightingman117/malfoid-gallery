"""Offline tests for the deleted-video checker. Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import check_deleted  # noqa: E402

OK_HTML = '<script>"playabilityStatus":{"status":"OK","playableInEmbed":true}</script>'
DEAD_HTML = '<script>"playabilityStatus":{"status":"ERROR","reason":"This video is unavailable"}</script>'


class RefTests(unittest.TestCase):
    def test_collects_ids_from_urls_and_skips_playlists(self):
        works = [{
            "id": "creator-x", "title": "X",
            "url": "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
            "also": ["https://www.youtube.com/playlist?list=PLabc"],
            "videos": [
                {"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA", "label": "one"},
                "https://youtu.be/BBBBBBBBBBB",
                "https://www.youtube.com/shorts/CCCCCCCCCCC",
                "https://www.youtube.com/embed/videoseries?list=PLabc",
            ],
        }]
        refs = check_deleted.video_refs(works)
        self.assertEqual(set(refs), {"AAAAAAAAAAA", "BBBBBBBBBBB", "CCCCCCCCCCC"})
        self.assertEqual(refs["AAAAAAAAAAA"][0]["entry"], "creator-x")

    def test_same_video_in_two_entries_lists_both(self):
        works = [
            {"id": "a", "title": "A", "videos": ["https://youtu.be/AAAAAAAAAAA"]},
            {"id": "b", "title": "B", "videos": ["https://www.youtube.com/watch?v=AAAAAAAAAAA"]},
        ]
        self.assertEqual([r["entry"] for r in check_deleted.video_refs(works)["AAAAAAAAAAA"]], ["a", "b"])


class ClassifyTests(unittest.TestCase):
    def test_oembed_ok_needs_no_page_read(self):
        r = check_deleted.classify(200, lambda: self.fail("should not read the page"))
        self.assertEqual(r["status"], "ok")

    def test_oembed_fail_but_page_ok_is_not_unavailable(self):
        r = check_deleted.classify(404, lambda: OK_HTML)
        self.assertEqual(r["status"], "ok")

    def test_page_error_is_unavailable_with_reason(self):
        r = check_deleted.classify(404, lambda: DEAD_HTML)
        self.assertEqual(r["status"], "unavailable")
        self.assertIn("ERROR", r["reason"])
        self.assertIn("unavailable", r["reason"])

    def test_unreadable_page_is_check_failed_not_unavailable(self):
        r = check_deleted.classify(404, lambda: None)
        self.assertEqual(r["status"], "check failed")

    def test_page_without_status_is_unavailable(self):
        r = check_deleted.classify(404, lambda: "<html>no data</html>")
        self.assertEqual(r["status"], "unavailable")


class ReportTests(unittest.TestCase):
    def test_report_marks_new_and_lists_refs(self):
        unavailable = [{"video_id": "AAAAAAAAAAA", "reason": "ERROR: gone", "since": "2026-11-18",
                        "refs": [{"entry": "creator-x", "title": "X", "url": "https://youtu.be/AAAAAAAAAAA"}]}]
        text = check_deleted.report_text("2026-11-18", unavailable, {"AAAAAAAAAAA"}, [], [])
        self.assertIn("(new)", text)
        self.assertIn("creator-x", text)


if __name__ == "__main__":
    unittest.main()
