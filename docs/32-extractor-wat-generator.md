[English](32-extractor-wat-generator.md) | [Português (Brasil)](32-extractor-wat-generator.pt-BR.md)

# 32 — WAT materialization and data segments

[Index](README.md) · Source: [extractor/wat_generator.py](../extractor/wat_generator.py)

## Purpose and inputs

Receives template_path/output_path and layout, LayerParams, serialization, weight, and quantization results. Does not compile. Kernel implementation remains in the template; the generator only replaces constants and inserts data. It does not structurally parse WAT.

## Byte conversion

`_as_bytes` accepts bytes, bytearray, memoryview, or an object with a tobytes method. Returns bytes in the first three cases and the result of tobytes in the last; it does not validate that the method actually returned bytes. Other types raise TypeError.

`wat_data_from_bytes(data,base)` returns an empty string for an empty blob. For each byte it generates a two-digit hexadecimal `\xx` escape and returns `(data (i32.const BASE) "...")`. Example: bytes 0,65,255 at base 2048 become `(data (i32.const 2048) "\00\41\ff")`. It does not interpret the blob's internal numbers.

```text
weights_raw ──────┐
bias_raw ─────────┤
mul_blob ─────────┤
shift_blob ───────┤
q6_blob ──────────┤
params_blob ──────┘
                 │ + bases from parameter_layout
                 ▼
          build_data_segments()
                 │
                 ▼
  (data (i32.const BASE) "\xx\xx...")
                 │ instantiation
                 ▼
       initialized WASM memory
```

Inputs are six blobs and their bases. The generator escapes every byte and omits empty segments; outputs are active data segments applied on instantiation. Data and addresses are model-specific; segment syntax is shared. Slots have no segments of their own and are initially zeroed by WebAssembly memory.

`build_data_segments` preserves WEIGHTS, BIAS, MUL, SHIFT, Q6, PARAMS order, indents, and separates segments with blank lines. Explicit addresses, not textual order, determine memory positions.

## generate_wat

Reads UTF-8; rejects an empty LayerParams list or serialization records. Takes the last layer and last record as output: result_base=out_ptr and result_count=out_h×out_w×cout. Requires exactly three slot bases. Replaces strings with `str.replace`, converts numbers via int→str, appends data segments, and searches for tokens still matching `@@[A-Z0-9_]+@@`. Remaining tokens cause RuntimeError. Creates the directory and writes UTF-8 to the destination.

```text
WAT template with placeholders
                 │
                 ▼
            generate_wat ◄─────────────┐
                 ▲                    │
                 │                    │
 parameter_layout / layer_memory / final_memory
                 │                    │
         params_serialization + blobs + last layer
                 │
                 ▼
      replacements + data segments
                 │ validate remaining tokens
                 ▼
        generated/model.wat
                 ▼ independent stage
       compiler → model.wasm
```

Inputs are the template and extractor structures; outputs are text and metadata. Template code is specific to the implementation chosen by the package; placeholders and ABI are shared conventions. The generator does not turn an incompatible implementation into a correct runtime.

## All supplied placeholders

| Token (between `@@`) | Source |
|---|---|
| MEM_PAGES | final_memory.mem_pages |
| PARAMS_BASE | parameter_layout.params_base |
| LP_SIZE | params_serialization.layer_param_size |
| NUM_LAYERS | len(layer_params) |
| WEIGHTS_BASE, BIAS_BASE | kernel_base, bias_base |
| MUL_BASE, SHIFT_BASE, Q6_BASE | respective bases |
| SLOT0_BASE, SLOT1_BASE, SLOT2_BASE | three slot bases |
| RESULT_BASE | out_ptr of the last record |
| RESULT_COUNT | spatial/channel product of the last layer |
| DATA_SEGMENTS | string containing the six nonempty blocks |

Returns output_path, mem_pages, num_layers, result_base, result_count, wat_bytes. The last value is measured in the file, not in linear memory.

## Limitations and invariants

The token check only finds the uppercase and digits/underscore pattern. It does not check that every expected placeholder was present; a template with a hardcoded address may pass. It does not prove data-segment bounds or matching exports. Using the last layer as output assumes a compatible graph/order; the pipeline compares only element counts, after compilation. Invalid UTF-8 and disk failures propagate. Writing overwrites the destination without a transaction; template and output must be distinct by configuration.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from pathlib import Path
import re
```

### `_as_bytes` — signature

```python
def _as_bytes(value)
```

### `wat_data_from_bytes` — signature

```python
def wat_data_from_bytes(data, base)
```

### `build_data_segments` — signature

```python
def build_data_segments(*, parameter_layout, weights_bias, quantization, params_serialization)
```

### `generate_wat` — signature

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
)
```

## Preserved technical material

The previous explanation is in [13-wat-generation.md](historico/13-wat-generation.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
