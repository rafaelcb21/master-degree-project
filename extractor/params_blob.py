import struct

from extractor.layer_params import (
    LP_FMT,
    LP_SIZE,

    OP_CONV,
    OP_DW,
    OP_FC,
    OP_ADD,
    OP_MEAN,
    OP_SOFTMAX,
    OP_QUANTIZE,
    OP_RGB565_TO_RGB888,

    FLAG_PADDING_SAME,
    FLAG_HAS_Q6,
    FLAG_QUANTIZE_INPUT_INT8,
)

from extractor.operator_options import (
    ACT_NONE,
    ACT_RELU,
    ACT_RELU6,
)


# ============================================================
# NOMES PARA RELATÓRIO
# ============================================================


def op_type_name(op_type):
    return {
        OP_CONV: "CONV",
        OP_DW: "DW",
        OP_FC: "FC",
        OP_ADD: "ADD",
        OP_MEAN: "MEAN",
        OP_SOFTMAX: "SOFTMAX",
        OP_QUANTIZE: "QUANTIZE",
        OP_RGB565_TO_RGB888: "RGB565_TO_RGB888",
    }.get(
        op_type,
        str(op_type),
    )


def act_name(act):
    return {
        ACT_NONE: "NONE",
        ACT_RELU: "RELU",
        ACT_RELU6: "RELU6",
    }.get(
        act,
        str(act),
    )


def flags_pretty(
    flags,
    optype="",
):
    parts = []

    if optype == "QUANTIZE":
        if (
            flags
            & FLAG_QUANTIZE_INPUT_INT8
        ):
            parts.append(
                "INPUT_INT8"
            )
        else:
            parts.append(
                "INPUT_UINT8"
            )

    else:
        if (
            flags
            & FLAG_PADDING_SAME
        ):
            parts.append(
                "PADDING_SAME"
            )

        if (
            flags
            & FLAG_HAS_Q6
        ):
            parts.append(
                "HAS_Q6"
            )

    return (
        "|".join(parts)
        if parts
        else "0"
    )


# ============================================================
# PACK DO LAYER PARAM
# ============================================================


def pack_layerparam(
    op_type,
    act,
    flags,

    in_ptr,
    out_ptr,

    in_h,
    in_w,
    cin,
    cout,

    kh,
    kw,

    stride_h,
    stride_w,

    dil_h,
    dil_w,

    pad_t,
    pad_b,
    pad_l,
    pad_r,

    wptr,
    bias_ptr,

    mul_ptr,
    shift_ptr,
    q6_ptr,

    zx,
    zw,
    zy,

    out_h,
    out_w,
):
    values = [
        op_type,
        act,
        flags,

        in_ptr,
        out_ptr,

        in_h,
        in_w,
        cin,
        cout,

        kh,
        kw,

        stride_h,
        stride_w,

        dil_h,
        dil_w,

        pad_t,
        pad_b,
        pad_l,
        pad_r,

        wptr,
        bias_ptr,

        mul_ptr,
        shift_ptr,
        q6_ptr,

        zx,
        zw,
        zy,

        out_h,
        out_w,
    ]

    if len(values) != 29:
        raise RuntimeError(
            "LayerParam deve possuir "
            f"29 inteiros, recebeu "
            f"{len(values)}"
        )

    return struct.pack(
        LP_FMT,
        *[
            int(value)
            for value in values
        ],
    )


# ============================================================
# VALIDAÇÃO
# ============================================================


def validate_layer_params(
    layer_params,
    *,
    slot_bases,
):
    """
    Valida principalmente operações que possuem
    múltiplas entradas, como ADD.
    """

    for layer_index, params in enumerate(
        layer_params
    ):
        in_slot = params[
            "in_slot"
        ]

        out_slot = params[
            "out_slot"
        ]

        if not (
            0
            <= in_slot
            < len(slot_bases)
        ):
            raise RuntimeError(
                f"L{layer_index}: "
                f"in_slot inválido: "
                f"{in_slot}"
            )

        if not (
            0
            <= out_slot
            < len(slot_bases)
        ):
            raise RuntimeError(
                f"L{layer_index}: "
                f"out_slot inválido: "
                f"{out_slot}"
            )

        # ====================================================
        # ADD
        # ====================================================

        if (
            params["optype"]
            != "ADD"
        ):
            continue

        input_slots = params.get(
            "input_slots",
            [],
        )

        if len(input_slots) != 2:
            raise RuntimeError(
                f"ADD L{layer_index} "
                f"(op_index="
                f"{params['op_index']}): "
                "esperados exatamente "
                "2 input_slots"
            )

        slot_a = input_slots[0]
        slot_b = input_slots[1]

        if (
            params["in_slot"]
            != slot_a
        ):
            raise RuntimeError(
                f"ADD L{layer_index}: "
                "in_slot diferente de "
                "input_slots[0]"
            )

        expected_ptr_a = (
            slot_bases[
                slot_a
            ]
        )

        expected_ptr_b = (
            slot_bases[
                slot_b
            ]
        )

        if (
            params["pad_t"]
            != expected_ptr_a
        ):
            raise RuntimeError(
                f"ADD L{layer_index}: "
                "pad_t diferente da "
                "base do input A"
            )

        if (
            params["pad_b"]
            != expected_ptr_b
        ):
            raise RuntimeError(
                f"ADD L{layer_index}: "
                "pad_b diferente da "
                "base do input B"
            )

        if (
            params["pad_t"]
            not in slot_bases
        ):
            raise RuntimeError(
                f"ADD L{layer_index}: "
                f"pad_t fora de "
                f"slot_bases: "
                f"{params['pad_t']}"
            )

        if (
            params["pad_b"]
            not in slot_bases
        ):
            raise RuntimeError(
                f"ADD L{layer_index}: "
                f"pad_b fora de "
                f"slot_bases: "
                f"{params['pad_b']}"
            )

    return True


# ============================================================
# CONSTRUÇÃO DO PARAMS BLOB
# ============================================================


def build_params_blob(
    layer_params,
    *,
    slot_bases,
    params_bytes,
    parameter_layout,
):
    """
    Serializa todas as LayerParams em um bloco binário
    contínuo.

    Cada LayerParam possui LP_SIZE bytes.
    """

    validate_layer_params(
        layer_params,
        slot_bases=slot_bases,
    )

    kernel_base = (
        parameter_layout[
            "kernel_base"
        ]
    )

    bias_base = (
        parameter_layout[
            "bias_base"
        ]
    )

    mul_base = (
        parameter_layout[
            "mul_base"
        ]
    )

    shift_base = (
        parameter_layout[
            "shift_base"
        ]
    )

    q6_base = (
        parameter_layout[
            "q6_base"
        ]
    )

    params_blob = bytearray()

    records = []

    for (
        layer_index,
        params,
    ) in enumerate(
        layer_params
    ):
        # ====================================================
        # INPUT POINTER
        # ====================================================

        if (
            params["optype"]
            == "ADD"
        ):
            # ADD possui duas entradas.
            # O primeiro ponteiro vai em in_ptr.
            # O segundo permanece em pad_b.
            in_ptr = int(
                params["pad_t"]
            )

        else:
            in_ptr = int(
                slot_bases[
                    params["in_slot"]
                ]
            )

        # ====================================================
        # OUTPUT POINTER
        # ====================================================

        out_ptr = int(
            slot_bases[
                params["out_slot"]
            ]
        )

        # ====================================================
        # PESOS
        # ====================================================

        wptr = int(
            kernel_base
            + params["w_off"]
        )

        # ====================================================
        # BIAS
        # ====================================================

        if params["has_bias"]:
            bias_ptr = int(
                bias_base
                + params["b_off"]
            )
        else:
            bias_ptr = 0

        # ====================================================
        # MULTIPLIER
        # ====================================================

        if params["has_mulq6"]:
            mul_ptr = int(
                mul_base
                + params["mul_off"]
            )

            shift_ptr = int(
                shift_base
                + params["shift_off"]
            )

        else:
            mul_ptr = 0
            shift_ptr = 0

        # ====================================================
        # Q6
        # ====================================================

        if (
            params["has_mulq6"]
            and params["act"]
            == ACT_RELU6
        ):
            q6_ptr = int(
                q6_base
                + params["q6_off"]
            )

        else:
            q6_ptr = 0

        # ====================================================
        # OFFSET DENTRO DO PARAMS_BLOB
        # ====================================================

        blob_offset = len(
            params_blob
        )

        # ====================================================
        # SERIALIZAÇÃO
        # ====================================================

        packed = pack_layerparam(
            params["op_type"],
            params["act"],
            params["flags"],

            in_ptr,
            out_ptr,

            params["in_h"],
            params["in_w"],
            params["cin"],
            params["cout"],

            params["kh"],
            params["kw"],

            params["stride_h"],
            params["stride_w"],

            params["dil_h"],
            params["dil_w"],

            params["pad_t"],
            params["pad_b"],
            params["pad_l"],
            params["pad_r"],

            wptr,
            bias_ptr,

            mul_ptr,
            shift_ptr,
            q6_ptr,

            params["zx"],
            params["zw"],
            params["zy"],

            params["out_h"],
            params["out_w"],
        )

        if len(packed) != LP_SIZE:
            raise RuntimeError(
                f"L{layer_index}: "
                "LayerParam serializado com "
                f"{len(packed)} bytes; "
                f"esperado={LP_SIZE}"
            )

        params_blob.extend(
            packed
        )

        # ====================================================
        # METADADOS PARA RELATÓRIO
        # ====================================================

        records.append(
            {
                "layer_index": (
                    layer_index
                ),

                "blob_offset": (
                    blob_offset
                ),

                "op_index": (
                    params["op_index"]
                ),

                "optype": (
                    params["optype"]
                ),

                "op_type": (
                    params["op_type"]
                ),

                "act": (
                    params["act"]
                ),

                "flags": (
                    params["flags"]
                ),

                "in_slot": (
                    params["in_slot"]
                ),

                "out_slot": (
                    params["out_slot"]
                ),

                "input_slots": (
                    params.get(
                        "input_slots",
                        [],
                    )
                ),

                "in_ptr": in_ptr,
                "out_ptr": out_ptr,

                "wptr": wptr,

                "bias_ptr": (
                    bias_ptr
                ),

                "mul_ptr": (
                    mul_ptr
                ),

                "shift_ptr": (
                    shift_ptr
                ),

                "q6_ptr": (
                    q6_ptr
                ),

                "params": params,
            }
        )

    # ========================================================
    # VALIDAÇÃO DE TAMANHO
    # ========================================================

    used_bytes = len(
        params_blob
    )

    if used_bytes > params_bytes:
        raise RuntimeError(
            "params_blob maior que a "
            "área reservada: "
            f"{used_bytes} > "
            f"{params_bytes}"
        )

    # ========================================================
    # PADDING ATÉ PARAMS_BYTES
    # ========================================================

    padding_bytes = (
        params_bytes
        - used_bytes
    )

    if padding_bytes > 0:
        params_blob.extend(
            b"\x00"
            * padding_bytes
        )

    return {
        "params_blob": bytes(
            params_blob
        ),

        "records": records,

        "layer_count": len(
            layer_params
        ),

        "layer_param_size": (
            LP_SIZE
        ),

        "used_bytes": (
            used_bytes
        ),

        "padding_bytes": (
            padding_bytes
        ),

        "params_bytes": (
            params_bytes
        ),
    }


# ============================================================
# RELATÓRIO
# ============================================================


def params_blob_to_text(
    serialization,
):
    """
    Gera o relatório que substitui os antigos
    comentários/debug inseridos no WAT.
    """

    lines = []

    lines.append(
        "PARAMS BLOB"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        f"LayerParam size : "
        f"{serialization['layer_param_size']} bytes"
    )

    lines.append(
        f"Layers          : "
        f"{serialization['layer_count']}"
    )

    lines.append(
        f"Bytes usados    : "
        f"{serialization['used_bytes']}"
    )

    lines.append(
        f"Padding         : "
        f"{serialization['padding_bytes']}"
    )

    lines.append(
        f"Params bytes    : "
        f"{serialization['params_bytes']}"
    )

    lines.append("")

    # ========================================================
    # DUMP DAS CAMADAS SERIALIZADAS
    # ========================================================

    for record in serialization[
        "records"
    ]:
        params = record[
            "params"
        ]

        lines.append(
            "=" * 80
        )

        lines.append(
            f"L{record['layer_index']}"
        )

        lines.append(
            "=" * 80
        )

        lines.append(
            f"blob_offset       : "
            f"{record['blob_offset']}"
        )

        lines.append(
            f"op_index          : "
            f"{record['op_index']}"
        )

        lines.append(
            f"optype            : "
            f"{record['optype']}"
        )

        lines.append(
            f"op_type           : "
            f"{record['op_type']} "
            f"({op_type_name(record['op_type'])})"
        )

        lines.append(
            f"act               : "
            f"{params['act']} "
            f"({act_name(params['act'])})"
        )

        lines.append(
            f"flags             : "
            f"{params['flags']} "
            f"({flags_pretty(params['flags'], params['optype'])})"
        )

        input_slots = params.get(
            "input_slots",
            [],
        )

        if len(input_slots) > 1:
            lines.append(
                f"in_slots/out_slot : "
                f"{input_slots} "
                f"-> "
                f"{params['out_slot']}"
            )

        else:
            lines.append(
                f"in_slot/out_slot  : "
                f"{params['in_slot']} "
                f"-> "
                f"{params['out_slot']}"
            )

        lines.append(
            f"in_ptr/out_ptr    : "
            f"{record['in_ptr']} "
            f"-> "
            f"{record['out_ptr']}"
        )

        # ====================================================
        # QUANTIZAÇÃO ESPECIAL
        # ====================================================

        quant_params = params.get(
            "quant_params"
        )

        if quant_params:
            lines.append("")

            if (
                params["optype"]
                == "ADD"
            ):
                lines.append(
                    "ADD QUANTIZATION"
                )

                lines.append(
                    f"  sA/sB/sY          : "
                    f"{quant_params['sA']:.6f} / "
                    f"{quant_params['sB']:.6f} / "
                    f"{quant_params['sY']:.6f}"
                )

                lines.append(
                    f"  zA/zB/zY          : "
                    f"{quant_params['zA']} / "
                    f"{quant_params['zB']} / "
                    f"{quant_params['zY']}"
                )

                lines.append(
                    f"  s_common          : "
                    f"{quant_params['s_common']:.6f}"
                )

                lines.append(
                    f"  mul0/shift0       : "
                    f"{quant_params['mul0']} / "
                    f"{quant_params['shift0']}"
                )

                lines.append(
                    f"  mul1/shift1       : "
                    f"{quant_params['mul1']} / "
                    f"{quant_params['shift1']}"
                )

                lines.append(
                    f"  out_mul/out_shift : "
                    f"{quant_params['out_mul']} / "
                    f"{quant_params['out_shift']}"
                )

            elif (
                params["optype"]
                == "SOFTMAX"
            ):
                lines.append(
                    "SOFTMAX QUANTIZATION"
                )

                lines.append(
                    f"  sX/sY                : "
                    f"{quant_params['sX']:.6f} / "
                    f"{quant_params['sY']:.6f}"
                )

                lines.append(
                    f"  zX/zY                : "
                    f"{quant_params['zX']} / "
                    f"{quant_params['zY']}"
                )

                lines.append(
                    f"  beta                 : "
                    f"{quant_params['beta']:.6f}"
                )

                lines.append(
                    f"  integer_bits         : "
                    f"{quant_params['integer_bits']}"
                )

                lines.append(
                    f"  internal_scale       : "
                    f"{quant_params['internal_scale']:.6f}"
                )

                lines.append(
                    f"  input_beta_mul       : "
                    f"{quant_params['input_beta_mul']}"
                )

                lines.append(
                    f"  input_beta_left_shift: "
                    f"{quant_params['input_beta_left_shift']}"
                )

                lines.append(
                    f"  input_left_shift     : "
                    f"{quant_params['input_left_shift']}"
                )

                lines.append(
                    f"  diff_min             : "
                    f"{quant_params['diff_min']}"
                )

            elif (
                params["optype"]
                == "QUANTIZE"
            ):
                lines.append(
                    "QUANTIZE PARAMETERS"
                )

                lines.append(
                    f"  input_dtype : "
                    f"{quant_params['input_dtype']}"
                )

                lines.append(
                    f"  scale_in/out: "
                    f"{quant_params['scale_in']:.6f} / "
                    f"{quant_params['scale_out']:.6f}"
                )

                lines.append(
                    f"  zp_in/out   : "
                    f"{quant_params['zp_in']} / "
                    f"{quant_params['zp_out']}"
                )

                lines.append(
                    f"  ratio       : "
                    f"{quant_params['ratio']:.6f}"
                )

                lines.append(
                    f"  mul/shift   : "
                    f"{quant_params['mul']} / "
                    f"{quant_params['shift']}"
                )

        lines.append("")

        # ====================================================
        # GEOMETRIA
        # ====================================================

        lines.append(
            f"in_h/in_w         : "
            f"{params['in_h']} x "
            f"{params['in_w']}"
        )

        lines.append(
            f"cin/cout          : "
            f"{params['cin']} -> "
            f"{params['cout']}"
        )

        if (
            params["optype"]
            == "ADD"
        ):
            lines.append(
                f"kh/kw (mul0/sh0) : "
                f"{params['kh']} / "
                f"{params['kw']}"
            )

            lines.append(
                f"stride (mul1/sh1): "
                f"{params['stride_h']} / "
                f"{params['stride_w']}"
            )

            lines.append(
                f"dil (outM/outSh) : "
                f"{params['dil_h']} / "
                f"{params['dil_w']}"
            )

            lines.append(
                f"pad_t/b (inPtr)  : "
                f"{params['pad_t']} / "
                f"{params['pad_b']}"
            )

            lines.append(
                f"pad_l/r (zA/zB)  : "
                f"{params['pad_l']} / "
                f"{params['pad_r']}"
            )

        elif (
            params["optype"]
            == "MEAN"
        ):
            lines.append(
                f"kh/kw (mul/shift): "
                f"{params['kh']} / "
                f"{params['kw']}"
            )

            lines.append(
                f"stride_h spatial : "
                f"{params['stride_h']}"
            )

            lines.append(
                f"pad_t input_ptr  : "
                f"{params['pad_t']}"
            )

        elif (
            params["optype"]
            == "SOFTMAX"
        ):
            lines.append(
                f"kh/kw beta       : "
                f"{params['kh']} / "
                f"{params['kw']}"
            )

            lines.append(
                f"stride_h diff_min: "
                f"{params['stride_h']}"
            )

            # CORRETO:
            # stride_w armazena input_left_shift,
            # não integer_bits.
            lines.append(
                f"stride_w input_left_shift: "
                f"{params['stride_w']}"
            )

            lines.append(
                f"pad_t input_ptr  : "
                f"{params['pad_t']}"
            )

        elif (
            params["optype"]
            == "QUANTIZE"
        ):
            lines.append(
                f"kh/kw (mul/shift): "
                f"{params['kh']} / "
                f"{params['kw']}"
            )

            lines.append(
                f"pad_t input_ptr  : "
                f"{params['pad_t']}"
            )

        else:
            lines.append(
                f"kh/kw             : "
                f"{params['kh']} x "
                f"{params['kw']}"
            )

            lines.append(
                f"stride_h/stride_w : "
                f"{params['stride_h']} x "
                f"{params['stride_w']}"
            )

            lines.append(
                f"dil_h/dil_w       : "
                f"{params['dil_h']} x "
                f"{params['dil_w']}"
            )

            lines.append(
                f"pad t/b/l/r       : "
                f"{params['pad_t']} "
                f"{params['pad_b']} "
                f"{params['pad_l']} "
                f"{params['pad_r']}"
            )

        lines.append(
            f"out_h/out_w       : "
            f"{params['out_h']} x "
            f"{params['out_w']}"
        )

        if (
            params["optype"]
            == "DEPTHWISE_CONV_2D"
        ):
            lines.append(
                f"depth_mult        : "
                f"{params['depth_mult']}"
            )

        # ====================================================
        # OFFSETS E PONTEIROS
        # ====================================================

        lines.append("")

        lines.append(
            f"w_off/b_off       : "
            f"{params['w_off']} / "
            f"{params['b_off']}"
        )

        lines.append(
            f"mul_off           : "
            f"{params['mul_off']}"
        )

        lines.append(
            f"shift_off         : "
            f"{params['shift_off']}"
        )

        lines.append(
            f"q6_off            : "
            f"{params['q6_off']}"
        )

        lines.append(
            f"wptr              : "
            f"{record['wptr']}"
        )

        lines.append(
            f"bias_ptr          : "
            f"{record['bias_ptr']}"
        )

        lines.append(
            f"mul_ptr           : "
            f"{record['mul_ptr']}"
        )

        lines.append(
            f"shift_ptr         : "
            f"{record['shift_ptr']}"
        )

        lines.append(
            f"q6_ptr            : "
            f"{record['q6_ptr']}"
        )

        lines.append(
            f"zx/zw/zy          : "
            f"{params['zx']} / "
            f"{params['zw']} / "
            f"{params['zy']}"
        )

        lines.append("")

    return "\n".join(
        lines
    )