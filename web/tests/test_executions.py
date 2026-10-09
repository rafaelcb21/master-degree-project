import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from executions import Executions


class ExecutionTests(unittest.TestCase):
    def test_streaming_single_run_and_report_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text('''from pathlib import Path
import time
print("started", flush=True)
while not Path("continue").exists(): time.sleep(0.02)
p = Path("models/drowsiness/reports/20261008T120000000000Z")
p.mkdir(parents=True)
(p / "02-grafo.txt").write_text("graph")
print("done", flush=True)
''')
            manager = Executions(root, {"runner_python": {"wasm": sys.executable}})
            try:
                manager.start("drowsiness", "wasm")
                with self.assertRaises(RuntimeError):
                    manager.start("drowsiness", "wasm")
                deadline = time.monotonic() + 10
                while not manager.snapshot()["run"]["logs"] and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(manager.snapshot()["run"]["logs"], ["started"])
                (root / "continue").touch()
                while manager.snapshot()["run"]["status"] == "running" and time.monotonic() < deadline:
                    time.sleep(.02)
                run = manager.snapshot()["run"]
                self.assertEqual(run["status"], "completed")
                self.assertEqual(len(run["reports"]), 1)
                self.assertEqual(run["exitCode"], 0)
                (root / "main.py").write_text('raise SystemExit(3)')
                manager.start("drowsiness", "wasm")
                while manager.snapshot()["run"]["status"] == "running" and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertEqual(manager.snapshot()["run"]["status"], "failed")
                self.assertEqual(manager.snapshot()["run"]["reports"], [])
            finally:
                manager.close()

    def test_invalid_selection_and_missing_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = Executions(tmp, {})
            for model, runtime in [("../other", "wasm"), ("drowsiness", "shell"), ("drowsiness", "tflite")]:
                with self.assertRaises(ValueError):
                    manager.start(model, runtime)
