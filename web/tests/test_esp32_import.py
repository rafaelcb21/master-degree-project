import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from esp32_import import import_reports
from app import Catalog

CSV = b"name_image,ok,inference_ms,right\nimage.raw,1,1785.0,1\n"
METADATA = b'{"runtime":"TensorFlow Lite Micro","total":1}'


class ImportTests(unittest.TestCase):
    def test_repeated_imports_preserve_files_and_are_indexed(self):
        with tempfile.TemporaryDirectory() as tmp, patch("esp32_import.download", side_effect=lambda ip, name: CSV if name == "report" else METADATA):
            root = Path(tmp)
            first = import_reports(root, "192.168.0.18", "tflite")
            second = import_reports(root, "192.168.0.18", "tflite")
            self.assertNotEqual(first["folder"], second["folder"])
            self.assertRegex(first["folder"], r"reports/\d{8}T\d{12}Z$")
            for result in (first, second):
                self.assertEqual((root / result["files"][0]).read_bytes(), CSV)
                self.assertEqual(json.loads((root / result["files"][1]).read_bytes())["total"], 1)
            self.assertEqual(len(Catalog(root).scan()["entries"]), 4)

    def test_wasm_only_requests_csv(self):
        with tempfile.TemporaryDirectory() as tmp, patch("esp32_import.download", return_value=CSV) as fetch:
            result = import_reports(Path(tmp), "192.168.0.18", "wasm")
            fetch.assert_called_once_with("192.168.0.18", "report")
            self.assertIn("cnn_webassembly_esp32/reports/", result["folder"])

    def test_metadata_failure_preserves_csv(self):
        with tempfile.TemporaryDirectory() as tmp, patch("esp32_import.download", side_effect=[CSV, OSError("offline")]):
            result = import_reports(Path(tmp), "192.168.0.18", "tflite")
            self.assertEqual(result["warnings"], ["metadata_unavailable"])
            self.assertEqual((Path(tmp) / result["files"][0]).read_bytes(), CSV)

    def test_bad_responses_and_addresses_do_not_create_reports(self):
        with tempfile.TemporaryDirectory() as tmp, patch("esp32_import.download", return_value=b"<html>error</html>"):
            root = Path(tmp)
            for ip in ("127.0.0.1", "8.8.8.8", "http://192.168.0.18/report", "192.168.0.18"):
                with self.assertRaises(ValueError):
                    import_reports(root, ip, "wasm")
            self.assertEqual(list(root.iterdir()), [])
