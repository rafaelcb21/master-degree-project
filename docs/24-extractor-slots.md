[English](24-extractor-slots.md) | [Português (Brasil)](24-extractor-slots.pt-BR.md)

# 24 — Slot allocation and lifetimes

[Index](README.md) · Source: [extractor/slots.py](../extractor/slots.py)

## Purpose and contract

`allocate_slots(layers,num_slots)` receives the graph's list of dicts in topological order and returns `(allocation,layer_output_slot)`. The first contains `layer,type,input_slots,output_slot,in_place`; the second maps layer names to logical slots. There are no addresses or bytes here. The pipeline supplies three slots, but the standalone function does not validate that `num_slots` is positive.

## State and exact algorithm

`layer_output_slot` remembers where each layer's output was stored. `slot_readers_count` counts consumers still pending per slot. `next_slot` starts at 1 and defines a rotation preference; this does not mean alternation alone is sufficient to preserve residuals.

For each normal layer: without predecessors, it uses input `[0]` and resets the preference to 1; with predecessors, it looks up their output slots. It builds all indices `[0,num_slots)`, excluding slots with a positive count. If none remain, it raises `RuntimeError("Sem slots livres em ...")`. It chooses `next_slot` if free, otherwise the smallest free index. Only then does it decrement input reader counts and remove entries that reach zero. It records the number of output consumers when `below` is nonempty, appends the record, and advances the circular preference.

Selection happens **before** releasing inputs consumed by the current operation. Therefore, the function may require an extra slot even when more aggressive planning could overwrite an input. It does not individually check whether the kernel supports overlap.

```text
Layer A → SLOT1 ───────────────────────────┐
             │                            │ residual shortcut
             ▼                            │
Layer B → SLOT2                            │
             │                            │
             └──────────┬─────────────────┘
                        ▼
                       ADD
                        ▼
                      SLOT0

occupied slot
     │
     ▼
are there still pending consumers?
     │
  ┌──┴───────────┐
  ▼              ▼
 yes             no
  │              │
retain       becomes a candidate again
```

The input is the A→B→ADD dependency with A also consumed by ADD. The allocator retains SLOT1 until the shortcut is read and chooses SLOT0 for the output. Outputs are reusable slots, not tensor copies. The residual pattern depends on the graph; reader counting and area selection are generic. The example illustrates the algorithm and is not a transcription of a particular layer in the models.

## QUANTIZE exception

For QUANTIZE, the function takes SLOT0 if there is no predecessor, otherwise the first predecessor's slot. It sets the same output slot, marks `in_place=True`, and executes `continue`. This branch **does not update** `slot_readers_count`, decrement reads, or advance `next_slot`. It works in the observed input/output paths, but is not a general liveness algorithm for QUANTIZE in the middle of branches. Do not treat this simplification as an optimization formally proven safe for every graph.

## Formatting, errors, and invariants

`slot_allocation_to_text` receives the list, prints type and label with `[inputs -> output]`, uses ` e ` for multiple inputs, and appends `(in-place)` where indicated. It returns a string without modifying allocation. Missing predecessor IDs cause `KeyError`; no available slot causes `RuntimeError`; there is no spill to a fourth area or automatic reallocation.

A slot is an area with uniform capacity calculated later from the largest tensor, not a graph variable with fixed dimensions. The same slot may contain different shapes at different times. Counting operator consumers assumes the graph adequately represents value lifetimes. Without that assumption, a complete tensor→slot map can still be numerically incorrect.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python

```

### `allocate_slots` — signature

```python
def allocate_slots(layers, num_slots)
```

### `slot_allocation_to_text` — signature

```python
def slot_allocation_to_text(allocation)
```

## Preserved technical material

The previous explanation is in [05-alocacao-slots.md](historico/05-alocacao-slots.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencias-e-limitacoes.md).
