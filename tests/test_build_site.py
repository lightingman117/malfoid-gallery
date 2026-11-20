"""Offline regression tests for the site build guardrails.

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_site  # noqa: E402


class WorkUrlsTests(unittest.TestCase):
    def test_collects_nested_links(self):
        w = {
            "url": "https://example.com/a",
            "embed": "https://youtube.com/watch?v=abcdefgh",
            "also": ["https://x.com/creator/status/1"],
            "embed_also": ["https://malfoid.tv/pay"],
            "videos": [
                {"url": "https://x.com/bad/status/2", "also": ["https://youtube.com/@chan"]},
                "https://youtu.be/abcdefgh",
            ],
            "items": [{"url": "https://example.com/item", "also": ["https://malfoid.tv/other"]}],
        }
        urls = build_site.work_urls(w)
        for expected in ("https://malfoid.tv/pay", "https://x.com/bad/status/2",
                         "https://youtube.com/@chan", "https://example.com/item"):
            self.assertIn(expected, urls)

    def test_scalar_list_is_one_item(self):
        self.assertEqual(build_site.work_urls({"also": "https://x.com/a"}), ["https://x.com/a"])


class BlockedHandleTests(unittest.TestCase):
    def test_blocked_handle_in_video_link(self):
        w = {"title": "test", "videos": [{"url": "https://x.com/katechon_studio/status/1"}]}
        self.assertEqual(build_site.blocked_handle(w), "katechon_studio")

    def test_blocked_domain_in_item_link(self):
        w = {"title": "test", "items": [{"title": "part", "also": ["https://malfoid.tv/pay"]}]}
        self.assertEqual(build_site.blocked_handle(w), "malfoid.tv")

    def test_blocked_handle_in_explicit_handles(self):
        self.assertEqual(build_site.blocked_handle({"handles": ["@maelle_gold"]}), "maelle_gold")

    def test_blocked_handle_in_creator_url(self):
        w = {"creator": "https://x.com/katechon_studio"}
        self.assertEqual(build_site.blocked_handle(w), "katechon_studio")

    def test_clean_work(self):
        w = {"creator": "@fan", "url": "https://x.com/fan",
             "videos": [{"url": "https://youtube.com/watch?v=abcdefgh"}]}
        self.assertIsNone(build_site.blocked_handle(w))


class CopyTests(unittest.TestCase):
    def test_missing_media_fails_the_build(self):
        with self.assertRaises(SystemExit):
            build_site.copy("images/definitely-missing-for-tests.jpg", tempfile.mkdtemp())


if __name__ == "__main__":
    unittest.main()
