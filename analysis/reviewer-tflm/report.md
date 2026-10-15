# Reviewer recommendation 7(a) — TensorFlow Lite Micro in Tables 5.2 and 5.3

[English](report.md) | [Português (Brasil)](relatorio.pt-BR.md)

**Date:** October 15, 2026. **Purpose:** supply verified data and ready-to-integrate changes for the dissertation project. No inference was executed and the original dissertation file was not modified.

## 1. Conclusion and recommended changes

The **TensorFlow Lite Micro (TFLM), ESP-NN enabled, ESP32-CAM at 240 MHz** experiment already has two complete collections of 2,000 images, with CSV and metadata. Exact timing and accuracy **from the same collection** can be reported without running new experiments to obtain those numbers.

Use collection **`20261009T120557541292Z`** as the single source for the TFLM row in both tables. It is the more recent of the two complete collections examined; it was not selected by choosing individual samples with lower times or higher accuracy. Later four-image collections must not replace the 2,000-image evaluation.

| Table | Change |
|---|---|
| **5.2**, `tab:tempos-inferencia-aceleracao` | Replace the approximate TFLM row with mean **1.777 s**, minimum **1.761 s**, maximum **1.793 s**, and descriptive speedup **81.06×** using the table's existing reference. |
| **5.3**, `tab:acuracia-configuracoes` | Identify the row as **TFLM + ESP-NN, ESP32-CAM, 240 MHz**, retaining **1,990 correct, 9 incorrect valid predictions, 1 without a valid prediction, 99.50%**; attribute these figures to the same collection used in Table 5.2. |

**Current document:** a TFLM row already exists in Table 5.2, showing `≈ 1.7 s` with minimum, maximum and speedup left blank. Replace it rather than adding a second TFLM row. Table 5.3 already contains the figures above under the generic name `TFLite ESP32-CAM`; make the runtime explicit and document its source. Table numbers were checked in the `.aux`; LaTeX labels remain the more stable reference if numbering changes.

## 2. Selected source and model identity

In the source repository:

```text
ESP32/cnn_tflite_esp32/reports/20261009T120557541292Z/report.csv
ESP32/cnn_tflite_esp32/reports/20261009T120557541292Z/metadata.json
```

Copies included in this package: [CSV](fontes/20261009T120557541292Z/report.csv) and [metadata](fontes/20261009T120557541292Z/metadata.json).

| Configuration | Recorded evidence |
|---|---|
| Runtime | `TensorFlow Lite Micro` |
| TFLM component | `1.3.5` |
| Kernels | `ESP-NN enabled` |
| CPU | `240 MHz` |
| ESP-IDF | `v5.3.1-dirty` |
| Input | 128 × 128; two classes; format 1, corresponding to little-endian RGB565 in the host |
| Output | `uint8`, scale `0.00390625`, zero point `0` |
| Arena reserved / used | 1,048,576 / 312,380 bytes |
| Warm-up | `0` runs declared |
| Processed / successful / failed | 2,000 / 2,000 / 0 |
| Restored results | `resumed=0` |
| Reference classes | 1,000 images per class |

The model SHA-256 recorded in metadata matches the digest calculated from `models/drowsiness/model_int8_esp32.tflite` in the current repository:

```text
b4521f926f0133355f970f237ca2c372af36dcae5265766a5f42f717954f02b0
```

Selected CSV SHA-256:

```text
315281d10ac4cb369bead77faef47d4ff788ab85c1a4416e59275ebda4afbeae
```

Selected metadata SHA-256:

```text
1ec223db5d33be36f64f1ced05734d1d40aaf900efd5c87f7b1c62ede0687aa0
```

These versions and settings are those recorded in the collection's metadata. New firmware settings are not retroactively attributed to this collection. `ESP-NN enabled` identifies the declared configuration without establishing that every operator uses optimized kernels.

## 3. Values calculated from the CSV

Timing statistics use all 2,000 successful rows in the selected collection. Accuracy uses all 2,000 images, including the observation without a valid decision.

| Metric | Value derived from recorded data | Suggested display |
|---|---:|---:|
| Mean inference time | **1,776.7145665 ms = 1.7767145665 s** | **1.777 s** |
| Minimum time | **1,760.819 ms = 1.760819 s** | **1.761 s** |
| Maximum time | **1,792.774 ms = 1.792774 s** | **1.793 s** |
| Mean preprocessing | 11.7326165 ms | 11.733 ms |
| Mean `Invoke` | 1,764.98195 ms | 1,764.982 ms |
| Correct predictions | **1,990** | **1,990** |
| Incorrect valid predictions | **9** | **9** |
| Without a valid prediction | **1**, due to a tie | **1** |
| Processing failures | **0** | **0** |
| Accuracy | **1,990 / 2,000 × 100 = 99.50%** | **99.50%** |

The tie is not a processing failure: inference completed without yielding a unique class. All 2,000 timings are therefore included, and the tied observation remains in the accuracy denominator as incorrect. Do not add the tie again to the nine entries in the incorrect-valid-predictions column.

The extended decimal values are arithmetic results from times recorded to three decimal places in milliseconds; they do not imply additional instrument resolution.

## 4. Timing interval and WASM comparison

Metadata defines `inference_ms_scope` as **`prepare_input + Invoke; download, checkpoint and output reading excluded`**. Timing therefore includes input preparation, including host RGB565 → RGB888 conversion, and TFLM execution. It excludes downloads, checkpoint persistence and output reading.

In the host, `esp_timer_get_time()` measures the interval immediately before `model_prepare_input(...)` and after `model_invoke()`. The historical interval specification is preserved in metadata; the current source allows implementation inspection without replacing the collection record.

Use **`inference_ms`**, not only `invoke_ms`, for comparison. Using only `Invoke` would remove preprocessing from the TFLM time while it remains included in the WASM inference call. Even with the same category of stage included, the implementations have different boundaries and structures; this does not eliminate all confounding factors.

Using the **6.195 s WASM AOT time at 240 MHz already reported in the dissertation**:

```text
6.195 / 1.7767145665 = 3.4867727866 ≈ 3.49
```

Thus, the dissertation's WASM AOT mean latency is approximately **3.49 times** the TFLM mean latency from this collection. The WASM value was not recalculated here: this is a contextual comparison with the existing table, not a new paired measurement or proof of firmware identity across the two collections.

For Table 5.2's speedup column, referenced to interpreted WAMR at 160 MHz:

```text
144.019 / 1.7767145665 = 81.0591654481 ≈ 81.06×
```

This ratio is descriptive and also involves different frequencies and sample sizes: the interpreted reference contains six images, while TFLM contains 2,000. If speedup is reserved strictly for WAMR strategies, keep `---` in that cell and give **3.49×** in the comparison paragraph. Explain that this omission reflects the scope of comparison rather than missing TFLM timing data.

**Interpretation:** the difference measures the relative performance of **WAMR AOT with operators implemented in WAT** and **TFLM with ESP-NN enabled**. It does not isolate an exclusive portability cost: kernels, optimizations, memory organization and runtimes differ. Avoid describing it as an “exclusive WebAssembly overhead” or “pure portability cost.”

## 5. Checking the “same collection” requirement

The two complete collections examined yielded:

| Collection | Images | Mean (s) | Minimum (s) | Maximum (s) | Correct / incorrect valid / no class |
|---|---:|---:|---:|---:|---:|
| `20261008T215503505222Z` | 2,000 | 1.7797058455 | 1.759206 | 1.791081 | 1,990 / 9 / 1 |
| **`20261009T120557541292Z` — selected** | **2,000** | **1.7767145665** | **1.760819** | **1.792774** | **1,990 / 9 / 1** |

Both have identical model and image-list hashes. Pairing the CSVs confirmed **2,000 identical names, labels and input hashes**, as well as identical class decisions on all 2,000 images. Output vectors are identical on 1,996 images; four images have numerical differences without a decision change.

The currently saved [representative accuracy report](fontes/acuracia-representativa.csv) combines **1,999 records from the first collection and one from the second**. It must not be treated as a single timing benchmark. All 2,000 of its decisions match those of the selected collection, and it also has 1,990 correct predictions and one tie.

**Solution:** explicitly attribute both TFLM rows in Tables 5.2 and 5.3 to raw CSV `20261009T120557541292Z`. Accuracy figures remain unchanged, now sourced from the same collection as timing. Do not automatically replace fidelity-study vectors with this CSV: that analysis uses its own sources and rules.

## 6. Suggested dissertation text

> As an embedded reference, the same drowsiness model was executed on ESP32-CAM at 240 MHz using TensorFlow Lite Micro, component version 1.3.5, with ESP-NN enabled. Collection `20261009T120557541292Z` processed 2,000 images, with a mean inference time of 1.776715 s, minimum of 1.760819 s and maximum of 1.792774 s. The interval includes input preparation and `Invoke`, excluding downloads, checkpoint writes and output reading. No explicit warm-up was performed, according to collection metadata. There were 1,990 correct predictions, nine incorrect valid predictions and one tie, yielding 99.50% accuracy over all 2,000 images. TFLM timing and accuracy in Tables 5.2 and 5.3 were calculated from this same collection.

> Compared with the 6.195 s WASM AOT mean at 240 MHz reported in Table 5.2, TFLM achieved a mean latency approximately 3.49 times lower. This ratio characterizes the relative performance of the evaluated implementations rather than an exclusive portability cost, since kernels, optimizations and execution organization differ. The comparison between interpreted WAMR and WAMR AOT at 160 MHz remains the specific evaluation of the effect of the WebAssembly execution strategy on the same hardware and frequency.

**Suggested response to the reviewer:**

> The recommendation has been addressed by including detailed results for the TensorFlow Lite Micro reference with ESP-NN on ESP32-CAM at 240 MHz. Table 5.2 now reports mean, minimum and maximum timings calculated over 2,000 images, and Table 5.3 explicitly identifies this runtime. Both rows use the same collection, with 1,990 correct predictions and 99.50% accuracy. The discussion explains that the latency ratio measures relative implementation performance without isolating an exclusive portability cost.

Use the past-tense response **after applying the changes** in the dissertation project. This task prepared the report and snippets without editing the external `.tex` file.

## 7. Transfer files and instructions for the other project

- [alteracoes-sugeridas.tex](alteracoes-sugeridas.tex): Portuguese LaTeX rows and paragraphs ready for integration; not a standalone compilable document.
- [evidencias-report.json](evidencias-report.json): statistics, metadata, hashes and reconciliation.
- [coletas.csv](coletas.csv): comparative summary of both collections.
- `fontes/`: preserved CSVs and metadata, representative report and copies of the three examined tables.
- [analyze.py](analyze.py): reproducible calculations in the source repository without executing models.
- [verificar_pacote.py](verificar_pacote.py): verifies copies and calculations after package extraction without depending on the original repository.

**Instruction for the dissertation project:** “Apply reviewer item 7(a) using this report. Replace the approximate row in Table `tab:tempos-inferencia-aceleracao`, explicitly identify TFLM + ESP-NN in Table `tab:acuracia-configuracoes`, and associate both rows with collection `20261009T120557541292Z`. Update the note stating that minimum and maximum timings are unavailable. Do not change figures or sources for other configurations or recompute fidelity from this collection without a separate analysis.”

The document examined was `C:/Users/rafae/Downloads/latex-mestrado-2/Dissertacao_Rafael_Braga_UNICO.tex`. Its audit-time hash is stored in the evidence JSON. Figures in this report were derived from preserved files, not estimated from “≈ 1.7 s.”
