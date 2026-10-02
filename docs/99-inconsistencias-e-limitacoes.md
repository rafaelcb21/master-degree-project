# 99 — Inconsistencies, limitations, and undetermined information

[English](99-inconsistencias-e-limitacoes.md) | [Português (Brasil)](99-inconsistencias-e-limitacoes.pt-BR.md)

[Index](README.md) · Local state reviewed on September 28, 2026.

## Method and scope

The items below come from reading existing code, manifests, templates, tests, and artifacts. The task changed documentation, not kernels or functional rules. “Recommendation” describes possible future work, not an implemented capability. A risk identified by inspection does not mean that current models triggered every case.

## Current behavior and verified discrepancies

| ID | File / concept | Current behavior | Discrepancy or limitation | Recommendation |
|---|---|---|---|---|
| 01 | `wat/templates/model_template.wat`, QUANTIZE | Legacy template uses `layer_idx==67` to select UINT8 | Does not follow current output flags; no manifest selects it | Use active templates; remove/deprecate the legacy template in a separate functional task |
| 02 | Active templates, SOFTMAX | Multiplies logit differences by 7877, uses shift 16, a Q15 table, and factor 256 | Python calculates model-specific parameters that the kernel does not use; comments suggest fixed scale 0.12 | Implement parameter use and compare numerically against a reference |
| 03 | Active templates, `FLAG_BASE` | Constant value is 4 | Comment says address 0; host writes the format marker at 0 | Distinguish format at 0 from busy at 4; correct the comment in an appropriate revision |
| 04 | `layer_params.py` and depthwise kernel | Python records depth_mult; WAT uses channel oc directly in the input | depth_mult is absent from the 29 fields and values >1 are not correctly generalized | Reject unsupported cases or implement channel mapping |
| 05 | `operator_options.py`, ADD/FC | Activation is extracted and recorded | ADD/FC kernels do not apply act | Implement or reject activation other than NONE in these kernels |
| 06 | MEAN builder/runtime | Spatial H×W mean per channel | Does not read axis/keep_dims; uses truncated division | Declare/restrict the supported case and validate rounding |
| 07 | `_build_softmax_params` | Fixed beta 1 and derived parameters | Does not read the actual beta from SoftmaxOptions | Validate model beta or implement it |
| 08 | `build_layer_params` | Unknown types and operators without output may be skipped | No mandatory global failure for incompatible opcodes | Add complete coverage validation before generation |
| 09 | `graph.py` versus `layer_params.py` | Slots use topological order; serialized layers use original order | The orders are not explicitly compared | Validate ordering/output identity invariants |
| 10 | `slots.py`, QUANTIZE | Uses the same slot and executes continue | Does not update reader counts in this branch | Test liveness in branches with intermediate QUANTIZE |
| 11 | `tensor_mapping.py` | Propagates the first slot found through a producer; multiple outputs receive the same slot | Does not demonstrate semantic equivalence of the alias | Restrict valid aliases and validate graphs with multiple outputs |
| 12 | Logical map versus runtime | Runtime reconstructs only allocation inputs/outputs | Recursive resolutions in the logical map are not reused | Check consistency between both maps for new models |
| 13 | Weights/bias and builders | Missing values may be skipped; w_off defaults to 0; missing pointers are 0 | Some kernels load bias/quantization without checking zero | Fail early for missing required parameters |
| 14 | Per-channel quantization | Uses the first I/O scale and fills missing weight scales by repeating the last | qdim is reported but does not generically control the quantization axis | Validate scale count/axis |
| 15 | `operator_options.py` | Catches exceptions and uses defaults | Incompatible options may silently become stride 1/VALID/NONE | Distinguish missing options from parsing failures |
| 16 | `tflite_utils.py` | Missing scale → 1; missing zp → 0; failed reshape is ignored | Neutral values do not prove tensor validity | Validate schema/shape/quantization in consumers |
| 17 | `ModelConfig` | Partial validation; unknown fields ignored | Annotated types are not enforced; num_slots=3.0 and top_k=true are problematic cases | Introduce explicit type validation |
| 18 | `ModelPackage.resolve` | Allows `..` and absolute paths | Previous README stated all paths were relative as an absolute rule | Current documentation distinguishes convention from restriction |
| 19 | `main.py` | Catches OSError, ValueError, RuntimeError | Not every error becomes a message without a traceback | Document propagated classes; improve the error boundary if needed |
| 20 | Runner | One instance per batch, memory not cleared, continues after per-case errors | A trap may leave partial state; no isolation or timeout | Test failure followed by inference and define a reinitialization policy |
| 21 | WAT ranking | get_top_class/get_top5 read INT8 | Outputs of both current TFLite files are UINT8 | Keep ranking in the adapter; generalize exports if used externally |
| 22 | Duplicate WAT helpers | `_2`, `_3`, and exported variants differ | Unsuffixed exported function does not perform the same left shift as `_3` | Consolidate or document each helper's numerical ABI |
| 23 | Runtime and host | Required name `run_mobilenetv2`, NHWC RGB images, and 8-bit I/O | Part of the infrastructure remains specific to this domain | Separate the execution contract when supporting audio/other formats |
| 24 | ImageNet INT8 | Normalizes pixel/127.5−1 before quantization | Not configurable preprocessing for any network | Make normalization explicit in future configuration |
| 25 | Shared/local template | Both active files have the same contents | No synchronization link; they may diverge | Version and test each selected template |
| 26 | Drowsiness package | Template is outside its folder | Not self-contained for standalone distribution | Include the shared template or use a local copy when distributing |
| 27 | Previous `README.md` | Referenced `test/incompatible/a0397.raw` | Path does not exist in the current state; intended destination cannot be determined | Operational reference removed; no data file was created to support it |
| 28 | `img_mobilenetv2/aviao_uint8.raw` | A copy exists outside the package | Manifest only reads the file in models/.../test/img | Document the copy as unused by current execution |
| 29 | Old documentation | Contains hundreds of examples about the previous extractor and architecture | Orchestrator main.py, global paths, and mandatory synthetic layer became obsolete | Bodies preserved in historico; current chapters 00–33 are the reference |
| 30 | `inference/wasm_inference.py` | Repeated constant imports; descriptive string in the middle of the file | That string is not a module docstring | Editorial cleanup in a separate task, with no required functional effect here |
| 31 | Artifacts/reports | Incremental writes and direct overwriting | Interrupted execution may mix versions; no timestamps/checksums | Check exit codes; consider metadata and atomic writes |
| 32 | `wat_generator.py` | Output comes from the last LayerParam; regex checks remaining tokens | Does not guarantee final tensor identity or presence of every placeholder | Validate identity and template interface |
| 33 | `memory.py` | Bitmask alignment; sizing with defaults for negative values | No complete checks for powers of two/overlap/dynamic shapes | Validate layout invariants |
| 34 | `setup_env.ps1` | Reuses an existing .venv and calls python/pip | Does not validate whether the venv interpreter still exists; the old local environment is broken | Create a valid environment explicitly; do not treat printed success as an execution test |
| 35 | Current tests | Seven focused tests | No full TFLite/WASM equivalence or coverage of every kernel | Add differential references per operator/tensor |
| 36 | Flag history | Old text “flags 0 uint8, 1 int8” was incomplete | Current code already describes input and output bits; old reports may retain the previous text | Regenerate reports in a functional run when needed; this task does not change them |

## Limits explicitly rejected by the code

The manifest accepts only `layerparam-v1`, three slots, and the three documented format/layer pairs. The pipeline requires one input/output, UINT8 or INT8 I/O dtype, rank-4 input shape, batch 1, three channels, and UINT8 input for the RGB565 synthetic layer. The runner requires exact RAW size and accesses within memory bounds. Adapters reject folders without cases; ImageNet rejects structurally invalid labels, and the binary adapter requires two classes.

## Information that cannot be determined here

The current workflow does not provide recoverable documentation of the full training provenance, origin/licenses of all RAW files, train/test split, model conversion chain, original Colab configuration, probability calibration, or ESP32 hardware performance. Filenames and comments are insufficient evidence. The purpose indicated by the manifests can be described, but those missing details cannot.

## Possible improvements

The suggested technical priority is operator coverage validation and numerical comparison per layer, followed by removing softmax constants and strictly validating options/dtypes. Formats, input/output counts, and contracts can then be generalized. These are documented proposals; the task did not implement them or alter existing results.

