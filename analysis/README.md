# Consolidated benchmark results

[Português (Brasil)](README.pt-BR.md)

Open **Consolidated analysis** in the web sidebar. **Generate / update table** rebuilds the saved files. Navigation, filters and pagination only read saved data. No models are executed.

CLI, from the repository root: `python consolidate_reports.py`.

## MobileNetV2 Top-15 (separate table)

Use the **MobileNetV2 · Top-15** tab. Its button regenerates only `mobilenet_top15.csv`; the Drowsiness button regenerates only `consolidated.csv`. MobileNetV2 is excluded from the Drowsiness table.

Columns: `model;execution;score;q;name`, with names such as `[404] airliner`. Each execution has 15 rows in original rank order. Both runtimes use their TXT reports: `reports/**/12-inferencia-wasm.txt` and `reports_tflite/**/inference-report.txt`. A report must contain exactly one complete Top-15; incomplete or multiple rankings stop regeneration and preserve the previous file.

`mobilenet_executions.csv` maps IDs to WASM/TFLite, folders and source files. IDs are stable within this table and independent of the Drowsiness IDs. The web execution selector also shows the runtime and folder. Saved data lives in `mobilenet_top15.json`. CLI: `python consolidate_mobilenet.py`.

## Files

- `consolidated.csv`: one row per image/execution; UTF-8 with BOM, semicolon delimiter, JSON arrays inside cells.
- `executions.csv`: execution IDs mapped to source folders and files.
- `consolidated.json`: cached data and persistent ID registry. Preserve this file to keep IDs stable across updates.
- `config.json`: ESP32 host/model/runtime mapping and fallback output quantization. Update when changing the embedded model. Metadata quantization takes precedence; fallback use appears in source notes.

Each folder is a separate execution, as requested. Renaming a folder creates a new identity. Nothing is deduplicated across execution folders.

## Interpretation

- ESP32: `A0001_pngxcr.raw` becomes `A0001.raw`, preserving case. Desktop names, including `aviao_uint8.raw`, are unchanged.
- `scores = (quantized - zero_point) * scale` for ESP32. Desktop scores come from the report.
- `output_indices` identifies the positions/classes of the arrays. Drowsiness positions `[0,1]` correspond to labels `[1,0]`.
- MobileNetV2 uses the separate Top-15 table described above; absent classes are not necessarily zero.
- Desktop `inference_ms=0` means timing is not used. ESP32 times retain their original measurement scope, which may differ between runtimes.
- Missing `invalid` and recovery fields stay blank. Blank means unknown, not false.
- Failed/skipped rows remain, with empty prediction arrays, result and correctness. `prediction_usable=1` excludes failures, skipped images and explicitly invalid outputs; it cannot prove validity when `invalid` is unknown.

Sources: `models/*/reports/**/12-inferencia-wasm.txt`, `models/*/reports_tflite/**/results-report.json` (TXT fallback), and configured `ESP32/*/reports/**/report.csv`. Only one desktop representation is used per folder. Empty reports and duplicate normalized names produce notes. Parse errors stop regeneration and preserve existing output.
