[English](12-params-blob.md) | [Português (Brasil)](12-params-blob.pt-BR.md)

> **Preserved historical document.** This text describes the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in Portuguese and translated here.

# 12 — LayerParam serialization (`params_blob.py`)

## 1. Module purpose

`extractor/params_blob.py` transforms the structured representation produced by `layer_params.py` into a contiguous binary block inserted directly into the WebAssembly module's linear memory.

Up to the previous module, each layer is represented by a Python dictionary such as:

```python
{
    "op_type": ...,
    "act": ...,
    "flags": ...,

    "in_slot": ...,
    "out_slot": ...,

    "in_h": ...,
    "in_w": ...,

    "cin": ...,
    "cout": ...,

    "kh": ...,
    "kw": ...,

    "w_off": ...,
    "b_off": ...,

    "mul_off": ...,
    "shift_off": ...,
    "q6_off": ...,

    ...
}
```

This representation works well for:

```text
calculation
validation
debug
report
```

but the WebAssembly runtime does not receive Python dictionaries.

It needs a fixed binary sequence:

```text
LayerParam 0
LayerParam 1
LayerParam 2
...
```

This module therefore performs:

```text
layer_params.py
      │
      ▼
Python dicts
      │
      ▼
params_blob.py
      │
      ├── validates slots
      ├── resolves pointers
      ├── packs 29 int32 values
      ├── concatenates structures
      └── adds padding
      │
      ▼
params_blob
      │
      ▼
wat_generator.py
      │
      ▼
WASM memory
```

---

# 2. Position in the pipeline

The complete workflow around this stage is:

```text
weights.py
   │
   └── weight and bias offsets

quantization.py
   │
   └── MUL / SHIFT / Q6 offsets

memory.py
   │
   └── absolute bases of these regions

layer_params.py
   │
   └── logical representation of each operation

         │
         ▼

    params_blob.py

         │
         ├── base + offset
         ├── pointers
         ├── struct.pack()
         └── binary blob

         │
         ▼

   wat_generator.py
```

This module therefore marks the boundary between:

```text
structured representation
```

and:

```text
binary representation
```

---

# 3. Imports

The file starts with:

```python
import struct
```

The `struct` library converts Python integer values to bytes using an exact binary layout.

The following are also imported from `layer_params.py`:

```python
LP_FMT
LP_SIZE
```

along with every operation code and flag needed to interpret the structures.

---

# 4. `LP_FMT`

In the previous module:

```python
LP_FMT = "<" + "i" * 29
```

Therefore:

```text
<
    little-endian

i
    signed int32

29
    number of values
```

Each `LayerParam` occupies:

```text
29 × 4
=
116 bytes
```

---

# 5. `LP_SIZE`

We also import:

```python
LP_SIZE
```

which corresponds to:

```text
116 bytes
```

in the current format.

This constant verifies that each call to:

```python
struct.pack()
```

produced exactly the expected size.

---

# 6. Known operations

The imports include:

```text
OP_CONV
OP_DW
OP_FC
OP_ADD
OP_MEAN
OP_SOFTMAX
OP_QUANTIZE
OP_RGB565_TO_RGB888
```

These codes mainly make reports readable.

---

# 7. Flags

The following are also imported:

```text
FLAG_PADDING_SAME
FLAG_HAS_Q6
FLAG_QUANTIZE_INPUT_INT8
```

The report needs to interpret:

```text
flags
```

in context.

This matters particularly because:

```text
FLAG_PADDING_SAME
```

and:

```text
FLAG_QUANTIZE_INPUT_INT8
```

use the same bit.

---

# 8. Activations

The following are imported from `operator_options.py`:

```python
ACT_NONE
ACT_RELU
ACT_RELU6
```

They are used in both serialization and reporting.

---

# 9. Separation of responsibilities

The module has four main groups of functions:

```text
1. names for reporting

op_type_name()
act_name()
flags_pretty()


2. individual serialization

pack_layerparam()


3. validation

validate_layer_params()


4. complete serialization

build_params_blob()
params_blob_to_text()
```

---

# 10. `op_type_name()`

The function:

```python
def op_type_name(op_type):
```

converts an integer code to a readable name.

For example:

```text
1 → CONV

2 → DW

3 → FC

4 → ADD

5 → MEAN

6 → SOFTMAX

7 → QUANTIZE

8 → RGB565_TO_RGB888
```

---

# 11. Unknown value

The code uses:

```python
.get(
    op_type,
    str(op_type),
)
```

An unknown code, for example:

```text
12
```

would therefore simply be displayed as:

```text
"12"
```

This does not cause the report to fail.

---

# 12. `act_name()`

This function serves the same purpose for activations.

```text
0 → NONE

1 → RELU

3 → RELU6
```

---

# 13. `flags_pretty()`

This function deserves particular attention:

```python
def flags_pretty(
    flags,
    optype="",
):
```

because bit interpretation depends on the operation type.

---

# 14. QUANTIZE flags

If:

```python
optype == "QUANTIZE"
```

the bit:

```text
FLAG_QUANTIZE_INPUT_INT8
```

is interpreted.

If set:

```text
INPUT_INT8
```

is displayed.

Otherwise:

```text
INPUT_UINT8
```

is displayed.

---

# 15. Flags for other operations

For other operations:

```text
bit 0
    ↓
PADDING_SAME

bit 1
    ↓
HAS_Q6
```

may be recorded.

---

# 16. Why context matters

This avoids always interpreting:

```text
flags = 1
```

as:

```text
PADDING_SAME
```

When:

```text
optype = QUANTIZE
```

the same value means:

```text
INPUT_INT8
```

The function implements precisely this contextual distinction.

---

# 17. Return value with no flags

If no description applies:

```python
return "0"
```

This produces a more readable report than an empty string.

---

# 18. `pack_layerparam()`

This is the central function for serializing one record:

```python
def pack_layerparam(
    ...
):
```

It receives exactly the fields that will be stored in the runtime.

---

# 19. Order of the 29 fields

The order is fixed:

```text
 1  op_type
 2  act
 3  flags

 4  in_ptr
 5  out_ptr

 6  in_h
 7  in_w
 8  cin
 9  cout

10  kh
11  kw

12  stride_h
13  stride_w

14  dil_h
15  dil_w

16  pad_t
17  pad_b
18  pad_l
19  pad_r

20  wptr
21  bias_ptr

22  mul_ptr
23  shift_ptr
24  q6_ptr

25  zx
26  zw
27  zy

28  out_h
29  out_w
```

This order is part of the protocol between:

```text
Python extractor
```

and:

```text
WAT runtime
```

---

# 20. The order cannot change arbitrarily

Imagine replacing:

```text
mul_ptr
```

with:

```text
shift_ptr
```

in Python while leaving the WAT reader unchanged.

The result would be:

```text
runtime requests multiplier
        ↓
reads SHIFT address
```

The WAT could remain syntactically valid, but inference would be incorrect.

Field order is therefore a binary contract.

---

# 21. The `values` list

The function first builds:

```python
values = [
    ...
]
```

with all 29 values in the exact order.

This makes it easier to check the count before serialization.

---

# 22. Count validation

There is:

```python
if len(values) != 29:
```

followed by:

```text
RuntimeError
```

if the structure is changed incorrectly.

---

# 23. Why validate?

Because:

```text
LP_FMT
```

expects exactly:

```text
29 int32
```

A difference would indicate a broken contract.

---

# 24. Explicit conversion to `int`

Before `pack`:

```python
int(value)
```

is applied to all elements.

This normalizes values that might use types such as:

```text
np.int32
np.int64
bool
```

into Python integers.

---

# 25. Serialization

Finally:

```python
struct.pack(
    LP_FMT,
    *values,
)
```

produces:

```text
116 bytes
```

for one layer.

---

# 26. Little-endian

Because:

```text
LP_FMT
```

starts with:

```text
<
```

each 32-bit integer is serialized in little-endian order.

For example, conceptually:

```text
value = 1
```

is stored as:

```text
01 00 00 00
```

---

# 27. Physical structure of a layer

```text
offset +0
┌────────────────────────┐
│ op_type      int32     │
├────────────────────────┤
│ act          int32     │
├────────────────────────┤
│ flags        int32     │
├────────────────────────┤
│ in_ptr       int32     │
├────────────────────────┤
│ out_ptr      int32     │
├────────────────────────┤
│ ...                    │
├────────────────────────┤
│ out_w        int32     │
└────────────────────────┘
offset +116
```

---

# 28. Field offset

Since each field has:

```text
4 bytes
```

the field at zero-based index `n` is at:

```text
layer_base
+
n × 4
```

---

# 29. Example

`op_type`:

```text
offset 0
```

`act`:

```text
offset 4
```

`flags`:

```text
offset 8
```

`in_ptr`:

```text
offset 12
```

`out_ptr`:

```text
offset 16
```

and so on.

---

# 30. The `validate_layer_params()` function

Before serialization, the module performs structural validation.

```python
def validate_layer_params(
    layer_params,
    *,
    slot_bases,
):
```

---

# 31. Validating `in_slot`

For each layer:

```python
in_slot = params["in_slot"]
```

must satisfy:

```text
0 <= in_slot < number of slots
```

---

# 32. Example

With three slots:

```text
valid:

0
1
2
```

Invalid:

```text
-1
3
4
...
```

---

# 33. `out_slot`

The same rule applies to:

```text
out_slot
```

---

# 34. Why validate indices?

Because a later step performs:

```python
slot_bases[
    params["in_slot"]
]
```

An invalid index would mean:

```text
nonexistent pointer
```

or an access error during construction.

---

# 35. Special ADD validation

Most additional validation concerns:

```text
ADD
```

because it has:

```text
two dynamic inputs
```

whereas the standard structure contains only one:

```text
in_ptr
```

---

# 36. Exactly two `input_slots`

For `ADD`:

```python
len(input_slots) == 2
```

is required.

Otherwise:

```text
RuntimeError
```

---

# 37. First slot

Also:

```text
params["in_slot"]
==
input_slots[0]
```

must hold.

---

# 38. Why does this matter?

The adopted convention is:

```text
first input
    ↓
in_slot
    ↓
in_ptr
```

The second input is carried differently.

---

# 39. Expected input A pointer

The code calculates:

```python
expected_ptr_a = (
    slot_bases[
        slot_a
    ]
)
```

---

# 40. Expected input B pointer

Likewise:

```python
expected_ptr_b = (
    slot_bases[
        slot_b
    ]
)
```

---

# 41. Special ADD convention

In `layer_params.py`:

```text
pad_t
```

was reused as:

```text
input A pointer
```

and:

```text
pad_b
```

as:

```text
input B pointer
```

---

# 42. Validating `pad_t`

The requirement is:

```text
params["pad_t"]
==
slot_bases[slot_a]
```

---

# 43. Validating `pad_b`

Likewise:

```text
params["pad_b"]
==
slot_bases[slot_b]
```

---

# 44. Additional check

The code also checks:

```text
pad_t in slot_bases

pad_b in slot_bases
```

Thus, pointers must exactly match a known physical slot base.

---

# 45. Why are some checks seemingly redundant?

For example:

```text
pad_t == expected_ptr_a
```

already implies that:

```text
pad_t
```

corresponds to slot A.

But the additional check:

```text
pad_t in slot_bases
```

makes the intention explicit:

```text
ADD's special pointers
must point to slot bases
```

---

# 46. What validation does not do

It does not check the following here:

```text
w_off within weights_raw

b_off within bias_raw

mul_off within mul_blob

q6_off within q6_blob
```

The function focuses mainly on:

```text
slot integrity
+
special ADD convention
```

The docstring itself states that focus.

---

# 47. Return value

If everything is correct:

```python
return True
```

The return value carries no new data.

Its main purpose is to:

```text
fail early
```

when an inconsistency exists.

---

# 48. `build_params_blob()`

This is the module's main function.

```python
def build_params_blob(
    layer_params,
    *,
    slot_bases,
    params_bytes,
    parameter_layout,
):
```

It serializes all layers into one contiguous binary block.

---

# 49. Inputs

The function receives four groups of information.

### `layer_params`

Logical description of all layers.

### `slot_bases`

Absolute slot addresses.

### `params_bytes`

Total size reserved for the PARAMS region.

### `parameter_layout`

Absolute bases of these regions:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

---

# 50. First operation: validation

Before any bytes are generated:

```python
validate_layer_params(...)
```

is executed.

Thus:

```text
inconsistent data
    ↓
error
```

happens before:

```text
struct.pack()
```

---

# 51. Absolute bases

The function retrieves:

```text
kernel_base

bias_base

mul_base

shift_base

q6_base
```

from:

```python
parameter_layout
```

---

# 52. Why are these bases needed?

`layer_params.py` stored relative offsets:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

Now we need to generate:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

---

# 53. General transformation

The rule is:

```text
absolute pointer
=
region base
+
internal offset
```

---

# 54. Weight example

Suppose:

```text
kernel_base = 2048
w_off = 5000
```

Then:

```text
wptr =
2048 + 5000
=
7048
```

---

# 55. Multiplier example

```text
mul_base = 414832
mul_off = 128
```

Then:

```text
mul_ptr =
414960
```

---

# 56. Initializing the blob

The code creates:

```python
params_blob = bytearray()
```

Again, construction uses a mutable structure.

---

# 57. Report records

Also:

```python
records = []
```

will store detailed information about each serialized layer.

---

# 58. Layer loop

The function iterates through:

```python
enumerate(
    layer_params
)
```

Therefore:

```text
layer_index = 0
1
2
3
...
```

corresponds directly to the structure's position in the blob.

---

# 59. Relationship between index and offset

Since:

```text
LP_SIZE = 116
```

we expect:

```text
L0 → offset 0

L1 → offset 116

L2 → offset 232

L3 → offset 348
```

provided no additional information is inserted between structures.

This is exactly what the code does.

---

# 60. Calculating `in_ptr`

This stage has a significant exception for:

```text
ADD
```

---

# 61. Ordinary operations

For any operation other than `ADD`:

```python
in_ptr = (
    slot_bases[
        params["in_slot"]
    ]
)
```

Therefore:

```text
in_slot
    ↓
slot_bases
    ↓
in_ptr
```

---

# 62. Example

If:

```text
in_slot = 2

slot_bases[2] = 900464
```

then:

```text
in_ptr = 900464
```

---

# 63. ADD

For `ADD`:

```python
in_ptr = int(
    params["pad_t"]
)
```

---

# 64. Why?

Because in `layer_params.py`:

```text
pad_t
```

has already been defined as:

```text
absolute input A pointer
```

---

# 65. ADD's second input

The code comment makes this explicit:

```text
the first pointer goes in in_ptr

the second remains in pad_b
```

The final structure therefore contains:

```text
in_ptr
    → input A
```

and:

```text
pad_b
    → input B
```

---

# 66. Intentional duplication in ADD

For ADD, `pad_t` also remains serialized later in its own `pad_t` field.

Input A therefore appears:

```text
in_ptr = ptr A
```

and:

```text
pad_t = ptr A
```

This duplication follows from the structure's current protocol.

---

# 67. `out_ptr`

The output pointer is always:

```python
out_ptr = (
    slot_bases[
        params["out_slot"]
    ]
)
```

---

# 68. Example

```text
out_slot = 1

SLOT1_BASE = 703856
```

then:

```text
out_ptr = 703856
```

---

# 69. Weight: `wptr`

The code always executes:

```python
wptr = (
    kernel_base
    + params["w_off"]
)
```

This is a significant property.

---

# 70. Operations without weights

Operations such as:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

normally have:

```text
w_off = 0
```

Their:

```text
wptr
```

will therefore be:

```text
kernel_base
```

rather than:

```text
0
```

---

# 71. Does that mean they use weights?

No.

The field's meaning depends on:

```text
op_type
```

These operations' kernels must not interpret `wptr` as a valid weight.

---

# 72. Why this distinction matters

The report may display:

```text
wptr = 2048
```

for an operation that does not use weights.

That does not mean it consumes the first weight tensor.

It only means current serialization always calculates:

```text
kernel_base + w_off
```

and:

```text
w_off = 0
```

for these operations.

---

# 73. Bias

The behavior differs here.

The code first checks:

```python
params["has_bias"]
```

---

# 74. Bias present

When true:

```text
bias_ptr =
bias_base
+
b_off
```

---

# 75. Bias absent

Otherwise:

```python
bias_ptr = 0
```

Thus, `bias_ptr = 0` has an explicit meaning:

```text
no bias
```

---

# 76. Why is `b_off = 0` alone insufficient?

Because a real bias may be at the start of the blob:

```text
b_off = 0
```

We therefore need the Boolean:

```text
has_bias
```

to distinguish:

```text
existing bias at offset zero
```

from:

```text
absent bias
```

---

# 77. MUL and SHIFT

There is also:

```python
params["has_mulq6"]
```

---

# 78. When true

The following are calculated:

```text
mul_ptr =
mul_base + mul_off
```

and:

```text
shift_ptr =
shift_base + shift_off
```

---

# 79. When false

The code sets:

```text
mul_ptr = 0

shift_ptr = 0
```

---

# 80. Q6 has an additional condition

Even with:

```text
has_mulq6 = True
```

`q6_ptr` is only materialized if:

```text
act == ACT_RELU6
```

---

# 81. Complete rule

```text
has_mulq6
AND
activation == RELU6
      │
      ├── yes
      │     ↓
      │ q6_ptr =
      │ Q6_BASE + q6_off
      │
      └── no
            ↓
         q6_ptr = 0
```

---

# 82. Why this difference?

Multipliers and shifts are required for requantization.

In contrast:

```text
Q6
```

is specifically needed to implement the upper limit of:

```text
ReLU6
```

---

# 83. Consequence for SOFTMAX

`SOFTMAX` may have:

```text
has_mulq6 = True
```

because `mul_off` and `shift_off` exist.

But:

```text
act = ACT_NONE
```

Therefore:

```text
q6_ptr = 0
```

---

# 84. `blob_offset`

Before serializing the layer:

```python
blob_offset = len(
    params_blob
)
```

is calculated.

---

# 85. Meaning

`blob_offset` is the start of that `LayerParam` within:

```text
params_blob
```

It is not the absolute address in WASM memory.

---

# 86. Conversion to an absolute address

Later:

```text
LayerParam address
=
PARAMS_BASE
+
blob_offset
```

---

# 87. Example

If:

```text
PARAMS_BASE = 499360
```

and:

```text
blob_offset = 232
```

then:

```text
LayerParam address
=
499592
```

---

# 88. Mathematical offset relationship

Since each layer occupies:

```text
116 bytes
```

before final padding:

```text
blob_offset
=
layer_index × 116
```

---

# 89. Calling `pack_layerparam()`

The module then passes all values in the contract's order.

The first are:

```text
op_type
act
flags
```

followed by:

```text
in_ptr
out_ptr
```

and finally all geometry parameters, auxiliary pointers, zero points, and output shape.

The call preserves the exact order of the 29 expected values.

---

# 90. Already resolved pointer fields

Notice the difference:

In the original dictionary:

```text
w_off

b_off

mul_off
```

In the call to `pack_layerparam()`:

```text
wptr

bias_ptr

mul_ptr
```

The final blob therefore does not need the concept of relative offsets.

It already receives the addresses the runtime will use.

---

# 91. Validating structure size

After:

```python
if len(packed) != LP_SIZE:
```

the code raises an error.

---

# 92. Expected value

In the current format:

```text
len(packed)
=
116
```

---

# 93. Why check even with `struct.pack()`?

Because this creates an explicit invariant between:

```text
LP_FMT
```

and:

```text
LP_SIZE
```

and makes future structural changes easier to diagnose.

---

# 94. Concatenation

Then:

```python
params_blob.extend(
    packed
)
```

The layer is appended immediately after the previous one.

---

# 95. Blob layout

```text
params_blob

offset 0
┌──────────────────────┐
│ LayerParam 0         │
│ 116 bytes            │
└──────────────────────┘

offset 116
┌──────────────────────┐
│ LayerParam 1         │
│ 116 bytes            │
└──────────────────────┘

offset 232
┌──────────────────────┐
│ LayerParam 2         │
│ 116 bytes            │
└──────────────────────┘

...
```

---

# 96. Serialized layer metadata

After serialization, a record is created containing:

```text
layer_index

blob_offset

op_index

optype

op_type

act

flags

in_slot

out_slot

input_slots

in_ptr

out_ptr

wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr

params
```

---

# 97. Why store the entire `params` again?

The record contains:

```python
"params": params
```

This gives the later report access to both:

```text
values before serialization
```

and:

```text
calculated absolute pointers
```

---

# 98. Example

We can show simultaneously:

```text
w_off = 5000
```

and:

```text
wptr = 7048
```

This makes the transformation clear:

```text
relative offset
    ↓
absolute address
```

---

# 99. End of the loop

After all layers:

```python
used_bytes = len(
    params_blob
)
```

represents how many bytes the structures actually use.

---

# 100. Expected formula

Since every layer has exactly `LP_SIZE`:

```text
used_bytes
=
layer_count
×
LP_SIZE
```

---

# 101. Example

For:

```text
68 layers
```

and:

```text
LP_SIZE = 116
```

we have:

```text
68 × 116
=
7888 bytes
```

---

# 102. Difference between `used_bytes` and `params_bytes`

`used_bytes` is:

```text
actual LayerParam size
```

`params_bytes` is:

```text
total reserved area,
including alignment
```

---

# 103. Example

Suppose:

```text
used_bytes = 7888
```

With alignment:

```text
params_bytes = 7888
```

if already aligned.

Alternatively:

```text
used_bytes = 7890

params_bytes = 7904
```

could occur in another scenario.

---

# 104. Validating reserved space

If:

```text
used_bytes > params_bytes
```

the code raises:

```text
RuntimeError
```

---

# 105. Meaning

This would indicate that:

```text
memory planning
```

reserved less memory than serialization actually requires.

This would be a serious inconsistency between:

```text
calculate_layer_memory_layout()
```

and:

```text
build_params_blob()
```

---

# 106. Final padding

If the reserved region is larger:

```python
padding_bytes = (
    params_bytes
    - used_bytes
)
```

---

# 107. Example

```text
used_bytes = 7890

params_bytes = 7904
```

then:

```text
padding_bytes = 14
```

---

# 108. Padding contents

The code adds:

```python
b"\x00"
*
padding_bytes
```

Padding is therefore filled with zero bytes.

---

# 109. Final structure

```text
PARAMS region

┌──────────────────────┐
│ LayerParam 0         │
├──────────────────────┤
│ LayerParam 1         │
├──────────────────────┤
│ ...                  │
├──────────────────────┤
│ last LayerParam    │
├──────────────────────┤
│ 00 00 00 ...         │
│ alignment padding│
└──────────────────────┘
```

---

# 110. Why include padding in `params_blob`?

This ensures:

```text
len(params_blob)
==
params_bytes
```

at completion.

The data segment generated later therefore covers exactly the entire reserved PARAMS area.

---

# 111. Relationship to SLOT0

Since planning calculated:

```text
SLOT0_BASE
```

after:

```text
PARAMS_BASE + params_bytes
```

the full blob must exactly respect that reserved size.

---

# 112. Final invariant

On return:

```text
len(serialization["params_blob"])
==
serialization["params_bytes"]
```

must hold.

---

# 113. Return value of `build_params_blob()`

The function returns:

```python
{
    "params_blob": ...,
    "records": ...,
    "layer_count": ...,
    "layer_param_size": ...,
    "used_bytes": ...,
    "padding_bytes": ...,
    "params_bytes": ...,
}
```

---

# 114. `params_blob`

The binary artifact that will actually be placed in memory.

Its return type is:

```text
bytes
```

no longer:

```text
bytearray
```

---

# 115. `records`

Metadata for:

```text
debug
report
later validation
```

---

# 116. `layer_count`

Corresponds to:

```python
len(
    layer_params
)
```

and includes the synthetic layer.

---

# 117. `layer_param_size`

It is:

```text
LP_SIZE
```

or, currently:

```text
116
```

This field is also consumed later by `wat_generator.py`.

---

# 118. `used_bytes`

Number of bytes actually occupied by the structures.

---

# 119. `padding_bytes`

Number of zero bytes added solely to fill the aligned area.

---

# 120. `params_bytes`

Final physical size of the reserved region.

The entire construction process, including pointer calculation, serialization, and padding, is concentrated in this function.

---

# 121. Relative offsets versus absolute pointers

This is probably the module's most significant concept.

Before:

```text
weights.py
    ↓
weight tensor → w_off
```

After:

```text
params_blob.py
    ↓
wptr =
WEIGHTS_BASE + w_off
```

---

# 122. For bias

```text
b_off
    ↓
BIAS_BASE + b_off
    ↓
bias_ptr
```

---

# 123. For multiplier

```text
mul_off
    ↓
MUL_BASE + mul_off
    ↓
mul_ptr
```

---

# 124. For shift

```text
shift_off
    ↓
SHIFT_BASE + shift_off
    ↓
shift_ptr
```

---

# 125. For Q6

```text
q6_off
    ↓
Q6_BASE + q6_off
    ↓
q6_ptr
```

only when:

```text
has_mulq6
AND
activation == RELU6
```

---

# 126. Slots work differently

A slot has no per-tensor offset.

Its pointer is directly:

```text
slot_bases[
    slot_index
]
```

---

# 127. Complete CONV example

Suppose:

```text
in_slot = 1
out_slot = 2

slot_bases =
[
    507248,
    703856,
    900464
]
```

Then:

```text
in_ptr = 703856

out_ptr = 900464
```

---

# 128. Weights of the same CONV

Suppose:

```text
kernel_base = 2048

w_off = 5000
```

Then:

```text
wptr = 7048
```

---

# 129. Bias

```text
bias_base = 386656

b_off = 256
```

Then:

```text
bias_ptr = 386912
```

---

# 130. Quantization

```text
mul_base = 414832
mul_off = 128

shift_base = 443008
shift_off = 128

q6_base = 471184
q6_off = 128
```

Then:

```text
mul_ptr = 414960

shift_ptr = 443136

q6_ptr = 471312
```

if the layer uses `ReLU6`.

---

# 131. Final CONV structure

The runtime directly receives:

```text
in_ptr     = 703856
out_ptr    = 900464

wptr       = 7048
bias_ptr   = 386912

mul_ptr    = 414960
shift_ptr  = 443136
q6_ptr     = 471312
```

It does not need to know:

```text
tensor IDs
relative offsets
Python dictionaries
```

---

# 132. This simplifies the runtime

All resolution of:

```text
graph
slots
tensors
offsets
bases
```

takes place in advance in Python.

WAT receives an already materialized structure.

---

# 133. Relationship to AOT and the interpreter

The module's logic can consume the same binary `LayerParam` whether WebAssembly later executes through:

```text
interpreted
```

or:

```text
AOT
```

The data structure remains the same.

---

# 134. `params_blob_to_text()`

The second main function generates a serialization report.

Its docstring explicitly states that it replaces old comments and debug information previously embedded in WAT itself.

---

# 135. Report header

The report begins with:

```text
PARAMS BLOB
================================================================================
```

and presents:

```text
LayerParam size

Layers

Bytes used

Padding

Params bytes
```

---

# 136. Conceptual example

```text
LayerParam size : 116 bytes
Layers          : 68
Bytes used    : 7888
Padding         : 0
Params bytes    : 7888
```

---

# 137. Per-layer dump

Then each:

```text
record
```

generates a section.

---

# 138. Identification

The report displays:

```text
L<layer_index>

blob_offset

op_index

optype

op_type
```

---

# 139. `layer_index` versus TFLite label

As in the previous report:

```text
L0
```

at this point represents:

```text
position within params_blob
```

and not necessarily the logical `L0` label from `graph.py`.

The first structure is the synthetic layer.

---

# 140. `blob_offset`

This field is particularly useful for checking:

```text
L0 → 0

L1 → 116

L2 → 232

L3 → 348
```

---

# 141. Operation name

The report presents:

```text
op_type = 1 (CONV)
```

for example.

This shows simultaneously:

```text
binary code
+
human interpretation
```

---

# 142. Activation

Also:

```text
act = 3 (RELU6)
```

---

# 143. Flags

And:

```text
flags = 3 (PADDING_SAME|HAS_Q6)
```

or, for QUANTIZE:

```text
flags = 1 (INPUT_INT8)
```

---

# 144. Slots

For operations with one input:

```text
in_slot/out_slot
```

is displayed.

For operations with multiple inputs:

```text
in_slots/out_slot
```

is used.

---

# 145. Actual pointers

Then:

```text
in_ptr/out_ptr
```

shows the addresses actually serialized.

This lets you compare:

```text
logical slot
```

with:

```text
physical address
```

---

# 146. Special quantization parameters

If the layer has:

```text
quant_params
```

the report creates dedicated sections for:

```text
ADD

SOFTMAX

QUANTIZE
```

---

# 147. ADD

The following are displayed:

```text
sA / sB / sY

zA / zB / zY

s_common

mul0 / shift0

mul1 / shift1

out_mul / out_shift
```

---

# 148. SOFTMAX

The following are shown:

```text
sX / sY

zX / zY

beta

integer_bits

internal_scale

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

---

# 149. Critical SOFTMAX distinction

The report explicitly contains the comment:

```text
stride_w stores input_left_shift,
no integer_bits
```

and prints:

```text
stride_w input_left_shift
```

This is the correct interpretation of the documented code.

---

# 150. QUANTIZE

The following are displayed:

```text
input_dtype

scale_in / scale_out

zp_in / zp_out

ratio

mul / shift
```

---

# 151. Conventional geometry

For ordinary operations, the report shows:

```text
kh / kw

stride_h / stride_w

dil_h / dil_w

pad top/bottom/left/right
```

---

# 152. Special operations

For:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
```

labels change to reflect the fields' actual meaning.

This avoids printing, for example:

```text
kernel 123456789 × -3
```

when the fields actually mean:

```text
multiplier / shift
```

---

# 153. ADD report

The report shows:

```text
kh/kw (mul0/sh0)

stride (mul1/sh1)

dil (outM/outSh)

pad_t/b (inPtr)

pad_l/r (zA/zB)
```

---

# 154. MEAN report

It shows:

```text
kh/kw (mul/shift)

stride_h spatial

pad_t input_ptr
```

---

# 155. SOFTMAX report

It shows:

```text
kh/kw beta

stride_h diff_min

stride_w input_left_shift

pad_t input_ptr
```

---

# 156. QUANTIZE report

It shows:

```text
kh/kw (mul/shift)

pad_t input_ptr
```

---

# 157. Depthwise

For:

```text
DEPTHWISE_CONV_2D
```

the report also shows:

```text
depth_mult
```

---

# 158. Offsets and pointers

The final part of each layer compares:

```text
w_off / b_off

mul_off

shift_off

q6_off
```

with:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

---

# 159. A useful debugging location

Imagine:

```text
w_off = 12000
```

but:

```text
wptr
```

does not match:

```text
WEIGHTS_BASE + 12000
```

The report would make the inconsistency clear.

---

# 160. Zero points

Also displayed are:

```text
zx / zw / zy
```

allowing you to check:

```text
input
weights
output
```

in one place.

---

# 161. Complete representation of the three phases

For a weight parameter, we can follow:

```text
TFLite tensor 42
        │
        ▼
weights.py

w_off = 5000
        │
        ▼
layer_params.py

"w_off": 5000
        │
        ▼
params_blob.py

wptr =
WEIGHTS_BASE + 5000
        │
        ▼
struct.pack()

bytes
        │
        ▼
WASM
```

---

# 162. For an activation

```text
TFLite tensor
      │
      ▼
tensor_mapping.py

tensor → runtime slot
      │
      ▼
layer_params.py

in_slot = 1
      │
      ▼
params_blob.py

in_ptr =
slot_bases[1]
      │
      ▼
struct.pack()
```

---

# 163. For multiplier

```text
op_index
   │
   ▼
quantization.py

mul_off
   │
   ▼
layer_params.py

mul_off
   │
   ▼
params_blob.py

MUL_BASE + mul_off
   │
   ▼
mul_ptr
```

---

# 164. Difference between `params_blob` and earlier blobs

`weights_raw` contains:

```text
trained data
```

`mul_blob` contains:

```text
requantization parameters
```

`params_blob`, in turn, contains:

```text
description of how to execute the network
```

---

# 165. Three conceptual categories

```text
data
    ↓
weights
bias


AUXILIARY NUMERICAL TABLES
    ↓
MUL
SHIFT
Q6


EXECUTION METADATA
    ↓
PARAMS
```

---

# 166. PARAMS as a high-level instruction table

Each `LayerParam` tells the runtime something like:

```text
which kernel to run?

where is the input?

where to write output?

where are the weights?

what are the dimensions?

which stride to use?

which padding to use?

where are requantization parameters?

what are the zero points?
```

---

# 167. It is not WASM bytecode

The distinction matters.

`params_blob` does not contain:

```text
WebAssembly instructions
```

It contains:

```text
data
```

which WebAssembly code reads to decide how to execute each layer.

---

# 168. Conceptual model

```text
WASM
    ↓
generic kernel code

PARAMS
    ↓
configuration of each execution
```

Kernels can therefore be reused across many layers.

---

# 169. Example

A single kernel:

```text
conv2d
```

can execute:

```text
CONV layer 1

CONV layer 5

CONV layer 17

CONV layer 42
```

because each `LayerParam` supplies different:

```text
shape
stride
padding
pointers
quantization
```

values.

---

# 170. Relationship to portability

This separation also helps keep:

```text
runtime algorithm
```

separate from:

```text
model-specific data
```

The WAT template can keep kernels static while the extractor changes:

```text
weights
parameters
addresses
number of layers
```

---

# 171. `params_blob` padding is not a LayerParam

The additional trailing bytes:

```text
00 00 00 ...
```

do not represent a layer.

The actual layer count remains:

```text
layer_count
```

---

# 172. Runtime must respect `NUM_LAYERS`

The runtime loop must execute:

```text
0 .. NUM_LAYERS - 1
```

rather than infer layer count from the total size of:

```text
PARAMS
```

because the end may contain padding.

---

# 173. Relationship to `NUM_LAYERS`

Later:

```text
NUM_LAYERS
=
serialization["layer_count"]
```

can be used by the WAT generator.

---

# 174. Relationship to `LP_SIZE`

Also:

```text
LP_SIZE
=
serialization["layer_param_size"]
```

is consumed by the template/runtime.

---

# 175. Address of a LayerParam

With:

```text
PARAMS_BASE
LP_SIZE
layer_index
```

we have:

```text
layer_ptr =
PARAMS_BASE
+
layer_index × LP_SIZE
```

---

# 176. Example

```text
PARAMS_BASE = 499360

LP_SIZE = 116

layer_index = 10
```

Then:

```text
layer_ptr =
499360
+
1160
=
500520
```

---

# 177. The WAT reader

The runtime can then load:

```text
op_type
act
flags
...
```

at fixed offsets within the structure.

---

# 178. Fundamental invariants

After `build_params_blob()`, several properties must hold.

### Each layer

```text
len(packed) == LP_SIZE
```

---

### Number of useful bytes

```text
used_bytes
=
layer_count × LP_SIZE
```

---

### Sufficient reserved area

```text
used_bytes
<=
params_bytes
```

---

### Final blob

```text
len(params_blob)
=
params_bytes
```

---

### Slots

```text
0 <= in_slot < len(slot_bases)

0 <= out_slot < len(slot_bases)
```

---

### ADD

```text
len(input_slots) == 2
```

and:

```text
pad_t = slot A base

pad_b = slot B base
```

---

# 179. Potential future validation

The code could later be strengthened to also check:

```text
wptr within WEIGHTS

bias_ptr within BIAS

mul_ptr within MUL

shift_ptr within SHIFT

q6_ptr within Q6
```

when these pointers are used.

---

# 180. Another possible check

We could confirm:

```text
blob_offset
==
layer_index × LP_SIZE
```

during each iteration.

Currently, this follows naturally from sequential construction.

---

# 181. Another possible check

It would also be possible to guarantee:

```text
used_bytes
==
len(layer_params) × LP_SIZE
```

explicitly.

Again, the code already produces this relationship by construction.

---

# 182. A detail about `wptr`

Unlike:

```text
bias_ptr
mul_ptr
shift_ptr
q6_ptr
```

which can explicitly be zero when absent,

`wptr` is always:

```text
kernel_base + w_off
```

---

# 183. Consequence for reporting

We must therefore not use:

```text
wptr == 0
```

to test for the existence of weights.

To know whether an operator actually uses `wptr`, interpret:

```text
op_type
```

---

# 184. Example

`ADD` may have:

```text
w_off = 0

wptr = KERNEL_BASE
```

But the ADD kernel simply does not use this field as a weight.

---

# 185. Fixed structure versus optional fields

This behavior follows directly from using:

```text
a fixed structure
```

for heterogeneous operations.

All 29 fields physically exist in every `LayerParam`, even when some are irrelevant.

---

# 186. Benefit

The runtime can work with:

```text
fixed LP_SIZE
```

and fixed offsets.

It does not need variable structures.

---

# 187. Cost

Some fields contain:

```text
0
```

or values with no meaning for a given operation.

The runtime must interpret each field based on:

```text
op_type
```

---

# 188. Protocol example

```text
op_type = CONV
    ↓
kh = kernel height

op_type = ADD
    ↓
kh = multiplier A

op_type = MEAN
    ↓
kh = multiplier

op_type = SOFTMAX
    ↓
kh = input_beta_mul

op_type = QUANTIZE
    ↓
kh = multiplier
```

`params_blob.py` does not need to reinterpret all this.

It only ensures that the value prepared by the previous module is placed in the correct position.

---

# 189. Separation of responsibilities between the two modules

`layer_params.py` answers:

```text
which value belongs in each field?
```

`params_blob.py` answers:

```text
how to transform these fields
into a binary structure
with absolute pointers?
```

---

# 190. Example

`layer_params.py`:

```python
{
    "w_off": 5000,
    "has_bias": True,
    "b_off": 256,
}
```

`params_blob.py`:

```text
wptr =
WEIGHTS_BASE + 5000

bias_ptr =
BIAS_BASE + 256
```

and finally:

```text
struct.pack(...)
```

---

# 191. Relationship to `memory.py`

`memory.py` decides:

```text
WEIGHTS_BASE

BIAS_BASE

MUL_BASE

SHIFT_BASE

Q6_BASE

PARAMS_BASE
```

`params_blob.py` uses these bases but does not decide where they reside.

---

# 192. Relationship to `wat_generator.py`

After this stage, the generator receives:

```text
params_blob
```

already fully prepared.

It does not need to:

```text
calculate pointers

interpret slots

calculate weight offsets

assemble LayerParam
```

---

# 193. The generator only positions the blob

Conceptually:

```wat
(data
    (i32.const PARAMS_BASE)
    "...params_blob..."
)
```

---

# 194. Intended separation

```text
params_blob.py
    ↓
produces correct bytes

wat_generator.py
    ↓
places those bytes
at the correct address
```

---

# 195. This reduces coupling

If we later want to store:

```text
params_blob
```

in another artifact format, structure construction logic does not depend on WAT syntax.

---

# 196. Complete address workflow

```text
weights.py
    ↓
w_off

quantization.py
    ↓
mul_off
shift_off
q6_off

memory.py
    ↓
WEIGHTS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE

layer_params.py
    ↓
logical structure

params_blob.py
    ↓
wptr
mul_ptr
shift_ptr
q6_ptr

WASM
```

---

# 197. Complete slot workflow

```text
slots.py
    ↓
logical slot

tensor_mapping.py
    ↓
tensor → slot

layer_params.py
    ↓
runtime slot

memory layout
    ↓
slot_bases

params_blob.py
    ↓
in_ptr / out_ptr
```

---

# 198. Complete PARAMS view

```text
PARAMS_BASE
   │
   ▼

┌─────────────────────────────┐
│ LayerParam 0                │
│ RGB565_TO_RGB888            │
│ 116 bytes                   │
├─────────────────────────────┤
│ LayerParam 1                │
│ first TFLite operation    │
│ 116 bytes                   │
├─────────────────────────────┤
│ LayerParam 2                │
│ 116 bytes                   │
├─────────────────────────────┤
│ ...                         │
├─────────────────────────────┤
│ LayerParam N-1              │
│ 116 bytes                   │
├─────────────────────────────┤
│ optional padding            │
│ 00 00 00 ...                │
└─────────────────────────────┘
   │
   ▼
SLOT0_BASE
```

---

# 199. Role in the full pipeline

```text
┌─────────────────────────────┐
│       layer_params.py       │
│                             │
│ structured dictionaries    │
│ relative offsets           │
│ slots                       │
│ special parameters        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│       params_blob.py        │
│                             │
│ validates slots                │
│ resolves pointers           │
│ struct.pack 29 × int32      │
│ concatenates LayerParams       │
│ adds padding            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         params_blob         │
│                             │
│ final PARAMS bytes      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      wat_generator.py       │
│                             │
│ data @ PARAMS_BASE          │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│           WASM              │
│                             │
│ runtime reads LayerParam[]     │
└─────────────────────────────┘
```

---

# 200. Summary

`params_blob.py` transforms the logical operation description into a binary representation directly consumable by the WebAssembly runtime.

Its first responsibility is validating slot use, especially `ADD`, which has two inputs and reuses:

```text
pad_t
pad_b
```

as pointers to those inputs.

Its second responsibility is converting relative information:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

into absolute addresses:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

using:

```text
BASE + OFFSET
```

Its third responsibility is organizing exactly 29 values in each `LayerParam`, in fixed order, and serializing them as:

```text
29 × int32 little-endian
=
116 bytes
```

Its fourth responsibility is concatenating all these structures:

```text
LayerParam[0]
LayerParam[1]
LayerParam[2]
...
```

and filling the region with zero bytes up to:

```text
params_bytes
```

ensuring the final size matches memory planning exactly.

This module therefore performs the transformation:

```text
Python network description
          ↓
absolute addresses
          ↓
fixed binary structure
          ↓
PARAMS
```

After it, virtually all semantic extraction work is complete.

`wat_generator.py` no longer needs to understand how a convolution, ADD, or SOFTMAX was built. It simply receives a binary block ready to be placed in:

```text
PARAMS_BASE
```

alongside the model's other blocks.


