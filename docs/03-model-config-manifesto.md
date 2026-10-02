[English](03-model-config-manifesto.md) | [Português (Brasil)](03-model-config-manifesto.pt-BR.md)

# 03 — ModelConfig and model.toml reference

[Index](README.md) · Source: [pipeline/model_config.py](../pipeline/model_config.py)

## Loading and representation

ModelConfig.load(path) opens TOML in binary mode and uses tomllib on Python 3.11+, falling back to tomli. It reads model, runtime, input and test tables and creates a frozen dataclass. Flat fields are name, tflite, wat_template, contract, num_slots, input_format, synthetic_layer, test and classes. test/classes remain mutable collections rather than specialized objects.

```text
model.toml → tomllib.load / tomli.load → table dictionary
           → required fields + defaults
           → contract == layerparam-v1?
           → num_slots == 3?
           → allowed format/layer pair?
           → ModelConfig → ModelPackage → pipeline + adapter
```

The loader applies three explicit checks and returns the dataclass. Paths, classes and tests are model-specific; allowed values reflect current runtime/adapter constraints.

## Fields, defaults and consumers

These are expected types for correct use. Type hints do not perform runtime validation; the loader does not implement a complete TOML schema.

| TOML field | Expected type | Required/default | Consumer and examples |
|---|---|---|---|
| [model].name | string | Required | CLI listing; "Drowsiness MobileNetV2" |
| [model].tflite | path string | Required | Package validation, model loader; "model_int8_esp32.tflite" |
| [runtime].wat_template | path string | Required | Package validation, generator; "wat/model_template.wat" |
| [runtime].contract | string | Required | Must equal "layerparam-v1" |
| [runtime].num_slots | integer | Optional: 3 | Must equal 3; allocation, mapping, memory |
| [input].format | string | Required | rgb565, bgr888, rgb888 in the combinations below; adapter |
| [input].synthetic_layer | string | Required | rgb565_to_rgb888 or none; pipeline, LayerParams, runner |
| [test].adapter | string | Required | Registry: binary-folders or imagenet-topk |
| [test].datasets | list of tables | Binary adapter requires it; internal default [] is rejected | Each entry has path and label |
| [[test.datasets]].path | path string | Required per dataset | raw_files; "test/drowsy" |
| [[test.datasets]].label | integer expected | Required per dataset | Must belong to class labels; e.g. 1 |
| [test].path | path string | Required for ImageNet | raw_files; "test/img" |
| [test].labels | path string | Required for ImageNet | JSON mapping index → [wnid, class_name] |
| [test].top_k | positive integer | Optional: 15 | Checked during discovery, used for ranking slice |
| [[classes]] | list of tables | Default []; binary adapter requires length 2 | Order matches output elements |
| [[classes]].name | string expected | Used by current manifests | Class list in report; not required to choose a winner |
| [[classes]].label | integer expected | Required by binary adapter | Label returned when that index wins |

Batch, alignment, kernel base, normalization, input address, output paths and execution export names are not configurable fields. BATCH, ALIGN and KERNEL_BASE_HINT come from extractor/config.py.

## Accepted combinations

| format | synthetic_layer | Count/shift | Adapter implementing preparation |
|---|---|---|---|
| rgb565 | rgb565_to_rgb888 | 1 | binary-folders |
| bgr888 | none | 0 | imagenet-topk swaps B/R |
| rgb888 | none | 0 | imagenet-topk preserves channels |

synthetic_layer_count returns int(self.synthetic_layer != "none"); prior validation ensures every non-none value means exactly one layer. The loader checks format/layer pairs, not their compatibility with the adapter. binary-folders with BGR/none passes configuration validation but fails in prepare_input.

## Complete minimal example

See the real [drowsiness](../models/drowsiness/model.toml) and [ImageNet](../models/mobilenetv2_alpha035/model.toml) manifests. The following names are illustrative; the executable example is preserved from the Portuguese document.

```toml
[model]
name = "Experimento binário"
tflite = "model.tflite"
[runtime]
contract = "layerparam-v1"
wat_template = "../../wat/templates/mobilenet_int8_v1.wat"
num_slots = 3
[input]
format = "rgb565"
synthetic_layer = "rgb565_to_rgb888"
[test]
adapter = "binary-folders"
[[test.datasets]]
path = "test/positivo"
label = 1
[[test.datasets]]
path = "test/negativo"
label = 0
[[classes]]
name = "positivo"
label = 1
[[classes]]
name = "negativo"
label = 0
```

This is valid only when TFLite output index 0 means positive and index 1 means negative. The code does not infer class meaning from the model or alphabetical folder order.

## Validation limits

Missing keys and some invalid construction-time types become ValueError("Manifesto incompleto..."). The parser raises TOML syntax errors; the filesystem reports missing files. Unknown keys are ignored. contract currently accepts/rejects the sole known name rather than selecting different implementations.

num_slots=3.0 may pass equality checking but later fail in range. top_k=true is a bool, an int subclass, and passes the adapter's check. These are validation gaps, not recommended formats. Duplicate labels, incomplete dataset sets and label types are not comprehensively audited. Consumers check path existence at later stages.

