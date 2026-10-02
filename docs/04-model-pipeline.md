[English](04-model-pipeline.md) | [Português (Brasil)](04-model-pipeline.pt-BR.md)

# 04 — ModelPipeline: detailed orchestration

[Index](README.md) · Source: [pipeline/model_pipeline.py](../pipeline/model_pipeline.py)

## Object contract

ModelPipeline.__init__(package) only stores the package. run() executes a fixed sequence and returns the inference dictionary {records, errors, processed} only if it finishes without per-case errors. Intermediate structures are local variables, not exposed attributes or data loaded from previous reports. The class has no cache, subclass hooks or resume mechanism.

Dependencies include all extractor stages, the adapter factory, compiler and Wasmtime runner. Shared constants are batch 1, alignment 16 and suggested weight base 2048. Model names never select behavioral branches in run(); manifests and tensor shapes supply variable data.

## Actual execution order

| Order | Call/input | Output and consumer | Disk effect |
|---|---|---|---|
| 1 | package.validate_sources() | Confirms nonempty TFLite/template | None |
| 2 | create_adapter(package); list(adapter.discover_cases()) | Materialized TestCase list; ImageNet loads labels here | None |
| 3 | load_model; get_subgraph(index=0) | FlatBuffer and subgraph | None |
| 4 | Input/output counts and tensor_info | One INT8/UINT8 input/output, positive scale; input [1,H,W,3] | None |
| 5 | build_graph(model, subgraph) | Layers, edges, orders, indices | 02-grafo.txt |
| 6 | allocate_slots(graph["layers"], num_slots) | Allocation list and layer_output_slot | 03-alocacao-slots.txt |
| 7 | build_tensor_slot_mapping; validate_tensor_slot_mapping | Logical map and input set | 04-mapeamento-tensor-slot.txt |
| 8 | extract_weights_and_bias | Bytes and per-tensor offsets | 05-pesos-bias.txt |
| 9 | extract_quantization_parameters | MUL/SHIFT/Q6 and per-operator offsets | 06-quantizacao.txt |
| 10 | calculate_slot_bytes | Largest tensor and aligned slot size | 07-slot-bytes.txt |
| 11 | calculate_parameter_layout | Weight/bias/quantization/PARAMS bases | 08-layout-parametros.txt |
| 12 | build_runtime_tensor_mapping | Map with slot_shift applied | Included in 09 |
| 13 | calculate_layer_memory_layout | Parameter region and slot bases | Included in 09 |
| 14 | build_layer_params | Kernel dictionaries; optional synthetic layer | 09-layer-params.txt |
| 15 | build_params_blob | Record bytes, padding, resolved pointers | 10-params-blob.txt |
| 16 | calculate_final_memory_layout | Regions, final address, pages | 11-layout-final-memoria.txt |
| 17 | generate_wat | WAT metadata, final output, count | generated/model.wat |
| 18 | compile_wat_to_wasm | Binary path and size | generated/model.wasm |
| 19 | Compare output_info.elements with result_count | Reject mismatched count | No new file |
| 20 | run_wasm_inference | Per-RAW records and errors | Progress every 100 cases |
| 21 | adapter.build_report; append errors; save_report | Domain report and failures | 12-inferencia-wasm.txt |
| 22 | Check errors | Return results or raise RuntimeError | Files already persisted |

## Structure dependencies

```text
TFLite/subgraph
 ├─ graph → slots → logical mapping → validation
 │            └────────┴─ runtime_mapping (shift)
 ├─ weights/bias ──┐
 ├─ MUL/SHIFT/Q6 ──┼─ parameter_layout → PARAMS_BASE
 └─ slot_bytes ────┘                         │
                    real + synthetic count ─┤
                                            ▼
                                       layer_memory
runtime_mapping + offsets + TFLite options ──┤
                                            ▼
                                       layer_params
                                            ▼
                                        params_blob
                                            ▼
                                       final_memory
                                            ▼
                             template + data → WAT → WASM
```

The pipeline combines module results without reimplementing their algorithms. Tensor, graph and operator inputs become physical layout and generator bytes. Counts, offsets and shapes vary by model; record size, region order and field meanings come from the runtime.

## What validation covers

Input must have four dimensions, batch 1 and three channels. Synthetic RGB565 requires UINT8 TFLite input. These checks neither require positive H/W nor prove the original layout is NHWC: the pipeline requires and interprets that format. tensor_info uses the first scale/zero point. Output count is compared **after** compilation; no identity comparison is made between the output tensor and the last serialized operation.

The graph topologically orders layers for slot allocation, while build_layer_params traverses original FlatBuffer operator order. Current models rely on compatible orders. Unsupported operators may be skipped by LayerParams construction; there is no global rejection of all incompatible opcodes before generation.

## Errors, partial effects and reruns

An empty test directory prevents even WAT generation because discovery runs first. Graph, memory, serialization, write or compilation failures stop execution immediately. Per-case failures are collected, subsequent cases are attempted, and errors are reported before the final exception. build_report can also fail; there is no fallback.

Reports are overwritten stage by stage, not transactionally. A failure at 08 can leave new 02–07 and older 08–12 files. The mere presence of generated/model.wasm does not prove the latest run succeeded. Check the exit code and report 12. Obsolete artifacts are not cleaned up.

## Model/runtime boundary

The package chooses template, TFLite, format and adapter. The extractor receives concrete data and produces a common contract. A new adapter need not change this sequence if it meets current three-channel NHWC input and 8-bit output checks. Audio, multiple-output detection or larger batches require contract changes, not merely a registry entry.

