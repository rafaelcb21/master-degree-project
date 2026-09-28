import math
import numpy as np

from extractor.tflite_utils import (
    op_name,
    qparams_np,
    scale_scalar,
    tensor_shape_list,
    zp_scalar,
)


INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1


QUANTIZED_WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}


def quantize_multiplier(
    real_multiplier: float,
):
    rm = float(real_multiplier)

    if rm == 0.0:
        return 0, 0

    q, exponent = math.frexp(
        rm
    )

    q31 = int(
        round(
            q * (1 << 31)
        )
    )

    if q31 == (1 << 31):
        q31 //= 2
        exponent += 1

    if q31 > INT32_MAX:
        q31 = INT32_MAX

    if q31 < INT32_MIN:
        q31 = INT32_MIN

    return (
        int(q31),
        int(exponent),
    )


def extract_quantization_parameters(
    model,
    subgraph,
):
    mul_vals = []
    shift_vals = []
    q6_vals = []

    mul_q6_off = {}

    records = []

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

        # ====================================================
        # SOFTMAX
        # ====================================================

        if op_type == "SOFTMAX":
            input_ids = [
                int(tensor_id)
                for tensor_id
                in op.InputsAsNumpy()
                if int(tensor_id) >= 0
            ]

            if len(input_ids) < 1:
                continue

            input_tensor = (
                subgraph.Tensors(
                    input_ids[0]
                )
            )

            input_scale = (
                scale_scalar(
                    input_tensor
                )
            )

            beta = 1.0
            integer_bits = 5

            input_left_shift = max(
                0,
                (
                    integer_bits
                    - int(
                        math.floor(
                            math.log2(
                                127.0
                                * input_scale
                                + 1e-9
                            )
                        )
                    )
                    - 1
                ),
            )

            real_multiplier = (
                beta * input_scale
            )

            (
                multiplier,
                shift,
            ) = quantize_multiplier(
                real_multiplier
            )

            mul_offset = (
                len(mul_vals) * 4
            )

            shift_offset = (
                len(shift_vals) * 4
            )

            mul_vals.append(
                int(multiplier)
            )

            shift_vals.append(
                int(shift)
            )

            mul_q6_off[op_idx] = (
                mul_offset,
                shift_offset,
                0,
                1,
            )

            records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,

                    "input_tensor_id": (
                        input_ids[0]
                    ),

                    "input_scale": (
                        input_scale
                    ),

                    "beta": beta,

                    "integer_bits": (
                        integer_bits
                    ),

                    "input_left_shift": (
                        input_left_shift
                    ),

                    "real_multiplier": (
                        real_multiplier
                    ),

                    "multipliers": [
                        int(multiplier)
                    ],

                    "shifts": [
                        int(shift)
                    ],

                    "q6": [],

                    "mul_offset": (
                        mul_offset
                    ),

                    "shift_offset": (
                        shift_offset
                    ),

                    "q6_offset": 0,

                    "nfeat": 1,
                }
            )

            continue

        # ====================================================
        # CONV / DEPTHWISE / FULLY CONNECTED
        # ====================================================

        if (
            op_type
            not in QUANTIZED_WEIGHT_OPERATORS
        ):
            continue

        input_ids = [
            int(tensor_id)
            for tensor_id
            in op.InputsAsNumpy()
            if int(tensor_id) >= 0
        ]

        output_ids = [
            int(tensor_id)
            for tensor_id
            in op.OutputsAsNumpy()
            if int(tensor_id) >= 0
        ]

        if (
            len(input_ids) < 2
            or len(output_ids) < 1
        ):
            continue

        input_tensor = (
            subgraph.Tensors(
                input_ids[0]
            )
        )

        weight_tensor = (
            subgraph.Tensors(
                input_ids[1]
            )
        )

        output_tensor = (
            subgraph.Tensors(
                output_ids[0]
            )
        )

        weight_shape = (
            tensor_shape_list(
                weight_tensor
            )
        )

        # ====================================================
        # NÚMERO DE FEATURES / CANAIS
        # ====================================================

        if op_type == "CONV_2D":
            nfeat = (
                int(weight_shape[0])
                if len(weight_shape) >= 1
                else None
            )

        elif (
            op_type
            == "DEPTHWISE_CONV_2D"
        ):
            nfeat = (
                int(weight_shape[3])
                if len(weight_shape) >= 4
                else None
            )

        else:
            nfeat = (
                int(weight_shape[0])
                if len(weight_shape) >= 1
                else None
            )

        if nfeat is None:
            continue

        # ====================================================
        # PARÂMETROS DE QUANTIZAÇÃO
        # ====================================================

        q_input = qparams_np(
            input_tensor
        )

        q_weights = qparams_np(
            weight_tensor
        )

        q_output = qparams_np(
            output_tensor
        )

        if (
            q_input is None
            or q_weights is None
            or q_output is None
        ):
            continue

        if (
            q_input["scales"].size == 0
            or q_weights["scales"].size == 0
            or q_output["scales"].size == 0
        ):
            continue

        input_scale = float(
            q_input["scales"][0]
        )

        weight_scales = (
            q_weights["scales"]
            .astype(np.float64)
        )

        output_scales = (
            q_output["scales"]
            .astype(np.float64)
        )

        output_scale = float(
            output_scales[0]
        )

        # ====================================================
        # OFFSETS
        # ====================================================

        mul_offset = (
            len(mul_vals) * 4
        )

        shift_offset = (
            len(shift_vals) * 4
        )

        q6_offset = (
            len(q6_vals) * 4
        )

        # Valores desta operação, usados no relatório.
        operation_multipliers = []
        operation_shifts = []
        real_multipliers = []

        # ====================================================
        # MULTIPLIER + SHIFT
        # ====================================================

        if weight_scales.size == 1:
            real_multiplier = (
                float(
                    weight_scales[0]
                )
                * input_scale
                / output_scale
            )

            (
                multiplier,
                shift,
            ) = quantize_multiplier(
                real_multiplier
            )

            operation_multipliers = [
                int(multiplier)
            ] * nfeat

            operation_shifts = [
                int(shift)
            ] * nfeat

            real_multipliers = [
                float(real_multiplier)
            ] * nfeat

        else:
            use = min(
                nfeat,
                weight_scales.size,
            )

            rm_values = (
                weight_scales[:use]
                * input_scale
                / output_scale
            )

            for rm in rm_values:
                (
                    multiplier,
                    shift,
                ) = quantize_multiplier(
                    rm
                )

                real_multipliers.append(
                    float(rm)
                )

                operation_multipliers.append(
                    int(multiplier)
                )

                operation_shifts.append(
                    int(shift)
                )

            # O legado possuía este bloco duplicado.
            # Aqui ele aparece apenas uma vez.
            if nfeat > use:
                missing = (
                    nfeat - use
                )

                operation_multipliers.extend(
                    [
                        operation_multipliers[-1]
                    ]
                    * missing
                )

                operation_shifts.extend(
                    [
                        operation_shifts[-1]
                    ]
                    * missing
                )

                real_multipliers.extend(
                    [
                        real_multipliers[-1]
                    ]
                    * missing
                )

        mul_vals.extend(
            operation_multipliers
        )

        shift_vals.extend(
            operation_shifts
        )

        # ====================================================
        # Q6
        # ====================================================

        output_zero_point = (
            zp_scalar(
                output_tensor
            )
        )

        operation_q6 = []

        if output_scales.size == 1:
            q6 = (
                int(
                    np.round(
                        6.0
                        / float(
                            output_scales[0]
                        )
                    )
                )
                + output_zero_point
            )

            operation_q6 = [
                q6
            ] * nfeat

        else:
            use = min(
                nfeat,
                output_scales.size,
            )

            q6_values = (
                np.round(
                    6.0
                    / output_scales[:use]
                )
                .astype(np.int64)
                + np.int64(
                    output_zero_point
                )
            )

            operation_q6.extend(
                int(value)
                for value
                in q6_values
            )

            if nfeat > use:
                operation_q6.extend(
                    [
                        int(
                            q6_values[-1]
                        )
                    ]
                    * (nfeat - use)
                )

        q6_vals.extend(
            operation_q6
        )

        # ====================================================
        # OFFSETS DA OPERAÇÃO
        # ====================================================

        mul_q6_off[op_idx] = (
            mul_offset,
            shift_offset,
            q6_offset,
            nfeat,
        )

        # ====================================================
        # DADOS PARA RELATÓRIO
        # ====================================================

        records.append(
            {
                "op_index": op_idx,
                "op_type": op_type,

                "input_tensor_id": (
                    input_ids[0]
                ),

                "weight_tensor_id": (
                    input_ids[1]
                ),

                "output_tensor_id": (
                    output_ids[0]
                ),

                "nfeat": nfeat,

                "input_scale": (
                    input_scale
                ),

                "weight_scales": [
                    float(value)
                    for value
                    in weight_scales
                ],

                "output_scales": [
                    float(value)
                    for value
                    in output_scales
                ],

                "output_zero_point": (
                    output_zero_point
                ),

                "real_multipliers": (
                    real_multipliers
                ),

                "multipliers": (
                    operation_multipliers
                ),

                "shifts": (
                    operation_shifts
                ),

                "q6": operation_q6,

                "mul_offset": (
                    mul_offset
                ),

                "shift_offset": (
                    shift_offset
                ),

                "q6_offset": (
                    q6_offset
                ),

                "weight_quantized_dimension": (
                    q_weights["qdim"]
                ),

                "output_quantized_dimension": (
                    q_output["qdim"]
                ),
            }
        )

    # ========================================================
    # BLOBS BINÁRIOS
    # ========================================================

    mul_blob = np.array(
        mul_vals,
        dtype="<i4",
    ).tobytes()

    shift_blob = np.array(
        shift_vals,
        dtype="<i4",
    ).tobytes()

    q6_blob = np.array(
        q6_vals,
        dtype="<i4",
    ).tobytes()

    return {
        "mul_vals": mul_vals,
        "shift_vals": shift_vals,
        "q6_vals": q6_vals,

        "mul_blob": mul_blob,
        "shift_blob": shift_blob,
        "q6_blob": q6_blob,

        "mul_q6_off": mul_q6_off,

        "records": records,
    }

def compute_add_quantization_params(
    scale_a,
    scale_b,
    scale_y,
):
    scale_common = max(
        scale_a,
        scale_b,
    ) * 2.0

    if (
        scale_a == 0.0
        and scale_b == 0.0
    ):
        return (
            0, 0,
            0, 0,
            0, 0,
            scale_common,
        )

    if scale_y == 0.0:
        return (
            0, 0,
            0, 0,
            0, 0,
            scale_common,
        )

    if scale_common == 0.0:
        return (
            0, 0,
            0, 0,
            0, 0,
            scale_common,
        )

    ratio_a = (
        scale_a
        / scale_common
    )

    mul_a, shift_a = (
        quantize_multiplier(
            ratio_a
        )
    )

    ratio_b = (
        scale_b
        / scale_common
    )

    mul_b, shift_b = (
        quantize_multiplier(
            ratio_b
        )
    )

    output_ratio = (
        scale_common
        / scale_y
    )

    (
        output_mul,
        output_shift,
    ) = quantize_multiplier(
        output_ratio
    )

    return (
        mul_a,
        shift_a,

        mul_b,
        shift_b,

        output_mul,
        output_shift,

        scale_common,
    )

def quantization_to_text(
    extraction,
):
    lines = []

    for record in extraction[
        "records"
    ]:
        lines.append(
            "=" * 80
        )

        lines.append(
            f"OP_INDEX: "
            f"{record['op_index']}"
        )

        lines.append(
            f"TIPO: "
            f"{record['op_type']}"
        )

        lines.append(
            f"NFEAT: "
            f"{record['nfeat']}"
        )

        lines.append("")

        lines.append(
            f"INPUT_SCALE: "
            f"{record['input_scale']}"
        )

        if (
            record["op_type"]
            == "SOFTMAX"
        ):
            lines.append(
                f"BETA: "
                f"{record['beta']}"
            )

            lines.append(
                f"INTEGER_BITS: "
                f"{record['integer_bits']}"
            )

            lines.append(
                f"INPUT_LEFT_SHIFT: "
                f"{record['input_left_shift']}"
            )

            lines.append(
                f"REAL_MULTIPLIER: "
                f"{record['real_multiplier']}"
            )

        else:
            lines.append(
                "WEIGHT_SCALES: "
                f"{record['weight_scales']}"
            )

            lines.append(
                "OUTPUT_SCALES: "
                f"{record['output_scales']}"
            )

            lines.append(
                "OUTPUT_ZERO_POINT: "
                f"{record['output_zero_point']}"
            )

            lines.append("")

            lines.append(
                "REAL_MULTIPLIERS: "
                f"{record['real_multipliers']}"
            )

        lines.append("")

        lines.append(
            "MULTIPLIERS: "
            f"{record['multipliers']}"
        )

        lines.append(
            "SHIFTS: "
            f"{record['shifts']}"
        )

        lines.append(
            "Q6: "
            f"{record['q6']}"
        )

        lines.append("")

        lines.append(
            "OFFSETS:"
        )

        lines.append(
            f"  MUL   = "
            f"{record['mul_offset']}"
        )

        lines.append(
            f"  SHIFT = "
            f"{record['shift_offset']}"
        )

        lines.append(
            f"  Q6    = "
            f"{record['q6_offset']}"
        )

        lines.append("")

    lines.append(
        "=" * 80
    )

    lines.append(
        "RESUMO"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        f"Quantidade de multipliers: "
        f"{len(extraction['mul_vals'])}"
    )

    lines.append(
        f"Quantidade de shifts: "
        f"{len(extraction['shift_vals'])}"
    )

    lines.append(
        f"Quantidade de Q6: "
        f"{len(extraction['q6_vals'])}"
    )

    lines.append(
        f"mul_blob: "
        f"{len(extraction['mul_blob'])} bytes"
    )

    lines.append(
        f"shift_blob: "
        f"{len(extraction['shift_blob'])} bytes"
    )

    lines.append(
        f"q6_blob: "
        f"{len(extraction['q6_blob'])} bytes"
    )

    return "\n".join(lines)