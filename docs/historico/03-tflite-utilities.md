[English](03-tflite-utilities.md) | [Português (Brasil)](03-utilitarios-tflite.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body is retained in translation.

# 03 — Utilities for reading TFLite (`tflite_utils.py`)

## 1. Module purpose

The `extractor/tflite_utils.py` file groups helper functions used by several modules when reading the TFLite structure.

Its main role is to turn information exposed by the TFLite binding into simpler, more predictable Python representations.

The current code is:

```python
import tflite
import numpy as np


TENSOR_TYPE_MAP = {
    0: ("float32", np.float32),
    1: ("float16", np.float16),
    2: ("int32", np.int32),
    3: ("uint8", np.uint8),
    4: ("int64", np.int64),
    6: ("bool", np.bool_),
    7: ("int16", np.int16),
    9: ("int8", np.int8),
}

BYTES_PER_TYPE = {
    0: 4,  # float32
    1: 2,  # float16
    2: 4,  # int32
    3: 1,  # uint8
    4: 8,  # int64
    6: 1,  # bool
    7: 2,  # int16
    9: 1,  # int8
}


def op_name(model, op):
    code = model.OperatorCodes(
        op.OpcodeIndex()
    ).BuiltinCode()

    for name, value in tflite.BuiltinOperator.__dict__.items():
        if isinstance(value, int) and value == code:
            return name

    return "CUSTOM"


def is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        tensor_id
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data = buffer.DataAsNumpy()
    except AttributeError:
        return False

    return (
        hasattr(data, "__len__")
        and len(data) > 0
    )


def safe_bytes_from_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        int(tensor_id)
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data_bytes = buffer.DataAsNumpy()
    except AttributeError:
        return None, None, None

    if (
        not hasattr(data_bytes, "__len__")
        or len(data_bytes) == 0
    ):
        return None, None, None

    shape = tensor.ShapeAsNumpy()
    dtype = int(tensor.Type())

    _, numpy_dtype = TENSOR_TYPE_MAP.get(
        dtype,
        (None, None),
    )

    if numpy_dtype is None:
        return None, None, None

    array = np.frombuffer(
        data_bytes.tobytes(),
        dtype=numpy_dtype,
    )

    try:
        array = array.reshape(shape)
    except Exception:
        pass

    raw = array.flatten().tobytes()

    return tensor, array, raw


def scale_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 1.0

    scales = quantization.ScaleAsNumpy()

    if scales is None or len(scales) == 0:
        return 1.0

    return float(
        np.array(
            scales,
            dtype=np.float64,
        ).flatten()[0]
    )


def zp_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 0

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if (
        zero_points is None
        or len(zero_points) == 0
    ):
        return 0

    return int(
        np.array(
            zero_points,
            dtype=np.int64,
        ).flatten()[0]
    )


def tensor_shape_list(tensor):
    shape = tensor.ShapeAsNumpy()

    if shape is None:
        return []

    return [
        int(value)
        for value in shape.tolist()
    ]


def qparams_np(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return None

    scales = (
        quantization.ScaleAsNumpy()
    )

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if scales is None:
        return None

    scales = np.atleast_1d(
        np.array(
            scales,
            dtype=np.float64,
        )
    )

    zero_points = np.atleast_1d(
        np.array(
            (
                zero_points
                if zero_points is not None
                else []
            ),
            dtype=np.int64,
        )
    )

    if scales.size == 0:
        return None

    return {
        "scales": scales,
        "zps": zero_points,
        "qdim": (
            quantization
            .QuantizedDimension()
        ),
    }
```

---

# 2. Architectural responsibility

This module does not execute a complete pipeline stage.

It acts as a support library.

Several modules need to perform repetitive operations such as:

```text
convert operator code to name
identify constant tensor
read tensor bytes
get shape
get scale
get zero point
get per-channel quantization parameters
```

Without this module, that logic would be duplicated in:

```text
graph.py
weights.py
quantization.py
memory.py
layer_params.py
```

The role of `tflite_utils.py` is to centralize these operations.

---

# 3. Position in the project

A simplified view is:

```text
                     Model + SubGraph
                           │
                           ▼
                  tflite_utils.py
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      graph.py         weights.py     quantization.py
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                    layer_params.py
```

It does not control the flow.

It provides reusable functions.

---

# 4. Importing the `tflite` module

```python
import tflite
```

This import is used mainly in:

```python
tflite.BuiltinOperator
```

The `BuiltinOperator` structure contains the numeric identifiers of operators known to the TFLite format.

For example, conceptually:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
```

Each name corresponds internally to an integer code.

The `op_name()` function uses this table to retrieve the textual name.

---

# 5. Importing NumPy

```python
import numpy as np
```

NumPy is used in this module for three main purposes:

```text
1. map TFLite types to NumPy types
2. reconstruct arrays from bytes
3. normalize quantization parameters
```

For example:

```python
np.int8
np.int32
np.float32
```

allow the bytes stored in model buffers to be interpreted correctly.

---

# 6. `TENSOR_TYPE_MAP`

The first key structure is:

```python
TENSOR_TYPE_MAP = {
    0: ("float32", np.float32),
    1: ("float16", np.float16),
    2: ("int32", np.int32),
    3: ("uint8", np.uint8),
    4: ("int64", np.int64),
    6: ("bool", np.bool_),
    7: ("int16", np.int16),
    9: ("int8", np.int8),
}
```

It relates:

```text
TFLite code
      ↓
readable name
      +
NumPy dtype
```

Example:

```python
9: ("int8", np.int8)
```

means:

```text
tensor.Type() == 9
        ↓
logical type = int8
        ↓
NumPy dtype = np.int8
```

---

# 7. Why do we need this map?

When the binding provides:

```python
tensor.Type()
```

the return value is an integer.

For example:

```text
9
```

On its own, this number does not directly tell the rest of the code:

```text
how many bytes each element occupies
how to interpret the bytes
how to reconstruct an ndarray
```

The map solves this.

Example:

```python
dtype = int(tensor.Type())

name, numpy_dtype = TENSOR_TYPE_MAP[dtype]
```

Result:

```text
name = "int8"
numpy_dtype = np.int8
```

---

# 8. Types used in the project

The current table covers:

| Code | Type | NumPy |
| -----: | --------- | ------------ |
|    `0` | `float32` | `np.float32` |
|    `1` | `float16` | `np.float16` |
|    `2` | `int32`   | `np.int32`   |
|    `3` | `uint8`   | `np.uint8`   |
|    `4` | `int64`   | `np.int64`   |
|    `6` | `bool`    | `np.bool_`   |
|    `7` | `int16`   | `np.int16`   |
|    `9` | `int8`    | `np.int8`    |

These are the types that the current extractor can convert directly into NumPy arrays.

A type outside this table is considered unsupported by `safe_bytes_from_tensor()`.

---

# 9. `BYTES_PER_TYPE`

The second table is:

```python
BYTES_PER_TYPE = {
    0: 4,
    1: 2,
    2: 4,
    3: 1,
    4: 8,
    6: 1,
    7: 2,
    9: 1,
}
```

This structure answers a different question:

```text
how many bytes does one element of this tensor occupy?
```

Example:

```text
int8
 ↓
1 byte
```

```text
int32
 ↓
4 bytes
```

```text
float32
 ↓
4 bytes
```

---

# 10. Why are there two maps?

In theory, we could keep a single structure with:

```text
name
NumPy dtype
bytes
```

But the current code separates two responsibilities.

`TENSOR_TYPE_MAP` is used to interpret contents:

```text
bytes → array
```

`BYTES_PER_TYPE`, in turn, is useful for memory planning:

```text
number of elements × bytes per element
```

For example:

```text
shape = [1, 128, 128, 3]

elements =
1 × 128 × 128 × 3
= 49152
```

For `int8`:

```text
49152 × 1
= 49152 bytes
```

For `float32`:

```text
49152 × 4
= 196608 bytes
```

---

# 11. The `op_name()` function

The function:

```python
def op_name(model, op):
```

turns an operator's internal identifier into its textual name.

Its flow is:

```text
Operator
   ↓
OpcodeIndex
   ↓
OperatorCodes
   ↓
BuiltinCode
   ↓
name
```

---

# 12. Getting the operation code

The first part is:

```python
code = model.OperatorCodes(
    op.OpcodeIndex()
).BuiltinCode()
```

We can break this down.

First:

```python
op.OpcodeIndex()
```

gets the index of the corresponding entry in the model's global operator table.

Then:

```python
model.OperatorCodes(...)
```

gets that entry.

Finally:

```python
.BuiltinCode()
```

gets the integer code identifying the operator.

---

# 13. Conceptual structure

Imagine:

```text
Operator
   │
   └── OpcodeIndex = 3
             │
             ▼
Model.OperatorCodes(3)
             │
             └── BuiltinCode = X
```

We now need to find which name corresponds to `X`.

---

# 14. Searching `BuiltinOperator`

The function iterates over:

```python
for name, value in (
    tflite.BuiltinOperator
    .__dict__
    .items()
):
```

This means it inspects the attributes defined inside:

```text
tflite.BuiltinOperator
```

When it finds:

```python
isinstance(value, int)
and value == code
```

it returns:

```python
return name
```

For example:

```text
code = code corresponding to CONV_2D
        ↓
"CONV_2D"
```

---

# 15. Why check `isinstance(value, int)`?

The internal dictionary of a class or module contains other attributes besides operator constants.

That is why:

```python
isinstance(
    value,
    int
)
```

filters only integer values.

Without this, the function could compare the code against attributes that do not represent operators.

---

# 16. Returning `"CUSTOM"`

If no known operator is found:

```python
return "CUSTOM"
```

This acts as a fallback.

In other words:

```text
known BuiltinCode
       ↓
corresponding name

BuiltinCode not found
       ↓
"CUSTOM"
```

The return value does not necessarily mean every unknown operator is correctly implemented as a custom operator.

It only indicates that it could not be associated with a known name in the table being searched.

---

# 17. Subsequent use of `op_name()`

Other modules can call:

```python
optype = op_name(
    model,
    op
)
```

and obtain:

```text
"CONV_2D"
"DEPTHWISE_CONV_2D"
"FULLY_CONNECTED"
"ADD"
"MEAN"
"SOFTMAX"
"QUANTIZE"
```

This allows readable code such as:

```python
if optype == "CONV_2D":
```

instead of comparing numbers directly.

---

# 18. The `is_constant_tensor()` function

The function:

```python
def is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
```

determines whether a given tensor has data stored in a model buffer.

The current criterion is:

```text
does the buffer have contents?
     │
     ├── yes → constant tensor
     └── no → nonconstant tensor
```

---

# 19. Locating the tensor

First:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

The received identifier is an index into the subgraph's tensor table.

---

# 20. Locating the buffer

Then:

```python
buffer = model.Buffers(
    tensor.Buffer()
)
```

Each tensor references a buffer.

Conceptual structure:

```text
Tensor
  │
  └── Buffer ID
          │
          ▼
    Model.Buffers(ID)
          │
          ▼
        Buffer
```

---

# 21. Attempting to read

The function tries:

```python
data = buffer.DataAsNumpy()
```

If the binding does not expose this method:

```python
except AttributeError:
    return False
```

The function then considers that it was unable to confirm the presence of constant contents.

---

# 22. Criterion for a constant tensor

The final return value is:

```python
return (
    hasattr(data, "__len__")
    and len(data) > 0
)
```

Thus, for the current extractor:

```text
empty buffer
    ↓
nonconstant

buffer containing bytes
    ↓
constant
```

---

# 23. Example with convolution weights

A dynamic network input may have:

```text
Tensor input
   │
   └── empty buffer
```

Thus:

```python
is_constant_tensor(...)
```

returns:

```text
False
```

Weights, however:

```text
Tensor weights
   │
   └── buffer containing thousands of bytes
```

return:

```text
True
```

---

# 24. Importance for the graph

This distinction matters because weights should not be treated as temporary tensors produced by another layer.

For example:

```text
           input activation
                  │
                  ▼
             CONV_2D
                  ▲
                  │
               weights
```

The input tensor is a data flow in the graph.

The weight tensor is constant.

This affects:

```text
dependencies
slot allocation
tensor→slot mapping
```

---

# 25. The `safe_bytes_from_tensor()` function

This function has a broader responsibility:

```text
constant tensor
     ↓
locate bytes
     ↓
determine dtype
     ↓
convert to NumPy
     ↓
apply shape
     ↓
produce normalized bytes
```

It returns three values:

```python
tensor, array, raw
```

---

# 26. Function inputs

```python
def safe_bytes_from_tensor(
    model,
    subgraph,
    tensor_id,
):
```

Receives:

```text
Model
SubGraph
tensor_id
```

It locates both the tensor and its buffer itself.

---

# 27. Normalizing `tensor_id`

The code uses:

```python
int(tensor_id)
```

before accessing:

```python
subgraph.Tensors(...)
```

This is useful because some indices supplied by NumPy arrays may be types such as:

```text
np.int32
np.int64
```

Conversion guarantees a normal Python `int`.

---

# 28. Reading the buffer

The process is:

```python
tensor = subgraph.Tensors(
    int(tensor_id)
)

buffer = model.Buffers(
    tensor.Buffer()
)
```

Then:

```python
data_bytes = buffer.DataAsNumpy()
```

If the method is unavailable:

```python
return None, None, None
```

---

# 29. Empty buffer

The function also checks:

```python
if (
    not hasattr(
        data_bytes,
        "__len__"
    )
    or len(data_bytes) == 0
):
    return None, None, None
```

This prevents attempts to interpret a tensor that has no constant data.

---

# 30. Reading the shape

Next:

```python
shape = tensor.ShapeAsNumpy()
```

Example:

```text
[32, 3, 3, 3]
```

for a hypothetical set of convolution weights.

---

# 31. Reading the type

Then:

```python
dtype = int(
    tensor.Type()
)
```

Suppose:

```text
dtype = 9
```

From the map:

```python
TENSOR_TYPE_MAP[9]
```

we have:

```text
("int8", np.int8)
```

---

# 32. Resolving the NumPy dtype

The code:

```python
_, numpy_dtype = (
    TENSOR_TYPE_MAP.get(
        dtype,
        (None, None),
    )
)
```

ignores the textual name and retrieves only the NumPy dtype.

For `int8`:

```text
numpy_dtype = np.int8
```

---

# 33. Unsupported type

If:

```python
numpy_dtype is None
```

the function returns:

```python
None, None, None
```

Thus, it does not attempt to interpret bytes of a type for which there is no known mapping.

This avoids assigning an incorrect meaning to the binary contents.

---

# 34. `np.frombuffer()`

The main transformation is:

```python
array = np.frombuffer(
    data_bytes.tobytes(),
    dtype=numpy_dtype,
)
```

This function interprets the same bytes according to the correct type.

A simple example.

Suppose four bytes:

```text
01 FF 02 FE
```

interpreted as `int8`:

```text
[1, -1, 2, -2]
```

The bytes are unchanged.

What changes is their interpretation.

---

# 35. Why is the dtype essential?

The same bytes can mean different values depending on the type.

Simplified example:

```text
byte FF
```

As `uint8`:

```text
255
```

As `int8`:

```text
-1
```

Therefore:

```python
dtype=numpy_dtype
```

is fundamental to preserving the model's values.

---

# 36. Initially linear array

`np.frombuffer()` initially produces a linear sequence.

For example:

```text
[1, 2, 3, 4, 5, 6]
```

Even if the original tensor has shape:

```text
[2, 3]
```

That is why the next stage attempts to restore the original shape.

---

# 37. `reshape(shape)`

The code:

```python
try:
    array = array.reshape(
        shape
    )
except Exception:
    pass
```

attempts to reconstruct the tensor's original dimensions.

Example:

```text
linear array:
[1, 2, 3, 4, 5, 6]

shape:
[2, 3]

result:
[
  [1, 2, 3],
  [4, 5, 6]
]
```

---

# 38. Why is there a `try/except` around reshape?

If the element count is incompatible with the supplied shape, `reshape()` raises an exception.

The current code chooses not to stop extraction at this point.

It keeps the linear array.

Therefore:

```text
reshape succeeded
    ↓
array with original shape

reshape failed
    ↓
array remains linear
```

---

# 39. Important caveat about `reshape`

This behavior was preserved from the original implementation, but deserves documentation.

The snippet:

```python
except Exception:
    pass
```

hides the reason for failure.

In a future version focused on strict validation, it may be better to turn an incompatibility between:

```text
buffer
and
shape
```

into an explicit error.

For now, the current decision favors compatibility with the existing extractor.

---

# 40. Generating `raw`

Then:

```python
raw = (
    array
    .flatten()
    .tobytes()
)
```

This creates a linear version in bytes.

Flow:

```text
original buffer
     ↓
NumPy array
     ↓
reshape
     ↓
flatten
     ↓
bytes
```

---

# 41. Why call `flatten()`?

Even if the array has several dimensions:

```text
[O, H, W, I]
```

WASM linear memory will be a sequential block of bytes.

That is why:

```python
array.flatten()
```

removes the dimensional structure before serialization.

Example:

```text
[
 [1, 2],
 [3, 4]
]
```

becomes:

```text
[1, 2, 3, 4]
```

and then:

```text
bytes
```

---

# 42. Return value of `safe_bytes_from_tensor()`

The return value is:

```python
return tensor, array, raw
```

Each element has a different purpose.

### `tensor`

Retains access to TFLite metadata:

```text
shape
type
quantization
buffer ID
```

### `array`

Provides values already interpreted by NumPy.

It is useful for:

```text
inspection
transformations
calculations
validation
```

### `raw`

Provides linear bytes.

It is useful for:

```text
serialization
weights blob
bias blob
WAT data segments
```

---

# 43. Complete example

Consider a tensor:

```text
shape = [2, 2]
dtype = int8
```

and bytes:

```text
01 02 FF FE
```

The process would be:

```text
bytes
01 02 FF FE
      │
      ▼
np.frombuffer(..., int8)
      │
      ▼
[1, 2, -1, -2]
      │
      ▼
reshape([2,2])
      │
      ▼
[
 [ 1,  2],
 [-1, -2]
]
      │
      ▼
flatten()
      │
      ▼
[1, 2, -1, -2]
      │
      ▼
tobytes()
```

The values retain their appropriate binary representation.

---

# 44. The `scale_scalar()` function

The function:

```python
def scale_scalar(tensor):
```

gets a single quantization scale associated with the tensor.

Its purpose is to simplify cases where quantization is per-tensor.

---

# 45. Getting the quantization structure

First:

```python
quantization = (
    tensor.Quantization()
)
```

This structure contains information such as:

```text
Scale
ZeroPoint
QuantizedDimension
```

---

# 46. Tensor without quantization

If:

```python
quantization is None
```

the function returns:

```python
1.0
```

This value acts as a neutral scale.

In other words:

```text
x × 1.0 = x
```

---

# 47. Tensor without `Scale`

Then:

```python
scales = (
    quantization
    .ScaleAsNumpy()
)
```

If:

```text
scales == None
```

or:

```text
len(scales) == 0
```

the function also returns:

```python
1.0
```

---

# 48. Conversion to `float64`

The normal return value is:

```python
return float(
    np.array(
        scales,
        dtype=np.float64,
    ).flatten()[0]
)
```

The operation performs:

```text
scales
   ↓
np.array(... float64)
   ↓
flatten()
   ↓
first element
   ↓
Python float
```

---

# 49. Why take only `[0]`?

Because this function explicitly represents:

```text
scalar scale
```

It is appropriate for per-tensor quantization.

Example:

```text
Scale = [0.0039215689]
```

result:

```text
0.0039215689
```

---

# 50. Per-tensor quantization

In per-tensor quantization, there is a single pair:

```text
scale
zero_point
```

for the entire tensor.

The conceptual conversion is:

```text
real_value =
scale × (quantized_value - zero_point)
```

Example:

```text
scale = 0.1
zero_point = -128
q = -118
```

Then:

```text
real =
0.1 × (-118 - (-128))

= 0.1 × 10

= 1.0
```

---

# 51. The `zp_scalar()` function

The function:

```python
def zp_scalar(tensor):
```

is equivalent to `scale_scalar()`, but returns the zero point.

---

# 52. Tensor without quantization

If:

```python
quantization is None
```

the return value is:

```python
0
```

Zero acts as a neutral offset.

---

# 53. Tensor without a zero point

The function reads:

```python
zero_points = (
    quantization
    .ZeroPointAsNumpy()
)
```

If there is no value:

```python
return 0
```

---

# 54. Conversion to integer

The return value is:

```python
return int(
    np.array(
        zero_points,
        dtype=np.int64,
    ).flatten()[0]
)
```

As with scale:

```text
array
  ↓
flatten
  ↓
first element
```

But the final type is:

```text
int
```

---

# 55. `scale_scalar()` and `zp_scalar()` together

The two helpers allow:

```python
scale = scale_scalar(
    tensor
)

zp = zp_scalar(
    tensor
)
```

producing:

```text
(scale, zero_point)
```

Example:

```text
scale = 0.0039215689
zp = -128
```

---

# 56. Use in special operations

These values are used later in operations such as:

```text
QUANTIZE
ADD
MEAN
SOFTMAX
```

and also for:

```text
zx
zw
zy
```

in `LayerParams`.

For example:

```text
zx = input zero point
zw = weight zero point
zy = output zero point
```

---

# 57. Deliberate limitation of scalar helpers

`scale_scalar()` and `zp_scalar()` always take:

```text
first element
```

That is why they do not replace a complete read of per-channel quantization.

If a tensor has:

```text
32 scales
```

these helpers would return only:

```text
scales[0]
```

For that case there is:

```python
qparams_np()
```

---

# 58. The `tensor_shape_list()` function

The function:

```python
def tensor_shape_list(tensor):
```

normalizes the shape into a Python list.

It receives:

```text
TFLite Tensor
```

and returns something like:

```python
[1, 128, 128, 3]
```

---

# 59. Shape from the binding

First:

```python
shape = (
    tensor.ShapeAsNumpy()
)
```

The result is normally a NumPy ndarray.

Example:

```text
array([1, 128, 128, 3])
```

---

# 60. Tensor without a shape

If:

```python
shape is None
```

the function returns:

```python
[]
```

Thus, consumer modules can always work with a list.

---

# 61. Conversion to a Python list

The normal return value is:

```python
return [
    int(value)
    for value
    in shape.tolist()
]
```

The transformation is:

```text
NumPy array
    ↓
.tolist()
    ↓
list
    ↓
int(value)
    ↓
list of Python ints
```

---

# 62. Why convert each value to `int`?

Without this conversion, elements may remain NumPy types such as:

```text
np.int32
np.int64
```

By producing:

```python
int(value)
```

the rest of the project receives common Python types.

This simplifies:

```text
serialization
comparisons
reports
struct.pack
```

---

# 63. Example

Input:

```text
tensor.ShapeAsNumpy()

→ np.array([1, 128, 128, 3])
```

Output:

```python
[1, 128, 128, 3]
```

---

# 64. The `qparams_np()` function

The function:

```python
def qparams_np(tensor):
```

performs a complete read of the quantization parameters.

Unlike:

```text
scale_scalar()
zp_scalar()
```

it preserves entire vectors of scales and zero points.

---

# 65. Why is this function necessary?

Quantized weights can use per-channel quantization.

In that case, instead of:

```text
1 scale
```

we can have:

```text
one scale for each output channel
```

Example:

```text
32 filters
     ↓
32 scales
```

In this scenario, taking only:

```text
scales[0]
```

would be insufficient.

---

# 66. Getting the quantization structure

First:

```python
quantization = (
    tensor.Quantization()
)
```

If it does not exist:

```python
return None
```

---

# 67. Reading `scales`

Then:

```python
scales = (
    quantization
    .ScaleAsNumpy()
)
```

If:

```python
scales is None
```

the return value is also:

```python
None
```

The function considers that no usable quantization information exists.

---

# 68. Reading `zero_points`

It also performs:

```python
zero_points = (
    quantization
    .ZeroPointAsNumpy()
)
```

There is a difference here.

If zero points are absent, the function does not return immediately.

It later creates an empty array.

---

# 69. Normalizing `scales`

The code:

```python
scales = np.atleast_1d(
    np.array(
        scales,
        dtype=np.float64,
    )
)
```

ensures that:

```text
scalar scale
```

and:

```text
vector of scales
```

always have a representation with at least one dimension.

---

# 70. What does `np.atleast_1d()` do?

Example:

```python
np.array(0.5)
```

has shape:

```text
()
```

Then:

```python
np.atleast_1d(...)
```

becomes:

```text
[0.5]
```

This lets the rest of the code handle a single scale and multiple scales uniformly.

---

# 71. Normalizing `zero_points`

The same is done with:

```python
zero_points = np.atleast_1d(
    np.array(
        (
            zero_points
            if zero_points is not None
            else []
        ),
        dtype=np.int64,
    )
)
```

Thus:

```text
zero_points present
       ↓
int64 array
```

or:

```text
zero_points absent
       ↓
[]
```

---

# 72. Final scale check

Then:

```python
if scales.size == 0:
    return None
```

Without a scale, quantization is not considered valid for subsequent calculations.

---

# 73. Return value of `qparams_np()`

The function returns:

```python
{
    "scales": scales,
    "zps": zero_points,
    "qdim": (
        quantization
        .QuantizedDimension()
    ),
}
```

In other words:

```text
scales
zero points
quantized dimension
```

---

# 74. `QuantizedDimension`

The field:

```python
quantization.QuantizedDimension()
```

indicates which tensor dimension is associated with per-channel quantization.

This value matters because a vector of scales must be interpreted relative to a specific dimension.

Conceptual example:

```text
weights shape:
[32, 3, 3, 3]

scales:
[32 values]

qdim:
0
```

This indicates that the 32 scales correspond to dimension:

```text
shape[0]
```

which has 32 elements.

---

# 75. Per-tensor versus per-channel quantization

We can represent the two cases as follows.

## Per-tensor

```text
Entire tensor
    │
    ├── scale = 0.05
    └── zp = -3
```

A single set of parameters applies to the entire tensor.

---

## Per-channel

```text
Tensor
│
├── channel 0 → scale[0]
├── channel 1 → scale[1]
├── channel 2 → scale[2]
├── ...
└── channel N → scale[N]
```

That is why:

```python
qparams_np()
```

preserves the entire vector.

---

# 76. Example of `qparams_np()`

Suppose:

```text
scales =
[
  0.0012,
  0.0015,
  0.0011,
  0.0017
]

zero_points =
[
  0,
  0,
  0,
  0
]

qdim = 0
```

The return value is conceptually:

```python
{
    "scales": np.array([
        0.0012,
        0.0015,
        0.0011,
        0.0017,
    ]),
    "zps": np.array([
        0,
        0,
        0,
        0,
    ]),
    "qdim": 0,
}
```

These contents will be used later to calculate per-channel requantization multipliers.

---

# 77. Relationship between `qparams_np()` and requantization

In a quantized layer, we conceptually have:

```text
input scale = Sx
weight scale = Sw
output scale = Sy
```

For each channel, a factor proportional to the following may be needed:

```text
Sx × Sw
───────
   Sy
```

If `Sw` has a different value per channel:

```text
Sw[0]
Sw[1]
Sw[2]
...
```

the multiplier will also differ for each channel.

This is one reason why complete quantization information needs to be preserved.

---

# 78. Difference between scalar and vector helpers

We can summarize:

```text
scale_scalar()
    ↓
a single scale

zp_scalar()
    ↓
a single zero point

qparams_np()
    ↓
all scales
all zero points
quantized dimension
```

Therefore:

```text
scale_scalar / zp_scalar
```

are convenient for per-tensor quantization,

while:

```text
qparams_np
```

is appropriate for calculations that need to preserve per-channel quantization.

---

# 79. Relationship with `weights.py`

`weights.py` uses functions from this module to:

```text
locate constant tensors
interpret buffers
get dtype
get bytes
```

Simplified flow:

```text
Weight tensor
      │
      ▼
safe_bytes_from_tensor()
      │
      ├── tensor
      ├── ndarray
      └── raw bytes
               │
               ▼
          weights_raw
```

---

# 80. Relationship with `quantization.py`

`quantization.py` mainly needs:

```text
scale_scalar
zp_scalar
qparams_np
```

Flow:

```text
Tensor
   │
   ▼
qparams_np()
   │
   ├── scales
   ├── zero points
   └── quantized dimension
           │
           ▼
calculate multiplier / shift / Q6
```

---

# 81. Relationship with `graph.py`

`graph.py` needs to distinguish:

```text
constant tensor
```

from:

```text
tensor dynamically produced by an operator
```

For this, it can use:

```python
is_constant_tensor(...)
```

This prevents weights and biases from being interpreted as normal edges between graph operators.

---

# 82. Relationship with `layer_params.py`

`layer_params.py` directly uses helpers such as:

```text
op_name
scale_scalar
zp_scalar
tensor_shape_list
```

For example:

```text
TFLite Tensor
      ↓
tensor_shape_list()
      ↓
[1, H, W, C]
      ↓
in_h
in_w
cin
```

and:

```text
Quantized tensor
      ↓
scale_scalar()
zp_scalar()
      ↓
zx / zy
```

---

# 83. Why is `tensor_hwc()` not here?

A key detail of the current architecture is that:

```python
tensor_hwc()
```

was kept in:

```text
layer_params.py
```

rather than:

```text
tflite_utils.py
```

The reason is semantic.

`tensor_shape_list()` only answers:

```text
what is the shape?
```

For example:

```text
[1, 128, 128, 3]
```

`tensor_hwc()`, however, interprets this shape according to the convention expected by the `LayerParams` implementation:

```text
shape[1] → height
shape[2] → width
shape[3] → channels
```

In other words:

```text
tflite_utils.py
        ↓
generic representation

layer_params.py
        ↓
application-specific interpretation
```

This separation is intentional.

---

# 84. The module as a normalization layer

We can understand this file as a normalization layer.

The TFLite binding provides:

```text
enumeration integers
ndarrays
FlatBuffer objects
optional arrays
specific methods
```

The rest of the extractor prefers to receive:

```text
operator names
Python ints
Python floats
Python lists
normalized NumPy arrays
bytes
```

Therefore:

```text
TFLite binding
      │
      ▼
tflite_utils.py
      │
      ▼
more convenient representation
      │
      ▼
rest of the extractor
```

---

# 85. Current policy for missing values

The module uses default values in some cases.

### Missing scale

```python
1.0
```

### Missing zero point

```python
0
```

### Missing shape

```python
[]
```

### Missing buffer

```python
None, None, None
```

### Missing quantization

```python
None
```

These decisions prevent every consumer module from having to repeat the same checks.

---

# 86. Meaning of neutral values

The defaults:

```text
scale = 1.0
zero point = 0
```

are mathematically neutral in the expression:

```text
real =
scale × (q - zero_point)
```

Substituting:

```text
real =
1 × (q - 0)

= q
```

This explains why these values are convenient when there is no quantization information.

---

# 87. Caveat about default values

Although mathematically neutral, these values can also hide an unexpected absence of metadata.

For example, if a quantized operation should have a scale but the model does not provide one:

```text
scale_scalar()
        ↓
1.0
```

the pipeline can continue.

In a stricter future version, certain calls could distinguish:

```text
a genuinely nonquantized tensor
```

from:

```text
a tensor that should be quantized but has incomplete metadata
```

In the current extractor, behavior was kept simple and compatible with the model used.

---

# 88. Return policy of `safe_bytes_from_tensor()`

The function returns three `None` values simultaneously in cases of failure or absence:

```python
return None, None, None
```

This lets the caller write:

```python
tensor, array, raw = (
    safe_bytes_from_tensor(...)
)

if raw is None:
    ...
```

The alternative would be to raise an exception in every case.

The current implementation prefers:

```text
expected absence
      ↓
None

critical structural error
      ↓
handled at later stages
```

---

# 89. Serialization and endianness

`safe_bytes_from_tensor()` does not reorder bytes manually.

It uses:

```python
np.frombuffer(...)
```

followed by:

```python
.tobytes()
```

The goal is to preserve the logical data sequence according to the interpreted dtype.

Later, specific structures such as `LayerParam` are explicitly serialized using little-endian format:

```text
<i
```

but that belongs to the serialization module, not this utility.

---

# 90. Difference between a weight buffer and `params_blob`

It is useful to distinguish two types of bytes used by the project.

## Bytes coming directly from TFLite

Produced by:

```python
safe_bytes_from_tensor()
```

Example:

```text
weights_raw
bias_raw
```

They represent model data.

## Bytes constructed by the extractor

Produced later by:

```text
quantization.py
params_blob.py
```

Example:

```text
mul_blob
shift_blob
q6_blob
params_blob
```

These did not exist in this form in TFLite.

They were calculated or reorganized by the pipeline.

---

# 91. Complete flow of a constant tensor

A weight follows approximately this path:

```text
TFLite Tensor
      │
      ├── Type()
      ├── ShapeAsNumpy()
      └── Buffer()
             │
             ▼
        TFLite Buffer
             │
             ▼
        DataAsNumpy()
             │
             ▼
safe_bytes_from_tensor()
             │
             ├── ndarray
             │
             └── raw bytes
                     │
                     ▼
               weights.py
                     │
                     ▼
               weights_raw
                     │
                     ▼
             wat_generator.py
                     │
                     ▼
             WASM data segment
```

---

# 92. Quantization information flow

For a quantized tensor:

```text
Tensor
  │
  └── Quantization()
         │
         ├── ScaleAsNumpy()
         ├── ZeroPointAsNumpy()
         └── QuantizedDimension()
                │
                ▼
          tflite_utils.py
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
scale_scalar()       qparams_np()
zp_scalar()              │
        │                │
        ▼                ▼
special operations    per-channel
```

---

# 93. What this module should not do

This file should not contain logic specific to:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
```

It should also not calculate:

```text
multipliers
shifts
Q6
padding
slots
memory addresses
LayerParams
```

These responsibilities belong to specialized modules.

---

# 94. Why does this matter?

Imagine putting inside:

```python
safe_bytes_from_tensor()
```

a specific rule for reorganizing `DEPTHWISE_CONV_2D` weights.

This would make a generic function start to know operator semantics.

The current architecture avoids this.

The division is:

```text
tflite_utils.py
    ↓
"how to read TFLite"

weights.py
    ↓
"how to organize weights"

quantization.py
    ↓
"how to calculate quantized parameters"

layer_params.py
    ↓
"how to represent each operation in the runtime"
```

---

# 95. A central but low-level dependency

`tflite_utils.py` is a low-level module.

It knows:

```text
TFLite binding
NumPy
```

but should not know:

```text
WAT
slots
memory layout
WASM execution
```

This reduces coupling.

---

# 96. Benefit for a future API/backend

When the extractor is used as a backend, this module will probably need few changes.

Its input will still be:

```text
Model + SubGraph
```

regardless of whether the file came from:

```text
command line
web upload
API
Angular interface
```

Thus, the utility remains reusable.

---

# 97. Function summary

| Function | Responsibility |
| -------------------------- | ---------------------------------------------------- |
| `op_name()` | Convert an internal operator code to a textual name |
| `is_constant_tensor()` | Check whether a tensor has a constant buffer |
| `safe_bytes_from_tensor()` | Read and interpret bytes of a constant tensor |
| `scale_scalar()` | Get the first quantization scale |
| `zp_scalar()` | Get the first zero point |
| `tensor_shape_list()` | Convert the shape to a list of `int` |
| `qparams_np()` | Get complete quantization parameters |

---

# 98. Constant summary

| Constant | Responsibility |
| ----------------- | ------------------------------------------ |
| `TENSOR_TYPE_MAP` | Relate TFLite type, name, and NumPy dtype |
| `BYTES_PER_TYPE` | Report the size of each element in bytes |

---

# 99. Conceptual summary

The module can be summarized as:

```text
            TFLite binding
                  │
                  ▼
        ┌───────────────────┐
        │ tflite_utils.py   │
        └───────────────────┘
                  │
        ┌─────────┼───────────┐
        │         │           │
        ▼         ▼           ▼
   operators    tensors   quantization
        │         │           │
        ▼         ▼           ▼
     names      arrays      scales
                bytes       zero points
                shapes      qdim
        │         │           │
        └─────────┼───────────┘
                  ▼
          higher-level modules
```

The central responsibility is:

```text
transform low-level structures
from the TFLite binding

into simple, consistent information
for the rest of the extractor
```

---

# 100. Role in the complete project

Up to this point, the architecture can be visualized as follows:

```text
┌─────────────────────────────┐
│          config.py          │
│                             │
│ paths                       │
│ policies                    │
│ alignment                   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      model_loader.py        │
│                             │
│ file → Model                │
│ Model → SubGraph            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      tflite_utils.py        │
│                             │
│ normalizes types            │
│ reads buffers               │
│ reads shapes                │
│ reads quantization          │
│ resolves op names           │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ engineering modules         │
│                             │
│ graph                       │
│ weights                     │
│ quantization                │
│ memory                      │
│ layer_params                │
└─────────────────────────────┘
```

`model_loader.py` makes the TFLite file navigable.

`tflite_utils.py` makes that navigable structure **convenient to use**.

This distinction matters:

```text
model_loader
    ↓
opens the structure

tflite_utils
    ↓
translates and normalizes the structure

other modules
    ↓
apply the extractor's specific logic
```

That is why, despite being a utility module, it occupies a central position in the pipeline's architecture.
