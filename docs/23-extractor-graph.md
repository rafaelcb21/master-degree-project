[English](23-extractor-graph.md) | [Português (Brasil)](23-extractor-graph.pt-BR.md)

# 23 — Operator graph and ordering

[Index](README.md) · Source: [extractor/graph.py](../extractor/graph.py)

## Input contract and position

Receives model/subgraph objects from the binding. Produces operator dependencies for `allocate_slots` and producer maps for `tensor_mapping`. It does not read tests or know about the synthetic operation, which is added later. `ignored_types` exists in the API, but the pipeline does not provide it; by default no type is ignored.

## Stages and functions

1. `build_graph_for_subgraph` visits all operators, obtains their names, associates each nonnegative output with a producer, and adds each nonnegative input to the consumer list. Returns `(op_types,producer_by_tensor,consumers_by_tensor)`. A later producer for the same tensor overwrites the earlier one; uniqueness is not validated.
2. `compute_useful_adjacency` builds `forward` as sets of consumers per operator, removes self-edges, and builds `backward` as its inverse. It separates ignored indices by type. Internal functions `next_useful_from` and `prev_useful_to` use a stack and `seen` to traverse ignored operators and find the first useful ones in each direction. Returns useful nodes and their edges. The search neither executes nor semantically reproduces an ignored operation.
3. `topo_order` implements Kahn's algorithm: indegree per node, sorted initial queue, removal from the left, sorted destinations, and insertion when indegree reaches zero. If the number produced differs from `nodes`, it raises `RuntimeError` for a cycle.
4. `build_layers` creates names `L0,L1,...` by enumerating `useful` (original order), but returns `layers` in topological order. Each dict contains `type,name,above,below,op_index`; neighbors are sorted by label number.
5. `graph_to_text` emits a header and one `type; label; [above]; [below]` line. The first header column is called `nome_da_camada`, but receives the operation type.
6. `build_graph` combines these functions and returns all structures: types, producers, consumers, useful nodes, adjacency, `order`, `new_label`, two inverse label maps, `layers`, and text `data`.

```text
tensor T0 ──► CONV A ──► tensor T1 ──┬──► CONV B ──► T2 ──┐
                                    │                    ▼
                                    └──────────────────► ADD C

producer_by_tensor: T1 → A, T2 → B
consumers_by_tensor: T1 → [B,C], T2 → [C]
useful edges: A → B, A → C, B → C
possible order: A, B, C
```

Inputs are FlatBuffer read/write relationships. `graph.py` transforms tensor dependencies into operator dependencies; outputs are an order and a representation suitable for counting readers. IDs and types are model-specific; the graph algorithm is generic. Constants also appear in input lists, but without an internal producer they do not create edges by themselves.

## Invariants and limitations

Every useful node has input/output sets, and the label maps are inverses. A node without a computational predecessor receives logical input SLOT0 in the allocator, an assumption that deserves review for graphs with multiple independent roots. There is no pruning by reachability to outputs: “useful” only means “not ignored.” Disconnected operations may remain in the list.

Edges use sets: multiple reads from the same producer by one consumer produce one operator dependency, not necessarily a per-tensor count. This matters for graphs with multiple outputs or repeated inputs. Label Lk is not guaranteed to equal op_index when types are ignored. The runtime serializes operators in their original order, so the report's topological ordering does not by itself determine final execution order.

Without ignored nodes, construction is close to O(operators + references + edges), plus sorting. With ignored chains, repeated searches per node may revisit graph sections; these traversals are not cached. Report 02 is diagnostic and is not read back to control execution.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from collections import defaultdict, deque
from extractor.tflite_utils import op_name
```

### `build_graph_for_subgraph` — signature

```python
def build_graph_for_subgraph(model, subgraph)
```

### `compute_useful_adjacency` — signature

```python
def compute_useful_adjacency(subgraph, op_types, consumers_by_tensor, ignored_types=None)
```

### `topo_order` — signature

```python
def topo_order(nodes, in_edges, out_edges)
```

### `build_layers` — signature

```python
def build_layers(op_types, useful, useful_inputs, useful_outputs, order)
```

### `graph_to_text` — signature

```python
def graph_to_text(layers)
```

### `build_graph` — signature

```python
def build_graph(model, subgraph, ignored_types=None)
```

## Preserved technical material

The previous explanation is in [04-graph.md](historico/04-graph.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
