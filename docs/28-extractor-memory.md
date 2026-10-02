[English](28-extractor-memory.md) | [Português (Brasil)](28-extractor-memory.pt-BR.md)

# 28 — Physical memory planning

[Index](README.md) · Source: [extractor/memory.py](../extractor/memory.py)

## Separation of responsibilities

This module sizes slots, positions blobs, and calculates pages; it does not allocate Wasmtime memory or write WAT. It receives arrays/bytes and TFLite metadata. The code reserving LayerParams and positioning slots is in `calculate_layer_memory_layout`, in `layer_params.py`; both are needed to understand the final layout.

## Counting and alignment

`tensor_numel(shape,batch=1)` multiplies dimensions, replacing each negative dimension with batch. An empty shape produces a product of 1, although `calculate_slot_bytes` skips empty shapes. A zero dimension produces zero. This does not resolve dynamic-shape semantics; it is a local estimation policy.

`align_up(value,alignment=16)` implements `(value + alignment - 1) & ~(alignment - 1)`. It requires a positive power of two without validating it. Example: 414824 aligned to 16 becomes 414832, creating an eight-byte gap. Do not confuse memory padding with spatial convolution padding.

## calculate_slot_bytes

Visits all subgraph tensors, skipping constants, empty shapes, and types absent from `BYTES_PER_TYPE`. Calculates `num_elements × bytes_per_element`, recording ID, name, shape, type, bytes/element, elements, and bytes. Retains the first strict maximum found. Returns `max_bytes,slot_bytes,alignment,batch,max_tensor,tensor_records`, with `slot_bytes=align_up(max_bytes,alignment)`.

Sizing uses all recognized nonconstant tensors, not just those live at one stage. All three slots have equal capacity. It does not include extra workspace for external kernels, count constants toward this capacity, or implement different sizes per slot. The host RGB565 buffer is smaller than RGB888 and is still checked against the slot by the runner.

## calculate_parameter_layout

Receives a hint, alignment, and five data blobs: weights, bias, and three quantization arrays (PARAMS is reserved later). Sets WEIGHTS at `align_up(hint)`, aligned BIAS after weights, MUL after bias, SHIFT after MUL, Q6 after SHIFT, and PARAMS after Q6. Returns bases and lengths of the five regions preceding PARAMS, `params_base`, alignment, and hint. It does not receive the LayerParams size at this stage.

```text
low address
      ▼
┌────────────────────────────────┐
│ reserved [0,2048)              │ format at 0; busy flag at 4
├────────────────────────────────┤
│ WEIGHTS                        │ original weight bytes
├────────────────────────────────┤
│ BIAS                           │ operator bias
├────────────────────────────────┤
│ MUL                            │ int32 per channel
├────────────────────────────────┤
│ SHIFT                          │ int32 per channel
├────────────────────────────────┤
│ Q6                             │ quantized limits
├────────────────────────────────┤
│ PARAMS                         │ N×116 + final padding
├────────────────────────────────┤
│ SLOT0                          │ slot_bytes
├────────────────────────────────┤
│ SLOT1                          │ slot_bytes
├────────────────────────────────┤
│ SLOT2                          │ slot_bytes
└────────────────────────────────┘
      ▼ MEM_END (exclusive)
space to the end of the last page
      ▼
high address
```

Inputs are model-specific lengths. `memory.py` and `layer_params.py` calculate bases and padding; outputs are regions for the generator. The layout and 65536-byte page are runtime conventions. Box boundaries do not imply an absence of gaps: each base may include alignment between regions. Slots receive no data segments; WASM memory initializes them to zero, and execution overwrites them.

## Finalization

`mem_pages_for(end_addr)` calculates `ceil(end_addr/65536)` using integer division. `calculate_final_memory_layout` builds `regions` for WEIGHTS, BIAS, MUL, SHIFT, Q6, PARAMS (actual padded blob length), and all supplied slots. It adds `end=base+bytes`, takes the largest end as `mem_end`, and calculates pages, allocated bytes, and remaining space. It also returns slots and page size. There is no explicit test for region overlap or order, nor a maximum page limit.

Drowsiness example: PARAMS starts at 499360; 68×116=7888, already a multiple of 16. SLOT0 starts at 507248, followed by three 196608-byte areas. End 1097072; 17 pages reserve 1114112, leaving 17040 bytes. ImageNet: 67×116=7772, rounded to 7776; end 3606880 and 56 pages, leaving 63136 bytes.

## Formatting and failures

`slot_memory_to_text` lists tensors, the largest tensor, and alignment arithmetic for 07. `parameter_layout_to_text` prints bases and sizes for 08. `final_memory_layout_to_text` lists regions, ends, and a summary for 11. All return strings without writing files. Incomplete structural input causes KeyError; invalid numeric parameters may produce meaningless layouts without immediate errors. An absence of recognized types may produce a zero-byte slot; the function does not reject this case.

## Relationship to source and artifact

WASM file size is not `mem_pages×65536`: slots are reserved memory without embedded contents. WAT size also differs because blobs are textually escaped. The current layout is static per model; there is no tensor allocator during inference.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from extractor.tflite_utils import BYTES_PER_TYPE, TENSOR_TYPE_MAP, is_constant_tensor, tensor_shape_list
```

### `tensor_numel` — signature

```python
def tensor_numel(shape, batch=1)
```

### `align_up` — signature

```python
def align_up(value, alignment=16)
```

### `calculate_slot_bytes` — signature

```python
def calculate_slot_bytes(model, subgraph, *, batch, alignment)
```

### `calculate_parameter_layout` — signature

```python
def calculate_parameter_layout(
    *,
    kernel_base_hint,
    alignment,
    weights_raw,
    bias_raw,
    mul_blob,
    shift_blob,
    q6_blob,
)
```

### `slot_memory_to_text` — signature

```python
def slot_memory_to_text(memory_info)
```

### `parameter_layout_to_text` — signature

```python
def parameter_layout_to_text(layout)
```

### `mem_pages_for` — signature

```python
def mem_pages_for(end_addr)
```

### `calculate_final_memory_layout` — signature

```python
def calculate_final_memory_layout(*, parameter_layout, params_blob, slot_bases, slot_bytes)
```

### `final_memory_layout_to_text` — signature

```python
def final_memory_layout_to_text(memory_layout)
```

## Preserved technical material

The previous explanation is in [09-layout-memoria.md](historico/09-layout-memoria.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencias-e-limitacoes.md).
