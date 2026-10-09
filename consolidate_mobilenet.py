"""Save MobileNetV2 Top-15 text reports as one row per ranked class."""
import json
from pathlib import Path
import re
from datetime import datetime, timezone

from consolidate_reports import ROOT, LOCK, atomic_write, csv_bytes, read_json

MODEL = "mobilenetv2_alpha035"
COLUMNS = ["model", "execution", "score", "q", "name"]
ENTRY = re.compile(
    r"^\s*(\d+)\. \[(\d+)\] ([^\r\n]+)\r?\n"
    r"\s*wnid=[^\r\n]+\r?\n\s*q=(-?\d+)\r?\n"
    r"\s*score=([\d.eE+-]+)", re.M)


def consolidate(root=ROOT):
    root = Path(root)
    with LOCK:
        destination = root / "analysis"
        saved = destination / "mobilenet_top15.json"
        previous = read_json(saved) if saved.exists() else {}
        ids = previous.get("execution_ids", {})
        rows, executions = [], []
        sources = []
        for runtime, directory, filename in [("wasm", "reports", "12-inferencia-wasm.txt"),
                                             ("tflite", "reports_tflite", "inference-report.txt")]:
            sources.extend((path, runtime) for path in (root / "models" / MODEL / directory).rglob(filename))
        for path, runtime in sorted(sources, key=lambda item: (item[0].parent.name, item[0].as_posix())):
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Report outside repository")
            text = path.read_text(encoding="utf-8-sig")
            entries = ENTRY.findall(text)
            # This schema describes a single Top-15 per execution. Never merge
            # multiple image rankings into an indistinguishable group.
            if [int(entry[0]) for entry in entries] != list(range(1, 16)):
                raise ValueError(f"Expected exactly one Top-15 (ranks 1..15): {path}")
            folder = path.parent.relative_to(root).as_posix()
            if folder not in ids:
                ids[folder] = max(ids.values(), default=0) + 1
            execution = ids[folder]
            for _, index, name, q, score in entries:
                rows.append(dict(model=MODEL, execution=execution, score=float(score),
                                 q=int(q), name=f"[{index}] {name.strip()}"))
            images = [line.strip() for line in text.splitlines() if line.strip().lower().endswith(".raw")]
            executions.append(dict(execution=execution, model=MODEL, type=runtime, env="desktop",
                                   folder=folder, source_file=path.relative_to(root).as_posix(),
                                   image=images[0] if len(images) == 1 else "", rows=15))
        result = dict(generated_at=datetime.now(timezone.utc).isoformat(), columns=COLUMNS,
                      rows=rows, executions=executions, execution_ids=ids, warnings=[])
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        table = csv_bytes(COLUMNS, rows)
        mapping = csv_bytes(["execution", "model", "type", "env", "folder", "source_file", "image", "rows"], executions)
        atomic_write(destination / "mobilenet_top15.csv", table)
        atomic_write(destination / "mobilenet_executions.csv", mapping)
        atomic_write(saved, payload)
        return result


if __name__ == "__main__":
    data = consolidate()
    print(f"analysis/mobilenet_top15.csv: {len(data['rows'])} rows, {len(data['executions'])} executions")
