[English](08-quantizacao.md) | [Português (Brasil)](08-quantizacao.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body has been preserved in the Portuguese edition.

# 08 — Extracting and preparing quantization parameters (`quantization.py`)

## 1. Module purpose

The `extractor/quantization.py` file transforms quantization metadata stored in the TFLite model into integer parameters that can be used directly by kernels implemented in WebAssembly.

Up to this stage, the model provides information such as:

```text
scale
zero_point
quantized_dimension
```

However, the runtime does not directly perform floating-point operations to convert each layer accumulator.

Instead, the extractor prepares structures such as:

```text
multiplier
shift
Q6
```

which will later be used by quantized kernels.

The conceptual flow is:

```text
TFLite

input scale
weight scale
output scale
zero point
        │
        ▼
quantization.py
        │
        ├── real_multiplier
        │
        ├── multiplier Q31
        │
        ├── shift
        │
        └── Q6
        │
        ▼
int32 tables
        │
        ├── mul_blob
        ├── shift_blob
        └── q6_blob
        │
        ▼
WASM memory
```

---

# 2. Code and main responsibilities

The module has four main responsibilities:

```text
quantize_multiplier()
        ↓
convert real multiplier
to integer representation

extract_quantization_parameters()
        ↓
extract operation parameters

compute_add_quantization_params()
        ↓
calculate ADD-specific parameters

quantization_to_text()
        ↓
generate report
```

---

# 3. Imports

The file starts with:

```python
import math
import numpy as np
```

and:

```python
from extractor.tflite_utils import (
    op_name,
    qparams_np,
    scale_scalar,
    tensor_shape_list,
    zp_scalar,
)
```

Each helper has a specific role.

---

# 4. `op_name()`

Used to determine whether the current operator is:

```text
SOFTMAX
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

or another type that should not be handled by this routine.

---

# 5. `qparams_np()`

Returns the complete quantization of a tensor:

```python
{
    "scales": ...,
    "zps": ...,
    "qdim": ...,
}
```

This is particularly important for weights quantized per channel.

---

# 6. `scale_scalar()`

Obtains a single scale.

Used, for example, in the specific handling of `SOFTMAX`.

---

# 7. `zp_scalar()`

Obtains a single zero point.

Used mainly to calculate the quantized value corresponding to the upper limit of `ReLU6`.

---

# 8. `tensor_shape_list()`

Converts the tensor shape into a Python list.

In this module, it is used to determine how many channels or features need requantization parameters.

---

# 9. `INT32` limits

The module defines:

```python
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
```

Which corresponds to:

```text
INT32_MIN = -2147483648

INT32_MAX =  2147483647
```

These are the limits of a signed 32-bit integer.

---

# 10. Why do these limits appear here?

The quantized multiplier is stored in a 32-bit integer representation.

Therefore, after calculation, the value must remain within:

```text
-2³¹
to
2³¹ - 1
```

---

# 11. Operators with quantized weights

The set:

```python
QUANTIZED_WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}
```

identifies operations whose requantization depends simultaneously on:

```text
input scale
weight scale
output scale
```

---

# 12. Basic requantization relationship

A quantized operation normally calculates an integer accumulator.

In simplified form:

```text
quantized input
      ×
quantized weight
      ↓
int32 accumulator
```

But this accumulator is associated with a scale different from the desired output scale.

A conversion factor is therefore needed.

Conceptually:

```text
real_multiplier =
input_scale × weight_scale
──────────────────────────
       output_scale
```

This factor appears directly in the code for operations with weights.

---

# 13. Why not use `float` directly in the kernel?

Conceptually, it would be possible to calculate:

```text
accumulator × real_multiplier
```

using floating point.

But the implemented runtime uses integer requantization.

Thus:

```text
real_multiplier
```

is converted into:

```text
integer multiplier
+
shift
```

---

# 14. The `quantize_multiplier()` function

The central function is:

```python
def quantize_multiplier(
    real_multiplier: float,
):
```

It receives a real number and returns:

```python
(
    q31,
    exponent,
)
```

which the rest of the project interprets as:

```text
multiplier
shift
```

---

# 15. Function input

First:

```python
rm = float(
    real_multiplier
)
```

The input is explicitly converted to `float`.

This avoids carrying specific NumPy types through the rest of the function.

---

# 16. Zero case

If:

```python
rm == 0.0
```

the return value is:

```python
return 0, 0
```

Because:

```text
real multiplier = 0
```

can be represented directly by:

```text
multiplier = 0
shift = 0
```

---

# 17. Decomposition with `frexp()`

For nonzero values:

```python
q, exponent = math.frexp(
    rm
)
```

The `frexp()` function decomposes the number approximately as:

```text
rm = q × 2^exponent
```

---

# 18. Property of `q`

For normal positive numbers, `q` usually falls within:

```text
0,5 ≤ q < 1
```

Thus, the real value is separated into:

```text
normalized fractional part
+
power of two
```

---

# 19. Example with `0.75`

For:

```text
real_multiplier = 0.75
```

we may have:

```text
q = 0.75
exponent = 0
```

because:

```text
0.75 =
0.75 × 2⁰
```

---

# 20. Example with `0.375`

For:

```text
real_multiplier = 0.375
```

we can represent:

```text
0.375 =
0.75 × 2⁻¹
```

Then:

```text
q = 0.75
exponent = -1
```

---

# 21. Example with `1.5`

Similarly:

```text
1.5 =
0.75 × 2¹
```

Then:

```text
q = 0.75
exponent = 1
```

---

# 22. Conversion to Q31

Then:

```python
q31 = int(
    round(
        q * (1 << 31)
    )
)
```

The value:

```text
1 << 31
```

corresponds to:

```text
2³¹
```

Thus, `q` is represented on an integer scale of approximately 31 fractional bits.

---

# 23. Example

For:

```text
q = 0.75
```

we have:

```text
q31 ≈
0.75 × 2147483648
```

resulting in:

```text
1610612736
```

Therefore:

```text
0.75
```

can be represented approximately by:

```text
multiplier = 1610612736
shift = 0
```

---

# 24. Same multiplier, different shifts

The examples:

```text
0.375
0.75
1.5
```

can share the same `q31`:

```text
1610612736
```

but use different shifts:

```text
0.375 → shift -1
0.75  → shift  0
1.5   → shift +1
```

It is the pair:

```text
(multiplier, shift)
```

that represents the complete factor.

---

# 25. The project's shift convention

In the current runtime:

```text
shift > 0
    ↓
left shift

shift < 0
    ↓
right shift
```

Thus, the exponent returned by `frexp()` is retained as part of the requantization representation.

---

# 26. Rounding boundary case

After rounding, the code contains:

```python
if q31 == (1 << 31):
    q31 //= 2
    exponent += 1
```

This handles the case where rounding produces exactly:

```text
2³¹
```

which would exceed the largest positive `int32`.

---

# 27. Why divide by two?

If:

```text
q31
```

is halved, we can compensate by increasing the exponent by 1.

Conceptually:

```text
q × 2^e

is equivalent to

(q/2) × 2^(e+1)
```

Thus, the represented value remains equivalent.

---

# 28. Safety saturation

Then:

```python
if q31 > INT32_MAX:
    q31 = INT32_MAX
```

and:

```python
if q31 < INT32_MIN:
    q31 = INT32_MIN
```

ensure that the result remains representable in 32 bits.

---

# 29. Return value

Finally:

```python
return (
    int(q31),
    int(exponent),
)
```

In other words:

```text
real_multiplier
      ↓
quantize_multiplier()
      ↓
multiplier int32
+
shift
```

---

# 30. The `extract_quantization_parameters()` function

The main function of this stage is:

```python
def extract_quantization_parameters(
    model,
    subgraph,
):
```

It visits model operators and builds three tables:

```text
MUL
SHIFT
Q6
```

---

# 31. Initially empty structures

The following are created:

```python
mul_vals = []
shift_vals = []
q6_vals = []
```

These lists store integer values.

They will later be converted into binary blobs.

---

# 32. Offset mapping

The following is also created:

```python
mul_q6_off = {}
```

It associates:

```text
op_index
    ↓
MUL table offset
SHIFT table offset
Q6 table offset
number of features
```

---

# 33. `mul_q6_off` format

For an operation, we may have:

```python
mul_q6_off[15] = (
    128,
    128,
    128,
    32,
)
```

representing:

```text
op 15

mul_offset   = 128
shift_offset = 128
q6_offset    = 128
nfeat        = 32
```

---

# 34. Offsets in bytes

These offsets are measured in bytes.

This is because each value is serialized as:

```text
int32
```

therefore:

```text
4 bytes
```

---

# 35. Calculating the offset

The code uses:

```python
mul_offset = (
    len(mul_vals) * 4
)
```

If there are already:

```text
10 multipliers
```

then:

```text
offset =
10 × 4
=
40 bytes
```

---

# 36. Same logic for SHIFT and Q6

```python
shift_offset = (
    len(shift_vals) * 4
)
```

and:

```python
q6_offset = (
    len(q6_vals) * 4
)
```

---

# 37. `records`

The following is also created:

```python
records = []
```

It contains detailed report information.

As in `weights.py`, there is a separation between:

```text
data used by the runtime
```

and:

```text
metadata used for analysis
```

---

# 38. Scanning operators

The module iterates:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

and identifies:

```python
op_type = op_name(
    model,
    op,
)
```

---

# 39. Two main paths

There are then two processing paths.

```text
SOFTMAX
```

has its own logic.

Whereas:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

share the main weight quantization logic.

---

# 40. Handling `SOFTMAX`

The first special case is:

```python
if op_type == "SOFTMAX":
```

`SOFTMAX` does not have a weight tensor like a convolution.

Therefore, it does not make sense to use:

```text
input_scale × weight_scale / output_scale
```

Preparation is different.

---

# 41. `SOFTMAX` inputs

The following are collected:

```python
input_ids = [
    int(tensor_id)
    for tensor_id
    in op.InputsAsNumpy()
    if int(tensor_id) >= 0
]
```

At least the following is required:

```text
1 input
```

Otherwise:

```python
continue
```

---

# 42. Input tensor

The main input is:

```python
input_tensor = (
    subgraph.Tensors(
        input_ids[0]
    )
)
```

---

# 43. Input scale

Then:

```python
input_scale = scale_scalar(
    input_tensor
)
```

This gives `SOFTMAX` the scale of the incoming quantized values.

---

# 44. `beta`

The current code defines:

```python
beta = 1.0
```

This is the value used by the implemented runtime.

---

# 45. `integer_bits`

The following is also defined:

```python
integer_bits = 5
```

This value contributes to the calculation of:

```text
input_left_shift
```

---

# 46. `input_left_shift`

The calculation is:

```python
input_left_shift = max(
    0,
    (
        integer_bits
        - floor(log2(
            127.0 * input_scale
            + 1e-9
        ))
        - 1
    ),
)
```

---

# 47. Role of `input_left_shift`

This value determines how far the `diff` used internally by `SOFTMAX` can be shifted left before multiplication.

In the current runtime, this value is retained separately from the parameters:

```text
input_beta_mul
input_beta_left_shift
```

---

# 48. The `127 × input_scale` term

For an `int8` tensor, the approximate maximum positive magnitude is:

```text
127
```

Multiplying by:

```text
input_scale
```

produces an estimate of the maximum representable real magnitude.

---

# 49. Using `log2`

The code uses:

```python
math.log2(
    127.0 * input_scale
    + 1e-9
)
```

to estimate how many bits are needed to represent this magnitude.

---

# 50. Role of `1e-9`

The small value:

```text
0.000000001
```

avoids numerical problems with:

```text
log2(0)
```

or values extremely close to zero.

---

# 51. Zero lower bound

Using:

```python
max(
    0,
    ...
)
```

ensures that:

```text
input_left_shift
```

is nonnegative.

---

# 52. SOFTMAX `real_multiplier`

Then:

```python
real_multiplier = (
    beta * input_scale
)
```

With:

```text
beta = 1
```

this reduces to:

```text
real_multiplier =
input_scale
```

---

# 53. Conversion to integer

This factor is passed to:

```python
quantize_multiplier(
    real_multiplier
)
```

producing:

```text
multiplier
shift
```

---

# 54. Important detail about `SOFTMAX`

The module retains two pieces of shift-related information:

```text
input_left_shift
```

and:

```text
shift
```

returned by `quantize_multiplier()`.

They are not the same variable.

---

# 55. Subsequent mapping

In the runtime's `LayerParam`, the current implementation stores:

```text
kh       = multiplier
kw       = shift
stride_h = diff_min
stride_w = input_left_shift
```

Therefore:

```text
kw
```

and:

```text
stride_w
```

represent different information in `SOFTMAX`.

---

# 56. Recording in the tables

`SOFTMAX` adds only one value to:

```python
mul_vals
```

and:

```python
shift_vals
```

because:

```text
nfeat = 1
```

for this parameter record.

---

# 57. SOFTMAX offsets

Before insertion:

```python
mul_offset = (
    len(mul_vals) * 4
)
```

and:

```python
shift_offset = (
    len(shift_vals) * 4
)
```

are calculated.

Then:

```python
mul_vals.append(
    multiplier
)
```

and:

```python
shift_vals.append(
    shift
)
```

---

# 58. Entry in `mul_q6_off`

The code records:

```python
mul_q6_off[
    op_idx
] = (
    mul_offset,
    shift_offset,
    0,
    1,
)
```

In other words:

```text
mul offset
shift offset
q6 offset = 0
nfeat = 1
```

`SOFTMAX` does not generate a Q6 table.

---

# 59. SOFTMAX record

The report preserves:

```text
input_tensor_id
input_scale
beta
integer_bits
input_left_shift
real_multiplier
multiplier
shift
offsets
```

This allows the exact values used to be reconstructed.

---

# 60. End of the SOFTMAX case

Then:

```python
continue
```

prevents the operator from falling through to handling intended for convolutions and fully connected layers.

---

# 61. Filtering operations with weights

After the `SOFTMAX` case:

```python
if (
    op_type
    not in QUANTIZED_WEIGHT_OPERATORS
):
    continue
```

Thus, only:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

continue.

---

# 62. Inputs and outputs

The following are collected:

```python
input_ids
```

and:

```python
output_ids
```

filtering negative IDs.

---

# 63. Minimum structure

The operation must have:

```text
at least 2 inputs
at least 1 output
```

Otherwise:

```python
continue
```

---

# 64. Main tensors

The code identifies:

```text
input_ids[0]
    ↓
input activation
```

```text
input_ids[1]
    ↓
weights
```

```text
output_ids[0]
    ↓
output activation
```

---

# 65. TFLite objects

The following are retrieved:

```python
input_tensor
weight_tensor
output_tensor
```

These three tensors provide the scales needed to calculate requantization.

---

# 66. Weight shape

The code obtains:

```python
weight_shape = tensor_shape_list(
    weight_tensor
)
```

This shape is used to determine:

```text
nfeat
```

---

# 67. What is `nfeat`?

In this module, `nfeat` represents how many sets of:

```text
multiplier
shift
Q6
```

must exist for that operation.

It usually corresponds to the number of output channels/features.

---

# 68. `nfeat` in `CONV_2D`

For:

```text
CONV_2D
```

the following is used:

```python
weight_shape[0]
```

Therefore:

```text
weight shape
[O, H, W, I]
```

produces:

```text
nfeat = O
```

where `O` is the number of output channels.

---

# 69. Example

Weights:

```text
[32, 3, 3, 3]
```

Then:

```text
nfeat = 32
```

The following will be prepared:

```text
32 multipliers
32 shifts
32 Q6 values
```

---

# 70. `nfeat` in `DEPTHWISE_CONV_2D`

For depthwise:

```python
weight_shape[3]
```

is used.

Thus, for the layout expected by the model:

```text
nfeat =
last weight dimension
```

---

# 71. Example

Shape:

```text
[1, 3, 3, 32]
```

results in:

```text
nfeat = 32
```

---

# 72. `nfeat` in `FULLY_CONNECTED`

In the third case:

```python
weight_shape[0]
```

is used again.

For a matrix:

```text
[1000, 1280]
```

we would have:

```text
nfeat = 1000
```

---

# 73. Invalid shape

If it is not possible to determine:

```text
nfeat
```

the function executes:

```python
continue
```

---

# 74. Reading complete quantization

Then:

```python
q_input = qparams_np(
    input_tensor
)
```

```python
q_weights = qparams_np(
    weight_tensor
)
```

```python
q_output = qparams_np(
    output_tensor
)
```

---

# 75. Quantization requirement

If any returns:

```text
None
```

the operation is skipped at this stage.

The same happens if any scale vector is empty.

---

# 76. `input_scale`

For the input:

```python
input_scale = float(
    q_input["scales"][0]
)
```

The code uses a single input scale.

---

# 77. `weight_scales`

Weights, in contrast, are retained as a vector:

```python
weight_scales = (
    q_weights["scales"]
    .astype(np.float64)
)
```

This supports:

```text
per-tensor
```

or:

```text
per-channel
```

---

# 78. `output_scales`

Output is also initially retained as a vector:

```python
output_scales = (
    q_output["scales"]
    .astype(np.float64)
)
```

---

# 79. `output_scale`

For the main multiplier calculation:

```python
output_scale = float(
    output_scales[0]
)
```

Therefore, the denominator used in the main calculation is the first output scale.

---

# 80. Starting offsets

Before inserting operation values:

```text
mul_offset
shift_offset
q6_offset
```

are calculated from the current table lengths.

This records where that operation's data will start.

---

# 81. Operation-local lists

The following are created:

```python
operation_multipliers = []
operation_shifts = []
real_multipliers = []
```

These lists contain only the current operation's data.

They will later be added to the global tables.

---

# 82. Case with a single `weight_scale`

If:

```python
weight_scales.size == 1
```

weight quantization is treated as per-tensor.

---

# 83. Real multiplier formula

The following is calculated:

```text
real_multiplier =

weight_scale
×
input_scale
────────────
output_scale
```

In the code:

```python
real_multiplier = (
    weight_scales[0]
    * input_scale
    / output_scale
)
```

---

# 84. Mathematical origin

The quantized input approximately represents:

```text
real_x =
Sx × (qx - Zx)
```

The weight:

```text
real_w =
Sw × (qw - Zw)
```

The product has scale:

```text
Sx × Sw
```

But the output must have scale:

```text
Sy
```

It is therefore necessary to convert:

```text
Sx × Sw
```

to:

```text
Sy
```

using:

```text
Sx × Sw
───────
   Sy
```

---

# 85. Conversion to multiplier + shift

This value is passed to:

```python
quantize_multiplier(
    real_multiplier
)
```

producing:

```text
multiplier
shift
```

---

# 86. Replication per feature

Since there is only one weight scale:

```python
operation_multipliers = [
    multiplier
] * nfeat
```

and:

```python
operation_shifts = [
    shift
] * nfeat
```

---

# 87. Example

If:

```text
nfeat = 32
```

and:

```text
multiplier = 1234567890
shift = -2
```

the following will be stored:

```text
32 copies of the multiplier
32 copies of the shift
```

---

# 88. Why replicate?

The runtime can access parameters using the channel index.

Keeping:

```text
one value per feature
```

simplifies the kernel, even when every channel shares the same value.

---

# 89. `real_multipliers`

The same replication is performed for:

```python
real_multipliers
```

but these values are mainly used in the report.

They do not form a blob used by the runtime.

---

# 90. Per-channel case

If:

```python
weight_scales.size > 1
```

each channel may have a different scale.

---

# 91. Number of scales used

The code calculates:

```python
use = min(
    nfeat,
    weight_scales.size,
)
```

This prevents access to nonexistent positions.

---

# 92. Vector real multipliers

The following are calculated:

```python
rm_values = (
    weight_scales[:use]
    * input_scale
    / output_scale
)
```

Now each channel may have a:

```text
different real_multiplier
```

---

# 93. Example

Suppose:

```text
input_scale = 0.02
output_scale = 0.04

weight_scales =
[
    0.10,
    0.20,
    0.30
]
```

Then:

```text
channel 0:
0.10 × 0.02 / 0.04
= 0.05

channel 1:
0.20 × 0.02 / 0.04
= 0.10

channel 2:
0.30 × 0.02 / 0.04
= 0.15
```

---

# 94. Channel-by-channel conversion

The loop:

```python
for rm in rm_values:
```

executes:

```python
quantize_multiplier(
    rm
)
```

individually.

---

# 95. Result

Lists such as these will be formed:

```text
multipliers:
[M0, M1, M2, ...]

shifts:
[S0, S1, S2, ...]
```

---

# 96. Padding when scales are missing

If:

```python
nfeat > use
```

the code calculates:

```python
missing = (
    nfeat - use
)
```

and replicates the last calculated parameter.

---

# 97. Example

If:

```text
nfeat = 32
```

but only the following were found:

```text
30 weight_scales
```

the code uses:

```text
channel 29
```

as a reference to fill the last two.

---

# 98. Multipliers

```python
operation_multipliers.extend(
    [
        operation_multipliers[-1]
    ] * missing
)
```

---

# 99. Shifts

The same is done for:

```python
operation_shifts
```

---

# 100. Real multipliers

And also for:

```python
real_multipliers
```

to keep lists the same size.

---

# 101. Note on the legacy code

The code itself notes that the old file contained this filling block twice.

The modularized version contains it only once.

This preserves the code's intent without unnecessarily repeating the same operation.

---

# 102. Insertion into global tables

Once calculated:

```python
mul_vals.extend(
    operation_multipliers
)
```

and:

```python
shift_vals.extend(
    operation_shifts
)
```

---

# 103. MUL table structure

After several operations:

```text
MUL

op 0:
[M0 M1 M2 ...]

op 1:
[M0 M1 M2 ...]

op 2:
[M0 M1 M2 ...]
```

They are all concatenated into a single table.

---

# 104. SHIFT table structure

Similarly:

```text
SHIFT

op 0:
[S0 S1 S2 ...]

op 1:
[S0 S1 S2 ...]

op 2:
[S0 S1 S2 ...]
```

Offsets indicate where each group starts.

---

# 105. Calculating Q6

After the multipliers comes the calculation of:

```text
Q6
```

---

# 106. What does Q6 represent?

`Q6` represents the quantized form of the real value:

```text
6.0
```

in the operation's output scale.

This value is used to implement saturation corresponding to:

```text
ReLU6
```

---

# 107. Quantizing a real value

The basic relationship is:

```text
q =
round(
    real / scale
)
+
zero_point
```

For:

```text
real = 6
```

we obtain:

```text
q6 =
round(
    6 / output_scale
)
+
output_zero_point
```

This is exactly the formula used by the code.

---

# 108. Output zero point

First:

```python
output_zero_point = zp_scalar(
    output_tensor
)
```

---

# 109. Output with a single scale

If:

```python
output_scales.size == 1
```

the following is calculated:

```python
q6 = (
    round(
        6.0
        / output_scales[0]
    )
    + output_zero_point
)
```

---

# 110. Example

Suppose:

```text
output_scale = 0.05
output_zero_point = -128
```

Then:

```text
6 / 0.05
=
120
```

Therefore:

```text
q6 =
120 - 128
=
-8
```

Therefore:

```text
quantized value -8
```

approximately represents the real value:

```text
6
```

for that quantization.

---

# 111. Replicating Q6

If the operation has:

```text
nfeat = 32
```

then:

```python
operation_q6 = [
    q6
] * nfeat
```

---

# 112. Why a table per feature?

Again, the runtime can directly index:

```text
q6[channel]
```

regardless of whether the scale is actually shared or per-channel.

---

# 113. Output with multiple scales

If:

```python
output_scales.size > 1
```

the code calculates one Q6 for each available scale.

---

# 114. Vectorized quantization

```python
q6_values = (
    np.round(
        6.0
        / output_scales[:use]
    )
    .astype(np.int64)
    + output_zero_point
)
```

---

# 115. Conversion to Python integers

Values are appended with:

```python
operation_q6.extend(
    int(value)
    for value
    in q6_values
)
```

---

# 116. Q6 padding

If there are fewer scales than `nfeat`, the last value is repeated.

Thus:

```text
len(operation_q6)
```

ends up equal to:

```text
nfeat
```

---

# 117. Insertion into the global table

Then:

```python
q6_vals.extend(
    operation_q6
)
```

---

# 118. Combined organization of the three tables

For a given operation, ideally there are:

```text
nfeat multipliers
nfeat shifts
nfeat Q6
```

Then, for channel `c`:

```text
multiplier[c]
shift[c]
q6[c]
```

form the set used for that output channel.

---

# 119. Recording offsets

Then:

```python
mul_q6_off[
    op_idx
] = (
    mul_offset,
    shift_offset,
    q6_offset,
    nfeat,
)
```

This is one of the function's most important results.

---

# 120. Example

Suppose:

```python
mul_q6_off[12] = (
    256,
    256,
    256,
    32,
)
```

Then operation 12 has:

```text
multipliers starting at MUL + 256

shifts starting at SHIFT + 256

Q6 starting at Q6_BASE + 256

32 features
```

---

# 121. An offset is still not an absolute address

As in `weights.py`:

```text
256
```

is not the final address in WASM memory.

Later:

```text
mul_ptr =
MUL_BASE + mul_offset
```

---

# 122. Example

If:

```text
MUL_BASE = 414832
mul_offset = 256
```

then:

```text
mul_ptr =
415088
```

---

# 123. Same principle for SHIFT

```text
shift_ptr =
SHIFT_BASE
+
shift_offset
```

---

# 124. And for Q6

```text
q6_ptr =
Q6_BASE
+
q6_offset
```

when the operation actually uses ReLU6.

---

# 125. Report records

A dictionary is stored for each operation, containing:

```text
op_index
op_type
input_tensor_id
weight_tensor_id
output_tensor_id
nfeat

input_scale
weight_scales
output_scales
output_zero_point

real_multipliers
multipliers
shifts
q6

offsets
quantized_dimension
```

---

# 126. Why store `real_multipliers`?

They allow comparison of:

```text
desired mathematical value
```

against:

```text
generated integer representation
```

This is very useful for debugging requantization.

---

# 127. `weight_quantized_dimension`

The report also records:

```python
q_weights["qdim"]
```

This indicates which weight tensor dimension is associated with per-channel quantization.

---

# 128. `output_quantized_dimension`

Similarly:

```python
q_output["qdim"]
```

is preserved.

Even though the current calculation mainly uses:

```text
output_scales[0]
```

this information remains available for analysis.

---

# 129. End of the scan

After all operators have been processed, there are three Python lists:

```text
mul_vals
shift_vals
q6_vals
```

But the runtime needs bytes.

---

# 130. Serializing `mul_blob`

The code uses:

```python
mul_blob = np.array(
    mul_vals,
    dtype="<i4",
).tobytes()
```

---

# 131. Meaning of `<i4`

The specification:

```text
<
```

means:

```text
little-endian
```

and:

```text
i4
```

means:

```text
4-byte signed integer
```

in other words:

```text
int32
```

---

# 132. Therefore

Each multiplier occupies exactly:

```text
4 bytes
```

in the blob.

---

# 133. `shift_blob`

It is built in the same way:

```python
shift_blob = np.array(
    shift_vals,
    dtype="<i4",
).tobytes()
```

---

# 134. `q6_blob`

And:

```python
q6_blob = np.array(
    q6_vals,
    dtype="<i4",
).tobytes()
```

---

# 135. Why serialize as `int32`?

The WebAssembly runtime uses integer operations and reads these parameters as 32-bit values.

Furthermore, offsets were calculated assuming:

```text
4 bytes per entry
```

There is therefore a direct relationship:

```text
len(list) × 4
=
len(blob)
```

---

# 136. Example

If:

```text
mul_vals has 7044 values
```

then:

```text
mul_blob =
7044 × 4
=
28176 bytes
```

---

# 137. Binary structure

Conceptually:

```text
mul_blob

[M0 4 bytes]
[M1 4 bytes]
[M2 4 bytes]
...
```

The same applies to `shift_blob` and `q6_blob`.

---

# 138. Extraction return value

The function returns:

```python
{
    "mul_vals": ...,
    "shift_vals": ...,
    "q6_vals": ...,

    "mul_blob": ...,
    "shift_blob": ...,
    "q6_blob": ...,

    "mul_q6_off": ...,

    "records": ...,
}
```

---

# 139. Values versus blobs

There is deliberate duplication of representation.

```text
mul_vals
```

is convenient for:

```text
calculation
debug
report
```

While:

```text
mul_blob
```

is convenient for:

```text
serialization
WAT
WASM memory
```

---

# 140. The same applies to SHIFT and Q6

```text
shift_vals
    ↓
structured form

shift_blob
    ↓
binary form
```

and:

```text
q6_vals
    ↓
structured form

q6_blob
    ↓
binary form
```

---

# 141. The `compute_add_quantization_params()` function

`ADD` is not handled in the main tables in the same way as a convolution.

It has its own function:

```python
def compute_add_quantization_params(
    scale_a,
    scale_b,
    scale_y,
):
```

---

# 142. Why is `ADD` different?

`ADD` combines two activations that may have different scales:

```text
A
+
B
```

If:

```text
A uses scale_a
```

and:

```text
B uses scale_b
```

the two values must be placed on a compatible scale before addition.

---

# 143. Inputs

The function receives:

```text
scale_a
scale_b
scale_y
```

where:

```text
scale_a = first input scale

scale_b = second input scale

scale_y = output scale
```

---

# 144. Common scale

First:

```python
scale_common = max(
    scale_a,
    scale_b,
) * 2.0
```

This creates a common intermediate scale.

---

# 145. Example

If:

```text
scale_a = 0.02

scale_b = 0.03
```

then:

```text
max = 0.03
```

and:

```text
scale_common =
0.03 × 2
=
0.06
```

---

# 146. Degenerate cases

The function checks several zero-scale cases.

If:

```text
scale_a == 0
and
scale_b == 0
```

returns zero multipliers and shifts.

---

# 147. Output with zero scale

Similarly:

```python
if scale_y == 0.0:
```

returns zeros.

---

# 148. Zero common scale

There is also:

```python
if scale_common == 0.0:
```

as protection.

---

# 149. Ratio for input A

In a normal case:

```python
ratio_a = (
    scale_a
    / scale_common
)
```

---

# 150. Converting input A

Then:

```python
mul_a, shift_a = (
    quantize_multiplier(
        ratio_a
    )
)
```

---

# 151. Input B

Similarly:

```text
ratio_b =
scale_b / scale_common
```

and:

```text
mul_b
shift_b
```

---

# 152. Converting the sum to the output

Once A and B are represented on the common scale, output must be converted to:

```text
scale_y
```

Therefore:

```python
output_ratio = (
    scale_common
    / scale_y
)
```

---

# 153. Output parameters

```python
output_mul,
output_shift
=
quantize_multiplier(
    output_ratio
)
```

---

# 154. ADD return value

The function returns seven values:

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

# 155. Conceptual ADD flow

```text
quantized A
   │
   └─ scale_a
        │
        ▼
  mul_a / shift_a
        │
        ▼
    common scale
        │
        │
        ├────────┐
        │        │
        ▼        ▼
       A'   +   B'
            │
            ▼
          sum
            │
            ▼
output_mul / output_shift
            │
            ▼
       scale_y
```

---

# 156. Where are ADD parameters stored?

Unlike convolutions, ADD parameters are later placed directly in reused `LayerParam` fields.

In the current runtime:

```text
kh       = mul0
kw       = shift0

stride_h = mul1
stride_w = shift1

dil_h    = out_mul
dil_w    = out_shift
```

Therefore, ADD does not necessarily need entries in this function's global MUL/SHIFT tables.

---

# 157. Why is this possible?

ADD has a fixed parameter count:

```text
3 multipliers
3 shifts
```

A convolution, however, may have:

```text
32
64
96
160
...
```

per-channel multipliers.

Therefore, convolution uses external tables, whereas ADD can store its parameters directly in the layer structure.

---

# 158. Relationship to `layer_params.py`

Later:

```text
quantization.py
     │
     ├── mul_q6_off
     │
     └── compute_add_quantization_params()
     │
     ▼
layer_params.py
```

The first is used by:

```text
CONV
DEPTHWISE
FC
SOFTMAX
```

while the specific function is used by:

```text
ADD
```

---

# 159. The `quantization_to_text()` function

The final function transforms:

```python
extraction
```

into a detailed report.

It does not participate in calculations.

---

# 160. Per-operation report

For each entry in:

```python
extraction["records"]
```

the report starts with:

```text
================================================================================
OP_INDEX: ...
TIPO: ...
NFEAT: ...
```

---

# 161. `INPUT_SCALE`

All operations record:

```text
INPUT_SCALE
```

because this value directly contributes to requantization.

---

# 162. `SOFTMAX` report

When:

```text
TIPO = SOFTMAX
```

the following are also shown:

```text
BETA
INTEGER_BITS
INPUT_LEFT_SHIFT
REAL_MULTIPLIER
```

---

# 163. Report for operations with weights

For:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

the following are shown:

```text
WEIGHT_SCALES
OUTPUT_SCALES
OUTPUT_ZERO_POINT
REAL_MULTIPLIERS
```

---

# 164. Integer parameters

Then, regardless of the recorded type, the report shows:

```text
MULTIPLIERS
SHIFTS
Q6
```

---

# 165. Offsets

The following are also shown:

```text
MUL
SHIFT
Q6
```

as byte offsets.

---

# 166. Conceptual example

```text
OP_INDEX: 12
TIPO: CONV_2D
NFEAT: 32

INPUT_SCALE: 0.023...

WEIGHT_SCALES:
[...]

OUTPUT_SCALES:
[...]

OUTPUT_ZERO_POINT: -128

REAL_MULTIPLIERS:
[...]

MULTIPLIERS:
[...]

SHIFTS:
[...]

Q6:
[...]

OFFSETS:
  MUL   = 128
  SHIFT = 128
  Q6    = 128
```

---

# 167. Final summary

The report ends with:

```text
Number of multipliers
Number of shifts
Number of Q6 values

mul_blob in bytes
shift_blob in bytes
q6_blob in bytes
```

---

# 168. Relationship between count and size

Since each value occupies:

```text
4 bytes
```

the following must hold:

```text
len(mul_blob)
=
len(mul_vals) × 4
```

Similarly:

```text
len(shift_blob)
=
len(shift_vals) × 4
```

and:

```text
len(q6_blob)
=
len(q6_vals) × 4
```

---

# 169. A useful validation property

For example:

```text
multipliers = 7000
```

must result in:

```text
28000 bytes
```

Otherwise, there is a serialization inconsistency.

---

# 170. Relationship to `weights.py`

`weights.py` produces:

```text
weights_raw
bias_raw
```

Whereas `quantization.py` produces:

```text
mul_blob
shift_blob
q6_blob
```

All will later be placed in the same linear memory, but in different regions.

---

# 171. Comparison

```text
weights_raw
    ↓
trained parameters

bias_raw
    ↓
trained bias

mul_blob
    ↓
derived requantization parameters

shift_blob
    ↓
derived requantization parameters

q6_blob
    ↓
limits derived from output quantization
```

---

# 172. Extracted versus derived data

This distinction matters.

Weights come directly from the model:

```text
TFLite buffer
    ↓
weights_raw
```

Whereas:

```text
multiplier
shift
Q6
```

are calculated by the extractor from model metadata.

---

# 173. Complete `CONV_2D` flow

Consider:

```text
input_scale = Sx

weight_scale[c] = Sw[c]

output_scale = Sy
```

For each channel:

```text
real_multiplier[c]
=
Sx × Sw[c] / Sy
```

Then:

```text
real_multiplier[c]
      ↓
quantize_multiplier()
      ↓
multiplier[c]
shift[c]
```

In parallel:

```text
6.0
 ↓
output quantization
 ↓
Q6[c]
```

---

# 174. Per-channel result

For a channel `c`:

```text
multiplier[c]
shift[c]
Q6[c]
```

will be used by the kernel to requantize the accumulated output.

---

# 175. Path to WAT

```text
quantization.py
      │
      ├── mul_blob
      ├── shift_blob
      └── q6_blob
      │
      ▼
memory.py
      │
      ├── MUL_BASE
      ├── SHIFT_BASE
      └── Q6_BASE
      │
      ▼
layer_params.py
      │
      ├── mul_ptr
      ├── shift_ptr
      └── q6_ptr
      │
      ▼
params_blob
      │
      ▼
WAT
```

---

# 176. Final address example

Suppose:

```text
MUL_BASE = 414832

mul_offset = 128
```

Then:

```text
mul_ptr =
414832 + 128
=
414960
```

This address will be inserted into `LayerParam`.

---

# 177. The same for SHIFT

```text
SHIFT_BASE = 443008

shift_offset = 128

shift_ptr =
443136
```

---

# 178. And Q6

```text
Q6_BASE = 471184

q6_offset = 128

q6_ptr =
471312
```

These numbers are only examples.

---

# 179. Q6 and activation

The Q6 blob can be prepared for every feature of quantized operations, but its pointer is later used according to layer activation.

For an operation with:

```text
ReLU6
```

the upper limit is required.

For a layer without this activation, the runtime may not use `q6_ptr`.

---

# 180. Why is Q6 `int32`?

Even when the operation's final output is `int8`, storing the limit as `int32` maintains a uniform representation in auxiliary tables and simplifies runtime access.

---

# 181. Relationship to zero points

Complete requantization does not depend only on:

```text
multiplier
shift
```

There are also:

```text
zx
zw
zy
```

which represent zero points for:

```text
input
weight
output
```

These values are later stored in `LayerParam`.

---

# 182. Division of responsibilities

Therefore:

```text
quantization.py
```

mainly produces:

```text
multiplier
shift
Q6
```

While:

```text
layer_params.py
```

brings together:

```text
multiplier pointers
zero points
layer geometry
addresses
flags
```

---

# 183. Why not put everything in this module?

Because this file should answer:

```text
which numerical quantization parameters
do I need to execute the operation?
```

rather than:

```text
where will they be stored in memory?
```

That second question belongs to `memory.py` and `layer_params.py`.

---

# 184. Relative offset versus pointer

As in `weights.py`:

```text
mul_offset
shift_offset
q6_offset
```

are relative.

Later:

```text
base + offset
```

generates the final pointer.

---

# 185. Independent tables

Offsets are independent because there are three separate blobs.

Thus:

```text
mul_offset = 100
shift_offset = 100
q6_offset = 100
```

does not mean all three data items occupy the same memory.

They belong respectively to:

```text
MUL_BASE + 100

SHIFT_BASE + 100

Q6_BASE + 100
```

---

# 186. Per-tensor quantization

When weights have a single scale:

```text
Sw
```

the same:

```text
multiplier
shift
```

is replicated across all channels.

---

# 187. Per-channel quantization

When there are:

```text
Sw[0]
Sw[1]
Sw[2]
...
```

each channel receives its own:

```text
multiplier[c]
shift[c]
```

---

# 188. Why does this matter for MobileNetV2?

Quantized convolutions may use channel-specific weight scales.

A single global requantization constant would therefore be insufficient.

The runtime must access the parameter corresponding to the output channel being calculated.

---

# 189. Conceptual kernel example

For channel:

```text
c
```

the runtime may actually query:

```text
mul_ptr + c × 4
```

and:

```text
shift_ptr + c × 4
```

to load that channel's parameters.

---

# 190. Direct relationship to `nfeat`

This is precisely why:

```text
nfeat
```

must match the number of parameter sets available for that operation.

---

# 191. What the module deliberately does not do

`quantization.py` does not:

```text
extract weight bytes

organize weights_raw

calculate absolute bases

allocate slots

calculate spatial padding

generate LayerParam

generate WAT
```

---

# 192. Its exact responsibility

It answers:

```text
how can scale factors
from the quantized model

be converted into integer parameters
usable by the runtime?
```

---

# 193. Current validations

The module checks, among other conditions:

```text
sufficient inputs and outputs

existing quantization

nonempty scale vectors

sufficient shape to determine nfeat
```

When one of these conditions fails:

```python
continue
```

is used.

---

# 194. Consequence of using `continue`

An operation with unexpected metadata may simply receive no entry in:

```python
mul_q6_off
```

Later stages must therefore assume that supported operations in the current model have valid quantization.

---

# 195. Possible future development

In a more generic tool, it may be useful to replace certain:

```python
continue
```

with explicit exceptions such as:

```text
quantized operation without scale

incompatible shape

unexpected quantized dimension
```

This would make failures in external models easier to diagnose.

---

# 196. Preserving current behavior

In the current modularization, the priority was:

```text
preserve the behavior
of the validated extractor
```

before tightening all checks.

This principle also explains filling with the last value when there is a difference between:

```text
nfeat
```

and:

```text
number of available scales
```

---

# 197. Relationship to numerical fidelity

This module is one of the most sensitive points for fidelity between:

```text
TFLite
```

and:

```text
WASM implementation
```

Because a small difference in:

```text
multiplier
shift
zero point
saturation
```

can change a layer's quantized output.

---

# 198. Propagation chain

A multiplier difference may produce:

```text
different activation value
       ↓
different input to the next layer
       ↓
different new accumulator
       ↓
difference propagated through the network
```

This is why the module deserves detailed reports.

---

# 199. The report's role in debugging

When a layer output diverges, it is possible to check:

```text
input_scale

weight_scale

output_scale

real_multiplier

multiplier

shift

Q6
```

before investigating the WebAssembly kernel.

---

# 200. Investigation example

If TFLite and WASM diverge in a convolution:

```text
1. check scales
2. check real_multiplier
3. check quantize_multiplier()
4. check serialized multiplier
5. check serialized shift
6. check pointers
7. check the requantization algorithm in WAT
```

This allows the problem to be isolated.

---

# 201. Separating formula and storage

The module has two conceptual phases:

```text
CALCULATION
   ↓
multipliers
shifts
Q6

SERIALIZATION
   ↓
mul_blob
shift_blob
q6_blob
```

This is better than directly mixing calculation with WAT generation.

---

# 202. Architectural benefit

In principle, the result could be consumed by a backend other than WAT.

For example:

```text
quantization.py
       │
       ├──→ WAT generator
       ├──→ C generator
       └──→ analysis tool
```

because its output is not a WebAssembly-specific string.

---

# 203. Complete module view

```text
                    TFLite
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    tensor metadata          op metadata
          │                       │
          └───────────┬───────────┘
                      ▼
             quantization.py
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
   multiplier        shift           Q6
       │              │              │
       ▼              ▼              ▼
   mul_vals       shift_vals      q6_vals
       │              │              │
       ▼              ▼              ▼
   mul_blob       shift_blob      q6_blob
       │              │              │
       └──────────────┼──────────────┘
                      ▼
                 memory.py
                      │
                      ▼
              layer_params.py
                      │
                      ▼
                  params_blob
                      │
                      ▼
                     WASM
```

---

# 204. Summary

`quantization.py` converts TFLite's mathematical quantization representation into one suitable for integer execution in the WebAssembly runtime.

For operations such as:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

the central point is:

```text
real_multiplier[c]
=
input_scale
×
weight_scale[c]
÷
output_scale
```

This value is converted into:

```text
multiplier[c]
+
shift[c]
```

by:

```python
quantize_multiplier()
```

The quantized representation of the following is also calculated:

```text
6.0
```

producing:

```text
Q6[c]
```

for use with `ReLU6`.

Parameters are organized into three contiguous tables:

```text
MUL
SHIFT
Q6
```

and each operation receives offsets indicating where its values start.

For `SOFTMAX`, the module uses its own preparation involving:

```text
input_scale
beta
integer_bits
input_left_shift
multiplier
shift
```

while `ADD` uses an independent function that transforms the two input scales and output scale into:

```text
mul_a / shift_a
mul_b / shift_b
output_mul / output_shift
```

Thus, by the end of this stage, the pipeline no longer has only abstract quantization metadata: it has **serializable integer tables**, directly suited to placement in WebAssembly linear memory and use by inference kernels.
