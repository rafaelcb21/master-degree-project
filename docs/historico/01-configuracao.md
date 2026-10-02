[English](01-configuracao.md) | [Português (Brasil)](01-configuracao.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body is retained in translation.

# 01 — Pipeline configuration (`config.py`)

## 1. Module purpose

The `extractor/config.py` file centralizes the global parameters used to extract the TFLite model and generate the WebAssembly Text (`.wat`) file.

Its purpose is to prevent paths, alignments, slot counts, and other structural parameters from being repeated or defined directly in several project modules.

The current file is:

```python
from pathlib import Path


MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)

WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)

OUT_WAT_PATH = Path(
    "generated/model.wat"
)

REPORTS_DIR = Path(
    "reports"
)

NUM_SLOTS = 3

BATCH = 1

ALIGN = 16

KERNEL_BASE_HINT = 2048
```

The module does not perform extraction or modify files. It only makes configuration values available to the other components.

---

# 2. Overview

The flow of configuration values can be represented as follows:

```text
                         config.py
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
      MODEL_PATH          memory            output
          │             parameters          paths
          │                 │                 │
          ▼                 ▼                 ▼
    model_loader.py     NUM_SLOTS        REPORTS_DIR
          │             BATCH            OUT_WAT_PATH
          │             ALIGN            WAT_TEMPLATE_PATH
          │             KERNEL_BASE_HINT
          ▼
      TFLite model
          │
          ▼
    extraction pipeline
          │
          ├── graph
          ├── slots
          ├── weights and biases
          ├── quantization
          ├── memory layout
          ├── LayerParams
          ├── params_blob
          │
          ▼
     WAT generation
```

Thus, `config.py` is at the beginning of the flow, but its constants influence several later stages.

---

# 3. `Path` and path handling

The module begins with:

```python
from pathlib import Path
```

`Path` belongs to the Python standard library and represents filesystem paths as objects.

For example:

```python
MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)
```

instead of:

```python
MODEL_PATH = "model_int8_esp32.tflite"
```

Using `Path` makes subsequent operations easier, such as:

```python
MODEL_PATH.read_bytes()
```

or:

```python
REPORTS_DIR / "02-grafo.txt"
```

In this second case:

```python
REPORTS_DIR = Path("reports")
```

and:

```python
REPORTS_DIR / "02-grafo.txt"
```

conceptually produce:

```text
reports/02-grafo.txt
```

On Windows, Python automatically adapts the directory separator as needed.

---

# 4. Relative paths

All paths defined in this file are relative:

```python
Path("model_int8_esp32.tflite")
Path("wat/model_template.wat")
Path("generated/model.wat")
Path("reports")
```

This means they are interpreted relative to the Python process's current working directory.

In normal project usage:

```powershell
PS C:\Users\rafae\Downloads\master-degree-project> python .\main.py
```

the working directory is:

```text
C:\Users\rafae\Downloads\master-degree-project
```

Consequently:

```text
MODEL_PATH
```

represents:

```text
C:\Users\rafae\Downloads\master-degree-project\
model_int8_esp32.tflite
```

and:

```text
WAT_TEMPLATE_PATH
```

represents:

```text
C:\Users\rafae\Downloads\master-degree-project\
wat\
model_template.wat
```

The expected structure is approximately:

```text
master-degree-project/
│
├── model_int8_esp32.tflite
├── main.py
│
├── extractor/
│   ├── config.py
│   ├── ...
│   └── wat_generator.py
│
├── wat/
│   └── model_template.wat
│
├── generated/
│   └── model.wat
│
├── reports/
│   └── ...
│
└── docs/
    └── ...
```

---

# 5. `MODEL_PATH`

```python
MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)
```

## Purpose

Defines the TFLite file used as pipeline input.

This file contains the neural model already converted to TensorFlow Lite and quantized.

The extractor uses this artifact as the canonical representation of the model.

Flow:

```text
model_int8_esp32.tflite
        │
        ▼
   model_loader.py
        │
        ▼
   Model object
        │
        ▼
    SubGraph 0
        │
        ├── operators
        ├── tensors
        ├── buffers
        ├── shapes
        ├── weights
        ├── biases
        └── quantization parameters
```

This file provides the information needed to build the executable representation subsequently used by the WAT.

## Important

`MODEL_PATH` only identifies the input file.

It does not load the model.

Loading happens later, for example:

```python
model = load_model(
    MODEL_PATH
)
```

This keeps `config.py` free of side effects.

---

# 6. `WAT_TEMPLATE_PATH`

```python
WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)
```

## Purpose

Specifies where the WebAssembly Text template used by the final generation stage is stored.

Unlike the old implementation, Python no longer builds all the WAT code line by line.

There is now a separation between:

```text
WebAssembly algorithms
        +
data extracted from the model
```

The file:

```text
wat/model_template.wat
```

contains the relatively static implementation of algorithms such as:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

It also contains helper functions for requantization and execution.

Model-dependent values appear in the template through placeholders.

Conceptual example:

```wat
(memory (export "memory") @@MEM_PAGES@@)

(global $PARAMS_BASE
    i32
    (i32.const @@PARAMS_BASE@@)
)

(global $NUM_LAYERS
    i32
    (i32.const @@NUM_LAYERS@@)
)
```

During generation:

```text
WAT template
      +
data produced by the extractor
      ↓
generated/model.wat
```

This separation avoids mixing algorithm logic with TFLite extraction logic.

---

# 7. `OUT_WAT_PATH`

```python
OUT_WAT_PATH = Path(
    "generated/model.wat"
)
```

## Purpose

Defines the destination of the final WAT file generated by the pipeline.

After all values have been extracted and calculated, the generator replaces the template placeholders and inserts the necessary binary segments.

The result is written to:

```text
generated/model.wat
```

Flow:

```text
wat/model_template.wat
          │
          │
          ├── MEM_PAGES
          ├── PARAMS_BASE
          ├── NUM_LAYERS
          ├── memory bases
          └── data segments
          │
          ▼
    wat_generator.py
          │
          ▼
generated/model.wat
```

This file can later be compiled with:

```text
wat2wasm
```

to produce the binary WebAssembly module.

Keeping the generated file in `generated/` also clearly separates:

```text
wat/model_template.wat
```

which is manually maintained source code,

from:

```text
generated/model.wat
```

which is an automatically produced artifact.

---

# 8. `REPORTS_DIR`

```python
REPORTS_DIR = Path(
    "reports"
)
```

## Purpose

Defines the directory where reports from the different extraction stages are written.

During refactoring, information previously inserted as comments inside the WAT was moved into these files.

The adopted principle is:

```text
WAT
    → only what is needed for execution

reports/
    → explanation of generated values
    → traceability
    → debugging
    → process validation
```

Examples:

```text
reports/
├── 02-grafo.txt
├── 03-alocacao-slots.txt
├── 04-mapeamento-tensor-slot.txt
├── 05-pesos-bias.txt
├── 06-quantizacao.txt
├── 07-slot-bytes.txt
├── 08-layout-parametros.txt
├── 09-layer-params.txt
├── 10-params-blob.txt
└── 11-layout-final-memoria.txt
```

This organization lets you verify, step by step, how the TFLite model was transformed into the structure consumed by the WebAssembly runtime.

---

# 9. `NUM_SLOTS`

```python
NUM_SLOTS = 3
```

## Purpose

Defines how many reusable memory regions are available for storing the network's intermediate tensors.

In this project:

```text
NUM_SLOTS = 3
```

means:

```text
SLOT0
SLOT1
SLOT2
```

These slots do not represent three specific tensors.

They are physical regions reused by different tensors throughout network execution.

The idea is:

```text
tensor A → SLOT0

tensor A is no longer needed

tensor D → SLOT0
```

This avoids reserving an independent memory region for every intermediate tensor.

---

# 10. Relationship between tensors and slots

Consider a simplified sequence:

```text
L1
 ↓
L2
 ↓
L3
 ↓
L4
```

One possible allocation would be:

```text
L1 → SLOT1
L2 → SLOT2
L3 → SLOT0
L4 → SLOT1
```

Representation:

```text
time ────────────────────────────────►

SLOT0                  [ L3 output ]

SLOT1     [ L1 output ]              [ L4 output ]

SLOT2           [ L2 output ]
```

The same physical space can be reused after its previous contents are no longer needed.

---

# 11. Why three slots?

The current value:

```python
NUM_SLOTS = 3
```

is part of the allocation strategy used in this project.

The algorithm in `slots.py` calculates which outputs can share regions without overwriting tensors that later layers still need to consume.

In addition, the current WAT template explicitly contains:

```text
SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
```

Thus, there is currently a structural relationship between:

```python
NUM_SLOTS = 3
```

and the WAT template.

Simply changing it to:

```python
NUM_SLOTS = 4
```

is not enough.

The current generator validates this condition, and the template would need to be adapted to accept a fourth slot.

Therefore, `NUM_SLOTS` should currently be treated as a structural runtime setting, rather than an arbitrary number.

---

# 12. `BATCH`

```python
BATCH = 1
```

## Purpose

Defines the batch size considered by memory planning.

In the current model, inference runs on one image at a time:

```text
batch = 1
```

Conceptually, an input could have shape:

```text
[1, 128, 128, 3]
```

representing:

```text
1 image
128 pixels high
128 pixels wide
3 channels
```

Number of elements:

```text
1 × 128 × 128 × 3
= 49,152 elements
```

For an `int8` or `uint8` tensor:

```text
49,152 × 1 byte
= 49,152 bytes
```

---

# 13. Relationship between `BATCH` and dynamic shapes

The current function for calculating the number of elements in a tensor retains legacy support for negative dimensions.

Conceptually:

```python
if dimension < 0:
    dimension = batch
```

Thus, for:

```text
[-1, 128, 128, 3]
```

with:

```python
BATCH = 1
```

the calculation becomes:

```text
[1, 128, 128, 3]
```

However, this rule should be interpreted carefully.

A dimension of `-1` in a model does not necessarily mean that dimension is the batch.

For example:

```text
[1, -1, 128, 3]
```

could represent a dynamic height.

In that case, automatically replacing:

```text
-1 → BATCH
```

would be incorrect.

For the model currently used in the project, the relevant dimensions are expected to be statically defined. Negative dimensions should therefore be treated as a validation point if new models are used in the future.

---

# 14. `ALIGN`

```python
ALIGN = 16
```

## Purpose

Defines the alignment, in bytes, used to organize different regions of linear memory.

The current value is:

```text
16 bytes
```

Several regions are positioned using:

```python
align_up(
    address,
    ALIGN
)
```

Thus, each new region starts at an address that is a multiple of 16.

Example:

```text
current address = 1001
ALIGN = 16
```

Nearby multiples are:

```text
992
1008
1024
...
```

Therefore:

```text
align_up(1001, 16)
= 1008
```

---

# 15. Why use alignment?

Consider two regions:

```text
WEIGHTS
BIAS
```

If the weights end at address:

```text
386651
```

the next region does not necessarily need to start immediately at:

```text
386651
```

With 16-byte alignment:

```text
align_up(386651, 16)
= 386656
```

Thus:

```text
WEIGHTS
│
├── data
│
└── end = 386651
        │
        ├── 5 bytes of padding
        │
        ▼
BIAS starts at 386656
```

These gaps between regions are called alignment padding.

---

# 16. Formula used

The project conceptually uses:

```python
(value + alignment - 1) & ~(alignment - 1)
```

For:

```text
alignment = 16
```

the calculation is appropriate because 16 is a power of two:

```text
16 = 2⁴
```

This bitwise implementation assumes that the alignment is a power of two.

Therefore, natural values for this implementation would be:

```text
1
2
4
8
16
32
64
...
```

rather than arbitrary values such as:

```text
10
12
20
```

In the current project:

```python
ALIGN = 16
```

satisfies this condition.

---

# 17. Where `ALIGN` is used

Alignment is involved in several memory decisions.

Simplified example:

```text
KERNEL_BASE_HINT
      │
      ▼
align_up()
      │
      ▼
KERNEL_BASE
      │
      │ + kernel_bytes
      ▼
align_up()
      │
      ▼
BIAS_BASE
      │
      │ + bias_bytes
      ▼
align_up()
      │
      ▼
MUL_BASE
      │
      ▼
SHIFT_BASE
      │
      ▼
Q6_BASE
      │
      ▼
PARAMS_BASE
      │
      ▼
SLOT0_BASE
```

Therefore, `ALIGN` is not only a property of the weights. It influences the global memory layout.

---

# 18. `KERNEL_BASE_HINT`

```python
KERNEL_BASE_HINT = 2048
```

## Purpose

Defines the reference starting address from which the weight block can be placed in linear memory.

The value still passes through the alignment function:

```python
kernel_base = align_up(
    KERNEL_BASE_HINT,
    ALIGN
)
```

In the current case:

```text
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

Since:

```text
2048 / 16 = 128
```

the address is already aligned.

Therefore:

```text
kernel_base = 2048
```

---

# 19. Why does the name contain `HINT`?

The value is not used directly as an absolute truth.

It serves as the requested starting point for the weight region:

```text
KERNEL_BASE_HINT
        │
        ▼
    align_up()
        │
        ▼
   actual KERNEL_BASE
```

Hypothetical example:

```python
KERNEL_BASE_HINT = 2050
ALIGN = 16
```

would produce:

```text
KERNEL_BASE = 2064
```

Therefore:

```text
hint ≠ necessarily the effective base
```

With the current value, both coincide because `2048` is already aligned.

---

# 20. Region before the weights

Since:

```text
KERNEL_BASE = 2048
```

the preceding addresses:

```text
0 ... 2047
```

are not used by the weight block.

This allows that region to remain available for runtime structures or communication.

For example, the WAT template currently uses a small initial region for flags that communicate with the host.

The key point for the extractor is that the weights **do not start at address zero**.

Simplified representation:

```text
WASM linear memory

0
│
│ initial/reserved region
│
│
2048  ← KERNEL_BASE
│
├── WEIGHTS
│
├── BIAS
│
├── MUL
│
├── SHIFT
│
├── Q6
│
├── LayerParams
│
├── SLOT0
│
├── SLOT1
│
└── SLOT2
```

The exact historical reason for choosing `2048` should be documented separately if it becomes necessary to explain why precisely 2 KiB was reserved rather than some other amount.

For the current pipeline, the objective fact is:

```text
2048 is the configured starting point for the parameter layout.
```

---

# 21. Relationship between `KERNEL_BASE_HINT` and the layout

Subsequent planning can be visualized as follows:

```text
KERNEL_BASE_HINT = 2048
           │
           ▼
    align_up(2048, 16)
           │
           ▼
    KERNEL_BASE = 2048
           │
           │ + weight size
           ▼
     end of weights
           │
           ▼
       align_up
           │
           ▼
       BIAS_BASE
           │
           │ + bias size
           ▼
       align_up
           │
           ▼
        MUL_BASE
           │
           ▼
       SHIFT_BASE
           │
           ▼
         Q6_BASE
           │
           ▼
       PARAMS_BASE
           │
           ▼
       SLOT0_BASE
           │
           ▼
       SLOT1_BASE
           │
           ▼
       SLOT2_BASE
```

Thus, only the first region has an initially configured base.

The following regions are derived mathematically from the sizes of the preceding regions.

---

# 22. Separating configuration from extracted values

It is useful to distinguish two categories of information in the project.

## Manually configured values

These are defined in `config.py`:

```text
MODEL_PATH
WAT_TEMPLATE_PATH
OUT_WAT_PATH
REPORTS_DIR

NUM_SLOTS
BATCH
ALIGN
KERNEL_BASE_HINT
```

## Automatically discovered or calculated values

These are produced during extraction:

```text
kernel_bytes
bias_bytes
mul_bytes
shift_bytes
q6_bytes

SLOT_BYTES

kernel_base
bias_base
mul_base
shift_base
q6_base
params_base

slot_bases

NUM_LAYERS
MEM_END
MEM_PAGES
RESULT_BASE
RESULT_COUNT
```

This division is fundamental.

For example, we should not put this in `config.py`:

```python
PARAMS_BASE = 499360
```

because `PARAMS_BASE` depends on the actual contents of the model.

Likewise, we should not put:

```python
MEM_PAGES = 17
```

because the page count depends on the calculated final layout.

These values are extraction results, not settings.

---

# 23. Configuration versus result

We can summarize the relationship as:

```text
config.py
   │
   │ input parameters
   ▼
extractor
   │
   │ calculations
   ▼
results
```

For example:

```text
ALIGN = 16
KERNEL_BASE_HINT = 2048
        │
        ▼
calculate_parameter_layout()
        │
        ▼
kernel_base
bias_base
mul_base
shift_base
q6_base
params_base
```

And:

```text
NUM_SLOTS = 3
        │
        ▼
allocate_slots()
calculate_slot_bytes()
        │
        ▼
slot allocation
SLOT_BYTES
slot_bases
```

---

# 24. Main dependencies

A simplified view of the current dependencies is:

```text
MODEL_PATH
    ↓
model_loader.py


NUM_SLOTS
    ↓
slots.py
    ↓
layer_params.py
    ↓
wat_generator.py


BATCH
    ↓
memory.py


ALIGN
    ↓
memory.py
    ↓
parameter layout
    ↓
layer memory layout


KERNEL_BASE_HINT
    ↓
memory.py
    ↓
kernel_base


REPORTS_DIR
    ↓
reporting.py / main.py


WAT_TEMPLATE_PATH
    ↓
wat_generator.py


OUT_WAT_PATH
    ↓
wat_generator.py
```

---

# 25. Why centralize this information?

Without `config.py`, values such as:

```python
3
1
16
2048
```

could be scattered across several modules.

For example:

```python
allocate_slots(
    layers,
    num_slots=3
)
```

and then:

```python
align_up(
    value,
    16
)
```

and also:

```python
kernel_base = 2048
```

This would introduce magic numbers.

By centralizing:

```python
NUM_SLOTS = 3
BATCH = 1
ALIGN = 16
KERNEL_BASE_HINT = 2048
```

the meaning of these numbers becomes explicit.

---

# 26. What happens if each setting changes?

### `MODEL_PATH`

Changing it to:

```python
MODEL_PATH = Path(
    "outro_modelo.tflite"
)
```

makes the pipeline attempt to extract another model.

However, this does not automatically guarantee that the new model is compatible with every operator implemented in the WAT template.

---

### `WAT_TEMPLATE_PATH`

Changing this value makes the generator use another WAT template.

In the future, this would make it possible to have, for example:

```text
wat/
├── model_template.wat
├── model_template_debug.wat
└── model_template_simd.wat
```

without changing the extractor logic.

---

### `OUT_WAT_PATH`

Changes only the destination of the generated WAT.

For example:

```python
OUT_WAT_PATH = Path(
    "generated/model_debug.wat"
)
```

---

### `REPORTS_DIR`

Changes where reports are written.

It should not change inference calculations.

---

### `NUM_SLOTS`

Has a structural impact on activation planning and on the WAT template.

In the current state:

```text
NUM_SLOTS = 3
```

must remain synchronized with the template, which has three slot bases.

---

### `BATCH`

Affects size calculations when a dynamic dimension needs to be resolved by the rule currently used by the extractor.

For the current model:

```text
BATCH = 1
```

is consistent with individual inference.

---

### `ALIGN`

Affects almost the entire memory layout.

Changing it can modify:

```text
kernel_base
bias_base
mul_base
shift_base
q6_base
params_base
slot_bases
MEM_END
MEM_PAGES
```

---

### `KERNEL_BASE_HINT`

Moves the starting point of the parameter region.

As a consequence, all subsequent regions may also move.

---

# 27. Example of a setting propagating

Consider:

```python
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

The first operation is:

```text
kernel_base =
align_up(2048, 16)

kernel_base = 2048
```

Suppose, only as an example:

```text
kernel_bytes = 384608
```

then:

```text
end of weights =
2048 + 384608

= 386656
```

The next region:

```text
bias_base =
align_up(386656, 16)

= 386656
```

The same process is then applied to the remaining regions.

Thus, a single initial setting helps determine the entire chain of addresses.

---

# 28. What should not go in `config.py`

This module should not contain values that belong to the specific model after extraction.

For example, it is inappropriate to put:

```python
NUM_LAYERS = 68

SLOT_BYTES = 196608

WEIGHTS_BASE = 2048

BIAS_BASE = 386656

PARAMS_BASE = 499360

MEM_PAGES = 17
```

even if these values are true for a particular run.

They should be calculated.

Otherwise, changing the TFLite file could produce a structurally incorrect WAT.

The adopted rule is:

```text
config.py
    ↓
defines policies and inputs

extractor
    ↓
discovers model properties

reports
    ↓
record results

wat_generator
    ↓
consumes results
```

---

# 29. Current module state

The module is deliberately small.

```python
from pathlib import Path


MODEL_PATH = Path(
    "model_int8_esp32.tflite"
)

WAT_TEMPLATE_PATH = Path(
    "wat/model_template.wat"
)

OUT_WAT_PATH = Path(
    "generated/model.wat"
)

REPORTS_DIR = Path(
    "reports"
)

NUM_SLOTS = 3

BATCH = 1

ALIGN = 16

KERNEL_BASE_HINT = 2048
```

There is no need for classes, functions, or more complex structures at this point.

The module serves as a centralized configuration source for a pipeline run locally.

---

# 30. Summary

The role of each variable can be summarized as follows:

| Setting | Purpose |
| ------------------- | --------------------------------------------------------------- |
| `MODEL_PATH` | Path to the TFLite model used as input |
| `WAT_TEMPLATE_PATH` | Path to the static WAT code used as a template |
| `OUT_WAT_PATH` | Path to the automatically generated WAT |
| `REPORTS_DIR` | Directory for extraction reports |
| `NUM_SLOTS` | Number of reusable regions for intermediate tensors |
| `BATCH` | Batch used in shape/size planning |
| `ALIGN` | Alignment of memory regions in bytes |
| `KERNEL_BASE_HINT` | Reference starting address for the weight block |

The main architectural idea is that `config.py` contains only **inputs and configuration policies**.

Model-dependent information should be obtained by the extractor itself.

In other words:

```text
CONFIGURATION
     │
     ▼
   EXTRACTION
     │
     ▼
   CALCULATION
     │
     ▼
  VALIDATION
     │
     ▼
 SERIALIZATION
     │
     ▼
 WAT GENERATION
```

This separation makes the pipeline more reproducible, traceable, and suitable for other models in the future without requiring manual changes to internal addresses and parameters.
