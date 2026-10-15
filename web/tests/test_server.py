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
    def test_versioned_memory_report_separates_internal_heap_and_flash(self):
        text = ("name_image,ok,right,inference_ms,internal_heap_before,internal_heap_after\n"
                "a.raw,1,1,10,80000,79000\n\n"
                "# memory_report_schema=1 cpu_frequency_mhz=160\n"
                "# internal_heap_total_bytes=180000 internal_heap_min_free_bytes=70000 internal_heap_used_bytes=101000\n"
                "# psram_total_bytes=4194304 psram_min_free_bytes=1313628 psram_occupied_bytes=2800000\n"
                "# sram_static_dram_bytes=42452 sram_static_iram_bytes=106986\n"
                "# flash_app_image_bytes=1824000 flash_app_partition_bytes=2097152 flash_app_partition_used_pct=86.98\n")
        report = parse_report(Path("report.csv"), text)
        self.assertEqual(len(report["rows"]), 1)
        metrics = {item["label"]: item["value"] for item in report["metrics"]}
        self.assertEqual(metrics["Registros"], 1)
        self.assertEqual(metrics["Heap interno livre mínimo desde o boot"], 70000)
        self.assertEqual(metrics["PSRAM livre mínima desde o boot"], 1313628)
        self.assertEqual(metrics["Firmware na flash"], 1824000)
        self.assertNotIn("SPIFFS ocupado", metrics)  # unavailable is not zero
        self.assertTrue(any("heap_caps_get_minimum_free_size" in note for note in report["memory_notes"]))

    def test_legacy_heap_is_not_reinterpreted_as_internal_sram(self):
        report = parse_report(Path("report.csv"), "name_image,ok,inference_ms\na.raw,1,10\n\n# heap_min_free_bytes=1800000 psram_min_free_bytes=1700000\n")
        self.assertEqual(len(report["rows"]), 1)
        self.assertFalse(report["memory_notes"])
        self.assertFalse(any("Heap interno" in item["label"] for item in report["metrics"]))

    def test_hash_prefixed_image_name_is_not_a_footer(self):
        report = parse_report(Path("report.csv"), "name_image,ok,inference_ms\n#image.raw,1,10\n")
        self.assertEqual(report["rows"][0]["name_image"], "#image.raw")

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
        paths = [p for p in (ROOT / "models").glob("*/reports/**/*") if p.is_file()]
        paths += list((ROOT / "ESP32").glob("*/reports/**/*.csv"))
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
        self.assertTrue({"inference", "memory", "topk", "records", "text"}.issubset(kinds))


if __name__ == "__main__":
    unittest.main()
