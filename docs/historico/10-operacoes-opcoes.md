[English](10-operacoes-opcoes.md) | [Português (Brasil)](10-operacoes-opcoes.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body has been preserved in the Portuguese edition.

# 10 — Reading operator options (`operator_operations.py`)

## 1. Module purpose

`extractor/operator_operations.py` interprets the specific options stored in TFLite operators.

The graph tells us that an operation is, for example:

```text
CONV_2D
```

but does not yet specify:

```text
vertical stride
horizontal stride
vertical dilation
horizontal dilation
padding
fused activation
```

Similarly, knowing that an operation is:

```text
DEPTHWISE_CONV_2D
```

does not automatically specify:

```text
depth multiplier
```

These values are stored in each operator's `BuiltinOptions`.

This module performs the transformation:

```text
TFLite BuiltinOptions
          │
          ▼
operator_operations.py
          │
          ├── stride_h
          ├── stride_w
          ├── dil_h
          ├── dil_w
          ├── padding_kind
          ├── activation
          └── depth_mult
```

The module also implements:

```python
same_padding(...)
```

which explicitly calculates the padding needed to reproduce `SAME` semantics.

---

# 2. Current code

The module uses these TFLite binding structures:

```python
from tflite import (
    ActivationFunctionType,
    AddOptions,
    Padding,
    Conv2DOptions,
    DepthwiseConv2DOptions,
    FullyConnectedOptions,
)
```

It defines three internal activation codes:

```python
ACT_NONE = 0
ACT_RELU = 1
ACT_RELU6 = 3
```

The main functions are:

```text
parse_fused_activation()

parse_add_options()

padding_is_same()

parse_conv2d_options()

parse_dwconv2d_options()

parse_fc_options()

same_padding()
```

---

# 3. Architectural role

This module translates between:

```text
TFLite representation
```

and:

```text
internal runtime representation
```

TFLite uses objects such as:

```text
Conv2DOptions
DepthwiseConv2DOptions
FullyConnectedOptions
AddOptions
```

The rest of the extractor prefers simple values:

```python
stride_h = 1
stride_w = 1

dil_h = 1
dil_w = 1

padding_kind = 0

activation = ACT_RELU6
```

Thus:

```text
TFLite FlatBuffer
       │
       ▼
operator_operations.py
       │
       ▼
simple integers and booleans
       │
       ▼
layer_params.py
```

---

# 4. Why separate this logic?

Without this module, `layer_params.py` would need code like:

```text
read BuiltinOptions
instantiate Conv2DOptions
initialize FlatBuffer
read stride
read dilation
read padding
read fused activation
```

for each operation.

This would mix two responsibilities:

```text
how to interpret TFLite
```

and:

```text
how to construct LayerParam
```

The current division is:

```text
operator_operations.py
    ↓
interprets TFLite options

layer_params.py
    ↓
uses the already interpreted values
```

---

# 5. Activation constants

The module defines:

```python
ACT_NONE = 0
ACT_RELU = 1
ACT_RELU6 = 3
```

These values form the internal representation used by the runtime.

---

# 6. Meaning

```text
ACT_NONE = 0
```

represents:

```text
no fused activation
```

---

```text
ACT_RELU = 1
```

represents:

```text
ReLU
```

---

```text
ACT_RELU6 = 3
```

represents:

```text
ReLU6
```

---

# 7. Fused activation

In TFLite, certain operations can incorporate an activation directly.

Conceptually:

```text
CONV_2D
   ↓
ReLU6
```

may be represented as a single operation:

```text
CONV_2D
fused_activation = RELU6
```

Instead of two independent operators.

---

# 8. Why does this matter to the runtime?

If the operation has:

```text
ReLU6
```

fused into it, the kernel must apply appropriate saturation before writing the output.

This information must therefore reach `LayerParam`.

Flow:

```text
TFLite
   │
   └── FusedActivationFunction()
                │
                ▼
parse_fused_activation()
                │
                ▼
ACT_RELU6
                │
                ▼
LayerParam.act
                │
                ▼
WASM kernel
```

---

# 9. The `parse_fused_activation()` function

The first function is:

```python
def parse_fused_activation(
    activation_value,
):
```

It normalizes the different ways the binding may represent an activation.

---

# 10. First strategy

The function first tries comparing with:

```python
ActivationFunctionType.NONE
```

```python
ActivationFunctionType.RELU
```

```python
ActivationFunctionType.RELU6
```

---

# 11. Example

If:

```python
activation_value == (
    ActivationFunctionType.RELU6
)
```

the return value will be:

```python
ACT_RELU6
```

---

# 12. Why use `try/except`?

The Python TFLite binding may differ in packaging or structure across versions.

The code therefore first tries to use the semantics of:

```text
ActivationFunctionType
```

but has a second path based directly on integer values.

---

# 13. Numeric fallback

If the first attempt fails, the code tests:

```python
if activation_value == 0:
    return ACT_NONE

if activation_value == 1:
    return ACT_RELU

if activation_value == 3:
    return ACT_RELU6
```

---

# 14. Two compatibility layers

Therefore:

```text
first attempt
      ↓
TFLite binding enum

second attempt
      ↓
numeric value
```

This makes the routine less dependent on exactly how the Python package exposes the enum.

---

# 15. Unknown activation

If no case is recognized:

```python
return ACT_NONE
```

In other words, the current behavior is conservative:

```text
unknown activation
        ↓
ACT_NONE
```

---

# 16. Important consequence

This strategy avoids stopping the extractor.

However, for a future model containing a different fused activation supported by TFLite but not implemented by the runtime, the current code could silently convert it to:

```text
ACT_NONE
```

This is an important feature of the current implementation.

---

# 17. Possible future development

In a more generic tool, the following might be preferable:

```text
known activation
    ↓
convert

unknown activation
    ↓
RuntimeError
```

This would prevent generating an artifact with semantics different from the original model.

The current code preserves existing behavior.

---

# 18. The `parse_add_options()` function

The function:

```python
def parse_add_options(op):
```

extracts the fused activation of an:

```text
ADD
```

---

# 19. Why does ADD have options?

An `ADD` may conceptually represent:

```text
A + B
```

but may also have:

```text
A + B
  ↓
ReLU
```

or:

```text
A + B
  ↓
ReLU6
```

as a fused activation.

---

# 20. Getting `BuiltinOptions`

The function starts with:

```python
builtin_options = (
    op.BuiltinOptions()
)
```

This object represents the position of that operator's specific data within the FlatBuffer.

---

# 21. Checking `Bytes` and `Pos`

Then:

```python
if (
    hasattr(
        builtin_options,
        "Bytes",
    )
    and hasattr(
        builtin_options,
        "Pos",
    )
):
```

The parser needs both pieces of information to initialize the correct options object.

---

# 22. Conceptual meaning

The object:

```text
builtin_options
```

acts as a reference to a region in the TFLite buffer.

The fields:

```text
Bytes
Pos
```

allow:

```text
AddOptions
```

to interpret that region according to its schema.

---

# 23. Compatibility when constructing `AddOptions`

The code:

```python
options = (
    AddOptions.AddOptions()
    if hasattr(
        AddOptions,
        "AddOptions",
    )
    else AddOptions()
)
```

supports two possible binding forms.

---

# 24. First form

In some environments:

```text
AddOptions
    │
    └── AddOptions
```

Then:

```python
AddOptions.AddOptions()
```

creates the structure.

---

# 25. Second form

In others:

```python
AddOptions()
```

is already the instantiable class itself.

---

# 26. Same issue observed during model loading

This logic resembles that in:

```text
model_loader.py
```

where the binding could expose:

```text
GetRootAsModel
```

at different levels.

The objective is again to reduce dependence on a single Python package organization.

---

# 27. Initializing options

Then:

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

Now:

```text
options
```

starts interpreting that FlatBuffer region as:

```text
AddOptions
```

---

# 28. Reading the activation

Then:

```python
options
.FusedActivationFunction()
```

is converted to an integer:

```python
int(...)
```

and passed to:

```python
parse_fused_activation(...)
```

---

# 29. ADD return value

The final result is one of the codes:

```text
ACT_NONE

ACT_RELU

ACT_RELU6
```

---

# 30. Read failure

If any stage raises an exception:

```python
except Exception:
    pass
```

and the function returns:

```python
ACT_NONE
```

---

# 31. Fallback approach

This module follows the pattern:

```text
try to extract the actual option
        │
        ├── success → use value
        │
        └── failure → use the chosen default
```

For ADD:

```text
default = ACT_NONE
```

---

# 32. The `padding_is_same()` function

The function:

```python
def padding_is_same(
    padding_value,
):
```

normalizes identification of padding:

```text
SAME
```

---

# 33. First comparison

The code tries:

```python
padding_value
==
Padding.SAME
```

---

# 34. Numeric fallback

If accessing the enum fails:

```python
except Exception:
    return padding_value == 0
```

Thus, the numeric representation:

```text
0
```

is treated as:

```text
SAME
```

in the current implementation.

---

# 35. Boolean result

The function returns:

```text
True
```

for `SAME`,

or:

```text
False
```

for another padding type.

---

# 36. Why use a separate function?

Without it, both:

```text
CONV_2D
```

and:

```text
DEPTHWISE_CONV_2D
```

would have to repeat enum compatibility logic.

Centralizing it avoids duplication.

---

# 37. Internal padding convention

The convolution functions convert the boolean into:

```python
padding_kind = (
    0 if padding_same
    else 1
)
```

Thus:

```text
padding_kind = 0
    ↓
SAME

padding_kind = 1
    ↓
non-SAME
```

In the current flow, the second case corresponds to the operation's alternative for non-`SAME` padding.

---

# 38. Important

The value:

```text
0
```

in `padding_kind`

is not necessarily used as the TFLite enum itself.

It is an internal extractor/runtime convention.

The translation is:

```text
TFLite padding
      ↓
padding_is_same()
      ↓
boolean
      ↓
internal padding_kind
```

---

# 39. The `parse_conv2d_options()` function

This function interprets options for:

```text
CONV_2D
```

---

# 40. Returned values

The normal return value contains:

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
)
```

---

# 41. Visual representation

```text
Conv2DOptions
      │
      ├── StrideH
      ├── StrideW
      ├── DilationHFactor
      ├── DilationWFactor
      ├── Padding
      └── FusedActivationFunction
             │
             ▼
      simple Python tuple
```

---

# 42. Getting options

Again:

```python
builtin_options = (
    op.BuiltinOptions()
)
```

followed by checking:

```text
Bytes
Pos
```

---

# 43. Binding compatibility

The structure is created with:

```python
options = (
    Conv2DOptions.Conv2DOptions()
    if hasattr(
        Conv2DOptions,
        "Conv2DOptions",
    )
    else Conv2DOptions()
)
```

The objective is to support both known binding forms.

---

# 44. Initialization

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

After this call, the specific methods can be queried.

---

# 45. `stride_h`

The vertical stride is:

```python
stride_h = int(
    options.StrideH()
)
```

---

# 46. `stride_w`

The horizontal stride:

```python
stride_w = int(
    options.StrideW()
)
```

---

# 47. What is stride?

Stride indicates how far the kernel advances between consecutive positions.

Example:

```text
stride = 1
```

means:

```text
position 0
position 1
position 2
position 3
...
```

---

# 48. Stride 2

With:

```text
stride = 2
```

the kernel advances through:

```text
position 0
position 2
position 4
position 6
...
```

This reduces the output's spatial size.

---

# 49. Independent strides

The format allows:

```text
stride_h
```

and:

```text
stride_w
```

to differ.

Although common architectures often use:

```text
stride_h == stride_w
```

the extractor does not enforce this.

---

# 50. Dilation

The function tries to read:

```python
options.DilationHFactor()
```

and:

```python
options.DilationWFactor()
```

---

# 51. Dilation fallback

If this read fails:

```python
dil_h = 1
dil_w = 1
```

---

# 52. Why is `1` the default?

Dilation 1 represents:

```text
a normal kernel
```

with no additional spacing between its elements.

---

# 53. Example with kernel size 3

For:

```text
kernel = 3
dilation = 1
```

the points used are:

```text
x x x
```

---

# 54. Dilation 2

For:

```text
kernel = 3
dilation = 2
```

conceptually:

```text
x . x . x
```

The kernel has three coefficients but covers a larger effective region.

---

# 55. Padding

The code reads:

```python
options.Padding()
```

converts to an integer, and passes it to:

```python
padding_is_same(...)
```

---

# 56. Result

```python
padding_same = (
    padding_is_same(...)
)
```

produces:

```text
True
```

or:

```text
False
```

---

# 57. Conversion to `padding_kind`

Then:

```python
padding_kind = (
    0 if padding_same
    else 1
)
```

---

# 58. Activation

The fused activation is read through:

```python
parse_fused_activation(
    int(
        options
        .FusedActivationFunction()
    )
)
```

---

# 59. Normal return value

The function returns:

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
)
```

---

# 60. Example

A convolution may result in:

```python
(
    2,
    2,
    1,
    1,
    0,
    ACT_RELU6,
)
```

This represents:

```text
stride = 2 × 2

dilation = 1 × 1

padding = SAME

activation = ReLU6
```

---

# 61. `CONV_2D` fallback

If reading options fails entirely:

```python
return (
    1,
    1,
    1,
    1,
    1,
    ACT_NONE,
)
```

---

# 62. Interpreting the fallback

```text
stride_h = 1

stride_w = 1

dil_h = 1

dil_w = 1

padding_kind = 1

activation = NONE
```

---

# 63. Important feature

The fallback does not necessarily represent the model's original options.

It is simply the set of defaults chosen when options cannot be interpreted.

This avoids immediate failure, but may hide an incompatibility in a different model.

---

# 64. The `parse_dwconv2d_options()` function

This function is equivalent to the `CONV_2D` parser but interprets:

```text
DEPTHWISE_CONV_2D
```

and has an additional parameter:

```text
depth_multiplier
```

---

# 65. Return value

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
    depth_mult,
)
```

---

# 66. Constructing options

The class used is:

```text
DepthwiseConv2DOptions
```

again supporting compatibility between:

```python
DepthwiseConv2DOptions
.DepthwiseConv2DOptions()
```

and:

```python
DepthwiseConv2DOptions()
```

---

# 67. Stride and dilation

Reading follows the same process as for `CONV_2D`.

Therefore:

```text
StrideH
StrideW
DilationHFactor
DilationWFactor
```

have the same meaning.

---

# 68. `depth_mult`

The additional value is:

```python
depth_mult = int(
    options.DepthMultiplier()
)
```

---

# 69. What does the depth multiplier represent?

In depthwise convolution, filters are applied separately to input channels.

`depth_multiplier` specifies how many output channels are produced for each input channel.

Conceptually:

```text
Cout =
Cin × depth_multiplier
```

---

# 70. Example

If:

```text
Cin = 32
depth_multiplier = 1
```

then:

```text
Cout = 32
```

---

# 71. Example with multiplier 2

If:

```text
Cin = 32
depth_multiplier = 2
```

then:

```text
Cout = 64
```

---

# 72. MobileNetV2

In MobileNetV2's depthwise convolution pattern, the common case is:

```text
depth_multiplier = 1
```

but the parser preserves the value present in the model.

---

# 73. Padding and activation

They are processed exactly as in `CONV_2D`:

```text
Padding()
    ↓
padding_is_same()
    ↓
padding_kind
```

and:

```text
FusedActivationFunction()
    ↓
parse_fused_activation()
    ↓
activation
```

---

# 74. Depthwise fallback

If a failure occurs:

```python
return (
    1,
    1,
    1,
    1,
    1,
    ACT_NONE,
    1,
)
```

---

# 75. Interpretation

```text
stride = 1

dilation = 1

padding_kind = 1

activation = NONE

depth_multiplier = 1
```

---

# 76. The `parse_fc_options()` function

This function interprets options for:

```text
FULLY_CONNECTED
```

---

# 77. What is extracted?

In the current implementation, only:

```text
fused activation
```

is needed.

---

# 78. Constructing `FullyConnectedOptions`

The same compatibility technique is used:

```python
options = (
    FullyConnectedOptions
    .FullyConnectedOptions()
    if hasattr(
        FullyConnectedOptions,
        "FullyConnectedOptions",
    )
    else FullyConnectedOptions()
)
```

---

# 79. Initialization

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

---

# 80. Return value

Then:

```python
return (
    parse_fused_activation(
        int(
            options
            .FusedActivationFunction()
        )
    )
)
```

---

# 81. Fallback

On failure:

```python
return ACT_NONE
```

---

# 82. Comparing parsing functions

| Operation | Extracted values |
| ------------------- | ----------------------------------------------------- |
| `ADD` | activation |
| `CONV_2D` | stride, dilation, padding, activation |
| `DEPTHWISE_CONV_2D` | stride, dilation, padding, activation, depth multiplier |
| `FULLY_CONNECTED` | activation |

---

# 83. Why are `SOFTMAX`, `MEAN`, and `QUANTIZE` absent?

Because their required information is handled elsewhere in the pipeline.

This file focuses on specific options of operations that require these `BuiltinOptions` objects.

---

# 84. The `same_padding()` function

The last function is mathematically different from the others.

It does not read the FlatBuffer.

It directly receives:

```text
input dimensions
kernel
stride
dilation
```

and calculates:

```text
explicit padding
+
output shape
```

---

# 85. Signature

```python
def same_padding(
    in_h,
    in_w,
    kernel_h,
    kernel_w,
    stride_h,
    stride_w,
    dil_h=1,
    dil_w=1,
):
```

---

# 86. Inputs

### `in_h`

Input height.

### `in_w`

Input width.

### `kernel_h`

Kernel height.

### `kernel_w`

Kernel width.

### `stride_h`

Vertical stride.

### `stride_w`

Horizontal stride.

### `dil_h`

Vertical dilation.

### `dil_w`

Horizontal dilation.

---

# 87. Outputs

The function returns:

```python
(
    pad_top,
    pad_bottom,
    pad_left,
    pad_right,
    out_h,
    out_w,
)
```

---

# 88. Why explicitly calculate padding?

In TFLite, knowing only:

```text
padding = SAME
```

does not directly specify how many positions must be added at:

```text
top
bottom
left
right
```

The WASM kernel needs concrete values.

Therefore:

```text
SAME
   ↓
same_padding()
   ↓
pad_top
pad_bottom
pad_left
pad_right
```

---

# 89. Calculating output height

First:

```python
out_h = (
    in_h + stride_h - 1
) // stride_h
```

This is equivalent to:

```text
out_h =
ceil(
    in_h / stride_h
)
```

for positive integers.

---

# 90. Why does this formula implement `ceil`?

Consider:

```text
in_h = 5
stride_h = 2
```

Then:

```text
(5 + 2 - 1) // 2
=
6 // 2
=
3
```

And:

```text
ceil(5 / 2)
=
3
```

---

# 91. Output width

The same is done:

```python
out_w = (
    in_w + stride_w - 1
) // stride_w
```

---

# 92. Example with 128 × 128 input and stride 2

```text
out_h =
ceil(128 / 2)
=
64
```

```text
out_w =
ceil(128 / 2)
=
64
```

---

# 93. Effective kernel

Dilation changes the area effectively covered by the kernel.

The code calculates:

```python
effective_kernel_h = (
    (kernel_h - 1)
    * dil_h
    + 1
)
```

---

# 94. Effective width

Similarly:

```python
effective_kernel_w = (
    (kernel_w - 1)
    * dil_w
    + 1
)
```

---

# 95. Kernel size 3 with dilation 1

```text
effective_kernel =
(3 - 1) × 1 + 1
=
3
```

No change.

---

# 96. Kernel size 3 with dilation 2

```text
effective_kernel =
(3 - 1) × 2 + 1
=
5
```

Visually:

```text
x . x . x
```

Three coefficients cover five positions.

---

# 97. Kernel size 3 with dilation 3

```text
effective_kernel =
(3 - 1) × 3 + 1
=
7
```

Visually:

```text
x . . x . . x
```

---

# 98. Total vertical padding

Then:

```python
pad_h_total = max(
    0,
    (
        (out_h - 1)
        * stride_h
        + effective_kernel_h
        - in_h
    ),
)
```

---

# 99. Formula intuition

The term:

```text
(out_h - 1) × stride_h
```

represents the starting position of the last kernel.

Adding:

```text
effective_kernel_h
```

gives the extent that kernel must reach.

Subtracting:

```text
in_h
```

reveals how much extends beyond the original input.

---

# 100. Using `max(0, ...)`

This ensures that:

```text
total padding
```

is never negative.

If the geometry requires no padding:

```text
padding = 0
```

---

# 101. Horizontal padding

The same calculation applies:

```python
pad_w_total = max(
    0,
    (
        (out_w - 1)
        * stride_w
        + effective_kernel_w
        - in_w
    ),
)
```

---

# 102. Vertical split

Then:

```python
pad_top = (
    pad_h_total // 2
)
```

and:

```python
pad_bottom = (
    pad_h_total - pad_top
)
```

---

# 103. Even padding

If:

```text
pad_h_total = 2
```

then:

```text
pad_top = 1

pad_bottom = 1
```

---

# 104. Odd padding

If:

```text
pad_h_total = 1
```

then:

```text
pad_top = 0

pad_bottom = 1
```

---

# 105. Consequence

When total padding is odd, the extra element goes to:

```text
bottom
```

in the vertical dimension.

---

# 106. Horizontal split

The same logic is used:

```python
pad_left = (
    pad_w_total // 2
)
```

```python
pad_right = (
    pad_w_total - pad_left
)
```

---

# 107. Odd horizontal padding

If:

```text
pad_w_total = 1
```

then:

```text
pad_left = 0

pad_right = 1
```

---

# 108. Example 1 — 3×3 kernel, stride 1

Consider:

```text
input = 128 × 128

kernel = 3 × 3

stride = 1 × 1

dilation = 1 × 1
```

---

# 109. Output

```text
out_h =
ceil(128 / 1)
=
128
```

```text
out_w =
128
```

---

# 110. Effective kernel

```text
effective_kernel_h = 3

effective_kernel_w = 3
```

---

# 111. Vertical padding

```text
pad_h_total =
(128 - 1) × 1
+ 3
- 128

=
127 + 3 - 128

=
2
```

---

# 112. Split

```text
pad_top = 1

pad_bottom = 1
```

---

# 113. Horizontal

Similarly:

```text
pad_left = 1

pad_right = 1
```

---

# 114. Result

```python
(
    1,
    1,
    1,
    1,
    128,
    128,
)
```

---

# 115. Visual representation

```text
128×128 input
       │
       │ SAME
       ▼

padding:
top    = 1
bottom = 1
left   = 1
right  = 1

       │
       ▼
128×128 output
```

---

# 116. Example 2 — 3×3 kernel, stride 2

Consider:

```text
input = 128 × 128

kernel = 3 × 3

stride = 2 × 2
```

---

# 117. Output shape

```text
out_h =
ceil(128 / 2)
=
64
```

and:

```text
out_w = 64
```

---

# 118. Total padding

```text
pad_h_total =
(64 - 1) × 2
+ 3
- 128

=
126 + 3 - 128

=
1
```

---

# 119. Vertical split

```text
pad_top = 0

pad_bottom = 1
```

---

# 120. Horizontal

```text
pad_left = 0

pad_right = 1
```

---

# 121. Result

```python
(
    0,
    1,
    0,
    1,
    64,
    64,
)
```

---

# 122. Asymmetry is expected

In this example:

```text
top ≠ bottom
```

and:

```text
left ≠ right
```

This is not an error.

When the required padding is odd, its distribution must be asymmetric.

---

# 123. Example 3 — dilation

Consider:

```text
input = 10 × 10

kernel = 3 × 3

stride = 1

dilation = 2
```

---

# 124. Effective kernel

```text
effective_kernel =
(3 - 1) × 2 + 1

=
5
```

---

# 125. SAME output

```text
out_h = 10

out_w = 10
```

---

# 126. Total padding

```text
pad_total =
(10 - 1)
+ 5
- 10

=
4
```

---

# 127. Split

```text
top = 2

bottom = 2

left = 2

right = 2
```

Dilation increases the required padding because it increases effective kernel size.

---

# 128. Relationship with `padding_kind`

`same_padding()` does not receive:

```text
padding_kind
```

It is called only after higher-level code determines that the operation requires `SAME`.

The subsequent logic is conceptually:

```text
padding_kind == SAME?
        │
        ├── yes
        │    ↓
        │ same_padding(...)
        │    ↓
        │ top/bottom/left/right
        │
        └── no
             ↓
           zero padding
           or corresponding handling
```

---

# 129. Relationship to `layer_params.py`

`layer_params.py` uses these values to fill fields such as:

```text
stride_h
stride_w

dil_h
dil_w

pad_t
pad_b
pad_l
pad_r

act
```

---

# 130. Transformation example

TFLite provides:

```text
CONV_2D

StrideH = 2
StrideW = 2

Dilation = 1

Padding = SAME

FusedActivation = RELU6
```

`operator_operations.py` returns:

```text
stride_h = 2
stride_w = 2

dil_h = 1
dil_w = 1

padding_kind = 0

activation = ACT_RELU6
```

Then:

```text
same_padding()
```

may produce:

```text
pad_t = 0
pad_b = 1
pad_l = 0
pad_r = 1
```

Finally, `layer_params.py` combines everything.

---

# 131. Complete flow

```text
TFLite Operator
      │
      ▼
BuiltinOptions
      │
      ▼
operator_operations.py
      │
      ├── stride
      ├── dilation
      ├── padding kind
      ├── activation
      └── depth multiplier
      │
      ▼
same_padding()
      │
      ├── pad_top
      ├── pad_bottom
      ├── pad_left
      ├── pad_right
      ├── out_h
      └── out_w
      │
      ▼
layer_params.py
```

---

# 132. Why calculate `out_h` and `out_w` here?

TFLite already contains the output shape, but the runtime needs kernel geometry consistent with:

```text
input
kernel
stride
dilation
padding
```

The function returns:

```text
out_h
out_w
```

as part of the mathematical calculation of `SAME`.

This allows using the same logic to fill the execution structure.

---

# 133. Tensor shape versus calculated shape

There are therefore two possible sources:

```text
Tensor.ShapeAsNumpy()
```

and:

```text
same_padding(...)
```

The first describes the model.

The second derives geometry from operation parameters.

This redundancy may also support future validation.

---

# 134. Possible future validation

We could check:

```text
calculated out_h
==
output tensor height
```

and:

```text
calculated out_w
==
output tensor width
```

Otherwise:

```text
RuntimeError
```

This would detect parsing or implementation inconsistencies.

---

# 135. Exception handling

A notable feature of this module is its use of:

```python
except Exception:
    pass
```

in several parsers.

---

# 136. Benefit

This improves compatibility across binding versions.

The pipeline does not require every method to be available in exactly the same form.

---

# 137. Cost of this strategy

An unexpected exception may also be silently converted into a default value.

Example:

```text
error interpreting Conv2DOptions
       ↓
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
```

---

# 138. Implication

For the current model, whose output was validated, this strategy preserves the original code's behavior.

A future generic tool should distinguish:

```text
known binding difference
```

from:

```text
actual model error
```

---

# 139. Possible future strategy

Instead of:

```python
except Exception:
    pass
```

we could catch only specific exceptions.

Or use explicit validations:

```text
missing BuiltinOptions
    ↓
fallback allowed

missing required field
    ↓
error
```

---

# 140. Why not change it now?

This refactoring and documentation stage first aims to:

```text
preserve the behavior
```

and make existing decisions explicit.

Changing all fallbacks at the same time would make it difficult to determine whether later differences come from:

```text
refactoring
```

or:

```text
semantic change
```

---

# 141. Separating parsing and kernel semantics

This module knows:

```text
StrideH
StrideW
Dilation
Padding
Activation
DepthMultiplier
```

but does not know:

```text
how to perform convolution in WAT
```

This separation matters.

---

# 142. It does not execute convolution

`parse_conv2d_options()` only produces:

```text
parameters
```

There is no:

```text
loop over H
loop over W
loop over channels
weight × input multiplication
accumulator
requantization
```

These operations belong to the WAT runtime.

---

# 143. Same for depthwise

This module finds:

```text
depth_multiplier
```

but does not decide how to index:

```text
input channel
output channel
weight channel
```

That belongs to the `DEPTHWISE_CONV_2D` kernel.

---

# 144. And for activation

The module returns:

```text
ACT_RELU6
```

but does not calculate:

```text
min(max(x, 0), 6)
```

or its quantized version.

Execution belongs to the runtime.

---

# 145. Relationship with `quantization.py`

When:

```text
activation = ACT_RELU6
```

execution also depends on:

```text
Q6
```

calculated by `quantization.py`.

Therefore:

```text
operator_operations.py
        │
        └── "this layer uses ReLU6"

quantization.py
        │
        └── "this is the quantized value corresponding to 6"

layer_params.py
        │
        └── combines both
```

---

# 146. Example

A layer may receive:

```text
activation = ACT_RELU6
```

and:

```text
q6_ptr = Q6 table address
```

The kernel then knows to:

```text
apply the upper bound
using the corresponding Q6
```

---

# 147. Relationship with flags

The module does not directly define:

```text
FLAG_PADDING_SAME
```

This representation belongs to the `LayerParam` stage.

Here it only produces:

```text
padding_kind
```

---

# 148. Subsequent conversion

Conceptually:

```text
padding_kind == 0
       ↓
SAME
       ↓
FLAG_PADDING_SAME
```

This transformation belongs to layer construction.

---

# 149. Why not return the flag directly?

Because this module should remain as close as possible to the operation's concept:

```text
what is the padding type?
```

Choosing bits within:

```text
LayerParam.flags
```

is specific to the runtime representation.

---

# 150. Modular structure

```text
operator_operations.py
      ↓
option semantics

layer_params.py
      ↓
option encoding

params_blob.py
      ↓
serialization of the encoding

WAT
      ↓
execution
```

---

# 151. Current fallback summary

## Unknown activation

```text
ACT_NONE
```

## Unreadable ADD options

```text
ACT_NONE
```

## Unreadable CONV options

```text
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
```

## Unreadable DEPTHWISE options

```text
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
depth_multiplier = 1
```

## Unreadable FC options

```text
ACT_NONE
```

---

# 152. Why document defaults?

Because they directly affect the generated artifact.

If an option is not read correctly, the runtime does not receive:

```text
None
```

It receives concrete values.

The resulting behavior therefore remains defined, although it may not match the intended model.

---

# 153. Expected invariants

For supported operations in the current model, we expect:

```text
stride_h >= 1

stride_w >= 1

dil_h >= 1

dil_w >= 1
```

---

# 154. For depthwise

Also:

```text
depth_mult >= 1
```

---

# 155. Activation

The current runtime expects one of:

```text
ACT_NONE

ACT_RELU

ACT_RELU6
```

---

# 156. Padding

The current code reduces the relevant state to:

```text
SAME
```

or:

```text
non-SAME
```

through:

```python
padding_is_same()
```

---

# 157. `same_padding()` and positive values

The function assumes consistent dimensions such as:

```text
in_h > 0

in_w > 0

kernel_h > 0

kernel_w > 0

stride_h > 0

stride_w > 0

dil_h > 0

dil_w > 0
```

The code does not explicitly validate these conditions.

---

# 158. Zero stride

For example, if:

```text
stride_h = 0
```

the function would attempt division by zero.

This is not expected in a valid TFLite model used by the project.

---

# 159. Zero kernel size

Likewise, a zero-sized kernel dimension would produce meaningless geometry.

The current implementation does not include this validation.

---

# 160. Complete CONV example

Suppose:

```text
input:
1 × 128 × 128 × 3

kernel:
3 × 3

stride:
2 × 2

dilation:
1 × 1

padding:
SAME

activation:
ReLU6
```

---

# 161. Parsing

`parse_conv2d_options()` returns:

```python
(
    2,
    2,
    1,
    1,
    0,
    ACT_RELU6,
)
```

---

# 162. Padding

`same_padding()` receives:

```python
same_padding(
    128,
    128,
    3,
    3,
    2,
    2,
    1,
    1,
)
```

---

# 163. Result

```text
pad_top = 0

pad_bottom = 1

pad_left = 0

pad_right = 1

out_h = 64

out_w = 64
```

---

# 164. Information passed to `LayerParam`

Conceptually:

```text
stride_h = 2
stride_w = 2

dil_h = 1
dil_w = 1

pad_t = 0
pad_b = 1
pad_l = 0
pad_r = 1

activation = ACT_RELU6

out_h = 64
out_w = 64
```

---

# 165. Runtime

This information tells the WAT kernel:

```text
where to position the kernel

how far to advance

when to access padding

how many positions to produce

which activation to apply
```

---

# 166. Complete Depthwise example

Suppose:

```text
input:
1 × 64 × 64 × 32

kernel:
3 × 3

stride:
1

dilation:
1

padding:
SAME

depth_multiplier:
1

activation:
ReLU6
```

---

# 167. Parsing

```python
(
    1,
    1,
    1,
    1,
    0,
    ACT_RELU6,
    1,
)
```

---

# 168. Padding

```text
top = 1
bottom = 1
left = 1
right = 1
```

---

# 169. Spatial output

```text
64 × 64
```

---

# 170. Channel count

With:

```text
Cin = 32

depth_multiplier = 1
```

we have:

```text
Cout = 32
```

---

# 171. FC example

A `FULLY_CONNECTED` may have:

```text
fused activation = NONE
```

Then:

```python
parse_fc_options(...)
```

returns:

```python
ACT_NONE
```

This representation has no stride, dilation, or padding.

---

# 172. ADD example

If:

```text
ADD
+
ReLU6
```

are fused:

```python
parse_add_options(...)
```

returns:

```python
ACT_RELU6
```

This information will be used with the specific quantization parameters calculated for ADD.

---

# 173. What this module deliberately does not do

`operator_operations.py` does not:

```text
read weights

read bias

compute quantization

calculate multiplier

calculate shift

calculate Q6

allocate slots

calculate memory addresses

serialize LayerParam

generate WAT
```

---

# 174. Exact responsibility

It answers:

```text
what operational options
describe how this layer should execute?
```

---

# 175. Types of information handled

```text
geometry
    ↓
stride
dilation
padding

activation
    ↓
NONE
RELU
RELU6

depthwise
    ↓
depth_multiplier
```

---

# 176. Relationship with other modules

```text
TFLite
  │
  ▼
operator_operations.py
  │
  ├── geometry
  ├── activation
  └── padding
  │
  ▼
layer_params.py
```

While:

```text
quantization.py
  │
  ├── multiplier
  ├── shift
  └── Q6
  │
  ▼
layer_params.py
```

And:

```text
memory.py
  │
  └── addresses
       │
       ▼
layer_params.py
```

---

# 177. `layer_params.py` as the point of convergence

This shows why the next module is especially important.

It combines:

```text
graph
slots
tensor mapping
weights
quantization
memory
operator options
```

into one structure.

Visually:

```text
                graph.py
                   │
                slots.py
                   │
           tensor_mapping.py
                   │
                   ▼
weights.py ───► layer_params.py ◄── operator_operations.py
                   ▲
                   │
quantization.py ───┤
                   │
memory.py ─────────┘
```

---

# 178. Possible naming issue

The name:

```text
operator_operations.py
```

works, but semantically the module mainly parses:

```text
operator options
```

and calculates padding.

A name such as:

```text
operator_options.py
```

would also describe its role well.

Documentation must follow the name actually used by the project while it remains:

```text
operator_operations.py
```

---

# 179. Function summary

| Function | Responsibility |
| -------------------------- | --------------------------------------------- |
| `parse_fused_activation()` | Convert TFLite activation to internal code |
| `parse_add_options()` | Extract ADD activation |
| `padding_is_same()` | Identify SAME padding |
| `parse_conv2d_options()` | Extract CONV_2D options |
| `parse_dwconv2d_options()` | Extract DEPTHWISE_CONV_2D options |
| `parse_fc_options()` | Extract FULLY_CONNECTED activation |
| `same_padding()` | Calculate explicit padding and output shape |

---

# 180. Constant summary

| Constant | Meaning |
| ----------- | ------------------------ |
| `ACT_NONE` | No fused activation |
| `ACT_RELU` | ReLU |
| `ACT_RELU6` | ReLU6 |

---

# 181. CONV parsing summary

```text
Conv2DOptions
      │
      ├── StrideH
      ├── StrideW
      ├── DilationH
      ├── DilationW
      ├── Padding
      └── Activation
             │
             ▼
(
 stride_h,
 stride_w,
 dil_h,
 dil_w,
 padding_kind,
 activation
)
```

---

# 182. Depthwise parsing summary

```text
DepthwiseConv2DOptions
          │
          ├── StrideH
          ├── StrideW
          ├── DilationH
          ├── DilationW
          ├── Padding
          ├── Activation
          └── DepthMultiplier
                 │
                 ▼
(
 stride_h,
 stride_w,
 dil_h,
 dil_w,
 padding_kind,
 activation,
 depth_mult
)
```

---

# 183. `same_padding()` summary

```text
input
kernel
stride
dilation
    │
    ▼
effective kernel
    │
    ▼
SAME output shape
    │
    ▼
total padding
    │
    ├── top
    ├── bottom
    ├── left
    └── right
```

---

# 184. Main formulas

## Output shape

```text
out_h =
ceil(in_h / stride_h)

out_w =
ceil(in_w / stride_w)
```

Implemented as:

```text
(in + stride - 1) // stride
```

---

## Effective kernel

```text
effective_kernel_h =
(kernel_h - 1) × dil_h + 1
```

```text
effective_kernel_w =
(kernel_w - 1) × dil_w + 1
```

---

## Total padding

```text
pad_h_total =
max(
    0,
    (out_h - 1) × stride_h
    + effective_kernel_h
    - in_h
)
```

```text
pad_w_total =
max(
    0,
    (out_w - 1) × stride_w
    + effective_kernel_w
    - in_w
)
```

---

## Distribution

```text
pad_top =
pad_h_total // 2
```

```text
pad_bottom =
pad_h_total - pad_top
```

```text
pad_left =
pad_w_total // 2
```

```text
pad_right =
pad_w_total - pad_left
```

---

# 185. Summary

`operator_operations.py` converts the specific configuration stored in TFLite operators into a simple representation used by the rest of the extractor.

Its first responsibility is to interpret:

```text
fused activation
```

normalizing:

```text
NONE
RELU
RELU6
```

to the internal codes:

```text
ACT_NONE
ACT_RELU
ACT_RELU6
```

Its second responsibility is to interpret convolution geometry options:

```text
stride
dilation
padding
```

and, for depthwise convolution:

```text
depth_multiplier
```

Its third responsibility is to convert the abstract description:

```text
padding = SAME
```

into concrete values:

```text
pad_top
pad_bottom
pad_left
pad_right
out_h
out_w
```

that the WebAssembly kernel can use directly.

The module thus separates:

```text
the TFLite-specific schema
```

and:

```text
the runtime's operational representation
```

without knowing weights, quantization, memory, or the WAT code itself.

As a result, `layer_params.py` does not need to understand FlatBuffer details. It receives normalized values and can focus exclusively on assembling the binary structure consumed by the runtime.
