[English](25-extractor-tensor-mapping.md) | [Português (Brasil)](25-extractor-tensor-mapping.pt-BR.md)

# 25 — Mapping tensors to slots

[Index](README.md) · Source: [extractor/tensor_mapping.py](../extractor/tensor_mapping.py)

## Input, output, and consumers

The module matches TFLite IDs to graph labels and logical allocation. `build_tensor_slot_mapping` returns `tensor_to_slot`, `graph_inputs`, `mapped_from_layers`, `graph_input_mappings`, `pending_before_resolution`, and `unmapped_after`. The pipeline validates and reports this map; the `graph_inputs` set contributes to the shifted runtime map, but the latter is rebuilt in `layer_params.py`, not simply mutated from the validated map.

## Construction in three passes

First, it visits each allocation record, obtains `op_idx` from `label_to_op_idx`, and associates all nonnegative outputs with `output_slot`. Next, it visits still-unmapped tensors, ignores constants, and assigns slot 0 to declared subgraph inputs; the others become pending. In the third pass, it attempts to resolve each remaining nonconstant through its producer chain. Finally, it lists those still missing, without raising an error in this method itself.

`resolve_slot_from_producer` uses `visiting` to prevent cycles; it returns None if it revisits a tensor or there is no producer. If the tensor is already mapped, it returns the slot. If its producer has a label and an allocated output, it stores that slot. Otherwise, it recursively follows the producer's nonnegative, nonconstant inputs, copying the visited set per branch; the first slot found propagates to the output tensor. The function modifies `tensor_to_slot` as a cache.

```text
allocation: L7 → SLOT2
          │
          ▼
label_to_op_idx[L7] → original operator
          │
          ▼
outputs: tensor 42, tensor 43
          │
          ├──► tensor_to_slot[42] = 2
          └──► tensor_to_slot[43] = 2

pending tensor → producer without label → nonconstant input
                                              │
                                              ▼
                                     recursively resolve slot
```

Inputs are allocation records and tensor connections. The module associates IDs with storage and attempts to fill gaps. The output is the logical map. IDs/labels are model data; the resolution policy is shared. Mapping multiple outputs to one slot and propagating the first input are assumptions, not implementations of transformation kernels.

## Validation

`validate_tensor_slot_mapping` visits only operators present in `old_idx_to_label`. For inputs, it ignores negative IDs and constants, requiring all others to be mapped. For outputs, it ignores only negative IDs and requires their presence in the map. Failures raise `RuntimeError` with `[MAP-ERROR]`, direction, op_index, tensor_id, and operation name. It returns True on success.

It does not validate slot index bounds, physical capacity, collisions between two live inputs, or whether the resulting pointers are correct. Later stages handle some of this; completing the dictionary does not prove liveness.

## Report

`tensor_mapping_to_text` lists mappings from layers, inputs, initial pending tensors, and a resolution summary. It does not necessarily print every recursive resolution individually; the total count reflects the final dictionary. Report 04 describes logical slots before the synthetic shift. To check the addresses actually used, compare 09 and 10.

## Pitfalls

Ignoring an operator in the graph and inheriting its input slot is semantically valid only when the transformation can actually be treated as an alias in that layout. The code does not prove this condition. `runtime_mapping` does not reuse this recursive search; models relying on aliases resolved only here may fail or diverge later. Current manifests have no configuration for ignoring operators.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from extractor.tflite_utils import is_constant_tensor, op_name
```

### `resolve_slot_from_producer` — signature

```python
def resolve_slot_from_producer(
    tensor_id,
    *,
    model,
    subgraph,
    tensor_to_slot,
    producer_by_tensor,
    old_idx_to_label,
    layer_output_slot,
    visiting=None,
)
```

### `build_tensor_slot_mapping` — signature

```python
def build_tensor_slot_mapping(
    model,
    subgraph,
    *,
    slot_allocation,
    layer_output_slot,
    label_to_op_idx,
    old_idx_to_label,
    producer_by_tensor,
)
```

### `validate_tensor_slot_mapping` — signature

```python
def validate_tensor_slot_mapping(model, subgraph, *, tensor_to_slot, old_idx_to_label)
```

### `tensor_mapping_to_text` — signature

```python
def tensor_mapping_to_text(mapping)
```

## Preserved technical material

The previous explanation is in [06-tensor-slot-mapping.md](historico/06-tensor-slot-mapping.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
