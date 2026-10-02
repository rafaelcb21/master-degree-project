# Technical documentation — index

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

[Main README](../README.md)

This reference describes the implementation and TFLite files present in the repository. Chapters 00–14 cover use and architecture; 20–33 document individual extractor modules. Earlier material is preserved in historico/ with scope notices. Proposed improvements are distinguished from implemented behavior.

## Architecture, interfaces and operation

- [00 — Overview and architecture](00-architecture-overview.md)
- [01 — CLI: main.py](01-cli-main.md)
- [02 — ModelPackage and path resolution](02-model-package.md)
- [03 — ModelConfig and model.toml reference](03-model-config-manifest.md)
- [04 — ModelPipeline: detailed orchestration](04-model-pipeline.md)
- [05 — Test adapters and registry](05-adapters.md)
- [06 — Wasmtime inference host](06-wasm-inference.md)
- [07 — WAT → WASM compilation](07-wat-wasm-compilation.md)
- [08 — The layerparam-v1 binary contract](08-layerparam-v1-contract.md)
- [09 — Included models and packages](09-models-and-packages.md)
- [10 — Tutorial: register a third model](10-how-to-add-a-model.md)
- [11 — Tests and validation scope](11-tests.md)
- [12 — Complete flow and reading reports](12-complete-workflow.md)
- [13 — Templates and WebAssembly runtime](13-runtime-wat.md)
- [14 — Inventory and traceability](14-inventory-and-traceability.md)
- [20 — Shared extractor constants](20-extractor-config.md)
- [21 — Loading the TFLite FlatBuffer](21-extractor-model-loader.md)
- [22 — TFLite tensor and quantization utilities](22-extractor-tflite-utils.md)
- [23 — Operator graph and ordering](23-extractor-graph.md)
- [24 — Slot allocation and lifetimes](24-extractor-slots.md)
- [25 — Tensor-to-slot mapping](25-extractor-tensor-mapping.md)
- [26 — Weight and bias extraction](26-extractor-weights.md)
- [27 — Integer quantization and per-channel blobs](27-extractor-quantization.md)
- [28 — Physical memory planning](28-extractor-memory.md)
- [29 — Operator options and geometry](29-extractor-operator-options.md)
- [30 — Building LayerParams and the synthetic layer](30-extractor-layer-params.md)
- [31 — Serialization and pointer resolution](31-extractor-params-blob.md)
- [32 — WAT generation and data segments](32-extractor-wat-generator.md)
- [33 — Writing reports](33-extractor-reporting.md)

## Model packages and ESP32

- [Drowsiness MobileNetV2](../models/drowsiness/README.md)
- [MobileNetV2 Alpha 0.35 ImageNet](../models/mobilenetv2_alpha035/README.md)
- [Independent ESP32 host](../ESP32/cnn_webassembly_esp32/README.md)
- [Host settings and measurements](../ESP32/cnn_webassembly_esp32/HOST.md)
- [WASM → AOT using WSL](../ESP32/cnn_webassembly_esp32/README_AOT_WSL.md)

## Audit and history

- [Documentation verification](98-documentation-verification.md)
- [Inconsistencies and limitations](99-inconsistencies-and-limitations.md)
- [Inventory, sources and preserved documents](14-inventory-and-traceability.md)

## Maintaining translations

Each English .md file has a Brazilian Portuguese .pt-BR.md counterpart. Follow the language links at the top of each page. Update both versions when changing instructions, examples or documented behavior. Keep filenames, identifiers and executable commands consistent. Preserve historical warnings and distinguish earlier observations from checks performed today.

See the [contribution guidelines](../CONTRIBUTING.md).

