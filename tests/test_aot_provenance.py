"""Exercise provenance checks with mocked compiler calls, not an ESP32 toolchain."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from build_aot_with_provenance import build, verify


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compiler = self.root / "compiler with spaces.exe"
        self.compiler.write_bytes(b"test fixture, not a real compiler")
        self.source = self.root / "model.wasm"
        self.source.write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.output = self.root / "new run"

    def successful_call(self, argv, cwd):
        if argv[-1] == "--version":
            return 0, "mock compiler for unit test"
        Path(argv[argv.index("-o") + 1]).write_bytes(b"\x00aot" + struct.pack("<I", 3))
        return 0, "mock successful compilation"

    def test_archives_input_and_records_explicit_command_and_hashes(self):
        evidence = self.root / "build-config.txt"
        evidence.write_text("test build config")
        with patch("build_aot_with_provenance.run", side_effect=self.successful_call):
            report = build(self.compiler, self.source, self.output, [evidence])
        self.assertEqual(report["status"], "compilation_verified")
        self.assertIn("--bounds-checks=1", report["command_argv"])
        self.assertIn("--target-abi=ilp32", report["command_argv"])
        self.assertEqual(report["command_argv"][-1], str(self.output / "input.wasm"))
        self.source.write_bytes(b"changed original")
        verify(self.output / "provenance-report.json")
        (self.output / "output.aot").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify(self.output / "provenance-report.json")

    def test_failure_is_not_accepted_as_provenance(self):
        with patch("build_aot_with_provenance.run", side_effect=[(0, "version"), (1, "missing Xtensa")]):
            report = build(self.compiler, self.source, self.output)
        self.assertEqual(report["status"], "failed")
        self.assertNotIn("output_aot", report)
        self.assertIn("missing Xtensa", (self.output / "compile-report.txt").read_text())
        with self.assertRaisesRegex(ValueError, "successful"):
            verify(self.output / "provenance-report.json")

    def test_refuses_reusing_directory_or_accepting_changed_input(self):
        self.output.mkdir()
        with self.assertRaises(FileExistsError):
            build(self.compiler, self.source, self.output)
        other = self.root / "other run"

        def mutating_call(argv, cwd):
            result = self.successful_call(argv, cwd)
            if argv[-1] != "--version":
                Path(argv[-1]).write_bytes(b"changed during compilation")
            return result

        with patch("build_aot_with_provenance.run", side_effect=mutating_call):
            report = build(self.compiler, self.source, other)
        self.assertEqual(report["status"], "failed")
        self.assertIn("changed during compilation", report["error"])

    def test_wrong_aot_version_is_rejected(self):
        def wrong_version(argv, cwd):
            result = self.successful_call(argv, cwd)
            if argv[-1] != "--version":
                Path(argv[argv.index("-o") + 1]).write_bytes(b"\x00aot" + struct.pack("<I", 4))
            return result

        with patch("build_aot_with_provenance.run", side_effect=wrong_version):
            report = build(self.compiler, self.source, self.output)
        self.assertEqual(report["status"], "failed")
        self.assertIn("version 3", report["error"])


if __name__ == "__main__":
    unittest.main()
