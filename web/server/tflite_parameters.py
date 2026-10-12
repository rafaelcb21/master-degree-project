"""Run structural inspection in the existing model Python environment."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import re
import time


class TFLiteParameters:
    def __init__(self, root, config):
        self.root = Path(root).resolve()
        self.config = config
        self.storage = self.root / "analysis/tflite-parameters"
        self._models_cached = None
        self._models_scanned = 0

    def _key(self, source, content):
        identity = "project:" + source if source else "upload:" + hashlib.sha256(content).hexdigest()
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def _read(self, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValueError("Relatório inválido.")
        path = self.storage / (key + ".json")
        if not self.allowed(path):
            raise ValueError("Pasta de relatórios não permitida.")
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if (saved.get("version") == 1 and all(key in saved for key in ("source", "sha256", "analyzer"))
                    and isinstance(saved.get("report", {}).get("layers"), list)
                    and isinstance(saved["report"].get("totals"), dict)):
                return saved
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def _analyzer_hash(self):
        return hashlib.sha256((self.root / "analyze_tflite_parameters.py").read_bytes()).hexdigest()

    def _save(self, report, content, source=None):
        key = self._key(source, content)
        if not self.allowed(self.storage):
            raise ValueError("Pasta de relatórios não permitida.")
        self.storage.mkdir(parents=True, exist_ok=True)
        report = dict(report, savedId=key)
        saved = {"version": 1, "source": source, "sha256": hashlib.sha256(content).hexdigest(),
                 "analyzer": self._analyzer_hash(), "report": report}
        # Readers see either the previous report or the complete new report.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.storage, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(saved, stream, ensure_ascii=False, allow_nan=False)
        try:
            temporary.replace(self.storage / (key + ".json"))
        finally:
            temporary.unlink(missing_ok=True)
        return report

    def _model_content(self, name):
        if not isinstance(name, str):
            raise ValueError("Selecione um modelo TFLite.")
        path = self.root / name
        if not self.allowed(path) or path.suffix.lower() != ".tflite" or not path.is_file():
            raise ValueError("Modelo TFLite não permitido.")
        if path.stat().st_size > self.config["max_file_bytes"]:
            raise ValueError("Modelo maior que o limite configurado.")
        return path.read_bytes(), path.relative_to(self.root).as_posix(), path.name

    def query(self, name):
        if isinstance(name, str) and name.startswith("saved:"):
            saved = self._read(name[6:])
            return {"exists": bool(saved), "report": saved["report"] if saved else None}
        content, source, _ = self._model_content(name)
        saved = self._read(self._key(source, content))
        valid = saved and saved["sha256"] == hashlib.sha256(content).hexdigest() and saved["analyzer"] == self._analyzer_hash()
        return {"exists": bool(valid), "report": saved["report"] if valid else None}

    def allowed(self, path):
        resolved = path.resolve()
        return resolved.is_relative_to(self.root) and not any(
            part in self.config["excluded_directories"] or part.startswith(".venv")
            for part in resolved.relative_to(self.root).parts) and not path.is_symlink()

    def _project_models(self):
        items = []
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if self.allowed(Path(directory) / d))
            for name in sorted(names):
                path = Path(directory) / name
                if path.suffix.lower() == ".tflite" and self.allowed(path):
                    items.append({"path": path.relative_to(self.root).as_posix(), "size": path.stat().st_size})
        return items

    def models(self):
        if self._models_cached is None or time.monotonic() - self._models_scanned > 30:
            self._models_cached = self._project_models()
            self._models_scanned = time.monotonic()
        uploads = []
        if self.storage.is_dir() and self.allowed(self.storage):
            for path in sorted(self.storage.glob("*.json")):
                if not re.fullmatch(r"[a-f0-9]{64}", path.stem):
                    continue
                saved = self._read(path.stem)
                if saved and saved["source"] is None:
                    uploads.append({"path": "saved:" + path.stem, "name": saved["report"]["name"]})
        return {"models": self._models_cached, "saved": uploads, "maxBytes": self.config["max_file_bytes"]}

    def from_path(self, name):
        content, source, filename = self._model_content(name)
        return self.from_bytes(content, filename, source)

    def from_bytes(self, content, name, source=None):
        if not 0 < len(content) <= self.config["max_file_bytes"]:
            raise ValueError("Modelo vazio ou maior que o limite configurado.")
        if len(content) < 8 or content[4:8] != b"TFL3":
            raise ValueError("Arquivo inválido: esperado um modelo TFLite (TFL3).")
        default = ".venv-models/Scripts/python.exe" if os.name == "nt" else ".venv-models/bin/python"
        python = self.root / self.config.get("runner_python", {}).get("wasm", default)
        if not python.is_file():
            raise ValueError("Ambiente Python ausente. Configure runner_python.wasm com tflite instalado.")
        with tempfile.TemporaryDirectory(prefix="tflite-parameters-") as tmp:
            model = Path(tmp) / "model.tflite"
            model.write_bytes(content)
            try:
                result = subprocess.run([str(python), str(self.root / "analyze_tflite_parameters.py"), str(model)],
                    cwd=self.root, capture_output=True, text=True, encoding="utf-8", timeout=60,
                    env=dict(os.environ, PYTHONIOENCODING="utf-8"), shell=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except subprocess.TimeoutExpired as error:
                raise ValueError("A análise excedeu o limite de 60 segundos.") from error
            if result.returncode:
                raise ValueError("Falha na análise. Verifique o arquivo e a instalação de tflite no ambiente do modelo.")
            report = json.loads(result.stdout)
            report["name"] = Path(name.replace("\\", "/")).name[:200]
            return self._save(report, content, source)
