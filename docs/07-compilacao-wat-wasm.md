[English](07-compilacao-wat-wasm.md) | [Português (Brasil)](07-compilacao-wat-wasm.pt-BR.md)

# 07 — WAT → WASM compilation

[Index](README.md) · Source: [pipeline/wasm_compiler.py](../pipeline/wasm_compiler.py)

## Interface and algorithm

compile_wat_to_wasm(wat_path, wasm_path) converts both arguments to Path and requires the source to be a file. It reads UTF-8, calls wasmtime.wat2wasm(wat_source), converts the result to bytes and checks the `b"\x00asm"` prefix. It creates the destination's parent directory and writes the binary. Returns {output_path: Path, wasm_bytes: int}.

```text
WAT template + extracted data → generate_wat
 → generated/model.wat (UTF-8)
 → read_text → wasmtime.wat2wasm → bytes
 → prefix 00 61 73 6d?
 → generated/model.wasm
 → Module + Instance in the runner
```

The compiler receives already-materialized text and the package-selected destination. It converts syntax and writes bytes. Model structure/parameters vary; the WASM format and conversion are shared. wat2wasm is a Python API, not an external executable or WABT command.

## Errors and guarantees

A missing source raises FileNotFoundError; invalid UTF-8, parser errors and write-permission failures propagate. An unexpected prefix raises RuntimeError. Magic-number checking does not prove layerparam-v1 compatibility, mathematical correctness or required exports. Execution validation/compilation occurs when the runner creates Module.

There are no optimization flags, target selection, clang invocation, TFLite library linking or AOT generation. The destination is overwritten directly, without atomic writing. Returned size is binary-file size, not linear memory or original TFLite size. WAT is generally larger because blob bytes are encoded as hexadecimal escapes.

The pipeline always generates WAT before compiling and compiles before inference. There is no CLI mode to compile only when a source changes. Compilation itself neither executes images nor produces metrics.

