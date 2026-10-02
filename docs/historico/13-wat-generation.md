[English](13-wat-generation.md) | [Português (Brasil)](13-geracao-wat.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in the Portuguese edition.

# 13 — Generating the WAT module (`wat_generator.py`)

## 1. Module purpose

`extractor/wat_generator.py` performs the final extraction stage: converting a static WAT template into a WAT file fully configured for the processed model.

All model-dependent information has already been calculated:

```text
weights
biases
multipliers
shifts
Q6

LayerParams

memory layout

slot bases

number of layers

memory size

output address
```

The generator no longer needs to interpret TFLite.

It only combines:

```text
WAT template
    +
calculated values
    +
binary blobs
        │
        ▼
final WAT
```

The overall flow is:

```text
model.tflite
     │
     ▼
extraction and calculations
     │
     ├── weights_raw
     ├── bias_raw
     ├── mul_blob
     ├── shift_blob
     ├── q6_blob
     ├── params_blob
     │
     ├── addresses
     ├── slots
     └── MEM_PAGES
             │
             ▼
       wat_generator.py
             │
             ▼
       generated/model.wat
```

---

# 2. Architectural responsibility

This module's main architectural decision is that it **does not calculate model parameters**.

It does not decide:

```text
how much space a slot occupies

where weights start

what a convolution's multiplier is

how to calculate SAME padding

which tensor goes into which slot

what the zero point is

how to build a LayerParam
```

All these decisions have already been made.

The generator only answers:

```text
how can the calculated results be inserted
into the WAT template?
```

This clearly separates:

```text
CALCULATION
   ↓
extractor/*

FINAL GENERATION
   ↓
wat_generator.py
```

---

# 3. Imports

The file starts with:

```python
from pathlib import Path
import re
```

Only two functions outside the standard library are needed.

---

# 4. `Path`

`Path` is used to:

```text
read the template

create the output directory

write the generated WAT

get the final file size
```

Paths therefore remain represented as `Path` objects.

---

# 5. `re`

The `re` module finds placeholders remaining in WAT after substitutions.

This serves as a final template check.

---

# 6. `PLACEHOLDER_PATTERN`

The regular expression is:

```python
PLACEHOLDER_PATTERN = re.compile(
    r"@@[A-Z0-9_]+@@"
)
```

It recognizes placeholders in the form:

```text
@@NAME@@
```

where `NAME` may contain:

```text
A-Z

0-9

_
```

---

# 7. Recognized examples

```text
@@MEM_PAGES@@

@@PARAMS_BASE@@

@@LP_SIZE@@

@@NUM_LAYERS@@

@@SLOT0_BASE@@

@@RESULT_COUNT@@
```

---

# 8. Unrecognized examples

With this regex, forms such as:

```text
@@mem_pages@@
```

or:

```text
@MEM_PAGES@
```

do not match the pattern.

The project's convention is therefore:

```text
@@UPPERCASE_PLACEHOLDER@@
```

---

# 9. Why validate placeholders?

Without this check, the generator could produce something like:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

and the issue would only be discovered during compilation.

The code instead detects it in the generator itself.

---

# 10. The `_as_bytes()` function

The first helper function is:

```python
def _as_bytes(value):
```

Its responsibility is to normalize different binary objects into:

```python
bytes
```

---

# 11. Input already of type `bytes`

If:

```python
isinstance(
    value,
    bytes,
)
```

the function simply returns:

```python
return value
```

No explicit copy is needed.

---

# 12. `bytearray` input

If the object is:

```python
bytearray
```

it is converted through:

```python
bytes(value)
```

---

# 13. Why convert `bytearray`?

During construction, blobs are often assembled as mutable structures:

```text
bytearray
```

Once ready, it is convenient to treat them as:

```text
bytes
```

which are immutable.

---

# 14. `memoryview` input

If:

```python
isinstance(
    value,
    memoryview,
)
```

the following is used:

```python
value.tobytes()
```

---

# 15. Objects with `.tobytes()`

There is then a more general rule:

```python
if hasattr(
    value,
    "tobytes",
):
    return value.tobytes()
```

This accepts binary objects providing that method.

A common example in scientific Python is a NumPy object.

---

# 16. Why this flexibility?

Different modules may work with:

```text
bytes

bytearray

memoryview

arrays with tobytes()
```

`_as_bytes()` provides a single boundary:

```text
any supported binary representation
            ↓
          bytes
```

---

# 17. Incompatible type

If none of the conditions is met:

```python
raise TypeError(...)
```

---

# 18. Example

Passing something like:

```python
"abc"
```

is not automatically interpreted as:

```text
UTF-8
```

The function raises an error.

This matters because the generator expects:

```text
binary data
```

rather than arbitrary text.

---

# 19. Error message

The exception includes:

```python
type(value)
```

revealing which unexpected type reached the generator.

---

# 20. Responsibility of `_as_bytes()`

We can summarize:

```text
bytes ───────────────┐
                     │
bytearray ───────────┤
                     │
memoryview ──────────┤
                     ▼
                _as_bytes()
                     │
object.tobytes() ────┤
                     │
                     ▼
                   bytes
```

---

# 21. The `wat_data_from_bytes()` function

The second function is:

```python
def wat_data_from_bytes(
    data,
    base,
):
```

It converts a binary blob into an:

```text
active data segment
```

in WAT syntax.

---

# 22. Data segment concept

In WebAssembly, a data segment initializes linear memory with bytes defined in the module.

Conceptually:

```text
WASM file is loaded
        │
        ▼
segment bytes
        │
        ▼
copied into memory
starting at the configured address
```

---

# 23. Generated form

The function produces:

```wat
(data
    (i32.const BASE)
    "BYTES"
)
```

The implementation represents it as a single string:

```wat
(data (i32.const BASE) "...")
```

---

# 24. `base`

The argument:

```python
base
```

represents the starting linear-memory address where data should be placed.

---

# 25. Conceptual example

If:

```text
base = 2048
```

the segment will have the form:

```wat
(data
    (i32.const 2048)
    "..."
)
```

---

# 26. Normalizing data

First:

```python
raw = _as_bytes(
    data
)
```

The rest of the function therefore works exclusively with:

```text
bytes
```

---

# 27. Empty blob

If:

```python
len(raw) == 0
```

the return value is:

```python
""
```

---

# 28. Why not generate an empty segment?

Something like:

```wat
(data
    (i32.const 1234)
    ""
)
```

would add no data to memory.

The function simply produces no segment.

---

# 29. Byte encoding

The central part is:

```python
encoded = "".join(
    f"\\{byte:02x}"
    for byte in raw
)
```

---

# 30. What does `byte` represent?

When iterating over a Python `bytes` object, each item is an integer:

```text
0 ... 255
```

For example:

```python
raw = bytes([
    0,
    1,
    127,
    255,
])
```

produces values:

```text
0
1
127
255
```

during the loop.

---

# 31. Hexadecimal formatting

The format specifier:

```text
02x
```

produces:

```text
lowercase hexadecimal
with two digits
```

Examples:

```text
0   → 00

1   → 01

10  → 0a

127 → 7f

255 → ff
```

---

# 32. WAT escape

Each byte receives a backslash:

```text
\00

\01

\7f

\ff
```

Thus:

```python
bytes([
    0x01,
    0x7F,
    0xFF,
])
```

conceptually produces:

```text
\01\7f\ff
```

---

# 33. Why encode every byte?

The docstring itself explains the decision (translated):

```text
All bytes are written as hexadecimal escapes,
avoiding problems with special characters.
```

The generator therefore does not try to decide:

```text
can this byte be written as a character?

does this one need escaping?

do quotation marks need escaping?

does a backslash need escaping?
```

All follow the same rule.

---

# 34. Advantage

A blob may contain any byte:

```text
00

22

5c

ff
```

without risking confusion with:

```text
quotation marks

backslash

newline

text character
```

inside the WAT string.

---

# 35. Final result

The function returns:

```python
f'(data (i32.const {int(base)}) '
f'"{encoded}")'
```

---

# 36. Converting the base

Using:

```python
int(base)
```

normalizes external integer types, such as NumPy values, before writing them into WAT.

---

# 37. Simple example

Input:

```python
data = bytes([
    1,
    2,
    255,
])

base = 2048
```

Output:

```wat
(data (i32.const 2048) "\01\02\ff")
```

---

# 38. Relationship with the layout

This function does not know whether bytes represent:

```text
weights

biases

multipliers

LayerParams
```

It only knows:

```text
data

+

address
```

---

# 39. Important separation

```text
weights.py
    ↓
defines contents

memory.py
    ↓
defines address

wat_data_from_bytes()
    ↓
combines both in WAT syntax
```

---

# 40. The `build_data_segments()` function

The next function:

```python
def build_data_segments(
    *,
    parameter_layout,
    weights_bias,
    quantization,
    params_serialization,
):
```

builds all model-dependent data segments.

---

# 41. The `segments` list

Initially:

```python
segments = []
```

Each nonempty blob produces one list element.

---

# 42. The `sources` structure

The code builds an explicit list:

```python
sources = [
    ...
]
```

containing pairs:

```text
(base, data)
```

---

# 43. First segment: WEIGHTS

```python
(
    parameter_layout[
        "kernel_base"
    ],
    weights_bias[
        "weights_raw"
    ],
)
```

Thus:

```text
weights_raw
    ↓
WEIGHTS_BASE
```

---

# 44. Second: BIAS

```text
bias_raw
    ↓
BIAS_BASE
```

---

# 45. Third: MUL

```text
mul_blob
    ↓
MUL_BASE
```

---

# 46. Fourth: SHIFT

```text
shift_blob
    ↓
SHIFT_BASE
```

---

# 47. Fifth: Q6

```text
q6_blob
    ↓
Q6_BASE
```

---

# 48. Sixth: PARAMS

```text
params_blob
    ↓
PARAMS_BASE
```

---

# 49. Segment order

The current textual order is therefore:

```text
WEIGHTS

BIAS

MUL

SHIFT

Q6

PARAMS
```

This follows the logical organization used in the memory layout.

---

# 50. Does textual order define addresses?

No.

Addresses are explicitly defined through:

```wat
(i32.const BASE)
```

Therefore it is the:

```text
base
```

of each segment that determines where its bytes are initialized.

Textual order only makes the file more predictable and readable.

---

# 51. Iteration

The code executes:

```python
for base, data in sources:
```

---

# 52. Normalization again

Each:

```python
data
```

is passed through:

```python
_as_bytes()
```

before the segment is created.

---

# 53. Empty segments

If:

```python
if not raw:
    continue
```

the segment is omitted entirely.

---

# 54. Example

If, hypothetically:

```text
bias_raw = b""
```

no:

```wat
(data ... bias ...)
```

will be written.

---

# 55. A memory region may still exist logically

Absence of a data segment does not necessarily mean the layout lacks an associated base.

It only means:

```text
there are no bytes to initialize
in that region
```

---

# 56. Generating the segment

For nonempty data:

```python
wat_data_from_bytes(
    raw,
    base,
)
```

is called.

---

# 57. Indentation

The code adds:

```python
"  "
```

before each segment.

Text inserted into the WAT module is thus visually indented.

---

# 58. Visual separation

Finally:

```python
"\n\n".join(
    segments
)
```

places a blank line between segments.

The result is conceptually:

```wat
  (data ... WEIGHTS ...)

  (data ... BIAS ...)

  (data ... MUL ...)

  (data ... SHIFT ...)

  (data ... Q6 ...)

  (data ... PARAMS ...)
```

---

# 59. Why one segment per major region?

The generator does not create an individual data segment for each:

```text
weight tensor

bias tensor

LayerParam
```

because previous modules have already concatenated these data into blobs.

---

# 60. Comparison

Without blobs:

```text
weight 0 → data segment

weight 1 → data segment

weight 2 → data segment

bias 0 → data segment

...
```

With the current architecture:

```text
all weights
    ↓
weights_raw
    ↓
1 data segment
```

---

# 61. Advantage

This keeps WAT simpler.

It also preserves the abstraction of:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
```

as large contiguous regions.

---

# 62. What does `build_data_segments()` not do?

The function does not:

```text
calculate bases

check overlap

calculate memory size

interpret bytes

align regions
```

It assumes that:

```text
parameter_layout
```

already contains correct addresses.

---

# 63. The `generate_wat()` function

This is the file's main function:

```python
def generate_wat(
    *,
    template_path,
    output_path,
    parameter_layout,
    layer_memory,
    final_memory,
    params_serialization,
    weights_bias,
    quantization,
    layer_params,
):
```

It combines all previous information and produces the final file.

---

# 64. Inputs

### `template_path`

Path to:

```text
wat/model_template.wat
```

or another equivalent template.

---

### `output_path`

Path where the final WAT will be saved.

Example:

```text
generated/model.wat
```

---

### `parameter_layout`

Contains:

```text
WEIGHTS_BASE

BIAS_BASE

MUL_BASE

SHIFT_BASE

Q6_BASE

PARAMS_BASE
```

---

### `layer_memory`

Provides:

```text
slot_bases
```

and other layer memory information.

---

### `final_memory`

Mainly provides:

```text
MEM_PAGES
```

already calculated.

---

### `params_serialization`

Contains:

```text
params_blob

records

LP_SIZE

serialization information
```

---

### `weights_bias`

Contains:

```text
weights_raw

bias_raw
```

---

### `quantization`

Contains:

```text
mul_blob

shift_blob

q6_blob
```

---

### `layer_params`

Structured operation list.

It is mainly used for:

```text
number of layers

identifying the last layer

final output shape
```

---

# 65. Converting paths

First:

```python
template_path = Path(
    template_path
)

output_path = Path(
    output_path
)
```

The function thus accepts `Path`-compatible paths.

---

# 66. Reading the template

The file is loaded through:

```python
wat = template_path.read_text(
    encoding="utf-8"
)
```

---

# 67. The template remains text

At this point:

```text
wat
```

is a string containing:

```text
WAT code

+

placeholders
```

Conceptual example:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

---

# 68. Validating LayerParams

Before making substitutions:

```python
if not layer_params:
```

produces:

```text
RuntimeError
```

with:

```text
"Nenhuma LayerParam foi gerada."
```

---

# 69. Why is this necessary?

Without layers, later code would try:

```python
layer_params[-1]
```

which would have no meaning.

An executable model in this pipeline must also contain at least the synthetic layer and/or actual operations.

---

# 70. Serialization records

Then:

```python
records = (
    params_serialization[
        "records"
    ]
)
```

---

# 71. Validating records

If empty:

```text
RuntimeError
```

is raised.

---

# 72. Why are `records` needed?

The generator needs to retrieve:

```text
out_ptr
```

from the last serialized layer.

This information is in:

```text
final_record
```

---

# 73. Last layer

The code uses:

```python
final_layer = (
    layer_params[-1]
)
```

and:

```python
final_record = (
    records[-1]
)
```

---

# 74. Important assumption

The implementation assumes that:

```text
last layer_params entry
```

and:

```text
last record
```

represent the same operation.

This holds in the normal flow because:

```text
params_blob.py
```

serializes `layer_params` sequentially.

---

# 75. No explicit size comparison

The current code does not directly check:

```text
len(records)
==
len(layer_params)
```

`build_params_blob()` naturally produces this equality in the expected pipeline.

An explicit check could be added later.

---

# 76. `RESULT_BASE`

The final output address is obtained through:

```python
result_base = int(
    final_record[
        "out_ptr"
    ]
)
```

---

# 77. Meaning

`result_base` is:

```text
physical slot base
where the last layer
wrote its output
```

---

# 78. Example

If the last layer writes to:

```text
SLOT2
```

and:

```text
SLOT2_BASE = 900464
```

then:

```text
RESULT_BASE = 900464
```

---

# 79. Important

`RESULT_BASE` is not a new memory region.

It points to:

```text
an existing slot
```

containing the last operation's result.

---

# 80. Flow

```text
last LayerParam
      │
      ▼
out_slot
      │
      ▼
out_ptr
      │
      ▼
RESULT_BASE
```

---

# 81. `RESULT_COUNT`

The number of output values is calculated through:

```python
result_count = int(
    final_layer["out_h"]
    * final_layer["out_w"]
    * final_layer["cout"]
)
```

---

# 82. Formula

```text
RESULT_COUNT
=
out_h
×
out_w
×
cout
```

---

# 83. Classification example

If output is represented as:

```text
1 × 1 × 1000
```

then:

```text
RESULT_COUNT
=
1 × 1 × 1000
=
1000
```

---

# 84. Advantage over a hardcoded value

The runtime does not need:

```text
1000
```

fixed manually.

If another compatible model produces:

```text
10 classes
```

we get:

```text
RESULT_COUNT = 10
```

automatically.

---

# 85. Spatial output

If the last layer hypothetically produces:

```text
7 × 7 × 32
```

we would have:

```text
RESULT_COUNT
=
7 × 7 × 32
=
1568
```

---

# 86. Current batch assumption

The formula uses only:

```text
H × W × C
```

and does not explicitly multiply by batch.

This matches the current pipeline, which uses:

```text
batch = 1
```

as a convention.

Generic support for batch sizes greater than 1 would require revisiting this part.

---

# 87. Retrieving slots

The code obtains:

```python
slot_bases = (
    layer_memory[
        "slot_bases"
    ]
)
```

---

# 88. Validating three slots

Then:

```python
if len(slot_bases) != 3:
```

raises an error.

---

# 89. Why exactly three?

The current WAT template has explicit placeholders:

```text
@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@
```

There is therefore a concrete dependency:

```text
current template
    ↕
3 slots
```

---

# 90. This is not a theoretical WebAssembly limitation

It is a decision of the:

```text
current template
+
current runtime
```

The extractor could support another count in the future, but the template would need adaptation.

---

# 91. Error message

The code reports:

```text
"O template atual espera exatamente 3 slots..."
```

This clarifies that:

```text
the issue is not NUM_SLOTS in the abstract
```

but:

```text
compatibility with the current template
```

---

# 92. The `replacements` dictionary

The next central stage is:

```python
replacements = {
    ...
}
```

It relates:

```text
text placeholder
        ↓
calculated value
```

---

# 93. `@@MEM_PAGES@@`

Receives:

```python
final_memory[
    "mem_pages"
]
```

This value defines the initial WebAssembly page count.

---

# 94. Origin

```text
memory.py
    ↓
MEM_END
    ↓
ceil(MEM_END / 65536)
    ↓
MEM_PAGES
```

---

# 95. `@@PARAMS_BASE@@`

Receives:

```python
parameter_layout[
    "params_base"
]
```

---

# 96. Runtime use

Allows WAT to locate:

```text
LayerParam[0]
```

and subsequently:

```text
LayerParam[i]
=
PARAMS_BASE
+
i × LP_SIZE
```

---

# 97. `@@LP_SIZE@@`

Receives:

```python
params_serialization[
    "layer_param_size"
]
```

---

# 98. Current value

With the current structure:

```text
LP_SIZE = 116
```

---

# 99. Why get it from serialization?

This keeps the generator dependent on the actual pipeline result rather than a number:

```text
116
```

hardcoded inside it.

---

# 100. `@@NUM_LAYERS@@`

Receives:

```python
len(
    layer_params
)
```

---

# 101. Includes the synthetic layer

Because `layer_params` starts with:

```text
RGB565_TO_RGB888
```

this total already includes the synthetic operation.

---

# 102. Example

```text
67 actual operations
+
1 synthetic operation
=
68 layers
```

Therefore:

```text
@@NUM_LAYERS@@
    ↓
68
```

---

# 103. `@@WEIGHTS_BASE@@`

Receives:

```text
kernel_base
```

from the layout.

---

# 104. `@@BIAS_BASE@@`

Receives:

```text
bias_base
```

---

# 105. `@@MUL_BASE@@`

Receives:

```text
mul_base
```

---

# 106. `@@SHIFT_BASE@@`

Receives:

```text
shift_base
```

---

# 107. `@@Q6_BASE@@`

Receives:

```text
q6_base
```

---

# 108. Why does the template receive bases when LayerParams already contain pointers?

LayerParams already contain many absolute pointers.

The template may still need global bases for:

```text
debug

globals

helper routines

structural documentation

or runtime-specific logic
```

The generator simply supplies the values expected by the template.

---

# 109. Slot bases

The following are replaced:

```text
@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@
```

---

# 110. Values

```python
slot_bases[0]

slot_bases[1]

slot_bases[2]
```

respectively.

---

# 111. `@@RESULT_BASE@@`

Receives:

```text
last layer's out_ptr
```

---

# 112. `@@RESULT_COUNT@@`

Receives:

```text
out_h × out_w × cout
```

of the last layer.

---

# 113. Placeholder table

| Placeholder | Source |
| ------------------ | ------------------------------------------ |
| `@@MEM_PAGES@@`    | `final_memory["mem_pages"]`                |
| `@@PARAMS_BASE@@`  | `parameter_layout["params_base"]`          |
| `@@LP_SIZE@@`      | `params_serialization["layer_param_size"]` |
| `@@NUM_LAYERS@@`   | `len(layer_params)`                        |
| `@@WEIGHTS_BASE@@` | `parameter_layout["kernel_base"]`          |
| `@@BIAS_BASE@@`    | `parameter_layout["bias_base"]`            |
| `@@MUL_BASE@@`     | `parameter_layout["mul_base"]`             |
| `@@SHIFT_BASE@@`   | `parameter_layout["shift_base"]`           |
| `@@Q6_BASE@@`      | `parameter_layout["q6_base"]`              |
| `@@SLOT0_BASE@@`   | `slot_bases[0]`                            |
| `@@SLOT1_BASE@@`   | `slot_bases[1]`                            |
| `@@SLOT2_BASE@@`   | `slot_bases[2]`                            |
| `@@RESULT_BASE@@`  | `final_record["out_ptr"]`                  |
| `@@RESULT_COUNT@@` | `out_h × out_w × cout`                     |

There is also:

```text
@@DATA_SEGMENTS@@
```

which is handled separately.

---

# 114. Replacing values

The code iterates over:

```python
for placeholder, value
in replacements.items():
```

---

# 115. Conversion

Each value is converted into:

```python
str(
    int(value)
)
```

---

# 116. Why `int()` first?

This normalizes values coming from external integer types.

---

# 117. Why `str()` next?

Because:

```python
wat.replace()
```

operates on strings.

---

# 118. Example

Template:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

With:

```text
MEM_PAGES = 17
```

becomes:

```wat
(memory
    (export "memory")
    17
)
```

---

# 119. `str.replace()`

The function uses:

```python
wat = wat.replace(
    placeholder,
    replacement,
)
```

---

# 120. Consequence

If a placeholder appears multiple times in the template, every occurrence is replaced.

---

# 121. Why this is useful

For example:

```text
@@SLOT0_BASE@@
```

may appear in:

```text
a global

a comment

or another expression
```

and all occurrences receive the same value.

---

# 122. `@@DATA_SEGMENTS@@`

Blobs are not inserted through the numeric dictionary.

First:

```python
data_segments = (
    build_data_segments(...)
)
```

is called.

---

# 123. Function inputs

The following are supplied:

```text
parameter_layout

weights_bias

quantization

params_serialization
```

This allows combining:

```text
BASE
+
BLOB
```

for each region.

---

# 124. Result

`data_segments` is a string such as:

```wat
  (data
      (i32.const WEIGHTS_BASE)
      "...")

  (data
      (i32.const BIAS_BASE)
      "...")

  ...
```

in the compact representation produced by the function.

---

# 125. Insertion

Then:

```python
wat = wat.replace(
    "@@DATA_SEGMENTS@@",
    data_segments,
)
```

---

# 126. Why handle this separately?

The other placeholders receive:

```text
an integer
```

Whereas:

```text
@@DATA_SEGMENTS@@
```

receives:

```text
a large block of WAT code
```

---

# 127. Relationship with blobs

```text
weights_raw
     ↓
hex escapes
     ↓
WAT data segment

bias_raw
     ↓
hex escapes
     ↓
WAT data segment

mul_blob
     ↓
hex escapes
     ↓
WAT data segment

...
```

---

# 128. Conceptual initialized-memory example

Suppose:

```text
WEIGHTS_BASE = 2048

BIAS_BASE = 10000

PARAMS_BASE = 20000
```

WAT could receive:

```wat
(data
    (i32.const 2048)
    "\01\02..."
)

(data
    (i32.const 10000)
    "\0a\00..."
)

(data
    (i32.const 20000)
    "\01\00\00\00..."
)
```

---

# 129. The generator does not interpret these bytes

To it:

```text
"\01\02..."
```

is just binary contents.

Semantics were defined earlier.

---

# 130. Validating unresolved placeholders

After all substitutions:

```python
unresolved = sorted(
    set(
        PLACEHOLDER_PATTERN.findall(
            wat
        )
    )
)
```

---

# 131. `findall()`

The regex searches for any remaining fragment of the form:

```text
@@NAME@@
```

---

# 132. Using `set`

If a placeholder appears multiple times:

```text
@@FOO@@
@@FOO@@
@@FOO@@
```

the error report shows only:

```text
@@FOO@@
```

once.

---

# 133. Using `sorted()`

Remaining placeholders are sorted.

This makes the error message deterministic and easier to read.

---

# 134. Error

If the list is not empty:

```python
raise RuntimeError(
    "Placeholders WAT não resolvidos: "
    + ", ".join(unresolved)
)
```

---

# 135. Example

If the template adds:

```text
@@SOMETHING_NEW@@
```

but `generate_wat()` is not updated, the result will be:

```text
Placeholders WAT não resolvidos:
@@SOMETHING_NEW@@
```

instead of silently generating an incomplete template.

---

# 136. Importance for template evolution

This mechanism creates a contract between:

```text
model_template.wat
```

and:

```text
wat_generator.py
```

If the template requires a new variable:

```text
@@NEW_VALUE@@
```

the generator must learn to fill it.

---

# 137. Limit of this validation

The regex only detects placeholders matching the defined pattern.

It does not check:

```text
complete WAT syntax

WebAssembly types

function indices

import validity

kernel correctness
```

---

# 138. Therefore

There are two distinct validations:

```text
wat_generator.py
    ↓
fully populated template
```

and later:

```text
wat2wasm
    ↓
valid WebAssembly syntax and structure
```

---

# 139. The generator does not compile WAT

This is an important point.

The function:

```python
generate_wat()
```

produces:

```text
.wat
```

It does not call:

```text
wat2wasm
```

and does not directly produce:

```text
.wasm
```

---

# 140. Separation of responsibilities

```text
wat_generator.py
      ↓
source WAT

wat2wasm
      ↓
binary WASM
```

This keeps the extractor independent of the compilation tool.

---

# 141. Output directory

Before writing the file:

```python
output_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

the following executes.

---

# 142. `parents=True`

Allows creating the entire required directory chain.

For example:

```text
generated/models/esp32/model.wat
```

can have its intermediate directories created.

---

# 143. `exist_ok=True`

An existing directory is not treated as an error.

---

# 144. Writing

The file is saved through:

```python
output_path.write_text(
    wat,
    encoding="utf-8",
)
```

---

# 145. Consequence

If the file already exists:

```text
generated/model.wat
```

it is overwritten with the current WAT.

---

# 146. Source of truth

This reinforces that:

```text
generated/model.wat
```

is a generated artifact.

It should not be manually edited as the primary source for model-dependent configuration.

The source is:

```text
wat/model_template.wat
```

*

```text
data calculated by the extractor
```

---

# 147. Function return value

After writing, the function returns metadata:

```python
{
    "output_path": ...,
    "mem_pages": ...,
    "num_layers": ...,
    "result_base": ...,
    "result_count": ...,
    "wat_bytes": ...,
}
```

---

# 148. `output_path`

This is the:

```python
Path
```

object for the generated file.

---

# 149. `mem_pages`

This is:

```python
int(
    final_memory[
        "mem_pages"
    ]
)
```

The caller can thus record configured memory without rereading WAT.

---

# 150. `num_layers`

This is:

```python
len(
    layer_params
)
```

---

# 151. `result_base`

The absolute address where the last layer's output starts.

---

# 152. `result_count`

The number of output elements according to:

```text
out_h × out_w × cout
```

---

# 153. `wat_bytes`

It is obtained through:

```python
output_path.stat().st_size
```

---

# 154. Meaning

This represents the actual WAT file size on the filesystem:

```text
in bytes
```

---

# 155. Do not confuse this with WASM size

```text
wat_bytes
```

is:

```text
textual .wat file size
```

It does not represent:

```text
compiled .wasm size
```

or:

```text
linear memory capacity
```

---

# 156. Why can WAT become large?

Blobs are encoded as text.

A single binary byte:

```text
0xff
```

becomes, in text:

```text
\ff
```

that is, several characters in the WAT file.

The `.wat` may therefore be significantly larger than the sum of its binary blobs.

---

# 157. WASM memory does not use that textual size

After compilation:

```text
\ff
```

again represents:

```text
one byte
```

in the binary data segment.

---

# 158. Complete `generate_wat()` flow

```text
template_path
      │
      ▼
read_text()
      │
      ▼
WAT template
      │
      ├── validate layers
      │
      ├── validate records
      │
      ▼
identify last layer
      │
      ├── RESULT_BASE
      └── RESULT_COUNT
      │
      ▼
validate 3 slots
      │
      ▼
replace numeric placeholders
      │
      ▼
build_data_segments()
      │
      ▼
replace @@DATA_SEGMENTS@@
      │
      ▼
find remaining placeholders
      │
      ├── found
      │       ↓
      │   RuntimeError
      │
      └── none
              ↓
       create directory
              ↓
         write_text()
              ↓
        generated WAT
```

---

# 159. Relationship with `config.py`

`config.py` provides:

```text
WAT_TEMPLATE_PATH

OUT_WAT_PATH
```

These paths can be passed directly as:

```text
template_path

output_path
```

---

# 160. Relationship to `weights.py`

`weights.py` produces:

```text
weights_raw

bias_raw
```

The generator converts these blobs into:

```wat
(data ...)
```

---

# 161. Relationship with `quantization.py`

The previous module produces:

```text
mul_blob

shift_blob

q6_blob
```

which also become:

```wat
(data ...)
```

---

# 162. Relationship with `params_blob.py`

This module produces:

```text
params_blob
```

already containing:

```text
LayerParam[0]
LayerParam[1]
...
```

in binary form.

`wat_generator.py` simply places it at:

```text
PARAMS_BASE
```

---

# 163. Relationship with `memory.py`

`memory.py` determines:

```text
where each blob starts

how many pages are needed

where slots are located
```

The generator simply inserts these values.

---

# 164. Relationship to `layer_params.py`

`layer_params.py` is still used directly for:

```text
NUM_LAYERS

last output shape
```

---

# 165. Relationship with the template

The template contains:

```text
algorithms
kernels
functions
execution control
```

that do not directly depend on a particular model's values.

---

# 166. Python injects only what varies

For example:

```text
addresses

memory capacity

layer count

blobs

output
```

---

# 167. Central architectural separation

```text
model_template.wat
    ↓
STATIC LOGIC

wat_generator.py
    ↓
DYNAMIC MODEL DATA
```

---

# 168. Conceptual example

Template:

```wat
(module

  (memory
      (export "memory")
      @@MEM_PAGES@@
  )

  (global $PARAMS_BASE
      i32
      (i32.const @@PARAMS_BASE@@)
  )

  ...

  @@DATA_SEGMENTS@@
)
```

---

# 169. After generation

```wat
(module

  (memory
      (export "memory")
      17
  )

  (global $PARAMS_BASE
      i32
      (i32.const 499360)
  )

  ...

  (data
      (i32.const 2048)
      "\..."
  )

  ...
)
```

These values are illustrative only.

---

# 170. Why is this better than generating all WAT in Python?

One alternative would be:

```python
sections.append(
    "(func ..."
)
```

for every function, loop, and kernel.

That would mix:

```text
WASM algorithm

+

Python generation
```

---

# 171. With a template

Kernels remain written directly in:

```text
WAT
```

where they can be:

```text
read

edited

tested

optimized
```

as WebAssembly code.

---

# 172. Python handles only specialization

```text
generic template
      +
specific model
      ↓
specific module
```

---

# 173. Maintenance benefit

If we want to change:

```text
convolution implementation
```

we modify:

```text
model_template.wat
```

If we want to change:

```text
how weights are extracted
```

we modify:

```text
weights.py
```

If we want to change:

```text
memory layout
```

we modify:

```text
memory.py
```

This reduces coupling.

---

# 174. Debugging benefit

When an error occurs, we can distinguish:

```text
incorrect extraction?

incorrect layout?

incorrect params_blob?

incorrect template?

incorrect compilation?
```

instead of mixing everything in one monolithic generator.

---

# 175. Data segments as the initial memory image

A useful way to think about data segments is:

```text
before the first inference executes

WASM memory already contains:

WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
```

Slots are working regions instead.

---

# 176. Visualization

```text
module initialization
        │
        ▼

┌──────────────────────┐
│ initial region       │
├──────────────────────┤
│ WEIGHTS              │ ← data segment
├──────────────────────┤
│ BIAS                 │ ← data segment
├──────────────────────┤
│ MUL                  │ ← data segment
├──────────────────────┤
│ SHIFT                │ ← data segment
├──────────────────────┤
│ Q6                   │ ← data segment
├──────────────────────┤
│ PARAMS               │ ← data segment
├──────────────────────┤
│ SLOT0                │ ← runtime
├──────────────────────┤
│ SLOT1                │ ← runtime
├──────────────────────┤
│ SLOT2                │ ← runtime
└──────────────────────┘
```

---

# 177. Why do slots not become data segments?

They represent working memory.

They need no persistent model-specific parameters at initialization.

Their values are filled during:

```text
input

RGB conversion

inference
```

---

# 178. `RESULT_BASE` does not create a data segment either

It only indicates:

```text
where to look for the result
after execution
```

---

# 179. `RESULT_COUNT` is also metadata

It indicates:

```text
how many values to read
starting at RESULT_BASE
```

---

# 180. Classification example

```text
RESULT_BASE = 900464

RESULT_COUNT = 5
```

could mean:

```text
900464 → class 0 score

900465 → class 1 score

900466 → class 2 score

900467 → class 3 score

900468 → class 4 score
```

depending on output type.

---

# 181. Output type

The generator does not calculate:

```text
how many bytes each result occupies
```

It calculates:

```text
number of elements
```

Type interpretation remains determined by the model/runtime.

In the current model, quantized classification uses the representation expected by the kernels.

---

# 182. Assumption about the last layer

The generator assumes:

```text
network result
=
last LayerParam output
```

---

# 183. This suits the current pipeline

The execution sequence is linearized so the last operation represents the final result used by the host.

---

# 184. Possible future generalization

A model with:

```text
multiple independent outputs
```

might require:

```text
RESULT_BASE_0
RESULT_COUNT_0

RESULT_BASE_1
RESULT_COUNT_1
...
```

The current code supports only one final result selected by the last layer.

---

# 185. Another assumption: exactly three slots

The function checks this explicitly.

There is therefore no ambiguity:

```text
2 slots → error

3 slots → accepted

4 slots → error
```

for the current template.

---

# 186. This prevents silent inconsistency

Without this check, we could have:

```text
NUM_SLOTS = 4
```

while the template still knows only:

```text
SLOT0
SLOT1
SLOT2
```

The fourth slot would never be configured correctly.

---

# 187. Placeholders as the template interface

We can view the set:

```text
@@MEM_PAGES@@
@@PARAMS_BASE@@
@@LP_SIZE@@
@@NUM_LAYERS@@
...
```

as a kind of:

```text
textual API
```

between:

```text
Python
```

and:

```text
WAT template
```

---

# 188. If the interface changes

For example, if the template starts requiring:

```text
@@SLOT_BYTES@@
```

we must update:

```python
replacements
```

---

# 189. Automatic detection

If we forget:

```text
@@SLOT_BYTES@@
```

remains in the text and is caught by:

```text
PLACEHOLDER_PATTERN
```

---

# 190. This makes the template partly self-checking

It is not complete semantic validation, but prevents an important class of errors:

```text
model-dependent variable
left unfilled
```

---

# 191. A regex limitation

It only detects placeholders matching exactly:

```text
@@[A-Z0-9_]+@@
```

Thus, a typo such as:

```text
@@mem_pages@@
```

would not be recognized as a pending placeholder.

Later WAT compilation would probably reveal the problem, depending on where the text appears.

---

# 192. Possible future improvement

A stricter template policy could require:

```text
any sequence starting with @@
```

to be validated.

The current implementation uses a simple, explicit convention.

---

# 193. Another possible future validation

The generator could check:

```text
len(records)
==
len(layer_params)
```

before choosing:

```text
records[-1]
```

---

# 194. Another possible validation

It could check:

```text
params_serialization["layer_count"]
==
len(layer_params)
```

---

# 195. Another possible validation

Also:

```text
RESULT_BASE
+
output bytes
<=
MEM_END
```

could be checked.

Currently this is an expected consequence of prior planning.

---

# 196. Another possible validation

`build_data_segments()` could check:

```text
base + len(blob)
```

against the start of the next region.

This would detect overlap directly before generation.

In the current pipeline, this responsibility remains with:

```text
memory.py
```

and the consistency of preceding structures.

---

# 197. Another possible validation

After WAT is written, an external stage can call:

```text
wat2wasm
```

to confirm:

```text
valid syntax

valid typing

valid WASM structure
```

This remains outside the current function.

---

# 198. The generator does not modify blobs

Notice that:

```text
weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
params_blob
```

undergo no numeric transformation.

The only transformation is:

```text
binary bytes
      ↓
WAT hexadecimal escapes
```

---

# 199. Blob fidelity

If:

```text
weights_raw
```

contains:

```text
01 ff 80
```

WAT contains:

```text
\01\ff\80
```

and the data segment represents the same three bytes.

---

# 200. No recalculation

`wat_generator.py` should not:

```text
recalculate multipliers

reorder weights

recalculate offsets

change zero points

reinterpret LayerParam
```

This absence of model logic is desirable.

---

# 201. Weight path to WAT

```text
TFLite
   │
   ▼
weights.py
   │
   ▼
weights_raw
   │
   ▼
memory.py
   │
   └── WEIGHTS_BASE
          │
          ▼
wat_generator.py
          │
          ▼
(data
  (i32.const WEIGHTS_BASE)
  "...weights..."
)
```

---

# 202. Quantization path

```text
TFLite scales
      │
      ▼
quantization.py
      │
      ├── mul_blob
      ├── shift_blob
      └── q6_blob
              │
              ▼
          memory.py
              │
              ▼
        wat_generator.py
```

---

# 203. LayerParams path

```text
layer_params.py
      │
      ▼
params_blob.py
      │
      ▼
params_blob
      │
      ▼
PARAMS_BASE
      │
      ▼
wat_generator.py
      │
      ▼
PARAMS data segment
```

---

# 204. Memory path

```text
memory.py
    │
    ├── MEM_PAGES
    ├── WEIGHTS_BASE
    ├── BIAS_BASE
    ├── MUL_BASE
    ├── SHIFT_BASE
    ├── Q6_BASE
    ├── PARAMS_BASE
    └── SLOT_BASES
              │
              ▼
        wat_generator.py
```

---

# 205. Result path

```text
last LayerParam
      │
      ▼
out_ptr
      │
      ▼
RESULT_BASE


last LayerParam
      │
      ├── out_h
      ├── out_w
      └── cout
             │
             ▼
        RESULT_COUNT
```

---

# 206. Complete architectural view

```text
                        TFLite
                           │
                           ▼
                  ┌─────────────────┐
                  │    extractor    │
                  └─────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       BLOBS           LAYOUT          LAYER INFO
          │                │                │
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  wat_generator.py   │
                └─────────────────────┘
                           │
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
       replace numbers           insert blobs
               │                       │
               └───────────┬───────────┘
                           ▼
                  validate template
                           │
                           ▼
                    model.wat
                           │
                           ▼
                      wat2wasm
                           │
                           ▼
                     model.wasm
```

---

# 207. Template as code and blobs as data

This architecture clearly separates:

```text
model_template.wat
        ↓
code


weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
params_blob
        ↓
data
```

---

# 208. Template specialization

The generator converts:

```text
generic WAT
```

into:

```text
model-specific WAT
```

without rebuilding algorithms.

---

# 209. Comparison with the old extractor

A monolithic approach could have:

```text
Python
 │
 ├── calculate weights
 ├── calculate memory
 ├── calculate quantization
 ├── write WAT conv function
 ├── write WAT add function
 ├── write debug information
 ├── write data segments
 └── save file
```

The current architecture has:

```text
Python extractor
      ↓
structured data

WAT template
      ↓
static algorithms

wat_generator.py
      ↓
final combination
```

---

# 210. Research benefit

This separation also makes the artifact easier to explain.

The runtime can be described as:

```text
a fixed set of WAT kernels
```

while the model is represented by:

```text
data
+
LayerParams
```

injected during generation.

---

# 211. `params_blob` as the network description

Instead of generating a separate WAT function for each convolution:

```text
conv_layer_1()
conv_layer_2()
conv_layer_3()
...
```

the runtime can have a generic kernel:

```text
conv()
```

and receive different `LayerParams`.

---

# 212. The generator preserves this idea

It does not produce layer-specific code.

Specific parameters are already in:

```text
params_blob
```

as the `generate_wat()` docstring states (translated):

```text
Each layer's specific parameters
are already contained in params_blob
and are not inserted directly
into WAT functions.
```

---

# 213. This statement summarizes the architecture

```text
model
    ↓
data

runtime
    ↓
code
```

rather than:

```text
model
    ↓
generate hundreds of different functions
```

---

# 214. Expected invariants before the call

When `generate_wat()` executes, it expects:

```text
layer_params is not empty

params_serialization.records is not empty

slot_bases has exactly 3 elements

all layouts have been calculated

all blobs have been serialized

MEM_PAGES has been finalized
```

---

# 215. Invariants after the call

If the function returns normally:

```text
the WAT file has been written

no recognized placeholder remains

MEM_PAGES has been inserted

NUM_LAYERS has been inserted

bases have been inserted

result metadata has been inserted

data segments have been inserted
```

---

# 216. What the return value does not guarantee

On its own, it does not guarantee:

```text
WAT compiles

inference is correct

weights are correct

kernels are correct

pointers do not overlap

output matches TFLite
```

These guarantees belong to other validations and tests.

---

# 217. What the module deliberately does not do

`wat_generator.py` does not:

```text
load TFLite

iterate over operators

calculate slots

extract weights

compute quantization

calculate SAME padding

build LayerParams

serialize LayerParams

calculate MEM_END

compile WAT into WASM

execute inference
```

---

# 218. Exact responsibility

It only answers:

```text
given a WAT template
and all previously calculated artifacts,

how can we produce the final WAT
corresponding to this model?
```

---

# 219. Function summary

| Function | Responsibility |
| ----------------------- | ------------------------------------------------------------------ |
| `_as_bytes()` | Normalize binary representations into `bytes` |
| `wat_data_from_bytes()` | Convert bytes into an active WAT data segment |
| `build_data_segments()` | Build WEIGHTS, BIAS, MUL, SHIFT, Q6, and PARAMS segments |
| `generate_wat()` | Replace placeholders, insert segments, validate, and write WAT |

---

# 220. Data segment summary

```text
weights_raw
    +
WEIGHTS_BASE
    ↓
DATA WEIGHTS


bias_raw
    +
BIAS_BASE
    ↓
DATA BIAS


mul_blob
    +
MUL_BASE
    ↓
DATA MUL


shift_blob
    +
SHIFT_BASE
    ↓
DATA SHIFT


q6_blob
    +
Q6_BASE
    ↓
DATA Q6


params_blob
    +
PARAMS_BASE
    ↓
DATA PARAMS
```

---

# 221. Numeric value summary

```text
MEM_PAGES
    ← final_memory

PARAMS_BASE
    ← parameter_layout

LP_SIZE
    ← params_serialization

NUM_LAYERS
    ← layer_params

WEIGHTS_BASE
BIAS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE
    ← parameter_layout

SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
    ← layer_memory

RESULT_BASE
    ← last serialized LayerParam

RESULT_COUNT
    ← last layer shape
```

---

# 222. Summary

`wat_generator.py` represents the final stage of WebAssembly artifact construction.

All previous modules convert TFLite into independent structures:

```text
weights.py
    → weights and biases

quantization.py
    → MUL, SHIFT, and Q6

memory.py
    → addresses

layer_params.py
    → operation descriptions

params_blob.py
    → binary operation representation
```

`wat_generator.py` receives these prepared results and performs two fundamental operations.

The first replaces the template's numeric placeholders:

```text
@@MEM_PAGES@@

@@PARAMS_BASE@@

@@LP_SIZE@@

@@NUM_LAYERS@@

@@WEIGHTS_BASE@@

@@BIAS_BASE@@

@@MUL_BASE@@

@@SHIFT_BASE@@

@@Q6_BASE@@

@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@

@@RESULT_BASE@@

@@RESULT_COUNT@@
```

The second converts binary blobs:

```text
weights_raw

bias_raw

mul_blob

shift_blob

q6_blob

params_blob
```

into WAT data segments placed at their respective addresses.

Thus:

```text
static template
        +
model-specific data
        +
model-specific layout
        │
        ▼
complete WAT
```

Finally, the module checks for unresolved recognized placeholders and only then writes:

```text
generated/model.wat
```

This architecture preserves an important separation:

```text
EXTRACTION / CALCULATION
        ↓
Python

INFERENCE ALGORITHMS
        ↓
WAT template

FINAL GENERATION
        ↓
wat_generator.py
```

The generator does not need to “understand” the neural network again. When called, TFLite interpretation is complete. It simply converts the validated artifacts into a self-contained WAT module specific to that model.
