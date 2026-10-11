"""Cached intra-environment determinism report API."""
from consolidate_reports import ROOT, LOCK, read_json, consolidate
from consolidate_mobilenet import consolidate as consolidate_mobilenet
from analyze_determinism import analyze


class Determinism:
    def __init__(self, root=ROOT):
        self.root = root
        self.cached = None
        self.signature = None

    def query(self, args):
        with LOCK:
            path = self.root / "analysis/determinism/report.json"
            if not path.exists():
                return {"exists": False}
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
            if signature != self.signature:
                self.cached = read_json(path)
                self.signature = signature
            data = self.cached
            items = data["images"]
            options = {key: sorted({item[key] for item in items}) for key in ("model", "type", "env")}
            for key in options:
                if args.get(key, [""])[0]:
                    items = [item for item in items if item[key] == args[key][0]]
            status = args.get("status", ["different"])[0]
            if status:
                items = [item for item in items if item["status"] == status]
            search = args.get("search", [""])[0]
            if search:
                items = [item for item in items if search in item["name_image"]]
            items = sorted(items, key=lambda item: (-(item.get("quantized_differences", {}).get("maximum") or 0), item["name_image"]))
            pages = max(1, (len(items) + 24) // 25)
            page = max(1, min(pages, int(args.get("page", ["1"])[0])))
            stale = []
            for source in data["sources"]:
                source_path = self.root / source["path"]
                if not source_path.exists() or source_path.stat().st_mtime_ns > stat.st_mtime_ns:
                    stale.append(source["path"])
            return dict(exists=True, generated_at=data["generated_at"], groups=data["groups"],
                        sources=data["sources"], stale=stale, options=options,
                        images=items[(page - 1) * 25:page * 25], matched=len(items), page=page, pages=pages,
                        execution_maps=data["execution_maps"])

    def rebuild(self):
        with LOCK:
            # Explicit regeneration must include newly imported report folders.
            # Ordinary queries continue to use the saved analysis.
            consolidate(self.root)
            consolidate_mobilenet(self.root)
            analyze(self.root)
            return self.query({})

    def download(self, filename):
        if filename not in ("report.md", "report.json", "images.csv"):
            raise ValueError("Unknown determinism report")
        with LOCK:
            return (self.root / "analysis/determinism" / filename).read_bytes()
