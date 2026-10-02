[English](04-grafo.md) | [Português (Brasil)](04-grafo.pt-BR.md)

> **Preserved historical document.** This text describes an earlier architecture and retains useful technical examples. Paths, orchestration in main.py, the mandatory synthetic layer and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original technical examples are preserved.

# 04 — Building the operator graph (`graph.py`)

## 1. Module purpose

The extractor/graph.py file transforms TFLite SubGraph operators and tensors into an explicit representation of dependencies between operations.

The code described here is:

```python
from collections import defaultdict, deque
from extractor.tflite_utils import op_name


def build_graph_for_subgraph(model, subgraph):
    n_ops = subgraph.OperatorsLength()

    producer_by_tensor = {}
    consumers_by_tensor = defaultdict(list)
    op_types = []

    for op_idx in range(n_ops):
        op = subgraph.Operators(op_idx)

        op_type = op_name(model, op)
        op_types.append(op_type)

        # Registra qual operador produz cada tensor.
        for j in range(op.OutputsLength()):
            tensor_id = int(op.Outputs(j))

            if tensor_id >= 0:
                producer_by_tensor[tensor_id] = op_idx

        # Registra quais operadores consomem cada tensor.
        for j in range(op.InputsLength()):
            tensor_id = int(op.Inputs(j))

            if tensor_id >= 0:
                consumers_by_tensor[tensor_id].append(op_idx)

    return (
        op_types,
        producer_by_tensor,
        consumers_by_tensor,
    )


def compute_useful_adjacency(
    subgraph,
    op_types,
    consumers_by_tensor,
    ignored_types=None,
):
    if ignored_types is None:
        ignored_types = set()

    n_ops = subgraph.OperatorsLength()

    ignored = {
        op_idx
        for op_idx, op_type in enumerate(op_types)
        if op_type in ignored_types
    }

    useful = [
        op_idx
        for op_idx in range(n_ops)
        if op_idx not in ignored
    ]

    # Relações:
    #
    # operador -> operadores seguintes
    forward = defaultdict(set)

    for op_idx in range(n_ops):
        op = subgraph.Operators(op_idx)

        for j in range(op.OutputsLength()):
            tensor_id = int(op.Outputs(j))

            if tensor_id < 0:
                continue

            for consumer in consumers_by_tensor.get(
                tensor_id,
                [],
            ):
                if consumer != op_idx:
                    forward[op_idx].add(consumer)

    # Relações:
    #
    # operador -> operadores anteriores
    backward = defaultdict(set)

    for source, destinations in forward.items():
        for destination in destinations:
            backward[destination].add(source)

    def next_useful_from(op_idx):
        result = set()
        stack = [op_idx]
        seen = set()

        while stack:
            current = stack.pop()

            for next_op in forward.get(current, []):
                if next_op in seen:
                    continue

                seen.add(next_op)

                if next_op in ignored:
                    stack.append(next_op)
                else:
                    result.add(next_op)

        return result

    def prev_useful_to(op_idx):
        result = set()
        stack = [op_idx]
        seen = set()

        while stack:
            current = stack.pop()

            for previous_op in backward.get(current, []):
                if previous_op in seen:
                    continue

                seen.add(previous_op)

                if previous_op in ignored:
                    stack.append(previous_op)
                else:
                    result.add(previous_op)

        return result

    useful_inputs = {
        op_idx: prev_useful_to(op_idx)
        for op_idx in useful
    }

    useful_outputs = {
        op_idx: next_useful_from(op_idx)
        for op_idx in useful
    }

    return (
        useful,
        useful_inputs,
        useful_outputs,
    )


def topo_order(
    nodes,
    in_edges,
    out_edges,
):
    indegree = {
        node: len(in_edges[node])
        for node in nodes
    }

    queue = deque(
        sorted(
            node
            for node in nodes
            if indegree[node] == 0
        )
    )

    order = []

    while queue:
        current = queue.popleft()

        order.append(current)

        for destination in sorted(
            out_edges[current]
        ):
            indegree[destination] -= 1

            if indegree[destination] == 0:
                queue.append(destination)

    if len(order) != len(nodes):
        raise RuntimeError(
            "Grafo possui ciclo "
            "(inesperado para TFLite)."
        )

    return order


def build_layers(
    op_types,
    useful,
    useful_inputs,
    useful_outputs,
    order,
):
    """
    Cria a representação estruturada das camadas.

    Exemplo:

    {
        "type": "ADD",
        "name": "L10",
        "above": ["L6", "L9"],
        "below": ["L11"],
        "op_index": 10
    }
    """

    new_label = {
        old_idx: f"L{i}"
        for i, old_idx in enumerate(useful)
    }

    layers = []

    for old_idx in order:
        above = sorted(
            [
                new_label[producer]
                for producer
                in useful_inputs[old_idx]
                if producer in new_label
            ],
            key=lambda label: int(label[1:]),
        )

        below = sorted(
            [
                new_label[consumer]
                for consumer
                in useful_outputs[old_idx]
                if consumer in new_label
            ],
            key=lambda label: int(label[1:]),
        )

        layers.append(
            {
                "type": op_types[old_idx],
                "name": new_label[old_idx],
                "above": above,
                "below": below,
                "op_index": old_idx,
            }
        )

    return layers, new_label


def graph_to_text(layers):
    """
    Converte o grafo estruturado para a representação textual
    utilizada nos relatórios.
    """

    lines = [
        (
            "nome_da_camada; "
            "camada_atual; "
            "camada_acima; "
            "camada_de_baixo"
        )
    ]

    for layer in layers:
        above = (
            "["
            + ", ".join(layer["above"])
            + "]"
            if layer["above"]
            else "[]"
        )

        below = (
            "["
            + ", ".join(layer["below"])
            + "]"
            if layer["below"]
            else "[]"
        )

        lines.append(
            f"{layer['type']}; "
            f"{layer['name']}; "
            f"{above}; "
            f"{below}"
        )

    return "\n".join(lines)


def build_graph(
    model,
    subgraph,
    ignored_types=None,
):
    """
    Executa todo o processo de construção do grafo.

    Retorna tanto as estruturas utilizadas pelas próximas
    etapas quanto a representação textual para relatório.
    """

    (
        op_types,
        producer_by_tensor,
        consumers_by_tensor,
    ) = build_graph_for_subgraph(
        model,
        subgraph,
    )

    (
        useful,
        useful_inputs,
        useful_outputs,
    ) = compute_useful_adjacency(
        subgraph,
        op_types,
        consumers_by_tensor,
        ignored_types=ignored_types,
    )

    order = topo_order(
        useful,
        useful_inputs,
        useful_outputs,
    )

    layers, new_label = build_layers(
        op_types,
        useful,
        useful_inputs,
        useful_outputs,
        order,
    )

    data = graph_to_text(layers)

    old_idx_to_label = {
        old_idx: label
        for old_idx, label
        in new_label.items()
    }

    label_to_op_idx = {
        label: old_idx
        for old_idx, label
        in new_label.items()
    }

    return {
        "op_types": op_types,

        "producer_by_tensor": (
            producer_by_tensor
        ),

        "consumers_by_tensor": (
            consumers_by_tensor
        ),

        "useful": useful,
        "useful_inputs": useful_inputs,
        "useful_outputs": useful_outputs,

        "order": order,

        "new_label": new_label,
        "old_idx_to_label": old_idx_to_label,
        "label_to_op_idx": label_to_op_idx,

        "layers": layers,

        # Somente para relatório/debug.
        "data": data,
    }
```

---

# 2. Architectural role

TFLite provides operators and tensors, but the rest of the extractor needs to answer questions such as:

```text
which layer produces the data this layer uses?

which layers depend on this layer's output?

will an output still be needed later?

when can a slot be reused?

what are the two inputs of an ADD?

what is a valid execution order?
```

graph.py builds the structures needed to answer these questions.

Conceptually:

```text
TFLite SubGraph
      │
      ├── Operators
      └── Tensors
             │
             ▼
          graph.py
             │
             ├── producers
             ├── consumers
             ├── dependencies
             ├── topological order
             └── layers
                     │
                     ▼
              subsequent modules
```

---

# 3. The graph is not built directly between tensors

The final representation used by the extractor is primarily an **operator graph**.

In TFLite, the original relationship passes through tensors:

```text
Operator A
    │
    │ produces
    ▼
Tensor 10
    │
    │ consumed by
    ▼
Operator B
```

The module converts that structure into:

```text
Operator A
    │
    ▼
Operator B
```

Tensors therefore provide the information needed to discover operation dependencies.

---

# 4. Simple example

Consider three operations:

```text
Op 0: CONV_2D
   ↓ tensor 4

Op 1: DEPTHWISE_CONV_2D
   ↓ tensor 7

Op 2: CONV_2D
```

TFLite describes:

```text
Op0 output = tensor 4
Op1 input  = tensor 4

Op1 output = tensor 7
Op2 input  = tensor 7
```

The logical graph becomes:

```text
Op0
 ↓
Op1
 ↓
Op2
```

Later:

```text
L0
 ↓
L1
 ↓
L2
```

---

# 5. Imports

The module starts with:

```python
from collections import defaultdict, deque
```

and:

```python
from extractor.tflite_utils import op_name
```

Each has a different role.

---

# 6. defaultdict

defaultdict builds collections where missing keys automatically receive an initial value.

Example:

```python
consumers_by_tensor = defaultdict(list)
```

Thus:

```python
consumers_by_tensor[10].append(3)
```

works even when:

```text
tensor 10
```

has not yet appeared in the dictionary.

The initial value is:

```python
[]
```

---

# 7. Using defaultdict(set)

Later:

```python
forward = defaultdict(set)
```

and:

```python
backward = defaultdict(set)
```

use sets.

The same relationship between two operators only needs to appear once.

For example:

```python
forward[3].add(5)
```

executed twice still gives:

```python
{5}
```

rather than:

```python
[5, 5]
```

---

# 8. deque

The structure:

```python
deque
```

is used in:

```python
topo_order()
```

to hold the queue of operators with no remaining dependencies.

The operations:

```python
queue.append(...)
queue.popleft()
```

are suitable for implementing a FIFO queue.

---

# 9. op_name()

The function:

```python
op_name(model, op)
```

comes from:

```text
tflite_utils.py
```

and converts TFLite's internal code into a name such as:

```text
CONV_2D
DEPTHWISE_CONV_2D
ADD
MEAN
SOFTMAX
QUANTIZE
```

This lets graph.py use readable names.

---

# 10. First phase: build_graph_for_subgraph()

The first function is:

```python
def build_graph_for_subgraph(
    model,
    subgraph,
):
```

It scans every operator in the subgraph.

Its purpose is to discover three structures:

```text
op_types

producer_by_tensor

consumers_by_tensor
```

---

# 11. Operator count

The first line is:

```python
n_ops = subgraph.OperatorsLength()
```

For a model containing, for example:

```text
67 TFLite operators
```

we get:

```python
n_ops = 67
```

The indices are:

```text
0
1
2
...
66
```

---

# 12. Initial structures

The following are created:

```python
producer_by_tensor = {}
```

```python
consumers_by_tensor = defaultdict(list)
```

```python
op_types = []
```

Each answers a different question.

---

# 13. op_types

This list maps:

```text
operator index
        ↓
operator type
```

For example:

```python
op_types = [
    "QUANTIZE",
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "CONV_2D",
    "ADD",
]
```

Thus:

```python
op_types[3]
```

returns:

```text
CONV_2D
```

---

# 14. Scanning operators

The main loop is:

```python
for op_idx in range(n_ops):
    op = subgraph.Operators(
        op_idx
    )
```

For each position:

```text
0
1
2
...
n_ops - 1
```

the corresponding operator is retrieved.

---

# 15. Identifying the type

Then:

```python
op_type = op_name(
    model,
    op
)
```

and:

```python
op_types.append(
    op_type
)
```

The list position therefore matches the operation's original TFLite index.

---

# 16. Identifying producers

The code:

```python
for j in range(
    op.OutputsLength()
):
```

visits every tensor produced by the operator.

Each output is retrieved with:

```python
tensor_id = int(
    op.Outputs(j)
)
```

---

# 17. producer_by_tensor

If:

```python
tensor_id >= 0
```

the following is stored:

```python
producer_by_tensor[
    tensor_id
] = op_idx
```

This creates relationships such as:

```text
tensor 10 → op 3
tensor 11 → op 4
tensor 15 → op 7
```

Or:

```python
{
    10: 3,
    11: 4,
    15: 7,
}
```

The interpretation is:

```text
tensor 10 was produced by operator 3
```

---

# 18. Why is a plain dictionary sufficient?

The structure assumes each tensor has one producer.

This matches the nature of the data flow:

```text
an intermediate tensor
        ↓
is the result of a particular operation
```

Therefore:

```python
tensor_id → op_idx
```

is sufficient.

---

# 19. Identifying consumers

The inputs are then traversed:

```python
for j in range(
    op.InputsLength()
):
```

Each tensor is retrieved with:

```python
tensor_id = int(
    op.Inputs(j)
)
```

For valid IDs:

```python
consumers_by_tensor[
    tensor_id
].append(
    op_idx
)
```

---

# 20. Why are consumers a list?

The same output can be consumed by several operations.

Example:

```text
               ┌──→ Op B
Op A → tensor X
               └──→ Op C
```

Then:

```python
consumers_by_tensor[X]
```

can be:

```python
[B, C]
```

This is why the code does not use:

```python
tensor → single consumer
```

but:

```python
tensor → list of consumers
```

---

# 21. Producer/consumer example

Consider:

```text
Op 0
 │
 └── tensor 5
       │
       ├──→ Op 1
       └──→ Op 3
```

The structures are:

```python
producer_by_tensor = {
    5: 0
}
```

and:

```python
consumers_by_tensor = {
    5: [1, 3]
}
```

---

# 22. Negative IDs

The code checks:

```python
if tensor_id >= 0:
```

for both inputs and outputs.

This prevents negative identifiers from being treated as real tensor indices.

Therefore:

```text
tensor_id < 0
```

is ignored when building relationships.

---

# 23. First-phase return value

The function returns:

```python
return (
    op_types,
    producer_by_tensor,
    consumers_by_tensor,
)
```

At this point there is no:

```text
L0
L1
L2
```

or topological ordering yet.

There is only a structural mapping of the original subgraph.

---

# 24. First representation

After build_graph_for_subgraph(), conceptually we have:

```text
                   tensor 5
                  /        \
                 /          \
             produces       consumes
               /              \
            Op 0              Op 1
```

Converted into structures:

```text
producer_by_tensor[5] = 0

consumers_by_tensor[5] = [1]
```

---

# 25. Second phase: compute_useful_adjacency()

The function:

```python
def compute_useful_adjacency(
    subgraph,
    op_types,
    consumers_by_tensor,
    ignored_types=None,
):
```

turns tensor-mediated relationships into direct operator relationships.

It also supports ignoring selected operation types without breaking the logical graph.

---

# 26. ignored_types

The parameter:

```python
ignored_types=None
```

specifies operator types excluded from the final useful graph's nodes.

When omitted:

```python
if ignored_types is None:
    ignored_types = set()
```

Thus, by default:

```text
no operations are ignored
```

---

# 27. Why use set()?

A set is suitable for checks such as:

```python
if op_type in ignored_types:
```

Example:

```python
ignored_types = {
    "RESHAPE",
    "IDENTITY",
}
```

The lookup is direct:

```text
"RESHAPE" ∈ ignored_types?
```

---

# 28. Identifying ignored operators

The code:

```python
ignored = {
    op_idx
    for op_idx, op_type
    in enumerate(op_types)
    if op_type in ignored_types
}
```

converts:

```text
ignored types
```

into:

```text
actual indices of ignored operators
```

Example:

```python
op_types = [
    "CONV_2D",
    "RESHAPE",
    "ADD",
]
```

and:

```python
ignored_types = {
    "RESHAPE"
}
```

give:

```python
ignored = {
    1
}
```

---

# 29. Useful operators

Then:

```python
useful = [
    op_idx
    for op_idx in range(n_ops)
    if op_idx not in ignored
]
```

In this example:

```text
op 0 = useful
op 1 = ignored
op 2 = useful
```

Therefore:

```python
useful = [
    0,
    2,
]
```

---

# 30. Ignoring does not mean simply deleting

If we took:

```text
Op 0 → Op 1 → Op 2
```

and removed:

```text
Op 1
```

the naive result would be:

```text
Op 0

Op 2
```

with no relationship.

However, the logical dependency should remain:

```text
Op 0 → Op 2
```

The function solves precisely this problem.

---

# 31. Building forward

The structure:

```python
forward = defaultdict(set)
```

represents:

```text
operator
    ↓
directly connected next operators
```

---

# 32. Traversing outputs

For each operator:

```python
for op_idx in range(n_ops):
```

the code traverses:

```python
op.OutputsLength()
```

Each output provides:

```python
tensor_id
```

---

# 33. Finding consumers

For each produced tensor:

```python
for consumer in (
    consumers_by_tensor.get(
        tensor_id,
        [],
    )
):
```

all operators consuming it are found.

---

# 34. Creating an edge

If:

```python
consumer != op_idx
```

the code adds:

```python
forward[
    op_idx
].add(
    consumer
)
```

In other words:

```text
op_idx → consumer
```

---

# 35. forward example

Suppose:

```text
Op 2 produces tensor 11
Op 4 consumes tensor 11
```

We get:

```python
forward[2] = {
    4
}
```

If Op2 feeds two operators:

```text
       ┌──→ Op 4
Op 2 ──┤
       └──→ Op 7
```

we get:

```python
forward[2] = {
    4,
    7,
}
```

---

# 36. Why a set?

Two different tensors may create a relationship between the same operators.

For topology, it is enough to record:

```text
Op A depends on Op B
```

once.

The set removes duplication.

---

# 37. backward structure

Next:

```python
backward = defaultdict(set)
```

is built by reversing all edges.

The code is:

```python
for source, destinations in (
    forward.items()
):
    for destination in destinations:
        backward[
            destination
        ].add(
            source
        )
```

---

# 38. forward versus backward

If:

```text
Op 3 → Op 8
```

we have:

```python
forward[3] = {
    8
}
```

and:

```python
backward[8] = {
    3
}
```

Therefore:

```text
forward
   asks:
   "who comes next?"

backward
   asks:
   "who comes before?"
```

---

# 39. Why both directions?

Later we want to build:

```text
above
below
```

for each layer.

For example:

```text
       L3
       ↓
       L5
       ↓
       L8
```

For L5:

```text
above = [L3]
below = [L8]
```

A single direction would be less convenient.

---

# 40. next_useful_from()

This inner function is:

```python
def next_useful_from(op_idx):
```

It finds the next **useful** operators, automatically traversing ignored operators.

---

# 41. Internal search structures

The following are created:

```python
result = set()
```

```python
stack = [
    op_idx
]
```

```python
seen = set()
```

Each has a role.

### `result`

Stores the next useful operators found.

### `stack`

Tracks nodes still to visit.

### `seen`

Prevents repeatedly visiting the same operator.

---

# 42. Search strategy

The code uses:

```python
current = stack.pop()
```

The structure therefore behaves as a stack.

Conceptually, this is depth-first traversal.

---

# 43. Next operators

For each current operator:

```python
for next_op in forward.get(
    current,
    [],
):
```

its logical outputs are examined.

---

# 44. Avoiding repeated visits

The code:

```python
if next_op in seen:
    continue
```

prevents reprocessing a previously encountered node.

Then:

```python
seen.add(
    next_op
)
```

records the visit.

---

# 45. Ignored operator

The key point is:

```python
if next_op in ignored:
    stack.append(
        next_op
    )
```

In other words:

```text
found an ignored operator
            ↓
do not add it to the result
            ↓
continue searching beyond it
```

---

# 46. Useful operator

Otherwise:

```python
else:
    result.add(
        next_op
    )
```

Search stops along that path as soon as the next useful operator is found.

---

# 47. Example without ignored operators

```text
Op0 → Op1 → Op2
```

If all are useful:

```python
next_useful_from(0)
```

returns:

```python
{1}
```

It does not return:

```python
{1, 2}
```

because Op1 is already the next useful node.

---

# 48. Example with an ignored operator

Consider:

```text
Op0 → Op1 → Op2
```

where:

```text
Op1 = ignored
```

Then:

```python
next_useful_from(0)
```

performs:

```text
Op0
 ↓
Op1 ignored
 ↓
continue search
 ↓
Op2 useful
```

Result:

```python
{2}
```

The useful relationship becomes:

```text
Op0 → Op2
```

---

# 49. A chain of ignored operators

This also works with:

```text
Op0
 ↓
Op1 ignored
 ↓
Op2 ignored
 ↓
Op3 ignored
 ↓
Op4 useful
```

Result:

```text
Op0 → Op4
```

---

# 50. Branches

Consider:

```text
            ┌→ Op2 ignored → Op4
Op0 → Op1 ──┤
            └→ Op3 ignored → Op5
```

The function can return:

```python
{
    4,
    5,
}
```

preserving branches.

---

# 51. prev_useful_to()

The second inner function:

```python
def prev_useful_to(op_idx):
```

performs the same operation in the opposite direction.

It uses:

```python
backward
```

instead of:

```python
forward
```

---

# 52. Purpose

The question answered is:

```text
which useful operators immediately precede this one?
```

while traversing ignored operators.

---

# 53. Example

```text
Op0 useful
 ↓
Op1 ignored
 ↓
Op2 useful
```

Then:

```python
prev_useful_to(2)
```

returns:

```python
{0}
```

---

# 54. Final useful relationships

The following are then built:

```python
useful_inputs = {
    op_idx: prev_useful_to(
        op_idx
    )
    for op_idx in useful
}
```

and:

```python
useful_outputs = {
    op_idx: next_useful_from(
        op_idx
    )
    for op_idx in useful
}
```

---

# 55. Meaning of useful_inputs

For an operation:

```text
Op 10
```

we could have:

```python
useful_inputs[10] = {
    6,
    9,
}
```

This means:

```text
Op6 ─┐
     ├→ Op10
Op9 ─┘
```

This occurs, for example, in operations with multiple inputs such as ADD.

---

# 56. Meaning of useful_outputs

We could have:

```python
useful_outputs[10] = {
    11,
    15,
}
```

Representing:

```text
          ┌→ Op11
Op10 ─────┤
          └→ Op15
```

---

# 57. Second-phase return value

The function returns:

```python
return (
    useful,
    useful_inputs,
    useful_outputs,
)
```

The graph now directly represents relationships between useful operators.

---

# 58. Before and after normalization

Before:

```text
Op A
 ↓
Tensor X
 ↓
Op B
 ↓
Tensor Y
 ↓
Op C
```

After:

```text
Op A
 ↓
Op B
 ↓
Op C
```

With ignored operators:

```text
BEFORE

Op A
 ↓
Tensor X
 ↓
Op B ignored
 ↓
Tensor Y
 ↓
Op C


AFTER

Op A
 ↓
Op C
```

---

# 59. Third phase: topological ordering

The function:

```python
def topo_order(
    nodes,
    in_edges,
    out_edges,
):
```

computes a valid graph-processing order.

---

# 60. What is topological ordering?

In a directed acyclic graph, topological ordering guarantees:

```text
if A must execute before B

A appears before B
```

Example:

```text
L0
 ↓
L1
 ↓
L2
```

Valid order:

```text
L0, L1, L2
```

Invalid order:

```text
L2, L0, L1
```

because L2 depends on earlier data.

---

# 61. Branching example

```text
       L0
      /  \
     ↓    ↓
    L1    L2
      \  /
       ↓
       L3
```

One possible order is:

```text
L0
L1
L2
L3
```

Another is:

```text
L0
L2
L1
L3
```

because L1 and L2 are independent of each other.

---

# 62. indegree

The algorithm starts by computing:

```python
indegree = {
    node: len(
        in_edges[node]
    )
    for node in nodes
}
```

Indegree represents:

```text
number of predecessors still awaiting processing
```

---

# 63. Indegree example

For the graph:

```text
       A
      / \
     ↓   ↓
     B   C
      \ /
       ↓
       D
```

we have:

```text
A = 0
B = 1
C = 1
D = 2
```

---

# 64. Initial queue

The code:

```python
queue = deque(
    sorted(
        node
        for node in nodes
        if indegree[node] == 0
    )
)
```

initially queues only nodes with no predecessors.

In this example:

```text
queue = [A]
```

---

# 65. Why sorted()?

Several nodes may have no dependencies.

Using:

```python
sorted(...)
```

makes behavior deterministic.

Otherwise, ordering could vary with the internal order of sets or dictionaries.

---

# 66. Processing the queue

The main loop:

```python
while queue:
```

removes:

```python
current = queue.popleft()
```

and adds:

```python
order.append(current)
```

---

# 67. Releasing dependencies

For each successor:

```python
for destination in sorted(
    out_edges[current]
):
```

the following is decremented:

```python
indegree[
    destination
] -= 1
```

This represents:

```text
one dependency of this node has been resolved
```

---

# 68. When does a node enter the queue?

When:

```python
indegree[
    destination
] == 0
```

it can execute.

Then:

```python
queue.append(
    destination
)
```

---

# 69. Step-by-step example

Consider:

```text
A → B
A → C
B → D
C → D
```

Initially:

```text
A=0
B=1
C=1
D=2
```

Queue:

```text
[A]
```

Process A:

```text
B=0
C=0
```

Queue:

```text
[B,C]
```

Process B:

```text
D=1
```

Process C:

```text
D=0
```

D enters the queue.

Result:

```text
A,B,C,D
```

---

# 70. Cycle detection

After the algorithm:

```python
if len(order) != len(nodes):
```

means some node never reached indegree zero.

This indicates a cycle.

Example:

```text
A → B
↑   ↓
└── C
```

There is no valid topological ordering in this case.

---

# 71. Exception

The code raises:

```python
raise RuntimeError(
    "Grafo possui ciclo "
    "(inesperado para TFLite)."
)
```

The intention is to fail early.

The remaining extractor assumes an acyclic flow of operations.

---

# 72. Fourth phase: build_layers()

After discovering dependencies and order, the module creates a more convenient representation for the rest of the pipeline.

The function is:

```python
def build_layers(
    op_types,
    useful,
    useful_inputs,
    useful_outputs,
    order,
):
```

---

# 73. Purpose of build_layers()

It converts:

```text
TFLite operator indices
```

into structures such as:

```python
{
    "type": "ADD",
    "name": "L10",
    "above": ["L6", "L9"],
    "below": ["L11"],
    "op_index": 10,
}
```

---

# 74. Difference between op_index and name

This distinction is fundamental.

op_index is the original operator index in the TFLite file.

Example:

```text
op_index = 37
```

By contrast:

```text
name = "L34"
```

is an extractor-created identifier for the logical representation.

Therefore:

```text
op_index
    ↓
original TFLite identity

name
    ↓
identity used by the extractor graph
```

---

# 75. Creating new_label

The code:

```python
new_label = {
    old_idx: f"L{i}"
    for i, old_idx
    in enumerate(useful)
}
```

creates the mapping:

```text
TFLite index → logical label
```

Example:

```python
useful = [
    0,
    1,
    3,
    4,
]
```

Then:

```python
new_label = {
    0: "L0",
    1: "L1",
    3: "L2",
    4: "L3",
}
```

---

# 76. Why renumber?

Ignoring some operations can leave gaps in TFLite indices:

```text
0
1
3
4
7
```

The logical representation can become:

```text
L0
L1
L2
L3
L4
```

This makes reports and subsequent structures more compact.

---

# 77. An important numbering detail

Labels are created with:

```python
enumerate(useful)
```

rather than:

```python
enumerate(order)
```

This means names:

```text
L0
L1
L2
...
```

follow the order of original useful TFLite indices.

Meanwhile:

```python
layers
```

is built by traversing:

```python
order
```

in topological order.

For most models whose original operator order already follows the graph, these orders coincide.

Conceptually, however, they differ:

```text
label
    ↓
based on the useful list

position in layers
    ↓
based on order
```

Keep that distinction when interpreting the code.

---

# 78. Building layers

The code creates:

```python
layers = []
```

Then:

```python
for old_idx in order:
```

each useful operation is processed in topological order.

---

# 79. Building above

The code:

```python
above = sorted(
    [
        new_label[producer]
        for producer
        in useful_inputs[old_idx]
        if producer in new_label
    ],
    key=lambda label:
        int(label[1:]),
)
```

converts predecessors from:

```text
TFLite index
```

to:

```text
labels Lx
```

---

# 80. above example

Suppose:

```python
useful_inputs[10] = {
    6,
    9,
}
```

and:

```python
new_label = {
    6: "L6",
    9: "L9",
    10: "L10",
}
```

Then:

```python
above = [
    "L6",
    "L9",
]
```

---

# 81. Why sort numerically?

Ordinary text sorting could produce:

```text
L1
L10
L11
L2
```

because strings are compared character by character.

The code therefore uses:

```python
key=lambda label:
    int(label[1:])
```

For:

```text
L10
```

we have:

```python
label[1:]
```

equal to:

```text
"10"
```

and:

```python
int("10")
```

equal to:

```text
10
```

The ordering is therefore numeric.

---

# 82. Building below

The same process applies to consumers:

```python
below = sorted(
    [
        new_label[consumer]
        for consumer
        in useful_outputs[old_idx]
        if consumer in new_label
    ],
    key=lambda label:
        int(label[1:]),
)
```

Example:

```text
L10
 ├→ L11
 └→ L15
```

produces:

```python
below = [
    "L11",
    "L15",
]
```

---

# 83. Layer structure

Then:

```python
layers.append(
    {
        "type": op_types[
            old_idx
        ],
        "name": new_label[
            old_idx
        ],
        "above": above,
        "below": below,
        "op_index": old_idx,
    }
)
```

Each entry has five properties.

---

# 84. type field

Example:

```python
"type": "CONV_2D"
```

Identifies the TFLite operation type.

---

# 85. name field

Example:

```python
"name": "L15"
```

The logical identifier created by the extractor.

---

# 86. above field

Example:

```python
"above": [
    "L12",
    "L14",
]
```

Lists the layers on which this operation directly depends.

---

# 87. below field

Example:

```python
"below": [
    "L16",
]
```

Lists operations that directly depend on the current output.

---

# 88. op_index field

Example:

```python
"op_index": 18
```

Preserves the link to the original TFLite operator.

Later stages need to return to:

```python
subgraph.Operators(
    op_index
)
```

to extract actual parameters.

---

# 89. Residual block example

A structure such as:

```text
L5 ───────────────┐
 ↓                │
L6                │
 ↓                │
L7                │
 ↓                │
L8 ───────────────┤
                  ↓
                 L9 ADD
```

can produce the following for L9:

```python
{
    "type": "ADD",
    "name": "L9",
    "above": [
        "L5",
        "L8",
    ],
    "below": [
        "L10",
    ],
    "op_index": ...,
}
```

This information is especially important for memory allocation.

---

# 90. build_layers() return value

The function returns:

```python
return (
    layers,
    new_label,
)
```

Both the full representation and index conversion table are retained.

---

# 91. Fifth phase: graph_to_text()

The function:

```python
def graph_to_text(
    layers
):
```

does not participate in subsequent calculations.

It turns the structure into readable report text.

This separation matters.

---

# 92. Structure versus report

The pipeline uses:

```python
layers
```

for calculations.

Meanwhile:

```python
graph_to_text(
    layers
)
```

only produces a textual view.

Therefore:

```text
layers
    ↓
structured source

data
    ↓
human-readable representation
```

The code does not read the report again to reconstruct the graph.

---

# 93. Header

The report starts with:

```text
nome_da_camada; camada_atual; camada_acima; camada_de_baixo
```

Despite the historical name nome_da_camada, the first field currently corresponds to:

```python
layer["type"]
```

such as:

```text
CONV_2D
ADD
SOFTMAX
```

---

# 94. Converting above

If predecessors exist:

```python
[
    "L5",
    "L8",
]
```

the text is:

```text
[L5, L8]
```

If none exist:

```text
[]
```

---

# 95. Converting below

The same applies to outputs:

```text
[L10]
```

or:

```text
[]
```

---

# 96. Final line

The line is built as:

```python
f"{layer['type']}; "
f"{layer['name']}; "
f"{above}; "
f"{below}"
```

Example:

```text
ADD; L9; [L5, L8]; [L10]
```

---

# 97. Report example

We could have:

```text
nome_da_camada; camada_atual; camada_acima; camada_de_baixo
QUANTIZE; L0; []; [L1]
CONV_2D; L1; [L0]; [L2]
DEPTHWISE_CONV_2D; L2; [L1]; [L3]
CONV_2D; L3; [L2]; [L4, L6]
ADD; L6; [L3, L5]; [L7]
```

This representation is useful for human inspection.

---

# 98. Sixth phase: build_graph()

The function:

```python
def build_graph(
    model,
    subgraph,
    ignored_types=None,
):
```

is the public entry point coordinating all previous stages.

It keeps main.py from needing to know their internal details.

---

# 99. Orchestration

The internal flow is:

```text
build_graph_for_subgraph()
          │
          ▼
compute_useful_adjacency()
          │
          ▼
topo_order()
          │
          ▼
build_layers()
          │
          ▼
graph_to_text()
```

---

# 100. First call

```python
(
    op_types,
    producer_by_tensor,
    consumers_by_tensor,
) = build_graph_for_subgraph(
    model,
    subgraph,
)
```

Result:

```text
operators + relationships through tensors
```

---

# 101. Second call

```python
(
    useful,
    useful_inputs,
    useful_outputs,
) = compute_useful_adjacency(...)
```

Result:

```text
logical graph of useful operators
```

---

# 102. Third call

```python
order = topo_order(...)
```

Result:

```text
valid processing order
```

---

# 103. Fourth call

```python
layers, new_label = (
    build_layers(...)
)
```

Result:

```text
Lx layer structure
```

---

# 104. Fifth call

```python
data = graph_to_text(
    layers
)
```

Result:

```text
report representation
```

---

# 105. old_idx_to_label

Next, the code creates:

```python
old_idx_to_label = {
    old_idx: label
    for old_idx, label
    in new_label.items()
}
```

In practice, it has the same direction as:

```python
new_label
```

In other words:

```text
original index → label
```

---

# 106. Example

```python
old_idx_to_label = {
    0: "L0",
    1: "L1",
    3: "L2",
}
```

This allows:

```python
old_idx_to_label[3]
```

to retrieve:

```text
L2
```

---

# 107. label_to_op_idx

Next, the inverse relationship is built:

```python
label_to_op_idx = {
    label: old_idx
    for old_idx, label
    in new_label.items()
}
```

Example:

```python
{
    "L0": 0,
    "L1": 1,
    "L2": 3,
}
```

Now:

```python
label_to_op_idx[
    "L2"
]
```

returns:

```text
3
```

---

# 108. Why keep both directions?

Different modules use different identifiers.

Some structures work with:

```text
L17
```

while the TFLite API requires:

```text
op_index
```

Thus:

```text
L17
 ↓
label_to_op_idx
 ↓
op_index
 ↓
subgraph.Operators(op_index)
```

In the reverse direction:

```text
op_index
 ↓
old_idx_to_label
 ↓
L17
```

---

# 109. Final dictionary

build_graph() returns:

```python
{
    "op_types": ...,
    "producer_by_tensor": ...,
    "consumers_by_tensor": ...,
    "useful": ...,
    "useful_inputs": ...,
    "useful_outputs": ...,
    "order": ...,
    "new_label": ...,
    "old_idx_to_label": ...,
    "label_to_op_idx": ...,
    "layers": ...,
    "data": ...,
}
```

This provides a single interface for subsequent modules.

---

# 110. Meaning of each item

| Field | Meaning |
| --------------------- | ------------------------------------ |
| op_types | Type of each TFLite operator |
| producer_by_tensor | Operator producing each tensor |
| consumers_by_tensor | Operators consuming each tensor |
| useful | Indices of non-ignored operators |
| useful_inputs | Useful predecessors of each operator |
| useful_outputs | Useful successors of each operator |
| order | Topological ordering |
| new_label | op_index → Lx mapping |
| old_idx_to_label | Explicit op_index → Lx mapping |
| label_to_op_idx | Lx → op_index mapping |
| layers | Structured graph representation |
| data | Text representation for reporting |

---

# 111. producer_by_tensor remains important

Although compute_useful_adjacency() builds forward primarily using:

```python
consumers_by_tensor
```

the map:

```python
producer_by_tensor
```

is still retained.

It provides structural information to stages that need to answer:

```text
who produced this tensor?
```

This differs from asking:

```text
who consumes this tensor?
```

---

# 112. Complete transformation example

Imagine:

```text
Op0: QUANTIZE
 output tensor 10

Op1: CONV_2D
 input tensor 10
 output tensor 11

Op2: DEPTHWISE_CONV_2D
 input tensor 11
 output tensor 12

Op3: CONV_2D
 input tensor 12
 output tensor 13

Op4: ADD
 inputs tensor 13 and tensor 11
 output tensor 14
```

---

# 113. Producers

```python
producer_by_tensor = {
    10: 0,
    11: 1,
    12: 2,
    13: 3,
    14: 4,
}
```

---

# 114. Consumers

```python
consumers_by_tensor = {
    10: [1],
    11: [2, 4],
    12: [3],
    13: [4],
}
```

---

# 115. Derived graph

```text
Op0
 ↓
Op1
 ├───────┐
 ↓       │
Op2      │
 ↓       │
Op3      │
 └──┐    │
    ↓    ↓
      Op4
```

---

# 116. Useful relationships

For Op4:

```python
useful_inputs[4] = {
    1,
    3,
}
```

For Op1:

```python
useful_outputs[1] = {
    2,
    4,
}
```

---

# 117. Layers

The representation can become:

```python
[
    {
        "type": "QUANTIZE",
        "name": "L0",
        "above": [],
        "below": ["L1"],
        "op_index": 0,
    },

    {
        "type": "CONV_2D",
        "name": "L1",
        "above": ["L0"],
        "below": ["L2", "L4"],
        "op_index": 1,
    },

    ...

    {
        "type": "ADD",
        "name": "L4",
        "above": ["L1", "L3"],
        "below": [],
        "op_index": 4,
    },
]
```

---

# 118. Why the graph matters for memory

Slot allocation cannot simply alternate:

```text
slot0
slot1
slot0
slot1
```

because an older output may still be needed later.

In this example:

```text
L1
 ├──→ L2 → L3
 └────────→ L4
```

L1's output must remain available until L4.

The graph therefore describes the logical lifetime of that result.

---

# 119. Risk example

A naive strategy might:

```text
L1 output → SLOT1
L2 output → SLOT2
L3 output → SLOT1
```

But that would destroy L1's result before the ADD in L4.

The graph lets us detect:

```text
L1 still has a future consumer
```

Therefore:

```text
SLOT1 cannot be reused yet
```

This directly connects:

```text
graph.py
```

with:

```text
slots.py
```

---

# 120. Relationship with tensor_mapping.py

Later we need to relate:

```text
TFLite tensor
```

to:

```text
memory slot
```

This requires information such as:

```text
which operation produced this tensor?

which label corresponds to the operation?

which slot was assigned to that layer?
```

Flow:

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
slot_allocation
   ↓
slot
```

---

# 121. Relationship with layer_params.py

layer_params.py also uses:

```text
old_idx_to_label
label_to_op_idx
```

to move between:

```text
logical graph
```

and:

```text
original TFLite operator
```

---

# 122. Separating graph and tensors

The project keeps two complementary representations:

```text
graph.py
    ↓
dependencies between operations
```

and:

```text
tensor_mapping.py
    ↓
relationship between tensors and memory
```

There is no need to merge everything into one large structure.

---

# 123. Why not use TFLite order directly?

TFLite has indexed operators, but the extractor does not rely solely on:

```text
op0
op1
op2
op3
```

as a sufficient semantic ordering.

It explicitly reconstructs dependencies and computes:

```python
topo_order(...)
```

This makes logical relationships explicit.

---

# 124. Benefits for branches

In a linear chain:

```text
L0 → L1 → L2
```

the order seems obvious.

Modern architectures, however, contain:

```text
        ┌──────────────┐
        │              ↓
L0 → L1 → L2 → L3 → ADD
```

The graph is needed to represent these dependencies correctly.

MobileNetV2 includes residual structures in some blocks.

---

# 125. Relationship with MobileNetV2

Residual blocks may contain:

```text
input
  │
  ├─────────────────────┐
  │                     │
  ▼                     │
Conv                    │
  ↓                     │
Depthwise               │
  ↓                     │
Conv                    │
  │                     │
  └──────────┬──────────┘
             ▼
            ADD
```

An earlier activation must therefore survive across several layers.

The graph captures that structure.

---

# 126. Ignored operators and semantics

Support for:

```python
ignored_types
```

must be used carefully.

Ignoring an operator in the graph does not mean it can be semantically removed from inference.

The function only builds logical adjacency through operators treated as transparent for a particular purpose.

In other words:

```text
ignore in the graph
```

is not automatically equivalent to:

```text
remove from execution
```

This distinction matters.

---

# 127. Example

If we have:

```text
CONV
 ↓
RESHAPE
 ↓
CONV
```

and RESHAPE is ignored for a particular structural calculation:

```text
CONV → CONV
```

that alone does not demonstrate that RESHAPE can be removed from the implementation.

Validity depends on the operation's actual semantics.

---

# 128. Current situation

The pipeline's ignored_types parameter preserves this abstraction capability.

The function is generic, but the pipeline must deliberately choose the set it uses.

---

# 129. Approximate complexity

The first scan visits:

```text
all operators
+
all inputs
+
all outputs
```

Conceptually:

```text
O(V + E)
```

where:

```text
V = operators
E = operator/tensor relationships
```

Topological sorting also operates approximately in:

```text
O(V + E)
```

for this kind of graph.

For a network like this project's, this cost is small compared with inference itself.

---

# 130. Data structure versus report format

A key refactoring decision was to stop using text as an intermediate structure.

The problematic approach would be:

```text
graph
 ↓
generate text
 ↓
parse text
 ↓
slots.py
```

The current approach is:

```text
graph
 ↓
layers
 ├────────────→ slots.py
 ├────────────→ tensor_mapping.py
 └────────────→ graph_to_text()
                         ↓
                    report
```

Thus:

```python
layers
```

is the source of truth.

---

# 131. How does this improve the project?

Python structures preserve actual types.

Example:

```python
{
    "above": [
        "L6",
        "L9",
    ]
}
```

is an actual list.

In text:

```text
[L6, L9]
```

it would require parsing again.

The structure avoids unnecessary:

```text
split()
replace()
regex
string conversions
```

operations.

---

# 132. Determinism

Several places in the code apply:

```python
sorted(...)
```

to produce reproducible results.

Even though internals use:

```python
set()
```

reports and processing order do not depend on arbitrary internal set ordering.

---

# 133. Expected invariants

After build_graph(), these conditions should hold.

### Every useful node has a useful_inputs entry

Even if it is:

```python
set()
```

### Every useful node has a useful_outputs entry

Even if it is:

```python
set()
```

### Every label points to an operator

```text
Lx → op_index
```

### Every useful operator has a label

```text
op_index → Lx
```

### order contains exactly the useful nodes

Otherwise topological sorting fails.

---

# 134. Graph input nodes

A node with:

```python
useful_inputs[op_idx] == set()
```

is a root in the logical graph.

This does not necessarily mean it lacks TFLite inputs.

It may consume:

```text
external model input
```

that was not produced by another operator.

---

# 135. Graph output nodes

A node with:

```python
useful_outputs[op_idx] == set()
```

is a leaf in the logical graph.

It usually corresponds to an operation whose result:

```text
is not consumed by another useful operation
```

may be a final model output.

---

# 136. Model input versus producer

Consider:

```text
Tensor 0
```

as an external input.

No operator produces that tensor.

Therefore:

```text
tensor 0
```

does not necessarily appear in:

```python
producer_by_tensor
```

but appears in:

```python
consumers_by_tensor
```

because the first layer consumes it.

---

# 137. Example

```text
INPUT TENSOR 0
      │
      ▼
    Op0
      │
      ▼
 Tensor 5
      │
      ▼
    Op1
```

We have:

```python
consumers_by_tensor[0] = [
    0
]
```

but not:

```python
producer_by_tensor[0]
```

because its origin is external to the operator graph.

---

# 138. Final model output

Similarly:

```text
Op67
 ↓
Tensor 100
 ↓
MODEL OUTPUT
```

There may be a producer:

```python
producer_by_tensor[100] = 67
```

but no consuming operator:

```python
consumers_by_tensor[100]
```

may be empty.

---

# 139. The graph represents computational dependencies

This explains an important distinction.

The graph does not literally represent:

```text
all objects in the TFLite file
```

It represents:

```text
computational dependency between operators
```

Therefore:

```text
external inputs
external outputs
constant weights
bias
```

need not appear as Lx nodes.

---

# 140. Operator graph versus complete data graph

A full graph could be bipartite:

```text
Operator
   ↓
Tensor
   ↓
Operator
   ↓
Tensor
```

The extractor simplifies it to:

```text
Operator
   ↓
Operator
```

because this is the representation needed for:

```text
order
liveness
slots
execution
```

---

# 141. What this module deliberately does not do

graph.py does not:

```text
extract weights
extract bias
compute quantization
compute padding
compute addresses
allocate bytes
generate LayerParams
serialize structures
generate WAT
```

Nor should it know the details of:

```text
ESP32
WAMR
WebAssembly
```

Its concern is structural:

```text
who depends on whom?
```

---

# 142. Architectural boundary

We can represent it as:

```text
TFLite
  │
  ▼
model_loader.py
  │
  ▼
tflite_utils.py
  │
  ▼
graph.py
  │
  ▼
logical graph
```

Then:

```text
logical graph
  │
  ├──→ slots.py
  ├──→ tensor_mapping.py
  └──→ layer_params.py
```

---

# 143. Module functions

| Function | Responsibility |
| ---------------------------- | ----------------------------------------------------- |
| build_graph_for_subgraph() | Discover types, producers and consumers |
| compute_useful_adjacency() | Build direct dependencies between useful operators |
| topo_order() | Compute topological ordering |
| build_layers() | Create the structured Lx representation |
| graph_to_text() | Convert the structure into a report |
| build_graph() | Orchestrate the entire process |

---

# 144. Produced structures

| Structure | Example |
| --------------------- | ------------------------- |
| `op_types`            | `["CONV_2D", "ADD", ...]` |
| `producer_by_tensor`  | `{10: 3}`                 |
| `consumers_by_tensor` | `{10: [4, 7]}`            |
| `useful`              | `[0, 1, 2, ...]`          |
| `useful_inputs`       | `{10: {6,9}}`             |
| `useful_outputs`      | `{10: {11}}`              |
| `order`               | `[0,1,2,...]`             |
| `new_label`           | `{10: "L8"}`              |
| layers | List of dictionaries |
| data | Report text |

---

# 145. Complete transformation

```text
                   TFLITE SUBGRAPH
                         │
                         ▼
              Operators + Tensors
                         │
                         ▼
          build_graph_for_subgraph()
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      op_types       producers      consumers
                         │
                         ▼
          compute_useful_adjacency()
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   useful_inputs                useful_outputs
          │                             │
          └──────────────┬──────────────┘
                         ▼
                   topo_order()
                         │
                         ▼
                 topological order
                         │
                         ▼
                  build_layers()
                         │
                         ▼
                    layers
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
       subsequent modules     graph_to_text()
               │                   │
               ▼                   ▼
        allocation/memory       report
```

---

# 146. Relationship with final execution

This file does not run inference, but its output directly affects the runtime.

The complete chain is:

```text
graph.py
   │
   ▼
dependencies
   │
   ▼
slots.py
   │
   ▼
which value occupies each region
   │
   ▼
tensor_mapping.py
   │
   ▼
tensor → slot
   │
   ▼
layer_params.py
   │
   ▼
in_ptr / out_ptr
   │
   ▼
params_blob
   │
   ▼
WAT
   │
   ▼
WASM
```

A graph error can eventually produce:

```text
incorrect slot
        ↓
incorrect pointer
        ↓
overwriting a still-live tensor
        ↓
incorrect inference
```

Although this stage performs no neural calculations, it is structurally critical.

---

# 147. Conceptual summary

graph.py essentially answers four questions.

## 1. Who produces each tensor?

```text
tensor
  ↓
producer_by_tensor
  ↓
operator
```

## 2. Who consumes each tensor?

```text
tensor
  ↓
consumers_by_tensor
  ↓
operators
```

## 3. Who depends on whom?

```text
operator
  ↓
useful_inputs / useful_outputs
  ↓
related operators
```

## 4. In what order can operations be processed?

```text
graph
  ↓
topo_order()
  ↓
topological order
```

---

# 148. Role in the overall extractor design

At this point, the pipeline has four distinct levels:

```text
┌────────────────────────────────┐
│           config.py            │
│                                │
│ defines inputs and policies    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       model_loader.py          │
│                                │
│ file → Model → SubGraph     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       tflite_utils.py          │
│                                │
│ interprets and normalizes         │
│ TFLite structures              │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│           graph.py             │
│                                │
│ reconstructs dependencies        │
│ between operations                │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       memory planning    │
│                                │
│ slots                          │
│ tensors                        │
│ parameters                     │
│ serialization                   │
└────────────────────────────────┘
```

The main transformation introduced by graph.py is:

```text
tensor-oriented TFLite structure

              ↓

operation-oriented logical graph
```

This intermediate representation forms the basis for deciding how network intermediates can share the limited memory provided by the runtime's three slots.
