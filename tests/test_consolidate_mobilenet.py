import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from consolidate_mobilenet import consolidate, MODEL
from consolidate_reports import consolidate as consolidate_general
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web/server"))
from consolidation import Consolidation


def report(q):
    return "test/img/aviao_uint8.raw\n" + "".join(
        f"{rank}. [{403 + rank}] {'airliner' if rank == 1 else 'class_' + str(rank)}\n"
        f"    wnid=n123\n    q={q - rank}\n    score={(q - rank)/256:.8f}\n"
        for rank in range(1, 16)) + "Erros de processamento: 0\n"


class MobileNetTests(unittest.TestCase):
    def test_rank_rows_independent_files_and_stable_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analysis").mkdir()
            (root / "analysis/config.json").write_text('{"esp32_projects":{}}')
            for folder, name, q in [("reports", "12-inferencia-wasm.txt", 227),
                                    ("reports_tflite", "inference-report.txt", 142)]:
                path = root / "models" / MODEL / folder / "2026" / name
                path.parent.mkdir(parents=True)
                path.write_text(report(q), encoding="utf-8")
            general = consolidate_general(root)
            self.assertEqual(general["rows"], [])
            before_general = (root / "analysis/consolidated.json").read_bytes()
            result = consolidate(root)
            self.assertEqual(result["columns"], ["model", "execution", "score", "q", "name"])
            self.assertEqual(len(result["rows"]), 30)
            self.assertEqual(result["rows"][0]["name"], "[404] airliner")
            self.assertEqual(result["rows"][0]["q"], 226)
            self.assertEqual(result["rows"][0]["score"], 0.8828125)
            self.assertEqual(result["rows"][15]["q"], 141)
            self.assertEqual(len(set(r["execution"] for r in result["rows"])), 2)
            self.assertEqual((root / "analysis/consolidated.json").read_bytes(), before_general)
            before_mobile = (root / "analysis/mobilenet_top15.json").read_bytes()
            consolidate_general(root)
            self.assertEqual((root / "analysis/mobilenet_top15.json").read_bytes(), before_mobile)
            self.assertEqual(consolidate(root)["execution_ids"], result["execution_ids"])
            service = Consolidation(root, mobilenet=True)
            selected = service.query({"execution": [str(result["rows"][15]["execution"])]})
            self.assertEqual(selected["matched"], 15)
            self.assertEqual(len(selected["rows"]), 15)
            self.assertEqual(service.query({"search": ["airliner"]})["matched"], 2)
            # An incomplete ranking must not silently overwrite a valid table.
            path.write_text("1. [404] airliner\n", encoding="utf-8")
            before_mobile = (root / "analysis/mobilenet_top15.json").read_bytes()
            with self.assertRaises(ValueError):
                consolidate(root)
            self.assertEqual((root / "analysis/mobilenet_top15.json").read_bytes(), before_mobile)


if __name__ == "__main__":
    unittest.main()
