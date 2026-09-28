# extractor/tensor_mapping.py

from extractor.tflite_utils import (
    is_constant_tensor,
    op_name,
)


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
    """
    Tenta descobrir o slot de um tensor seguindo
    recursivamente sua cadeia de produtores.
    """

    if visiting is None:
        visiting = set()

    # Evita ciclo durante a busca recursiva.
    if tensor_id in visiting:
        return None

    visiting.add(tensor_id)

    # O tensor já possui slot conhecido.
    if tensor_id in tensor_to_slot:
        return tensor_to_slot[tensor_id]

    # Descobre qual operador produziu o tensor.
    producer_op_idx = producer_by_tensor.get(
        tensor_id
    )

    if producer_op_idx is None:
        return None

    # ========================================================
    # PRODUTOR DIRETAMENTE REPRESENTADO NO GRAFO
    # ========================================================

    if producer_op_idx in old_idx_to_label:
        layer_name = old_idx_to_label[
            producer_op_idx
        ]

        output_slot = layer_output_slot.get(
            layer_name
        )

        if output_slot is not None:
            tensor_to_slot[tensor_id] = (
                output_slot
            )

            return output_slot

    # ========================================================
    # PRODUTOR NÃO REPRESENTADO DIRETAMENTE
    # ========================================================
    #
    # Nesse caso, segue os tensores de entrada do produtor
    # procurando uma origem que já possua slot conhecido.
    #

    producer_op = subgraph.Operators(
        producer_op_idx
    )

    for j in range(
        producer_op.InputsLength()
    ):
        input_tensor_id = int(
            producer_op.Inputs(j)
        )

        if input_tensor_id < 0:
            continue

        if is_constant_tensor(
            model,
            subgraph,
            input_tensor_id,
        ):
            continue

        slot = resolve_slot_from_producer(
            input_tensor_id,
            model=model,
            subgraph=subgraph,
            tensor_to_slot=tensor_to_slot,
            producer_by_tensor=producer_by_tensor,
            old_idx_to_label=old_idx_to_label,
            layer_output_slot=layer_output_slot,
            visiting=visiting.copy(),
        )

        if slot is not None:
            tensor_to_slot[tensor_id] = slot
            return slot

    return None


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
    """
    Constrói o mapeamento:

        tensor_id -> slot

    para todos os tensores não constantes que puderem
    ser associados à alocação lógica de memória.
    """

    tensor_to_slot = {}

    mapped_from_layers = []
    graph_input_mappings = []
    pending_before_resolution = []

    # ========================================================
    # 1. MAPEAR SAÍDAS DAS CAMADAS
    # ========================================================

    for alloc in slot_allocation:
        layer_name = alloc["layer"]

        op_idx = label_to_op_idx.get(
            layer_name
        )

        if op_idx is None:
            continue

        op = subgraph.Operators(op_idx)

        for j in range(
            op.OutputsLength()
        ):
            tensor_id = int(
                op.Outputs(j)
            )

            if tensor_id < 0:
                continue

            output_slot = alloc[
                "output_slot"
            ]

            tensor_to_slot[tensor_id] = (
                output_slot
            )

            mapped_from_layers.append(
                {
                    "tensor_id": tensor_id,
                    "layer": layer_name,
                    "op_index": op_idx,
                    "slot": output_slot,
                }
            )

    # ========================================================
    # 2. MAPEAR ENTRADAS DO SUBGRAFO
    # ========================================================

    graph_inputs = {
        int(subgraph.Inputs(i))
        for i in range(
            subgraph.InputsLength()
        )
    }

    for tensor_id in range(
        subgraph.TensorsLength()
    ):
        if tensor_id in tensor_to_slot:
            continue

        if is_constant_tensor(
            model,
            subgraph,
            tensor_id,
        ):
            continue

        if tensor_id in graph_inputs:
            tensor_to_slot[tensor_id] = 0

            graph_input_mappings.append(
                {
                    "tensor_id": tensor_id,
                    "slot": 0,
                }
            )

        else:
            pending_before_resolution.append(
                tensor_id
            )

    # ========================================================
    # 3. TENTAR RESOLVER TENSORES INTERMEDIÁRIOS
    # ========================================================

    for tensor_id in range(
        subgraph.TensorsLength()
    ):
        if tensor_id in tensor_to_slot:
            continue

        if is_constant_tensor(
            model,
            subgraph,
            tensor_id,
        ):
            continue

        resolve_slot_from_producer(
            tensor_id,
            model=model,
            subgraph=subgraph,
            tensor_to_slot=tensor_to_slot,
            producer_by_tensor=producer_by_tensor,
            old_idx_to_label=old_idx_to_label,
            layer_output_slot=layer_output_slot,
        )

    # ========================================================
    # 4. IDENTIFICAR TENSORES AINDA NÃO MAPEADOS
    # ========================================================

    unmapped_after = []

    for tensor_id in range(
        subgraph.TensorsLength()
    ):
        if is_constant_tensor(
            model,
            subgraph,
            tensor_id,
        ):
            continue

        if tensor_id not in tensor_to_slot:
            unmapped_after.append(
                tensor_id
            )

    return {
        "tensor_to_slot": tensor_to_slot,

        "graph_inputs": graph_inputs,

        "mapped_from_layers": (
            mapped_from_layers
        ),

        "graph_input_mappings": (
            graph_input_mappings
        ),

        "pending_before_resolution": (
            pending_before_resolution
        ),

        "unmapped_after": unmapped_after,
    }


def validate_tensor_slot_mapping(
    model,
    subgraph,
    *,
    tensor_to_slot,
    old_idx_to_label,
):
    """
    Verifica se todas as entradas e saídas
    não constantes dos operadores considerados
    possuem slot mapeado.
    """

    for op_idx in range(
        subgraph.OperatorsLength()
    ):
        # Somente operadores que fazem parte
        # do grafo utilizado pelo extrator.
        if op_idx not in old_idx_to_label:
            continue

        op = subgraph.Operators(
            op_idx
        )

        # ====================================================
        # VALIDAR INPUTS
        # ====================================================

        for j in range(
            op.InputsLength()
        ):
            tensor_id = int(
                op.Inputs(j)
            )

            if tensor_id < 0:
                continue

            if is_constant_tensor(
                model,
                subgraph,
                tensor_id,
            ):
                continue

            if tensor_id not in tensor_to_slot:
                raise RuntimeError(
                    "[MAP-ERROR] "
                    "input tensor sem slot: "
                    f"op_index={op_idx}, "
                    f"tensor_id={tensor_id}, "
                    f"op={op_name(model, op)}"
                )

        # ====================================================
        # VALIDAR OUTPUTS
        # ====================================================

        for j in range(
            op.OutputsLength()
        ):
            tensor_id = int(
                op.Outputs(j)
            )

            if tensor_id < 0:
                continue

            if tensor_id not in tensor_to_slot:
                raise RuntimeError(
                    "[MAP-ERROR] "
                    "output tensor sem slot: "
                    f"op_index={op_idx}, "
                    f"tensor_id={tensor_id}, "
                    f"op={op_name(model, op)}"
                )

    return True


def tensor_mapping_to_text(mapping):
    """
    Cria representação textual para relatório/debug.

    Não participa da lógica do mapeamento.
    """

    lines = []

    for item in mapping[
        "mapped_from_layers"
    ]:
        lines.append(
            f"tensor {item['tensor_id']} "
            f"(produzido por {item['layer']}) "
            f"-> slot {item['slot']}"
        )

    for item in mapping[
        "graph_input_mappings"
    ]:
        lines.append(
            f"tensor {item['tensor_id']} "
            "(input do subgrafo) "
            f"-> slot {item['slot']}"
        )

    pending = mapping[
        "pending_before_resolution"
    ]

    if pending:
        lines.append("")
        lines.append(
            "Tensores inicialmente pendentes:"
        )

        for tensor_id in pending:
            lines.append(
                f"  tensor {tensor_id}"
            )

    unmapped = mapping[
        "unmapped_after"
    ]

    lines.append("")

    lines.append(
        "Total de tensores mapeados: "
        f"{len(mapping['tensor_to_slot'])}"
    )

    if unmapped:
        lines.append(
            "Tensores sem slot após fechamento: "
            f"{unmapped}"
        )
    else:
        lines.append(
            "Fechamento de mapeamento: "
            "nenhum tensor não-constante pendente."
        )

    return "\n".join(lines)