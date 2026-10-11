"""Local repository explorer, served with Python's standard library."""
import argparse
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit, quote

from reports import parse_report
from esp32_import import import_reports
from executions import Executions
from esp32_execution import ESP32Executions
from consolidation import Consolidation
from determinism import Determinism
from representative_reports import ESP32Consensus

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
CONFIG = json.loads((WEB / "config.json").read_text(encoding="utf-8"))


class Catalog:
    def __init__(self, root=ROOT, config=CONFIG):
        self.root = root.resolve()
        self.config = config
        self.entries = {}
        self.lock = threading.RLock()

    def allowed(self, path):
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            return False
        return not any(part in self.config["excluded_directories"] or part.startswith(".venv") for part in resolved.relative_to(self.root).parts)

    def scan(self):
        entries = {}
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if self.allowed(Path(directory) / d) and not (Path(directory) / d).is_symlink() and not (Path(directory) / d / "pyvenv.cfg").exists())
            for name in sorted(names):
                p = Path(directory) / name
                if p.is_symlink() or not self.allowed(p):
                    continue
                relative = p.relative_to(self.root)
                ext = p.suffix.lower()
                report = ext in self.config["report_extensions"] and (any(x.lower() in self.config["report_directories"] for x in relative.parts[:-1]) or re.search(r"report|relat[oó]rio", name, re.I))
                if ext != ".md" and not report:
                    continue
                try:
                    stat = p.stat()
                    with p.open(encoding="utf-8-sig", errors="replace") as f:
                        prefix = f.read(16384)
                except OSError:
                    continue
                parts = relative.parts
                project = "/".join(parts[:2]) if parts[0] in ("models", "ESP32") and len(parts) > 2 else ("repository" if len(parts) == 1 or parts[0] == "docs" else parts[0])
                heading = re.search(r"^#\s+(.+)", prefix, re.M)
                title = heading[1] if ext == ".md" and heading else (next((s.strip() for s in prefix.splitlines() if s.strip()), name) if ext == ".txt" else name)
                entry = {"path": relative.as_posix(), "name": name, "title": title[:180], "kind": "document" if ext == ".md" else "report", "project": project, "folder": relative.parent.as_posix(), "language": "pt-BR" if name.endswith(".pt-BR.md") else "en", "historical": "historico" in parts, "size": stat.st_size, "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "counterpart": None}
                if ext == ".md":
                    candidates = re.findall(r"\[(?:English|Português \(Brasil\))\]\(([^)]+)\)", prefix)
                    for target in candidates:
                        other = (p.parent / unquote(target)).resolve()
                        if other != p.resolve() and self.allowed(other):
                            entry["counterpart"] = other.relative_to(self.root).as_posix()
                entries[entry["path"]] = entry
        with self.lock:
            self.entries = entries
        return {"entries": list(entries.values()), "scannedAt": datetime.now(timezone.utc).isoformat(), "repository": self.root.name}

    def read(self, name):
        with self.lock:
            entry = self.entries.get(name)
        if entry is None:
            raise FileNotFoundError(name)
        p = self.root / name
        if not self.allowed(p) or p.is_symlink():
            raise FileNotFoundError(name)
        if p.stat().st_size > self.config["max_file_bytes"]:
            raise ValueError("Arquivo maior que o limite configurado em web/config.json.")
        data = p.read_bytes()
        if len(data) > self.config["max_file_bytes"]:
            raise ValueError("Arquivo maior que o limite de leitura.")
        return entry, data


CATALOG = Catalog()
EXECUTIONS = Executions(ROOT, CONFIG)
ESP32 = ESP32Executions(ROOT, CONFIG)
START_LOCK = threading.Lock()
CONSOLIDATION = Consolidation(ROOT)
MOBILENET_CONSOLIDATION = Consolidation(ROOT, mobilenet=True)
DETERMINISM = Determinism(ROOT)
ESP32_CONSENSUS = ESP32Consensus(ROOT)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/api/esp32/import", "/api/executions", "/api/esp32/start", "/api/esp32/stop", "/api/consolidation", "/api/mobilenet-consolidation", "/api/analyses/determinism", "/api/analyses/esp32-consensus"):
            self.json(404, {"error": "not_found"})
            return
        origin = self.headers.get("Origin")
        if (origin and origin != "http://" + self.headers.get("Host", "")) or self.headers.get("Sec-Fetch-Site") == "cross-site":
            self.json(403, {"error": "invalid_origin"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048 or self.headers.get_content_type() != "application/json":
                raise ValueError("invalid_request")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("invalid_request")
            if self.path == "/api/analyses/esp32-consensus":
                self.json(200, ESP32_CONSENSUS.rebuild())
            elif self.path == "/api/analyses/determinism":
                self.json(200, DETERMINISM.rebuild())
            elif self.path == "/api/mobilenet-consolidation":
                self.json(200, MOBILENET_CONSOLIDATION.rebuild())
            elif self.path == "/api/consolidation":
                self.json(200, CONSOLIDATION.rebuild())
            elif self.path == "/api/executions":
                with START_LOCK:
                    if ESP32.busy():
                        raise RuntimeError("execution_busy")
                    result = EXECUTIONS.start(data.get("model"), data.get("runtime"))
                self.json(202, result)
            elif self.path == "/api/esp32/start":
                with START_LOCK:
                    desktop = EXECUTIONS.snapshot()["run"]
                    if desktop and desktop["status"] == "running":
                        raise RuntimeError("execution_busy")
                    result = ESP32.start(data.get("runtime"), data.get("port"), data.get("action"), data.get("autoImport") is True)
                self.json(202, result)
            elif self.path == "/api/esp32/stop":
                self.json(200, ESP32.stop_monitor())
            else:
                result = import_reports(CATALOG.root, data.get("ip", ""), data.get("runtime", ""))
                self.json(201, result)
        except RuntimeError as error:
            self.json(409, {"error": str(error)})
        except (ValueError, TypeError) as error:
            self.json(400, {"error": str(error)})
        except OSError:
            self.json(502, {"error": "import_failed"})

    def send(self, status, data, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(filename))
        self.end_headers()
        self.wfile.write(data)

    def json(self, status, value):
        self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        url = urlsplit(self.path)
        args = parse_qs(url.query)
        try:
            if url.path == "/api/analyses/esp32-consensus":
                self.json(200, ESP32_CONSENSUS.query(args))
            elif url.path == "/api/analyses/esp32-consensus/download":
                content, filename = ESP32_CONSENSUS.download(args)
                self.send(200, content, "application/octet-stream", filename)
            elif url.path == "/api/analyses/determinism":
                self.json(200, DETERMINISM.query(args))
            elif url.path == "/api/analyses/determinism/download":
                filename = args.get("file", ["report.md"])[0]
                self.send(200, DETERMINISM.download(filename), "application/octet-stream", filename)
            elif url.path == "/api/mobilenet-consolidation":
                self.json(200, MOBILENET_CONSOLIDATION.query(args))
            elif url.path == "/api/mobilenet-consolidation/download":
                filename = args.get("file", ["mobilenet_top15.csv"])[0]
                self.send(200, MOBILENET_CONSOLIDATION.download(filename), "text/csv; charset=utf-8", filename)
            elif url.path == "/api/consolidation":
                self.json(200, CONSOLIDATION.query(args))
            elif url.path == "/api/consolidation/download":
                filename = args.get("file", ["consolidated.csv"])[0]
                self.send(200, CONSOLIDATION.download(filename), "text/csv; charset=utf-8", filename)
            elif url.path == "/api/index":
                self.json(200, CATALOG.scan())
            elif url.path == "/api/executions":
                self.json(200, EXECUTIONS.snapshot())
            elif url.path == "/api/esp32/status":
                self.json(200, ESP32.snapshot())
            elif url.path == "/api/esp32/ports":
                try:
                    self.json(200, {"ports": ESP32.ports()})
                except (OSError, ValueError, TimeoutError) as error:
                    self.json(200, {"ports": [], "error": str(error)})
            elif url.path == "/api/file":
                entry, data = CATALOG.read(args.get("path", [""])[0])
                if args.get("download") == ["1"]:
                    self.send(200, data, "application/octet-stream", entry["name"])
                else:
                    text = data.decode("utf-8-sig", errors="replace")
                    self.json(200, {"entry": entry, "content": text, "report": parse_report(Path(entry["path"]), text) if entry["kind"] == "report" else None})
            else:
                assets = {"/": ("index.html", "text/html"), "/app.js": ("public/app.js", "text/javascript"), "/styles.css": ("styles/styles.css", "text/css"), "/favicon.svg": ("public/favicon.svg", "image/svg+xml")}
                assets["/docs/assets/research-explorer.png"] = ("../docs/assets/research-explorer.png", "image/png")
                if url.path not in assets:
                    raise FileNotFoundError()
                file, mime = assets[url.path]
                self.send(200, (WEB / file).read_bytes(), mime + "; charset=utf-8")
        except (FileNotFoundError, PermissionError):
            self.json(404, {"error": "Arquivo não encontrado no índice. Atualize a biblioteca."})
        except ValueError as error:
            self.json(413, {"error": str(error)})
        except (OSError, UnicodeError):
            self.json(500, {"error": "Não foi possível ler o arquivo."})


def main():
    parser = argparse.ArgumentParser(description="Explore project documentation and reports locally.")
    parser.add_argument("--port", type=int, default=CONFIG["port"])
    args = parser.parse_args()
    CATALOG.scan()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as error:
        parser.exit(1, f"Não foi possível iniciar: {error}. Tente --port 8001.\n")
    print(f"Research Explorer: http://127.0.0.1:{server.server_port}\nCtrl+C para encerrar.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        EXECUTIONS.close()
        ESP32.close()
        server.server_close()


if __name__ == "__main__":
    main()
