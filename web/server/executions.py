"""One desktop benchmark at a time, using fixed local entry points."""
from collections import deque
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import threading

MODELS = ("drowsiness", "mobilenetv2_alpha035")
RUNTIMES = {"wasm": (".venv-models", "main.py", "reports"),
            "tflite": (".venv-tflite", "run_tflite.py", "reports_tflite")}


class Executions:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config = config
        self.lock = threading.RLock()
        self.process = None
        self.closed = False
        self.state = None
        self.logs = deque(maxlen=1500)

    def snapshot(self):
        with self.lock:
            return {"run": dict(self.state, logs=list(self.logs)) if self.state else None}

    def start(self, model, runtime):
        if model not in MODELS or runtime not in RUNTIMES:
            raise ValueError("invalid_selection")
        env, script, reports = RUNTIMES[runtime]
        default = f"{env}/Scripts/python.exe" if os.name == "nt" else f"{env}/bin/python"
        python = (self.root / self.config.get("runner_python", {}).get(runtime, default)).resolve()
        if not python.is_file():
            raise ValueError("python_environment_missing")
        with self.lock:
            if self.closed or (self.state and self.state["status"] == "running"):
                raise RuntimeError("execution_busy")
            destination = self.root / "models" / model / reports
            before = set(destination.glob("*"))
            environment = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
            self.process = subprocess.Popen([str(python), "-u", script, "--model", model],
                cwd=self.root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.logs.clear()
            self.state = {"model": model, "runtime": runtime, "status": "running",
                "startedAt": datetime.now(timezone.utc).isoformat(), "finishedAt": None,
                "exitCode": None, "reports": []}
            threading.Thread(target=self._watch, args=(self.process, destination, before), daemon=True).start()
            return self.snapshot()

    def _watch(self, process, destination, before):
        try:
            for line in process.stdout:
                with self.lock:
                    self.logs.append(line.rstrip()[:4000])
            code = process.wait()
        except OSError as error:
            with self.lock:
                self.logs.append(str(error))
            process.terminate()
            code = process.wait()
        finally:
            process.stdout.close()
        files = sorted(p.relative_to(self.root).as_posix()
                       for folder in set(destination.glob("*")) - before if folder.is_dir()
                       for p in folder.iterdir() if p.is_file())
        with self.lock:
            self.state.update(status="completed" if code == 0 else "failed", exitCode=code,
                finishedAt=datetime.now(timezone.utc).isoformat(), reports=files)

    def close(self):
        with self.lock:
            self.closed = True
            if self.process and self.process.poll() is None:
                self.process.terminate()
                self.process.wait()
