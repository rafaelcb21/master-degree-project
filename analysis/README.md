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

Desktop folders remain separate executions. For ESP32, consolidation uses one representative report per model/runtime. Original executions remain in JSON `raw_rows` and `raw_executions` for determinism analysis. Renaming a folder creates a new identity.

## ESP32 representative reports

Open **Analyses → Representative reports · ESP32** and click **Generate / update reports**. Generation also updates consolidated analysis. Its generate button and `python consolidate_reports.py` perform the same selection.

Per image, equal outputs are retained and differing outputs are grouped by the complete vector (`quantized`, `scores`, indices and result). Each execution contributes one vote. A unique most frequent variant is selected; an absolute majority is not required. Ties, identity conflicts and missing complete outputs remain unusable. Failures, skipped images and duplicate image records within an execution do not vote. Single observations are retained and identified. Image normalization preserves case.

Generated CSVs live in `esp32_consensus/<model>/<wasm|tflite>/report.csv`. The row and timings are copied from the earliest execution with the selected vector. Consolidation records `consensus_status`, `consensus_votes`, `consensus_observations` and `selected_execution`. `esp32_consensus/report.json` records all variants, votes, exclusions and sources; `images.csv` summarizes selection. Recorded hashes and configurations are checked when available; matching names without hashes do not establish matching bytes. Original reports remain unchanged and determinism analysis continues using all original executions.

## Interpretation

### Environment and runtime comparison

**Quantized difference statistics**, **Quantized difference distribution** and **Accuracy by reference class** read the same saved data and provide CSV/Markdown downloads: `quantized_stats.*`, `quantized_buckets.*` and `accuracy.*`. The first includes maximum, mean, median, P95/P99 and Δq=0 count/percentage; the second includes the five quantized buckets. Each comparable image contributes two components, so 2,000 complete image pairs produce N=4,000 differences. Decimal rounding is half-up, matching the interface; unrounded values remain in the detailed JSON.

Accuracy reports include Overall, class 0 (non_drowsy) and class 1 (drowsy) per selected source. Correct means `result == label`, recalculated against reference labels. Each source/image is counted once despite appearing in three pairs. The main percentage is correct / all labelled images in the reference class; failures, invalid outputs and ties do not count as correct. Coverage also displays accuracy among valid predictions, unknown labels and missing/duplicate records outside the denominator. This measures performance against reference labels separately from agreement between implementations. No new inferences are needed. Generating comparisons refreshes all these files and includes accuracy in JSON.

The **Agreement summary** section shows all six comparisons with differing/identical vectors, vector agreement, class changes and class agreement. It reads saved data without new inferences or comparison regeneration. Download `agreement.csv` (UTF-8 BOM, `;` delimiter) or `agreement.md` (ready-to-copy table), including denominators and execution IDs. Generation also updates these files.

Vector agreement = numerically identical quantized vectors and scores / comparable vectors, independently of the decision. Class agreement = identical classes / pairs with comparable vectors and valid classes on both sides. Invalid outputs, ties and non-comparable pairs are excluded from this denominator. **Denominators and coverage** displays exclusions. Percentages without comparable observations are unavailable (—), never 100%.

Open **Analyses → Environment and runtime comparison**. **Generate / update comparisons** refreshes consolidation and ESP32 representative reports, then builds six pairs: WASM ESP32 × TFLite ESP32; WASM desktop × TFLite desktop; WASM ESP32 × TFLite desktop; WASM desktop × TFLite ESP32; WASM ESP32 × WASM desktop; TFLite desktop × TFLite ESP32. Desktop defaults to its latest execution, with selectors for other executions. Each side uses one selected execution, without mixing desktop runs.

Images match by exact case-sensitive name and outputs by index. Each image shows scores and predicted class side by side, quantized vectors, sources, absolute component differences, maximum, mean, median, P95 and P99 for both quantized values and scores. Counts `0`, `1`, `2–5`, `6–10` and `>10` refer to quantized differences. Drowsiness has two output components: index 0 is class 1 (drowsy), index 1 is class 0 (non_drowsy).

Statistics include zeros and percentiles use linear interpolation. Summaries aggregate all comparable components, without averaging averages. Missing images, failures, unresolved selection, duplicates and incomplete vectors are non-comparable with empty statistics; they do not become zero differences. Completed invalid outputs allow numeric comparison but do not count as transitions between valid classes. Class changes and decision changes are distinct. Equality requires matching values and decisions.

Files live in `analysis/comparisons/`: one CSV per pair, `images.csv` for all six pairs, `summary.csv` for aggregate statistics, and `report.json` for detailed evidence and selected executions. CSVs use UTF-8 BOM and `;` delimiters. Browsing reads saved files and flags changed consolidation. CLI: `python compare_environments.py`, which refreshes sources and defaults to the latest desktop executions. Comparisons are limited to recorded precision; matching names do not prove identical bytes or establish the cause of differences.

- ESP32: `A0001_pngxcr.raw` becomes `A0001.raw`, preserving case. Desktop names, including `aviao_uint8.raw`, are unchanged.
- `scores = (quantized - zero_point) * scale` for ESP32. Desktop scores come from the report.
- `output_indices` identifies the positions/classes of the arrays. Drowsiness positions `[0,1]` correspond to labels `[1,0]`.
- MobileNetV2 uses the separate Top-15 table described above; absent classes are not necessarily zero.
- Desktop `inference_ms=0` means timing is not used. ESP32 times retain their original measurement scope, which may differ between runtimes.
- Missing `invalid` and recovery fields stay blank. Blank means unknown, not false.
- Failed/skipped rows remain, with empty prediction arrays, result and correctness. `prediction_usable=1` excludes failures, skipped images and explicitly invalid outputs; it cannot prove validity when `invalid` is unknown.

Sources: `models/*/reports/**/12-inferencia-wasm.txt`, `models/*/reports_tflite/**/results-report.json` (TXT fallback), and configured `ESP32/*/reports/**/report.csv`. Only one desktop representation is used per folder. Empty reports and duplicate normalized names produce notes. Parse errors stop regeneration and preserve existing output.
