[English](30-extractor-layer-params.md) | [Português (Brasil)](30-extractor-layer-params.pt-BR.md)

# 30 — Building LayerParams and the synthetic layer

[Index](README.md) · Source: [extractor/layer_params.py](../extractor/layer_params.py)

## Responsibility and input data

This module bridges TFLite semantics and the ABI. It receives the model/subgraph, runtime slot maps, physical bases, weight/bias offsets, and quantization map per operator. It produces a list of dicts; it does not yet write the 116 bytes. Constants define OP_CONV=1 through OP_RGB565_TO_RGB888=8, flags, and LP_FMT/LP_SIZE. The serialized field table is in the [contract](08-contrato-layerparam-v1.md).

## Shape, mapping, and memory helpers

`tensor_hwc` returns `(shape,height,width,channels)`: H=shape[1] and W=shape[2] for rank≥3; for rank 2 it uses H=W=1,C=shape[1]; rank≥4 uses C=shape[3]. It is not a universal layout normalizer and does not validate rank. Rank 3 falls through to C=1.

`build_runtime_tensor_mapping` maps inputs to `slot_shift`; for each allocated output it uses `(original_slot+slot_shift)%num_slots`. Returns `tensor_to_slot,records,slot_shift`. It neither performs the recursive resolution from `tensor_mapping.py` nor validates collisions; it uses the original allocation's outputs.

`calculate_layer_memory_layout` calculates `num_layers=real+synthetic`, `params_bytes=ceil(num_layers*layer_param_size/alignment)*alignment`, `slot0=align(params_base+params_bytes)`, and subsequent bases by adding slot_bytes and aligning. Returns num_layers, params_bytes, slot_bases. The function has an initial slot even if num_slots were zero, but the pipeline allows only 3.

## Synthetic layer: a transformation absent from TFLite

`build_rgb565_layer` uses the subgraph's first input and creates a dict with op_index −1, optype RGB565_TO_RGB888, flags=0 (marker address), kh=65 (sentinel), input_slot 0, and output_slot 1. It creates no weights/bias and uses the image dimensions. The text label is not an original L0 layer. The runtime reads a little-endian uint16 and expands R5/G6/B5 by replicating the high bits.

```text
RAW RGB565                           RAW BGR888
    │                                    │
    ▼                                    ▼
  SLOT0                         ImageNet adapter: BGR→RGB
    │                                    │
    ▼                                    ▼
┌──────────────────────┐               SLOT0
│ RGB565_TO_RGB888     │                 │
│ synthetic operation 8│                 │
└──────────┬───────────┘                 │
           ▼                            │
         SLOT1                          │
           ▼                            ▼
 first real operation             first real operation
 count=1 / shift=1                 count=0 / shift=0
```

Inputs are bytes prepared according to the package. With a synthetic layer, Python adds a kernel and shifts slots; without it, the adapter prepares RGB directly. The result represents the logical TFLite input. Dimensions are model-specific; OP8 and the format protocol belong to the runtime. The host always writes to SLOT0, regardless of slot_shift.

## build_layer_params: Python dispatcher

Starts an empty list, optionally appending RGB565. An unknown synthetic value causes ValueError. Visits operators in original order, skipping those absent from `old_idx_to_label`, types outside the seven supported types, and operators without valid outputs. Requires a runtime map for the first output; calls the appropriate builder and appends the dict. Returns a list. It does not use `graph.order` to order these records and does not raise an error for every unsupported operator.

## Individual builders

### _build_quantize_params

Requires at least one input and a known slot. Reads shapes, first input/output scale/zp, rejects zero scale_out, and quantizes scale_in/scale_out into kh/kw. Bit 0 marks INT8 input; unknown input receives UINT8 flags and the metadata name `unknown(code)`, without immediate rejection. Bit 1 marks UINT8 output; output other than INT8/UINT8 is rejected. Forces out_slot=in_slot, even if another value was passed. Records pad_t=input_ptr, zx/zy, input_dtype, and quant_params. The QUANTIZE kernel uses cout×out_h×out_w as length.

### _build_add_params

Requires two inputs and both slots. Reads geometry from the first input and output, scales/zps A,B,Y; calculates three multiplier/shift pairs with `compute_add_quantization_params`. Stores them in kh/kw, stride_h/w, dil_h/w. Uses pad_t/pad_b for pointers A/B and pad_l/pad_r for zero points A/B. Reads fused activation and records it in act. Returns input_slots with two positions, input_ptrs, and detailed quant_params. It does not check equal shapes or implement broadcasting; WAT iterates over the first input's length and reads both at the same index.

### _build_mean_params

Requires input and mapping; rejects zero scale_y. Quantizes sX/sY, records spatial_size=H×W and the input pointer. Fixes ACT_NONE, without reading the axis tensor or ReducerOptions. The runtime's effective behavior is a per-channel spatial mean, with truncated integer division before requantization. It is not arbitrary MEAN over any axis.

### _build_softmax_params

Requires input and mapping. Fixes beta=1, integer_bits=5, diff_min=−128; calculates internal_scale=1/32, input_left_shift, and the beta*sX multiplier. Stores values in special fields and metadata; if op_idx is in mul_q6_off, enables MUL/SHIFT pointers. The current kernel ignores these multipliers in favor of a fixed constant; see chapter 13. The builder does not read beta from the FlatBuffer.

### _build_weighted_params

Handles CONV_2D, DEPTHWISE_CONV_2D, and FULLY_CONNECTED; requires two inputs and the activation slot. Obtains geometry from weight shape: CONV cout=dim0, kh=dim1, kw=dim2; depthwise cout=dim3; FC cout=dim0, kernel 1×1. Reads stride/dilation/padding/activation options; marks SAME and RELU6 and recalculates padding/out_h/out_w for SAME. Reads scalar zps and offsets per tensor and operator. Absent weights use offset 0; absent bias and quantization disable their pointers. `depth_mult` remains in the dict but is not one of the 29 fields, and the current kernel indexes input by output channel, assuming multiplier 1. FC does not explicitly flatten H×W×C in the builder.

## Common structure and metadata

Dicts include identity (`op_index`, `optype`, `op_type`, and label for real operations), slots, geometry, offsets and has_bias/has_mulq6 booleans, zero points, depth_mult, input_slots, and input_ptrs. Special builders add `quant_params` for reporting. None of these auxiliary fields increases LP_SIZE: the serializer selects exactly 29 values.

## layer_params_to_text

Receives the list and required keyword-only arguments lp_size, memory_layout, and runtime_mapping. Emits record size, layer count, bases, runtime shift, a special-field legend, and all values per layer. Includes quantization parameters, shift convention, and the current QUANTIZE flag table 0–3. It does not recalculate kernels or serialize; the report may contain fields WAT does not read.

## Invariants and risks

Builder inputs/outputs must be in the runtime map; ADD needs two coherent pointers. Reservation size uses the graph's layer count, whereas the actual list may be shorter due to skips. The generator uses actual list length for NUM_LAYERS; it does not automatically reject a graph that has lost an operation. `real_layer_count` and the identity of the last output deserve auditing for new models. Contract validation in configuration does not detect these semantic differences.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
import math
import struct
from extractor.tflite_utils import op_name, scale_scalar, zp_scalar, tensor_shape_list
from extractor.quantization import quantize_multiplier, compute_add_quantization_params
from extractor.operator_options import ACT_NONE, ACT_RELU6, parse_add_options, parse_conv2d_options, parse_dwconv2d_options, parse_fc_options, same_padding
```

### `tensor_hwc` — signature

```python
def tensor_hwc(tensor)
```

### `build_runtime_tensor_mapping` — signature

```python
def build_runtime_tensor_mapping(
    subgraph,
    *,
    graph_inputs,
    slot_allocation,
    label_to_op_idx,
    num_slots,
    slot_shift,
)
```

### `calculate_layer_memory_layout` — signature

```python
def calculate_layer_memory_layout(
    *,
    real_layer_count,
    synthetic_layer_count,
    layer_param_size,
    params_base,
    slot_bytes,
    num_slots,
    alignment,
)
```

### `build_rgb565_layer` — signature

```python
def build_rgb565_layer(subgraph, *, slot_bases)
```

### `_build_quantize_params` — signature

```python
def _build_quantize_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_add_params` — signature

```python
def _build_add_params(
    subgraph,
    *,
    op_idx,
    op,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_mean_params` — signature

```python
def _build_mean_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_softmax_params` — signature

```python
def _build_softmax_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    mul_q6_off,
)
```

### `_build_weighted_params` — signature

```python
def _build_weighted_params(
    subgraph,
    *,
    op_idx,
    op,
    op_type_name,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
)
```

### `build_layer_params` — signature

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
    synthetic_layer='rgb565_to_rgb888',
)
```

### `layer_params_to_text` — signature

```python
def layer_params_to_text(layer_params, *, lp_size, memory_layout, runtime_mapping)
```

## Preserved technical material

The previous explanation is in [11-layer-params.md](historico/11-layer-params.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencias-e-limitacoes.md).
