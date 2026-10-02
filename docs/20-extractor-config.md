[English](20-extractor-config.md) | [Português (Brasil)](20-extractor-config.pt-BR.md)

# 20 — Shared extractor constants

[Index](README.md) · Source: [extractor/config.py](../extractor/config.py)

## Responsibility and position in the pipeline

The module contains only `BATCH=1`, `ALIGN=16`, and `KERNEL_BASE_HINT=2048`. It takes no parameters, has no functions, and writes no files. `ModelPipeline` imports these constants and passes them explicitly to memory calculations. This file no longer contains model, template, or report paths.

| Constant | Consumer | Actual effect |
|---|---|---|
| BATCH | `calculate_slot_bytes` → `tensor_numel` | Replaces negative dimensions with 1 when counting; does not implement image batching |
| ALIGN | Blob, slot, and parameter layout | Aligns bases/sizes to multiples of 16 |
| KERNEL_BASE_HINT | `calculate_parameter_layout` | Starts the WEIGHTS region at `align_up(2048,16)` |

```text
config.py                         model.toml
   │ shared constants                │ per-package choices
   └────────────────┬────────────────┘
                    ▼
               ModelPipeline
                    │
                    ├── memory: ALIGN / weight base / BATCH
                    └── slots: num_slots from manifest
```

Constants and package configuration enter the pipeline, which forwards each value to the responsible module. Layout decisions are the output. These constants apply to the current runtime in general; the slot count is read from the model but validated as 3. Changing BATCH does not bypass the batch-1 input validation in `ModelPipeline`.

## Invariants and pitfalls

`align_up` in `memory.py` uses a bit mask, requiring positive, power-of-two alignment for the formula to work as intended. The configuration module does not validate this condition. The space below 2048 reserves the flags used by the template, but has no independent allocator. Reducing this base can overlap control areas. Although the constant is called HINT, the code does not search for another address: it simply aligns it.

## Documentation migration

Older descriptions of `MODEL_PATH`, `WAT_TEMPLATE_PATH`, `OUT_WAT_PATH`, `REPORTS_DIR`, and `NUM_SLOTS` as globals describe the previous architecture. Paths now come from `ModelPackage`, `ModelConfig`, and `model.toml`. This module does not depend on `Path`, TOML, or the package.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python

```

## Preserved technical material

The previous explanation is in [01-configuration.md](historico/01-configuration.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
