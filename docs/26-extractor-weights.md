[English](26-extractor-weights.md) | [Português (Brasil)](26-extractor-weights.pt-BR.md)

# 26 — Extracting weights and bias

[Index](README.md) · Source: [extractor/weights.py](../extractor/weights.py)

## Responsibility

`extract_weights_and_bias(model,subgraph)` identifies constants for operations in `WEIGHT_OPERATORS`: CONV_2D, DEPTHWISE_CONV_2D, and FULLY_CONNECTED. It is called after the logical map and before quantization. It does not dequantize, transpose kernels, or fold batch normalization. It preserves the byte order extracted by the helper.

## Algorithm and structures

It visits operators in TFLite order and filters negative IDs. With at least two inputs, the second is treated as a weight. `safe_bytes_from_tensor` returns tensor/array/raw; if an array exists and the ID has not already been extracted, it records the current offset, appends raw bytes, and adds metadata. If there is a third input, it is a bias candidate; it is extracted only when the array exists, is one-dimensional, and has not already been recorded. Shared IDs are deduplicated separately in the weight and bias maps.

Returns six fields: `weights_raw` and `bias_raw` as bytes; `weight_tensor_off` and `bias_tensor_off` as ID→offset dicts; and `weight_records` and `bias_records` with op_index, op_type, tensor_id, offset, nbytes, shape, and dtype. The offset is relative to the start of its respective blob, not to the TFLite file or WASM memory.

```text
op inputs: [activation, weight, optional bias]
                          │       │
                          ▼       ▼
                 safe_bytes_from_tensor
                          │       │
                    dedup by tensor_id
                          │       │
                          ▼       ▼
                  weights_raw   bias_raw
                          │       │
                  relative offset per tensor
                          └───┬───┘
                              ▼
                   memory → LayerParams → blob
```

Inputs are model constants. The extractor concatenates them and records their locations. Outputs are bytes and offsets, consumed by the physical layout and layer builders. Weights and shapes are model-specific; shared storage rules require the WAT to interpret the preserved TFLite layout.

## Layouts expected by the runtime

CONV indexes weights as `[cout,kh,kw,cin]`; depthwise as `[1,kh,kw,cout]`; FC uses a `[cout,cin]` matrix. The module does not validate all these dimensions before copying. Bias must be int32 for kernels using `i32.load`, but this extractor does not restrict bias dtype; it only checks dimensionality. Declared operator support also depends on builders and kernels.

## Failures and permissive behavior

An unreadable tensor, absent buffer, or unknown dtype may be skipped by the helper without an exception. Too few inputs also cause a skip. Later builders use defaults for missing offsets; this may hide absent required data. Individual tensors in this blob are not aligned; `memory.py` aligns region bases. Typical sizes keep int32 bias offsets aligned, but alignment is not checked per record.

`weights_bias_to_text` lists weight and bias records followed by tensor counts and total bytes. It receives the extraction dict and returns a string for 05. It does not include complete weight values or reconstruct arrays. Use offsets and lengths to locate the corresponding data-segment range.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from extractor.tflite_utils import op_name, safe_bytes_from_tensor
```

### `extract_weights_and_bias` — signature

```python
def extract_weights_and_bias(model, subgraph)
```

### `weights_bias_to_text` — signature

```python
def weights_bias_to_text(extraction)
```

## Preserved technical material

The previous explanation is in [07-weight-bias-extraction.md](historico/07-weight-bias-extraction.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
