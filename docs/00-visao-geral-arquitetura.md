[English](00-visao-geral-arquitetura.md) | [Português (Brasil)](00-visao-geral-arquitetura.pt-BR.md)

# 00 — Overview and architecture

[Index](README.md) · [Complete flow](12-fluxo-completo.md) · [Limitations](99-inconsistencias-e-limitacoes.md)

## Scope and evidence

This documentation describes the local files inspected on September 28, 2026. Python modules, manifests, templates and reports were read; shapes, types and quantization were extracted from both TFLite FlatBuffers. Published results are observations from existing reports, not guarantees of equivalence with a TFLite interpreter. The documentation task does not change kernels, models, manifests or tests.

The project turns **supported TFLite models** into specialized WebAssembly modules. Python extracts network descriptions/parameters, a WAT template supplies kernels, and Wasmtime converts text into WASM and runs RAW tests. Training, PNG/JPEG conversion, ESP32 execution and a web server are not part of this Python flow. The separate ESP32 project has its own host and documentation.

TFLite is the source FlatBuffer containing tensors, operators and buffers. WAT is WebAssembly text with code/data segments. WASM is its compiled binary. The resulting module contains the template runtime and extracted package data, not a TFLite interpreter.

## System view

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

Inputs are a package name, sources and tests. ModelPipeline converts TFLite data into runtime structures and coordinates both branches. Outputs are WAT, WASM and reports. Paths, classes, format and weights vary by model; serialization, allocation and execution protocol are shared. Reports 02–11 are written during extraction, before inference; placing reports last in the diagram does not imply one final write.

## Repository layout

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

The tree groups repetitive files; the [inventory](14-inventario-e-rastreabilidade.md) lists modules and datasets. Each models/ directory supplies configuration/sources and receives files in generated/ and reports/. The current manifest does not read img_mobilenetv2/. Git metadata, caches and environments are local infrastructure, not part of the generated runtime.

## Responsibilities and boundaries

| Layer | Decides | Does not decide |
|---|---|---|
| CLI | Package selection/listing | Network architecture |
| ModelPackage | Source/output path resolution | Binary layout |
| ModelConfig | TOML loading and explicit validation | Full numerical compatibility |
| ModelPipeline | Stage order and persistence | ImageNet classes or binary labels |
| extractor | Graph, blobs, operator parameters | Adapter selection |
| wat_generator | Placeholders/data segments | Kernel mathematics |
| wasm_compiler | Text-to-binary conversion | Inference/metrics |
| inference | Instance, memory, calls, error collection | Ranking/accuracy |
| adapters | Discovery, preparation, interpretation | WAT compilation |

ModelPipeline is fixed sequential orchestration, resembling a pipeline/Template Method, but it has no base class with subclass hooks. TestAdapter uses Strategy/Adapter through composition. ADAPTERS and create_adapter form an explicit Registry/Simple Factory. There is no automatic plugin discovery.

## Sources and artifacts

Sources: Python, model.toml, TFLite, templates, labels and RAWs. Artifacts: generated/model.wat, generated/model.wasm, reports/02-... through 12-.... They can be regenerated when sources, dependencies and tests are valid. The pipeline does not remove extra files, version outputs or write atomically. A failed run may leave mixed results. Normal execution does not modify the TFLite.

## Suggested reading order

Start with CLI, package and manifest (01–03), then orchestration (04) and testing interfaces (05–07). Read the ABI (08) before editing templates; consult models, tutorial, tests and complete flow (09–12). Chapters 20–33 cover individual extractor modules. Chapter 99 distinguishes current limitations from proposed improvements.

