"""Local ESP-IDF build, flash and serial monitoring controller (Windows)."""
from collections import deque
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from esp32_import import PROJECTS, import_reports


class ESP32Executions:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config = config.get("esp32", {})
        self.lock = threading.RLock()
        self.state = None
        self.process = None
        self.closed = False
        self.logs = deque(maxlen=1500)
        self.worker = Path(__file__).with_name("esp32_worker.py")

    def settings(self):
        defaults = {"idf_root": "C:/Espressif/frameworks/esp-idf-v5.3.1",
                    "python": "C:/Espressif/python_env/idf5.3_py3.11_env/Scripts/python.exe",
                    "tools": "C:/Espressif"}
        values = {key: str(Path(self.config.get(key, value)).resolve()) for key, value in defaults.items()}
        if os.name != "nt" or not Path(values["python"]).is_file():
            raise ValueError("esp32_environment_missing")
        return values

    def ports(self):
        settings = self.settings()
        try:
            result = subprocess.run([settings["python"], str(self.worker), "--ports"],
                capture_output=True, text=True, encoding="utf-8", timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired:
            raise ValueError("esp32_port_detection_timeout") from None
        if result.returncode:
            raise ValueError("esp32_port_detection_failed")
        return json.loads(result.stdout)

    def snapshot(self):
        with self.lock:
            return {"run": dict(self.state, logs=list(self.logs)) if self.state else None}

    def busy(self):
        return bool(self.state and self.state["status"] == "running")

    def start(self, runtime, port, action, auto_import=True):
        if runtime not in PROJECTS or action not in ("flash", "restart") or not isinstance(port, str):
            raise ValueError("invalid_selection")
        with self.lock:
            if self.closed or self.busy():
                raise RuntimeError("execution_busy")
            settings = self.settings()
            if port not in [p["port"] for p in self.ports()]:
                raise ValueError("esp32_not_connected")
            if action == "flash" and not (Path(settings["idf_root"]) / "export.ps1").is_file():
                raise ValueError("esp32_environment_missing")
            environment = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                WEB_IDF_PYTHON=settings["python"], WEB_IDF_ROOT=settings["idf_root"],
                WEB_IDF_TOOLS=settings["tools"], WEB_ESP_PORT=port,
                WEB_IDF_BUILD="build-tflite" if runtime == "tflite" else "build")
            process = subprocess.Popen([settings["python"], "-u", str(self.worker), "--port", port, "--action", action],
                cwd=self.root / "ESP32" / PROJECTS[runtime], env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
            self.process = process
            self.logs.clear()
            self.state = {"status": "running", "phase": "checking", "runtime": runtime, "port": port,
                "action": action, "startedAt": datetime.now(timezone.utc).isoformat(), "exitCode": None,
                "ip": None, "reports": [], "importStatus": "waiting" if auto_import else "disabled"}
            threading.Thread(target=self._watch, args=(process, auto_import), daemon=True).start()
            return self.snapshot()

    def _watch(self, process, auto_import):
        try:
            for line in process.stdout:
                line = re.sub(r"\x1b\[[0-9;]*m", "", line.rstrip())
                with self.lock:
                    if line.startswith("@@esp32 "):
                        self.state["phase"] = json.loads(line[8:])["phase"]
                    else:
                        self.logs.append(line[:4000])
                    match = re.search(r"http://(\d+\.\d+\.\d+\.\d+)(?::80)?/report", line)
                    if not match:
                        match = re.search(r"Conectado ao Wi-Fi\. IP: (\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        self.state["ip"] = match[1]
                    ready = "Servidor HTTP iniciado" in line
                    should_import = auto_import and ready and self.state["ip"] and self.state["importStatus"] == "waiting"
                    if should_import:
                        self.state["importStatus"] = "importing"
                if should_import:
                    try:
                        result = import_reports(self.root, self.state["ip"], self.state["runtime"])
                        with self.lock:
                            self.state.update(reports=result["files"], importStatus="partial" if result["warnings"] else "saved")
                    except (OSError, ValueError):
                        with self.lock:
                            self.state["importStatus"] = "failed"
                            self.logs.append("Automatic import failed. Use Import from ESP32 to retry.")
            code = process.wait()
        except Exception as error:
            self.logs.append(str(error))
            self._terminate()
            code = process.wait()
        finally:
            process.stdout.close()
            process.stdin.close()
        with self.lock:
            self.state.update(status="completed" if code == 0 else "failed", exitCode=code)

    def stop_monitor(self):
        with self.lock:
            if not self.busy() or self.state["phase"] != "monitoring":
                raise RuntimeError("monitor_not_running")
            self.process.stdin.write("stop\n")
            self.process.stdin.flush()
            return self.snapshot()

    def _terminate(self):
        if self.process and self.process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def close(self):
        with self.lock:
            self.closed = True
            self._terminate()
