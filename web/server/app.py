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


class Handler(BaseHTTPRequestHandler):
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
            if url.path == "/api/index":
                self.json(200, CATALOG.scan())
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
        server.server_close()


if __name__ == "__main__":
    main()
