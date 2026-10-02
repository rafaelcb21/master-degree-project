[English](11-layer-params.md) | [Português (Brasil)](11-layer-params.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body has been preserved in the Portuguese edition.

# 11 — Building LayerParams (`layer_params.py`)

## 1. Module purpose

`extractor/layer_params.py` converts all previously extracted and calculated information into a uniform representation of operations executed by the WebAssembly runtime.

At this point, information is distributed across several modules:

```text
graph.py
    ↓
graph structure

slots.py
    ↓
logical slot allocation

tensor_mapping.py
    ↓
tensor → slot

weights.py
    ↓
weight and bias offsets

quantization.py
    ↓
multipliers, shifts, and Q6

memory.py
    ↓
physical region addresses

operator_options.py
    ↓
stride, dilation, padding,
activation and depth multiplier
```

`layer_params.py` brings all of this together.

The result is a list:

```text
layer_params
```

in which each element describes one runtime operation.

Conceptually:

```text
TFLite + extraction + planning
              │
              ▼
        layer_params.py
              │
              ▼
       logical LayerParam
              │
              ▼
        params_blob.py
              │
              ▼
       binary LayerParam[]
              │
              ▼
             WASM
```

---

# 2. Architectural role

This module is the boundary between:

```text
TFLite model
+
extractor structures
```

and:

```text
the format expected by the runtime
```

Before it, data still have specific meanings:

```text
tensor_id
op_index
weight_offset
mul_offset
logical slot
SAME padding
scale
zero point
```

After it, this information occupies standardized fields:

```text
op_type
act
flags

in_slot
out_slot

in_h
in_w
cin
cout

kh
kw

stride_h
stride_w

dil_h
dil_w

pad_t
pad_b
pad_l
pad_r

w_off
b_off

mul_off
shift_off
q6_off

zx
zw
zy

out_h
out_w
```

These fields will later be serialized into a fixed binary structure.

---

# 3. Imports

The module starts with:

```python
import math
import struct
```

`math` is mainly used for `SOFTMAX`-specific calculations.

`struct` determines the size of the binary `LayerParam` structure.

TFLite helpers are also imported:

```python
from extractor.tflite_utils import (
    op_name,
    scale_scalar,
    zp_scalar,
    tensor_shape_list,
)
```

These helpers provide:

```text
op_name()
    → operation name

scale_scalar()
    → tensor scale

zp_scalar()
    → tensor zero point

tensor_shape_list()
    → Python shape
```

The module also receives quantization calculations:

```python
from extractor.quantization import (
    quantize_multiplier,
    compute_add_quantization_params,
)
```

and operator options:

```python
from extractor.operator_options import (
    ACT_NONE,
    ACT_RELU6,
    parse_add_options,
    parse_conv2d_options,
    parse_dwconv2d_options,
    parse_fc_options,
    same_padding,
)
```

This composition shows that `layer_params.py` should not repeat calculations belonging to specialized modules.

---

# 4. `LP_FMT`

The future binary structure is defined by:

```python
LP_FMT = "<" + "i" * 29
```

This means:

```text
<
    little-endian

i
    signed 32-bit integer

29
    field count
```

The structure therefore has:

```text
29 × 4 bytes
=
116 bytes
```

---

# 5. `LP_SIZE`

The size is calculated automatically:

```python
LP_SIZE = struct.calcsize(
    LP_FMT
)
```

Resulting in:

```text
LP_SIZE = 116
```

This value is not written manually.

If the format changes, `struct.calcsize()` remains the source of truth for its size.

---

# 6. Why a fixed structure?

The runtime must iterate quickly over layers.

A constant-sized structure allows calculating:

```text
address of layer i
=
PARAMS_BASE
+
i × LP_SIZE
```

With:

```text
LP_SIZE = 116
```

we have:

```text
layer 0 → PARAMS_BASE

layer 1 → PARAMS_BASE + 116

layer 2 → PARAMS_BASE + 232

layer 3 → PARAMS_BASE + 348
...
```

---

# 7. Internal operation types

The module defines:

```python
OP_CONV = 1
OP_DW = 2
OP_FC = 3
OP_ADD = 4
OP_MEAN = 5
OP_SOFTMAX = 6
OP_QUANTIZE = 7
OP_RGB565_TO_RGB888 = 8
```

These codes form the protocol between:

```text
extractor
```

and:

```text
WAT runtime
```

The runtime does not need to manipulate strings such as:

```text
"CONV_2D"
```

It receives:

```text
1
```

and executes the corresponding kernel.

---

# 8. Operation mapping

| Code | Operation |
| -----: | ------------------- |
|    `1` | `CONV_2D`           |
|    `2` | `DEPTHWISE_CONV_2D` |
|    `3` | `FULLY_CONNECTED`   |
|    `4` | `ADD`               |
|    `5` | `MEAN`              |
|    `6` | `SOFTMAX`           |
|    `7` | `QUANTIZE`          |
|    `8` | `RGB565_TO_RGB888`  |

The eighth operation does not originate in the TFLite model.

It is created by the extractor itself.

---

# 9. Flags

The following are defined:

```python
FLAG_PADDING_SAME = 1 << 0
FLAG_HAS_Q6 = 1 << 1
```

Therefore:

```text
FLAG_PADDING_SAME = 1

FLAG_HAS_Q6 = 2
```

In binary representation:

```text
bit 0 → SAME padding

bit 1 → Q6 presence/use
```

---

# 10. Combination example

A convolution with:

```text
SAME padding
+
ReLU6
```

may have:

```text
flags = 1 | 2
```

resulting in:

```text
flags = 3
```

In binary:

```text
00000011
```

---

# 11. Reusing bit 0 for `QUANTIZE`

There is an important decision:

```python
FLAG_QUANTIZE_INPUT_INT8 = (
    FLAG_PADDING_SAME
)
```

In other words:

```text
FLAG_QUANTIZE_INPUT_INT8 = 1
```

and:

```text
FLAG_PADDING_SAME = 1
```

use exactly the same bit.

---

# 12. This does not imply the same semantics

The meaning depends on:

```text
op_type
```

For a convolution:

```text
bit 0 = 1
    ↓
SAME padding
```

For `QUANTIZE`:

```text
bit 0 = 1
    ↓
input is int8
```

Therefore:

```text
flags
```

must not be interpreted in isolation.

The correct interpretation is:

```text
(op_type, flags)
```

---

# 13. TFLite types used

The module defines:

```python
TFLITE_UINT8 = 3
TFLITE_INT8 = 9
```

These codes determine the meaning of the `QUANTIZE` input.

---

# 14. RGB layer constants

There are also:

```python
FORMAT_FLAG_ADDR = 0
FORMAT_RGB565 = 65
```

and:

```python
INPUT_FORMAT_SLOT = 0
RGB888_SLOT = 1
```

These values belong to the synthetic input layer.

---

# 15. The `tensor_hwc()` function

The first helper function is:

```python
def tensor_hwc(tensor):
```

It converts a tensor's shape into:

```text
complete shape
height
width
channels
```

---

# 16. Original shape

First:

```python
shape = tensor_shape_list(
    tensor
)
```

Example:

```text
[1, 128, 128, 3]
```

---

# 17. Height

The code uses:

```text
shape[1]
```

when there are at least three dimensions.

Thus:

```text
[1, 128, 128, 3]
    ↑
    height
```

produces:

```text
height = 128
```

---

# 18. Width

When possible:

```text
width = shape[2]
```

Example:

```text
[1, 128, 128, 3]
         ↑
       width
```

---

# 19. Channels

For 4D tensors:

```text
channels = shape[3]
```

---

# 20. 2D tensors

There is special handling:

```python
shape[1]
if len(shape) == 2
```

Thus, a tensor such as:

```text
[1, 1000]
```

results in:

```text
height = 1
width = 1
channels = 1000
```

This representation is useful for `FULLY_CONNECTED`.

---

# 21. Fallback

When an appropriate dimension is absent:

```text
height = 1

width = 1

channels = 1
```

The function normalizes different shapes into a common HWC representation.

---

# 22. First special issue: runtime slots

Up to `tensor_mapping.py`, the model input was logically associated with:

```text
SLOT0
```

The runtime now introduces a new stage before the first TFLite operator:

```text
RGB565_TO_RGB888
```

This requires reorganizing slots.

---

# 23. Before the synthetic layer

Conceptually:

```text
TFLite input
    ↓
SLOT0
    ↓
QUANTIZE / first operation
```

---

# 24. After the synthetic layer

The runtime now uses:

```text
received data
    ↓
SLOT0
    ↓
RGB565_TO_RGB888
    ↓
SLOT1
    ↓
TFLite model
```

The former logical SLOT0 output must therefore shift.

---

# 25. `build_runtime_tensor_mapping()`

This transformation is performed by:

```python
def build_runtime_tensor_mapping(
    subgraph,
    *,
    graph_inputs,
    slot_allocation,
    label_to_op_idx,
    num_slots,
    slot_shift,
):
```

The function creates a new:

```text
tensor → slot
```

specific to the runtime.

---

# 26. Original graph input

For each:

```python
tensor_id in graph_inputs
```

the code does:

```python
tensor_to_slot[
    tensor_id
] = slot_shift
```

With the current shift:

```text
slot_shift = 1
```

this means:

```text
TFLite input
    ↓
runtime SLOT1
```

---

# 27. Why SLOT1?

Because:

```text
SLOT0
```

now represents the input region used by the synthetic layer.

After conversion:

```text
SLOT1
```

contains the RGB888 data expected by the rest of the network.

---

# 28. Remapping actual outputs

For each original allocation:

```python
original_slot = (
    alloc["output_slot"]
)
```

the following is calculated:

```python
runtime_slot = (
    original_slot
    + slot_shift
) % num_slots
```

---

# 29. Example with three slots

With:

```text
num_slots = 3
slot_shift = 1
```

we have:

```text
original SLOT0
    ↓
runtime SLOT1

original SLOT1
    ↓
runtime SLOT2

original SLOT2
    ↓
runtime SLOT0
```

---

# 30. Circular rotation

Therefore:

```text
0 → 1

1 → 2

2 → 0
```

We are not adding a fourth slot.

We are rotating the three existing slots.

---

# 31. Why use modulo `%`?

For:

```text
original_slot = 2
```

we would have:

```text
2 + 1 = 3
```

But:

```text
3 % 3 = 0
```

returns the rotation to its starting point.

---

# 32. Recording the conversion

Each output receives:

```python
{
    "tensor_id": ...,
    "layer": ...,
    "original_slot": ...,
    "runtime_slot": ...,
}
```

This allows generating a report such as:

```text
tensor=42
layer=L10
slot_original=2
slot_runtime=0
```

---

# 33. Runtime mapping result

The function returns:

```python
{
    "tensor_to_slot": ...,
    "records": ...,
    "slot_shift": ...,
}
```

From this point onward, `layer_params.py` must use:

```text
runtime_tensor_to_slot
```

rather than the previous logical mapping.

Rotation explicitly accommodates the synthetic input conversion.

---

# 34. Planning the `LayerParam[]` region

The function:

```python
calculate_layer_memory_layout()
```

calculates the space occupied by layer structures and where slots start.

---

# 35. Total layer count

The following is calculated:

```python
num_layers = (
    real_layer_count
    + synthetic_layer_count
)
```

---

# 36. Example

If the model has:

```text
67 actual operations in use
```

and we add:

```text
1 synthetic layer
```

we get:

```text
num_layers = 68
```

---

# 37. Raw `PARAMS` size

With:

```text
LP_SIZE = 116
```

the raw size would be:

```text
68 × 116
=
7888 bytes
```

---

# 38. Aligning `params_bytes`

The code uses:

```text
ceil(
    num_layers × LP_SIZE
    / alignment
)
× alignment
```

producing an aligned size.

---

# 39. Why align the entire block?

The next region:

```text
SLOT0
```

must start at a boundary consistent with the memory policy.

---

# 40. First slot base

Then:

```text
SLOT0_BASE
=
align_up(
    PARAMS_BASE
    +
    params_bytes
)
```

The implementation applies the formula directly instead of calling `align_up()`.

---

# 41. Subsequent slots

For each subsequent slot:

```text
next_base
=
previous_slot_base
+
slot_bytes
```

and then:

```text
next_base
=
align_up(next_base)
```

---

# 42. Result

The function returns:

```python
{
    "num_layers": ...,
    "params_bytes": ...,
    "slot_bases": ...,
}
```

The layout at this stage is therefore:

```text
PARAMS_BASE
    │
    ├── LayerParam 0
    ├── LayerParam 1
    ├── LayerParam 2
    ├── ...
    │
    ▼
end of PARAMS
    │
    ▼
alignment
    │
    ▼
SLOT0
    │
    ▼
SLOT1
    │
    ▼
SLOT2
```

---

# 43. Synthetic `RGB565_TO_RGB888` layer

Before actual operations, it creates:

```python
build_rgb565_layer()
```

This layer does not exist in TFLite.

---

# 44. Purpose

It creates a runtime operation:

```text
RGB565_TO_RGB888
```

before the network.

The layer is identified by:

```python
"op_index": -1
```

indicating that:

```text
there is no corresponding TFLite operator
```

---

# 45. Internal type

```python
"op_type": OP_RGB565_TO_RGB888
```

or:

```text
op_type = 8
```

---

# 46. Slots

The layer uses:

```text
input = SLOT0
output = SLOT1
```

through:

```python
"in_slot": INPUT_FORMAT_SLOT
```

and:

```python
"out_slot": RGB888_SLOT
```

---

# 47. Geometry

Height, width, and channels come from the original model input tensor:

```text
in_h
in_w
input_channels
```

---

# 48. Output shape

Conversion does not change:

```text
height
width
channel count
```

Thus:

```text
out_h = in_h

out_w = in_w

cout = cin
```

---

# 49. The `kh` field

The layer uses:

```python
"kh": FORMAT_RGB565
```

with:

```text
FORMAT_RGB565 = 65
```

Therefore:

```text
kh = 65
```

is a special value for this operation.

It does not represent kernel height.

---

# 50. No weights

The layer has:

```text
w_off = 0

has_bias = False

has_mulq6 = False
```

because this is a format conversion implemented directly by the runtime.

---

# 51. Input pointer

The helper field:

```python
"input_ptrs"
```

contains:

```text
slot_bases[0]
```

that is, SLOT0's physical address.

The synthetic layer is explicitly inserted before any actual model operator.

---

# 52. Specialized builders

After the synthetic layer, each operation type has an appropriate builder.

```text
QUANTIZE
    ↓
_build_quantize_params()

ADD
    ↓
_build_add_params()

MEAN
    ↓
_build_mean_params()

SOFTMAX
    ↓
_build_softmax_params()

CONV / DW / FC
    ↓
_build_weighted_params()
```

This avoids one enormous function full of conditionals.

---

# 53. `_build_quantize_params()`

This function builds the representation of:

```text
QUANTIZE
```

---

# 54. Input validation

The operation requires at least one input.

If none exists:

```text
RuntimeError
```

is raised.

---

# 55. Input and output quantization

The following are obtained:

```text
scale_in
zp_in

scale_out
zp_out
```

---

# 56. Scale relationship

Requantization uses:

```text
ratio =
scale_in
─────────
scale_out
```

---

# 57. Integer multiplier

Then:

```text
ratio
    ↓
quantize_multiplier()
    ↓
multiplier
shift
```

---

# 58. Validating `scale_out`

If:

```text
scale_out = 0
```

the function stops construction.

This prevents division by zero.

---

# 59. Input slot

The function requires:

```text
input_tensor_id
```

to be present in:

```text
tensor_to_slot
```

Otherwise, it raises:

```text
RuntimeError
```

---

# 60. Pointer

Then:

```text
input_ptr =
slot_bases[in_slot]
```

Thus:

```text
tensor
 ↓
runtime slot
 ↓
physical slot base
```

---

# 61. Input type

The code inspects:

```python
input_tensor.Type()
```

---

# 62. INT8 input

If:

```text
input_dtype = TFLITE_INT8
```

the following is set:

```text
flags =
FLAG_QUANTIZE_INPUT_INT8
```

or:

```text
flags = 1
```

---

# 63. UINT8 input

If:

```text
input_dtype = TFLITE_UINT8
```

we have:

```text
flags = 0
```

---

# 64. Other types

Unknown types also receive:

```text
flags = 0
```

but are recorded in the dictionary:

```text
quant_params
```

such as:

```text
unknown(code)
```

---

# 65. `QUANTIZE` runs in place

The function explicitly resets:

```python
out_slot = in_slot
```

Therefore:

```text
input
    ↓
SLOTn
    ↓
QUANTIZE
    ↓
same SLOTn
```

This preserves the decision already present in `slots.py`.

---

# 66. Reusing fields in `QUANTIZE`

For this operation:

```text
kh = multiplier

kw = shift

pad_t = input_ptr

zx = input zero point

zy = output zero point
```

The fields no longer have their traditional geometric meanings.

---

# 67. Special QUANTIZE structure

```text
LayerParam
┌────────────────────────┐
│ op_type = 7            │
│ flags = input type     │
│                        │
│ kh = multiplier        │
│ kw = shift             │
│                        │
│ pad_t = input_ptr      │
│                        │
│ zx = zp_in             │
│ zy = zp_out            │
└────────────────────────┘
```

The function also retains a detailed `quant_params` dictionary for reporting and diagnostics.

---

# 68. `_build_add_params()`

`ADD` is more complex because it has two dynamic inputs.

---

# 69. Inputs

The following are loaded:

```text
input_tensor_a

input_tensor_b

output_tensor
```

---

# 70. Quantization

For A:

```text
scale_a
zp_a
```

For B:

```text
scale_b
zp_b
```

For the output:

```text
scale_y
zp_y
```

---

# 71. ADD parameters

The function calls:

```python
compute_add_quantization_params(
    scale_a,
    scale_b,
    scale_y,
)
```

receiving:

```text
mul_a
shift_a

mul_b
shift_b

output_mul
output_shift

scale_common
```

---

# 72. Fused activation

It is obtained through:

```python
parse_add_options(
    op
)
```

An ADD can therefore carry:

```text
NONE
RELU
RELU6
```

as supported by the parser.

---

# 73. Two input slots

The module requires both tensors to be mapped:

```text
tensor A → slot A

tensor B → slot B
```

Then:

```text
input_ptr_a =
slot_bases[slot_a]

input_ptr_b =
slot_bases[slot_b]
```

---

# 74. Reusing fields in ADD

`ADD` uses:

```text
kh       = multiplier A

kw       = shift A

stride_h = multiplier B

stride_w = shift B

dil_h    = output multiplier

dil_w    = output shift
```

---

# 75. ADD pointers

Padding fields are reused:

```text
pad_t = input A pointer

pad_b = input B pointer
```

---

# 76. ADD zero points

Also:

```text
pad_l = zero point A

pad_r = zero point B
```

Also:

```text
zx = zp_a

zw = zp_b

zy = zp_y
```

---

# 77. Why duplicate zero points?

`pad_l` and `pad_r` belong to the special protocol used by the ADD kernel.

Whereas:

```text
zx
zw
zy
```

retain the standardized representation of the operation's zero points.

---

# 78. ADD diagram

```text
tensor A
   │
   ▼
SLOT A ────────────────┐
                       │
                       ▼
                    ADD
                       │
tensor B               │
   │                   │
   ▼                   │
SLOT B ────────────────┘
                       │
                       ▼
                  output SLOT
```

`LayerParam` must therefore carry two actual input pointers.

---

# 79. Special ADD fields

```text
kh       → mul0
kw       → shift0

stride_h → mul1
stride_w → shift1

dil_h    → out_mul
dil_w    → out_shift

pad_t    → input_ptr A
pad_b    → input_ptr B

pad_l    → zero point A
pad_r    → zero point B
```

This mapping appears in both the builder and the report generated by the module.

---

# 80. `_build_mean_params()`

The operation:

```text
MEAN
```

also receives a specialized representation.

---

# 81. Quantization

The function obtains:

```text
scale_x
zp_x

scale_y
zp_y
```

---

# 82. Relationship

The following is calculated:

```text
ratio =
scale_x / scale_y
```

and then:

```text
multiplier
shift
```

---

# 83. `spatial_size`

The function calculates:

```python
spatial_size = (
    in_h
    * in_w
)
```

---

# 84. Example

For:

```text
input =
7 × 7 × 1280
```

we have:

```text
spatial_size =
7 × 7
=
49
```

MEAN needs this value to compute the spatial average.

---

# 85. Special fields

The mapping is:

```text
kh = multiplier

kw = shift

stride_h = spatial_size

pad_t = input_ptr
```

---

# 86. Other parameters

There are no:

```text
weights
biases
external MUL
external SHIFT
external Q6
```

for this representation.

Therefore:

```text
has_bias = False

has_mulq6 = False
```

---

# 87. Zero points

The following are recorded:

```text
zx = zp_x

zy = zp_y
```

---

# 88. Representation

```text
LayerParam MEAN

kh        → multiplier
kw        → shift
stride_h  → H × W
pad_t     → input pointer

zx        → input zero point
zy        → output zero point
```

---

# 89. `_build_softmax_params()`

`SOFTMAX` has even more specific preparation.

---

# 90. Input and output data

The following are obtained:

```text
scale_x
zp_x

scale_y
zp_y
```

---

# 91. Constants used

The implementation defines:

```text
beta = 1.0

integer_bits = 5
```

---

# 92. `input_left_shift`

It is calculated from:

```text
integer_bits

127 × scale_x
```

using:

```text
log2
floor
```

and bounded below by zero.

---

# 93. `internal_scale`

The following is also calculated:

```text
internal_scale =
1 / 2^integer_bits
```

With:

```text
integer_bits = 5
```

we have:

```text
internal_scale =
1 / 32
=
0.03125
```

This value is retained in:

```text
quant_params
```

for the report.

---

# 94. Beta multiplier

The calculation uses:

```text
real_multiplier =
beta × scale_x
```

Then:

```text
real_multiplier
    ↓
quantize_multiplier()
    ↓
input_beta_mul
input_beta_left_shift
```

---

# 95. `diff_min`

The implementation fixes:

```text
diff_min = -128
```

---

# 96. Slot and pointer

As with other operations:

```text
input_tensor
    ↓
runtime tensor mapping
    ↓
in_slot
    ↓
slot_bases[in_slot]
    ↓
input_ptr
```

---

# 97. Relationship with `mul_q6_off`

`SOFTMAX` checks:

```python
op_idx in mul_q6_off
```

If a record exists:

```text
mul_off
shift_off
```

are retained.

`q6_off` remains:

```text
0
```

---

# 98. Correct SOFTMAX mapping

In the current implementation:

```text
kh
=
input_beta_mul
```

```text
kw
=
input_beta_left_shift
```

```text
stride_h
=
diff_min
```

```text
stride_w
=
input_left_shift
```

```text
pad_t
=
input_ptr
```

This detail is especially important: **`stride_w` stores `input_left_shift`**.

It does not store `integer_bits`.

The current code explicitly documents this behavior.

---

# 99. Why emphasize this?

The names:

```text
kh
kw
stride_h
stride_w
```

do not represent geometry for `SOFTMAX`.

They are reused to carry kernel-specific parameters.

Thus, one should not interpret:

```text
stride_w
```

as horizontal stride when:

```text
op_type = OP_SOFTMAX
```

---

# 100. SOFTMAX zero points

The following are retained:

```text
zx = zp_x

zy = zp_y
```

and:

```text
zw = 0
```

because there is no weight tensor.

---

# 101. Quantization metadata

SOFTMAX's `quant_params` records:

```text
sX
sY

zX
zY

beta

integer_bits

internal_scale

real_multiplier

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

This provides full traceability of the operation's mathematical preparation.

---

# 102. `_build_weighted_params()`

This function groups three structurally related operations:

```text
CONV_2D

DEPTHWISE_CONV_2D

FULLY_CONNECTED
```

All have:

```text
activation input
weights
optional bias
```

and use external requantization tables.

---

# 103. Minimum structure

The operation must have:

```text
input[0]
    → activation

input[1]
    → weights
```

If there is:

```text
input[2]
```

it is treated as:

```text
biases
```

---

# 104. Common data

First, the following are retrieved:

```text
input_tensor

weight_tensor

output_tensor

bias_id
```

Along with:

```text
input HWC

output shape

weight shape
```

---

# 105. Initial defaults

The function starts with:

```text
stride = 1

dilation = 1

padding = 0

activation = NONE

flags = 0

depth_mult = 1
```

Each operator type then changes only what is needed.

---

# 106. `CONV_2D` path

For:

```text
CONV_2D
```

the following is set:

```text
op_type = OP_CONV
```

---

# 107. CONV `cout`

Preferably:

```text
cout =
weight_shape[0]
```

---

# 108. CONV kernel

The expected structure provides:

```text
kernel_h =
weight_shape[1]

kernel_w =
weight_shape[2]
```

---

# 109. CONV options

Then:

```python
parse_conv2d_options(
    op
)
```

provides:

```text
stride_h
stride_w

dil_h
dil_w

padding_kind

activation
```

---

# 110. `SAME` flag

If:

```text
padding_kind == 0
```

the following executes:

```text
flags |= FLAG_PADDING_SAME
```

---

# 111. `DEPTHWISE_CONV_2D` path

For depthwise:

```text
op_type = OP_DW
```

---

# 112. Depthwise kernel

The following are also used:

```text
weight_shape[1]
weight_shape[2]
```

such as:

```text
kernel_h
kernel_w
```

---

# 113. `cout`

For depthwise:

```text
cout =
weight_shape[3]
```

when available.

---

# 114. Specific options

`parse_dwconv2d_options()` also provides:

```text
depth_mult
```

in addition to stride, dilation, padding, and activation.

---

# 115. `FULLY_CONNECTED` path

For:

```text
FULLY_CONNECTED
```

the following is used:

```text
op_type = OP_FC
```

---

# 116. Output count

Preferably:

```text
cout =
weight_shape[0]
```

---

# 117. Logical FC kernel

The code sets:

```text
kernel_h = 1

kernel_w = 1
```

These fields do not describe an actual convolution here.

They are simply consistent values for the uniform structure.

---

# 118. FC options

The only option needed here is:

```text
activation
```

obtained through:

```python
parse_fc_options(
    op
)
```

---

# 119. Unexpected operation

If `_build_weighted_params()` receives a type other than these three:

```text
RuntimeError
```

is raised.

This check prevents using the generic builder for an incompatible operation.

---

# 120. ReLU6 flag

After identifying the operation:

```python
if activation == ACT_RELU6:
    flags |= FLAG_HAS_Q6
```

Thus:

```text
ReLU6
    ↓
HAS_Q6 bit
```

---

# 121. Calculating SAME

If:

```text
flags & FLAG_PADDING_SAME
```

is active:

```python
same_padding(...)
```

is called.

---

# 122. Produced values

The following are calculated:

```text
pad_t
pad_b
pad_l
pad_r

out_h
out_w
```

---

# 123. Zero points

Next, it extracts:

```text
zp_x
    → input

zp_w
    → weights

zp_y
    → output
```

---

# 124. Weight offsets

The weight tensor is:

```text
input_ids[1]
```

and:

```python
weight_tensor_off.get(
    weight_tensor_id,
    0,
)
```

provides the relative offset within the weight blob.

---

# 125. Important note about the fallback

If there is no entry in:

```text
weight_tensor_off
```

the value will be:

```text
0
```

There is no boolean here:

```text
has_weight
```

equivalent to `has_bias`.

The previous stage must therefore have correctly extracted weights for supported operations.

---

# 126. Bias

The code calculates:

```text
has_bias =
bias_id >= 0
and
bias_id exists in bias_tensor_off
```

---

# 127. Bias offset

Even when there is no bias:

```text
bias_offset = 0
```

But:

```text
has_bias = False
```

allows serialization to distinguish:

```text
valid zero offset
```

from:

```text
no bias
```

---

# 128. MUL, SHIFT, and Q6

The function checks:

```text
op_idx in mul_q6_off
```

---

# 129. If present

The following are retrieved:

```text
mul_offset

shift_offset

q6_offset
```

---

# 130. If absent

All are set to:

```text
0
```

and:

```text
has_mulq6 = False
```

---

# 131. Input slot

The activation tensor:

```text
input_ids[0]
```

must exist in:

```text
runtime_tensor_to_slot
```

Otherwise the extractor fails immediately.

---

# 132. Pointer

Then:

```text
input_ptr =
slot_bases[in_slot]
```

This pointer is still retained only as helper metadata in:

```text
input_ptrs
```

Final serialization calculates the required pointers according to the structure's convention.

---

# 133. Resulting CONV/DW/FC structure

The builder returns fields with their natural meanings:

```text
kh
kw
    → kernel dimensions

stride_h
stride_w
    → stride

dil_h
dil_w
    → dilation

pad_t
pad_b
pad_l
pad_r
    → padding

w_off
    → weight offset

b_off
    → bias offset

mul_off
shift_off
q6_off
    → quantization table offsets

zx
zw
zy
    → zero points
```

In this operation group, unlike the special builders, fields mostly retain meanings consistent with their original names.

---

# 134. `depth_mult`

Only:

```text
DEPTHWISE_CONV_2D
```

retains the `depth_mult` read from TFLite.

For the others:

```text
depth_mult = 1
```

---

# 135. Uniform structure and polymorphism through `op_type`

The main `LayerParam` design decision is to use a fixed structure for very different operations.

Thus:

```text
op_type
```

defines how to interpret the other fields.

---

# 136. Example

For:

```text
op_type = OP_CONV
```

we have:

```text
kh = kernel height
```

But for:

```text
op_type = OP_ADD
```

we have:

```text
kh = input A multiplier
```

And for:

```text
op_type = OP_SOFTMAX
```

we have:

```text
kh = input_beta_mul
```

---

# 137. Therefore

The correct meaning of a field is:

```text
meaning =
function(
    op_type,
    field
)
```

rather than merely:

```text
meaning =
field name
```

This is a fundamental property of the protocol.

---

# 138. Main overloaded fields

| Field | CONV/DW/FC | ADD | MEAN | SOFTMAX | QUANTIZE |
| ---------- | -------------- | ------------ | ------------ | ---------------- | ---------- |
| `kh`       | kernel H       | mul A        | multiplier   | beta mul         | multiplier |
| `kw`       | kernel W       | shift A      | shift        | beta shift       | shift      |
| `stride_h` | stride H       | mul B        | spatial size | diff_min         | 0          |
| `stride_w` | stride W       | shift B      | 1            | input_left_shift | 0          |
| `dil_h`    | dilation H     | output mul   | 1            | 1                | 1          |
| `dil_w`    | dilation W     | output shift | 1            | 1                | 1          |
| `pad_t`    | top padding    | ptr A        | input ptr    | input ptr        | input ptr  |
| `pad_b`    | bottom padding | ptr B        | 0            | 0                | 0          |
| `pad_l`    | left padding   | zp A         | 0            | 0                | 0          |
| `pad_r`    | right padding  | zp B         | 0            | 0                | 0          |

This table is essential for interpreting a `LayerParam` dump.

---

# 139. `build_layer_params()`

After the individual builders comes the function coordinating complete construction:

```python
def build_layer_params(
    model,
    subgraph,
    *,
    old_idx_to_label,
    runtime_tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
):
```

---

# 140. First element

The function starts with:

```python
layer_params = []
```

and immediately creates:

```text
RGB565_TO_RGB888
```

---

# 141. Consequence

The position:

```text
layer_params[0]
```

does not correspond to the first TFLite operation.

It corresponds to the synthetic layer.

---

# 142. Actual operations

Only afterward are model operations added.

Accepted types are:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
```

---

# 143. Filtering by the useful graph

The loop traverses all TFLite operators, but executes:

```python
if (
    op_idx
    not in old_idx_to_label
):
    continue
```

Only operations belonging to the graph considered by the extractor generate a `LayerParam`.

---

# 144. Second filter

Even among these operations:

```text
op_type_name
```

must be in:

```text
supported_operations
```

Otherwise, the operation is skipped at this stage.

---

# 145. Inputs and outputs

The following are collected:

```text
input_ids
output_ids
```

removing negative IDs.

---

# 146. Operation without output

If:

```text
output_ids = []
```

the operation is skipped.

---

# 147. Output needs a runtime slot

The first output must be in:

```text
runtime_tensor_to_slot
```

Otherwise:

```text
RuntimeError
```

is raised.

---

# 148. Why validate here?

Because every operation needs to know:

```text
where to write its result
```

before its `LayerParam` is constructed.

---

# 149. Finding `out_slot`

```text
output tensor
      ↓
runtime_tensor_to_slot
      ↓
out_slot
```

---

# 150. Dispatch by type

Then:

```text
QUANTIZE
    ↓
_build_quantize_params()

ADD
    ↓
_build_add_params()

MEAN
    ↓
_build_mean_params()

SOFTMAX
    ↓
_build_softmax_params()

other supported types
    ↓
_build_weighted_params()
```

---

# 151. Why is the `else` safe?

Before dispatch there is:

```text
supported_operations
```

and the four special types have already been handled.

The remaining `else` therefore contains only:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

---

# 152. Result

Each builder returns a dictionary:

```python
params
```

which is added through:

```python
layer_params.append(
    params
)
```

---

# 153. Final order

The list has:

```text
position 0
    RGB565_TO_RGB888

position 1
    first actual operation considered

position 2
    second actual operation

...
```

The function explicitly assembles this sequence.

---

# 154. Important note about order

`build_layer_params()` iterates over:

```python
range(
    subgraph.OperatorsLength()
)
```

that is, operator order in the TFLite subgraph.

It does not explicitly iterate over:

```text
graph["order"]
```

Graph membership is determined by:

```text
old_idx_to_label
```

but insertion order follows the original `op_idx`.

For the current model, this is compatible with the execution used.

---

# 155. `layer_params_to_text()`

The last major function reports all created structures.

Its docstring states that this report replaces the old debug comments written directly into WAT.

---

# 156. Why is this an architectural improvement?

Previously we might have:

```text
WAT
 │
 ├── executable code
 ├── debug comments
 ├── layer dump
 ├── parameters
 └── explanations
```

Now:

```text
WAT
    ↓
only required code

reports/
    ↓
diagnostic information
```

---

# 157. Initial report summary

The report shows:

```text
LayerParam size

layer count

params bytes

slot bases

runtime slot shift
```

---

# 158. Shift convention

It also explicitly records:

```text
shift > 0
    → LEFT SHIFT

shift < 0
    → RIGHT SHIFT
```

This is essential for interpreting requantization parameters.

---

# 159. Special field mapping

The report directly documents:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

and how each reuses structure fields.

---

# 160. ADD in the report

It documents:

```text
kh       = mul0

kw       = shift0

stride_h = mul1

stride_w = shift1

dil_h    = out_mul

dil_w    = out_shift

pad_t    = input_ptr[0]

pad_b    = input_ptr[1]

pad_l    = zero point input A

pad_r    = zero point input B
```

---

# 161. MEAN in the report

```text
kh       = multiplier

kw       = shift

stride_h = in_h × in_w

pad_t    = input_ptr
```

---

# 162. SOFTMAX in the report

The current report correctly documents:

```text
kh       = input_beta_mul

kw       = input_beta_left_shift

stride_h = diff_min

stride_w = input_left_shift

pad_t    = input_ptr
```

---

# 163. QUANTIZE in the report

```text
flags =
0 for uint8

1 for int8
```

and:

```text
kh = multiplier

kw = shift

pad_t = input_ptr

zx = input zero point

zy = output zero point
```

---

# 164. RGB565 in the report

The synthetic layer is explained as:

```text
input slot = SLOT0

output slot = SLOT1

kh = 65
```

---

# 165. Runtime mapping

The report also shows the transformation:

```text
slot_original
    ↓
slot_runtime
```

for each produced tensor.

Example:

```text
tensor=45
layer=L12
slot_original=2
slot_runtime=0
```

---

# 166. Full layer dump

A dump of every layer is then produced.

For each layer it displays:

```text
op_index

label

optype

op_type

act

flags

in_slot / out_slot

input_slots

input_ptrs

in_h / in_w

cin / cout

kh / kw

stride_h / stride_w

dil_h / dil_w

padding

out_h / out_w

weight offset

bias offset

mul offset

shift offset

Q6 offset

zero points

depth multiplier
```

---

# 167. `quant_params`

When an operation has:

```python
quant_params
```

the report also prints every calculated parameter.

This occurs, for example, in:

```text
QUANTIZE
ADD
MEAN
SOFTMAX
```

---

# 168. QUANTIZE example

The following may appear:

```text
scale_in
scale_out

zp_in
zp_out

ratio

mul
shift

input_dtype
```

---

# 169. ADD example

```text
sA
sB
sY

zA
zB
zY

mul0
shift0

mul1
shift1

out_mul
out_shift

s_common
```

---

# 170. SOFTMAX example

```text
sX
sY

zX
zY

beta

integer_bits

internal_scale

real_multiplier

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

---

# 171. Runtime structures versus debug structures

Not everything in the returned dictionary is serialized.

Fields such as:

```text
label

op_index

optype

has_bias

has_mulq6

input_slots

input_ptrs

quant_params
```

are mainly extractor metadata.

---

# 172. Serialized fields

The numeric fields corresponding to the 29-`int32` structure are consumed by:

```text
params_blob.py
```

Examples:

```text
op_type

act

flags

in_h
in_w

cin
cout

kh
kw

stride

dilation

padding

offsets

zero points

out_h
out_w
```

---

# 173. Important separation

`layer_params.py` builds:

```text
structured logical representation
```

It does not yet produce:

```text
116 bytes per layer
```

That is the next module's responsibility.

---

# 174. Therefore

```text
layer_params.py
       ↓
Python dict

params_blob.py
       ↓
struct.pack()

WAT
       ↓
data segment
```

---

# 175. Offsets versus pointers

Another important point is that this module still retains:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

as relative offsets.

For example:

```text
w_off = 5000
```

means:

```text
5000 bytes within WEIGHTS
```

rather than an absolute address.

---

# 176. Subsequent conversion

`params_blob.py` will perform:

```text
wptr =
WEIGHTS_BASE
+
w_off
```

Similarly:

```text
bias_ptr =
BIAS_BASE
+
b_off
```

```text
mul_ptr =
MUL_BASE
+
mul_off
```

```text
shift_ptr =
SHIFT_BASE
+
shift_off
```

```text
q6_ptr =
Q6_BASE
+
q6_off
```

---

# 177. Why not calculate everything here?

Because separating:

```text
relative offset
```

from:

```text
serialized absolute pointer
```

keeps each module's responsibility clearer.

---

# 178. Slots are different

For activations, the physical address is already known through:

```text
slot_bases
```

Special builders can therefore store in their metadata:

```text
input_ptrs
```

and reuse addresses in special fields such as:

```text
pad_t
```

---

# 179. Two addressing systems coexist

### Constant parameters

```text
tensor
 ↓
offset
 ↓
base + offset
 ↓
pointer
```

### Activations

```text
tensor
 ↓
runtime slot
 ↓
slot_bases[slot]
 ↓
pointer
```

---

# 180. `layer_params.py` is where they meet

A convolution simultaneously needs:

```text
activation
    → slot

weight
    → offset

biases
    → offset

multiplier
    → offset

zero points
    → integer values
```

This combination occurs in this module.

---

# 181. Complete CONV view

```text
input tensor
    │
    ▼
runtime slot
    │
    ▼
in_slot


weight tensor
    │
    ▼
weight_tensor_off
    │
    ▼
w_off


bias tensor
    │
    ▼
bias_tensor_off
    │
    ▼
b_off


op_index
    │
    ▼
mul_q6_off
    │
    ├── mul_off
    ├── shift_off
    └── q6_off


operator options
    │
    ├── stride
    ├── dilation
    ├── padding
    └── activation


tensor quantization
    │
    ├── zx
    ├── zw
    └── zy

        ↓
    LayerParam
```

---

# 182. ADD view

```text
input tensor A ──→ SLOT A ──→ pointer A ──┐
                                          │
input tensor B ──→ SLOT B ──→ pointer B ──┤
                                          ▼
                                     LayerParam ADD

scales A/B/Y
      │
      ▼
ADD quantization
      │
      ├── mul A
      ├── shift A
      ├── mul B
      ├── shift B
      ├── out mul
      └── out shift
```

---

# 183. SOFTMAX view

```text
input tensor
    │
    ├── scale
    ├── zero point
    └── slot
         │
         ▼
input pointer

scale
 │
 ▼
softmax preparation
 │
 ├── input_beta_mul
 ├── input_beta_left_shift
 ├── input_left_shift
 └── diff_min

         ↓
   LayerParam SOFTMAX
```

---

# 184. Synthetic layer and portability

Inserting:

```text
RGB565_TO_RGB888
```

is a feature of the integration between model and host application.

TFLite continues to describe only its network.

The extractor adds a runtime stage required by the way data reaches the module.

---

# 185. Conceptual separation

```text
neural model
    ↓
TFLite operations
```

is not exactly the same as:

```text
complete firmware pipeline
```

The latter includes an additional preprocessing/formatting stage.

---

# 186. Effect on layer count

Therefore:

```text
runtime NUM_LAYERS
=
number of actual operations used
+
1 synthetic layer
```

---

# 187. Effect on slots

This is also why there is:

```text
slot_shift
```

The synthetic layer changes where the original logical flow starts within the physical set of slots.

---

# 188. Explicit validations in this module

The code fails in situations such as:

```text
QUANTIZE without input

QUANTIZE with scale_out = 0

input without a runtime slot

ADD with fewer than two inputs

ADD with input A or B without a slot

MEAN without input

MEAN with scale_y = 0

SOFTMAX without input

weighted op with fewer than two inputs

unsupported operation sent to the weighted builder

output without a runtime slot
```

---

# 189. Why are these validations important?

Because we are now directly building the runtime contract.

It is better to fail in the extractor:

```text
input tensor without a slot
```

than to generate:

```text
invalid LayerParam
        ↓
syntactically valid WAT
        ↓
WASM compiles
        ↓
runtime reads an incorrect address
```

---

# 190. Current limitations

Some situations still use a fallback instead of an error.

For example:

```text
weight_tensor_off.get(..., 0)
```

may result in:

```text
w_off = 0
```

if the weight is absent from the map.

This assumes `weights.py` has worked correctly for all supported operations.

---

# 191. Another feature

`build_layer_params()` silently skips useful operations whose:

```text
op_type_name
```

is not in:

```text
supported_operations
```

This preserves current behavior, but a future generic tool might preferably fail explicitly to prevent silent omission.

---

# 192. `input_ptrs` does not replace `in_slot`

The module stores both:

```text
in_slot
```

and:

```text
input_ptrs
```

The first preserves the region's logical identity.

The second allows auditing the assigned physical address.

---

# 193. Example

```text
in_slot = 2

slot_bases[2] = 900464
```

Then:

```text
input_ptrs = [900464]
```

---

# 194. In ADD

There are two elements:

```text
input_slots =
[
    slot_a,
    slot_b
]
```

and:

```text
input_ptrs =
[
    ptr_a,
    ptr_b
]
```

This makes the two-input operation fully traceable.

---

# 195. `label` versus list index

Another important detail:

```text
label = Lx
```

comes from the original graph.

But:

```text
layer_index
```

in the report starts at the synthetic layer.

Thus:

```text
FULL LAYER DUMP
L0
```

in the report does not necessarily mean:

```text
graph label L0
```

The first dump entry is:

```text
RGB565_TO_RGB888
```

and its:

```text
label
```

appears as:

```text
-
```

---

# 196. Important distinction

There are therefore:

```text
graph label
```

and:

```text
position within layer_params
```

These are different identities.

---

# 197. Example

```text
layer_params[0]
    → RGB565 synthetic

layer_params[1]
    → label L0

layer_params[2]
    → label L1
```

in a simple model.

---

# 198. Relationship with `LP_SIZE`

After serialization:

```text
layer_params[0]
    ↓
PARAMS_BASE + 0 × 116

layer_params[1]
    ↓
PARAMS_BASE + 1 × 116

layer_params[2]
    ↓
PARAMS_BASE + 2 × 116
```

Position in this list is therefore operationally important.

---

# 199. Module responsibility

`layer_params.py` does not generate:

```text
WAT
```

and does not yet generate:

```text
params_blob
```

It produces the intermediate structured description consumed by the next stage.

---

# 200. What it deliberately does not do

The module does not:

```text
concatenate weight bytes

generate (data ...) segments

write .wat files

execute inference

implement kernels

compile WASM
```

---

# 201. What it does

It answers:

```text
for each runtime operation,
which integer parameters,
logical addresses,
offsets,
flags,
dimensions, and information
will the kernel need?
```

---

# 202. Complete flow so far

```text
                    TFLite
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      graph          tensors        options
        │              │              │
        ▼              │              ▼
      slots            │      operator_options
        │              │
        ▼              │
 tensor mapping        │
        │              │
        └──────┐       │
               ▼       ▼
             layer_params
               ▲
               │
      ┌────────┼─────────┐
      │        │         │
   weights  quantization memory
```

---

# 203. After this module

```text
layer_params
      │
      ▼
params_blob.py
      │
      ▼
29 × int32
per layer
      │
      ▼
WAT data segment
```

---

# 204. Architectural synthesis

`layer_params.py` acts as the **final adapter between model and runtime**.

It receives:

```text
model structure
+
slot planning
+
memory addresses
+
parameter offsets
+
quantization
+
operation options
```

and produces:

```text
a uniform representation
for each executable layer
```

The main idea is that all operations use the same fixed-size structure:

```text
29 × int32
=
116 bytes
```

even when their needs differ greatly.

For traditional operations such as:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

fields retain meanings close to their names:

```text
kh/kw
stride
dilation
padding
```

For special operations:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

those same fields are deliberately reused to carry other parameters.

Thus:

```text
op_type
```

is the key determining how the runtime should interpret each field.

---

# 205. Final map of special operations

```text
ADD
────────────────────────────────
kh       → multiplier input A
kw       → shift input A
stride_h → multiplier input B
stride_w → shift input B
dil_h    → multiplier output
dil_w    → shift output
pad_t    → pointer input A
pad_b    → pointer input B
pad_l    → zero point A
pad_r    → zero point B


MEAN
────────────────────────────────
kh       → multiplier
kw       → shift
stride_h → in_h × in_w
pad_t    → input pointer


SOFTMAX
────────────────────────────────
kh       → input_beta_mul
kw       → input_beta_left_shift
stride_h → diff_min
stride_w → input_left_shift
pad_t    → input pointer


QUANTIZE
────────────────────────────────
flags    → uint8/int8 input
kh       → multiplier
kw       → shift
pad_t    → input pointer
zx       → zero point input
zy       → zero point output


RGB565_TO_RGB888
────────────────────────────────
in_slot  → SLOT0
out_slot → SLOT1
kh       → 65
```

This map is, in practice, part of the binary protocol between the extractor and the kernels implemented in WAT.

---

# 206. Final pipeline view

```text
TFLITE MODEL
     │
     ▼
graph.py
     │
     ▼
slots.py
     │
     ▼
tensor_mapping.py
     │
     ├─────────────────────┐
     │                     │
     ▼                     ▼
weights.py          quantization.py
     │                     │
     └──────────┬──────────┘
                │
                ▼
             memory.py
                │
                │
operator_options.py
                │
                ▼
        ┌───────────────────┐
        │  layer_params.py  │
        └───────────────────┘
                │
                ▼
        list[LayerParam]
                │
                ▼
          params_blob.py
                │
                ▼
        binary LayerParam[]
                │
                ▼
        wat_generator.py
                │
                ▼
             WASM
```

`layer_params.py` is therefore the stage where previously independent decisions come together to form each operation's complete execution contract.
