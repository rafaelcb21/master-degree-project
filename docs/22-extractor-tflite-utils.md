[English](22-extractor-tflite-utils.md) | [Português (Brasil)](22-extractor-tflite-utils.pt-BR.md)

# 22 — TFLite tensor and quantization utilities

[Index](README.md) · Source: [extractor/tflite_utils.py](../extractor/tflite_utils.py)

## Responsibility and structures

This module normalizes repeated schema queries. It is used by graph, weights, quantization, memory, LayerParams, and `tensor_info`. It does not choose directories or classes. `TENSOR_TYPE_MAP` maps TFLite codes to names/NumPy dtypes; `BYTES_PER_TYPE` specifies storage size. A dtype's presence in this table does not mean kernels can execute it.

| Code | Name | Bytes |
|---:|---|---:|
| 0 | float32 | 4 |
| 1 | float16 | 2 |
| 2 | int32 | 4 |
| 3 | uint8 | 1 |
| 4 | int64 | 8 |
| 6 | bool | 1 |
| 7 | int16 | 2 |
| 9 | int8 | 1 |

## Functions, decisions, and return values

`op_name(model,op)` queries `OperatorCodes(op.OpcodeIndex()).BuiltinCode()` and looks up the value in `tflite.BuiltinOperator.__dict__`. It returns the matching name or `CUSTOM`. It does not interpret `CustomCode` or operator versioning; two operators with the same builtin but different versions have the same name here.

`is_constant_tensor(model,subgraph,tensor_id)` treats a tensor as constant when its buffer's `DataAsNumpy()` has length greater than zero. It catches only `AttributeError` from this access and returns False. It does not inspect the variable attribute or analyze writes by operators; allocation and mapping use this definition based on the presence of bytes.

`safe_bytes_from_tensor` obtains the tensor/buffer and returns `(tensor,array,raw)`. Missing data, an empty buffer, or an unknown dtype produces `(None,None,None)`. It converts with `np.frombuffer`, attempts to reshape to the TFLite shape, and ignores any reshape exception, retaining the original vector. Finally, it flattens and returns bytes. Thus, “safe” does not mean complete size/shape validation; invalid schema calls and `frombuffer` may still fail.

`scale_scalar(tensor)` returns the first scale as a float; without quantization/scales, it returns 1. `zp_scalar` returns the first zero point as an int, or 0. These defaults handle some missing values but may conceal insufficient data. They neither compute averages nor choose values per channel.

`tensor_shape_list` converts `ShapeAsNumpy()` to a list of ints, or `[]` if it is None. It does not resolve shape signatures, validate dimensions, or materialize the batch dimension.

`qparams_np` returns `{scales: float64 array, zps: int64 array, qdim}` with arrays of at least one dimension. Without quantization/scales, it returns None. It preserves multiple scales for the per-channel extractor. The binding may represent absent arrays in different ways; the helpers assume the forms explicitly handled in the code.

```text
tensor_id
   │
   ├──► Tensors(id) ──► Type / Shape / Quantization
   │                        │             │
   │                        ▼             ├── scalar: first value
   │                   dtype/shape        └── qparams_np: arrays
   ▼
Buffers(tensor.Buffer())
   │ nonempty data?
   ├── no ──► not constant / no extractable bytes
   └── yes ─► NumPy → attempted reshape → raw
```

Inputs are model IDs or objects. The helpers extract simple representations; outputs are names, arrays, scalars, and bytes. Shapes/scales are model-specific; dtype conventions are shared. Consumers must distinguish None from valid data, since absence does not always raise an exception.

## Endianness and limitations

The basic NumPy dtypes in the map are native. Buffer bytes come from TFLite; on a little-endian host such as the observed environment, multibyte types match the expected storage. The module does not explicitly normalize all buffers to little-endian. In contrast, MUL/SHIFT/Q6 and LayerParam blobs use explicit little-endian formats in their modules. Do not assume portability to big-endian hosts without checking this difference.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
import tflite
import numpy as np
```

### `op_name` — signature

```python
def op_name(model, op)
```

### `is_constant_tensor` — signature

```python
def is_constant_tensor(model, subgraph, tensor_id)
```

### `safe_bytes_from_tensor` — signature

```python
def safe_bytes_from_tensor(model, subgraph, tensor_id)
```

### `scale_scalar` — signature

```python
def scale_scalar(tensor)
```

### `zp_scalar` — signature

```python
def zp_scalar(tensor)
```

### `tensor_shape_list` — signature

```python
def tensor_shape_list(tensor)
```

### `qparams_np` — signature

```python
def qparams_np(tensor)
```

## Preserved technical material

The previous explanation is in [03-tflite-utilities.md](historico/03-tflite-utilities.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
