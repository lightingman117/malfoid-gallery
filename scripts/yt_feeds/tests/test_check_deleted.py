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
    def test_both_signals_fine_is_ok(self):
        self.assertEqual(check_deleted.classify(200, 200, OK_HTML)["status"], "ok")

    def test_page_ok_but_oembed_fails_is_suspect(self):
        r = check_deleted.classify(404, 200, OK_HTML)
        self.assertEqual(r["status"], "suspect")
        self.assertIn("404", r["reason"])

    def test_page_error_is_unavailable_with_reason(self):
        r = check_deleted.classify(404, 200, DEAD_HTML)
        self.assertEqual(r["status"], "unavailable")
        self.assertIn("ERROR", r["reason"])

    def test_page_404_is_unavailable(self):
        self.assertEqual(check_deleted.classify(404, 404, "")["status"], "unavailable")

    def test_unreadable_page_is_check_failed(self):
        self.assertEqual(check_deleted.classify(200, None, None)["status"], "check failed")

    def test_page_without_status_is_check_failed_not_unavailable(self):
        self.assertEqual(check_deleted.classify(200, 200, "<html>no data</html>")["status"], "check failed")


class ReportTests(unittest.TestCase):
    def test_report_marks_new_and_lists_refs(self):
        unavailable = [{"video_id": "AAAAAAAAAAA", "reason": "ERROR: gone", "since": "2026-11-18",
                        "refs": [{"entry": "creator-x", "title": "X", "url": "https://youtu.be/AAAAAAAAAAA"}]}]
        text = check_deleted.report_text("2026-11-18", unavailable, {"AAAAAAAAAAA"}, [], [])
        self.assertIn("(new)", text)
        self.assertIn("creator-x", text)


if __name__ == "__main__":
    unittest.main()
