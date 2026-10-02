[English](07-weight-bias-extraction.md) | [Português (Brasil)](07-extracao-pesos-bias.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in the Portuguese edition.

# 07 — Extracting and serializing weights and biases (`weights.py`)

## 1. Module purpose

`extractor/weights.py` extracts constant weight and bias tensors from TFLite operations that have trainable parameters.

It converts the TFLite file's separate buffers into two contiguous binary blocks:

```text
weights_raw
bias_raw
```

The module also records where each tensor was placed within these blocks.

The conceptual result is:

```text
TFLite

weight tensor 10 ──┐
weight tensor 20 ──┼──► weights_raw
weight tensor 35 ──┘

bias tensor 11 ──┐
bias tensor 21 ──┼──► bias_raw
bias tensor 36 ──┘
```

Each tensor receives a relative offset:

```text
tensor 10 → offset 0
tensor 20 → offset 864
tensor 35 → offset 1728
```

These offsets will later determine actual addresses in WebAssembly linear memory.

---

# 2. Current code

```python
from extractor.tflite_utils import (
    op_name,
    safe_bytes_from_tensor,
)


WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}


def extract_weights_and_bias(
    model,
    subgraph,
):
    """
    Extrai os pesos e bias das operações que possuem
    parâmetros treináveis.

    Retorna:
        weights_raw:
            bloco contínuo contendo os bytes dos pesos.

        bias_raw:
            bloco contínuo contendo os bytes dos bias.

        weight_tensor_off:
            tensor_id -> offset do peso dentro de weights_raw.

        bias_tensor_off:
            tensor_id -> offset do bias dentro de bias_raw.

        weight_records:
            metadados utilizados para relatório.

        bias_records:
            metadados utilizados para relatório.
    """

    weights_raw = bytearray()
    bias_raw = bytearray()

    weight_tensor_off = {}
    bias_tensor_off = {}

    weight_records = []
    bias_records = []

    for op_idx in range(
        subgraph.OperatorsLength()
    ):
        op = subgraph.Operators(
            op_idx
        )

        op_type = op_name(
            model,
            op,
        )

        if op_type not in WEIGHT_OPERATORS:
            continue

        input_ids = [
            int(tensor_id)
            for tensor_id
            in op.InputsAsNumpy()
            if int(tensor_id) >= 0
        ]

        # Essas operações precisam de pelo menos:
        #
        # input[0] = ativação
        # input[1] = pesos
        #
        if len(input_ids) < 2:
            continue

        # ====================================================
        # PESOS
        # ====================================================

        weight_tensor_id = input_ids[1]

        (
            weight_tensor,
            weight_array,
            weight_raw,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            weight_tensor_id,
        )

        if (
            weight_array is not None
            and weight_tensor_id
            not in weight_tensor_off
        ):
            offset = len(
                weights_raw
            )

            weight_tensor_off[
                weight_tensor_id
            ] = offset

            weights_raw.extend(
                weight_raw
            )

            weight_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        weight_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        weight_raw
                    ),
                    "shape": list(
                        weight_array.shape
                    ),
                    "dtype": str(
                        weight_array.dtype
                    ),
                }
            )

        # ====================================================
        # BIAS
        # ====================================================

        if len(input_ids) < 3:
            continue

        bias_tensor_id = input_ids[2]

        (
            bias_tensor,
            bias_array,
            bias_raw_tensor,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            bias_tensor_id,
        )

        if (
            bias_array is not None
            and bias_array.ndim == 1
            and bias_tensor_id
            not in bias_tensor_off
        ):
            offset = len(
                bias_raw
            )

            bias_tensor_off[
                bias_tensor_id
            ] = offset

            bias_raw.extend(
                bias_raw_tensor
            )

            bias_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        bias_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        bias_raw_tensor
                    ),
                    "shape": list(
                        bias_array.shape
                    ),
                    "dtype": str(
                        bias_array.dtype
                    ),
                }
            )

    return {
        "weights_raw": bytes(
            weights_raw
        ),

        "bias_raw": bytes(
            bias_raw
        ),

        "weight_tensor_off": (
            weight_tensor_off
        ),

        "bias_tensor_off": (
            bias_tensor_off
        ),

        "weight_records": (
            weight_records
        ),

        "bias_records": (
            bias_records
        ),
    }


def weights_bias_to_text(
    extraction,
):
    ...
```

---

# 3. Position in the pipeline

The flow up to this stage is:

```text
model.tflite
     │
     ▼
model_loader.py
     │
     ▼
Model + SubGraph
     │
     ├── graph.py
     ├── slots.py
     ├── tensor_mapping.py
     │
     ▼
weights.py
     │
     ├── weights_raw
     ├── bias_raw
     ├── weight_tensor_off
     └── bias_tensor_off
```

This module does not handle temporary activations.

It handles constant network parameters.

---

# 4. Two major memory categories

At this point, it is important to separate:

```text
ACTIVATIONS
```

from:

```text
CONSTANT PARAMETERS
```

Activations use:

```text
SLOT0
SLOT1
SLOT2
```

Weights and biases use their own regions:

```text
WEIGHTS
BIAS
```

Conceptually:

```text
WASM memory

┌──────────────────────┐
│ initial region       │
├──────────────────────┤
│ WEIGHTS              │ ← this module
├──────────────────────┤
│ BIAS                 │ ← this module
├──────────────────────┤
│ MUL                  │
├──────────────────────┤
│ SHIFT                │
├──────────────────────┤
│ Q6                   │
├──────────────────────┤
│ LayerParams          │
├──────────────────────┤
│ SLOT0                │
├──────────────────────┤
│ SLOT1                │
└──────────────────────┘
```

---

# 5. Importing `op_name()`

The module imports:

```python
op_name
```

from:

```text
tflite_utils.py
```

This function converts internal TFLite codes into names such as:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

The module needs this to decide which operations have weights and biases to extract.

---

# 6. Importing `safe_bytes_from_tensor()`

It also imports:

```python
safe_bytes_from_tensor
```

Its purpose is to convert:

```text
tensor_id
```

into:

```text
TFLite Tensor
+
NumPy array
+
linear bytes
```

Flow:

```text
tensor_id
    │
    ▼
safe_bytes_from_tensor()
    │
    ├── tensor
    ├── ndarray
    └── raw bytes
```

`weights.py` mainly uses:

```text
ndarray
raw bytes
```

---

# 7. `WEIGHT_OPERATORS`

The module defines:

```python
WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}
```

This explicitly defines which operations are examined for weight and bias extraction.

The current rule is:

```text
op_type ∈ WEIGHT_OPERATORS
          │
          ├── yes → analyze parameters
          │
          └── no → skip
```

---

# 8. Operations considered

The current set contains:

```text
CONV_2D

DEPTHWISE_CONV_2D

FULLY_CONNECTED
```

Other network operations, such as:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
```

do not go through this weight and bias extraction routine.

---

# 9. Why keep an explicit set?

We could write:

```python
if op_type == "CONV_2D":
```

and then repeat rules.

But:

```python
WEIGHT_OPERATORS
```

makes it explicit that these three operations share the same structural convention used by the extractor:

```text
input[0] = activation
input[1] = weights
input[2] = bias, when present
```

---

# 10. The `extract_weights_and_bias()` function

The main function is:

```python
def extract_weights_and_bias(
    model,
    subgraph,
):
```

It receives:

```text
Model
SubGraph
```

and returns all blocks and indices needed to locate parameters later.

---

# 11. Byte structures

Initially, it creates:

```python
weights_raw = bytearray()
bias_raw = bytearray()
```

---

# 12. Why `bytearray`?

`bytearray` is a mutable binary structure.

It allows:

```python
weights_raw.extend(
    weight_raw
)
```

repeatedly.

This is convenient because the final size is not yet known.

The block grows as tensors are found.

---

# 13. Example

Initially:

```text
weights_raw = empty
```

After the first tensor:

```text
[ WEIGHT A ]
```

After the second:

```text
[ WEIGHT A ][ WEIGHT B ]
```

After the third:

```text
[ WEIGHT A ][ WEIGHT B ][ WEIGHT C ]
```

There is no separate region per layer.

All tensors are concatenated.

---

# 14. Offset dictionaries

The following are also created:

```python
weight_tensor_off = {}
bias_tensor_off = {}
```

They relate:

```text
tensor_id
    ↓
offset within the blob
```

---

# 15. Example of `weight_tensor_off`

Suppose:

```text
tensor 10:
400 bytes

tensor 20:
800 bytes

tensor 30:
100 bytes
```

Concatenation will be:

```text
offset
0
│
├── tensor 10
│   400 bytes
│
400
│
├── tensor 20
│   800 bytes
│
1200
│
├── tensor 30
│   100 bytes
│
1300
```

Then:

```python
weight_tensor_off = {
    10: 0,
    20: 400,
    30: 1200,
}
```

---

# 16. An offset is not an absolute address

This distinction is fundamental.

When we have:

```python
weight_tensor_off[20] = 400
```

this does NOT mean:

```text
WASM address = 400
```

It means:

```text
400 bytes after the start of WEIGHTS
```

---

# 17. Later conversion

Later:

```text
WEIGHTS_BASE
+
weight_tensor_off[tensor_id]
=
absolute address
```

Example:

```text
WEIGHTS_BASE = 2048

offset = 400
```

Then:

```text
wptr =
2048 + 400
=
2448
```

---

# 18. Same concept for bias

If:

```python
bias_tensor_off[21] = 128
```

and:

```text
BIAS_BASE = 386656
```

then:

```text
bias_ptr =
386656 + 128
```

The offset remains relative to its own block.

---

# 19. Report records

The following are also created:

```python
weight_records = []
bias_records = []
```

These lists do not store binary contents.

They store metadata:

```text
which operation
which type
which tensor
offset
number of bytes
shape
dtype
```

---

# 20. Separating data and metadata

We have:

```text
weights_raw
    ↓
data actually used by the runtime
```

and:

```text
weight_records
    ↓
traceability information
```

Similarly:

```text
bias_raw
```

versus:

```text
bias_records
```

---

# 21. Scanning operators

The function iterates over:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

It therefore examines all subgraph operators in their original order.

---

# 22. Retrieving the operator

```python
op = subgraph.Operators(
    op_idx
)
```

This provides access to that operation's inputs.

---

# 23. Identifying the type

Then:

```python
op_type = op_name(
    model,
    op,
)
```

produces something like:

```text
CONV_2D
```

---

# 24. Filtering

If:

```python
op_type not in WEIGHT_OPERATORS
```

the following executes:

```python
continue
```

That operation therefore does not participate in extraction.

---

# 25. Example

A sequence:

```text
CONV_2D
DEPTHWISE_CONV_2D
ADD
CONV_2D
MEAN
FULLY_CONNECTED
SOFTMAX
```

results in processing only:

```text
CONV_2D
DEPTHWISE_CONV_2D
CONV_2D
FULLY_CONNECTED
```

---

# 26. Collecting input IDs

For an accepted operation:

```python
input_ids = [
    int(tensor_id)
    for tensor_id
    in op.InputsAsNumpy()
    if int(tensor_id) >= 0
]
```

This expression converts inputs into an ordinary list of Python integers.

---

# 27. Example

If:

```text
op.InputsAsNumpy()
=
[12, 30, 31]
```

the result will be:

```python
input_ids = [
    12,
    30,
    31,
]
```

---

# 28. Negative inputs

Negative IDs are discarded:

```python
if int(tensor_id) >= 0
```

Only valid references remain.

---

# 29. Input convention

The module uses the convention:

```text
input[0] = activation

input[1] = weights

input[2] = bias
```

when the third input exists.

This convention is central to the implementation.

---

# 30. Example

An operation may have:

```python
input_ids = [
    45,
    46,
    47,
]
```

The module interprets:

```text
tensor 45 → activation

tensor 46 → weights

tensor 47 → bias
```

---

# 31. Operation with insufficient weight inputs

Before attempting to access:

```python
input_ids[1]
```

there is:

```python
if len(input_ids) < 2:
    continue
```

This prevents:

```text
IndexError
```

and indicates that the operation lacks the minimum structure expected for weight extraction.

---

# 32. Extracting the weight tensor

The weight is identified by:

```python
weight_tensor_id = (
    input_ids[1]
)
```

---

# 33. Reading the weight

Then:

```python
(
    weight_tensor,
    weight_array,
    weight_raw,
) = safe_bytes_from_tensor(
    model,
    subgraph,
    weight_tensor_id,
)
```

Three representations are received.

---

# 34. `weight_tensor`

This is the TFLite object itself.

In the current implementation, it is assigned to:

```python
weight_tensor
```

but is not used later in the function.

Its presence follows from the uniform interface of:

```python
safe_bytes_from_tensor()
```

---

# 35. `weight_array`

This is the NumPy array containing weight values.

It provides information such as:

```text
shape
dtype
ndim
```

Example:

```python
weight_array.shape
```

and:

```python
weight_array.dtype
```

---

# 36. `weight_raw`

This is the tensor's corresponding linear byte block.

This representation will be concatenated into:

```python
weights_raw
```

---

# 37. Insertion condition

The tensor is included only if:

```python
weight_array is not None
```

and:

```python
weight_tensor_id
not in weight_tensor_off
```

---

# 38. First condition

```python
weight_array is not None
```

means that:

```text
safe_bytes_from_tensor()
```

successfully retrieved and interpreted the buffer.

---

# 39. Second condition

```python
weight_tensor_id
not in weight_tensor_off
```

prevents inserting the same tensor more than once.

---

# 40. Why is deduplication important?

Multiple operations may reference the same constant tensor.

Without the check:

```text
tensor X
```

could appear twice in:

```text
weights_raw
```

wasting memory.

---

# 41. Sharing example

Suppose:

```text
Op10 uses tensor 50

Op20 also uses tensor 50
```

At the first occurrence:

```text
tensor 50 → extracted
```

At the second:

```text
tensor 50 already exists in weight_tensor_off
```

Therefore:

```text
it is not duplicated
```

Both operations can use the same offset.

---

# 42. Determining the offset

Before inserting bytes:

```python
offset = len(
    weights_raw
)
```

The block's current length is exactly the next free relative address.

---

# 43. Example

If:

```text
weights_raw contains 15,000 bytes
```

so the next tensor starts at:

```text
offset = 15000
```

---

# 44. Recording the offset

Then:

```python
weight_tensor_off[
    weight_tensor_id
] = offset
```

Example:

```python
weight_tensor_off[50] = 15000
```

---

# 45. Inserting bytes

```python
weights_raw.extend(
    weight_raw
)
```

Bytes are concatenated immediately after the preceding contents.

---

# 46. Progressive layout

Before:

```text
weights_raw

[ A ][ B ]
```

Then:

```text
weights_raw

[ A ][ B ][ NEW WEIGHT ]
```

---

# 47. No alignment between tensors here

An important detail of the current implementation is that `weights.py` simply concatenates tensors.

There is no:

```text
align_up()
```

between one weight tensor and the next.

Therefore:

```text
next offset =
current offset + current byte count
```

---

# 48. Alignment occurs at another level

The project's `ALIGN = 16` is used later when placing the major regions:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOTS
```

This module inserts no alignment padding between individual weight tensors.

---

# 49. Recording metadata

After insertion, it creates:

```python
{
    "op_index": op_idx,
    "op_type": op_type,
    "tensor_id": weight_tensor_id,
    "offset": offset,
    "nbytes": len(weight_raw),
    "shape": list(
        weight_array.shape
    ),
    "dtype": str(
        weight_array.dtype
    ),
}
```

---

# 50. op_index field

Example:

```text
op_index = 12
```

indicates which operation led to the discovery of that tensor.

---

# 51. The `op_type` field

Example:

```text
CONV_2D
```

identifies the operation semantically.

---

# 52. The `tensor_id` field

Identifies the original TFLite tensor.

Example:

```text
tensor_id = 78
```

---

# 53. The `offset` field

This is the relative position within:

```text
weights_raw
```

Example:

```text
offset = 25856
```

---

# 54. The `nbytes` field

```python
len(
    weight_raw
)
```

indicates how many bytes that tensor occupies.

---

# 55. The `shape` field

The code uses:

```python
list(
    weight_array.shape
)
```

producing something like:

```python
[
    32,
    3,
    3,
    3,
]
```

---

# 56. Why use `list(weight_array.shape)`?

`NumPy.shape` is a tuple.

For example:

```python
(32, 3, 3, 3)
```

The report uses an ordinary list:

```python
[32, 3, 3, 3]
```

This conversion also standardizes the returned structure.

---

# 57. The `dtype` field

```python
str(
    weight_array.dtype
)
```

produces a text representation such as:

```text
int8
```

---

# 58. Weight shape

The module does not semantically interpret weight dimensions.

It only records:

```python
weight_array.shape
```

and preserves the byte order produced by:

```python
safe_bytes_from_tensor()
```

In other words, `weights.py` does not perform:

```text
transposition
channel reordering
layout conversion
```

---

# 59. Consequence

The WAT code that later reads the weights must be compatible with the layout serialized by the pipeline.

This module only:

```text
reads
concatenates
records offsets
```

---

# 60. Starting bias extraction

After weights:

```python
if len(input_ids) < 3:
    continue
```

If there is no third input, the operation has no bias handled by this function.

---

# 61. This does not cancel weight extraction

Notice where this check occurs.

The weight has already been processed.

Therefore:

```text
2 inputs
```

may result in:

```text
weight extracted
no bias
```

---

# 62. Identifying bias

When a third input exists:

```python
bias_tensor_id = (
    input_ids[2]
)
```

---

# 63. Reading bias

```python
(
    bias_tensor,
    bias_array,
    bias_raw_tensor,
) = safe_bytes_from_tensor(
    model,
    subgraph,
    bias_tensor_id,
)
```

---

# 64. The name `bias_raw_tensor`

Here the name differs from:

```python
bias_raw
```

because:

```text
bias_raw_tensor
```

represents only the tensor currently being extracted,

while:

```text
bias_raw
```

is the complete accumulated blob.

---

# 65. Example

```text
bias_raw_tensor
=
bytes of a single bias tensor
```

While:

```text
bias_raw
=
[bias A][bias B][bias C][...]
```

---

# 66. `bias_tensor`

As with:

```python
weight_tensor
```

the variable:

```python
bias_tensor
```

is received from `safe_bytes_from_tensor()` but is not used later in the current function.

---

# 67. Conditions for inserting bias

The condition is:

```python
if (
    bias_array is not None
    and bias_array.ndim == 1
    and bias_tensor_id
    not in bias_tensor_off
):
```

There are three checks.

---

# 68. Bias must exist

```python
bias_array is not None
```

indicates that the buffer could be retrieved.

---

# 69. Bias must be one-dimensional

```python
bias_array.ndim == 1
```

is an additional structural check.

Accepted example:

```text
shape = [32]
```

---

# 70. Rejected example

Something like:

```text
shape = [1, 32]
```

has:

```text
ndim = 2
```

and would therefore not be inserted by this implementation.

---

# 71. Why is this check useful?

It ensures that the runtime's bias structure matches the format expected by the rest of the project.

The module does not attempt to fix or reshape bias with an unexpected shape.

---

# 72. Bias deduplication

The third condition:

```python
bias_tensor_id
not in bias_tensor_off
```

has the same purpose as for weights:

```text
avoid storing the same constant tensor twice
```

---

# 73. Bias offset

The offset is:

```python
offset = len(
    bias_raw
)
```

Example:

```text
current bias_raw = 1024 bytes
```

Then:

```text
new bias starts at offset 1024
```

---

# 74. Recording

```python
bias_tensor_off[
    bias_tensor_id
] = offset
```

---

# 75. Concatenation

```python
bias_raw.extend(
    bias_raw_tensor
)
```

---

# 76. Recording metadata

The structure is equivalent to that used for weights:

```python
{
    "op_index": op_idx,
    "op_type": op_type,
    "tensor_id": bias_tensor_id,
    "offset": offset,
    "nbytes": len(
        bias_raw_tensor
    ),
    "shape": list(
        bias_array.shape
    ),
    "dtype": str(
        bias_array.dtype
    ),
}
```

---

# 77. Bias example

Suppose:

```text
shape = [32]
dtype = int32
```

Since:

```text
32 × 4 bytes = 128 bytes
```

the record may contain:

```text
bytes = 128
```

The actual size comes directly from the serialized buffer.

---

# 78. Two independent blobs

Weights and biases are not mixed.

We have:

```text
weights_raw

[W0][W1][W2][W3]...
```

and separately:

```text
bias_raw

[B0][B1][B2][B3]...
```

---

# 79. Why separate them?

Later, the memory layout has:

```text
WEIGHTS_BASE
```

and:

```text
BIAS_BASE
```

independently.

This allows calculating:

```text
wptr =
WEIGHTS_BASE + weight_offset
```

and:

```text
bias_ptr =
BIAS_BASE + bias_offset
```

---

# 80. Relationship with `LayerParam`

Later, a convolution may have:

```text
wptr
bias_ptr
```

These pointers are calculated using the maps generated here.

Flow:

```text
weight tensor_id
      ↓
weight_tensor_off
      ↓
offset
      ↓
WEIGHTS_BASE + offset
      ↓
wptr
```

And:

```text
bias tensor_id
      ↓
bias_tensor_off
      ↓
offset
      ↓
BIAS_BASE + offset
      ↓
bias_ptr
```

---

# 81. Function return value

At the end:

```python
return {
    ...
}
```

a single structure is created with data and metadata.

---

# 82. Converting `bytearray` to `bytes`

The return value uses:

```python
"bytes_raw": bytes(...)
```

more specifically:

```python
"weights_raw": bytes(
    weights_raw
)
```

and:

```python
"bias_raw": bytes(
    bias_raw
)
```

---

# 83. Why convert?

During construction, we need mutability:

```text
bytearray
```

Once extraction finishes, the blob can be treated as ready binary data:

```text
bytes
```

---

# 84. Lifecycle

```text
start
  ↓
mutable bytearray
  ↓
extend()
extend()
extend()
  ↓
extraction complete
  ↓
immutable bytes
```

---

# 85. Returned structure

The result has:

```python
{
    "weights_raw": ...,
    "bias_raw": ...,
    "weight_tensor_off": ...,
    "bias_tensor_off": ...,
    "weight_records": ...,
    "bias_records": ...,
}
```

---

# 86. Data needed for execution

The fields directly used later to generate the artifact are mainly:

```text
weights_raw
bias_raw

weight_tensor_off
bias_tensor_off
```

---

# 87. Report data

Mainly:

```text
weight_records
bias_records
```

The blobs can also be used to calculate byte totals.

---

# 88. Complete output example

Consider two operations.

```text
Op0 CONV
weight tensor 10
bias tensor 11

Op1 CONV
weight tensor 20
bias tensor 21
```

Suppose:

```text
tensor 10 = 100 bytes
tensor 20 = 200 bytes

tensor 11 = 16 bytes
tensor 21 = 32 bytes
```

---

# 89. `weights_raw`

```text
offset 0
│
├── tensor 10
│   100 bytes
│
offset 100
│
├── tensor 20
│   200 bytes
│
offset 300
```

---

# 90. `weight_tensor_off`

```python
{
    10: 0,
    20: 100,
}
```

---

# 91. `bias_raw`

```text
offset 0
│
├── tensor 11
│   16 bytes
│
offset 16
│
├── tensor 21
│   32 bytes
│
offset 48
```

---

# 92. `bias_tensor_off`

```python
{
    11: 0,
    21: 16,
}
```

---

# 93. Future addresses

If later:

```text
WEIGHTS_BASE = 2048
BIAS_BASE = 10000
```

we get:

```text
tensor 10:
wptr = 2048 + 0

tensor 20:
wptr = 2048 + 100
```

and:

```text
tensor 11:
bias_ptr = 10000 + 0

tensor 21:
bias_ptr = 10000 + 16
```

---

# 94. Independent offsets

Notice that:

```text
weight offset = 0
```

and:

```text
bias offset = 0
```

can coexist.

There is no conflict because they belong to different regions.

---

# 95. Important: logical offset per blob

Therefore:

```text
offset 128 in weights_raw
```

and:

```text
offset 128 in bias_raw
```

are completely different positions.

An offset must always be interpreted together with its base.

---

# 96. Relationship with TFLite

In a TFLite file, each constant tensor may point to its own buffer.

Conceptually:

```text
Tensor W0 → Buffer X
Tensor B0 → Buffer Y
Tensor W1 → Buffer Z
...
```

The module reorganizes this into:

```text
WEIGHTS

W0 | W1 | W2 | W3 | ...


BIAS

B0 | B1 | B2 | B3 | ...
```

---

# 97. Structural transformation

This module therefore transforms the representation:

```text
buffers distributed throughout TFLite
          ↓
contiguous runtime blobs
```

---

# 98. It does not change values

Although locations are reorganized, the code does not numerically modify extracted values.

It receives:

```python
weight_raw
```

and performs:

```python
weights_raw.extend(
    weight_raw
)
```

---

# 99. No type conversion

There is no:

```text
int8 → float32
int32 → int8
```

or any other explicit numeric conversion here.

The original dtype interpreted by `safe_bytes_from_tensor()` is preserved in the serialized representation returned by that function.

---

# 100. No quantization in this module

Although the model's weights are quantized, `weights.py` does not calculate:

```text
scale
zero point
multiplier
shift
Q6
```

This responsibility belongs to:

```text
quantization.py
```

---

# 101. Important separation

```text
weights.py
    ↓
what are the weight bytes?
where is each tensor in the blob?


quantization.py
    ↓
how should the accumulated output be requantized?
```

These are different problems.

---

# 102. No absolute address

The following are not calculated either:

```text
WEIGHTS_BASE
BIAS_BASE
```

This responsibility belongs to memory planning.

---

# 103. Separation

```text
weights.py
   ↓
relative offset

memory.py
   ↓
absolute base

layer_params.py
   ↓
base + offset
```

---

# 104. Relationship with `memory.py`

`memory.py` uses the sizes:

```python
len(
    weights_raw
)
```

and:

```python
len(
    bias_raw
)
```

to plan where each region will be placed.

Example:

```text
KERNEL_BASE
   │
   ├── weights_raw
   │
   ▼
end of weights
   │
   ▼
align_up()
   │
   ▼
BIAS_BASE
   │
   ├── bias_raw
```

---

# 105. Relationship with `wat_generator.py`

During final generation:

```text
weights_raw
```

is converted to a data segment at:

```text
WEIGHTS_BASE
```

And:

```text
bias_raw
```

at address:

```text
BIAS_BASE
```

Conceptually:

```wat
(data
    (i32.const WEIGHTS_BASE)
    "...bytes..."
)
```

---

# 106. Blobs as intermediate artifacts

This allows viewing:

```text
weights_raw
bias_raw
```

as intermediate binary artifacts independent of WAT.

The WAT generator simply consumes them.

---

# 107. Architectural benefit

Previously we might have:

```text
weight extraction
      ↓
immediately generate a WAT string
```

Now we have:

```text
extraction
   ↓
structured bytes
   ↓
memory layout
   ↓
generator
   ↓
WAT
```

This makes validation and reuse easier.

---

# 108. The `weights_bias_to_text()` function

The second function:

```python
def weights_bias_to_text(
    extraction,
):
```

converts metadata into a readable report.

It does not participate in extraction.

---

# 109. First section: PESOS (weights)

It starts with:

```python
lines.append(
    "PESOS"
)
```

and:

```python
lines.append(
    "=" * 80
)
```

---

# 110. Iterating over `weight_records`

```python
for item in extraction[
    "weight_records"
]:
```

Each extracted tensor produces one line.

---

# 111. Line contents

The report prints:

```text
op
operation type
tensor
offset
bytes
shape
dtype
```

---

# 112. Example

Something like:

```text
op=  3 CONV_2D                  tensor=  12 offset=       0 bytes=     864 shape=[32, 3, 3, 3] dtype=int8
```

---

# 113. The `op` field

```python
f"op={item['op_index']:3}"
```

The format specifier:

```text
:3
```

serves only for visual alignment.

---

# 114. The `op_type` field

```python
f"{item['op_type']:25}"
```

reserves 25 positions in the report.

---

# 115. The `tensor` field

```python
f"tensor={item['tensor_id']:4}"
```

allows locating the tensor in the model.

---

# 116. The `offset` field

```python
f"offset={item['offset']:8}"
```

is the relative displacement within `weights_raw`.

It is not an absolute address.

---

# 117. The `bytes` field

```python
f"bytes={item['nbytes']:8}"
```

indicates that tensor's size.

---

# 118. The `shape` field

```python
f"shape={item['shape']}"
```

shows the interpreted dimensions.

---

# 119. The `dtype` field

```python
f"dtype={item['dtype']}"
```

shows how elements are interpreted.

---

# 120. Second section: BIAS

Next, it generates:

```text
BIAS
================================================================================
```

using:

```python
bias_records
```

with the same field structure.

---

# 121. Benefit of symmetry

The report makes it easy to compare:

```text
operation
weight
biases
```

even though both are in different blocks.

---

# 122. Summary section

The last part is:

```text
RESUMO
================================================================================
```

It presents four totals.

---

# 123. Number of weight tensors

```python
len(
    extraction[
        "weight_records"
    ]
)
```

---

# 124. Total weight bytes

```python
len(
    extraction[
        "weights_raw"
    ]
)
```

---

# 125. Number of bias tensors

```python
len(
    extraction[
        "bias_records"
    ]
)
```

---

# 126. Total bias bytes

```python
len(
    extraction[
        "bias_raw"
    ]
)
```

---

# 127. Summary example

```text
RESUMO
================================================================================
Total de tensors de pesos: 54
Total de bytes de pesos: 384608
Total de tensors de bias: 52
Total de bytes de bias: 28176
```

These numbers are illustrative; the actual report uses values from the run.

---

# 128. Why can record counts and operator counts differ?

The number of:

```text
weight_records
```

does not have to equal the number of examined operations.

This is because the code deduplicates by:

```text
tensor_id
```

---

# 129. Example

```text
Op10 → weight tensor 50
Op20 → weight tensor 50
```

There are:

```text
2 operation references
```

but only:

```text
1 stored tensor
```

Therefore:

```text
weight_records = 1
```

---

# 130. Blob order

Tensor order within:

```text
weights_raw
```

is determined by the first occurrence of each tensor during the scan:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

---

# 131. Consequence

The layout is not sorted by:

```text
tensor_id
```

or by:

```text
size
```

It essentially follows:

```text
operator order
+
first occurrence of each tensor
```

---

# 132. Example

If the scan encounters:

```text
tensor 50
tensor 12
tensor 90
```

in that order, the blob will be:

```text
[ tensor 50 ][ tensor 12 ][ tensor 90 ]
```

even though numerically:

```text
12 < 50 < 90
```

---

# 133. Why is this not a problem?

Because the runtime does not assume ID order.

It uses:

```text
tensor_id → offset
```

The actual location is explicitly recorded.

---

# 134. Important offset invariant

For every stored tensor:

```text
offset + nbytes
```

must not exceed:

```text
len(blob)
```

Example:

```text
offset = 1000
nbytes = 200
```

The bytes therefore occupy:

```text
1000 ... 1199
```

and:

```text
1200 <= len(weights_raw)
```

at the end of construction.

---

# 135. Contiguity

Because insertion always uses:

```python
offset = len(blob)
blob.extend(data)
```

tensors are contiguous.

This module creates no internal gaps.

---

# 136. Example

```text
tensor A:
offset = 0
size = 100

tensor B:
offset = 100
size = 50

tensor C:
offset = 150
size = 20
```

Therefore:

```text
[0..........99][100....149][150...169]
```

---

# 137. Last offset

If the last tensor starts at:

```text
offset = 150
```

and has:

```text
20 bytes
```

the total size is:

```text
170 bytes
```

---

# 138. Why are relative offsets better?

If `weights.py` directly calculated:

```text
wptr = 2448
```

it would be coupled to the current physical layout.

With a relative offset:

```text
tensor → 400
```

we can change:

```text
WEIGHTS_BASE
```

without extracting again or internally reorganizing weights.

---

# 139. Example

Today:

```text
WEIGHTS_BASE = 2048
offset = 400
wptr = 2448
```

Tomorrow:

```text
WEIGHTS_BASE = 4096
offset = 400
wptr = 4496
```

The blob remains the same.

---

# 140. Separating contents and placement

This is an important architectural decision:

```text
weights.py
   ↓
contents + internal offsets
```

```text
memory.py
   ↓
where the entire block starts
```

```text
layer_params.py
   ↓
final address used by the operation
```

---

# 141. Relationship with `params_blob`

Later, a convolution's `LayerParam` contains:

```text
wptr
bias_ptr
```

It does not contain only:

```text
tensor_id
```

This module's offsets must therefore be converted into pointers before serialization.

---

# 142. Complete weight flow

```text
TFLite weight tensor
        │
        ▼
safe_bytes_from_tensor()
        │
        ├── array
        └── raw
             │
             ▼
weights.py
        │
        ├── weights_raw
        └── weight_tensor_off
             │
             ▼
memory.py
        │
        └── WEIGHTS_BASE
             │
             ▼
layer_params / params_blob
        │
        └── wptr
             │
             ▼
WAT/WASM
```

---

# 143. Complete bias flow

```text
TFLite bias tensor
        │
        ▼
safe_bytes_from_tensor()
        │
        ├── array
        └── raw
             │
             ▼
weights.py
        │
        ├── bias_raw
        └── bias_tensor_off
             │
             ▼
memory.py
        │
        └── BIAS_BASE
             │
             ▼
LayerParam
        │
        └── bias_ptr
             │
             ▼
WAT/WASM
```

---

# 144. Difference from `tensor_mapping.py`

`tensor_mapping.py` handles activation tensors:

```text
tensor → SLOT
```

`weights.py` handles constant tensors:

```text
tensor → OFFSET
```

This distinction is fundamental.

---

# 145. Comparison

| Tensor type | Structure |
| -------------- | ------------------- |
| Activation | `tensor_to_slot` |
| Weight | `weight_tensor_off` |
| Bias | `bias_tensor_off` |

All will later be converted into memory addresses.

---

# 146. Complete convolution example

Suppose:

```text
CONV_2D

input[0] = tensor 100
input[1] = tensor 101
input[2] = tensor 102
```

After previous stages:

```text
tensor 100 → SLOT1
```

After `weights.py`:

```text
tensor 101 → weight offset 5000
tensor 102 → bias offset 256
```

After layout:

```text
SLOT1_BASE = 700000

WEIGHTS_BASE = 2048

BIAS_BASE = 386656
```

The pointers become:

```text
in_ptr =
700000
```

```text
wptr =
2048 + 5000
=
7048
```

```text
bias_ptr =
386656 + 256
=
386912
```

This information will ultimately be serialized for the runtime.

---

# 147. Why do weights not need slots?

Weights are not produced during inference.

They exist before the first image.

Their lifetime is therefore conceptually:

```text
module start
        ↓
entire inference
        ↓
end
```

It makes no sense to treat them as reusable temporary activations.

---

# 148. Why does bias also not need a slot?

For the same reason.

Bias is constant during execution.

It resides in its permanent region:

```text
BIAS
```

---

# 149. Memory cost

The size of:

```text
weights_raw
```

directly contributes to linear memory consumption.

This stage therefore provides key information for later calculation of:

```text
MEM_END
MEM_PAGES
```

---

# 150. Extracted data versus calculated data

The bytes of:

```text
weights_raw
bias_raw
```

come from the model.

The offsets:

```text
weight_tensor_off
bias_tensor_off
```

are built by the extractor.

We therefore have:

```text
extracted data
    ↓
raw bytes
```

and:

```text
derived data
    ↓
offsets
```

---

# 151. What this module deliberately does not do

`weights.py` does not:

```text
calculate scales
calculate zero points
calculate multiplier
calculate shift
calculate Q6

calculate WEIGHTS_BASE
calculate BIAS_BASE

calculate slots
calculate final pointers

generate LayerParam
generate WAT
```

---

# 152. Exact responsibility

It only answers:

```text
which bytes belong to weights?

which bytes belong to biases?

at which internal offset was each tensor placed?
```

---

# 153. Current validation

The module has some implicit checks.

For weights:

```text
supported operation
at least 2 inputs
retrievable buffer
tensor not yet stored
```

For biases:

```text
at least 3 inputs
retrievable buffer
one-dimensional array
tensor not yet stored
```

---

# 154. What is not validated here?

The module does not explicitly check:

```text
whether the weight dtype exactly matches runtime expectations

whether the bias dtype exactly matches expectations

whether the bias element count matches the channel count

whether the weight shape is semantically compatible with the operation
```

It records:

```text
shape
dtype
```

for inspection, but does not enforce these properties here.

---

# 155. Why does this matter?

If the extractor accepts more varied models in the future, these expectations may warrant formal validation.

Currently, the focus is on correctly extracting the model used by the project.

---

# 156. The `weight_tensor` and `bias_tensor` variables

The code has:

```python
weight_tensor
```

and:

```python
bias_tensor
```

but they are not used after the call.

This is not a functional error.

The function:

```python
safe_bytes_from_tensor()
```

always returns three components:

```text
tensor
array
raw
```

and `weights.py` uses only the last two.

---

# 157. Could they be replaced with `_`?

Technically, one could write:

```python
(
    _,
    weight_array,
    weight_raw,
) = safe_bytes_from_tensor(...)
```

The current implementation retains the explicit names.

For documentation purposes, it is enough to note that:

```text
the Tensor object is retrieved,
but does not participate in this function's calculations.
```

---

# 158. Deterministic order

Because scanning follows:

```python
range(
    subgraph.OperatorsLength()
)
```

and the first occurrence determines the offset, running on the same model produces the same blob order, provided the model structure stays the same.

This contributes to artifact reproducibility.

---

# 159. Avoiding duplication

Deduplication is based on:

```text
tensor_id
```

rather than byte comparison.

Two different tensors with identical contents are therefore still stored separately.

---

# 160. Example

If:

```text
tensor 10 = [1,2,3]

tensor 20 = [1,2,3]
```

but the IDs differ:

```text
10 ≠ 20
```

so both are stored.

The module does not deduplicate by contents.

---

# 161. Why is this decision simple and safe?

From the model's structural perspective:

```text
tensor 10
```

and:

```text
tensor 20
```

are distinct objects.

Sharing memory merely because bytes match would introduce an additional optimization the current code does not attempt.

---

# 162. The report as an auditing mechanism

The fields:

```text
op_index
op_type
tensor_id
offset
nbytes
shape
dtype
```

allow checking almost every decision made by this module without printing thousands of bytes.

---

# 163. Audit example

Given:

```text
op=15 CONV_2D tensor=89 offset=15200 bytes=2048 shape=[...] dtype=int8
```

we can check:

```text
which operation uses the weight?

which tensor was it?

where was it placed?

how much space does it occupy?

which shape was read?

how were its bytes interpreted?
```

---

# 164. Why not print weight values?

A network may have hundreds of thousands of parameters.

Generating:

```text
weight[0] = ...
weight[1] = ...
weight[2] = ...
```

would make the report enormous and less useful.

The report therefore works at tensor level.

---

# 165. Blobs and efficiency

Storing parameters in contiguous blocks also simplifies WAT generation.

Instead of generating a segment for each weight tensor:

```text
data W0
data W1
data W2
...
```

the generator can insert a single block:

```text
WEIGHTS
```

and use internal offsets.

---

# 166. Final conceptual representation

```text
                      TFLite
                         │
                         ▼
               supported operators
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
       input[1]                    input[2]
        weights                      bias
           │                           │
           ▼                           ▼
safe_bytes_from_tensor()   safe_bytes_from_tensor()
           │                           │
           ▼                           ▼
      weight_raw                bias_raw_tensor
           │                           │
           ▼                           ▼
     weights_raw                  bias_raw
           │                           │
           ▼                           ▼
 weight_tensor_off            bias_tensor_off
           │                           │
           └─────────────┬─────────────┘
                         ▼
                 memory layout
```

---

# 167. Role in the complete pipeline

```text
┌────────────────────────────┐
│       TFLite Model         │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│       weights.py           │
│                            │
│ weights_raw                │
│ bias_raw                   │
│ weight_tensor_off          │
│ bias_tensor_off            │
└─────────────┬──────────────┘
              │
       ┌──────┴───────┐
       │              │
       ▼              ▼
quantization.py    memory.py
       │              │
       │              ├── WEIGHTS_BASE
       │              └── BIAS_BASE
       │              │
       └──────┬───────┘
              ▼
       layer_params.py
              │
              ├── wptr
              └── bias_ptr
              │
              ▼
        params_blob.py
              │
              ▼
       wat_generator.py
```

---

# 168. Summary

`weights.py` transforms trainable parameters distributed across multiple TFLite buffers into a representation suitable for the project's runtime.

The main transformation is:

```text
TFLite

weight tensor
weight tensor
weight tensor
bias tensor
bias tensor

        ↓

runtime

weights_raw
[W0][W1][W2]...

bias_raw
[B0][B1][B2]...
```

Each tensor receives an offset:

```text
tensor_id → offset
```

which will later be combined with a memory base:

```text
address =
base + offset
```

This separation lets the module focus exclusively on **parameter contents and internal organization**, while `memory.py` decides where blocks are placed and `layer_params.py` converts offsets into pointers consumed by WebAssembly.

The module also preserves traceability through records containing:

```text
operation
tensor
offset
size
shape
dtype
```

without mixing this metadata with the binary contents actually used during inference.

After `weights.py`, the pipeline has more than TFLite buffer references: it has two contiguous binary artifacts directly usable by the runtime:

```text
weights_raw
bias_raw
```

along with the maps needed to locate each tensor within them.
