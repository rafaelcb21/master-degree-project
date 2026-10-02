[English](09-memory-layout.md) | [Português (Brasil)](09-layout-memoria.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in the Portuguese edition.

# 09 — Planning linear memory (`memory.py`)

## 1. Module purpose

`extractor/memory.py` plans the linear memory used by the WebAssembly module.

Previous pipeline stages have already supplied information such as:

```text
weights_raw
bias_raw

mul_blob
shift_blob
q6_blob

intermediate tensors
number of slots
```

The following questions remain:

```text
how much space should each slot occupy?

where do weights start?

where does bias start?

where are MUL, SHIFT, and Q6 placed?

where do LayerParams start?

where do slots start?

what is the final address used?

how many WebAssembly pages are needed?
```

This module makes those decisions.

The overall transformation is:

```text
data sizes
       │
       ▼
region planning
       │
       ▼
absolute addresses
       │
       ▼
final memory size
       │
       ▼
WASM page count
```

---

# 2. File responsibilities

The module has five main calculation functions:

```text
tensor_numel()
        ↓
number of elements

align_up()
        ↓
address alignment

calculate_slot_bytes()
        ↓
physical size of each slot

calculate_parameter_layout()
        ↓
bases of WEIGHTS/BIAS/MUL/SHIFT/Q6/PARAMS

calculate_final_memory_layout()
        ↓
complete layout + MEM_END + MEM_PAGES
```

There are also three functions dedicated to reporting:

```text
slot_memory_to_text()

parameter_layout_to_text()

final_memory_layout_to_text()
```

---

# 3. Imports

The file uses:

```python
from extractor.tflite_utils import (
    BYTES_PER_TYPE,
    TENSOR_TYPE_MAP,
    is_constant_tensor,
    tensor_shape_list,
)
```

Each element has a specific purpose.

---

# 4. `BYTES_PER_TYPE`

It converts:

```text
tensor type
```

into:

```text
bytes per element
```

Example:

```text
int8
 ↓
1 byte

int32
 ↓
4 bytes

float32
 ↓
4 bytes
```

This information is needed to calculate how much space an intermediate tensor occupies.

---

# 5. `TENSOR_TYPE_MAP`

It is mainly used in reports to convert:

```text
9
```

into:

```text
int8
```

or:

```text
2
```

into:

```text
int32
```

---

# 6. `is_constant_tensor()`

It excludes the following from slot analysis:

```text
weights
biases
other constant tensors
```

These data do not share intermediate activation buffers.

---

# 7. `tensor_shape_list()`

Converts the TFLite shape into a Python list.

Example:

```text
[1, 128, 128, 3]
```

This shape determines the total element count.

---

# 8. Three memory categories

It is useful to divide this module's planning into three categories.

## 8.1 Constant parameters

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

These regions remain valid throughout inference.

---

## 8.2 Operation descriptions

```text
PARAMS
```

Contains the serialized `LayerParam` array.

---

## 8.3 Working memory

```text
SLOT0
SLOT1
SLOT2
```

These regions are reused by different activations during execution.

---

# 9. Memory overview

Conceptually:

```text
low address
      │
      ▼

┌──────────────────────────┐
│ initial reserved region  │
├──────────────────────────┤
│ WEIGHTS                  │
├──────────────────────────┤
│ padding/alignment        │
├──────────────────────────┤
│ BIAS                     │
├──────────────────────────┤
│ padding/alignment        │
├──────────────────────────┤
│ MUL                      │
├──────────────────────────┤
│ padding/alignment        │
├──────────────────────────┤
│ SHIFT                    │
├──────────────────────────┤
│ padding/alignment        │
├──────────────────────────┤
│ Q6                       │
├──────────────────────────┤
│ padding/alignment        │
├──────────────────────────┤
│ PARAMS                   │
├──────────────────────────┤
│ SLOT0                    │
├──────────────────────────┤
│ SLOT1                    │
├──────────────────────────┤
│ SLOT2                    │
└──────────────────────────┘

      │
      ▼
   MEM_END
```

---

# 10. The `tensor_numel()` function

The first function is:

```python
def tensor_numel(
    shape,
    batch=1,
):
```

Its purpose is to calculate:

```text
total element count
```

of a tensor.

---

# 11. Basic calculation

For:

```text
shape = [1, 128, 128, 3]
```

the calculation is:

```text
1 × 128 × 128 × 3
```

resulting in:

```text
49,152 elements
```

---

# 12. Implementation

The function starts with:

```python
num_elements = 1
```

and iterates over each dimension:

```python
for dimension in shape:
```

performing:

```python
num_elements *= dimension
```

---

# 13. Why start with `1`?

Because `1` is the multiplicative identity.

For example:

```text
1 × 128
    ↓
128

128 × 128
    ↓
16384

16384 × 3
    ↓
49152
```

---

# 14. Conversion to `int`

Each dimension is converted:

```python
dimension = int(
    dimension
)
```

This normalizes NumPy types such as:

```text
np.int32
np.int64
```

into an ordinary Python integer.

---

# 15. Negative dimensions

The code contains:

```python
if dimension < 0:
    dimension = batch
```

This rule preserves the original implementation's behavior.

---

# 16. Example

For:

```text
shape = [-1, 128, 128, 3]
batch = 1
```

the function interprets:

```text
-1 → 1
```

and calculates:

```text
1 × 128 × 128 × 3
=
49152
```

---

# 17. Intended meaning

Normally a dimension:

```text
-1
```

may represent a dynamic dimension.

For the model used by this project, the rule treats it as:

```text
batch
```

---

# 18. Important limitation

This rule is not universal.

For example:

```text
[1, -1, 128, 3]
```

could represent:

```text
dynamic height
```

rather than batch.

The current implementation would still substitute:

```text
-1 → batch
```

This rule therefore suits the current model's expected behavior, but should not be considered a generic solution for any dynamic shape.

---

# 19. Return value

The function returns:

```python
return num_elements
```

In other words:

```text
shape
  ↓
tensor_numel()
  ↓
number of elements
```

---

# 20. Relationship between elements and bytes

Later we have:

```text
num_bytes =
num_elements
×
bytes_per_element
```

For example:

```text
49152 elements
×
1 byte
=
49152 bytes
```

---

# 21. The `align_up()` function

The second function is:

```python
def align_up(
    value,
    alignment=16,
):
```

It rounds an address up to the next alignment multiple.

---

# 22. Example

Consider:

```text
value = 1001
alignment = 16
```

Nearby multiples are:

```text
992
1008
1024
```

The first valid value greater than or equal to `1001` is:

```text
1008
```

Therefore:

```text
align_up(1001, 16)
=
1008
```

---

# 23. Already aligned value

If:

```text
value = 2048
alignment = 16
```

we have:

```text
2048 % 16 = 0
```

Therefore:

```text
align_up(2048, 16)
=
2048
```

No padding is needed.

---

# 24. Bitwise implementation

The code is:

```python
return (
    value
    + (alignment - 1)
) & ~(alignment - 1)
```

This is an efficient alignment method when:

```text
alignment
```

is a power of two.

---

# 25. Important condition

With:

```text
ALIGN = 16
```

we have:

```text
16 = 2⁴
```

so the formula is appropriate.

Other compatible alignments include:

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

---

# 26. Arbitrary values

The same expression should not be considered generally correct for:

```text
10
12
20
```

because they are not powers of two.

In the current project:

```text
ALIGN = 16
```

satisfies the required condition.

---

# 27. Why align memory?

Alignment creates predictable block boundaries.

Example:

```text
end of weights = 386651
```

With alignment 16:

```text
BIAS_BASE =
386656
```

There are therefore:

```text
5 bytes
```

unused between the regions.

---

# 28. Alignment padding

Visually:

```text
WEIGHTS
│
│ last useful byte
▼
386650

386651 ─┐
386652  │
386653  ├── padding
386654  │
386655 ─┘

386656
▲
│
BIAS_BASE
```

Padding contains no tensor.

It exists only for placement.

---

# 29. The `calculate_slot_bytes()` function

This function answers:

```text
how large should each slot be?
```

The code finds the largest nonconstant subgraph tensor and reserves enough space in every slot to hold it.

---

# 30. Adopted strategy

The rule is:

```text
SLOT_BYTES
=
aligned size
of the largest nonconstant tensor
```

Because any slot may hold different activations during execution, all slots have the same size.

---

# 31. Initialization

The function starts with:

```python
max_bytes = 0
max_tensor = None
```

It also creates:

```python
tensor_records = []
```

for the report.

---

# 32. Scanning tensors

All tensors are examined:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

---

# 33. Retrieval

For each ID:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

---

# 34. Excluding constants

The code executes:

```python
if is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
    continue
```

Therefore:

```text
weight
biases
auxiliary constants
```

do not participate in slot size calculation.

---

# 35. Why exclude constants?

Because slots represent:

```text
intermediate activations
```

rather than permanent parameters.

Weights have:

```text
WEIGHTS
```

Biases have:

```text
BIAS
```

and do not need to fit in slots.

---

# 36. Shape

Then:

```python
shape = tensor_shape_list(
    tensor
)
```

If the shape is empty:

```python
if not shape:
    continue
```

---

# 37. Tensor type

The following is obtained:

```python
tensor_type = int(
    tensor.Type()
)
```

---

# 38. Bytes per element

The code looks up:

```python
bytes_per_element = (
    BYTES_PER_TYPE.get(
        tensor_type
    )
)
```

---

# 39. Unknown type

If:

```python
bytes_per_element is None
```

the tensor is skipped.

This means current planning depends on types recognized by:

```text
BYTES_PER_TYPE
```

---

# 40. Element count

Then:

```python
num_elements = tensor_numel(
    shape,
    batch=batch,
)
```

---

# 41. Size in bytes

Then:

```python
num_bytes = (
    num_elements
    * bytes_per_element
)
```

---

# 42. `int8` example

Shape:

```text
[1, 128, 128, 3]
```

Elements:

```text
49152
```

Type:

```text
int8
```

Bytes per element:

```text
1
```

Result:

```text
49152 bytes
```

---

# 43. `int32` example

Shape:

```text
[1, 1000]
```

Elements:

```text
1000
```

Bytes per element:

```text
4
```

Result:

```text
4000 bytes
```

---

# 44. Tensor name

For reporting purposes:

```python
tensor_name = (
    tensor
    .Name()
    .decode(
        "utf-8",
        "ignore",
    )
)
```

---

# 45. Why `decode()`?

The TFLite binding normally provides the name as:

```text
bytes
```

and the report needs:

```text
str
```

---

# 46. `"ignore"`

The option:

```text
ignore
```

discards invalid UTF-8 bytes instead of interrupting report generation.

---

# 47. Type name

The code also converts:

```text
tensor_type
```

into something readable:

```python
type_name = (
    TENSOR_TYPE_MAP.get(
        tensor_type,
        ("UNKNOWN", None),
    )[0]
)
```

---

# 48. Example

```text
tensor_type = 9
```

produces:

```text
int8
```

---

# 49. Recording the tensor

Each valid nonconstant tensor generates:

```python
{
    "tensor_id": ...,
    "name": ...,
    "shape": ...,
    "tensor_type": ...,
    "type_name": ...,
    "bytes_per_element": ...,
    "num_elements": ...,
    "num_bytes": ...,
}
```

---

# 50. Purpose of `tensor_records`

This list does not directly participate in subsequent calculations.

It explains:

```text
which tensors were considered?

how much space does each occupy?

which was largest?
```

---

# 51. Identifying the largest tensor

The code compares:

```python
if num_bytes > max_bytes:
```

and updates:

```python
max_bytes = num_bytes
max_tensor = record
```

---

# 52. Using `>`

Notice that the condition is:

```text
>
```

rather than:

```text
>=
```

If two tensors have exactly the same maximum size, the first one found remains recorded as:

```text
max_tensor
```

This does not affect `SLOT_BYTES`.

It only determines which tensor is shown as the representative of the maximum size.

---

# 53. Example

Suppose:

```text
tensor 10 = 120000 bytes

tensor 20 = 196608 bytes

tensor 30 = 40000 bytes
```

At the end:

```text
max_bytes = 196608
```

and:

```text
max_tensor = tensor 20
```

---

# 54. Slot alignment

Then:

```python
slot_bytes = align_up(
    max_bytes,
    alignment,
)
```

---

# 55. Already aligned example

If:

```text
max_bytes = 196608
alignment = 16
```

and `196608` is already a multiple of 16:

```text
SLOT_BYTES = 196608
```

---

# 56. Example with padding

If:

```text
max_bytes = 196601
```

the next multiple of 16 will be:

```text
196608
```

Then:

```text
SLOT_BYTES = 196608
```

---

# 57. Why do all slots use the maximum size?

Because `slots.py` can reuse any slot for different tensors throughout inference:

```text
SLOT0 currently stores tensor A

later it stores tensor D

then tensor H
```

we must ensure:

```text
each slot fits any tensor
that may be assigned to it
```

The current strategy solves this simply:

```text
all slots have the size
of the largest nonconstant tensor
```

---

# 58. Consequence

If:

```text
SLOT_BYTES = 196608
```

and:

```text
NUM_SLOTS = 3
```

memory reserved exclusively for slots will be:

```text
3 × 196608
=
589824 bytes
```

---

# 59. Simplicity versus optimization

This strategy may reserve more memory than the theoretical minimum.

For example:

```text
SLOT0 never receives a tensor larger than 50 KiB

SLOT1 needs 192 KiB

SLOT2 never exceeds 80 KiB
```

Even so:

```text
all = 192 KiB
```

in the current implementation.

---

# 60. Advantage

The advantage is simplicity:

```text
a single SLOT_BYTES value
```

and:

```text
slot_base =
initial base
+
slot_index × SLOT_BYTES
```

can be used.

---

# 61. Possible future optimization

A more sophisticated version could calculate:

```text
a specific maximum size
for each slot
```

according to the actual allocation.

This would increase planning complexity.

The current implementation favors:

```text
simplicity
predictability
```

---

# 62. Return value of `calculate_slot_bytes()`

The function returns:

```python
{
    "max_bytes": ...,
    "slot_bytes": ...,
    "alignment": ...,
    "batch": ...,
    "max_tensor": ...,
    "tensor_records": ...,
}
```

---

# 63. The `max_bytes` field

The actual size of the largest tensor before alignment.

---

# 64. The `slot_bytes` field

The final space reserved for each slot after alignment.

---

# 65. The `max_tensor` field

Contains all metadata for the tensor that determined the maximum size.

---

# 66. `tensor_records`

Allows auditing every tensor considered in the calculation.

---

# 67. The `calculate_parameter_layout()` function

After parameter sizes have been calculated in previous modules, this function places each block in memory.

It receives:

```text
kernel_base_hint

alignment

weights_raw
bias_raw

mul_blob
shift_blob
q6_blob
```

---

# 68. Why `kernel`?

In this project, the weight region is sometimes called:

```text
KERNEL
```

and elsewhere:

```text
WEIGHTS
```

Thus:

```text
kernel_base
```

is the base of the block:

```text
weights_raw
```

---

# 69. Produced layout

The sequence is:

```text
KERNEL/WEIGHTS
      ↓
BIAS
      ↓
MUL
      ↓
SHIFT
      ↓
Q6
      ↓
PARAMS
```

Each new base is aligned.

---

# 70. Weight base

First:

```python
kernel_base = align_up(
    kernel_base_hint,
    alignment,
)
```

---

# 71. Current configuration

With:

```text
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

because `2048` is already a multiple of 16:

```text
kernel_base = 2048
```

---

# 72. Weight size

```python
kernel_bytes = len(
    weights_raw
)
```

There is therefore no manually hardcoded size.

It comes directly from the extracted blob.

---

# 73. Weight interval

The logical region is:

```text
[kernel_base,
 kernel_base + kernel_bytes)
```

The notation:

```text
[a, b)
```

means:

```text
includes a
excludes b
```

---

# 74. Example

If:

```text
kernel_base = 2048
kernel_bytes = 384608
```

then:

```text
WEIGHTS =
[2048, 386656)
```

The last used byte is:

```text
386655
```

---

# 75. Bias base

The next block starts at:

```python
bias_base = align_up(
    kernel_base + kernel_bytes,
    alignment,
)
```

---

# 76. Example without padding

If:

```text
kernel_base + kernel_bytes
=
386656
```

and this value is already aligned:

```text
bias_base = 386656
```

---

# 77. Example with padding

If the end of weights were:

```text
386651
```

we would have:

```text
bias_base = 386656
```

Creating five bytes of padding.

---

# 78. Bias size

```python
bias_bytes = len(
    bias_raw
)
```

---

# 79. Multiplier base

Then:

```python
mul_base = align_up(
    bias_base + bias_bytes,
    alignment,
)
```

---

# 80. MUL size

```python
mul_bytes = len(
    mul_blob
)
```

---

# 81. SHIFT base

```python
shift_base = align_up(
    mul_base + mul_bytes,
    alignment,
)
```

---

# 82. Q6 base

```python
q6_base = align_up(
    shift_base + shift_bytes,
    alignment,
)
```

---

# 83. `params_base`

After Q6:

```python
params_base = align_up(
    q6_base + q6_bytes,
    alignment,
)
```

This address represents:

```text
where the future PARAMS region can start
```

---

# 84. Important: `PARAMS` has not been placed yet

In this function, we do not yet have:

```text
params_blob
```

Therefore:

```text
params_base
```

is just the next aligned free area after Q6.

The actual `LayerParams` size will be known later.

---

# 85. Why this function stops at `params_base`

The partial layout is:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6

PARAMS_BASE
    ↓
next available address
```

What is still missing:

```text
PARAMS bytes
SLOT0
SLOT1
SLOT2
```

---

# 86. Partial layout return value

The function returns:

```python
{
    "kernel_base": ...,
    "kernel_bytes": ...,

    "bias_base": ...,
    "bias_bytes": ...,

    "mul_base": ...,
    "mul_bytes": ...,

    "shift_base": ...,
    "shift_bytes": ...,

    "q6_base": ...,
    "q6_bytes": ...,

    "params_base": ...,

    "alignment": ...,
    "kernel_base_hint": ...,
}
```

---

# 87. Bases versus sizes

Each region conceptually has:

```text
BASE
+
BYTES
=
END
```

For example:

```text
BIAS_BASE
+
BIAS_BYTES
=
end of bias
```

---

# 88. Avoiding overlap

The function always uses:

```text
next_base =
align_up(
    previous_base + previous_size
)
```

The next region therefore starts after the preceding one ends.

---

# 89. Chained example

Consider:

```text
kernel_base = 2048
kernel_bytes = 1000
```

End:

```text
3048
```

With alignment 16:

```text
bias_base = 3056
```

Suppose:

```text
bias_bytes = 100
```

End:

```text
3156
```

Next alignment:

```text
mul_base = 3168
```

And so on.

---

# 90. Does padding belong to the preceding region?

No.

Conceptually:

```text
region data
       ↓
logical end
       ↓
padding
       ↓
next base
```

Padding is unused space between regions.

---

# 91. `slot_memory_to_text()`

This function reports the first part of memory planning.

It does not modify any information.

---

# 92. First section

The report lists:

```text
TENSORES NÃO CONSTANTES
```

showing, for each tensor:

```text
tensor ID
name
shape
dtype
bytes per element
element count
total bytes
```

---

# 93. Example

```text
tensor=  12
name=activation_4
shape=[1, 64, 64, 24]
dtype=int8
bpe=1
elements=98304
bytes=98304
```

---

# 94. The `MAIOR TENSOR` (largest tensor) section

Next it shows the tensor that determined:

```text
max_bytes
```

---

# 95. Recorded information

The report shows:

```text
tensor_id

name

shape

dtype

bytes per element

element count

bytes before alignment
```

---

# 96. Final slot calculation

The last section shows:

```text
max_bytes
alignment
SLOT_BYTES
```

It is therefore possible to check:

```text
actual size
      ↓
alignment
      ↓
reserved size
```

---

# 97. `parameter_layout_to_text()`

This function reports the layout of constant parameters.

It shows:

```text
alignment
kernel_base_hint

KERNEL_BASE
KERNEL_BYTES

BIAS_BASE
BIAS_BYTES

MUL_BASE
MUL_BYTES

SHIFT_BASE
SHIFT_BYTES

Q6_BASE
Q6_BYTES

PARAMS_BASE
```

---

# 98. Usefulness

This report directly shows:

```text
where does each region start?

how much space does it occupy?

what will be the next free area?
```

before constructing the slots.

---

# 99. Intermediate pipeline point

At this point we have:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

with absolute addresses.

We do not yet have the complete layout.

---

# 100. The `WASM_PAGE_BYTES` constant

The file defines:

```python
WASM_PAGE_BYTES = 65536
```

A WebAssembly memory page has:

```text
65536 bytes
```

or:

```text
64 KiB
```

---

# 101. Difference between KB and KiB

Technically:

```text
64 KiB
=
64 × 1024
=
65536 bytes
```

This is the unit used by WebAssembly pages.

---

# 102. WebAssembly memory

When WAT declares:

```wat
(memory (export "memory") N)
```

the number:

```text
N
```

represents:

```text
initial page count
```

rather than byte count.

---

# 103. Example

```wat
(memory (export "memory") 17)
```

means:

```text
17 × 65536 bytes
```

resulting in:

```text
1,114,112 bytes
```

of initially available linear memory.

---

# 104. The `mem_pages_for()` function

The function:

```python
def mem_pages_for(
    end_addr,
):
```

calculates the minimum pages needed to cover a given final address.

---

# 105. Formula

```python
return (
    end_addr
    + WASM_PAGE_BYTES
    - 1
) // WASM_PAGE_BYTES
```

This is integer division rounded up.

---

# 106. Mathematical form

We can represent it as:

```text
MEM_PAGES =
ceil(
    MEM_END / 65536
)
```

---

# 107. Exact example

If:

```text
MEM_END = 65536
```

then:

```text
MEM_PAGES = 1
```

---

# 108. One byte beyond

If:

```text
MEM_END = 65537
```

a single page is insufficient.

Then:

```text
MEM_PAGES = 2
```

---

# 109. Larger example

If:

```text
MEM_END = 1,096,000
```

we would have approximately:

```text
1.096.000 / 65.536
≈ 16,72
```

therefore:

```text
MEM_PAGES = 17
```

---

# 110. Why round up?

The runtime cannot reserve:

```text
16.72 pages
```

Only whole pages.

Therefore:

```text
16,01 → 17
16,99 → 17
17,00 → 17
17,01 → 18
```

---

# 111. The `calculate_final_memory_layout()` function

This function completes memory planning.

It receives:

```text
parameter_layout

params_blob

slot_bases

slot_bytes
```

---

# 112. Why does it come later?

We now know:

```text
params_blob
```

and:

```text
slot_bases
```

which did not yet exist in:

```python
calculate_parameter_layout()
```

---

# 113. Responsibility

It answers:

```text
what is each region's interval?

what is the final address?

how many WASM pages do I need?

how much space remains in the last page?
```

---

# 114. The `regions` list

The function starts with:

```python
regions = []
```

Each memory block is represented by a dictionary.

---

# 115. WEIGHTS region

The following is added:

```python
{
    "name": "WEIGHTS",
    "base": kernel_base,
    "bytes": kernel_bytes,
}
```

---

# 116. BIAS region

Then:

```text
BIAS
```

with:

```text
bias_base
bias_bytes
```

---

# 117. MUL region

Next:

```text
MUL
```

with its base and size.

---

# 118. SHIFT region

Similarly:

```text
SHIFT
```

---

# 119. Q6 region

Then:

```text
Q6
```

---

# 120. PARAMS region

Now we finally know:

```python
len(
    params_blob
)
```

We can therefore record:

```python
{
    "name": "PARAMS",
    "base": params_base,
    "bytes": len(params_blob),
}
```

---

# 121. Difference from the partial layout

Previously we knew only:

```text
PARAMS_BASE
```

Now we know:

```text
PARAMS_BASE
+
PARAMS_BYTES
```

and therefore also:

```text
PARAMS_END
```

---

# 122. Including slots

Then:

```python
for slot_index, slot_base in enumerate(
    slot_bases
):
```

each slot is added.

---

# 123. Example

If:

```python
slot_bases = [
    507248,
    703856,
    900464,
]
```

and:

```text
slot_bytes = 196608
```

the following are created:

```text
SLOT0

base = 507248
bytes = 196608
```

```text
SLOT1

base = 703856
bytes = 196608
```

```text
SLOT2

base = 900464
bytes = 196608
```

The numbers only illustrate the produced format.

---

# 124. Calculating `end`

Each region then receives:

```python
region["end"] = (
    region["base"]
    + region["bytes"]
)
```

---

# 125. The `end` convention

This value represents:

```text
first address after the region
```

rather than the last valid byte.

---

# 126. Example

If:

```text
base = 100
bytes = 20
```

the region occupies:

```text
100 ... 119
```

and:

```text
end = 120
```

---

# 127. Half-open interval

Therefore:

```text
[base, end)
```

is the correct representation.

---

# 128. Why is this convention useful?

Because:

```text
bytes =
end - base
```

directly.

It also allows placing the next region exactly at:

```text
end
```

when no additional alignment is required.

---

# 129. Calculating `mem_end`

The code does:

```python
mem_end = max(
    region["end"]
    for region in regions
)
```

---

# 130. Why use `max()`?

Instead of simply assuming:

```text
last slot = last region
```

the code explicitly calculates which region ends at the highest address.

This makes finalization more robust to list order.

---

# 131. Example

If the end addresses are:

```text
WEIGHTS → 386656

BIAS → 414832

PARAMS → 507248

SLOT0 → 703856

SLOT1 → 900464

SLOT2 → 1097072
```

then:

```text
MEM_END = 1097072
```

---

# 132. Meaning of `MEM_END`

`MEM_END` represents:

```text
the first address after
the last used byte
```

---

# 133. Do not confuse it with the last byte index

If:

```text
MEM_END = 1097072
```

the last byte actually used is:

```text
1097071
```

---

# 134. Calculating `MEM_PAGES`

Then:

```python
mem_pages = mem_pages_for(
    mem_end
)
```

---

# 135. Memory actually reserved

The total reserved bytes will be:

```python
allocated_memory_bytes = (
    mem_pages
    * WASM_PAGE_BYTES
)
```

---

# 136. Example

If:

```text
MEM_PAGES = 17
```

we have:

```text
17 × 65536
=
1114112 bytes
```

---

# 137. Unused space

The code calculates:

```python
unused_memory_bytes = (
    allocated_memory_bytes
    - mem_end
)
```

---

# 138. Meaning

This is the space remaining between:

```text
MEM_END
```

and:

```text
the end of the last reserved page
```

---

# 139. Example

If:

```text
mem_end = 1097072

allocated_memory_bytes = 1114112
```

then:

```text
unused =
17040 bytes
```

---

# 140. Is this waste?

It is a natural effect of WebAssembly memory granularity.

Memory cannot be reserved byte by byte.

It is reserved in pages of:

```text
64 KiB
```

There may therefore always be an unused fraction of the last page.

---

# 141. Final return value

The function returns:

```python
{
    "regions": ...,

    "mem_end": ...,

    "mem_pages": ...,

    "wasm_page_bytes": ...,

    "allocated_memory_bytes": ...,

    "unused_memory_bytes": ...,

    "slot_bases": ...,

    "slot_bytes": ...,
}
```

---

# 142. `regions`

It is particularly useful for:

```text
report

validation

future visualization
```

because it contains every region in a uniform format.

---

# 143. Region example

```python
{
    "name": "MUL",
    "base": 414832,
    "bytes": 28176,
    "end": 443008,
}
```

---

# 144. Uniform representation

This lets us handle:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOT0
SLOT1
SLOT2
```

in the same way.

---

# 145. `final_memory_layout_to_text()`

This function produces the final report.

It starts with a table:

```text
REGIAO              BASE       BYTES         END
------------------------------------------------
...
```

---

# 146. Conceptual example

```text
REGIAO              BASE       BYTES         END
------------------------------------------------
WEIGHTS             2048      384608      386656
BIAS              386656       28176      414832
MUL               414832       28176      443008
SHIFT             443008       28176      471184
Q6                471184       28176      499360
PARAMS            499360        7888      507248
SLOT0             507248      196608      703856
SLOT1             703856      196608      900464
SLOT2             900464      196608     1097072
```

These values only illustrate the format.

---

# 147. Why is this table useful?

A single view allows checking:

```text
region order

each block's size

possible gaps

final address

slot positions
```

---

# 148. The `RESUMO` (summary) section

Next it displays:

```text
MEM_END

WASM_PAGE_BYTES

MEM_PAGES

reserved memory

remaining space

SLOT_BYTES

SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
```

---

# 149. Relationship with the WAT template

The result:

```python
memory_layout[
    "mem_pages"
]
```

is used to fill:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

---

# 150. Example

If:

```python
final_memory[
    "mem_pages"
] = 17
```

the generated WAT will contain:

```wat
(memory
    (export "memory")
    17
)
```

---

# 151. Slot bases

Previously calculated values also appear in WAT:

```wat
(global $SLOT0_BASE
    i32
    (i32.const ...)
)

(global $SLOT1_BASE
    i32
    (i32.const ...)
)

(global $SLOT2_BASE
    i32
    (i32.const ...)
)
```

---

# 152. Relationship to `weights.py`

`weights.py` produces:

```text
weights_raw
bias_raw
```

`memory.py` converts these blob sizes into:

```text
kernel_base
bias_base
```

---

# 153. Relationship with `quantization.py`

`quantization.py` produces:

```text
mul_blob
shift_blob
q6_blob
```

`memory.py` converts their sizes into:

```text
mul_base
shift_base
q6_base
```

---

# 154. Relationship with `params_blob.py`

`params_blob.py` produces:

```text
params_blob
```

and this final stage records:

```text
PARAMS_BASE
PARAMS_BYTES
PARAMS_END
```

---

# 155. Relationship with `slots.py`

`slots.py` decided:

```text
which layer uses SLOT0, SLOT1, or SLOT2
```

But it did not know:

```text
where those slots are physically located
```

That physical decision occurs in the memory planning used by subsequent stages.

---

# 156. Relationship to `layer_params.py`

A `LayerParam` needs pointers such as:

```text
wptr
bias_ptr
mul_ptr
shift_ptr
q6_ptr

in_ptr
out_ptr
```

These pointers depend on the bases calculated in this module.

---

# 157. Weight example

`weights.py`:

```text
tensor 30
offset = 5000
```

`memory.py`:

```text
WEIGHTS_BASE = 2048
```

Subsequent result:

```text
wptr =
2048 + 5000
=
7048
```

---

# 158. Multiplier example

`quantization.py`:

```text
mul_offset = 128
```

`memory.py`:

```text
MUL_BASE = 414832
```

Result:

```text
mul_ptr =
414832 + 128
=
414960
```

---

# 159. Activation example

`tensor_mapping.py`:

```text
tensor → SLOT1
```

Physical planning:

```text
SLOT1_BASE = 703856
```

Result:

```text
in_ptr = 703856
```

---

# 160. This module connects the data to real addresses

Before:

```text
relative offset
logical slot
```

Then:

```text
absolute base
```

And finally:

```text
pointer used by WASM
```

---

# 161. `kernel_base_hint` versus `kernel_base`

This distinction matters.

The first:

```text
KERNEL_BASE_HINT
```

is configuration.

The second:

```text
kernel_base
```

is the actual address after alignment.

---

# 162. Example

If:

```text
KERNEL_BASE_HINT = 2050
ALIGN = 16
```

then:

```text
kernel_base =
2064
```

Therefore:

```text
hint ≠ necessarily the base
```

---

# 163. `params_base` versus `PARAMS_END`

Another important distinction:

```text
params_base
```

indicates the start.

Whereas:

```text
params_base
+
len(params_blob)
```

indicates the end.

---

# 164. Planning phases

The project plans in stages because some sizes are available only after other transformations.

### Phase 1

```text
weights/bias/quantization
        ↓
calculate_parameter_layout()
```

Produces:

```text
PARAMS_BASE
```

---

### Phase 2

`LayerParam` is built.

Then:

```text
params_blob
```

now has a known size.

---

### Phase 3

The following are also known:

```text
slot_bases
```

Then:

```text
calculate_final_memory_layout()
```

completes the whole memory layout.

---

# 165. Why not calculate everything in one function?

Because this would create circular dependencies.

For example:

```text
slot_bases
```

depend on the final position of `PARAMS`.

But:

```text
params_blob
```

exists only after `LayerParams` have been built.

It therefore makes sense to have:

```text
partial layout
      ↓
LayerParams construction
      ↓
final layout
```

---

# 166. Temporal relationship

```text
weights.py
quantization.py
      │
      ▼
calculate_parameter_layout()
      │
      ▼
PARAMS_BASE
      │
      ▼
layer_params.py
      │
      ▼
params_blob.py
      │
      ▼
PARAMS_BYTES
      │
      ▼
calculate_final_memory_layout()
```

---

# 167. An important detail about `slot_bases`

The function:

```python
calculate_final_memory_layout()
```

does not calculate `slot_bases`.

It receives them already calculated.

Its role is to:

```text
include them in the final layout
```

rather than decide their positions again.

---

# 168. Separation of responsibilities

Thus:

```text
calculating slot bases
```

occurs when the `LayerParams` layout is defined.

Whereas:

```text
memory.py
```

completes and conceptually validates the global map using those bases.

---

# 169. The file does not generate WAT

The docstring makes this explicit (translated):

```text
Does not generate WAT.
Only completes memory planning.
```

This separation matters.

---

# 170. Correct architecture

```text
memory.py
   ↓
structured data

wat_generator.py
   ↓
converts this data
into WAT code
```

---

# 171. Avoided approach

We do not do this here:

```python
wat_lines.append(
    f"(memory ... {mem_pages})"
)
```

That would mix:

```text
memory engineering
```

with:

```text
code generation
```

---

# 172. Benefit

`memory.py` can be tested and analyzed independently of WAT.

For example:

```text
what is MEM_END?

is there enough memory?

how much space does each slot occupy?

how many pages would be needed?
```

can be studied without generating a WebAssembly module.

---

# 173. Nonoverlap invariant

The layout's structural objective is that distinct regions do not occupy the same bytes.

For two consecutive regions:

```text
A
B
```

we should have:

```text
A.end <= B.base
```

---

# 174. For sequentially calculated regions

This is guaranteed by construction:

```text
next_base =
align_up(
    previous_base
    +
    previous_bytes
)
```

---

# 175. For `PARAMS` and slots

Correctness depends on the bases calculated in the `layer_params.py` stage.

`calculate_final_memory_layout()` currently records and summarizes these regions, but does not explicitly check every pair for overlap.

---

# 176. Possible future validation

The following could be implemented:

```text
sort regions by base

for each consecutive pair:

previous.end <= current.base
```

Otherwise:

```text
RuntimeError
```

---

# 177. Why would it be useful?

Because an error in:

```text
params_bytes
slot_bases
slot_bytes
```

could create overlap without:

```text
MEM_END
```

alone revealing the problem.

---

# 178. Current state

In the current flow, bases are produced sequentially and WAT compiled successfully, but explicit validation would improve robustness in the future.

---

# 179. Another invariant

Every region must satisfy:

```text
bytes >= 0
```

and:

```text
end =
base + bytes
```

---

# 180. Empty region

If a blob has:

```text
0 bytes
```

we would have:

```text
base == end
```

This represents an empty region.

---

# 181. Minimum page count

`mem_pages_for()` returns exactly the minimum count needed to cover:

```text
[0, MEM_END)
```

---

# 182. If MEM_END is page-aligned

If:

```text
MEM_END = N × 65536
```

then:

```text
MEM_PAGES = N
```

No extra page is needed.

---

# 183. If just one byte is missing

If:

```text
MEM_END =
N × 65536 + 1
```

then:

```text
MEM_PAGES = N + 1
```

---

# 184. Relationship with ESP32

Although this calculation follows WebAssembly linear memory rules, the final page count also directly affects the memory needed to load the module in the embedded environment.

The larger:

```text
MEM_PAGES
```

the larger the linear region the runtime must provide.

---

# 185. Slots may be the largest memory consumer

An important layout property is that:

```text
weights
```

are not necessarily the largest memory category.

Because there are several slots:

```text
NUM_SLOTS × SLOT_BYTES
```

may represent a significant share.

---

# 186. Example

If:

```text
SLOT_BYTES = 196608
NUM_SLOTS = 3
```

we have:

```text
589824 bytes
```

for activations alone.

This is approximately:

```text
576 KiB
```

---

# 187. Benefit of reuse

Without reusable slots, space might need to be reserved for many activations simultaneously.

Planning reduces this to a fixed number of large regions.

---

# 188. Relationship with liveness

`memory.py` does not calculate liveness.

This was already handled conceptually by:

```text
graph.py
slots.py
```

Here we assume that:

```text
3 slots
```

are sufficient for the previously determined strategy.

---

# 189. Separation revisited

```text
slots.py
    ↓
when can a region be reused?
```

```text
memory.py
    ↓
how much space does this region occupy and where does it start?
```

---

# 190. `SLOT_BYTES` is not a specific tensor's size

Although determined by the largest tensor:

```text
SLOT_BYTES
```

is a property of the physical region.

During execution, it holds different tensors of the same size or smaller.

---

# 191. Example

```text
SLOT1 = 196608 bytes
```

can store, at different times:

```text
tensor A = 49152 bytes

tensor B = 98304 bytes

tensor C = 196608 bytes
```

All fit within the same region.

---

# 192. Remaining space within a slot

If a tensor occupies:

```text
49152 bytes
```

inside a slot of:

```text
196608 bytes
```

the remaining bytes are unused by that tensor.

This is expected.

---

# 193. Slots are not dynamically partitioned

The current implementation does not try to place simultaneously:

```text
tensor A
+
tensor B
```

in different parts of the same slot.

Each slot is treated as one reusable buffer.

---

# 194. Consequence for simplicity

This greatly simplifies the runtime.

An operation receives:

```text
in_ptr = SLOTn_BASE
```

without needing to calculate variable internal activation offsets.

---

# 195. Quantization blob sizes

Since:

```text
MUL
SHIFT
Q6
```

are `int32` arrays, their sizes are normally multiples of:

```text
4
```

Even so, the next region is aligned to:

```text
16 bytes
```

by the global policy.

---

# 196. Two conceptually different alignments

We have:

```text
internal blob structure
    ↓
int32 = 4 bytes
```

and:

```text
start of major regions
    ↓
ALIGN = 16 bytes
```

They are not the same thing.

---

# 197. Example

A `mul_blob` may have:

```text
28,180 bytes
```

which is not a multiple of 16.

Then:

```text
SHIFT_BASE
```

will be rounded up to the next multiple of 16.

---

# 198. Why not align every multiplier to 16 bytes?

That would be extremely wasteful.

Each value naturally occupies:

```text
4 bytes
```

The region as a whole is aligned; elements remain contiguous within it.

---

# 199. Same logic for weights

`int8` weights remain:

```text
1 byte per value
```

contiguous in the blob.

Alignment to 16 applies to the:

```text
region base
```

rather than every weight.

---

# 200. Addressing hierarchy

We can visualize:

```text
WASM memory
   │
   ├── region
   │      │
   │      └── internal offset
   │
   ▼
address
```

Example:

```text
MUL_BASE
    +
mul_offset
    +
channel × 4
```

---

# 201. Three levels

For a multiplier:

```text
level 1:
MUL_BASE

level 2:
operation's mul_offset

level 3:
channel × 4
```

Then:

```text
address =
MUL_BASE
+
mul_offset
+
channel × 4
```

---

# 202. For weights

Similarly:

```text
WEIGHTS_BASE
+
weight_tensor_off
+
internal kernel offset
```

---

# 203. For slots

Activations normally start directly at:

```text
SLOTn_BASE
```

and the kernel internally calculates offsets for:

```text
pixel
channel
row
column
```

---

# 204. Calculation function summary

| Function | Result |
| --------------------------------- | --------------------------------- |
| `tensor_numel()` | Tensor element count |
| `align_up()` | Next aligned address |
| `calculate_slot_bytes()` | Size of each slot |
| `calculate_parameter_layout()` | Constant parameter bases |
| `mem_pages_for()` | Minimum WASM page count |
| `calculate_final_memory_layout()` | Complete memory map |

---

# 205. Report function summary

| Function | Report |
| ------------------------------- | ------------------------------------ |
| `slot_memory_to_text()` | Tensors and slot size calculation |
| `parameter_layout_to_text()` | Parameter bases and sizes |
| `final_memory_layout_to_text()` | Complete layout and WASM pages |

---

# 206. Data entering this module

From `config.py`:

```text
BATCH
ALIGN
KERNEL_BASE_HINT
```

From `weights.py`:

```text
weights_raw
bias_raw
```

From `quantization.py`:

```text
mul_blob
shift_blob
q6_blob
```

Later:

```text
params_blob
slot_bases
```

---

# 207. Output data

Among others:

```text
SLOT_BYTES

WEIGHTS_BASE
BIAS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE
PARAMS_BASE

MEM_END
MEM_PAGES
```

---

# 208. Configuration versus calculation

To emphasize:

```text
ALIGN = 16
```

is a configuration policy.

Whereas:

```text
BIAS_BASE
```

is a calculated result.

---

# 209. Similarly

```text
KERNEL_BASE_HINT = 2048
```

is configuration.

But:

```text
kernel_base
```

is the result of alignment.

---

# 210. And

```text
NUM_SLOTS = 3
```

is configuration.

While:

```text
SLOT_BYTES
```

is derived from the model.

---

# 211. Model-dependent addresses should not be hardcoded

The architectural principle is:

```text
model changes
   ↓
sizes may change
   ↓
bases are recalculated
   ↓
WAT receives new values
```

Not:

```text
model changes
   ↓
edit addresses manually
```

---

# 212. Relationship with the WAT template

WAT simply consumes these results.

Example:

```wat
(global $WEIGHTS_BASE
    i32
    (i32.const @@WEIGHTS_BASE@@)
)
```

The extractor replaces:

```text
@@WEIGHTS_BASE@@
```

with the value produced by memory planning.

---

# 213. Same principle for memory

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

The template does not need to know in advance how many pages the model requires.

---

# 214. Benefit for new models

When replacing:

```text
model_int8_esp32.tflite
```

with another compatible model, the following may change:

```text
weight count
biases
multipliers
shifts
Q6
LayerParams
maximum activation size
```

and consequently:

```text
all bases
MEM_END
MEM_PAGES
```

The pipeline recalculates these values.

---

# 215. Central responsibility

We can summarize `memory.py` with the question:

```text
how can sizes
and logical offsets be converted

into a consistent physical map
of WebAssembly linear memory?
```

---

# 216. Complete module flow

```text
                MODEL + BLOBS
                     │
                     ▼
          calculate_slot_bytes()
                     │
                     ▼
                SLOT_BYTES


weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
      │
      ▼
calculate_parameter_layout()
      │
      ├── WEIGHTS_BASE
      ├── BIAS_BASE
      ├── MUL_BASE
      ├── SHIFT_BASE
      ├── Q6_BASE
      └── PARAMS_BASE
              │
              ▼
       LayerParams generated
              │
              ▼
         params_blob
              │
              ▼
      slot bases
              │
              ▼
calculate_final_memory_layout()
              │
              ├── regions
              ├── MEM_END
              ├── MEM_PAGES
              └── reserved memory
```

---

# 217. Role in the complete pipeline

```text
┌─────────────────────────────┐
│         weights.py          │
│                             │
│ weights_raw                 │
│ bias_raw                    │
└──────────────┬──────────────┘
               │
               │
┌──────────────▼──────────────┐
│      quantization.py        │
│                             │
│ mul_blob                    │
│ shift_blob                  │
│ q6_blob                     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         memory.py           │
│                             │
│ bases                       │
│ sizes                       │
│ SLOT_BYTES                  │
│ PARAMS_BASE                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      layer_params.py        │
│                             │
│ LayerParams                 │
│ slot_bases                  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│       params_blob.py        │
│                             │
│ params_blob                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         memory.py           │
│                             │
│ finalization                │
│ MEM_END                     │
│ MEM_PAGES                   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      wat_generator.py       │
│                             │
│ injects values into WAT     │
└─────────────────────────────┘
```

---

# 218. Summary

`memory.py` converts structures produced by previous stages into a physical map of WebAssembly linear memory.

Its first responsibility is to find the largest nonconstant tensor:

```text
largest tensor
     ↓
align_up()
     ↓
SLOT_BYTES
```

This ensures that any intermediate activation compatible with the model fits in any reusable slot.

Its second responsibility is to organize constant parameters:

```text
KERNEL/WEIGHTS
      ↓
BIAS
      ↓
MUL
      ↓
SHIFT
      ↓
Q6
      ↓
PARAMS_BASE
```

Each base is calculated from the preceding region's end and aligned according to:

```text
ALIGN = 16
```

Its third responsibility comes after `LayerParams` and slots have been placed. All regions are then collected:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOT0
SLOT1
SLOT2
```

and each receives:

```text
base
bytes
end
```

The largest `end` determines:

```text
MEM_END
```

and then:

```text
MEM_PAGES =
ceil(
    MEM_END / 65536
)
```

determines the minimum number of 64 KiB pages the WebAssembly module must declare.

This module therefore converts:

```text
abstract sizes
offsets
and logical slots
```

into:

```text
absolute addresses
and concrete capacity
of WASM linear memory
```

without directly generating WebAssembly code.

This separation lets `wat_generator.py` serve only as the final generation stage: it receives a calculated, conceptually validated layout and injects those values into the template.
