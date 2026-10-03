"""Contracts for the shared journal and native Briefing integration."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import changes


class IntegrationTests(unittest.TestCase):
    def test_two_frontends_share_records_and_reject_stale_edits(self):
        spec = importlib.util.spec_from_file_location("other_frontend", Path(changes.__file__))
        other = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(other)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            record = {"title":"Example", "why":"Keep context", "date":"2026-10-03", "kind":"Other", "status":"Trying it"}
            first = changes.save(directory, {"record":record})["entries"][0]
            self.assertEqual(other.listing(directory)["entries"][0], first)
            request = {"record":record | {"why":"Updated elsewhere"}, "id":first["id"], "expectedUpdatedAt":first["updatedAt"]}
            other.save(directory, request)
            with self.assertRaisesRegex(ValueError, "changed elsewhere"):
                changes.save(directory, request)
            self.assertEqual(changes.listing(directory)["entries"][0]["why"], "Updated elsewhere")

    def test_both_views_use_shared_font_and_button_components(self):
        directory = Path(__file__).parent
        for file in ("Panel.qml", "ChangesView.qml"):
            text = (directory / file).read_text()
            self.assertIn("component Copy: BriefingText", text)
            self.assertIn("component Action: BriefingButton", text)
        text = (directory / "ChangesView.qml").read_text()
        self.assertNotRegex(text, r"font\.pixelSize:\s*\d")
        self.assertIn('function explain(change, completed)', text)

    def test_original_state_location_is_retained(self):
        self.assertEqual(changes.STATE.name, "my-linux-changes")


if __name__ == "__main__":
    unittest.main()
