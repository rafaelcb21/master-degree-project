# 15 — Execute the original TFLite models

[English](15-tflite-baseline.md) | [Português (Brasil)](15-referencia-tflite.pt-BR.md)

`run_tflite.py` executes the original `.tflite` files and writes separate reports for later comparison with WASM. It uses the same model manifests, test images, class order and evaluation adapters. It does not regenerate WASM or overwrite `models/<model>/reports/`.

## Install and run

Use a separate Python 3.11 environment. From the repository root in PowerShell:

```powershell
python -m venv .venv-tflite
.\.venv-tflite\Scripts\python.exe -m pip install -r requirements-tflite.txt
.\.venv-tflite\Scripts\python.exe run_tflite.py
```

The default runs both registered packages. To select one:

```powershell
.\.venv-tflite\Scripts\python.exe run_tflite.py --model drowsiness
.\.venv-tflite\Scripts\python.exe run_tflite.py --model mobilenetv2_alpha035
```

The runner uses TensorFlow 2.20.0's `tf.lite.Interpreter`, one CPU thread by default, and built-in kernels without default delegates. `--threads N` changes the thread count. The interpreter allocates tensors, receives the input, executes `invoke()` and returns the output. See the [official interpreter API](https://www.tensorflow.org/api_docs/python/tf/lite/Interpreter). TensorFlow may print a deprecation warning for this API; the dependency is pinned to the version used here.

## Matching inputs

| Package | Input preparation |
|---|---|
| Drowsiness | Read little-endian RGB565 and expand to RGB888 with the same bit replication as the WAT converter. Pass uint8 RGB to the original TFLite input; its own QUANTIZE operator remains part of the model. |
| MobileNetV2 Alpha 0.35 | Reuse the WASM adapter's BGR888→RGB888 preparation, including its normalization and quantization if the input tensor is int8. |

No resizing or new image conversion is performed. The runner requires a single NHWC RGB input with batch size 1 and quantized uint8/int8 input/output tensors. It rejects unsupported shapes, types and quantization instead of guessing preprocessing.

## Output files

Each execution creates a UTC timestamp directory:

```text
models/<model>/reports_tflite/<UTC timestamp>/
  inference-report.txt
  samples-report.csv
  results-report.json
```

- **TXT:** the same readable binary classification or Top-K structure as the WASM report, labeled TFLite.
- **CSV:** one row per image, success/failure, prediction, label/correctness when available, inference time, quantized outputs and scores. Failed samples have `ok=0` and an error description. ImageNet has no ground-truth labels, so accuracy fields remain empty.
- **JSON:** complete output vectors, Top-K where applicable, per-image records and errors, model/manifest hashes, RAW and prepared-input hashes, tensor shapes and quantization, runtime versions, timestamps and summary metrics.

Paths in these reports are relative to the model package, such as `test/drowsy/A0001.raw`. Old runs remain available. When sample processing fails, reports are still written and the CLI returns a nonzero exit code. Initialization/configuration failures stop execution before report generation.

In Research Explorer, click **Refresh index** and filter by model. Files appear under `reports_tflite/`; TXT and CSV use the existing report views, while JSON is shown as source text.

## Later comparison with WASM

Use `models/<model>/reports/12-inferencia-wasm.txt` as the existing WASM result and the new TFLite report as the reference. Match images by path relative to the model package, not by row number or the machine-specific prefix in older WASM reports. Compare quantized outputs, dequantized scores, predicted classes, ties and errors. The ImageNet JSON retains all 1,000 outputs, while its text report shows Top-15.

The same preprocessing does not guarantee identical outputs: kernel implementations and integer rounding can differ. Existing WASM reports do not record model/input hashes, so their provenance must be checked before a formal numerical comparison; this command does not validate or rerun those earlier reports.

Times measure only `interpreter.invoke()`, excluding file reading, preprocessing and tensor copying. There is no warm-up run, and the first invocation is included. These CPU times should not be treated as directly equivalent to ESP32 measurements or differently timed WASM runs. Binary accuracy includes successfully processed labeled samples; ties count as incorrect, and processing errors are reported separately.
