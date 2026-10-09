"""Serve saved consolidation with filtering and pagination, without rescanning reports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from consolidate_reports import LOCK, ROOT, consolidate, read_json
from consolidate_mobilenet import consolidate as consolidate_mobilenet


class Consolidation:
    def __init__(self, root=ROOT, mobilenet=False):
        self.root = root
        self.mobilenet = mobilenet
        self.cached = None
        self.signature = None

    def load(self):
        path = self.root / "analysis" / ("mobilenet_top15.json" if self.mobilenet else "consolidated.json")
        if not path.exists():
            return None
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != self.signature:
            self.cached = read_json(path)
            self.signature = signature
        return self.cached

    def rebuild(self):
        with LOCK:
            (consolidate_mobilenet if self.mobilenet else consolidate)(self.root)
            return self.query({})

    def query(self, args):
        with LOCK:
            data = self.load()
            if data is None:
                return {"exists": False}
            rows = data["rows"]
            keys = ("execution",) if self.mobilenet else ("model", "type", "env", "execution")
            options = {key: sorted({str(r[key]) for r in rows}) for key in keys}
            options["execution"].sort(key=int)
            for key in options:
                value = args.get(key, [""])[0]
                if value:
                    rows = [r for r in rows if str(r[key]) == value]
            search = args.get("search", [""])[0].lower()
            if search:
                rows = [r for r in rows if search in r["name" if self.mobilenet else "name_image"].lower()]
            usable = args.get("usable", [""])[0]
            if not self.mobilenet and usable in ("0", "1"):
                rows = [r for r in rows if r["prediction_usable"] == int(usable)]
            if not self.mobilenet and args.get("sort") == ["name_image"]:
                rows = sorted(rows, key=lambda r: (r["name_image"].casefold(), r["name_image"], r["execution"]),
                              reverse=args.get("direction") == ["desc"])
            size = 15 if self.mobilenet else 50
            pages = max(1, (len(rows) + size - 1) // size)
            page = max(1, min(pages, int(args.get("page", ["1"])[0])))
            return dict(exists=True, generated_at=data["generated_at"], total=len(data["rows"]),
                        matched=len(rows), execution_count=len(data["executions"]), options=options,
                        columns=data["columns"], rows=rows[(page - 1) * size:page * size],
                        execution_labels={str(run["execution"]): f"{run['execution']} · {run['type']} · {Path(run['folder']).name}" for run in data["executions"]},
                        warnings=data["warnings"], page=page, pages=pages)

    def download(self, filename):
        allowed = ("mobilenet_top15.csv", "mobilenet_executions.csv") if self.mobilenet else ("consolidated.csv", "executions.csv")
        if filename not in allowed:
            raise ValueError("Unknown consolidation file")
        with LOCK:
            return (self.root / "analysis" / filename).read_bytes()
