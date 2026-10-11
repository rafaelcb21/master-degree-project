"""Select the most frequent complete ESP32 output per image, retaining evidence."""
from collections import defaultdict
import csv
import io
import math
import re


def output_key(record):
    q = record.get("quantized")
    scores = record.get("scores")
    if record.get("ok") != 1 or record.get("recovery_skipped") == 1:
        return None
    if record.get("result") is None:
        return None
    if not isinstance(q, list) or not q or any(v is None or not math.isfinite(v) for v in q):
        return None
    if scores is not None and (len(scores) != len(q) or any(v is None or not math.isfinite(v) for v in scores)):
        return None
    return (tuple(q), tuple(scores) if scores is not None else None,
            tuple(record.get("output_indices") or range(len(q))), record.get("result"))


def select_image(records):
    per_run = defaultdict(list)
    for record in records:
        per_run[record["execution"]].append(record)
    duplicates = sorted(run for run, items in per_run.items() if len(items) != 1)
    good = [items[0] for run, items in sorted(per_run.items())
            if run not in duplicates and output_key(items[0]) is not None]
    variants = defaultdict(list)
    for record in good:
        variants[output_key(record)].append(record)
    ordered = sorted(variants.values(), key=lambda items: (-len(items), items[0]["execution"]))
    conflicts = []
    for field in ("model_sha256", "input_sha256", "input_format", "width", "height", "output_type", "output_scale", "output_zero_point"):
        values = {record.get("_identity", {}).get(field) for record in good}
        values.discard(None)
        if len(values) > 1:
            conflicts.append(field)
    labels = {record["label"] for record in good if record.get("label") is not None and record["label"] >= 0}
    if len(labels) > 1:
        conflicts.append("label")
    if conflicts:
        status = "conflict"
    elif not ordered:
        status = "no_valid"
    elif len(ordered) > 1 and len(ordered[0]) == len(ordered[1]):
        status = "tie"
    elif len(good) == 1:
        status = "single"
    else:
        status = "equal" if len(ordered) == 1 else "mode"
    chosen = ordered[0][0] if status in ("single", "equal", "mode") else None
    return dict(status=status, winner=chosen, observations=len(good), available=len(per_run),
                votes=len(ordered[0]) if ordered else 0, variant_count=len(ordered),
                duplicate_executions=duplicates,
                excluded_executions=sorted(set(per_run) - {r["execution"] for r in good}),
                conflicts=conflicts,
                input_identity_verified=bool(good) and all(r.get("_identity", {}).get("input_sha256") for r in good),
                model_identity_verified=bool(good) and all(r.get("_identity", {}).get("model_sha256") for r in good),
                variants=[dict(quantized=items[0]["quantized"], scores=items[0]["scores"],
                               result=items[0]["result"], votes=len(items),
                               executions=[r["execution"] for r in items],
                               sources=[r["source_file"] for r in items]) for items in ordered])


def build(rows, executions, ids, generated_at):
    """Return synthetic consolidation rows, report summary and files to publish."""
    from consolidate_reports import csv_bytes, COLUMNS
    grouped = defaultdict(list)
    for record in rows:
        if record["env"] == "esp32":
            grouped[(record["model"], record["type"])].append(record)
    derived, runs, groups, artifacts = [], [], [], {}
    for (model, runtime), records in sorted(grouped.items()):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", model) or runtime not in ("wasm", "tflite"):
            raise ValueError("Unsupported ESP32 model/runtime for representative reports")
        folder = f"analysis/esp32_consensus/{model}/{runtime}"
        source_file = folder + "/report.csv"
        if folder not in ids:
            ids[folder] = max(ids.values(), default=0) + 1
        by_image = defaultdict(list)
        for record in records:
            by_image[record["name_image"]].append(record)
        images, report_rows = [], []
        for name, observations in sorted(by_image.items()):
            selection = select_image(observations)
            winner = selection.pop("winner")
            image = dict(name_image=name, **selection,
                         selected_execution=winner["execution"] if winner else None,
                         selected_source=winner["source_file"] if winner else None)
            images.append(image)
            template = winner or sorted(observations, key=lambda r: r["execution"])[0]
            result = {key: template.get(key) for key in COLUMNS}
            result.update(execution=ids[folder], source_file=source_file,
                          consensus_status=selection["status"], consensus_votes=selection["votes"],
                          consensus_observations=selection["observations"],
                          selected_execution=image["selected_execution"])
            if not winner:
                result.update(ok=0, prediction_usable=0, quantized=None, scores=None, result=None,
                              right=None, inference_ms=None, output_indices=None,
                              error="ESP32 representative report: " + selection["status"])
            elif winner["result"] == -1:
                result.update(invalid=1, prediction_usable=0)
            derived.append(result)
            raw = dict(template.get("_source_record", {}))
            # Keep the actual row's measurements; they are never averaged or voted.
            raw.update(name_image=name, ok=result["ok"], result=result["result"],
                       label=result["label"], right=result["right"], inference_ms=result["inference_ms"],
                       consensus_status=selection["status"], consensus_votes=selection["votes"],
                       consensus_observations=selection["observations"],
                       selected_execution=image["selected_execution"], selected_source=image["selected_source"])
            if not winner:
                for key in raw:
                    if re.fullmatch(r"class_\d+_raw", key):
                        raw[key] = None
            report_rows.append(raw)
        columns = ["name_image", "ok"]
        classes = sorted({key for record in report_rows for key in record if re.fullmatch(r"class_\d+_raw", key)},
                         key=lambda key: int(key.split("_")[1]))
        columns += classes + ["result", "label", "right", "inference_ms"]
        columns += sorted({key for record in report_rows for key in record} - set(columns))
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report_rows)
        artifacts[source_file] = stream.getvalue().encode("utf-8-sig")
        run = dict(execution=ids[folder], model=model, type=runtime, env="esp32", folder=folder,
                   source_file=source_file, rows=len(images), derived=True)
        runs.append(run)
        groups.append(dict(model=model, type=runtime, execution=ids[folder], images=images,
                           source_file=source_file, source_executions=sorted({r["execution"] for r in records}),
                           source_rows=len(records), selected=sum(r["selected_execution"] is not None for r in images),
                           unresolved=sum(r["selected_execution"] is None for r in images),
                           statuses={status: sum(r["status"] == status for r in images)
                                     for status in ("equal", "mode", "single", "tie", "conflict", "no_valid")}))
    summary = dict(generated_at=generated_at, groups=groups,
                   sources=[run for run in executions if run["env"] == "esp32"],
                   method="Full output-vector mode per model/runtime/image; one vote per source execution; unique maximum required.")
    evidence = [dict(model=g["model"], type=g["type"], **item) for g in groups for item in g["images"]]
    artifacts["analysis/esp32_consensus/images.csv"] = csv_bytes(
        ["model", "type", "name_image", "status", "votes", "observations", "available", "variant_count",
         "selected_execution", "selected_source", "duplicate_executions", "excluded_executions", "conflicts"], evidence)
    return derived, runs, summary, artifacts
