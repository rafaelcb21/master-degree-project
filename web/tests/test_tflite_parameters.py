"""Saved reports survive a new service instance and invalidate on model changes."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from tflite_parameters import TFLiteParameters

CONFIG = {"excluded_directories": [".git"], "max_file_bytes": 1024}
REPORT = {"name": "demo.tflite", "layers": [], "totals": {"total": 8}}


class SavedParameterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "analyze_tflite_parameters.py").write_text("# analyzer", encoding="utf-8")
        self.content = b"\x08\x00\x00\x00TFL3demo"
        (self.root / "demo.tflite").write_bytes(self.content)
        self.service = TFLiteParameters(self.root, CONFIG)

    def test_project_report_survives_service_restart(self):
        saved = self.service._save(REPORT, self.content, "demo.tflite")
        result = TFLiteParameters(self.root, CONFIG).query("demo.tflite")
        self.assertTrue(result["exists"])
        self.assertEqual(result["report"], saved)

    def test_changed_model_invalidates_report(self):
        self.service._save(REPORT, self.content, "demo.tflite")
        (self.root / "demo.tflite").write_bytes(self.content + b"changed")
        self.assertFalse(self.service.query("demo.tflite")["exists"])

    def test_changed_analyzer_invalidates_report(self):
        self.service._save(REPORT, self.content, "demo.tflite")
        (self.root / "analyze_tflite_parameters.py").write_text("# revised analyzer", encoding="utf-8")
        self.assertFalse(self.service.query("demo.tflite")["exists"])

    def test_upload_is_selectable_without_original_file(self):
        saved = self.service._save(REPORT, self.content)
        new = TFLiteParameters(self.root, CONFIG)
        selected = new.models()["saved"][0]["path"]
        self.assertEqual(selected, "saved:" + saved["savedId"])
        self.assertEqual(new.query(selected)["report"], saved)

    def test_invalid_and_missing_reports(self):
        self.assertFalse(self.service.query("demo.tflite")["exists"])
        with self.assertRaises(ValueError):
            self.service.query("saved:../../outside")
        with self.assertRaises(ValueError):
            self.service.query("../outside.tflite")

    def test_corrupt_report_is_not_displayed(self):
        saved = self.service._save(REPORT, self.content, "demo.tflite")
        (self.service.storage / (saved["savedId"] + ".json")).write_text("{bad", encoding="utf-8")
        self.assertFalse(self.service.query("demo.tflite")["exists"])


if __name__ == "__main__":
    unittest.main()
