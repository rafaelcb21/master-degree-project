"""Serve saved representative ESP32 reports and regenerate their consolidation."""
from pathlib import Path
from consolidate_reports import ROOT, LOCK, read_json, consolidate


class ESP32Consensus:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.cached = None
        self.signature = None

    def load(self):
        path = self.root / "analysis/esp32_consensus/report.json"
        if not path.exists():
            return None
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if signature != self.signature:
            self.cached = read_json(path)
            self.signature = signature
        return self.cached

    def query(self, args):
        with LOCK:
            data = self.load()
            if data is None:
                return {"exists": False}
            groups = data["groups"]
            requested = args.get("group", [""])[0]
            group = next((g for g in groups if f"{g['model']}/{g['type']}" == requested), groups[0] if groups else None)
            images = group["images"] if group else []
            search = args.get("search", [""])[0].casefold()
            status = args.get("status", [""])[0]
            if search:
                images = [item for item in images if search in item["name_image"].casefold()]
            if status:
                images = [item for item in images if item["status"] == status]
            pages = max(1, (len(images) + 49) // 50)
            page = max(1, min(pages, int(args.get("page", ["1"])[0])))
            return dict(exists=True, generated_at=data["generated_at"], method=data["method"],
                        groups=[{k: v for k, v in g.items() if k != "images"} for g in groups],
                        group=f"{group['model']}/{group['type']}" if group else None,
                        images=images[(page - 1) * 50:page * 50], matched=len(images), page=page, pages=pages,
                        sources=data["sources"])

    def rebuild(self):
        with LOCK:
            consolidate(self.root)
            return self.query({})

    def download(self, args):
        with LOCK:
            data = self.load()
            if data is None:
                raise FileNotFoundError("Representative reports not generated")
            filename = args.get("file", ["report.csv"])[0]
            if filename in ("report.json", "images.csv"):
                path = self.root / "analysis/esp32_consensus" / filename
            elif filename == "report.csv":
                key = args.get("group", [""])[0]
                group = next((g for g in data["groups"] if f"{g['model']}/{g['type']}" == key), None)
                if group is None:
                    raise ValueError("Unknown representative report")
                path = self.root / group["source_file"]
                filename = f"report-esp32-{group['model']}-{group['type']}.csv"
            else:
                raise ValueError("Unknown representative report file")
            if not path.resolve().is_relative_to(self.root.resolve() / "analysis/esp32_consensus"):
                raise ValueError("Report outside representative report directory")
            return path.read_bytes(), filename
