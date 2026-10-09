"""Run with .venv-models Python; needs LLVM clang/wasm-ld and wasmtime.

Compiles the real downloader with a fake HTTP transport into a tiny WASM test
module. This validates host control flow, not the ESP-IDF TLS implementation.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wasmtime


class DownloadTests(unittest.TestCase):
    def test_success_and_network_failures(self):
        root = Path(__file__).resolve().parents[1]
        clang = shutil.which("clang") or "C:/Program Files/LLVM/bin/clang.exe"
        with tempfile.TemporaryDirectory() as temp:
            module_path = Path(temp) / "download.wasm"
            subprocess.run([clang, "--target=wasm32", "-nostdlib", "-O1", "-Wl,--no-entry",
                "-Wl,--export=check", "-I", str(root / "main"),
                str(root / "tests/download_harness.c"), "-o", str(module_path)], check=True)
            engine = wasmtime.Engine()
            store = wasmtime.Store(engine)
            instance = wasmtime.Instance(store, wasmtime.Module.from_file(engine, str(module_path)), [])
            cases = ["success", "partial read then retry", "read error/timeout", "truncated body",
                     "oversized chunked body", "HTTP 503", "total deadline", "header error",
                     "connect error", "allocation failure", "wrong content length", "chunked completion"]
            for mode, name in enumerate(cases):
                with self.subTest(name=name):
                    self.assertEqual(instance.exports(store)["check"](store, mode), 0)


if __name__ == "__main__":
    unittest.main()
