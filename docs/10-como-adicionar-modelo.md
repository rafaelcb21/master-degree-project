[English](10-como-adicionar-modelo.md) | [Português (Brasil)](10-como-adicionar-modelo.pt-BR.md)

# 10 — Tutorial: register a third model

[Index](README.md) · [Manifest reference](03-model-config-manifesto.md) · [Contract](08-contrato-layerparam-v1.md)

## Before copying files

Inspect the actual TFLite: one input/output, NHWC input [1,H,W,3], UINT8 or INT8 I/O, valid scales and runtime-supported operators. A filename or MobileNet name is insufficient. The builder can skip unknown operators, so opcode auditing is necessary before trusting results.

Run this inspection after creating the manifest:

```python
from pipeline.model_package import ModelPackage
from extractor.model_loader import load_model, get_subgraph
from extractor.tflite_utils import op_name
from inference.wasm_inference import tensor_info

package = ModelPackage.load("novo_modelo")
model = load_model(package.resolve(package.config.tflite))
subgraph = get_subgraph(model, index=0)
print("inputs/outputs:", subgraph.InputsLength(), subgraph.OutputsLength())
print(tensor_info(subgraph.Tensors(subgraph.Inputs(0))))
print(tensor_info(subgraph.Tensors(subgraph.Outputs(0))))
print([op_name(model, subgraph.Operators(i))
       for i in range(subgraph.OperatorsLength())])
```

This inspects the model; it does not compile or prove kernel equivalence. Dynamic shapes, alternative layouts and incompatible normalization require further analysis.

## Steps

1. Create models/novo_modelo/. The directory name is the --model value; CLI edits are unnecessary.
2. Put the original TFLite there. Its name can be model.tflite or another path specified in model.tflite. The pipeline neither converts nor renames it.
3. Choose the active ../../wat/templates/mobilenet_int8_v1.wat template, or copy it into wat/model_template.wat and update the manifest. Avoid the root legacy wat/templates/model_template.wat.
4. Declare contract="layerparam-v1" and num_slots=3. A new contract requires Python/WAT implementation, not just a new name.
5. Determine host byte format. RGB565 requires 2×H×W bytes; RGB/BGR888 requires 3×H×W. There are no headers or automatic PNG conversion.
6. RGB565 requires synthetic_layer="rgb565_to_rgb888" and UINT8 TFLite input. RGB/BGR888 uses "none".
7. Select a compatible adapter. Binary uses RGB565 and exactly two classes; ImageNet uses indexed labels and RGB/BGR. Other domains need their own Strategy.
8. Create nonempty test directories. Discovery precedes generation; the current CLI cannot compile a package without valid tests.
9. Match labels/classes to actual output tensor order. ImageNet JSON entries must contain [wnid, class_name] and cover output indices. Binary datasets need labels included in classes.
10. Run the following commands and inspect the exit code.
11. Inspect intermediate reports and compare against an appropriate numerical reference before broader use.

```powershell
python main.py --list-models
python main.py --model novo_modelo
python -m unittest discover -s tests -v
```

## Package tree

```text
models/novo_modelo/
├── model.toml                  sources, format, adapter
├── model.tflite                original source
├── test/                       RAWs in the documented format
├── labels/                     if required by the adapter
├── wat/                        optional local template
├── generated/                  created by writers
│   ├── model.wat
│   └── model.wasm
└── reports/                    created during extraction/testing
```

The author supplies sources, ModelPackage resolves paths, and writers create output directories without changing TFLite. Sources are model-specific; artifact names are fixed. generated/ and reports/ need not exist beforehand.

## Compatibility decision

```text
new TFLite → compatible I/O, operators and normalization?
               ├─ yes → manifest + tests → run → inspect reports → compare reference
               └─ no → identify the boundary
                         ├─ adapter: format/semantics
                         ├─ extractor: operator/metadata
                         ├─ ABI: fields/exports
                         └─ WAT: kernel/mathematics
                       implement and validate before claiming support
```

Compatibility determines whether registration suffices or code changes are needed. ModelPipeline shares orchestration, but does not generalize kernels that still assume INT8, depth multiplier 1, spatial mean and specific softmax behavior.

## When registration is insufficient

New opcodes, FLOAT32, multiple inputs/outputs, audio, larger batches, more than three slots, other INT8 normalization, broadcasting ADD and arbitrary-axis MEAN exceed current configuration support. A different softmax output scale also requires attention to fixed WAT constants. Numerical changes must update the contract and tests.

## Reading the first result

02 reveals dependencies; 03/04 logical storage; 05/06 extracted parameters; 07/08 region sizes; 09 kernel fields; 10 serialized pointers; 11 complete memory layout; 12 cases/errors. Trap-free inference does not prove correct translation. Compare per-layer intermediates against a reference interpreter to investigate differences; this is not yet automated.

