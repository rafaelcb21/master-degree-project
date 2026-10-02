[English](06-tensor-slot-mapping.md) | [Português (Brasil)](06-mapeamento-tensor-slot.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencies-and-limitations.md). The original body has been preserved in the Portuguese edition.

# 06 — Mapping tensors to slots (`tensor_mapping.py`)

## 1. Module purpose

`extractor/tensor_mapping.py` associates tensor identifiers in the TFLite model with the logical slots previously calculated by `slots.py`.

At the preceding stage, the project has information such as:

```text
L0 → SLOT0
L1 → SLOT1
L2 → SLOT2
```

The rest of extraction often needs to answer:

```text
which slot holds TFLite tensor 37?
```

Thus, this module builds:

```text
tensor_id → slot
```

For example:

```python
{
    0: 0,
    17: 1,
    23: 2,
    31: 0,
}
```

The interpretation is:

```text
tensor 0  → SLOT0
tensor 17 → SLOT1
tensor 23 → SLOT2
tensor 31 → SLOT0
```

---

# 2. Current code

The module contains four main functions:

```text
resolve_slot_from_producer()
build_tensor_slot_mapping()
validate_tensor_slot_mapping()
tensor_mapping_to_text()
```

Their responsibilities are:

| Function | Responsibility |
| -------------------------------- | --------------------------------------------------------- |
| `resolve_slot_from_producer()` | Recursively resolve a tensor's slot |
| `build_tensor_slot_mapping()` | Build the complete mapping |
| `validate_tensor_slot_mapping()` | Check that useful operators have mapped tensors |
| `tensor_mapping_to_text()` | Generate a text report |

---

# 3. Position in the pipeline

The module comes after:

```text
graph.py
   ↓
dependencies between layers

slots.py
   ↓
layer → slot
```

and before:

```text
layer_params.py
   ↓
tensor → slot → pointer
```

Flow:

```text
TFLite
  │
  ▼
graph.py
  │
  │ layer → predecessors
  ▼
slots.py
  │
  │ layer → slot
  ▼
tensor_mapping.py
  │
  │ tensor → slot
  ▼
layer_params.py
  │
  │ slot → address
  ▼
LayerParam
```

---

# 4. Why is this module needed?

`slots.py` knows:

```text
L8 → SLOT2
```

A TFLite operation has something like:

```text
input tensor = 57
output tensor = 61
```

We therefore need to relate:

```text
tensor 61
    ↓
was produced by L8
    ↓
L8 uses SLOT2
    ↓
tensor 61 → SLOT2
```

This is exactly the transformation performed by the module.

---

# 5. Imports

The file starts with:

```python
from extractor.tflite_utils import (
    is_constant_tensor,
    op_name,
)
```

Two pieces of information are needed.

### `is_constant_tensor()`

It distinguishes:

```text
intermediate activation
```

from:

```text
weight
biases
another constant tensor
```

Only dynamic data tensors need slots.

### `op_name()`

It is used in validation error messages.

---

# 6. Three different identities

At this stage, there are three ways to identify network elements.

### TFLite operator

```text
op_index = 17
```

### Logical layer

```text
L15
```

### TFLite tensor

```text
tensor_id = 43
```

The module must navigate between these three representations.

---

# 7. Relationships available before this stage

From `graph.py` we have:

```text
producer_by_tensor
```

which answers:

```text
tensor_id → producer op_index
```

Example:

```python
producer_by_tensor[43] = 17
```

We also have:

```text
old_idx_to_label
```

which answers:

```text
op_index → logical layer
```

Example:

```python
old_idx_to_label[17] = "L15"
```

And from `slots.py`:

```text
layer_output_slot
```

which answers:

```text
layer → slot
```

Example:

```python
layer_output_slot["L15"] = 2
```

Combining them:

```text
tensor 43
   ↓
op 17
   ↓
L15
   ↓
SLOT2
```

Therefore:

```text
tensor 43 → SLOT2
```

---

# 8. The `resolve_slot_from_producer()` function

The first function is:

```python
def resolve_slot_from_producer(
    tensor_id,
    *,
    model,
    subgraph,
    tensor_to_slot,
    producer_by_tensor,
    old_idx_to_label,
    layer_output_slot,
    visiting=None,
):
```

It tries to find a tensor's slot by following its origin.

The conceptual logic is:

```text
tensor
  ↓
does it already have a slot?
  │
  ├── yes → return
  │
  └── no
       ↓
which operator produced it?
       ↓
is the producer in the useful graph?
  │
  ├── yes → use the layer's slot
  │
  └── no
       ↓
follow the producer's inputs
       ↓
try to find an origin with a slot
```

---

# 9. Why is the function recursive?

Not every intermediate operator needs direct representation in the graph used by the extractor.

Conceptually, there may be:

```text
L4
 ↓
unrepresented operation
 ↓
tensor X
 ↓
L5
```

In this case, there is not necessarily:

```text
intermediate operation → Lx → slot
```

The function therefore follows the chain backward.

---

# 10. Conceptual example

Consider:

```text
tensor 20
   ↓
useful Op 8
   ↓
tensor 21
   ↓
ignored Op 9
   ↓
tensor 22
```

Suppose:

```text
Op8 → L7 → SLOT1
```

But:

```text
Op9
```

has no logical label.

When we want to find:

```text
tensor 22 → ?
```

the function finds:

```text
tensor 22
   ↓
producer = Op9
   ↓
Op9 has no Lx
   ↓
Op9 input = tensor 21
   ↓
tensor 21 producer = Op8
   ↓
Op8 → L7
   ↓
L7 → SLOT1
```

Result:

```text
tensor 22 → SLOT1
```

---

# 11. The `visiting` parameter

The function has:

```python
visiting=None
```

When no collection is supplied:

```python
if visiting is None:
    visiting = set()
```

This set tracks which tensors are already being visited during the current resolution.

---

# 12. Purpose of `visiting`

Even if the expected graph is acyclic, a defensive recursive routine must prevent:

```text
tensor A
  ↓
tensor B
  ↓
tensor C
  ↓
tensor A
  ↓
...
```

if an unexpected relationship creates a cycle during the search.

---

# 13. Detecting repetition

The code:

```python
if tensor_id in visiting:
    return None
```

prevents repeating the same search indefinitely.

Then:

```python
visiting.add(tensor_id)
```

marks the current tensor.

---

# 14. Graph cycles versus search cycles

`graph.py` already checks for cycles in the structure of useful operators.

Here, however, the function may traverse:

```text
unrepresented operators
intermediate tensors
```

It therefore has its own local protection.

---

# 15. First case: known tensor

The first attempt is:

```python
if tensor_id in tensor_to_slot:
    return tensor_to_slot[tensor_id]
```

This acts as a cache.

If we already know:

```python
tensor_to_slot[43] = 2
```

there is no need to retrace the entire producer chain.

---

# 16. Cache benefit

Without this check, different tensors could trigger repeated traversals of the same graph region.

With caching:

```text
first resolution
    ↓
calculate slot
    ↓
store tensor_to_slot
    ↓
subsequent queries return directly
```

---

# 17. Finding the producer

If the tensor has no slot yet:

```python
producer_op_idx = (
    producer_by_tensor.get(
        tensor_id
    )
)
```

This structure came from `graph.py`.

---

# 18. Tensor without a producer

If:

```python
producer_op_idx is None
```

the function returns:

```python
None
```

This may occur, for example, when the tensor is:

```text
external input
```

and is not produced by any operation.

Graph inputs are handled separately in `build_tensor_slot_mapping()`.

---

# 19. Directly represented producer

The first useful scenario is:

```python
if producer_op_idx in old_idx_to_label:
```

This means the producer operator belongs to the logical graph.

---

# 20. Converting to a label

The following is obtained:

```python
layer_name = (
    old_idx_to_label[
        producer_op_idx
    ]
)
```

Example:

```text
producer_op_idx = 17
```

becomes:

```text
L15
```

---

# 21. Converting a label to a slot

Then:

```python
output_slot = (
    layer_output_slot.get(
        layer_name
    )
)
```

Example:

```python
layer_output_slot["L15"] = 2
```

Then:

```text
output_slot = 2
```

---

# 22. Recording in the cache

If the slot was found:

```python
tensor_to_slot[tensor_id] = (
    output_slot
)
```

and:

```python
return output_slot
```

That relationship is now directly known.

---

# 23. Complete direct flow

```text
tensor_id
    ↓
producer_by_tensor
    ↓
op_index
    ↓
old_idx_to_label
    ↓
Lx
    ↓
layer_output_slot
    ↓
slot
    ↓
tensor_to_slot[tensor_id] = slot
```

---

# 24. Producer not directly represented

If:

```python
producer_op_idx
```

is not in:

```python
old_idx_to_label
```

the function does not give up immediately.

It retrieves the operator:

```python
producer_op = (
    subgraph.Operators(
        producer_op_idx
    )
)
```

and starts examining its inputs.

---

# 25. Idea behind this stage

The assumption is:

```text
if the producer has no slot of its own in the logical graph,
its tensor may be associated with the same flow
as an earlier dynamic input.
```

This logic is especially useful for operators traversed during graph simplification.

---

# 26. Iterating over inputs

The code:

```python
for j in range(
    producer_op.InputsLength()
):
```

obtains:

```python
input_tensor_id = int(
    producer_op.Inputs(j)
)
```

---

# 27. Negative inputs

If:

```python
input_tensor_id < 0
```

the input is skipped:

```python
continue
```

This follows the same convention used in other modules for invalid or optional IDs.

---

# 28. Constant tensors are skipped

The function executes:

```python
if is_constant_tensor(
    model,
    subgraph,
    input_tensor_id,
):
    continue
```

This is essential.

Consider an operation:

```text
dynamic input
+
constant weight
```

The slot search must follow:

```text
dynamic input
```

rather than:

```text
weight
```

because weights do not live in activation slots.

---

# 29. Recursive call

For a dynamic input:

```python
slot = resolve_slot_from_producer(
    input_tensor_id,
    ...
)
```

The function tries to resolve the chain again.

---

# 30. `visiting.copy()`

The call uses:

```python
visiting=visiting.copy()
```

This copies the visited-node set for that branch.

---

# 31. Why copy?

Imagine an operator with two inputs:

```text
           input A
          /
current op
          \
           input B
```

Each search branch receives its own derived state.

Visiting a tensor in branch A thus does not necessarily block its independent analysis in branch B.

---

# 32. When a slot is found

If:

```python
slot is not None
```

the result is associated with the original tensor:

```python
tensor_to_slot[
    tensor_id
] = slot
```

and the function returns immediately.

---

# 33. First resolvable path

It is important to state the current behavior precisely:

```text
the function iterates over the producer's inputs
and returns the first slot it can resolve
```

It does not compare multiple slots.

---

# 34. Implication of this decision

For intermediate operators considered transparent, this may be appropriate.

For an unrepresented operator that combines two semantically different dynamic inputs, such as:

```text
input A in SLOT1
input B in SLOT2
```

the function would return the first resolved slot.

Recursive resolution therefore assumes that traversal through unrepresented operators is semantically compatible with this simplification.

This is an important property of the current algorithm.

---

# 35. Resolution failure

If no input reveals a slot:

```python
return None
```

This tensor remains unmapped.

It will later be included in:

```text
unmapped_after
```

and validation will fail if a useful operator needs it.

---

# 36. The `build_tensor_slot_mapping()` function

This is the main construction function:

```python
def build_tensor_slot_mapping(
    model,
    subgraph,
    *,
    slot_allocation,
    layer_output_slot,
    label_to_op_idx,
    old_idx_to_label,
    producer_by_tensor,
):
```

It performs four stages:

```text
1. map layer outputs
2. map subgraph inputs
3. resolve intermediates
4. list what remains unmapped
```

This organization is explicit in the code.

---

# 37. Initial structures

Initially:

```python
tensor_to_slot = {}
```

This will be the main structure.

Alongside it:

```python
mapped_from_layers = []
graph_input_mappings = []
pending_before_resolution = []
```

additional information is retained for reporting and diagnostics.

---

# 38. `tensor_to_slot`

This is the source of truth.

Example:

```python
{
    0: 0,
    5: 0,
    9: 1,
    14: 2,
    17: 0,
}
```

Subsequent modules use this dictionary to find slots.

---

# 39. `mapped_from_layers`

This list records tensors directly associated with layer outputs.

Example:

```python
{
    "tensor_id": 17,
    "layer": "L4",
    "op_index": 4,
    "slot": 2,
}
```

It is primarily a traceability structure.

---

# 40. `graph_input_mappings`

It explicitly records the subgraph's external inputs assigned to slot 0.

Example:

```python
{
    "tensor_id": 0,
    "slot": 0,
}
```

---

# 41. `pending_before_resolution`

It records dynamic tensors that initially:

```text
were not already mapped outputs
were not constants
were not subgraph inputs
```

They become candidates for subsequent recursive resolution.

---

# 42. First stage: map layer outputs

The code iterates over:

```python
for alloc in slot_allocation:
```

It directly uses the result produced by `slots.py`.

---

# 43. Getting the label

Each record has:

```python
layer_name = alloc["layer"]
```

Example:

```text
L12
```

---

# 44. Returning to the TFLite operator

To find which tensors the layer produces:

```python
op_idx = (
    label_to_op_idx.get(
        layer_name
    )
)
```

Example:

```text
L12 → op_index 14
```

---

# 45. Label without an operator

If:

```python
op_idx is None
```

the record is skipped:

```python
continue
```

In the normal flow, labels produced by `graph.py` should have a corresponding operator.

---

# 46. Getting the operator

```python
op = subgraph.Operators(
    op_idx
)
```

Its actual outputs can now be queried.

---

# 47. Iterating over all outputs

The code uses:

```python
for j in range(
    op.OutputsLength()
):
```

It therefore does not assume that an operation necessarily has only one output.

---

# 48. Output tensor ID

Each output is obtained through:

```python
tensor_id = int(
    op.Outputs(j)
)
```

Negative IDs are skipped.

---

# 49. Layer slot

The slot comes directly from the allocation:

```python
output_slot = (
    alloc["output_slot"]
)
```

---

# 50. Associating tensor → slot

Then:

```python
tensor_to_slot[
    tensor_id
] = output_slot
```

Example:

```text
L12 → SLOT2
L12 produces tensor 48
```

results in:

```text
tensor 48 → SLOT2
```

---

# 51. Recording for the report

In addition to the main mapping, it stores:

```python
{
    "tensor_id": tensor_id,
    "layer": layer_name,
    "op_index": op_idx,
    "slot": output_slot,
}
```

This will help explain the origin of each relationship later.

---

# 52. First phase result

After this stage, all useful operator outputs should be associated with their respective layer slots.

Example:

```text
L0 output tensor 3  → SLOT0
L1 output tensor 10 → SLOT1
L2 output tensor 15 → SLOT2
L3 output tensor 21 → SLOT0
```

---

# 53. Second stage: subgraph inputs

The module now identifies external inputs:

```python
graph_inputs = {
    int(subgraph.Inputs(i))
    for i in range(
        subgraph.InputsLength()
    )
}
```

---

# 54. Why use a `set`?

The main subsequent operation is:

```python
if tensor_id in graph_inputs:
```

A set is appropriate for membership tests.

---

# 55. Example

If the model has:

```text
input tensor = 0
```

we get:

```python
graph_inputs = {
    0
}
```

---

# 56. Scanning all tensors

The code iterates over:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

At this stage it examines the entire tensor table.

---

# 57. Already mapped tensor

If:

```python
tensor_id in tensor_to_slot
```

the function executes:

```python
continue
```

This avoids overwriting an association created in the first phase.

---

# 58. Constant tensor

If:

```python
is_constant_tensor(...)
```

returns `True`, it is also skipped.

Weights and biases do not need activation slots.

---

# 59. Subgraph input

If:

```python
tensor_id in graph_inputs
```

the code sets:

```python
tensor_to_slot[
    tensor_id
] = 0
```

---

# 60. Why SLOT0?

Under the logical convention used before introducing the synthetic RGB565→RGB888 layer, external input is initially associated with logical slot 0.

Later, `layer_params.py` applies the transformation needed for the layout actually used by the runtime.

Thus, in this module:

```text
graph input → logical SLOT0
```

---

# 61. Recording the input

The following is also inserted:

```python
{
    "tensor_id": tensor_id,
    "slot": 0,
}
```

into:

```python
graph_input_mappings
```

---

# 62. Tensor not immediately resolved

If the tensor:

```text
is not mapped
is not constant
is not an input
```

it is added to:

```python
pending_before_resolution
```

---

# 63. Meaning of “pending”

Pending does not necessarily mean an error.

It only means:

```text
this tensor could not be mapped by the two direct rules
```

The recursive stage will still try to resolve it.

---

# 64. Example

Consider:

```text
L3
 ↓
ignored operation
 ↓
tensor 27
 ↓
L4
```

Tensor 27:

```text
is not directly the output of a layer Lx
is not a model input
is not constant
```

Initially, therefore:

```text
tensor 27 = pending
```

Recursive resolution may discover that it belongs to the same flow as L3's output slot.

---

# 65. Third stage: recursive closure

Then:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

all tensors are traversed again.

---

# 66. Already known tensors

If they are already in:

```python
tensor_to_slot
```

they are skipped.

---

# 67. Constants

They are also skipped again.

---

# 68. Resolution attempt

For the others:

```python
resolve_slot_from_producer(
    tensor_id,
    ...
)
```

is executed.

---

# 69. Why traverse everything again?

Because the recursive function may add new mappings to:

```python
tensor_to_slot
```

during the search.

This acts as a closure stage for relationships still missing.

---

# 70. Closure example

Before:

```python
tensor_to_slot = {
    10: 1,
    20: 2,
}
```

Pending:

```text
tensor 21
```

Resolution finds:

```text
tensor 21
 ↓
ignored producer
 ↓
input tensor 20
 ↓
SLOT2
```

Then:

```python
tensor_to_slot = {
    10: 1,
    20: 2,
    21: 2,
}
```

---

# 71. Fourth stage: finding what remains

After resolution, the following is created:

```python
unmapped_after = []
```

---

# 72. New scan

All tensors are checked again.

Constants are skipped.

If a dynamic tensor is not in:

```python
tensor_to_slot
```

it is added to:

```python
unmapped_after
```

---

# 73. Difference between `pending_before_resolution` and `unmapped_after`

This difference is important.

### `pending_before_resolution`

Tensors not immediately resolved.

### `unmapped_after`

Tensors still without a slot after recursive resolution.

---

# 74. Example

Initially:

```python
pending_before_resolution = [
    21,
    22,
    30,
]
```

After the search:

```text
21 resolved
22 resolved
30 unresolved
```

Result:

```python
unmapped_after = [
    30
]
```

---

# 75. Why keep both?

They help answer different questions.

```text
pending_before_resolution
```

shows:

```text
which tensors needed indirect handling?
```

Whereas:

```text
unmapped_after
```

shows:

```text
which tensors remained problematic?
```

---

# 76. Return value of `build_tensor_slot_mapping()`

The function returns:

```python
{
    "tensor_to_slot": ...,
    "graph_inputs": ...,
    "mapped_from_layers": ...,
    "graph_input_mappings": ...,
    "pending_before_resolution": ...,
    "unmapped_after": ...,
}
```

---

# 77. Meaning of each field

| Field | Meaning |
| --------------------------- | ------------------------------------------------- |
| `tensor_to_slot` | Main tensor → slot mapping |
| `graph_inputs` | IDs of subgraph input tensors |
| `mapped_from_layers` | Tensors mapped directly from layers |
| `graph_input_mappings` | External inputs associated with SLOT0 |
| `pending_before_resolution` | Tensors initially without a mapping |
| `unmapped_after` | Tensors still without a slot after resolution |

---

# 78. Which structure is used in calculations?

The main one is:

```python
mapping["tensor_to_slot"]
```

The others mainly help with:

```text
tracking
diagnostics
reports
```

---

# 79. Complete example

Suppose:

```text
input tensor 0

L0 produces tensor 5 → SLOT0
L1 produces tensor 8 → SLOT1

ignored op receives tensor 8
and produces tensor 9

L2 receives tensor 9
and produces tensor 12 → SLOT2
```

---

# 80. Phase 1

Layer outputs:

```python
tensor_to_slot = {
    5: 0,
    8: 1,
    12: 2,
}
```

---

# 81. Phase 2

External input:

```python
tensor_to_slot = {
    0: 0,
    5: 0,
    8: 1,
    12: 2,
}
```

Tensor 9 goes into:

```python
pending_before_resolution = [
    9
]
```

---

# 82. Phase 3

Resolve tensor 9:

```text
tensor 9
 ↓
ignored producer
 ↓
input tensor 8
 ↓
tensor 8 → SLOT1
```

Then:

```python
tensor_to_slot[9] = 1
```

---

# 83. Result

```python
{
    0: 0,
    5: 0,
    8: 1,
    9: 1,
    12: 2,
}
```

And:

```python
unmapped_after = []
```

---

# 84. The `validate_tensor_slot_mapping()` function

Building the mapping is not enough.

The pipeline must ensure that every dynamic tensor actually used by graph operators has a slot.

The validation function starts at line 289 of the file and examines only operators belonging to the graph used by the extractor.

---

# 85. Signature

```python
def validate_tensor_slot_mapping(
    model,
    subgraph,
    *,
    tensor_to_slot,
    old_idx_to_label,
):
```

It returns:

```python
True
```

if all checks pass.

Otherwise it raises an exception.

---

# 86. Iterating over operators

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

Initially, all operators are visited.

There is an important filter, however.

---

# 87. Only useful operators

The code:

```python
if op_idx not in old_idx_to_label:
    continue
```

means:

```text
if the operator is not part of the logical graph,
it is not validated here
```

---

# 88. Why does this make sense?

Traversed or ignored operators may have tensors that do not receive their own slots.

Validation ensures that operations actually represented for execution have all the required dynamic inputs.

---

# 89. Retrieving the operator

For each useful operator:

```python
op = subgraph.Operators(
    op_idx
)
```

---

# 90. Validating inputs

The first part iterates over:

```python
op.InputsLength()
```

and retrieves each:

```python
tensor_id
```

---

# 91. Negative input

If:

```python
tensor_id < 0
```

is skipped.

---

# 92. Constant input

If:

```python
is_constant_tensor(...)
```

is true, it is also skipped.

This is because constants are accessed through the blocks:

```text
WEIGHTS
BIAS
```

rather than activation slots.

---

# 93. Dynamic input without a slot

If:

```python
tensor_id not in tensor_to_slot
```

the following is raised:

```python
RuntimeError
```

with a message such as:

```text
[MAP-ERROR] input tensor sem slot:
op_index=...
tensor_id=...
op=...
```

---

# 94. Why include `op_name()` in the message?

Just:

```text
op_index=37
```

may provide little information.

Adding:

```text
op=ADD
```

makes the problem easier to locate semantically.

---

# 95. Validating outputs

Next, the function iterates over:

```python
op.OutputsLength()
```

---

# 96. Negative output

Negative IDs are skipped.

---

# 97. Output without a slot

If:

```python
tensor_id not in tensor_to_slot
```

the following also occurs:

```python
RuntimeError
```

with:

```text
[MAP-ERROR] output tensor sem slot
```

---

# 98. Difference in input and output handling

For inputs, the code explicitly skips constants.

For outputs, there is no equivalent call to:

```python
is_constant_tensor()
```

The current behavior assumes that useful operator outputs relevant to execution must be mapped.

This is the actual implementation and should be considered when reading the code.

---

# 99. What does this validation guarantee?

It guarantees:

```text
for each useful operator:

every dynamic input has a slot

every valid output has a slot
```

---

# 100. What does it not guarantee?

On its own, it does not prove that:

```text
the selected slot is semantically correct
lifetimes were calculated perfectly
physical pointers do not overlap
quantization parameters are correct
```

These are responsibilities of other stages.

---

# 101. Example of a detected error

Consider:

```text
L10 ADD
inputs:
tensor 40
tensor 55
```

Mapping:

```python
tensor_to_slot = {
    40: 1
}
```

Tensor 55 is missing.

Validation raises an error before an incorrect `LayerParam` is created.

---

# 102. Importance of failing early

Without this validation, the error could appear much later:

```text
tensor without a slot
   ↓
invalid pointer
   ↓
incorrect LayerParam
   ↓
WAT generated
   ↓
WASM compiled
   ↓
incorrect inference
```

Validation turns this into:

```text
tensor without a slot
   ↓
immediate extractor error
```

---

# 103. The `tensor_mapping_to_text()` function

The last function converts the result to text.

It is exclusively for:

```text
report
debug
traceability
```

and does not participate in mapping logic.

---

# 104. Tensors mapped from layers

First, it lists:

```python
mapping[
    "mapped_from_layers"
]
```

Each entry generates something like:

```text
tensor 25 (produzido por L8) -> slot 2
```

---

# 105. Format benefit

This text records three identities at once:

```text
tensor 25
   ↓
L8
   ↓
slot 2
```

This makes it easier to check the relationship between TFLite, graph, and memory.

---

# 106. Subgraph inputs

Next, it lists:

```python
mapping[
    "graph_input_mappings"
]
```

Example:

```text
tensor 0 (input do subgrafo) -> slot 0
```

---

# 107. Initially pending tensors

The function retrieves:

```python
pending = mapping[
    "pending_before_resolution"
]
```

If there are entries:

```text
Tensores inicialmente pendentes:
  tensor 17
  tensor 31
```

---

# 108. Important: pending does not mean unresolved

A tensor in this section may have been resolved later.

This list represents its state **before** recursive closure.

---

# 109. Total mapped

Then:

```python
len(
    mapping[
        "tensor_to_slot"
    ]
)
```

is displayed.

Example:

```text
Total de tensores mapeados: 71
```

---

# 110. Still unresolved tensors

If:

```python
unmapped_after
```

is not empty:

```text
Tensores sem slot após fechamento: [...]
```

Otherwise:

```text
Fechamento de mapeamento:
nenhum tensor não-constante pendente.
```

---

# 111. Report versus validation

It is important to distinguish:

```text
tensor_mapping_to_text()
```

from:

```text
validate_tensor_slot_mapping()
```

The first only reports information.

The second actually stops the pipeline if a relevant inconsistency occurs.

---

# 112. Conceptual report example

```text
tensor 5 (produzido por L0) -> slot 0
tensor 8 (produzido por L1) -> slot 1
tensor 12 (produzido por L2) -> slot 2
tensor 15 (produzido por L3) -> slot 0

tensor 0 (input do subgrafo) -> slot 0

Tensores inicialmente pendentes:
  tensor 9
  tensor 10

Total de tensores mapeados: 7

Fechamento de mapeamento:
nenhum tensor não-constante pendente.
```

---

# 113. Relationship with `slots.py`

`slots.py` generates:

```text
layer → slot
```

Example:

```python
{
    "L4": 1,
    "L5": 2,
}
```

`tensor_mapping.py` transforms this into:

```text
tensor → slot
```

Example:

```python
{
    31: 1,
    37: 2,
}
```

---

# 114. Structural relationship

```text
L4
 │
 │ produces
 ▼
tensor 31
```

and:

```text
L4 → SLOT1
```

imply:

```text
tensor 31 → SLOT1
```

---

# 115. Why not use only layer → slot?

Because `layer_params.py` analyzes TFLite operators directly.

When it finds:

```python
input_ids = [...]
```

it needs to answer:

```text
which slot corresponds to tensor input_ids[0]?
```

It does not necessarily start with a layer label.

---

# 116. `ADD` example

A TFLite `ADD` may have:

```text
input tensor A = 42
input tensor B = 57
```

To build the operation in the runtime, we need:

```text
tensor 42 → SLOT1
tensor 57 → SLOT2
```

It is not enough to know in general that:

```text
L6 and L9
```

are its predecessors.

---

# 117. Relationship with physical pointers

After finding:

```text
tensor 42 → SLOT1
```

and:

```text
SLOT1_BASE = 703856
```

we can obtain:

```text
input_ptr = 703856
```

Therefore:

```text
tensor_id
   ↓
tensor_to_slot
   ↓
slot
   ↓
slot_bases
   ↓
physical address
```

---

# 118. Relationship to `layer_params.py`

This flow builds fields such as:

```text
in_slot
out_slot
pad_t
pad_b
input_ptrs
```

depending on the operation type.

Especially for:

```text
ADD
```

we need to know where both inputs are.

---

# 119. Complete `ADD` example

Suppose:

```text
L6 output
  ↓
tensor 50
  ↓
SLOT1
```

and:

```text
L9 output
  ↓
tensor 61
  ↓
SLOT2
```

The `ADD` operator has:

```text
inputs = [50, 61]
```

The mapping provides:

```python
tensor_to_slot[50] = 1
tensor_to_slot[61] = 2
```

Then:

```text
slot_bases[1] → input_ptr A
slot_bases[2] → input_ptr B
```

---

# 120. Constant tensors do not use slots

This is a fundamental architectural separation.

Activations:

```text
tensor → slot
```

Weights:

```text
tensor → offset in the weights blob
```

Bias:

```text
tensor → offset in the bias blob
```

Therefore:

```text
slot memory
```

and:

```text
parameter memory
```

are distinct systems.

---

# 121. CONV_2D example

A convolution may receive:

```text
input[0] = activation
input[1] = weights
input[2] = bias
```

Only:

```text
input[0]
```

needs a slot.

The others are constants and are skipped by:

```python
is_constant_tensor()
```

---

# 122. CONV flow

```text
activation tensor
     ↓
tensor_to_slot
     ↓
SLOT1
     ↓
in_ptr

weight tensor
     ↓
weight_tensor_off
     ↓
wptr

bias tensor
     ↓
bias_tensor_off
     ↓
bias_ptr
```

The three inputs are handled differently.

---

# 123. The module as a bridge

`tensor_mapping.py` can be viewed as the bridge between:

```text
graph representation
```

and:

```text
concrete TFLite representation
```

Because:

```text
slots.py knows Lx
```

while:

```text
TFLite knows tensor IDs
```

This module connects the two representations.

---

# 124. Difference from `producer_by_tensor`

It may seem that:

```python
producer_by_tensor
```

already solves everything.

It only provides:

```text
tensor → operator
```

What is still missing:

```text
operator → label
label → slot
```

Thus:

```text
producer_by_tensor
```

is just the first relationship in the chain.

---

# 125. Complete chain

```text
tensor_id
   │
   ▼
producer_by_tensor
   │
   ▼
op_index
   │
   ▼
old_idx_to_label
   │
   ▼
layer_name
   │
   ▼
layer_output_slot
   │
   ▼
slot
```

---

# 126. Reverse chain in the initial phase

For layer outputs, the code partly follows the reverse path:

```text
layer_name
   ↓
label_to_op_idx
   ↓
op_index
   ↓
op.Outputs(...)
   ↓
tensor_id
   ↓
associate output_slot
```

The module therefore works in both directions.

---

# 127. `old_idx_to_label` versus `label_to_op_idx`

These two maps are inverses.

### `old_idx_to_label`

```text
op_index → Lx
```

It is mainly used when resolving the producer.

### `label_to_op_idx`

```text
Lx → op_index
```

It is used when mapping layer outputs.

---

# 128. Why keep both?

Because it avoids linear searches.

Without `label_to_op_idx`, finding the operator for:

```text
L17
```

would require traversing the entire reverse dictionary.

With both maps:

```text
conversion in either direction is direct
```

---

# 129. Recursive cache

Another important detail is that:

```python
tensor_to_slot
```

is not just the final result.

It also acts as a cache during:

```python
resolve_slot_from_producer()
```

This means the structure is built incrementally.

---

# 130. Cache example

Resolve tensor 40:

```text
40
 ↓
39
 ↓
38
 ↓
SLOT2
```

During this process, the following may be added:

```python
tensor_to_slot[38] = 2
tensor_to_slot[39] = 2
tensor_to_slot[40] = 2
```

Later, resolving another tensor that depends on 39 finishes immediately.

---

# 131. Practical complexity

Recursive resolution may traverse producer chains.

Caching greatly reduces repetition.

The model used also has a relatively small number of operators and tensors.

The cost of this phase is therefore negligible compared with inference.

---

# 132. Limitation of recursive resolution

The algorithm's main conceptual assumption is:

```text
a tensor produced by an unrepresented operation
can inherit the slot of a dynamic input path
```

This makes sense for operations treated as transparent by the abstraction.

It is not a universally valid transformation for every operator.

---

# 133. Hypothetical problematic example

Suppose there is an ignored operator:

```text
A ─┐
   ├→ OP_X → C
B ─┘
```

with:

```text
A → SLOT1
B → SLOT2
```

If `OP_X` semantically combines A and B, there is not necessarily a correct answer such as:

```text
C → SLOT1
```

or:

```text
C → SLOT2
```

The current algorithm would nevertheless return the first resolved path.

---

# 134. Architectural consequence

Thus, `ignored_types` and this routine must remain consistent.

One should not simply add any operation to:

```text
ignored_types
```

without checking whether it can be traversed this way.

---

# 135. Transparent operation

An operator conceptually transparent to storage might be one that:

```text
does not require a new independent buffer
```

or whose output can be related to the same logical flow as an input.

This property must be analyzed for each operation type.

---

# 136. Why document this limitation?

Because the extractor may receive different models in the future.

If a new operator appears:

```text
TRANSPOSE
RESHAPE
CONCATENATION
SPLIT
```

we should not automatically assume the same recursive resolution is appropriate.

---

# 137. Relationship with portability

This separation is important to the project's broader objective.

TFLite describes the model using its own tensor and operator schema.

The WASM runtime uses:

```text
slots
pointers
LayerParams
```

The extractor must translate between these representations.

`tensor_mapping.py` is one stage in that translation.

---

# 138. Successive representations

```text
TFLite:

tensor 42
tensor 57
operator 18


graph:

L12
L15


slots:

L12 → SLOT1
L15 → SLOT2


tensor mapping:

tensor 42 → SLOT1
tensor 57 → SLOT2


runtime:

tensor 42 → SLOT1 address
tensor 57 → SLOT2 address
```

---

# 139. Separating logical slots and runtime slots

There is another important subsequent stage.

The mapping produced here is the:

```text
original logical slot
```

Later, `layer_params.py` creates a runtime mapping with a shift because of the synthetic layer:

```text
RGB565_TO_RGB888
```

Therefore:

```text
tensor_mapping.py
    ↓
logical slot

layer_params.py
    ↓
runtime slot
```

These concepts should not be confused.

---

# 140. Example

Here:

```text
tensor 10 → SLOT0
```

After runtime reorganization, it may end up in:

```text
runtime SLOT1
```

because the initial physical SLOT0 is reserved for the image received from the host.

This transformation belongs to the subsequent stage.

---

# 141. `graph_inputs`

The set:

```python
graph_inputs
```

is also returned because it will be reused to build the runtime mapping.

The subgraph therefore does not need to be queried again.

---

# 142. Why return additional metadata?

We could return only:

```python
tensor_to_slot
```

The additional fields provide traceability.

This is useful in a research project because it explains:

```text
how was that slot obtained?
```

---

# 143. Traceability example

For a tensor:

```text
tensor 73 → SLOT2
```

we can discover whether it was:

```text
mapped directly as an Lx output
```

or:

```text
resolved indirectly
```

Although the current report does not record every recursive step individually, the lists help identify the process.

---

# 144. Possible future development

A future version could record an explicit origin:

```python
{
    "tensor_id": 73,
    "slot": 2,
    "source": "recursive",
    "via_tensor": 71,
}
```

This would increase traceability.

It is not required for the current behavior.

---

# 145. Validation versus `unmapped_after`

An important detail:

```text
nonempty unmapped_after
```

does not necessarily mean execution will fail.

Final validation checks only tensors used by useful operators.

A nonconstant subgraph tensor may be irrelevant to the graph under consideration.

---

# 146. Therefore

```text
unmapped_after
```

is global information about the subgraph.

Whereas:

```text
validate_tensor_slot_mapping()
```

answers a more specific question:

```text
is every tensor needed by useful operations mapped?
```

---

# 147. Example

Suppose:

```python
unmapped_after = [
    99
]
```

But tensor 99 belongs only to an ignored operator that does not feed any useful operation.

Validation may still pass.

---

# 148. Why is this useful?

It avoids confusing:

```text
I have not mapped absolutely every tensor
```

with:

```text
I cannot execute the selected graph
```

These are different problems.

---

# 149. Expected invariants

After construction and validation, we expect:

### Known external inputs

```text
graph input → logical SLOT0
```

### Known useful operator outputs

```text
output tensor → layer slot
```

### Known dynamic inputs of useful operators

```text
every dynamic input → some slot
```

### Constants excluded

```text
weights/bias → independent of tensor_to_slot
```

---

# 150. Range invariant

The slots found must belong to the configured set:

```text
0 <= slot < NUM_SLOTS
```

This function does not explicitly check this condition because values come from the preceding allocation.

Validity therefore depends on `slots.py`.

---

# 151. Module dependencies

This stage demonstrates an important feature of the modular architecture:

```text
graph.py
```

provides producers and labels.

```text
slots.py
```

provides layer → slot.

```text
tensor_mapping.py
```

combines the two structures.

Each module has a different responsibility.

---

# 152. Possible error chain

If:

```text
graph.py gets the producer wrong
```

then:

```text
tensor_mapping.py may point to the wrong layer
```

If:

```text
slots.py gets the slot wrong
```

then:

```text
tensor_mapping.py propagates the incorrect slot
```

This stage therefore depends on the correctness of previous ones.

---

# 153. It also serves as a check

The function:

```python
validate_tensor_slot_mapping()
```

introduces a consistency check.

Before building execution parameters:

```text
all required tensors must have slots
```

This reduces the chance of silent errors.

---

# 154. What this module does not do

`tensor_mapping.py` does not:

```text
calculate slot addresses
calculate slot sizes
extract weights
extract bias
compute quantization
serialize LayerParam
generate WAT
```

It works exclusively with:

```text
tensor IDs
operator IDs
layer labels
logical slots
```

---

# 155. Why not calculate addresses here?

Because this would create a dependency on:

```text
params_base
SLOT_BYTES
ALIGN
slot_bases
```

These details belong to physical memory planning.

Here we only want:

```text
tensor 42 → slot 1
```

rather than:

```text
tensor 42 → address 703856
```

---

# 156. Logical/physical separation

```text
tensor_mapping.py
      ↓
tensor → SLOT1

memory.py
      ↓
SLOT1 → 703856

layer_params.py
      ↓
tensor → SLOT1 → 703856
```

This division reduces coupling.

---

# 157. Relationship with the next report

This stage's report file can be used to manually check:

```text
layer outputs
graph inputs
pending tensors
unresolved tensors
```

Before proceeding to:

```text
weights
quantization
memory
LayerParams
```

---

# 158. Direct resolution summary

```text
tensor
  ↓
producer
  ↓
useful op
  ↓
Lx
  ↓
layer slot
  ↓
tensor → slot
```

---

# 159. Indirect resolution summary

```text
tensor
  ↓
producer
  ↓
unrepresented op
  ↓
nonconstant input
  ↓
resolve recursively
  ↓
known slot
  ↓
tensor → same slot
```

---

# 160. Complete construction summary

```text
                  slot_allocation
                        │
                        ▼
          map layer outputs
                        │
                        ▼
                  tensor_to_slot
                        │
                        ▼
              map graph inputs
                        │
                        ▼
                 logical SLOT0
                        │
                        ▼
             find pending tensors
                        │
                        ▼
          recursive resolution by producer
                        │
                        ▼
                 closure
                        │
                        ▼
              list unmapped tensors
                        │
                        ▼
                  validation
```

---

# 161. Validation summary

```text
for each useful operator
       │
       ├── inputs
       │     │
       │     ├── constant → skip
       │     └── dynamic → needs a slot
       │
       └── outputs
             │
             └── need slots
```

---

# 162. Architectural summary

The project now has three levels of memory representation:

```text
LEVEL 1 — GRAPH

L6 → L9 → L10


LEVEL 2 — SLOT PER LAYER

L6  → SLOT1
L9  → SLOT2
L10 → SLOT0


LEVEL 3 — SLOT PER TENSOR

tensor 41 → SLOT1
tensor 52 → SLOT2
tensor 60 → SLOT0
```

Still missing:

```text
LEVEL 4 — PHYSICAL ADDRESS

SLOT0 → base X
SLOT1 → base Y
SLOT2 → base Z
```

This stage will be resolved later by memory planning.

---

# 163. Role in the complete pipeline

```text
┌──────────────────────────────┐
│          graph.py            │
│                              │
│ tensor → producer            │
│ op → Lx                      │
└──────────────┬───────────────┘
               │
               │
┌──────────────▼───────────────┐
│          slots.py            │
│                              │
│ Lx → slot                    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    tensor_mapping.py         │
│                              │
│ tensor → slot                │
│                              │
│ + recursive resolution       │
│ + validation                 │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      layer_params.py         │
│                              │
│ tensor → runtime slot        │
│ runtime slot → pointer       │
└──────────────────────────────┘
```

---

# 164. Summary

The central problem solved by `tensor_mapping.py` is the difference between how memory was planned and how the TFLite model references its data.

Planning works with:

```text
layers
```

TFLite works with:

```text
tensors
```

The following transformation is therefore needed:

```text
layer
   ↓
slot

tensor
   ↓
producer
   ↓
layer
   ↓
slot
```

For outputs directly linked to a useful layer, this association is simple.

For tensors produced by operations not directly represented, the module tries to preserve flow continuity by recursively following earlier producers.

Finally, validation ensures that all dynamic inputs and outputs required by operators actually used by the extractor have known slots before the pipeline proceeds.

The main output:

```python
tensor_to_slot
```

is therefore the essential connection between:

```text
TFLite structure
```

and:

```text
logical memory planning
```

and will later convert tensor IDs into runtime slots and ultimately into concrete addresses in the WebAssembly module's linear memory.
