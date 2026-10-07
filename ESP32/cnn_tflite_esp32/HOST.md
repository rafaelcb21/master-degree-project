# TFLite host settings and measurements

[English](HOST.md) | [Português (Brasil)](HOST.pt-BR.md)

[Build and run](README.md)

## Editable files

| File | Purpose |
|---|---|
| `main/host_config.h` | Wi-Fi, HTTP, RAW layout, labels, PSRAM arena and task settings |
| `main/image_list.h` | Cloudinary RAW URLs and labels, in execution order |
| `main/CMakeLists.txt` / `TFLITE_MODEL_FILE` | Embedded original model |
| `sdkconfig` / `sdkconfig.defaults` | Board, PSRAM, flash, CPU and TLS settings |

Default class order is `{1, 0}`: output 0 means label 1 and output 1 means label 0. This must agree with the model and the image list. `CLASS_LABELS_ARE_INDICES=1` uses output indices directly. A tied maximum gives `result=-1`; unknown reference labels give `right=-1`. Ties remain successful inference rows (`ok=1`) and count as incorrect when labeled. This is the ESP32 WASM host's rule; the Python binary adapter additionally rejects nonpositive summed scores.

## CSV fields

| Fields | Meaning |
|---|---|
| `name_image` | URL basename, matching the copied WASM image list |
| `ok` | 1 only after successful download, preparation, Invoke and output reading |
| `class_N_raw` | Raw output tensor element, in model order; failed rows are blank |
| `result`, `label`, `right` | Predicted mapped label, reference label, correctness (1/0 or -1 when unavailable) |
| `download_ms` | HTTP client request duration |
| `preprocess_ms` | RAW decoding/channel ordering/normalization and tensor writes |
| `invoke_ms` | TFLite Micro Invoke duration |
| `inference_ms` | `preprocess_ms + invoke_ms`; excludes network, hashing and reading output |
| `heap_before`, `heap_after`, `heap_used` | Free heap across capabilities before/after preparation + Invoke; positive decrease, clipped at zero |
| `psram_before`, `psram_after`, `psram_used` | The same measurements restricted to PSRAM |
| `stack_min_free_bytes` | Lifetime minimum free task stack, not per-image stack allocation |
| `arena_reserved_bytes`, `arena_used_bytes` | Configured allocation and TFLite Micro's used arena size |
| `input_sha256` | Hash of the downloaded RAW bytes, before preprocessing |

The interpreter and arena are created before collecting per-image deltas, so `heap_used=0` does **not** mean the model uses no memory. Do not add heap and PSRAM figures: the total heap may already include PSRAM. CSV storage grows after each sample and affects subsequent free-memory values.

The report is immutable once served. If report allocation fails, `/report` returns an error instead of presenting a partial report as complete. Rows for failed images have `ok=0`; summaries appear in the serial log and `/metadata`, not as fake CSV data rows. HTTP endpoints start after the benchmark and remain available while the board is powered.

## Metadata and reproducibility

`/metadata` includes model and image-list SHA-256, runtime/component version, IDF version, output dtype/scale/zero point, CPU frequency, arena sizes and summary counts. Dequantize output as `(raw - output_zero_point) * output_scale`; float output is already real-valued. Keep `dependencies.lock`, `host_config.h` and `sdkconfig` with a reproducible experiment. Espressif's component enables ESP-NN kernels; these are different implementations from the desktop TFLite and custom WASM kernels.

Use identical model hashes and downloaded bytes to compare predictions. The old WASM CSV lacks input hashes; validate the Cloudinary sources separately. Keep download and inference times separate, match CPU/PSRAM settings, and record that there is no warm-up. The default 1 MiB arena is a starting allocation; only execution on the board establishes whether this model fits and runs correctly.
