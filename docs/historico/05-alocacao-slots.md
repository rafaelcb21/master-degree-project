[English](05-alocacao-slots.md) | [Português (Brasil)](05-alocacao-slots.pt-BR.md)

> **Preserved historical document.** This text belongs to the previous architecture and retains useful technical examples. Paths, orchestration in `main.py`, the mandatory synthetic layer, and runtime descriptions may be outdated. For current behavior, see the [index](../README.md) and [verified inconsistencies](../99-inconsistencias-e-limitacoes.md). The original body has been preserved in the Portuguese edition.

# 05 — Logical slot allocation (`slots.py`)

## 1. Module purpose

The `extractor/slots.py` file decides which logical slot stores each intermediate network output.

The code described here is:

```python
# extractor/slots.py


def allocate_slots(layers, num_slots):
    """
    Aloca slots lógicos para as saídas das camadas.

    Parâmetros
    ----------
    layers:
        Lista de camadas produzida por graph.py.

    num_slots:
        Quantidade de slots lógicos disponíveis.

    Retorna
    -------
    allocation:
        Lista contendo os slots de entrada e saída de cada camada.

    layer_output_slot:
        Mapeamento:
            nome_da_camada -> slot_de_saida
    """

    layer_output_slot = {}
    slot_readers_count = {}
    allocation = []

    next_slot = 1

    for layer in layers:
        layer_name = layer["name"]
        layer_type = layer["type"]
        layers_above = layer["above"]
        layers_below = layer["below"]

        # ====================================================
        # QUANTIZE
        # ====================================================
        #
        # No comportamento atual, QUANTIZE é executado
        # in-place: entrada e saída utilizam o mesmo slot.
        #
        if layer_type == "QUANTIZE":
            if not layers_above:
                input_slot = 0
            else:
                input_slot = (
                    layer_output_slot[
                        layers_above[0]
                    ]
                )

            layer_output_slot[layer_name] = input_slot

            allocation.append(
                {
                    "layer": layer_name,
                    "type": layer_type,
                    "input_slots": [input_slot],
                    "output_slot": input_slot,
                    "in_place": True,
                }
            )

            continue

        # ====================================================
        # SLOTS DE ENTRADA
        # ====================================================

        if not layers_above:
            input_slots = [0]
            next_slot = 1

        else:
            input_slots = [
                layer_output_slot[above]
                for above in layers_above
            ]

        # ====================================================
        # DESCOBRIR SLOTS DISPONÍVEIS
        # ====================================================

        available_slots = list(
            range(num_slots)
        )

        for slot in list(available_slots):
            if (
                slot in slot_readers_count
                and slot_readers_count[slot] > 0
            ):
                available_slots.remove(slot)

        if not available_slots:
            raise RuntimeError(
                f"Sem slots livres em {layer_name}"
            )

        # ====================================================
        # ESCOLHER SLOT DE SAÍDA
        # ====================================================

        if next_slot in available_slots:
            output_slot = next_slot

        else:
            output_slot = available_slots[0]

        # ====================================================
        # REGISTRAR CONSUMO DAS ENTRADAS
        # ====================================================

        for input_slot in input_slots:
            if input_slot in slot_readers_count:
                slot_readers_count[input_slot] -= 1

                if (
                    slot_readers_count[input_slot]
                    == 0
                ):
                    del slot_readers_count[
                        input_slot
                    ]

        # ====================================================
        # REGISTRAR CONSUMIDORES DA NOVA SAÍDA
        # ====================================================

        if layers_below:
            slot_readers_count[output_slot] = (
                len(layers_below)
            )

        # ====================================================
        # CAMADA -> SLOT DE SAÍDA
        # ====================================================

        layer_output_slot[layer_name] = (
            output_slot
        )

        # ====================================================
        # REGISTRO DA ALOCAÇÃO
        # ====================================================

        allocation.append(
            {
                "layer": layer_name,
                "type": layer_type,
                "input_slots": input_slots,
                "output_slot": output_slot,
                "in_place": False,
            }
        )

        # ====================================================
        # PRÓXIMO SLOT PREFERENCIAL
        # ====================================================

        next_slot = (
            output_slot + 1
        ) % num_slots

    return allocation, layer_output_slot


def slot_allocation_to_text(allocation):
    """
    Gera uma representação textual da alocação de slots.

    Essa função é apenas para relatório/debug.
    A lógica de alocação não depende desse texto.
    """

    lines = []

    for alloc in allocation:
        input_slots = alloc["input_slots"]
        output_slot = alloc["output_slot"]

        if len(input_slots) == 1:
            inputs = str(input_slots[0])

        else:
            inputs = " e ".join(
                map(str, input_slots)
            )

        line = (
            f"{alloc['type']:25} "
            f"{alloc['layer']:5} "
            f"[{inputs} -> {output_slot}]"
        )

        if alloc["in_place"]:
            line += " (in-place)"

        lines.append(line)

    return "\n".join(lines)
```

---

# 2. Architectural role

Up to `graph.py`, the project knows only logical dependencies:

```text
L0 → L1 → L2
```

or:

```text
L1 ─────────────┐
 ↓              │
L2              │
 ↓              │
L3              │
 └──────────────┤
                ↓
               L4 ADD
```

The runtime must physically store each layer's output.

Because ESP32 memory is limited, reserving a dedicated region for every intermediate tensor is undesirable.

The adopted strategy reuses a few memory regions.

These regions are called:

```text
slots
```

In the current project:

```python
NUM_SLOTS = 3
```

Initially, there are therefore:

```text
slot 0
slot 1
slot 2
```

---

# 3. Logical slots versus physical addresses

In this module, a slot is just a number.

For example:

```text
slot 0
slot 1
slot 2
```

It does not yet mean:

```text
507248
703856
900464
```

These addresses will be calculated later.

There are therefore two levels:

```text
slots.py
    ↓
logical slot

memory.py / layer_params.py
    ↓
physical slot address
```

Example:

```text
logical slot 1
      ↓
SLOT1_BASE
      ↓
703856
```

The purpose of `slots.py` is to decide **who uses which slot**, rather than where that slot starts in linear memory.

---

# 4. Why reuse memory?

Consider a linear network:

```text
L0 → L1 → L2 → L3
```

If each layer had a dedicated region:

```text
L0 output → buffer 0
L1 output → buffer 1
L2 output → buffer 2
L3 output → buffer 3
```

four activation regions would be required.

Once L1 has completely consumed L0's result, that memory may eventually be reused.

We can then have something like:

```text
L0 output → SLOT1
L1 output → SLOT2
L2 output → SLOT1
L3 output → SLOT2
```

Timeline:

```text
time ────────────────────────────────────►

SLOT1   [L0 output]          [L2 output]

SLOT2          [L1 output]          [L3 output]
```

Memory is thus reused.

---

# 5. Why is alternating slots insufficient?

A neural network is not necessarily a linear chain.

MobileNetV2 has residual connections.

For example:

```text
        ┌────────────────────────┐
        │                        │
        │                        ▼
L5 → L6 → L7 → L8 ───────────── ADD
```

L5's output must remain available while L6, L7, and L8 execute.

If we immediately reuse L5's slot:

```text
L5 output → SLOT1
L6 output → SLOT2
L7 output → SLOT1
```

L5's contents would be destroyed before reaching `ADD`.

This is why allocation depends on the graph.

---

# 6. Relationship with `graph.py`

The module receives:

```python
layers
```

produced by:

```text
graph.py
```

Each layer has:

```python
{
    "type": ...,
    "name": ...,
    "above": ...,
    "below": ...,
    "op_index": ...,
}
```

The most important fields here are:

```text
above
below
```

`above` identifies the producers of the inputs.

`below` indicates how many operations will still use the current output.

---

# 7. Main input

The function is:

```python
def allocate_slots(
    layers,
    num_slots,
):
```

Receives:

### `layers`

The structured representation of the graph.

### `num_slots`

Maximum number of available logical slots.

In current usage:

```python
num_slots = 3
```

---

# 8. Function outputs

The function returns:

```python
return (
    allocation,
    layer_output_slot,
)
```

These are two complementary representations.

---

# 9. `allocation`

The list:

```python
allocation
```

stores the complete allocation for each layer.

Example:

```python
[
    {
        "layer": "L0",
        "type": "QUANTIZE",
        "input_slots": [0],
        "output_slot": 0,
        "in_place": True,
    },

    {
        "layer": "L1",
        "type": "CONV_2D",
        "input_slots": [0],
        "output_slot": 1,
        "in_place": False,
    },
]
```

It records both:

```text
where the layer reads from
```

and:

```text
where the layer writes
```

---

# 10. `layer_output_slot`

The second result is a simpler map:

```python
layer_output_slot
```

Example:

```python
{
    "L0": 0,
    "L1": 1,
    "L2": 2,
}
```

It directly answers:

```text
which slot holds Lx's output?
```

This is useful when a later layer has:

```python
"above": ["L1"]
```

In this case:

```python
layer_output_slot["L1"]
```

provides the input slot.

---

# 11. Initial internal state

Initially:

```python
layer_output_slot = {}
```

```python
slot_readers_count = {}
```

```python
allocation = []
```

```python
next_slot = 1
```

Each structure has a different purpose.

---

# 12. `layer_output_slot`

It starts empty because no layer has been processed.

As the network is traversed:

```python
layer_output_slot[layer_name] = output_slot
```

fills in the state.

Example:

```text
after L0:
L0 → 0

after L1:
L0 → 0
L1 → 1

after L2:
L0 → 0
L1 → 1
L2 → 2
```

---

# 13. `slot_readers_count`

This is the algorithm's central structure.

It represents:

```text
slot
 ↓
how many consumers still need to read its contents
```

Example:

```python
slot_readers_count = {
    1: 2
}
```

means:

```text
the contents stored in SLOT1
will still be used by two operations
```

While:

```text
count > 0
```

the slot must not be overwritten.

---

# 14. Reader concept

Suppose:

```text
L1
 ├──→ L2
 └──→ L4
```

L1's output has:

```text
2 consumidores
```

Then:

```python
slot_readers_count[
    slot_de_L1
] = 2
```

When L2 uses this data:

```text
2 → 1
```

When L4 uses it:

```text
1 → 0
```

From that point onward, the slot can be reused.

---

# 15. `allocation`

The list:

```python
allocation = []
```

records each decision made by the algorithm.

It differs from `slot_readers_count`.

`slot_readers_count` is temporary state used during the calculation.

`allocation` is the permanent result.

---

# 16. `next_slot`

Initially:

```python
next_slot = 1
```

This indicates the initial write preference.

Slot 0 is handled specially because it normally contains the graph's initial input.

Thus, for an initial layer that does not run in place:

```text
input  → slot 0
output → preferably slot 1
```

---

# 17. Iterating over layers

The function iterates over:

```python
for layer in layers:
```

The order of `layers` comes from `graph.py`, which builds the list in topological order.

When a layer is analyzed, its producers are therefore expected to have been processed already.

This property is essential for:

```python
layer_output_slot[
    layers_above[0]
]
```

to work.

---

# 18. Information extracted from each layer

For each layer:

```python
layer_name = layer["name"]
```

```python
layer_type = layer["type"]
```

```python
layers_above = layer["above"]
```

```python
layers_below = layer["below"]
```

Example:

```python
{
    "type": "ADD",
    "name": "L10",
    "above": [
        "L6",
        "L9",
    ],
    "below": [
        "L11",
    ],
}
```

results in:

```text
layer_name = L10
layer_type = ADD
layers_above = [L6, L9]
layers_below = [L11]
```

---

# 19. Special case: `QUANTIZE`

The first special case is:

```python
if layer_type == "QUANTIZE":
```

In the current runtime, this operation is handled as:

```text
in-place
```

in other words:

```text
input slot = output slot
```

---

# 20. What does in-place execution mean?

Normally we have:

```text
input buffer
    ↓
operation
    ↓
a different output buffer
```

For example:

```text
SLOT0 → CONV → SLOT1
```

In an in-place operation:

```text
SLOT0 → QUANTIZE → SLOT0
```

The operation reads and writes the same logical region.

---

# 21. First `QUANTIZE` in the network

If:

```python
not layers_above
```

is true, the layer has no preceding useful operation.

In this case:

```python
input_slot = 0
```

This represents the model's external input.

Flow:

```text
external input
     ↓
   SLOT0
     ↓
 QUANTIZE
     ↓
   SLOT0
```

---

# 22. `QUANTIZE` after another layer

If a preceding layer exists:

```python
input_slot = (
    layer_output_slot[
        layers_above[0]
    ]
)
```

Example:

```text
L5 output → SLOT2
```

Then:

```text
L5 → QUANTIZE
```

performs:

```text
input_slot = 2
output_slot = 2
```

---

# 23. Recording the `QUANTIZE` output

Then:

```python
layer_output_slot[
    layer_name
] = input_slot
```

If:

```text
L4 reads SLOT1
```

then:

```text
L4 also has its output in SLOT1
```

---

# 24. Complete `QUANTIZE` record

The following is inserted:

```python
{
    "layer": layer_name,
    "type": layer_type,
    "input_slots": [
        input_slot
    ],
    "output_slot": input_slot,
    "in_place": True,
}
```

Example:

```python
{
    "layer": "L0",
    "type": "QUANTIZE",
    "input_slots": [0],
    "output_slot": 0,
    "in_place": True,
}
```

---

# 25. `continue`

Then:

```python
continue
```

This means `QUANTIZE` skips the rest of the normal allocation logic.

In other words, it does not:

```text
search for a free slot
choose next_slot
record a new output_slot
```

because its output must reuse the input.

---

# 26. Important note about `QUANTIZE`

In-place behavior is not a universal property of every TFLite `QUANTIZE` operation.

It is a decision of this runtime's current implementation.

Therefore the correct rule is:

```text
in this project:
QUANTIZE executes in place
```

rather than:

```text
QUANTIZE must always execute in place
```

---

# 27. Normal layer: determining inputs

If the operation is not `QUANTIZE`, the general logic begins.

The first step is to determine the input slots.

---

# 28. Layer without a predecessor

If:

```python
if not layers_above:
```

then:

```python
input_slots = [0]
```

and:

```python
next_slot = 1
```

This represents an operation whose input comes directly from external input.

---

# 29. First convolution example

```text
image
  ↓
SLOT0
  ↓
CONV_2D
  ↓
SLOT1
```

For this operation:

```python
input_slots = [0]
```

and the preferred write destination is:

```python
next_slot = 1
```

---

# 30. Layer with predecessors

If:

```python
layers_above
```

is not empty:

```python
input_slots = [
    layer_output_slot[above]
    for above in layers_above
]
```

---

# 31. Single-input example

If:

```python
layers_above = [
    "L4"
]
```

and:

```python
layer_output_slot[
    "L4"
] = 2
```

then:

```python
input_slots = [
    2
]
```

---

# 32. Two-input example

For an `ADD`:

```python
layers_above = [
    "L6",
    "L9",
]
```

and:

```python
layer_output_slot = {
    "L6": 1,
    "L9": 2,
}
```

the result will be:

```python
input_slots = [
    1,
    2,
]
```

Representation:

```text
SLOT1 ─┐
       ├→ ADD
SLOT2 ─┘
```

---

# 33. Finding available slots

The function starts by assuming:

```python
available_slots = list(
    range(num_slots)
)
```

For:

```python
num_slots = 3
```

this results in:

```python
[
    0,
    1,
    2,
]
```

---

# 34. Filtering occupied slots

Then:

```python
for slot in list(
    available_slots
):
```

the following is checked:

```python
if (
    slot in slot_readers_count
    and slot_readers_count[
        slot
    ] > 0
):
```

If there are still pending consumers:

```python
available_slots.remove(
    slot
)
```

---

# 35. Example

Suppose:

```python
slot_readers_count = {
    1: 2,
    2: 1,
}
```

We start with:

```python
available_slots = [
    0,
    1,
    2,
]
```

After filtering:

```python
available_slots = [
    0
]
```

Because:

```text
SLOT1 still has 2 readers
SLOT2 still has 1 reader
SLOT0 has no pending readers
```

---

# 36. Meaning of a free slot

In this algorithm, a slot is considered available when it:

```text
does not exist in slot_readers_count
```

or has no pending readers.

Because zero-count entries are removed from the dictionary, normally:

```text
free slot
    ↓
slot is absent from slot_readers_count
```

---

# 37. No slot available

If:

```python
not available_slots
```

the function raises:

```python
raise RuntimeError(
    f"Sem slots livres em {layer_name}"
)
```

This error means that, for the graph's current state and the configured slot count, all regions still hold values the algorithm considers live.

---

# 38. Example

With three slots:

```text
SLOT0 → still needed
SLOT1 → still needed
SLOT2 → still needed
```

and a new layer needs to produce another output:

```text
no logical space is available
```

In this case, extractor execution stops.

---

# 39. Choosing the output slot

If there are free slots:

```python
if next_slot in available_slots:
    output_slot = next_slot
```

Otherwise:

```python
output_slot = (
    available_slots[0]
)
```

---

# 40. Role of `next_slot`

`next_slot` is not mandatory.

It acts as the:

```text
preferred slot
```

The algorithm attempts to maintain a simple rotation.

For three slots:

```text
0 → 1 → 2 → 0 → 1 → ...
```

But only if the next slot is actually free.

---

# 41. Example

Suppose:

```text
next_slot = 2
available_slots = [0, 2]
```

Then:

```text
output_slot = 2
```

---

# 42. Example with an occupied preferred slot

If:

```text
next_slot = 2
available_slots = [0, 1]
```

then:

```text
2 is unavailable
```

Therefore:

```python
output_slot = (
    available_slots[0]
)
```

Result:

```text
output_slot = 0
```

---

# 43. Why have a preference?

Without this, the algorithm could always choose:

```python
available_slots[0]
```

The circular preference helps distribute activations naturally among the slots.

Correctness depends first on availability.

The priority is:

```text
1. the slot must be free
2. if next_slot is free, prefer it
3. otherwise, use the first free slot
```

---

# 44. Consuming inputs

After choosing the output slot, the function records that the current operation consumed its inputs.

The code is:

```python
for input_slot in input_slots:
```

For each one:

```python
if input_slot in slot_readers_count:
```

the count is decremented:

```python
slot_readers_count[
    input_slot
] -= 1
```

---

# 45. Meaning of the decrement

Consider:

```text
L2 output is in SLOT1
```

and:

```text
there are still 2 consumers
```

State:

```python
slot_readers_count = {
    1: 2
}
```

When processing one of them:

```text
2 → 1
```

The output must still be preserved.

---

# 46. Last consumer

When:

```python
slot_readers_count[
    input_slot
] == 0
```

the following executes:

```python
del slot_readers_count[
    input_slot
]
```

This means:

```text
there are no more known consumers
for the value stored in this slot
```

It can therefore be reused later.

---

# 47. Lifetime example

Consider:

```text
L1 output → SLOT1

L2 uses L1
L5 uses L1
```

When producing L1:

```python
slot_readers_count = {
    1: 2
}
```

After L2:

```python
slot_readers_count = {
    1: 1
}
```

After L5:

```python
slot_readers_count = {}
```

SLOT1 is now released.

---

# 48. Recording readers of the new output

After consuming the inputs, the function records how many future operations will consume the new output:

```python
if layers_below:
```

Then:

```python
slot_readers_count[
    output_slot
] = len(
    layers_below
)
```

---

# 49. Simple example

If:

```python
layers_below = [
    "L4"
]
```

then:

```python
slot_readers_count[
    output_slot
] = 1
```

---

# 50. Branching example

If:

```python
layers_below = [
    "L4",
    "L7",
]
```

then:

```python
slot_readers_count[
    output_slot
] = 2
```

The value cannot be overwritten until both operations have been processed.

---

# 51. Layer without consumers

If:

```python
layers_below == []
```

no entry is created in:

```python
slot_readers_count
```

This normally occurs at the final output.

The output still physically exists in the slot, but the algorithm does not need to protect it for another network layer.

---

# 52. Recording layer → slot

Then:

```python
layer_output_slot[
    layer_name
] = output_slot
```

This information will be used by future layers.

Example:

```python
layer_output_slot[
    "L8"
] = 2
```

When L9 has:

```python
"above": ["L8"]
```

it will discover that its input is in:

```text
SLOT2
```

---

# 53. Detailed record in `allocation`

The function adds:

```python
{
    "layer": layer_name,
    "type": layer_type,
    "input_slots": input_slots,
    "output_slot": output_slot,
    "in_place": False,
}
```

This record contains everything subsequent stages need to know about the logical movement of activations.

---

# 54. Example

A convolution could produce:

```python
{
    "layer": "L12",
    "type": "CONV_2D",
    "input_slots": [1],
    "output_slot": 2,
    "in_place": False,
}
```

Representing:

```text
SLOT1
  ↓
CONV_2D L12
  ↓
SLOT2
```

---

# 55. `ADD` example

An `ADD` could produce:

```python
{
    "layer": "L18",
    "type": "ADD",
    "input_slots": [
        1,
        2,
    ],
    "output_slot": 0,
    "in_place": False,
}
```

Representing:

```text
SLOT1 ──┐
        ├── ADD L18 ──→ SLOT0
SLOT2 ──┘
```

---

# 56. Updating the preferred slot

At the end of the iteration:

```python
next_slot = (
    output_slot + 1
) % num_slots
```

---

# 57. The `%` operator

With:

```python
num_slots = 3
```

we have:

```text
output_slot 0
    ↓
(0 + 1) % 3
    ↓
1
```

```text
output_slot 1
    ↓
(1 + 1) % 3
    ↓
2
```

```text
output_slot 2
    ↓
(2 + 1) % 3
    ↓
0
```

There is therefore a rotation:

```text
0 → 1 → 2 → 0 → 1 → 2 ...
```

---

# 58. Final return value

At the end:

```python
return (
    allocation,
    layer_output_slot,
)
```

Example:

```python
allocation = [
    ...,
]
```

and:

```python
layer_output_slot = {
    "L0": 0,
    "L1": 1,
    "L2": 2,
    ...
}
```

---

# 59. Complete linear chain example

Consider:

```text
L0 QUANTIZE
 ↓
L1 CONV
 ↓
L2 DW
 ↓
L3 CONV
```

With three slots.

---

# 60. L0 — QUANTIZE

It has no preceding layer.

Therefore:

```text
input_slot = 0
output_slot = 0
```

Result:

```text
SLOT0 → QUANTIZE → SLOT0
```

---

# 61. L1 — CONV

Input:

```text
SLOT0
```

Preference:

```text
next_slot = 1
```

Output:

```text
SLOT1
```

Result:

```text
SLOT0 → CONV → SLOT1
```

---

# 62. L2 — DEPTHWISE

Input:

```text
SLOT1
```

If SLOT2 is free:

```text
output = SLOT2
```

Result:

```text
SLOT1 → DW → SLOT2
```

---

# 63. L3 — CONV

Input:

```text
SLOT2
```

If SLOT0 has already been released:

```text
output = SLOT0
```

Result:

```text
SLOT2 → CONV → SLOT0
```

---

# 64. Chain result

```text
             input
                │
                ▼
             SLOT0
                │
             QUANTIZE
                │
                ▼
             SLOT0
                │
              CONV
                │
                ▼
             SLOT1
                │
                DW
                │
                ▼
             SLOT2
                │
              CONV
                │
                ▼
             SLOT0
```

Memory is reused cyclically.

---

# 65. Residual example

Consider:

```text
L1
 ├─────────────────────────────┐
 ↓                             │
L2                             │
 ↓                             │
L3                             │
 ↓                             │
L4                             │
 └───────────────┐             │
                 ▼             ▼
                    L5 ADD
```

Suppose:

```text
L1 output = SLOT1
```

Because L1 has two consumers:

```text
L2
L5
```

the state is:

```python
slot_readers_count = {
    1: 2
}
```

---

# 66. L2 consumes SLOT1

After L2:

```text
SLOT1 readers:
2 → 1
```

Memory remains protected.

---

# 67. Intermediate layers

L3 and L4 can use other slots.

SLOT1 remains unavailable because:

```text
L5 still needs it
```

---

# 68. L5 ADD

L5 receives:

```text
SLOT1
+
slot holding L4's output
```

After L5 consumes SLOT1:

```text
1 → 0
```

The slot can now be reused.

This is the mechanism that preserves skip connections.

---

# 69. Relationship between `above` and `input_slots`

The code does not consult tensors directly at this stage.

It uses:

```text
layer["above"]
```

and:

```text
layer_output_slot
```

The transformation is:

```text
L6
 ↓
layer_output_slot["L6"]
 ↓
slot 1
```

Then:

```text
above
 ↓
input_slots
```

---

# 70. Relationship between `below` and liveness

Similarly:

```text
layer["below"]
```

defines:

```text
how many future readers exist
```

In other words:

```text
len(layers_below)
    ↓
slot_readers_count
```

This implements a simple form of lifetime analysis.

---

# 71. Liveness concept

In compilers and memory planning, a value is "live" while it may still be used in the future.

In this module:

```text
slot_readers_count[slot] > 0
```

represents:

```text
the value stored in the slot is still live
```

When:

```text
slot_readers_count
no longer contains the slot
```

the value is considered dead for the rest of the graph.

---

# 72. This is not memory allocation in bytes

It is important not to confuse:

```text
allocate_slots()
```

with:

```text
malloc()
```

or address calculation.

Here the result is:

```text
L10 → slot 2
```

not:

```text
L10 → address 900464
```

Physical conversion occurs later.

---

# 73. Relationship with `memory.py`

Later:

```text
memory.py
```

calculates:

```text
SLOT_BYTES
```

and then:

```text
slot_bases
```

For example:

```text
SLOT0_BASE = 507248
SLOT1_BASE = 703856
SLOT2_BASE = 900464
```

Thus:

```text
output_slot = 2
```

can become:

```text
out_ptr = slot_bases[2]
        = 900464
```

---

# 74. Relationship with tensor_mapping.py

`allocate_slots()` works per layer.

Other parts of the pipeline need to answer:

```text
which slot holds TFLite tensor 173?
```

This responsibility belongs to:

```text
tensor_mapping.py
```

Flow:

```text
layer
 ↓
allocate_slots()
 ↓
layer → slot
 ↓
tensor_mapping.py
 ↓
tensor → slot
```

---

# 75. Relationship to `layer_params.py`

Then:

```text
input_slots
output_slot
```

are converted into real pointers.

Conceptually:

```text
input_slot = 1
      ↓
slot_bases[1]
      ↓
in_ptr
```

and:

```text
output_slot = 2
      ↓
slot_bases[2]
      ↓
out_ptr
```

These pointers go into `LayerParams`.

---

# 76. Complete flow

```text
graph.py
  │
  │ above / below
  ▼
slots.py
  │
  │ input_slot / output_slot
  ▼
tensor_mapping.py
  │
  │ tensor → slot
  ▼
memory.py
  │
  │ slot → base
  ▼
layer_params.py
  │
  │ in_ptr / out_ptr
  ▼
params_blob
  │
  ▼
WAT
```

---

# 77. `slot_allocation_to_text()`

The module's second function is:

```python
def slot_allocation_to_text(
    allocation
):
```

It does not affect the calculation.

Its only purpose is to convert:

```python
allocation
```

into readable text.

---

# 78. Important separation

The source of truth is:

```python
allocation
```

The report is derived from it.

Therefore:

```text
allocation
   ├──→ subsequent modules
   └──→ slot_allocation_to_text()
               ↓
            report
```

Never the reverse.

---

# 79. Initializing the report

```python
lines = []
```

Each decision is converted into a text line.

---

# 80. Iterating over records

```python
for alloc in allocation:
```

Each element contains:

```text
layer
type
input_slots
output_slot
in_place
```

---

# 81. Retrieving inputs and output

```python
input_slots = (
    alloc["input_slots"]
)
```

```python
output_slot = (
    alloc["output_slot"]
)
```

---

# 82. Single input

If:

```python
len(input_slots) == 1
```

the text is:

```python
inputs = str(
    input_slots[0]
)
```

Example:

```text
[1 -> 2]
```

---

# 83. Multiple inputs

Otherwise:

```python
inputs = " e ".join(
    map(str, input_slots)
)
```

For:

```python
[1, 2]
```

produces:

```text
1 e 2
```

Then:

```text
[1 e 2 -> 0]
```

---

# 84. Assembling the line

The line uses:

```python
line = (
    f"{alloc['type']:25} "
    f"{alloc['layer']:5} "
    f"[{inputs} -> {output_slot}]"
)
```

The format specifiers:

```text
:25
:5
```

serve only to align columns visually.

They do not change the data.

---

# 85. Report example

```text
QUANTIZE                  L0    [0 -> 0] (in-place)
CONV_2D                   L1    [0 -> 1]
DEPTHWISE_CONV_2D         L2    [1 -> 2]
CONV_2D                   L3    [2 -> 0]
ADD                       L4    [0 e 1 -> 2]
```

---

# 86. In-place marker

If:

```python
alloc["in_place"]
```

is true:

```python
line += " (in-place)"
```

The report thus explicitly shows that input and output share the same logical region.

---

# 87. Text return value

Finally:

```python
return "\n".join(
    lines
)
```

turns the list into a single text string.

---

# 88. Temporary state versus permanent result

It is important to distinguish:

```text
slot_readers_count
```

from:

```text
allocation
```

`slot_readers_count` exists only during algorithm execution.

`allocation` is the final result.

Example:

```text
during L10:

slot_readers_count = {
    0: 1,
    2: 2
}
```

This state does not need to be retained afterward.

Whereas:

```python
{
    "layer": "L10",
    "input_slots": [0, 2],
    "output_slot": 1,
}
```

is permanent.

---

# 89. The algorithm does not physically reserve memory

When it executes:

```python
output_slot = 1
```

no bytes are allocated.

It only produces a logical decision.

The physical allocation will be:

```text
slot 1
    ↓
SLOT1_BASE
    ↓
region [SLOT1_BASE,
       SLOT1_BASE + SLOT_BYTES)
```

---

# 90. Why is `NUM_SLOTS = 3` sufficient for the current model?

The model used by the project can be planned by the current algorithm with three reusable regions.

The need comes mainly from the combination of:

```text
current input
new output
preserved residual value
```

In a typical residual block:

```text
SLOT A
  ├─────────────────────────┐
  ▼                         │
chain of operations        │
  ▼                         │
SLOT B/C                    │
                            ▼
                           ADD
```

three slots allow an old value to be retained while the other two participate in the computation chain.

This describes the behavior observed in the current model, not a guarantee that any network can run with three slots.

---

# 91. `NUM_SLOTS` is not a TFLite property

The TFLite file does not say:

```text
use three slots
```

This is a decision made by the runtime developed in this project.

Therefore:

```text
TFLite
    ↓
graph
    ↓
custom strategy
    ↓
3 slots
```

---

# 92. Important limitation: counting per slot

The current algorithm maintains:

```python
slot_readers_count
```

per slot.

For example:

```python
{
    1: 2
}
```

It does not explicitly maintain:

```text
tensor X has 2 readers
tensor Y has 1 reader
```

This is an important simplification in the implementation.

---

# 93. Why does this work in the current scenario?

The strategy assumes that a slot represents a single live logical value at that moment.

While it has pending readers:

```text
cannot be overwritten
```

When the count reaches zero:

```text
it can receive another value
```

Thus, the slot acts as a proxy for the lifetime of the tensor currently stored in it.

---

# 94. Conceptual limit of this approach

A more general liveness analysis could track:

```text
tensor_id
    ↓
number of remaining uses
```

and then associate tensors with slots.

The current algorithm combines part of these two responsibilities:

```text
slot
    ↓
number of remaining readers
```

This is simpler, but depends on the adopted reuse strategy.

---

# 95. Special case requiring attention: `QUANTIZE`

In the block:

```python
if layer_type == "QUANTIZE":
```

the function records the same slot for input and output and executes:

```python
continue
```

Therefore the `QUANTIZE` path does not execute the common logic for:

```text
decrementing input readers
recording output readers
```

This is exactly how the current code behaves.

---

# 96. Implication

For the current model, this implementation was retained to preserve the original version's behavior.

Conceptually, however, there is a difference between:

```text
in-place operation
```

and:

```text
the value's lifetime before and after the operation
```

If future models have different branching patterns around a `QUANTIZE`, this point needs specific validation.

---

# 97. Why not change it now?

The refactoring's initial objective was:

```text
separate responsibilities
while preserving existing functional behavior
```

Changing the slot algorithm at the same time could introduce differences that are difficult to attribute.

The adopted strategy was:

```text
first modularize
then validate
then improve
```

---

# 98. Important invariant

Before a layer uses:

```python
layer_output_slot[above]
```

the corresponding producer must have been processed already.

This depends on the topological order of `layers`.

If `layers` were not in a valid order:

```text
consumer before producer
```

the function could raise:

```text
KeyError
```

when looking up a slot that does not yet exist.

---

# 99. Slot invariant

Every value in:

```python
input_slots
```

and:

```python
output_slot
```

must satisfy:

```text
0 <= slot < num_slots
```

With:

```python
num_slots = 3
```

the only valid values are:

```text
0
1
2
```

---

# 100. Output invariant

For each processed layer, there must be:

```python
layer_output_slot[
    layer_name
]
```

This ensures that any subsequent consumer can discover its input.

---

# 101. Live slot invariant

When:

```python
slot_readers_count[slot] > 0
```

the algorithm must prevent it from being chosen as another layer's output.

This is exactly what the filter on:

```python
available_slots
```

implements.

---

# 102. Detailed step-by-step example

Consider:

```text
L0 QUANTIZE
 ↓
L1 CONV
 ├───────────────┐
 ↓               │
L2 DW            │
 ↓               │
L3 CONV           │
 └───────┐       │
         ▼       ▼
          L4 ADD
```

Suppose:

```text
NUM_SLOTS = 3
```

---

# 103. Step L0

`QUANTIZE`.

No predecessors.

```text
input = 0
output = 0
```

State:

```python
layer_output_slot = {
    "L0": 0
}
```

---

# 104. Step L1

Input:

```text
L0 → SLOT0
```

Initially available slots:

```text
0, 1, 2
```

Preference:

```text
1
```

Then:

```text
L1 → SLOT1
```

Because L1 has two consumers:

```text
L2
L4
```

we record:

```python
slot_readers_count = {
    1: 2
}
```

---

# 105. Step L2

Input:

```text
SLOT1
```

Before choosing the output:

```text
SLOT1 protected
```

Available:

```text
SLOT0
SLOT2
```

Current preference:

```text
SLOT2
```

Therefore:

```text
L2 output → SLOT2
```

When consuming SLOT1:

```text
2 → 1
```

If L2 has one consumer:

```text
L3
```

we record:

```text
SLOT2 → 1 reader
```

State:

```python
slot_readers_count = {
    1: 1,
    2: 1,
}
```

---

# 106. Step L3

Input:

```text
SLOT2
```

Protected slots:

```text
1
2
```

Free:

```text
0
```

Therefore:

```text
L3 output → SLOT0
```

SLOT2 is consumed:

```text
1 → 0
```

SLOT2 is then released.

If L3 feeds L4:

```text
SLOT0 → 1 reader
```

State:

```python
slot_readers_count = {
    1: 1,
    0: 1,
}
```

---

# 107. Step L4 — ADD

Inputs:

```text
L1 → SLOT1
L3 → SLOT0
```

Protected slots before consumption:

```text
SLOT1
SLOT0
```

Free:

```text
SLOT2
```

Then:

```text
ADD output → SLOT2
```

After consumption:

```text
SLOT1:
1 → 0

SLOT0:
1 → 0
```

Both are released.

---

# 108. Final example result

```text
L0 QUANTIZE  [0 → 0]
L1 CONV      [0 → 1]
L2 DW        [1 → 2]
L3 CONV      [2 → 0]
L4 ADD       [1,0 → 2]
```

Visually:

```text
                ┌──────────── SLOT1 ──────────────┐
                │                                  │
SLOT0 → L0 → SLOT0 → L1 → SLOT1 → L2 → SLOT2     │
                                      ↓            │
                                     L3            │
                                      ↓            │
                                    SLOT0          │
                                      │            │
                                      └──── L4 ADD ◄┘
                                             │
                                             ▼
                                           SLOT2
```

---

# 109. Relationship between liveness and residual connections

This example shows the module's most important point:

```text
L1's result remains live
even after L2 and L3
```

because there is still:

```text
L4
```

as a consumer.

Without this control, the residual connection would be destroyed.

---

# 110. Complexity

For each layer, the algorithm examines:

```text
inputs
slots
consumidores
```

Because the number of slots in the project is small and fixed:

```text
3
```

the cost of this stage is negligible compared with inference.

Conceptually, the cost depends approximately on:

```text
number of layers
+
number of graph relationships
```

---

# 111. What this module deliberately does not do

`slots.py` does not:

```text
calculate SLOT_BYTES
calculate SLOT0_BASE
calculate SLOT1_BASE
calculate SLOT2_BASE
read TFLite tensors
compute quantization
generate LayerParam
generate params_blob
generate WAT
```

It only answers:

```text
which logical slot does each layer read and write?
```

---

# 112. Why is this separation important?

If `slots.py` also calculated physical addresses, it would need to know:

```text
maximum tensor size
alignment
params_base
memory size
```

This would couple it to `memory.py`.

The current architecture keeps:

```text
slots.py
    ↓
logical identity

memory.py
    ↓
physical location
```

---

# 113. Final representation of the module

We can summarize it as follows:

```text
           graph.py
              │
              │ layers
              ▼
       ┌───────────────┐
       │   slots.py    │
       └───────────────┘
              │
        ┌─────┴─────┐
        ▼           ▼
 allocation   layer_output_slot
        │           │
        │           └──→ tensor_mapping.py
        │
        ├──→ report
        │
        └──→ layer_params.py
```

---

# 114. Relationship with the ESP32 memory problem

Choosing reusable slots is especially important in this project because the target device has limited resources.

A conceptually simple implementation could use:

```text
one region per tensor
```

But this would significantly increase memory consumption.

The adopted strategy is:

```text
determine lifetimes
       ↓
reuse regions
       ↓
reduce activation memory
```

---

# 115. Slots versus weights

Slots store:

```text
intermediate activations
```

rather than:

```text
weights
biases
multipliers
shifts
q6
LayerParams
```

These data have their own regions.

Conceptual layout:

```text
WASM memory

┌──────────────────────┐
│ initial region       │
├──────────────────────┤
│ WEIGHTS              │
├──────────────────────┤
│ BIAS                 │
├──────────────────────┤
│ MUL                  │
├──────────────────────┤
│ SHIFT                │
├──────────────────────┤
│ Q6                   │
├──────────────────────┤
│ PARAMS               │
├──────────────────────┤
│ SLOT0                │
├──────────────────────┤
│ SLOT1                │
├──────────────────────┤
│ SLOT2                │
└──────────────────────┘
```

`slots.py` only decides the logical occupancy of the last three regions.

---

# 116. Slots versus tensors

One slot can store many different tensors over the course of inference.

Example:

```text
SLOT1

tempo 1:
L1 output tensor

tempo 2:
L4 output tensor

tempo 3:
L7 output tensor
```

Therefore:

```text
slot ≠ tensor
```

The relationship is temporal:

```text
a tensor uses a slot during part of execution
```

---

# 117. Implication for debugging

When the report shows:

```text
L5 → SLOT1
```

this does not mean:

```text
SLOT1 always contains L5
```

It means:

```text
after L5 executes,
its output is placed in SLOT1
until it is consumed or safely overwritten
```

---

# 118. Why retain `in_place`

The field:

```python
"in_place": True
```

may seem redundant because:

```text
input_slot == output_slot
```

already reveals the sharing.

Keeping it makes the intention explicit.

One can imagine situations where:

```text
input_slot == output_slot
```

occurs for some other reason.

The flag states:

```text
this operation was deliberately planned to run in place
```

---

# 119. Difference between a free slot and an empty slot

The algorithm does not clear bytes when a slot is released.

Therefore:

```text
free slot
```

does not mean:

```text
memory contains zeros
```

It only means:

```text
the previous value is no longer semantically needed
```

The next operation can overwrite the region.

---

# 120. Importance of this distinction

After:

```text
SLOT1 released
```

it may still contain the previous activation's bytes.

This does not matter because no future layer should read them as that tensor.

Thus, "free" is a logical property, not a property of the physical contents.

---

# 121. Dependence on graph quality

This module's correctness depends directly on:

```text
layers_above
layers_below
```

being correct.

If `graph.py` omits a consumer:

```text
readers_count is lower than it should be
```

the slot may be reused too early.

Possible result:

```text
tensor overwritten before use
```

---

# 122. Chain of consequences of an error

```text
incorrect graph
      ↓
incorrect readers_count
      ↓
slot released too early
      ↓
another tensor overwrites memory
      ↓
future layer reads incorrect data
      ↓
incorrect inference
```

This shows that slot allocation is a critical stage even though it performs no neural operation.

---

# 123. Current validation

The algorithm has an explicit validation:

```python
if not available_slots:
    raise RuntimeError(...)
```

It detects:

```text
need for more slots
```

according to the computed state.

Other properties are checked indirectly during pipeline execution.

---

# 124. Possible future validations

A stricter future version could explicitly check:

```text
all input_slots are within range
all output_slots are within range
no layer references a nonexistent predecessor
every predecessor already has an output_slot
in-place execution only occurs for allowed types
```

Allocation could also be compared against a per-tensor lifetime analysis.

These improvements are not needed to explain the current behavior, but are natural validation paths.

---

# 125. Role of the report

`slot_allocation_to_text()` makes suspicious patterns immediately visible.

For example:

```text
CONV_2D             L10   [1 -> 2]
ADD                 L11   [1 e 2 -> 0]
```

is consistent with two distinct inputs.

An unexpected output such as:

```text
ADD                 L11   [1 e 1 -> 2]
```

may justify further inspection, depending on the graph.

---

# 126. The report is not used by inference

After the text is written:

```text
reports/03-alocacao-slots.txt
```

the pipeline does not read it again.

Therefore:

```text
report = observability
```

and:

```text
allocation = execution data
```

---

# 127. Structure summary

| Structure | Purpose |
| -------------------- | ------------------------------------------------------------------------ |
| `layer_output_slot` | Find the slot containing each layer's output |
| `slot_readers_count` | Track how many consumers still need each slot's contents |
| `allocation` | Record each layer's final allocation |
| `next_slot` | Indicate the preferred slot for the next output |
| `available_slots` | Slots that can be overwritten at that moment |

---

# 128. Summary of `allocation` fields

| Field | Meaning |
| ------------- | ------------------------------------------------- |
| `layer` | Logical layer label |
| `type` | Operation type |
| `input_slots` | Slots containing the inputs |
| `output_slot` | Slot where the output will be stored |
| `in_place` | Indicates deliberate reuse of the input slot |

---

# 129. Algorithm summary

The general logic can be represented as follows:

```text
for each layer
      │
      ▼
find input slots
      │
      ▼
is it QUANTIZE?
  │          │
 yes        no
  │          │
  ▼          ▼
reuse      find
input      free slots
  │          │
  │          ▼
  │       choose
  │       output_slot
  │          │
  │          ▼
  │       consume
  │       input readers
  │          │
  │          ▼
  │       record readers
  │       of the new output
  │          │
  └──────┬───┘
         ▼
record layer → slot
         │
         ▼
next layer
```

---

# 130. More abstract view

The problem solved by the module is:

```text
DEPENDENCY GRAPH
        │
        ▼
LIFETIME ANALYSIS
        │
        ▼
BUFFER REUSE
        │
        ▼
FEWER REQUIRED
ACTIVATION REGIONS
```

---

# 131. Role in the complete pipeline

At this point, the project can be understood as follows:

```text
┌──────────────────────────────┐
│          config.py           │
│                              │
│ defines NUM_SLOTS = 3        │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│          graph.py            │
│                              │
│ Lx → predecessors           │
│ Lx → consumers              │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│          slots.py            │
│                              │
│ Lx → input slots             │
│ Lx → output slot             │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│      tensor_mapping.py       │
│                              │
│ TFLite tensor → slot        │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│         memory.py            │
│                              │
│ slot → physical address     │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│      layer_params.py         │
│                              │
│ in_ptr / out_ptr             │
└──────────────────────────────┘
```

---

# 132. Summary

`slots.py` implements the transition between:

```text
logical dependency
```

and:

```text
concrete memory reuse
```

It does not yet know bytes or addresses, but decides an essential property:

```text
which result can occupy which region
without destroying data that will still be needed
```

The central logic is:

```text
does the output have consumers?
        │
        ▼
keep the slot protected

has the last consumer executed?
        │
        ▼
release the slot

does a new layer need an output?
        │
        ▼
choose an available slot
```

This strategy allows a network with dozens of layers to reuse just three large intermediate buffers instead of reserving an independent region for every layer output.

The code also preserves the special behavior of `QUANTIZE`, which currently runs in place, and makes the limitations of counting per slot explicit so future extractor generalizations can be deliberate and validated.
