[English](21-extractor-model-loader.md) | [Português (Brasil)](21-extractor-model-loader.pt-BR.md)

# 21 — Loading the TFLite FlatBuffer

[Index](README.md) · Source: [extractor/model_loader.py](../extractor/model_loader.py)

## Purpose, input, and output

The module reads the original binary and returns TFLite schema access objects. It is called after test discovery and before extracting input/output metadata. It does not use TensorFlow, allocate interpreter tensors, or run TFLite inference.

`load_model(model_path)` reads all bytes with `Path.read_bytes`. It tries `TFLModel.GetRootAsModel(buf,0)`; if unavailable, it tries `TFLModel.Model.GetRootAsModel(buf,0)`. These two forms accommodate differences in the Python binding's exposed API. If neither exists, it raises `RuntimeError`. It returns the FlatBuffer root object; subsequent accessors query the loaded buffer.

`get_subgraph(model,index=0)` simply returns `model.Subgraphs(index)`. The pipeline always passes zero. It does not combine subgraphs, resolve calls between subgraphs, or offer CLI selection. A file with multiple subgraphs is not fully supported merely because its first subgraph can be read.

```text
model.toml: model.tflite
             │ ModelPackage.resolve
             ▼
          File path
             │ read_bytes
             ▼
       GetRootAsModel(buf,0)
             │ schema object
             ▼
       Subgraphs(0) ──► graph / tensors / options
```

The input is the package-specific path. The loader creates a structured view of the bytes; model and subgraph objects go to the extractor. The FlatBuffer format is shared; operators and buffers belong to the model. The TFLite file is neither modified nor permanently copied on disk.

## Validation and errors

The package already requires a nonempty file, but `load_model` can also be called directly. Opening errors propagate `OSError`; an invalid buffer may fail in the binding or only during later accesses. There is no explicit check of the TFLite magic identifier, schema version, opcode compatibility, or subgraph index bounds. The method does not return a report; the pipeline's first report file is graph report 02.

## Correct use

Keep the model object and derived data within the same run. Do not confuse a schema object with an interpreter: it does not provide `invoke()` in this workflow. Validation of a single input/output and of types belongs to the pipeline/runner, not this module. An `int8` filename has no bearing on loading; inspect `tensor.Type()`.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from pathlib import Path
import tflite.Model as TFLModel
```

### `load_model` — signature

```python
def load_model(model_path)
```

### `get_subgraph` — signature

```python
def get_subgraph(model, index=0)
```

## Preserved technical material

The previous explanation is in [02-carregamento-modelo.md](historico/02-carregamento-modelo.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencias-e-limitacoes.md).
