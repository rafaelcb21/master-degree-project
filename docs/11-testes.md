[English](11-testes.md) | [Português (Brasil)](11-testes.pt-BR.md)

# 11 — Tests and validation scope

[Index](README.md) · Source: [tests/test_model_packages.py](../tests/test_model_packages.py)

## Execution and organization

```powershell
python -m unittest discover -s tests -v
```

ModelPackagesTests(unittest.TestCase) contains seven methods. Dependencies are tempfile, re, struct, Path, SimpleNamespace, unittest.mock.patch, adapters and extractor; one test imports Wasmtime. pytest is not required. The unittest.main() entry point also supports direct execution if the repository is on the import path.

| Method | Group | Execution and protected regression |
|---|---|---|
| test_wasm_quantize_uses_output_type_at_any_layer_index | ABI/QUANTIZE/dtypes | Reads the active drowsiness template, substitutes placeholders for a one-page module, writes a temporary WASM and manually stores 29 int32 fields. Calls quantize at index 0 with flags 3: INT8 bytes [128,0,127] must become UINT8 [0,128,255]. With flags 0, UINT8 [0,128,255] becomes INT8 bytes [128,0,127]. Prevents reintroducing fixed index 67. |
| test_paths_are_relative_to_package | Paths/sources | Loads all packages, validates sources, checks generated WAT is under root/generated and differs from the template. Protects destination conventions, but does not change cwd or test path confinement. |
| test_unknown_contract_rejected | Manifest/ABI | Copies the drowsiness manifest into a temporary directory, replaces v1 with v2 and requires ValueError containing “Contrato”. Prevents silent acceptance of unimplemented versions. |
| test_synthetic_layer_optional | Synthetic layer | Uses an operator-free subgraph and mocked build_rgb565_layer. none gives an empty list without calling the helper; default gives one layer. Does not run the RGB565 kernel. |
| test_bgr_conversion_and_invalid_size | Input | Temporary one-pixel RAW [10,20,30] must yield [30,20,10]; metadata requesting six elements must fail. Protects channel order and size. |
| test_signed_output_and_stable_topk | Output/Top-K | Decodes [128,255,127] as [-128,-1,127], verifies scores and stable tie ranking. Label fixtures use [wnid,name]. Does not compare the complete report text. |
| test_binary_class_order_and_ties | Classification | Checks [200,55] predicts label 1 correctly, and rejects [100,100] ties and a zero vector. Protects class order and invalidity criteria. |

## Binary ABI test

```text
active WAT template → minimal placeholders → wasmtime.wat2wasm → temporary file
                                                                  ↓
                                                            Store / Instance
struct.pack("<29i") → memory[1024:1140]                             │
input bytes        → memory[4096:4099]                             │
                                                                  ▼
                                                       export quantize(store, 0)
                                                                  ▼
                                                       memory[8192:8195] → assert
```

Inputs are a template and artificial parameters, not a TFLite. The real kernel is exercised and bytes compared, establishing behavior for flags and quantization at index 0. Pointers/values are fixtures; record layout and export signature belong to the runtime. This exceeds merely testing Python flag construction, but does not cover the full network.

## Results and gaps

The original documentation review ran all seven tests; see [verification](98-verificacao-documental.md). This translation does not represent a new test run. Existing package reports supply additional evidence but are not assertions in this suite.

There are no current tests for complete TFLite/WASM equivalence, every isolated kernel, liveness on arbitrary graphs, a trap followed by another image, malformed JSON, broadcasting ADD, MEAN axes, softmax across scales or adapter INT8 normalization. Dataset provenance/licensing and statistical evaluation are also not tested. Do not describe these as existing coverage.

## Possible improvements

Differential TFLite tests with intermediate tensors and rounding checks would distinguish integration regressions from existing numerical differences. Invalid-format and manifest cases would improve error reporting. These are proposals, not implemented parts of this suite or translation task.

