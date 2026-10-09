import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consolidate_reports import consolidate, desktop_rows, image_name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web/server"))
from consolidation import Consolidation


class ConsolidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("analysis/config.json", json.dumps({"esp32_projects": {
            "host": {"model": "drowsiness", "type": "tflite", "output_scale": 1/256, "output_zero_point": 0}}}))

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_four_sources_and_recovery(self):
        self.write("models/drowsiness/reports/2026/12-inferencia-wasm.txt",
                   "C:\\test\\A0001.raw | quantized=[255, 0] | scores=[0.99609375, 0.0] | result=1 label=1 right=1 invalid=False\n"
                   "C:\\test\\A0002.raw | quantized=[0, 0] | scores=[0.0, 0.0] | result=None label=1 right=0 invalid=True\n")
        self.write("models/drowsiness/reports_tflite/2026/results-report.json", json.dumps({"records": [
            {"file": "test/A0001.raw", "quantized": [255, 0], "scores": [255/256, 0], "result": 1,
             "label": 1, "right": True, "invalid": False, "inference_ms": 86}], "errors": [{"file": "bad.raw", "error": "failed"}]}))
        self.write("models/drowsiness/reports_tflite/2026/inference-report.txt", "ignored duplicate")
        self.write("ESP32/host/reports/2026/report.csv",
                   "name_image,ok,class_0_raw,class_1_raw,result,label,right,inference_ms,recovery_attempts,recovery_skipped\n"
                   "A0001_xyz.raw,1,255,0,1,1,1,1784.06,1,0\n"
                   "a0001_abc.raw,0,0,0,-1,0,-1,0,2,1\n")
        self.write("models/mobile/reports/2026/12-inferencia-wasm.txt",
                   "C:\\test\\aviao_uint8.raw\n 1. [404] airliner\n    wnid=n02690373\n    q=226\n    score=0.88281250\n"
                   " 2. [812] shuttle\n    wnid=n04266014\n    q=11\n    score=0.04296875\n")
        data = consolidate(self.root)
        self.assertEqual(len(data["executions"]), 4)
        self.assertEqual(len(data["rows"]), 7)
        embedded = [r for r in data["rows"] if r["env"] == "esp32"]
        self.assertEqual(embedded[0]["name_image"], "A0001.raw")
        self.assertEqual(embedded[0]["scores"], [255/256, 0])
        self.assertEqual(embedded[0]["inference_ms"], 1784.06)
        self.assertIsNone(embedded[0]["invalid"])
        self.assertEqual(embedded[1]["name_image"], "a0001.raw")
        self.assertEqual(embedded[1]["prediction_usable"], 0)
        self.assertIsNone(embedded[1]["quantized"])
        self.assertEqual(embedded[1]["recovery_attempts"], 2)
        invalid = next(r for r in data["rows"] if r["invalid"] == 1)
        self.assertEqual(invalid["ok"], 1)
        self.assertEqual(invalid["prediction_usable"], 0)
        mobile = next(r for r in data["rows"] if r["model"] == "mobile")
        self.assertEqual(mobile["output_indices"], [404, 812])
        self.assertEqual(mobile["output_scope"], "top_k")
        self.assertEqual(mobile["name_image"], "aviao_uint8.raw")
        self.assertTrue(all(r["inference_ms"] == 0 for r in data["rows"] if r["env"] == "desktop"))
        exported = list(csv.DictReader(io.StringIO((self.root / "analysis/consolidated.csv").read_text(encoding="utf-8-sig")), delimiter=";"))
        self.assertEqual(len(exported), 7)
        old_ids = data["execution_ids"].copy()
        self.write("models/mobile/reports/0000/12-inferencia-wasm.txt", "empty")
        second = consolidate(self.root)
        self.assertTrue(all(second["execution_ids"][k] == v for k, v in old_ids.items()))
        service = Consolidation(self.root)
        saved = service.query({"env": ["esp32"], "usable": ["1"]})
        self.assertEqual(saved["matched"], 1)
        unusable = service.query({"usable": ["0"]})
        self.assertEqual(unusable["matched"], 3)
        self.assertTrue(all(r["prediction_usable"] == 0 for r in unusable["rows"]))
        # Reading/filtering uses saved output even after source files are removed.
        (self.root / "ESP32/host/reports/2026/report.csv").unlink()
        self.assertEqual(service.query({})["total"], 7)

    def test_metadata_overrides_legacy_quantization(self):
        self.write("ESP32/host/reports/one/report.csv",
                   "name_image,ok,class_0_raw,class_1_raw,result\nx_123.raw,1,2,4,0\n")
        self.write("ESP32/host/reports/one/metadata.json", '{"output_scale":0.5,"output_zero_point":2}')
        data = consolidate(self.root)
        self.assertEqual(data["rows"][0]["scores"], [0, 1])
        self.assertEqual(data["warnings"], [])

    def test_csv_summaries_are_not_images_and_failed_images_remain(self):
        self.write("ESP32/host/reports/one/report.csv",
                   "name_image,ok,class_0_raw,class_1_raw,result\n"
                   '"A0001_pngxcr.raw",1,255,0,1\n'
                   '"a0002_suffix.raw",0,0,0,-1\n'
                   "# total=2000 sucesso=2000 erros=0 empates=5\n"
                   "# rotuladas_com_sucesso=2000 acertos=1965\n"
                   "# accuracy_pct=98.250\n"
                   "# inference_avg_ms=6183.526 inference_min_ms=6121.972 inference_max_ms=6226.452\n"
                   "# download_avg_ms=600.363\n"
                   "# heap_min_free_bytes=1780148 psram_min_free_bytes=1710944 psram_total_bytes=4194304\n"
                   "summary.txt,not-a-number\n"
                   ",not-a-number\n\n")
        data = consolidate(self.root)
        self.assertEqual([r["name_image"] for r in data["rows"]], ["A0001.raw", "a0002.raw"])
        self.assertEqual(data["executions"][0]["rows"], 2)
        self.assertEqual(data["rows"][1]["ok"], 0)
        self.assertEqual(Consolidation(self.root).query({"usable": ["0"]})["matched"], 1)

    def test_failed_rebuild_keeps_previous_files(self):
        consolidate(self.root)
        before = (self.root / "analysis/consolidated.csv").read_bytes()
        self.write("models/a/reports/one/12-inferencia-wasm.txt", "x.raw | quantized=[bad] | broken")
        with self.assertRaises(ValueError):
            consolidate(self.root)
        self.assertEqual(before, (self.root / "analysis/consolidated.csv").read_bytes())

    def test_normalization_preserves_case_and_desktop_suffix(self):
        self.assertEqual(image_name("A0001_pngxcr.raw", True), "A0001.raw")
        self.assertEqual(image_name("a0001_pngxcr.raw", True), "a0001.raw")
        self.assertEqual(image_name("aviao_uint8.raw"), "aviao_uint8.raw")

    def test_image_sort_groups_executions_before_pagination(self):
        rows = [dict(name_image=f"A{i:04}.raw", execution=execution, model="drowsiness",
                     type="wasm", env="desktop", prediction_usable=1)
                for execution in (2, 1) for i in range(30, 0, -1)]
        self.write("analysis/consolidated.json", json.dumps(dict(rows=rows, columns=[],
                   executions=[], generated_at="saved", warnings=[])))
        service = Consolidation(self.root)
        first = service.query({"sort": ["name_image"]})
        second = service.query({"sort": ["name_image"], "page": ["2"]})
        combined = first["rows"] + second["rows"]
        self.assertEqual([r["name_image"] for r in combined],
                         [f"A{i:04}.raw" for i in range(1, 31) for _ in (1, 2)])
        self.assertEqual([r["execution"] for r in first["rows"][:2]], [1, 2])
        descending = service.query({"sort": ["name_image"], "direction": ["desc"]})
        self.assertEqual(descending["rows"][0]["name_image"], "A0030.raw")
        self.assertEqual(service.query({})["rows"][0], rows[0])


if __name__ == "__main__":
    unittest.main()
