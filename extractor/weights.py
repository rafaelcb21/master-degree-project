from extractor.tflite_utils import (
    op_name,
    safe_bytes_from_tensor,
)


WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}


def extract_weights_and_bias(
    model,
    subgraph,
):
    """
    Extrai os pesos e bias das operações que possuem
    parâmetros treináveis.

    Retorna:
        weights_raw:
            bloco contínuo contendo os bytes dos pesos.

        bias_raw:
            bloco contínuo contendo os bytes dos bias.

        weight_tensor_off:
            tensor_id -> offset do peso dentro de weights_raw.

        bias_tensor_off:
            tensor_id -> offset do bias dentro de bias_raw.

        weight_records:
            metadados utilizados para relatório.

        bias_records:
            metadados utilizados para relatório.
    """

    weights_raw = bytearray()
    bias_raw = bytearray()

    weight_tensor_off = {}
    bias_tensor_off = {}

    weight_records = []
    bias_records = []

    for op_idx in range(
        subgraph.OperatorsLength()
    ):
        op = subgraph.Operators(
            op_idx
        )

        op_type = op_name(
            model,
            op,
        )

        if op_type not in WEIGHT_OPERATORS:
            continue

        input_ids = [
            int(tensor_id)
            for tensor_id
            in op.InputsAsNumpy()
            if int(tensor_id) >= 0
        ]

        # Essas operações precisam de pelo menos:
        #
        # input[0] = ativação
        # input[1] = pesos
        #
        if len(input_ids) < 2:
            continue

        # ====================================================
        # PESOS
        # ====================================================

        weight_tensor_id = input_ids[1]

        (
            weight_tensor,
            weight_array,
            weight_raw,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            weight_tensor_id,
        )

        if (
            weight_array is not None
            and weight_tensor_id
            not in weight_tensor_off
        ):
            offset = len(
                weights_raw
            )

            weight_tensor_off[
                weight_tensor_id
            ] = offset

            weights_raw.extend(
                weight_raw
            )

            weight_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        weight_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        weight_raw
                    ),
                    "shape": list(
                        weight_array.shape
                    ),
                    "dtype": str(
                        weight_array.dtype
                    ),
                }
            )

        # ====================================================
        # BIAS
        # ====================================================

        if len(input_ids) < 3:
            continue

        bias_tensor_id = input_ids[2]

        (
            bias_tensor,
            bias_array,
            bias_raw_tensor,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            bias_tensor_id,
        )

        if (
            bias_array is not None
            and bias_array.ndim == 1
            and bias_tensor_id
            not in bias_tensor_off
        ):
            offset = len(
                bias_raw
            )

            bias_tensor_off[
                bias_tensor_id
            ] = offset

            bias_raw.extend(
                bias_raw_tensor
            )

            bias_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        bias_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        bias_raw_tensor
                    ),
                    "shape": list(bias_array.shape),
                    "dtype": str(
                        bias_array.dtype
                    ),
                }
            )

    return {
        "weights_raw": bytes(
            weights_raw
        ),

        "bias_raw": bytes(
            bias_raw
        ),

        "weight_tensor_off": (
            weight_tensor_off
        ),

        "bias_tensor_off": (
            bias_tensor_off
        ),

        "weight_records": (
            weight_records
        ),

        "bias_records": (
            bias_records
        ),
    }

def weights_bias_to_text(
    extraction,
):
    lines = []

    lines.append(
        "PESOS"
    )
    lines.append(
        "=" * 80
    )

    for item in extraction[
        "weight_records"
    ]:
        lines.append(
            f"op={item['op_index']:3} "
            f"{item['op_type']:25} "
            f"tensor={item['tensor_id']:4} "
            f"offset={item['offset']:8} "
            f"bytes={item['nbytes']:8} "
            f"shape={item['shape']} "
            f"dtype={item['dtype']}"
        )

    lines.append("")
    lines.append(
        "BIAS"
    )
    lines.append(
        "=" * 80
    )

    for item in extraction[
        "bias_records"
    ]:
        lines.append(
            f"op={item['op_index']:3} "
            f"{item['op_type']:25} "
            f"tensor={item['tensor_id']:4} "
            f"offset={item['offset']:8} "
            f"bytes={item['nbytes']:8} "
            f"shape={item['shape']} "
            f"dtype={item['dtype']}"
        )

    lines.append("")
    lines.append(
        "RESUMO"
    )
    lines.append(
        "=" * 80
    )

    lines.append(
        "Total de tensors de pesos: "
        f"{len(extraction['weight_records'])}"
    )

    lines.append(
        "Total de bytes de pesos: "
        f"{len(extraction['weights_raw'])}"
    )

    lines.append(
        "Total de tensors de bias: "
        f"{len(extraction['bias_records'])}"
    )

    lines.append(
        "Total de bytes de bias: "
        f"{len(extraction['bias_raw'])}"
    )

    return "\n".join(lines)