# Drowsiness MobileNetV2

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

[Main documentation](../../README.md) · [Package comparison](../../docs/09-models-and-packages.md)

## Purpose

Binary drowsiness classification package. The manifest names the network MobileNetV2 and defines two classes: `drowsy` (label 1) and `non_drowsy` (label 0). The project uses this network to test TFLite extraction, RGB565 conversion, and quantized execution in the WAT runtime. The file is named `model_int8_esp32.tflite`, but the Python workflow here runs Wasmtime on the host, not on ESP32.

## Package files and dependencies

```text
models/drowsiness/
├── README.md
├── model.toml
│   ├── model_int8_esp32.tflite
│   ├── ../../wat/templates/mobilenet_int8_v1.wat
│   ├── input: rgb565 + rgb565_to_rgb888
│   └── test: binary-folders + datasets/classes
├── model_int8_esp32.tflite
├── test/
│   ├── drowsy/       1000 RAWs
│   └── non_drowsy/   1000 RAWs
├── generated/
│   ├── model.wat
│   └── model.wasm
└── reports/          11 files, listed below
```

Inputs are the manifest, TFLite, external template, and RAW files; `ModelPackage` resolves them and the pipeline writes local artifacts.
Test files and classes are specific to this model; the template is shared.
The package depends on this file outside its folder and cannot be distributed alone without including it or adjusting configuration.
There is no labels folder or local template in this package.

## Running

From the repository root:

```powershell
python main.py
python main.py --model drowsiness
```

The commands are equivalent because drowsiness is the default.
In the local environment used for validation, `.venv-models/Scripts/python.exe` can also replace `python`.

## RAW format and synthetic layer

Each image is 128×128, 2 bytes per pixel, **32,768 bytes** total, without a header.
WAT reads little-endian with `i32.load16_u`: bits 15–11 are R, 10–5 are G, and 4–0 are B. The adapter does not swap endianness.
Maximum red is 0xf800, represented by bytes `00 f8`.
The file must already be resized; no module performs resizing.

```text
RAW RGB565 (32768 bytes)
             │ BinaryFoldersAdapter reads unchanged
             ▼
           SLOT0
             │ host writes memory[0]=65
             ▼
┌─────────────────────────────┐
│ synthetic layer             │
│ RGB565_TO_RGB888             │
│ R5/G6/B5 → R8/G8/B8          │
└─────────────┬───────────────┘
              ▼
            SLOT1 (49152 RGB888 bytes)
              ▼
      actual TFLite QUANTIZE
              ▼
        rest of network
```

RGB565 dataset bytes enter the synthetic WAT layer, which expands channels through bit replication. RGB888 UINT8 leaves it for the real graph's first operation.
Format/dimensions belong to the package; OP8 and flags belong to the runtime.
`synthetic_layer_count=1` and `slot_shift=1`: one extra record is reserved and the logical slot map is rotated by 1. The original TFLite has 67 operators; the runtime has 68 records.

## Adapter and test data

`discover_cases()` requires two classes and nonempty datasets, visits `test/drowsy` first (1,000 RAW files, label 1), then `test/non_drowsy` (1,000 RAW files, label 0), with files sorted within each folder.
All discovered RAW files contain 32,768 bytes.
`prepare_input()` only reads RGB565 bytes.
`evaluate_output()` uses two UINT8 values and the TFLite zero point/scale.
`build_report()` lists each case and aggregates correct predictions, invalid cases, and accuracy; the pipeline adds per-case errors.

## Output and binary interpretation

Order is `output[0] → drowsy → label 1`, `output[1] → non_drowsy → label 0`. This is not ascending label order.
`score=q/256` because scale=1/256 and zp=0.
The winning class has the unique largest value; a tie or score sum≤0 is invalid.
An invalid case has result=None and does not count as correct.
Errors that prevent a record from being generated are excluded from the denominator; invalid cases remain.

```text
2 UINT8 bytes
      │
      ▼
values and dequantized scores
      │
      ├── tie/zero sum ──────► invalid, right=False
      └── unique maximum ───► index → classes[index].label
                                       │
                                       ▼
                               compare with folder label
                                       ▼
                              correct / processed cases
```

Inputs are the output vector and folder ground truth.
The adapter calculates validity and correctness, producing a record and aggregate metric.
Labels belong to the package; the binary criterion belongs to the reusable adapter.
The current report records **1965/2000 = 98.25%**, with **5 invalid cases/ties and 0 errors**. This measures performance on that set without implying performance on other datasets.

## Input and output measured in TFLite

The values below were read from subgraph 0 with the project's bindings; they were not inferred from the filename.

| Property | Input | Output |
|---|---|---|
| Shape | `[1, 128, 128, 3]` | `[1, 2]` |
| Elements | `49152` | `2` |
| Dtype | `uint8` | `uint8` |
| Scale | `0.003921508323401213` | `0.00390625` |
| Zero point | `0` | `0` |

The pipeline interprets input as NHWC: batch 1, height and width at positions 1 and 2, and three channels at position 3.
The FlatBuffer stores shape and type; RGB/BGR interpretation comes from the manifest and kernels.
Both models expose UINT8, even with internal INT8 operations.

## Selected manifest

```toml
[model]
name = "Drowsiness MobileNetV2"
tflite = "model_int8_esp32.tflite"
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
path = "test/drowsy"
label = 1
[[test.datasets]]
path = "test/non_drowsy"
label = 0
[[classes]]
name = "drowsy"
label = 1
[[classes]]
name = "non_drowsy"
label = 0
```

Paths are resolved from this folder. The meaning and validation of each field are in the [TOML reference](../../docs/03-model-config-manifest.md).

## Architecture found in the FlatBuffer

The file contains 618,376 bytes, 1 subgraph, and 175 tensors. There are 67 operators:

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
model_int8_esp32.tflite
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
WEIGHTS             2048      384608      386656
BIAS              386656       28168      414824
MUL               414832       28172      443004
SHIFT             443008       28172      471180
Q6                471184       28168      499352
PARAMS            499360        7888      507248
SLOT0             507248      196608      703856
SLOT1             703856      196608      900464
SLOT2             900464      196608     1097072
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

The network's purpose is indicated by its name/configuration and confirmed by the output shape; the repository does not provide the complete training history, RAW origin/license, or original conversion script. The current test does not prove full TFLite equivalence. See the [verified limitations](../../docs/99-inconsistencies-and-limitations.md), especially fixed softmax, specialized kernels, and test coverage.

