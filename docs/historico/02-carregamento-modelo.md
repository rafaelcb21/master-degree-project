[English](02-carregamento-modelo.md) | [Português (Brasil)](02-carregamento-modelo.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body is retained in translation.

# 02 — Loading the TFLite model (`model_loader.py`)

## 1. Module purpose

The `extractor/model_loader.py` file is responsible for the first transformation performed by the pipeline:

```text
.tflite file on disk
        │
        ▼
sequence of bytes
        │
        ▼
TFLite Python binding
        │
        ▼
Model object
        │
        ▼
SubGraph used by the extractor
```

The current code is:

```python
from pathlib import Path
import tflite.Model as TFLModel


def load_model(model_path):
    buf = Path(model_path).read_bytes()

    if hasattr(TFLModel, "GetRootAsModel"):
        model = TFLModel.GetRootAsModel(buf, 0)

    elif (
        hasattr(TFLModel, "Model")
        and hasattr(TFLModel.Model, "GetRootAsModel")
    ):
        model = TFLModel.Model.GetRootAsModel(buf, 0)

    else:
        raise RuntimeError(
            "Binding tflite.Model não possui GetRootAsModel."
        )

    return model


def get_subgraph(model, index=0):
    return model.Subgraphs(index)
```

This module has two clearly defined responsibilities:

1. load and interpret the TFLite file;
2. select the subgraph used by the rest of the pipeline.

It does **not** analyze operators, tensors, weights, quantization, or memory.

Those responsibilities belong to later modules.

---

# 2. Position in the pipeline

The module appears immediately after configuration.

```text
config.py
   │
   │ MODEL_PATH
   ▼
model_loader.py
   │
   ├── load_model()
   │
   └── get_subgraph()
   ▼
Model + SubGraph
   │
   ├── graph.py
   ├── tflite_utils.py
   ├── weights.py
   ├── quantization.py
   ├── slots.py
   └── layer_params.py
```

Thus, almost all of the remaining extractor indirectly depends on this stage.

If the model cannot be loaded correctly, none of the following stages can run.

---

# 3. Importing `Path`

The file begins with:

```python
from pathlib import Path
```

`Path` handles the path received by `load_model()`.

Inside the function:

```python
buf = Path(model_path).read_bytes()
```

This allows `model_path` to be supplied either as:

```python
Path("model_int8_esp32.tflite")
```

or as:

```python
"model_int8_esp32.tflite"
```

because:

```python
Path(model_path)
```

normalizes the argument to a `Path` object.

---

# 4. Importing the TFLite binding

The second import is:

```python
import tflite.Model as TFLModel
```

The name:

```text
TFLModel
```

is simply a Python alias that makes explicit that this module represents the `Model` structure defined by the TFLite format.

The extractor does not use TensorFlow to execute the network at this stage.

It uses the Python binding for the TFLite format to navigate the file's serialized structure.

The distinction matters:

```text
TensorFlow / TFLite Interpreter
        │
        └── would execute the model

tflite binding used here
        │
        └── allows its structure to be inspected
```

In this project, the goal is not to ask TFLite to perform inference.

The goal is to extract information such as:

```text
operators
tensors
shapes
buffers
weights
biases
zero points
scales
operator options
```

to subsequently build a custom representation used by the WebAssembly module.

---

# 5. The `.tflite` file

A file such as:

```text
model_int8_esp32.tflite
```

is neither a Python file nor a text file.

It is a structured binary representation.

That is why we do not use:

```python
open(...).read()
```

to read it as text.

The code uses:

```python
read_bytes()
```

producing:

```text
bytes
```

Conceptually:

```text
model_int8_esp32.tflite
       │
       ▼
  Path.read_bytes()
       │
       ▼
b'\x1c\x00\x00...'
```

The actual contents comprise thousands or millions of bytes.

This sequence will be interpreted by the TFLite binding.

---

# 6. The `load_model()` function

The main function is:

```python
def load_model(model_path):
```

Its responsibility is:

```text
file path
      ↓
read bytes
      ↓
find the correct parser in the binding
      ↓
obtain Model object
      ↓
return Model
```

It receives only one piece of information:

```text
model_path
```

and returns:

```text
model
```

There is no global state or side effect related to the model.

---

# 7. Reading the bytes

The first instruction is:

```python
buf = Path(model_path).read_bytes()
```

It can be broken down into:

```text
model_path
    │
    ▼
Path(model_path)
    │
    ▼
Path object
    │
    ▼
.read_bytes()
    │
    ▼
buf
```

The name:

```text
buf
```

is short for `buffer`.

It contains the entire TFLite file in memory.

Conceptually:

```python
buf: bytes
```

---

# 8. Why load the entire file?

The current code uses:

```python
read_bytes()
```

and therefore loads the entire TFLite file into memory.

For the model used in this project, this is appropriate because the extractor needs to navigate different parts of the structure:

```text
Model
 ├── OperatorCodes
 ├── SubGraphs
 │    ├── Operators
 │    ├── Tensors
 │    ├── Inputs
 │    └── Outputs
 └── Buffers
```

During extraction, different modules repeatedly access these structures.

Keeping the buffer available allows the binding to perform these queries.

---

# 9. `GetRootAsModel`

After reading:

```python
if hasattr(TFLModel, "GetRootAsModel"):
    model = TFLModel.GetRootAsModel(buf, 0)
```

The function:

```text
GetRootAsModel
```

interprets the root structure stored in the buffer as a TFLite `Model` object.

Conceptually:

```text
bytes
  │
  ▼
GetRootAsModel
  │
  ▼
Model
```

This step is fundamental because the bytes are no longer treated as an opaque sequence and can instead be accessed through methods such as:

```python
model.Subgraphs(...)
model.OperatorCodes(...)
model.Buffers(...)
```

---

# 10. The second argument, `0`

The call is:

```python
TFLModel.GetRootAsModel(
    buf,
    0
)
```

The second argument:

```text
0
```

specifies the starting offset used to locate the root structure in the buffer.

When using a complete TFLite file normally, parsing starts at the beginning of the buffer.

The extractor does not need to know the internal offsets of every tensor or operator manually.

The binding provides this navigation.

---

# 11. The returned object is not a simplified copy of the model

It is useful to understand that:

```python
model = TFLModel.GetRootAsModel(buf, 0)
```

does not convert the entire model into common structures such as:

```python
dict
list
numpy.ndarray
```

The result is an object supplied by the TFLite binding.

It exposes methods for accessing the serialized structure.

For example:

```python
model.SubgraphsLength()
```

can report how many subgraphs exist.

And:

```python
model.Subgraphs(0)
```

allows one of them to be accessed.

Extraction happens on demand as these methods are called.

---

# 12. Compatibility between binding versions

The code contains two possible ways to locate `GetRootAsModel`.

First:

```python
if hasattr(
    TFLModel,
    "GetRootAsModel"
):
```

Second:

```python
elif (
    hasattr(TFLModel, "Model")
    and hasattr(
        TFLModel.Model,
        "GetRootAsModel"
    )
):
```

This is because different packaging approaches or versions of the Python binding can expose the generated class with slightly different structures.

In one environment, this may exist directly:

```python
TFLModel.GetRootAsModel(...)
```

In another:

```python
TFLModel.Model.GetRootAsModel(...)
```

The extractor accepts both.

---

# 13. First supported form

The first attempt is:

```python
if hasattr(TFLModel, "GetRootAsModel"):
```

If true:

```python
model = TFLModel.GetRootAsModel(
    buf,
    0
)
```

Structurally:

```text
TFLModel
   │
   └── GetRootAsModel()
```

This is the most direct form.

---

# 14. Second supported form

If the method does not exist directly, the code checks:

```python
elif (
    hasattr(TFLModel, "Model")
    and hasattr(
        TFLModel.Model,
        "GetRootAsModel"
    )
):
```

In this case, the structure is:

```text
TFLModel
   │
   └── Model
         │
         └── GetRootAsModel()
```

And the call becomes:

```python
model = (
    TFLModel.Model
    .GetRootAsModel(
        buf,
        0
    )
)
```

The logical result is the same:

```text
TFLite buffer
      ↓
Model object
```

---

# 15. Using `hasattr`

The function:

```python
hasattr(objeto, "atributo")
```

checks whether a given object has an attribute.

Example:

```python
hasattr(
    TFLModel,
    "GetRootAsModel"
)
```

returns:

```text
True
```

or:

```text
False
```

This makes it possible to decide dynamically which binding interface is available.

Without this check, directly using:

```python
TFLModel.GetRootAsModel(...)
```

could produce:

```text
AttributeError
```

in an installation with a different structure.

---

# 16. Why not use `try/except` directly?

It would also be possible to write something like:

```python
try:
    model = TFLModel.GetRootAsModel(
        buf,
        0
    )
except AttributeError:
    ...
```

But the current code prefers to check the available structure explicitly.

This makes it clearer that there are **two known, supported interfaces**.

The intention is not to ignore arbitrary errors.

It is to detect which binding format is installed.

---

# 17. Explicit failure

If neither form is available:

```python
else:
    raise RuntimeError(
        "Binding tflite.Model não possui GetRootAsModel."
    )
```

The extractor stops execution.

This is better than continuing with:

```python
model = None
```

and producing errors that are difficult to interpret later.

Failure occurs precisely at the stage responsible for reading the model.

Flow:

```text
GetRootAsModel available?
        │
     ┌──┴──┐
     │     │
    yes    no
     │     │
     ▼     ▼
 Model   RuntimeError
```

---

# 18. Why `RuntimeError`?

The detected problem is not simply a missing file or an invalid argument.

At this point, the extractor has found an incompatibility between the expected interface and the installed TFLite binding.

That is why the message:

```text
Binding tflite.Model não possui GetRootAsModel.
```

directly explains which requirement was not met. (The message means: the tflite.Model binding does not have GetRootAsModel.)

---

# 19. Other possible errors

Not all errors are handled manually by `load_model()`.

For example, if:

```python
MODEL_PATH
```

points to a nonexistent file:

```python
Path(model_path).read_bytes()
```

will produce the corresponding filesystem exception.

This is intentionally different from:

```text
incompatible binding
```

The code does not try to turn every error into a single generic exception.

This makes it possible to distinguish:

```text
nonexistent file
inaccessible file
incompatible binding
invalid file
```

according to where the failure occurs.

---

# 20. Return value of `load_model`

At the end:

```python
return model
```

The function returns the object representing the root of the TFLite model.

In `main.py`, its conceptual usage is:

```python
model = load_model(
    MODEL_PATH
)
```

From this point onward:

```text
MODEL_PATH
```

is no longer the main source used by the pipeline.

The structure in memory becomes:

```text
model
```

---

# 21. Conceptual structure of `Model`

A simplified representation of the information accessed later is:

```text
Model
│
├── OperatorCodes
│    ├── opcode 0
│    ├── opcode 1
│    └── ...
│
├── SubGraphs
│    │
│    └── SubGraph 0
│         ├── Inputs
│         ├── Outputs
│         ├── Tensors
│         └── Operators
│
└── Buffers
     ├── buffer 0
     ├── buffer 1
     └── ...
```

This structure is essential to understanding the rest of the extractor.

---

# 22. Relationship between operators and operation codes

An operator stored inside a subgraph does not need to carry the name directly:

```text
CONV_2D
```

The operator can reference an entry in the table of:

```text
OperatorCodes
```

That is why the extractor later uses helper functions to convert:

```text
OpcodeIndex
      ↓
OperatorCode
      ↓
BuiltinCode
      ↓
CONV_2D
```

This information already exists in the model loaded by `load_model()`.

However, `model_loader.py` does not interpret these contents.

It only makes the necessary object available so that `tflite_utils.py` and `graph.py` can do this later.

---

# 23. Relationship between tensors and buffers

Another useful example is the relationship:

```text
Tensor
  │
  └── Buffer()
         │
         ▼
      Model.Buffers(...)
```

A tensor can point to a buffer containing constant data.

This is how the extractor later identifies and retrieves:

```text
weights
biases
other constant tensors
```

Again, `model_loader.py` only provides access to the structure.

Interpretation happens in later modules.

---

# 24. The `get_subgraph()` function

The second function in the file is:

```python
def get_subgraph(
    model,
    index=0
):
    return model.Subgraphs(
        index
    )
```

It has a single responsibility:

```text
Model
  ↓
select SubGraph
  ↓
return SubGraph
```

---

# 25. What is a subgraph in this context?

The model can contain a collection of subgraphs.

Conceptually:

```text
Model
│
├── SubGraph 0
├── SubGraph 1
├── SubGraph 2
└── ...
```

Each subgraph can have:

```text
inputs
outputs
tensors
operators
```

For the current pipeline, the default is:

```python
index = 0
```

Therefore:

```python
get_subgraph(model)
```

is equivalent to:

```python
model.Subgraphs(0)
```

---

# 26. Why `index=0`?

The current extractor works with the main subgraph used by the model being analyzed.

That is why the API provides:

```python
index=0
```

as the default.

Normal usage:

```python
subgraph = get_subgraph(
    model
)
```

Result:

```text
SubGraph 0
```

But the function still explicitly allows:

```python
subgraph = get_subgraph(
    model,
    index=1
)
```

if another subgraph needs to be accessed.

---

# 27. Why create `get_subgraph()` if the call is simple?

It would be possible to write this directly in `main.py`:

```python
subgraph = model.Subgraphs(0)
```

However, encapsulating the operation has some advantages.

First, it makes the intention explicit:

```python
get_subgraph(model)
```

is semantically clearer than:

```python
model.Subgraphs(0)
```

for someone reading the main flow.

Second, it centralizes the current policy:

```text
default subgraph = index 0
```

Third, if additional validation is needed in the future, it can be implemented here without changing every call.

For example, future checks could include:

```text
does the index exist?
does the subgraph have inputs?
does the subgraph have outputs?
```

The current code does not yet perform these checks.

---

# 28. Return value of `get_subgraph()`

The result is normally stored as:

```python
subgraph = get_subgraph(
    model
)
```

From this object, subsequent modules can make queries such as:

```python
subgraph.OperatorsLength()
```

```python
subgraph.Operators(i)
```

```python
subgraph.Tensors(tensor_id)
```

```python
subgraph.Inputs(...)
```

```python
subgraph.Outputs(...)
```

Thus:

```text
model
```

represents the global structure,

while:

```text
subgraph
```

is the main focus of network analysis.

---

# 29. Relationship between `model` and `subgraph`

A simplified view is:

```text
model
│
├── global metadata
│
├── OperatorCodes
│
├── Buffers
│
│
└── SubGraphs
      │
      └── subgraph
            │
            ├── tensors
            ├── operators
            ├── inputs
            └── outputs
```

That is why several subsequent functions receive both:

```python
func(
    model,
    subgraph,
    ...
)
```

The reason is that some information belongs to `subgraph`, while other information remains at the global `model` level.

---

# 30. Example: resolving an operation name

Later, a function such as:

```python
op_name(
    model,
    op
)
```

needs both levels.

The operator:

```text
op
```

belongs to:

```text
subgraph
```

but its code can be resolved through:

```text
model.OperatorCodes(...)
```

Flow:

```text
SubGraph
   │
   └── Operator
          │
          └── OpcodeIndex
                 │
                 ▼
             Model
                 │
                 └── OperatorCodes
                        │
                        ▼
                     CONV_2D
```

This explains why it is useful to preserve both objects.

---

# 31. Example: reading weights

Something similar happens with a constant tensor.

The tensor is located in the subgraph:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

It then indicates which buffer contains the data:

```python
tensor.Buffer()
```

And that buffer is accessed in the model:

```python
model.Buffers(
    tensor.Buffer()
)
```

Flow:

```text
SubGraph
   │
   └── Tensor
          │
          └── Buffer ID
                 │
                 ▼
              Model
                 │
                 └── Buffers
                       │
                       ▼
                  weight bytes
```

Thus, `model_loader.py` prepares exactly the two access levels that the rest of the extractor needs.

---

# 32. What this module deliberately does not do

The module contains no logic for:

```text
identifying operators
building the graph
calculating topology
allocating slots
extracting weights
extracting biases
calculating multipliers
calculating shifts
calculating Q6
calculating memory
generating LayerParams
generating params_blob
generating WAT
```

This separation matters.

The role of this file is exclusively:

```text
file → Model → SubGraph
```

---

# 33. No effects during `import`

A key decision in the current code is that the model is not loaded directly in the module body.

We do not run:

```python
MODEL = load_model(
    "model_int8_esp32.tflite"
)
```

when importing `model_loader.py`.

Instead:

```python
def load_model(...):
```

only defines the function.

Reading happens when `main.py` decides to execute it.

This avoids side effects at import time.

---

# 34. Why avoid automatic loading?

Imagine another module executing:

```python
from extractor.model_loader import (
    load_model
)
```

If the file were read automatically during import, merely importing the function would already attempt to access:

```text
model_int8_esp32.tflite
```

This would create unnecessary coupling.

The current implementation allows:

```text
import module
      │
      ▼
no file opened
      │
      ▼
call load_model()
      │
      ▼
file actually loaded
```

This separation makes testing and reuse easier.

---

# 35. Complete flow of this module

The behavior can be summarized as follows:

```text
MODEL_PATH
    │
    ▼
load_model()
    │
    ├── Path(model_path)
    │
    ├── read_bytes()
    │
    ▼
   buf
    │
    ├── TFLModel.GetRootAsModel?
    │          │
    │          └── yes → parse
    │
    └── TFLModel.Model.GetRootAsModel?
               │
               └── yes → parse
                      │
                      ▼
                    model
                      │
                      ▼
              get_subgraph()
                      │
                      ▼
                 SubGraph 0
```

---

# 36. Relationship with `main.py`

In the main flow, expected usage is simple:

```python
model = load_model(
    MODEL_PATH
)

subgraph = get_subgraph(
    model
)
```

After this:

```text
MODEL_PATH
    ↓
model
    ↓
subgraph
```

and the extractor can begin structural analysis.

`main.py` remains responsible for orchestration, while `model_loader.py` only implements the specific task.

---

# 37. Why return objects instead of custom structures?

At this stage there is no reason to copy the entire model into an intermediate Python structure.

For example, we do not create:

```python
model_data = {
    "operators": ...,
    "tensors": ...,
    "buffers": ...
}
```

The original structure can already be navigated through the binding.

Specialized modules extract only what they actually need.

This avoids an unnecessary complete intermediate transformation.

---

# 38. Architectural responsibility

The role of this module can be represented in three layers:

```text
Filesystem
      │
      ▼
model_loader.py
      │
      ▼
TFLite binding
      │
      ▼
Extraction modules
```

It acts as a small boundary between:

```text
persistent representation
```

and:

```text
navigable representation
```

In other words:

```text
binary file on disk
           ↓
         bytes
           ↓
      Model object
```

---

# 39. Why does this matter for the project?

The project's goal is not to execute the model directly through a TensorFlow Lite runtime.

The TFLite model serves as a structured source of information needed to build another execution representation.

Thus, the overall flow is not:

```text
TFLite
  ↓
TFLite Interpreter
  ↓
inference
```

The extractor's flow is:

```text
TFLite
  ↓
structural reading
  ↓
parameter extraction
  ↓
custom serialization
  ↓
WAT
  ↓
WASM
  ↓
WebAssembly runtime
```

Within this process, `model_loader.py` implements the first bridge.

---

# 40. Relationship with later independence from TFLite

During extraction, the pipeline depends on the TFLite structure.

However, the final WAT/WASM artifact does not need to consult the TFLite file during each inference.

The conceptual transformation is:

```text
                 BUILD PHASE

model.tflite
    │
    ▼
model_loader
    │
    ▼
extractor
    │
    ▼
weights + parameters + code
    │
    ▼
model.wat
    │
    ▼
model.wasm


                 EXECUTION PHASE

image
  │
  ▼
model.wasm
  │
  ▼
inference
```

Thus, TFLite participates in building the artifact, but does not need to remain as the inference runtime of the produced module.

This separation is central to this project's architecture.

---

# 41. Current handling of multiple subgraphs

Although:

```python
get_subgraph(
    model,
    index=0
)
```

allows another index to be supplied, the rest of the pipeline was developed treating the selected subgraph as the network to process in full.

Therefore, support for models that depend on multiple interrelated subgraphs should not be assumed merely because the function accepts:

```python
index
```

The function allows a subgraph to be selected.

This does not mean the pipeline automatically implements execution semantics involving several subgraphs.

This distinction matters.

---

# 42. Validation that does not yet exist

The current code is deliberately simple.

It does not explicitly check:

```text
whether model_path has the .tflite extension
whether the file is empty
whether at least one subgraph exists
whether index is within range
whether the subgraph has operators
whether the subgraph has an input
whether the subgraph has an output
```

Some of these situations would naturally cause errors later.

If the extractor is used as the backend for a graphical interface in the future, turning these conditions into friendlier validation could be useful.

For example:

```text
uploaded file
    ↓
validation
    ├── valid model?
    ├── has a subgraph?
    ├── supported operators?
    └── compatible quantization?
```

But this belongs to a future layer of application robustness.

There is no need to add complexity now solely for the current local execution.

---

# 43. Possible future evolution

When the extractor becomes a backend, the function can receive a file selected by the user.

The flow could become:

```text
Angular
   │
   │ upload .tflite
   ▼
Python backend
   │
   ▼
load_model()
   │
   ▼
validation
   │
   ▼
extraction
   │
   ▼
WAT/WASM
```

The advantage of the current implementation is that:

```python
load_model(model_path)
```

already does not depend directly on a global constant.

Today, `main.py` supplies:

```python
MODEL_PATH
```

In the future, the backend can supply:

```python
uploaded_model_path
```

without modifying the loading function.

---

# 44. Design decision: explicitly passing the path

Notice the difference between:

```python
def load_model():
    buf = MODEL_PATH.read_bytes()
```

and the chosen implementation:

```python
def load_model(model_path):
    buf = Path(model_path).read_bytes()
```

The second is better decoupled.

`config.py` decides:

```text
which file to use
```

while:

```text
model_loader.py
```

decides:

```text
how to load a TFLite file
```

This follows the separation:

```text
configuration
     ≠
implementation
```

---

# 45. Function summary

| Function | Input | Output | Responsibility |
| ---------------- | -------------------- | ---------- | --------------------------------------------- |
| `load_model()` | Path to the `.tflite` | `Model` | Read the file and create the TFLite root object |
| `get_subgraph()` | `Model` and index | `SubGraph` | Select the subgraph used by the extractor |

---

# 46. Module summary

`model_loader.py` implements a simple but essential stage:

```text
FILE
   │
   ▼
BYTES
   │
   ▼
MODEL
   │
   ▼
SUBGRAPH
```

Its main architectural characteristic is keeping loading separate from interpretation.

It does not need to know:

```text
what a convolution is;
how weights will be serialized;
how many slots will exist;
where data will be placed in memory;
how the WAT will execute the network.
```

It only needs to know:

```text
how to turn the TFLite file
into a structure that subsequent modules can navigate.
```

From there, responsibility passes to the specialized modules.

The project flow up to this point is:

```text
┌───────────────────────────────┐
│          config.py            │
│                               │
│ MODEL_PATH                    │
│ NUM_SLOTS                     │
│ ALIGN                         │
│ ...                           │
└───────────────┬───────────────┘
                │
                │ MODEL_PATH
                ▼
┌───────────────────────────────┐
│       model_loader.py         │
│                               │
│ load_model()                  │
│ get_subgraph()                │
└───────────────┬───────────────┘
                │
                │ Model + SubGraph
                ▼
┌───────────────────────────────┐
│       structural extraction   │
│                               │
│ graph.py                      │
│ tflite_utils.py               │
│ weights.py                    │
│ quantization.py               │
│ ...                           │
└───────────────────────────────┘
```

The file is small because its responsibility is also small and clearly defined. This is desirable: the rest of the extractor's complexity is divided among modules with specific knowledge about graphs, tensors, quantization, memory, and serialization.
