# TFLite → WAT/WASM with model packages

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

## From model to device

Explore a quantized neural network from its TFLite representation to WebAssembly execution, inspect its results and study embedded inference on ESP32. This repository brings together a Python pipeline, two model packages, an independent ESP32 host and a local website for browsing documentation and measurements.

[![Research Explorer: project overview, reports and documentation](docs/assets/research-explorer.png)](web/README.md)

*Research Explorer brings the projects together in one local library. The counts shown are a snapshot of the repository.*

## What each project offers

| Project | What you can do | Start here |
|---|---|---|
| Python · TFLite → WAT/WASM | Extract supported graphs, weights and quantization; inspect memory allocation; generate and compile WAT; run RAW images with Wasmtime and produce reports. | [Complete workflow](docs/12-complete-workflow.md) |
| Drowsiness | Study binary classification with RGB565 input, inspect predictions and compare them with known labels. | [Model package](models/drowsiness/README.md) |
| MobileNetV2 Alpha 0.35 | Explore ImageNet classification with BGR888 input and inspect the Top-15 classes for the included example. | [Model package](models/mobilenetv2_alpha035/README.md) |
| ESP32 host | Run a compatible WASM/AOT module, download input images from Cloudinary and collect predictions, inference/download times and memory measurements in a CSV report. | [Host guide](ESP32/cnn_webassembly_esp32/README.md) · [AOT with WSL](ESP32/cnn_webassembly_esp32/README_AOT_WSL.md) |
| Research Explorer | Browse projects, read Portuguese/English Markdown, search and sort report tables, inspect timing/memory charts and download original files. | [Website guide](web/README.md) |

The ESP32 host is configured and compiled independently of the Python pipeline. The website reads existing files; it does not run inference or fetch reports from the device. Supported operators and the host/module contract determine which models can run.

## About the pipeline

This project extracts supported quantized TFLite networks, organizes their graphs, weights, quantization and memory, fills a WAT template, and compiles a WASM module. It then runs RAW images with Wasmtime and writes results for each model. It is intended for studying translation into a custom WebAssembly runtime, including slot reuse and the binary contract between Python and the kernels.

Two packages are included: **drowsiness** (binary classification with RGB565 RAW input) and **mobilenetv2_alpha035** (ImageNet Top-15 classification with BGR888 RAW input). Each has its own manifest, TFLite file, tests and output directories. This is not a universal TFLite converter.

Start with the [technical index](docs/README.md). Earlier documentation is preserved in `docs/historico/`. The [ESP32 host](ESP32/cnn_webassembly_esp32/README.md) is independent of the Python pipeline; see its [AOT guide](ESP32/cnn_webassembly_esp32/README_AOT_WSL.md) and [configuration reference](ESP32/cnn_webassembly_esp32/HOST.md).

## Browse documentation and reports

Run `python web/server/app.py` from the repository root and open **http://127.0.0.1:8000**. The local [Research Explorer](web/README.md) organizes Markdown and reports by project, with charts, searchable tables and language navigation. Python 3.10+ is sufficient; inference dependencies are not required.

## Installation

Requires a working Python 3.10+ installation. From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On POSIX shells, activate with `source .venv/bin/activate`. The `setup_env.ps1` script also creates/activates `.venv` and installs dependencies, but cannot repair an environment whose base interpreter has been removed. Original local checks used `.venv-models/Scripts/python.exe`; the older `.venv` had a missing base interpreter. Virtual environments do not replace installing Python on another computer.

| Dependency | Declared version | Purpose |
|---|---|---|
| flatbuffers | 25.12.19 | FlatBuffer access |
| numpy | 2.2.6 | Arrays, bytes, quantization and ranking |
| tflite | 2.18.0 | Schema bindings, not a TensorFlow interpreter |
| wasmtime | >=49,<50 | WAT compilation and WASM execution |
| tomli | >=2,<3, Python<3.11 only | TOML parsing; Python 3.11+ uses tomllib |

The WABT `wat2wasm` executable is not required: compilation uses the Python API `wasmtime.wat2wasm`.

## Commands

```powershell
python main.py --list-models
python main.py
python main.py --model drowsiness
python main.py --model mobilenetv2_alpha035
python -m unittest discover -s tests -v
```

The default model is drowsiness. Listing displays directory names and manifest descriptions. There is no compile-only mode or case filter: execution discovers tests, extracts, generates, compiles and runs inference. Supply a directory name under `models/`, not a TFLite path.

## Architecture

```text
python main.py --model X
        │
        ▼
ModelPackage / ModelConfig ← models/X/model.toml
        │
        ├── original TFLite
        ├── WAT template
        └── test configuration → registry → adapter
        │
        ▼
ModelPipeline: validate sources and discover cases
        │
        ▼
extractor
  graph → slots → tensor/slot mapping
  weights → quantization → memory layout
  LayerParams → params_blob
        │
        ▼
wat_generator + template
        │
        ▼
models/X/generated/model.wat
        │
        ▼
wasmtime.wat2wasm → models/X/generated/model.wasm
        │
        ▼
inference/wasm_inference.py + adapter
  prepare_input → memory.write → run → memory.read
        │
        ▼
evaluate_output → build_report + errors
        │
        ▼
models/X/reports/12-inferencia-wasm.txt
```

The inputs are the package name, sources and tests. The pipeline converts TFLite data into runtime structures and coordinates extraction and testing. Outputs are WAT, WASM and reports. Paths, classes, formats and weights are model-specific; serialization, allocation and the execution protocol are shared. Reports 02–11 are written during extraction, before inference.

## Repository tree

```text
master-degree-project/
├── main.py                         CLI
├── requirements.txt                Python dependencies
├── setup_env.ps1                    .venv creation/activation
├── README.md
├── README.pt-BR.md
├── .gitignore
├── adapters/                       base, binary_folders, imagenet_topk, registry
├── extractor/                      15 Python files, including __init__.py
├── inference/wasm_inference.py      Wasmtime host
├── pipeline/                       config, package, pipeline, compiler
├── models/
│   ├── drowsiness/
│   │   ├── model.toml
│   │   ├── model_int8_esp32.tflite
│   │   ├── test/{drowsy,non_drowsy}/
│   │   ├── generated/{model.wat,model.wasm}
│   │   └── reports/                11 reports
│   └── mobilenetv2_alpha035/
│       ├── model.toml
│       ├── mobilenetv2_alpha035_quant.tflite
│       ├── labels/imagenet_class_index.json
│       ├── test/img/aviao_uint8.raw
│       ├── wat/model_template.wat
│       ├── generated/{model.wat,model.wasm}
│       └── reports/                11 reports
├── ESP32/cnn_webassembly_esp32/     independent firmware
├── img_mobilenetv2/aviao_uint8.raw   copy outside the package
├── wat/templates/
│   ├── mobilenet_int8_v1.wat        used by drowsiness
│   └── model_template.wat          legacy, unused by manifests
├── tests/test_model_packages.py
├── docs/                           current and historical documentation
├── .venv/                          older local environment
├── .venv-models/                    used for the original checks
└── __pycache__/                    local cache, also present in modules
```

The tree groups repetitive files; the [inventory](docs/14-inventory-and-traceability.md) lists modules and datasets. Each package provides sources and receives artifacts in its output directories. The current manifest does not read `img_mobilenetv2/`. Git metadata, caches and environments are infrastructure, not part of the generated runtime.

## Concepts

**TFLite** is the source FlatBuffer of operators and tensors. **WAT** is WebAssembly text generated from a template and extracted data. **WASM** is its compiled binary. The network runs template kernels, not an embedded TFLite interpreter.

**ModelPackage** groups root/config and resolves sources and destinations. **model.toml** declares name, TFLite, contract/template/slots, input format/synthetic layer and test adapter. Current manifests use package-relative paths; the resolver also supports absolute paths. See the [field reference](docs/03-model-config-manifest.md).

**Adapters** implement TestAdapter to prepare inputs and interpret outputs. `binary-folders` maps folders to labels and calculates accuracy. `imagenet-topk` swaps BGR→RGB, dequantizes, and reports classes/wnid/scores. The registry selects an adapter through `test.adapter`.

**synthetic_layer** is an extractor-inserted operation absent from the original graph. `rgb565_to_rgb888` inserts a SLOT0→SLOT1 kernel with slot shift 1. `none` inserts no kernel and uses shift 0; input preparation belongs to the adapter. See the [two variants](docs/09-models-and-packages.md).

**layerparam-v1** names the ABI: each layer contains 29 little-endian int32 fields, totaling 116 bytes, read at fixed WAT offsets. Templates must match operation codes, flags, fields and exports. Changing a template path alone does not guarantee compatibility. See the [complete table](docs/08-layerparam-v1-contract.md).

## Sources, outputs and reports

The pipeline writes `models/<name>/generated/model.wat`, `model.wasm` and reports 02–12 under `models/<name>/reports/`. Code, manifests, original TFLite, templates, labels and RAW files are sources. Generated modules and reports are artifacts. A full run regenerates them but does not delete extra files, retain history or write atomically. Failures can leave files from different runs together.

Active templates are `wat/templates/mobilenet_int8_v1.wat` for drowsiness and `models/mobilenetv2_alpha035/wat/model_template.wat` for ImageNet. The legacy `wat/templates/model_template.wat` is unused by manifests and has older QUANTIZE behavior.

| Package | Host input | Output | Existing report observations |
|---|---|---|---|
| [drowsiness](models/drowsiness/README.md) | 128×128 RGB565, 32768 bytes | 2 UINT8 classes | 1965/2000 correct; 98.25%; 5 invalid; 0 errors |
| [mobilenetv2_alpha035](models/mobilenetv2_alpha035/README.md) | 224×224 BGR888, 150528 bytes | 1000 classes, Top-15 | One RAW; first: airliner, q=226, score=0.8828125 |

These observations do not establish complete TFLite equivalence or performance on new data. Scores are dequantized values, not calibrated probabilities.

## Add a third model

1. Create `models/<name>/` with TFLite and `model.toml`.
2. Check shapes/dtypes/opcodes and choose a layerparam-v1-compatible template.
3. Configure input format and synthetic layer; choose an adapter and supply nonempty RAW files.
4. Configure class order or labels by index.
5. Run `python main.py --model <name>` and inspect reports/intermediates.

The [tutorial](docs/10-how-to-add-a-model.md) includes a TFLite inspection command, package tree and cases where registration is insufficient. New adapters require implementing and registering a class. New operators also require appropriate extractor, kernel and ABI support.

## Current limitations

The Python flow accepts one 8-bit input/output, NHWC input with batch 1 and three channels, and exactly three slots. Kernels cover CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, ADD, MEAN, SOFTMAX, QUANTIZE and synthetic RGB565. Depthwise assumes multiplier 1; MEAN is spatial; ADD lacks broadcasting; some fused activations are not applied. WAT softmax uses a fixed multiplier despite Python extracting model-specific parameters. The builder may skip unknown operators, so compilation success does not prove complete graph coverage.

Seven targeted tests include a real WASM QUANTIZE kernel; there is no full automated comparison against a TFLite interpreter. Training, compressed-image preprocessing, multiple outputs, per-inference timeout and hardware execution integration are outside the Python flow. Read the [limitations](docs/99-inconsistencies-and-limitations.md) before extending it.

## Documentation languages

English pages use `.md`; Brazilian Portuguese counterparts use `.pt-BR.md`. Update both versions whenever documentation changes. Keep commands, identifiers, file names and executable examples consistent. Preserve the historical status of archived documents.

See the [documentation contribution guidelines](CONTRIBUTING.md).

