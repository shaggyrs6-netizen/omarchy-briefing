import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import changes as c


def record(**kw):
    return dict(title="Example", why="Try a useful tool", details="", backup="", undo="",
                evidence="", date="2026-09-30", kind="Software", status="Trying it") | kw


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def test_empty_read_does_not_create_state(self):
        self.assertEqual(c.listing(self.path)["entries"], [])
        self.assertEqual(list(self.path.iterdir()), [])

    def test_save_and_edit_keep_identity_and_backup(self):
        result = c.save(self.path, {"record": record()})
        old = result["entries"][0]
        edited = c.save(self.path, {"record": record(why="Changed reason"), "id": old["id"], "expectedUpdatedAt": old["updatedAt"]})["entries"][0]
        self.assertEqual(edited["id"], old["id"])
        self.assertEqual(edited["createdAt"], old["createdAt"])
        self.assertEqual(json.loads((self.path / "records.previous.json").read_text())["entries"][0], old)
        self.assertEqual((self.path / "records.json").stat().st_mode & 0o777, 0o600)

    def test_stale_edit_refused(self):
        old = c.save(self.path, {"record": record()})["entries"][0]
        with self.assertRaisesRegex(ValueError, "changed elsewhere"):
            c.save(self.path, {"record": record(), "id": old["id"], "expectedUpdatedAt": "old"})

    def test_corruption_preserved(self):
        path = self.path / "records.json"
        path.write_text("broken")
        with self.assertRaises(ValueError):
            c.save(self.path, {"record": record()})
        self.assertEqual(path.read_text(), "broken")

    def test_invalid_fields_and_dates(self):
        for update in ({"title":""}, {"why":""}, {"date":"2026-02-30"}, {"status":"Installed"}, {"title":"x"*161}, {"undo":42}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                c.validate(record(**update))

    def test_commands_are_inert(self):
        marker = self.path / "must-not-exist"
        saved = c.save(self.path, {"record": record(undo=f"touch {marker}", details="<script>alert(1)</script>")})
        self.assertFalse(marker.exists())
        self.assertIn("<script>", saved["entries"][0]["details"])

    def test_size_limit_preserves_original(self):
        c.save(self.path, {"record": record()})
        before = (self.path / "records.json").read_bytes()
        with patch.object(c, "MAX_BYTES", 1), self.assertRaises(ValueError):
            c.save(self.path, {"record": record()})
        self.assertEqual(before, (self.path / "records.json").read_bytes())

    def test_detection_baseline_and_changes(self):
        a = {"package:x": {"name":"x", "version":"1", "kind":"Software"}}
        baseline = c.compare(None, a, "2026-09-30T10:00:00+00:00")
        self.assertEqual(baseline["events"], [])
        b = {"package:x": {"name":"x", "version":"2", "kind":"Software"},
             "plugin:y": {"name":"Y", "version":"1", "revision":"abc", "kind":"Plugin"}}
        changed = c.compare(baseline, b, "2026-09-30T11:00:00+00:00")
        self.assertEqual(len(changed["events"]), 2)
        self.assertEqual(changed["events"][0]["since"], baseline["checkedAt"])
        self.assertEqual(len(c.compare(changed, b, "2026-09-30T12:00:00+00:00")["events"]), 2)
        self.assertEqual(c.compare(changed, {}, "2026-09-30T12:00:00+00:00")["events"][-1]["change"], "No longer listed")

    def test_scan_failure_preserves_baseline(self):
        with patch.object(c, "inventory", return_value={}):
            c.scan(self.path, True)
        before = (self.path / "observed.json").read_bytes()
        with patch.object(c, "inventory", side_effect=OSError("unavailable")), self.assertRaises(OSError):
            c.scan(self.path, True)
        self.assertEqual(before, (self.path / "observed.json").read_bytes())

    def test_corrupt_detection_does_not_block_manual_records(self):
        (self.path / "observed.json").write_text("broken")
        result = c.save(self.path, {"record": record()})
        self.assertEqual(len(result["entries"]), 1)
        self.assertIn("invalid", result["detectionError"])

    def test_event_handling(self):
        baseline = c.compare(None, {}, c.now())
        changed = c.compare(baseline, {"package:x":{"name":"X", "version":"1", "kind":"Software"}}, c.now())
        c.write_observations(self.path, changed)
        identity = c.listing(self.path)["pending"][0]["id"]
        c.handle_event(self.path, identity)
        self.assertEqual(c.listing(self.path)["pending"], [])
        self.assertEqual(len(c.read_observations(self.path)["events"]), 1)

    def test_due_scan_avoids_repeated_inventory(self):
        with patch.object(c, "inventory", return_value={}) as scan:
            c.scan(self.path)
            c.scan(self.path)
        self.assertEqual(scan.call_count, 1)

    def test_inventory_covers_packages_and_plugin_git_revisions(self):
        plugins = self.path / "omarchy/plugins/example"
        plugins.mkdir(parents=True)
        (plugins / "manifest.json").write_text(json.dumps({"name":"Example plugin", "version":"1.0"}))
        (plugins / ".git").mkdir()
        def command(args, **kw):
            if args[0] == "pacman":
                kw["stdout"].write(b"example 1.2-1\n")
                return c.subprocess.CompletedProcess(args, 0)
            return c.subprocess.CompletedProcess(args, 0, stdout="abcdef\n")
        with patch.dict(os.environ, {"XDG_CONFIG_HOME":str(self.path)}), patch.object(c.subprocess, "run", side_effect=command):
            rows = c.inventory()
        self.assertEqual(rows["package:example"]["version"], "1.2-1")
        self.assertEqual(rows["plugin:example"]["revision"], "abcdef")

    def test_pending_queue_never_silently_pruned(self):
        first = c.compare(None, {}, c.now())
        rows = {str(n):{"name":str(n),"kind":"Software","version":"1"} for n in range(3)}
        with patch.object(c, "MAX_ENTRIES", 2), self.assertRaisesRegex(ValueError, "full"):
            c.compare(first, rows, c.now())

    def test_git_revision_change_detected_without_manifest_bump(self):
        before = {"plugin:x":{"name":"X","kind":"Plugin","version":"1","revision":"abc"}}
        baseline = c.compare(None, before, c.now())
        after = {"plugin:x":before["plugin:x"] | {"revision":"def"}}
        self.assertEqual(len(c.compare(baseline, after, c.now())["events"]), 1)


if __name__ == "__main__":
    unittest.main()
