"""Consolidate saved benchmark runs without executing models (standard library only)."""
import argparse
import csv
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
LOCK = threading.RLock()
COLUMNS = ["execution", "model", "name_image", "quantized", "scores", "result",
           "label", "right", "ok", "invalid", "type", "env", "inference_ms",
           "recovery_attempts", "recovery_skipped", "prediction_usable",
           "output_indices", "output_scope", "source_file", "error"]
BINARY = re.compile(r"^(.*?)\s*\|\s*quantized=(\[.*?\])\s*\|\s*scores=(\[.*?\])\s*\|\s*result=(None|-?\d+) label=(-?\d+) right=([01]) invalid=(True|False)\s*$")
TOP = re.compile(r"^\s*\d+\. \[(\d+)\].*?\n\s*wnid=.*?\n\s*q=(-?\d+)\n\s*score=([\d.eE+-]+)", re.M)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def image_name(value, cloudinary=False):
    name = str(value).replace("\\", "/").rsplit("/", 1)[-1]
    # Strip only the final Cloudinary suffix, and only for ESP32 sources.
    return re.sub(r"_[^_.]+(?=\.[^.]+$)", "", name) if cloudinary else name


def is_image(value):
    value = str(value or "").strip()
    if not value or value.startswith("#"):
        return False
    return Path(image_name(value)).suffix.lower() in {
        ".raw", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff", ".pgm", ".ppm"
    }


def number(value):
    if value in (None, ""):
        return None
    n = float(value)
    if not math.isfinite(n):
        raise ValueError("Non-finite number in report")
    return int(n) if n.is_integer() else n


def row(base, **values):
    result = dict.fromkeys(COLUMNS)
    result.update(base, inference_ms=0, **values)
    for key in ("right", "invalid", "ok", "recovery_skipped"):
        if result[key] is not None:
            result[key] = int(result[key])
    result["prediction_usable"] = int(result["ok"] == 1 and
        result["invalid"] != 1 and result["recovery_skipped"] != 1)
    return result


def desktop_rows(path, base):
    if path.suffix == ".json":
        data = read_json(path)
        for record in data["records"]:
            q = record["quantized"]
            yield row(base, name_image=image_name(record["file"]), quantized=q,
                      scores=record["scores"], output_indices=list(range(len(q))),
                      output_scope="full", result=record.get("result", record.get("top", [{}])[0].get("index")),
                      label=record.get("label"), right=record.get("right"),
                      invalid=record.get("invalid"), ok=1)
        for error in data.get("errors", []):
            yield row(base, name_image=image_name(error["file"]), ok=0, error=error["error"])
        return
    text = path.read_text(encoding="utf-8-sig")
    current = None
    blocks = []
    for line in text.splitlines():
        match = BINARY.match(line)
        if match:
            name, q, scores, result, label, right, invalid = match.groups()
            q = json.loads(q)
            yield row(base, name_image=image_name(name), quantized=q, scores=json.loads(scores),
                      output_indices=list(range(len(q))), output_scope="full", result=None if result == "None" else int(result),
                      label=int(label), right=int(right), invalid=invalid == "True", ok=1)
        elif re.search(r"\.raw\s*\|", line, re.I):
            if "quantized=" in line:
                raise ValueError(f"Unrecognized inference row: {path}")
            name, error = line.split("|", 1)
            yield row(base, name_image=image_name(name.strip()), ok=0, error=error.strip())
        elif line.strip().lower().endswith(".raw"):
            current = [line.strip(), []]
            blocks.append(current)
        elif current is not None:
            current[1].append(line)
    for name, lines in blocks:
        top = TOP.findall("\n".join(lines))
        if not top:
            raise ValueError(f"Missing Top-K values: {path}: {name}")
        yield row(base, name_image=image_name(name), quantized=[int(x[1]) for x in top],
                  scores=[float(x[2]) for x in top], output_indices=[int(x[0]) for x in top],
                  output_scope="top_k", result=int(top[0][0]), ok=1)


def esp32_rows(path, base, config, warnings):
    metadata_path = path.with_name("metadata.json")
    metadata = read_json(metadata_path) if metadata_path.exists() else {}
    scale = metadata.get("output_scale", config.get("output_scale"))
    zero = metadata.get("output_zero_point", config.get("output_zero_point"))
    if "output_scale" not in metadata:
        warnings.append(f"{base['source_file']}: output quantization from analysis/config.json; no recorded output scale.")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        classes = sorted((key for key in reader.fieldnames or [] if re.fullmatch(r"class_\d+_raw", key)),
                         key=lambda key: int(key.split("_")[1]))
        if not classes or not {"name_image", "ok", "result"}.issubset(reader.fieldnames or []):
            raise ValueError(f"Unsupported ESP32 CSV: {path}")
        for record in reader:
            # Firmware appends human-readable summaries after the CSV samples.
            # Reject those before parsing numbers or normalizing Cloudinary names.
            if not is_image(record.get("name_image")):
                continue
            skipped = number(record.get("recovery_skipped"))
            ok = number(record["ok"])
            valid = ok == 1 and skipped != 1
            q = [number(record[key]) for key in classes] if valid else None
            scores = [(v - zero) * scale for v in q] if q is not None and scale is not None and zero is not None else None
            output = row(base, name_image=image_name(record["name_image"], True),
                         quantized=q, scores=scores, output_indices=[int(key.split("_")[1]) for key in classes] if valid else None,
                         output_scope="full" if valid else None, result=number(record["result"]) if valid else None,
                         label=number(record.get("label")), right=number(record.get("right")) if valid else None,
                         ok=ok, recovery_attempts=number(record.get("recovery_attempts")), recovery_skipped=skipped)
            output["inference_ms"] = number(record.get("inference_ms"))
            yield output


def discover(root, config):
    sources = []
    for model_dir in sorted((root / "models").glob("*")):
        if not model_dir.is_dir():
            continue
        for runtime, folder, names in [("wasm", "reports", ["12-inferencia-wasm.txt"]),
                                       ("tflite", "reports_tflite", ["results-report.json", "inference-report.txt"])]:
            parents = sorted({p.parent for name in names for p in (model_dir / folder).rglob(name)})
            for parent in parents:
                source = next(parent / name for name in names if (parent / name).is_file())
                sources.append((source, model_dir.name, runtime, "desktop", {}))
    for project, info in config["esp32_projects"].items():
        for source in sorted((root / "ESP32" / project / "reports").rglob("report.csv")):
            sources.append((source, info["model"], info["type"], "esp32", info))
    for item in sorted(sources, key=lambda x: (x[0].parent.name, x[0].as_posix())):
        if not item[0].resolve().is_relative_to(root.resolve()):
            raise ValueError("Report outside repository")
        yield item


def csv_bytes(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, delimiter=";", extrasaction="ignore")
    writer.writeheader()
    for record in rows:
        writer.writerow({key: json.dumps(value, separators=(",", ":"), allow_nan=False) if isinstance(value, list) else value
                         for key, value in record.items()})
    return stream.getvalue().encode("utf-8-sig")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def consolidate(root=ROOT):
    root = Path(root)
    with LOCK:
        destination = root / "analysis"
        config = read_json(destination / "config.json")
        previous = read_json(destination / "consolidated.json") if (destination / "consolidated.json").exists() else {}
        ids = previous.get("execution_ids", {})
        rows, executions, warnings = [], [], []
        for path, model, runtime, env, info in discover(root, config):
            if model == "mobilenetv2_alpha035":
                continue
            folder = path.parent.relative_to(root).as_posix()
            if folder not in ids:
                ids[folder] = max(ids.values(), default=0) + 1
            base = dict(execution=ids[folder], model=model, type=runtime, env=env,
                        source_file=path.relative_to(root).as_posix())
            items = list(esp32_rows(path, base, info, warnings) if env == "esp32" else desktop_rows(path, base))
            items = [item for item in items if is_image(item["name_image"])]
            if not items:
                warnings.append(f"{base['source_file']}: no sample rows found.")
            names = [r["name_image"] for r in items]
            if len(set(names)) != len(names):
                warnings.append(f"{base['source_file']}: duplicate normalized image names; rows preserved.")
            rows.extend(items)
            executions.append(dict(base, folder=folder, rows=len(items)))
        result = dict(generated_at=datetime.now(timezone.utc).isoformat(), columns=COLUMNS,
                      rows=rows, executions=executions, execution_ids=ids, warnings=warnings)
        # Validate everything before replacing existing output files.
        payload = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        table = csv_bytes(COLUMNS, rows)
        mapping = csv_bytes(["execution", "model", "type", "env", "folder", "source_file", "rows"], executions)
        atomic_write(destination / "consolidated.csv", table)
        atomic_write(destination / "executions.csv", mapping)
        atomic_write(destination / "consolidated.json", payload)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    report = consolidate()
    print(f"analysis/consolidated.csv: {len(report['rows'])} rows, {len(report['executions'])} executions")
    for warning in report["warnings"]:
        print(warning)
