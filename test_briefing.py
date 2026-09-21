import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import briefing as b

LOG = """[2026-09-16T03:04:12-0500] [ALPM] transaction started
[2026-09-16T03:04:12-0500] [ALPM] upgraded omarchy (4.0.3-1 -> 4.0.4-1)
[2026-09-16T03:04:12-0500] [ALPM] transaction completed
[2026-09-16T03:04:20-0500] [ALPM] transaction started
[2026-09-16T03:04:20-0500] [ALPM] installed linux-omarchy (7.2.5-3)
[2026-09-16T03:04:21-0500] [ALPM] transaction completed
[2026-09-16T03:04:24-0500] [ALPM-SCRIPTLET] ==> dkms install --no-depmod nvidia/610.57.04 -k 7.2.5-3-omarchy
[2026-09-16T03:05:49-0500] [ALPM] transaction started
[2026-09-16T03:05:49-0500] [ALPM] upgraded google-chrome (153.0.8010.36-1 -> 153.0.8010.47-1)
[2026-09-16T03:05:49-0500] [ALPM] transaction completed
node 26.7.0 → 26.8.2 (available)
"""
RSS = b'''<rss version="2.0"><channel><item><title>News &amp; more</title><link>https://omarchy.org/news/example#section</link><pubDate>Wed, 16 Sep 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;Hello&lt;/p&gt;&lt;script&gt;bad()&lt;/script&gt;</description></item><item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>'''
ATOM = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>42</id><title>v4.0.4</title><updated>2026-09-15T22:15:08Z</updated><link rel="alternate" href="https://github.com/omacom/omarchy/releases/tag/v4.0.4"/><content type="html">&lt;p&gt;A new kernel.&lt;/p&gt;</content></entry></feed>'''


class EvidenceTests(unittest.TestCase):
    def test_installs_rebuilds_and_available_are_different(self):
        txs = b.parse_log(LOG)
        changes = [x for tx in txs for x in tx["changes"]]
        self.assertEqual([x["package"] for x in changes], ["google-chrome", "linux-omarchy", "omarchy"])
        self.assertEqual(changes[1]["oldVersion"], None)
        self.assertEqual(txs[1]["rebuilds"][0]["version"], "610.57.04")
        self.assertEqual(txs[1]["status"], "Completed")

    def test_interrupted_transaction_is_not_completed(self):
        txs = b.parse_log(LOG + "[2026-09-16T04:00:00-0500] [ALPM] transaction started\n[2026-09-16T04:00:01-0500] [ALPM] upgraded example (1.0-1 -> 1.0-2)\n")
        self.assertEqual(txs[0]["status"], "Incomplete record")
        self.assertIsNone(txs[0]["completed"])
        self.assertIn("Packaging revision", txs[0]["changes"][0]["changeKind"])

    def test_new_transaction_does_not_complete_abandoned_transaction(self):
        txs = b.parse_log("[2026-09-15T04:00:00-0500] [ALPM] transaction started\n[2026-09-15T04:00:01-0500] [ALPM] installed example (1.0-1)\n" + LOG)
        self.assertEqual(txs[-1]["status"], "Incomplete record")

    def test_remove_reinstall_and_downgrade(self):
        log = "[2026-09-16T04:00:00-0500] [ALPM] transaction started\n"
        for action in ("removed foo (1.0-1)", "reinstalled bar (2.0-1)", "downgraded baz (3.0-1 -> 2.0-1)"):
            log += f"[2026-09-16T04:00:01-0500] [ALPM] {action}\n"
        changes = b.parse_log(log)[0]["changes"]
        self.assertIsNone(changes[0]["newVersion"])
        self.assertEqual(changes[1]["oldVersion"], changes[1]["newVersion"])
        self.assertEqual(changes[2]["newVersion"], "2.0-1")


class FeedTests(unittest.TestCase):
    def test_rss_strips_markup_and_rejects_executable_urls(self):
        items = b.parse_feed(RSS, "official")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["excerpt"], "Hello")
        self.assertNotIn("#", items[0]["url"])
        self.assertEqual(items[0]["published"], "2026-09-16T12:00:00+00:00")

    def test_atom_and_unsafe_xml(self):
        self.assertEqual(b.parse_feed(ATOM, "releases")[0]["title"], "v4.0.4")
        for body in (b"<html>blocked</html>", b'<!DOCTYPE rss><rss/>', b"x" * 2_000_001):
            with self.assertRaises(ValueError):
                b.parse_feed(body, "official")

    def test_failed_refresh_preserves_cache(self):
        previous = {"items": b.parse_feed(RSS, "official"), "lastSuccess": "2026-09-15T00:00:00Z"}
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.HTTPError("url", 429, "Rate limited", {}, None)):
            result = b.fetch_source("official", previous)
        self.assertEqual(result["items"], previous["items"])
        self.assertEqual(result["lastSuccess"], previous["lastSuccess"])
        self.assertIn("429", result["error"])

    def test_304_preserves_cache_and_marks_success(self):
        previous = {"items": b.parse_feed(RSS, "official"), "etag": "v1"}
        with patch("urllib.request.OpenerDirector.open", side_effect=urllib.error.HTTPError("url", 304, "Unchanged", {}, None)):
            result = b.fetch_source("official", previous)
        self.assertEqual(result["items"], previous["items"])
        self.assertIsNone(result["error"])
        self.assertTrue(result["lastSuccess"])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.log = self.directory / "pacman.log"
        self.log.write_text(LOG)

    def test_read_state_persists_and_unknown_settings_rejected(self):
        item = b.parse_feed(RSS, "official")[0]
        b.write_json(self.directory / "news.json", {"official": {"items": [item]}})
        self.assertEqual(b.status(self.directory, self.log)["unread"], 1)
        b.action(self.directory, self.log, {"action": "read", "ids": [item["id"]]})
        self.assertEqual(b.status(self.directory, self.log)["unread"], 0)
        with self.assertRaises(ValueError):
            b.action(self.directory, self.log, {"action": "settings", "settings": {"intervalHours": 1, "enabledSources": []}})

    def test_manual_and_recent_checks_do_not_fetch(self):
        with patch("briefing.fetch_source") as fetch:
            b.refresh(self.directory)
            fetch.assert_not_called()
            b.write_json(self.directory / "settings.json", {"intervalHours": 6, "enabledSources": ["official"]})
            b.write_json(self.directory / "news.json", {"official": {"lastAttempt": b.now(), "items": []}})
            b.refresh(self.directory)
            fetch.assert_not_called()

    def test_overdue_source_refreshes_and_disabled_source_does_not(self):
        b.write_json(self.directory / "settings.json", {"intervalHours": 2, "enabledSources": ["official"]})
        with patch("briefing.fetch_source", return_value={"items": [], "lastAttempt": b.now()}) as fetch:
            b.refresh(self.directory)
            self.assertEqual(fetch.call_args.args[0], "official")
            self.assertEqual(fetch.call_count, 1)

    def test_only_matching_release_is_attached(self):
        b.write_json(self.directory / "news.json", {"releases": {"items": b.parse_feed(ATOM, "releases")}})
        txs = b.status(self.directory, self.log)["transactions"]
        self.assertIn("releaseUrl", txs[-1]["changes"][0])
        self.assertNotIn("releaseUrl", txs[0]["changes"][0])
        self.log.write_text(LOG.replace("4.0.4-1", "4.0.2-1"))
        self.assertNotIn("releaseUrl", b.status(self.directory, self.log)["transactions"][-1]["changes"][0])

    def test_corrupt_state_is_not_overwritten(self):
        path = self.directory / "settings.json"
        path.write_text("broken")
        with self.assertRaises(json.JSONDecodeError):
            b.refresh(self.directory)
        self.assertEqual(path.read_text(), "broken")
        report = b.status(self.directory, self.log)
        self.assertEqual(len(report["transactions"]), 3)
        self.assertIn("Original file preserved", report["newsError"])

    def test_broken_news_does_not_hide_updates_and_missing_log_does_not_hide_news(self):
        cache = self.directory / "news.json"
        cache.write_text("broken")
        report = b.status(self.directory, self.log)
        self.assertEqual(len(report["transactions"]), 3)
        self.assertTrue(report["newsError"])
        b.write_json(cache, {"official": {"items": b.parse_feed(RSS, "official")}})
        report = b.status(self.directory, self.directory / "missing.log")
        self.assertEqual(len(report["news"]), 1)
        self.assertTrue(report["logError"])


if __name__ == "__main__":
    unittest.main()
