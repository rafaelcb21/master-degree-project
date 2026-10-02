# MobileNetV2 Alpha 0.35 ImageNet

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

[Main documentation](../../README.md) · [Package comparison](../../docs/09-modelos-e-pacotes.md)

## Purpose

The manifest identifies this package as MobileNetV2 Alpha 0.35 for ImageNet classification. The TFLite exposes 1,000 outputs associated with the class JSON.
The current test uses one airplane RAW image and produces Top-15 without calculating ground-truth accuracy. Alpha width 0.35 comes from the model/file name; this workflow has no training recipe from which its full provenance can be reconstructed.

## Files

```text
models/mobilenetv2_alpha035/
├── README.md
├── model.toml
│   ├── mobilenetv2_alpha035_quant.tflite
│   ├── wat/model_template.wat
│   ├── input: bgr888 + none
│   └── test: imagenet-topk / top_k=15
├── mobilenetv2_alpha035_quant.tflite
├── labels/imagenet_class_index.json
├── test/img/aviao_uint8.raw
├── wat/model_template.wat
├── generated/
│   ├── model.wat
│   └── model.wasm
└── reports/          11 files, listed below
```

The package's local sources are inputs; the pipeline writes generated and reports.
The manifest selects the local template, whose contents match the active shared template in the current revision.
Labels and image belong to the package; ABI and generation are shared.
Another RAW copy exists in root-level `img_mobilenetv2/`, unused by the manifest.

## Running

From the root:

```powershell
python main.py --model mobilenetv2_alpha035
```

top_k is configured in TOML, not through a CLI argument.
Discovery finds exactly **one file**, `test/img/aviao_uint8.raw`, containing **150,528 bytes**.
No expected label is assigned to the folder or case.

## Input format and no synthetic layer

224×224 RAW, three UINT8 channels, 3 bytes per pixel, **B,G,R** order, no header: 224×224×3=150528 bytes.
The adapter does not decode compressed images or resize.
The RAW filename's `uint8` describes its bytes; `input.format=bgr888` determines the assumed channel order.
The file alone does not carry metadata that can confirm that order.

```text
RAW BGR888
    │
    ▼
ImageNetTopKAdapter.prepare_input
    │ reshape(-1,3)[:,::-1].copy()
    ▼
RGB888 UINT8
    │ memory.write
    ▼
  SLOT0
    ▼
first REAL operation: QUANTIZE
    ▼
rest of TFLite translated into WAT
```

BGR bytes enter; the adapter swaps B/R and sends RGB to SLOT0.
The manifest uses `synthetic_layer="none"`, count=0, and shift=0: no extra operation is inserted.
Preparation is test-specific; execution uses the common runtime.
Because this TFLite input is UINT8, the adapter's INT8 normalization branch is not executed.

## Adapter and labels

`discover_cases()` reads JSON, validates that each value is `[wnid,class_name]`, validates top_k, and lists RAW files.
The JSON contains 1,000 class indices; for example, `"404": ["n02690373", "airliner"]`.
`prepare_input()` checks length and swaps B/R.
`evaluate_output()` reads output as UINT8, dequantizes, requires coverage of every index, and sorts scores.
`build_report()` displays class, wnid, q, and score on separate lines.

Previous documentation records obtaining labels from `https://storage.googleapis.com/download.tensorflow.org/data/imagenet_class_index.json`.
Inference does not download them automatically.
The JSON is a local source; the code does not semantically validate its correspondence with model training.

## Output and Top-15

Output is `[1,1000]` UINT8, scale=1/256, zero point=0.
Each score is q/256.
Python does not apply softmax: the adapter only decodes and sorts values produced by the runtime.

```text
1000 output bytes
        │ dtype UINT8
        ▼
1000 quantized values q
        │ score=(q-zp)×scale
        ▼
1000 real-valued scores
        │ argsort(-scores, stable)
        ▼
descending order; ties preserve indices
        │ [:top_k], currently 15
        ▼
┌───────────────────────────┐
│ Top-1                     │
│ Top-2                     │
│ ...                       │
│ Top-15                    │
└───────────────────────────┘
```

The full output and labels are inputs.
The Strategy selects the K largest scores and produces a report without ground truth.
N and class names are specific; sorting/dequantization are shared.
K greater than N returns N items.
A score is not called a calibrated probability: the current softmax kernel uses specific constants and approximations described in the limitations.

## Observed result

```text
1. [404] airliner
   wnid=n02690373
   q=226
   score=0.88281250
```

The existing report also lists space_shuttle and wing with q=11/score=0.04296875 in subsequent positions.
The recorded run processed one case without errors.
This single-image test does not measure ImageNet accuracy or prove numerical equivalence with TFLite.

## Input and output measured in TFLite

The values below were read from subgraph 0 with the project's bindings; they were not inferred from the filename.

| Property | Input | Output |
|---|---|---|
| Shape | `[1, 224, 224, 3]` | `[1, 1000]` |
| Elements | `150528` | `1000` |
| Dtype | `uint8` | `uint8` |
| Scale | `0.007843137718737125` | `0.00390625` |
| Zero point | `127` | `0` |

The pipeline interprets input as NHWC: batch 1, height and width at positions 1 and 2, and three channels at position 3.
The FlatBuffer stores shape and type; RGB/BGR interpretation comes from the manifest and kernels.
Both models expose UINT8, even with internal INT8 operations.

## Selected manifest

```toml
[model]
name = "MobileNetV2 Alpha 0.35 ImageNet"
tflite = "mobilenetv2_alpha035_quant.tflite"
[runtime]
contract = "layerparam-v1"
wat_template = "wat/model_template.wat"
num_slots = 3
[input]
format = "bgr888"
synthetic_layer = "none"
[test]
adapter = "imagenet-topk"
path = "test/img"
top_k = 15
labels = "labels/imagenet_class_index.json"
```

Paths are resolved from this folder. The meaning and validation of each field are in the [TOML reference](../../docs/03-model-config-manifesto.md).

## Architecture found in the FlatBuffer

The file contains 1,925,904 bytes, 1 subgraph, and 175 tensors. There are 67 operators:

| Operator | Count |
|---|---:|
| QUANTIZE | 2 |
| CONV_2D | 35 |
| DEPTHWISE_CONV_2D | 17 |
| ADD | 10 |
| MEAN | 1 |
| FULLY_CONNECTED | 1 |
| SOFTMAX | 1 |

The first operator is QUANTIZE. The final sequence is FULLY_CONNECTED → SOFTMAX → QUANTIZE. The runtime uses the project's own WAT kernels described in [chapter 13](../../docs/13-runtime-wat.md); it does not run a TFLite interpreter.

## Generation and execution

```text
mobilenetv2_alpha035_quant.tflite
             │
             ▼
ModelPipeline: graph / slots / parameters / memory
             │ + manifest template
             ▼
generated/model.wat
             │ wasmtime.wat2wasm
             ▼
generated/model.wasm
             │ Wasmtime host + adapter
             ▼
reports/12-inferencia-wasm.txt
```

The original TFLite and this package's configuration are inputs; the pipeline materializes data and code, compiles, and tests. It produces two artifacts and eleven reports. The model, selected template, and RAW files are specific sources; extraction, ABI, and compilation are shared. A failure may leave partial or old artifacts because there is no transaction. The TFLite is not rewritten.

## Recorded memory layout

```text
REGION              BASE       BYTES         END
------------------------------------------------
WEIGHTS             2048     1662048     1664096
BIAS             1664096       32160     1696256
MUL              1696256       32164     1728420
SHIFT            1728432       32164     1760596
Q6               1760608       32160     1792768
PARAMS           1792768        7776     1800544
SLOT0            1800544      602112     2402656
SLOT1            2402656      602112     3004768
SLOT2            3004768      602112     3606880
```

Blob lengths and the largest tensor are inputs. The extractor calculates aligned bases and produces the physical regions used by WAT. These numbers belong to the package; 65,536-byte pages, three slots, and 116-byte records are shared conventions. END is exclusive, not the last occupied byte.

## Generated reports

| File | Contents |
|---|---|
| [02-grafo.txt](reports/02-grafo.txt) | Operator types, labels, and dependencies. |
| [03-alocacao-slots.txt](reports/03-alocacao-slots.txt) | Logical slots and in-place operations. |
| [04-mapeamento-tensor-slot.txt](reports/04-mapeamento-tensor-slot.txt) | Tensor IDs associated with slots and unresolved mappings. |
| [05-pesos-bias.txt](reports/05-pesos-bias.txt) | Weight/bias shapes, offsets, and bytes. |
| [06-quantizacao.txt](reports/06-quantizacao.txt) | Scales, multipliers, shifts, and Q6 limits. |
| [07-slot-bytes.txt](reports/07-slot-bytes.txt) | Largest nonconstant tensor and capacity of each slot. |
| [08-layout-parametros.txt](reports/08-layout-parametros.txt) | WEIGHTS, BIAS, MUL, SHIFT, Q6, and PARAMS bases. |
| [09-layer-params.txt](reports/09-layer-params.txt) | Per-layer fields, runtime map, and special parameters. |
| [10-params-blob.txt](reports/10-params-blob.txt) | Serialized records, absolute pointers, and padding. |
| [11-layout-final-memoria.txt](reports/11-layout-final-memoria.txt) | Physical regions, end, pages, and remaining space. |
| [12-inferencia-wasm.txt](reports/12-inferencia-wasm.txt) | Per-image results and processing errors. |

Existing reports are a snapshot of runs preceding the documentation task.
With valid sources/dependencies, a full run recreates and overwrites them; extra files are not cleaned up. Report 09 describes Python values, 10 the serialized fields, and 12 the adapter's interpretation. A reported field is not always consumed by the kernel, particularly in the current softmax.

## Limitations and provenance

The network's purpose is indicated by its name/configuration and confirmed by the output shape; the repository does not provide the complete training history, RAW origin/license, or original conversion script. The current test does not prove full TFLite equivalence. See the [verified limitations](../../docs/99-inconsistencias-e-limitacoes.md), especially fixed softmax, specialized kernels, and test coverage.

