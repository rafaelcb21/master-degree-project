"""Read preserved TFLM reports; no inference, consolidation or firmware changes."""
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNS = ["20261008T215503505222Z", "20261009T120557541292Z"]


def digest(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return [r for r in csv.DictReader(stream) if r.get("name_image") and not r["name_image"].startswith("#")]


def normalized(name):
    return name.split("_")[0] + ".raw" if "_" in name else name


def summarize(path):
    records = rows(path)
    names = [normalized(r["name_image"]) for r in records]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate image names: {path}")
    successful = [r for r in records if r["ok"] == "1"]
    times = [Decimal(r["inference_ms"]) for r in successful]
    if not times or any(t <= 0 or not t.is_finite() for t in times):
        raise ValueError("Invalid timing data")
    count = len(records)
    mean = sum(times) / len(times)
    correct = sum(r.get("right") == "1" and r.get("ok") == "1" for r in records)
    invalid = sum(r.get("ok") != "1" or r.get("result") not in ("0", "1") for r in records)
    stats = {"rows": count, "successful": len(successful), "failed": count - len(successful),
             "correct": correct, "valid_wrong": count - correct - invalid, "without_valid_prediction": invalid,
             "accuracy_pct_all_rows": str(Decimal(100) * correct / count),
             "class_counts": dict(Counter(r["label"] for r in records)),
             "mean_ms": str(mean), "min_ms": str(min(times)), "max_ms": str(max(times)),
             "mean_seconds": str(mean / 1000),
             "preprocess_mean_ms": str(sum(Decimal(r["preprocess_ms"]) for r in successful) / len(successful)),
             "invoke_mean_ms": str(sum(Decimal(r["invoke_ms"]) for r in successful) / len(successful)),
             "resumed_rows_with_attempts_gt_1": sum(int(r.get("recovery_attempts") or 0) > 1 for r in records),
             "input_hashes_recorded": sum(bool(r.get("input_sha256")) for r in records)}
    return stats, {normalized(r["name_image"]): r for r in records}


def main():
    result = {"audit_date": "2026-10-15", "method": "Read-only Decimal statistics from successful raw CSV rows; accuracy uses all rows", "runs": {}}
    data = {}
    for run in RUNS:
        source = ROOT / "ESP32/cnn_tflite_esp32/reports" / run
        target = OUT / "fontes" / run
        target.mkdir(parents=True, exist_ok=True)
        for name in ("report.csv", "metadata.json"):
            shutil.copyfile(source / name, target / name)
        stats, data[run] = summarize(source / "report.csv")
        metadata = json.loads((source / "metadata.json").read_text(encoding="utf-8"))
        for key, value in [("total", stats["rows"]), ("success", stats["successful"]), ("correct", stats["correct"])]:
            if metadata[key] != value:
                raise ValueError(f"Metadata mismatch: {run} {key}")
        result["runs"][run] = {"source": source.relative_to(ROOT).as_posix(), "stats": stats, "metadata": metadata,
                               "csv_identity": digest(source / "report.csv"), "metadata_identity": digest(source / "metadata.json")}
    a, b = (data[run] for run in RUNS)
    common = a.keys() & b.keys()
    result["between_complete_runs"] = {
        "common_images": len(common),
        "same_labels": sum(a[k]["label"] == b[k]["label"] for k in common),
        "same_input_sha256": sum(a[k]["input_sha256"] == b[k]["input_sha256"] for k in common),
        "same_predictions": sum(a[k]["result"] == b[k]["result"] for k in common),
        "same_output_vectors": sum((a[k]["class_0_raw"], a[k]["class_1_raw"]) == (b[k]["class_0_raw"], b[k]["class_1_raw"]) for k in common),
    }
    representative = ROOT / "analysis/esp32_consensus/drowsiness/tflite/report.csv"
    representative_data = {r["name_image"]: r for r in rows(representative)}
    rep = OUT / "fontes" / "acuracia-representativa.csv"
    shutil.copyfile(representative, rep)
    result["representative_accuracy"] = {"source": representative.relative_to(ROOT).as_posix(),
        "identity": digest(representative), "rows": len(representative_data),
        "correct": sum(r["right"] == "1" for r in representative_data.values()),
        "without_valid_prediction": sum(r["result"] not in ("0", "1") for r in representative_data.values()),
        "selected_source_counts": dict(Counter(r["selected_source"] for r in representative_data.values())),
        "same_predictions_vs_selected_raw_run": sum(k in b and r["result"] == b[k]["result"] for k, r in representative_data.items())}
    model = ROOT / "models/drowsiness/model_int8_esp32.tflite"
    result["current_model"] = {"source": model.relative_to(ROOT).as_posix(), **digest(model)}
    if any(run["metadata"]["model_sha256"] != result["current_model"]["sha256"] for run in result["runs"].values()):
        raise ValueError("Model hashes do not match")
    selected = result["runs"][RUNS[-1]]["stats"]
    result["selected_run"] = RUNS[-1]
    result["contextual_ratios_using_rounded_thesis_wasm_times"] = {
        "interpreted_160_seconds": "144.019", "aot_240_seconds": "6.195",
        "interpreted_divided_by_selected_tflm": str(Decimal("144.019") / Decimal(selected["mean_seconds"])),
        "aot_240_divided_by_selected_tflm": str(Decimal("6.195") / Decimal(selected["mean_seconds"]))}
    thesis = Path("C:/Users/rafae/Downloads/latex-mestrado-2/Dissertacao_Rafael_Braga_UNICO.tex")
    if thesis.is_file():
        text = thesis.read_text(encoding="utf-8")
        snippets = []
        for label in ("tab:configuracoes-experimentos-wasm", "tab:tempos-inferencia-aceleracao", "tab:acuracia-configuracoes"):
            position = text.index("\\label{" + label + "}")
            start = text.rfind("\\begin{table}", 0, position)
            end = text.index("\\end{table}", position) + len("\\end{table}")
            snippets.append(text[start:end])
        (OUT / "fontes/tabelas-da-versao-consultada.tex").write_text("\n\n".join(snippets) + "\n", encoding="utf-8")
        result["dissertation_examined"] = {"path": str(thesis), **digest(thesis), "modified": False}
    (OUT / "evidencias-report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (OUT / "coletas.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["run", *selected.keys()])
        writer.writeheader()
        for run in RUNS:
            writer.writerow({"run": run, **result["runs"][run]["stats"]})
    print(json.dumps({"runs": {k: v["stats"] for k, v in result["runs"].items()},
                      "between_complete_runs": result["between_complete_runs"],
                      "representative_accuracy": result["representative_accuracy"],
                      "ratios": result["contextual_ratios_using_rounded_thesis_wasm_times"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
