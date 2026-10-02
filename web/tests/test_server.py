"""Run with: python -m unittest discover -s web/tests -v."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from app import Catalog, CONFIG, ROOT
from reports import parse_report


class CatalogTests(unittest.TestCase):
    def test_discovery_counterparts_and_restricted_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "docs/guide.md": "# Guide\n[Português (Brasil)](guia.pt-BR.md)",
                "docs/guia.pt-BR.md": "# Guia\n[English](guide.md)",
                "ESP32/demo/.git/config": "private",
                "ESP32/demo/README.md": "# Host",
                "ESP32/demo/report.csv": "ok,right\n1,1",
                "ESP32/demo/build/internal.md": "ignored",
                "ESP32/demo/managed_components/vendor/README.md": "ignored",
                "models/new/reports/result.txt": "results",
                "custom-env/pyvenv.cfg": "home=x",
                "custom-env/vendor.md": "ignored",
                "secret.txt": "private",
            }
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            catalog = Catalog(root)
            catalog.scan()
            self.assertEqual(len(catalog.entries), 5)
            self.assertEqual(catalog.entries["docs/guide.md"]["counterpart"], "docs/guia.pt-BR.md")
            self.assertEqual(catalog.entries["ESP32/demo/report.csv"]["project"], "ESP32/demo")
            for name in ["../secret.txt", "secret.txt", "docs/../secret.txt", str(root / "secret.txt")]:
                with self.assertRaises(FileNotFoundError):
                    catalog.read(name)
            self.assertFalse(catalog.allowed(root / "../outside.md"))
            (root / "new.md").write_text("# New", encoding="utf-8")
            catalog.scan()
            self.assertIn("new.md", catalog.entries)
            (root / "new.md").unlink()
            catalog.scan()
            self.assertNotIn("new.md", catalog.entries)

    def test_file_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "big.md").write_text("# Long document")
            catalog = Catalog(root, {**CONFIG, "max_file_bytes": 4})
            catalog.scan()
            with self.assertRaises(ValueError):
                catalog.read("big.md")


class ReportTests(unittest.TestCase):
    def test_csv_denominators_and_invalid_times(self):
        report = parse_report(Path("report.csv"), "name_image,ok,right,inference_ms,download_ms\na,1,1,10,2\nb,0,0,100,99\nc,1,0,20,4\nd,1,-1,nan,-1\n")
        metrics = {m["label"]: m["value"] for m in report["metrics"]}
        self.assertEqual(metrics["Acurácia"], 50)
        self.assertEqual(metrics["Amostras avaliadas"], 2)
        self.assertEqual(metrics["Falhas"], 1)
        self.assertEqual(metrics["Inferência média"], 15)
        self.assertEqual(metrics["Download médio"], 3)
        self.assertEqual([p["x"] for p in report["series"][0]["points"]], [1, 3])
        json.dumps(report, allow_nan=False)

    def test_semicolon_and_unknown_report(self):
        report = parse_report(Path("report.csv"), 'name;value\n"hello;world";2\n')
        self.assertEqual(report["rows"][0]["name"], "hello;world")
        self.assertEqual(parse_report(Path("new.txt"), "unrecognized format")["kind"], "text")

    def test_existing_reports(self):
        paths = list((ROOT / "models").glob("*/reports/*")) + [ROOT / "ESP32/cnn_webassembly_esp32/report.csv"]
        kinds = set()
        for path in paths:
            report = parse_report(path, path.read_text(encoding="utf-8-sig"))
            kinds.add(report["kind"])
            json.dumps(report, allow_nan=False)
            if report["kind"] == "memory":
                self.assertTrue(all(row["Fim"] - row["Base"] == row["Bytes"] for row in report["regions"]))
            if report["kind"] == "inference":
                self.assertEqual(len(report["rows"]), 2000)
                self.assertEqual(next(m["value"] for m in report["metrics"] if m["label"] == "Acurácia"), 98.25)
            if report["kind"] == "topk":
                self.assertTrue(all(0 <= row["Score"] <= 1 for row in report["rows"]))
        self.assertTrue({"csv", "inference", "memory", "topk", "records", "text"}.issubset(kinds))


if __name__ == "__main__":
    unittest.main()
