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