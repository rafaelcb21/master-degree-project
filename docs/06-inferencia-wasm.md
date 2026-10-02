[English](06-inferencia-wasm.md) | [Português (Brasil)](06-inferencia-wasm.pt-BR.md)

# 06 — Wasmtime inference host

[Index](README.md) · Source: [inference/wasm_inference.py](../inference/wasm_inference.py)

## Responsibility and dependencies

This module bridges Python bytes and WebAssembly linear memory. It depends on pathlib, math, Wasmtime classes, layer_params format constants and tensor helpers. extractor/wasm_inference.py no longer exists. inference/ has no __init__.py; it is importable as a namespace package when running from the root.

## _instantiate_wasm(wasm_path)

Converts the path to Path, requires an existing file, reads bytes, creates Store(), compiles Module(store.engine, wasm_bytes), and resolves imports in declaration order. Only env.log, env.logf and env.log64 functions are accepted, with lambda *args: None callbacks. Other imports raise RuntimeError. Callbacks assume signatures compatible with returning None; arbitrary numeric return values are not implemented.

After creating Instance, it requires memory, run_mobilenetv2 and get_result_ptr exports. memory must be wasmtime.Memory; function signatures are not checked in advance. It returns store, instance, memory, run and get_result_ptr in a dictionary. Binary validation, instantiation and signature errors can originate in Wasmtime.

## tensor_info(tensor)

Accepts TFLite type 3 (UINT8) or 9 (INT8); other types raise ValueError. Scalar helpers provide scale and zero point. scale <= 0 is rejected, but isfinite is not checked. Returns shape, elements=math.prod(shape), scale, zero_point and dtype. Helper defaults mean absent quantization may appear as scale 1/zp 0; explicit tensor quantization is not established. Positive dimensions, channels and batch are not checked here; some checks belong to the pipeline.

## run_wasm_inference parameters

All parameters are keyword-only: wasm_path, adapter, cases, input_info, output_info, input_ptr and slot_bytes. cases must support iteration and len, as the pipeline's list does. One instance is created for all cases.

```text
synthetic_layer_count = 1              synthetic_layer_count = 0
input_info.elements // 3 * 2           input_info.elements
       RGB565 bytes                       RGB888/INT8 bytes
                └────────────┬─────────────┘
                   expected <= slot_bytes
                   input end <= memory size
```

Geometry and synthetic mode determine accepted byte length. Dimensions are model-specific; 2/3 bytes per pixel reflect currently supported formats. Integer division by 3 assumes the pipeline already validated three channels.

## Per-case cycle

```text
single instance
  TestCase → adapter.prepare_input → validate len(data)
           → memory.write(data, input_ptr)
           → if synthetic: memory[0] = 65
           → run_mobilenetv2(store), return value ignored
           → get_result_ptr(store)
           → validate [ptr, ptr+elements)
           → memory.read → bytes → adapter.evaluate_output
           → records.append, or errors.append(file, str(exc))
```

The runner writes prepared bytes, calls the runtime and reads 8-bit output. It returns adapter records or per-file errors. The extractor determines the slot address; exports use a shared protocol. Labels/ranking do not belong to this host.

Before processing, it checks expected <= slot_bytes, input_ptr >= 0 and input end within memory. Each case checks exact input size and output bounds. Slots are not cleared, exceptions do not trigger reinstantiation, and output need not lie in a specific slot region: linear-memory bounds are sufficient. The graph must overwrite values it reads on each run. Partially written memory after a kernel error can affect subsequent cases; cases are not isolated.

The per-case try catches Exception during reading, preparation, execution and evaluation. Instantiation happens before that block, so its failures stop the entire run. KeyboardInterrupt is not caught. Progress prints every 100 attempted cases, including failures. Returns records, errors and processed=len(records), not accuracy.

## Format and synchronization

Synthetic mode writes format byte 65 at address 0. A separate WAT flag at address 4 is used by is_ready_for_image and run_mobilenetv2; this synchronous host does not query it. Neither flag is a LayerParam dtype bit. No threads, image queue, timeout or fuel limit is configured.

## Generalization limits

Adapters are interchangeable, but the host still requires the run_mobilenetv2 export name, one byte per output element and an image protocol. It does not use get_top_class, get_top5 or get_result_count: ranking is Python-side and count comes from TFLite/generation. Results are not automatically compared against TensorFlow Lite.

