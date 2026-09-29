import math
import struct

from extractor.tflite_utils import (
    op_name,
    scale_scalar,
    zp_scalar,
    tensor_shape_list,
)

from extractor.quantization import (
    quantize_multiplier,
    compute_add_quantization_params,
)

from extractor.operator_options import (
    ACT_NONE,
    ACT_RELU6,
    parse_add_options,
    parse_conv2d_options,
    parse_dwconv2d_options,
    parse_fc_options,
    same_padding,
)


# ============================================================
# CONSTANTES DO LAYER PARAM
# ============================================================

LP_FMT = "<" + "i" * 29
LP_SIZE = struct.calcsize(LP_FMT)

OP_CONV = 1
OP_DW = 2
OP_FC = 3
OP_ADD = 4
OP_MEAN = 5
OP_SOFTMAX = 6
OP_QUANTIZE = 7
OP_RGB565_TO_RGB888 = 8

FLAG_PADDING_SAME = 1 << 0
FLAG_HAS_Q6 = 1 << 1

FLAG_QUANTIZE_INPUT_INT8 = FLAG_PADDING_SAME
FLAG_QUANTIZE_OUTPUT_UINT8 = 1 << 1

TFLITE_UINT8 = 3
TFLITE_INT8 = 9

FORMAT_FLAG_ADDR = 0
FORMAT_RGB565 = 65

INPUT_FORMAT_SLOT = 0
RGB888_SLOT = 1

# ============================================================
# HELPERS
# ============================================================

def tensor_hwc(tensor):
    shape = tensor_shape_list(tensor)

    height = (
        shape[1]
        if len(shape) >= 3
        else 1
    )

    width = (
        shape[2]
        if len(shape) >= 3
        else 1
    )

    channels = (
        shape[3]
        if len(shape) >= 4
        else (
            shape[1]
            if len(shape) == 2
            else 1
        )
    )

    return (
        shape,
        int(height),
        int(width),
        int(channels),
    )

def build_runtime_tensor_mapping(
    subgraph,
    *,
    graph_inputs,
    slot_allocation,
    label_to_op_idx,
    num_slots,
    slot_shift,
):
    tensor_to_slot = {}

    records = []

    # Input original passa a entrar pelo
    # slot de saída da conversão RGB.
    for tensor_id in graph_inputs:
        tensor_to_slot[
            tensor_id
        ] = slot_shift

    for alloc in slot_allocation:
        label = alloc["layer"]

        op_idx = (
            label_to_op_idx.get(
                label
            )
        )

        if op_idx is None:
            continue

        op = subgraph.Operators(
            op_idx
        )

        original_slot = (
            alloc["output_slot"]
        )

        runtime_slot = (
            original_slot
            + slot_shift
        ) % num_slots

        for j in range(
            op.OutputsLength()
        ):
            tensor_id = int(
                op.Outputs(j)
            )

            if tensor_id < 0:
                continue

            tensor_to_slot[
                tensor_id
            ] = runtime_slot

            records.append(
                {
                    "tensor_id": tensor_id,
                    "layer": label,
                    "original_slot": (
                        original_slot
                    ),
                    "runtime_slot": (
                        runtime_slot
                    ),
                }
            )

    return {
        "tensor_to_slot": (
            tensor_to_slot
        ),

        "records": records,

        "slot_shift": (
            slot_shift
        ),
    }

def calculate_layer_memory_layout(
    *,
    real_layer_count,
    synthetic_layer_count,
    layer_param_size,
    params_base,
    slot_bytes,
    num_slots,
    alignment,
):
    num_layers = (
        real_layer_count
        + synthetic_layer_count
    )

    params_bytes = (
        (
            num_layers
            * layer_param_size
            + alignment - 1
        )
        // alignment
        * alignment
    )

    slot0_base = (
        (
            params_base
            + params_bytes
            + alignment - 1
        )
        // alignment
        * alignment
    )

    slot_bases = [
        slot0_base
    ]

    for _ in range(
        1,
        num_slots,
    ):
        next_base = (
            slot_bases[-1]
            + slot_bytes
        )

        next_base = (
            (
                next_base
                + alignment - 1
            )
            // alignment
            * alignment
        )

        slot_bases.append(
            next_base
        )

    return {
        "num_layers": num_layers,
        "params_bytes": params_bytes,
        "slot_bases": slot_bases,
    }

# ============================================================
# CAMADA SINTÉTICA RGB565 → RGB888
# ============================================================

def build_rgb565_layer(
    subgraph,
    *,
    slot_bases,
):
    graph_input_id = int(
        subgraph.Inputs(0)
    )

    graph_input_tensor = (
        subgraph.Tensors(
            graph_input_id
        )
    )

    (
        _,
        input_h,
        input_w,
        input_channels,
    ) = tensor_hwc(
        graph_input_tensor
    )

    return {
        "op_index": -1,
        "optype": "RGB565_TO_RGB888",
        "op_type": OP_RGB565_TO_RGB888,

        "act": ACT_NONE,
        "flags": FORMAT_FLAG_ADDR,

        "in_slot": INPUT_FORMAT_SLOT,
        "out_slot": RGB888_SLOT,

        "in_h": input_h,
        "in_w": input_w,

        "cin": input_channels,
        "cout": input_channels,

        "kh": FORMAT_RGB565,
        "kw": 0,

        "stride_h": 0,
        "stride_w": 0,

        "dil_h": 1,
        "dil_w": 1,

        "pad_t": 0,
        "pad_b": 0,
        "pad_l": 0,
        "pad_r": 0,

        "out_h": input_h,
        "out_w": input_w,

        "w_off": 0,

        "has_bias": False,
        "b_off": 0,

        "has_mulq6": False,
        "mul_off": 0,
        "shift_off": 0,
        "q6_off": 0,

        "zx": 0,
        "zw": 0,
        "zy": 0,

        "depth_mult": 1,

        "input_slots": [
            INPUT_FORMAT_SLOT
        ],

        "input_ptrs": [
            slot_bases[
                INPUT_FORMAT_SLOT
            ]
        ],
    }

# ============================================================
# BUILDERS POR TIPO DE OPERAÇÃO
# ============================================================


def _build_quantize_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
):
    if len(input_ids) < 1:
        raise RuntimeError(
            f"QUANTIZE op_index={op_idx}: "
            "nenhum tensor de entrada"
        )

    input_tensor = subgraph.Tensors(
        input_ids[0]
    )

    output_tensor = subgraph.Tensors(
        output_ids[0]
    )

    (
        _,
        in_h,
        in_w,
        cin,
    ) = tensor_hwc(
        input_tensor
    )

    (
        _,
        out_h,
        out_w,
        cout,
    ) = tensor_hwc(
        output_tensor
    )

    scale_in = scale_scalar(
        input_tensor
    )

    zp_in = zp_scalar(
        input_tensor
    )

    scale_out = scale_scalar(
        output_tensor
    )

    zp_out = zp_scalar(
        output_tensor
    )

    if scale_out == 0.0:
        raise RuntimeError(
            f"QUANTIZE op_index={op_idx}: "
            "scale_out=0"
        )

    ratio = (
        scale_in
        / scale_out
    )

    (
        multiplier,
        shift,
    ) = quantize_multiplier(
        ratio
    )

    input_tensor_id = input_ids[0]

    if input_tensor_id not in tensor_to_slot:
        raise RuntimeError(
            f"QUANTIZE op_index={op_idx}: "
            "input tensor sem slot mapeado "
            f"(tensor_id={input_tensor_id})"
        )

    in_slot = tensor_to_slot[
        input_tensor_id
    ]

    input_ptr = slot_bases[
        in_slot
    ]

    input_dtype = int(
        input_tensor.Type()
    )

    if input_dtype == TFLITE_INT8:
        flags = (
            FLAG_QUANTIZE_INPUT_INT8
        )

        input_dtype_name = "int8"

    elif input_dtype == TFLITE_UINT8:
        flags = 0
        input_dtype_name = "uint8"

    else:
        flags = 0

        input_dtype_name = (
            f"unknown({input_dtype})"
        )

    if output_tensor.Type() == TFLITE_UINT8:
        flags |= FLAG_QUANTIZE_OUTPUT_UINT8
    elif output_tensor.Type() != TFLITE_INT8:
        raise ValueError("QUANTIZE suporta apenas saída UINT8 ou INT8.")

    # QUANTIZE é in-place.
    # Mesmo que out_slot tenha sido passado,
    # a saída permanece no slot da entrada.
    out_slot = in_slot

    return {
        "label": label,

        "op_index": op_idx,
        "optype": "QUANTIZE",
        "op_type": OP_QUANTIZE,

        "act": ACT_NONE,
        "flags": flags,

        "in_slot": in_slot,
        "out_slot": out_slot,

        "in_h": int(in_h),
        "in_w": int(in_w),

        "cin": int(cin),
        "cout": int(cout),

        # Para QUANTIZE:
        # kh = multiplier
        # kw = shift
        "kh": int(multiplier),
        "kw": int(shift),

        "stride_h": 0,
        "stride_w": 0,

        "dil_h": 1,
        "dil_w": 1,

        # Para QUANTIZE:
        # pad_t = endereço da entrada
        "pad_t": int(input_ptr),

        "pad_b": 0,
        "pad_l": 0,
        "pad_r": 0,

        "out_h": int(out_h),
        "out_w": int(out_w),

        "w_off": 0,

        "has_bias": False,
        "b_off": 0,

        "has_mulq6": False,

        "mul_off": 0,
        "shift_off": 0,
        "q6_off": 0,

        "zx": int(zp_in),
        "zw": 0,
        "zy": int(zp_out),

        "depth_mult": 1,

        "input_slots": [
            in_slot
        ],

        "input_ptrs": [
            int(input_ptr)
        ],

        "quant_params": {
            "scale_in": float(
                scale_in
            ),

            "scale_out": float(
                scale_out
            ),

            "zp_in": int(
                zp_in
            ),

            "zp_out": int(
                zp_out
            ),

            "ratio": float(
                ratio
            ),

            "mul": int(
                multiplier
            ),

            "shift": int(
                shift
            ),

            "input_dtype": (
                input_dtype_name
            ),

            "input_dtype_code": (
                input_dtype
            ),
        },
    }


def _build_add_params(
    subgraph,
    *,
    op_idx,
    op,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
):
    if len(input_ids) < 2:
        raise RuntimeError(
            f"ADD op_index={op_idx}: "
            "menos de duas entradas"
        )

    input_tensor_a = (
        subgraph.Tensors(
            input_ids[0]
        )
    )

    input_tensor_b = (
        subgraph.Tensors(
            input_ids[1]
        )
    )

    output_tensor = (
        subgraph.Tensors(
            output_ids[0]
        )
    )

    (
        _,
        in_h,
        in_w,
        cin,
    ) = tensor_hwc(
        input_tensor_a
    )

    (
        _,
        out_h,
        out_w,
        cout,
    ) = tensor_hwc(
        output_tensor
    )

    scale_a = scale_scalar(
        input_tensor_a
    )

    zp_a = zp_scalar(
        input_tensor_a
    )

    scale_b = scale_scalar(
        input_tensor_b
    )

    zp_b = zp_scalar(
        input_tensor_b
    )

    scale_y = scale_scalar(
        output_tensor
    )

    zp_y = zp_scalar(
        output_tensor
    )

    (
        mul_a,
        shift_a,
        mul_b,
        shift_b,
        output_mul,
        output_shift,
        scale_common,
    ) = compute_add_quantization_params(
        scale_a,
        scale_b,
        scale_y,
    )

    activation = (
        parse_add_options(
            op
        )
    )

    tensor_id_a = input_ids[0]
    tensor_id_b = input_ids[1]

    if (
        tensor_id_a
        not in tensor_to_slot
    ):
        raise RuntimeError(
            f"ADD op_index={op_idx}: "
            "input A sem slot "
            f"(tensor_id={tensor_id_a})"
        )

    if (
        tensor_id_b
        not in tensor_to_slot
    ):
        raise RuntimeError(
            f"ADD op_index={op_idx}: "
            "input B sem slot "
            f"(tensor_id={tensor_id_b})"
        )

    slot_a = tensor_to_slot[
        tensor_id_a
    ]

    slot_b = tensor_to_slot[
        tensor_id_b
    ]

    input_ptr_a = slot_bases[
        slot_a
    ]

    input_ptr_b = slot_bases[
        slot_b
    ]

    return {
        "label": label,

        "op_index": op_idx,
        "optype": "ADD",
        "op_type": OP_ADD,

        "act": activation,
        "flags": 0,

        "in_slot": slot_a,
        "out_slot": out_slot,

        "in_h": int(in_h),
        "in_w": int(in_w),

        "cin": int(cin),
        "cout": int(cout),

        # ADD:
        #
        # kh       = multiplier input A
        # kw       = shift input A
        # stride_h = multiplier input B
        # stride_w = shift input B
        # dil_h    = multiplier output
        # dil_w    = shift output
        "kh": int(mul_a),
        "kw": int(shift_a),

        "stride_h": int(mul_b),
        "stride_w": int(shift_b),

        "dil_h": int(output_mul),
        "dil_w": int(output_shift),

        # ADD:
        #
        # pad_t = ptr input A
        # pad_b = ptr input B
        # pad_l = zero point A
        # pad_r = zero point B
        "pad_t": int(input_ptr_a),
        "pad_b": int(input_ptr_b),

        "pad_l": int(zp_a),
        "pad_r": int(zp_b),

        "out_h": int(out_h),
        "out_w": int(out_w),

        "w_off": 0,

        "has_bias": False,
        "b_off": 0,

        "has_mulq6": False,

        "mul_off": 0,
        "shift_off": 0,
        "q6_off": 0,

        "zx": int(zp_a),
        "zw": int(zp_b),
        "zy": int(zp_y),

        "depth_mult": 1,

        "input_slots": [
            slot_a,
            slot_b,
        ],

        "input_ptrs": [
            int(input_ptr_a),
            int(input_ptr_b),
        ],

        "quant_params": {
            "sA": float(
                scale_a
            ),

            "sB": float(
                scale_b
            ),

            "sY": float(
                scale_y
            ),

            "zA": int(
                zp_a
            ),

            "zB": int(
                zp_b
            ),

            "zY": int(
                zp_y
            ),

            "mul0": int(
                mul_a
            ),

            "shift0": int(
                shift_a
            ),

            "mul1": int(
                mul_b
            ),

            "shift1": int(
                shift_b
            ),

            "out_mul": int(
                output_mul
            ),

            "out_shift": int(
                output_shift
            ),

            "s_common": float(
                scale_common
            ),
        },
    }


def _build_mean_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
):
    if len(input_ids) < 1:
        raise RuntimeError(
            f"MEAN op_index={op_idx}: "
            "nenhuma entrada"
        )

    input_tensor = (
        subgraph.Tensors(
            input_ids[0]
        )
    )

    output_tensor = (
        subgraph.Tensors(
            output_ids[0]
        )
    )

    (
        _,
        in_h,
        in_w,
        cin,
    ) = tensor_hwc(
        input_tensor
    )

    (
        _,
        out_h,
        out_w,
        cout,
    ) = tensor_hwc(
        output_tensor
    )

    scale_x = scale_scalar(
        input_tensor
    )

    zp_x = zp_scalar(
        input_tensor
    )

    scale_y = scale_scalar(
        output_tensor
    )

    zp_y = zp_scalar(
        output_tensor
    )

    if scale_y == 0.0:
        raise RuntimeError(
            f"MEAN op_index={op_idx}: "
            "scale_y=0"
        )

    ratio = (
        scale_x
        / scale_y
    )

    (
        multiplier,
        shift,
    ) = quantize_multiplier(
        ratio
    )

    input_tensor_id = (
        input_ids[0]
    )

    if (
        input_tensor_id
        not in tensor_to_slot
    ):
        raise RuntimeError(
            f"MEAN op_index={op_idx}: "
            "input tensor sem slot "
            f"(tensor_id={input_tensor_id})"
        )

    in_slot = tensor_to_slot[
        input_tensor_id
    ]

    input_ptr = slot_bases[
        in_slot
    ]

    spatial_size = (
        int(in_h)
        * int(in_w)
    )

    return {
        "label": label,

        "op_index": op_idx,
        "optype": "MEAN",
        "op_type": OP_MEAN,

        "act": ACT_NONE,
        "flags": 0,

        "in_slot": in_slot,
        "out_slot": out_slot,

        "in_h": int(in_h),
        "in_w": int(in_w),

        "cin": int(cin),
        "cout": int(cout),

        # MEAN:
        #
        # kh = multiplier
        # kw = shift
        "kh": int(multiplier),
        "kw": int(shift),

        # MEAN:
        # stride_h = número de elementos espaciais
        "stride_h": int(
            spatial_size
        ),

        "stride_w": 1,

        "dil_h": 1,
        "dil_w": 1,

        # MEAN:
        # pad_t = input pointer
        "pad_t": int(input_ptr),

        "pad_b": 0,
        "pad_l": 0,
        "pad_r": 0,

        "out_h": int(out_h),
        "out_w": int(out_w),

        "w_off": 0,

        "has_bias": False,
        "b_off": 0,

        "has_mulq6": False,

        "mul_off": 0,
        "shift_off": 0,
        "q6_off": 0,

        "zx": int(zp_x),
        "zw": 0,
        "zy": int(zp_y),

        "depth_mult": 1,

        "input_slots": [
            in_slot
        ],

        "input_ptrs": [
            int(input_ptr)
        ],

        "quant_params": {
            "sX": float(
                scale_x
            ),

            "sY": float(
                scale_y
            ),

            "zX": int(
                zp_x
            ),

            "zY": int(
                zp_y
            ),

            "ratio": float(
                ratio
            ),

            "mul": int(
                multiplier
            ),

            "shift": int(
                shift
            ),

            "spatial_size": int(
                spatial_size
            ),
        },
    }


def _build_softmax_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    mul_q6_off,
):
    if len(input_ids) < 1:
        raise RuntimeError(
            f"SOFTMAX op_index={op_idx}: "
            "nenhuma entrada"
        )

    input_tensor = (
        subgraph.Tensors(
            input_ids[0]
        )
    )

    output_tensor = (
        subgraph.Tensors(
            output_ids[0]
        )
    )

    (
        _,
        in_h,
        in_w,
        cin,
    ) = tensor_hwc(
        input_tensor
    )

    (
        _,
        out_h,
        out_w,
        cout,
    ) = tensor_hwc(
        output_tensor
    )

    scale_x = scale_scalar(
        input_tensor
    )

    zp_x = zp_scalar(
        input_tensor
    )

    scale_y = scale_scalar(
        output_tensor
    )

    zp_y = zp_scalar(
        output_tensor
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
                        * scale_x
                        + 1e-9
                    )
                )
            )
            - 1
        ),
    )

    internal_scale = (
        1.0
        / (1 << integer_bits)
    )

    real_multiplier = (
        beta
        * scale_x
    )

    (
        input_beta_mul,
        input_beta_left_shift,
    ) = quantize_multiplier(
        real_multiplier
    )

    diff_min = -128

    input_tensor_id = (
        input_ids[0]
    )

    if (
        input_tensor_id
        not in tensor_to_slot
    ):
        raise RuntimeError(
            f"SOFTMAX op_index={op_idx}: "
            "input tensor sem slot "
            f"(tensor_id={input_tensor_id})"
        )

    in_slot = tensor_to_slot[
        input_tensor_id
    ]

    input_ptr = slot_bases[
        in_slot
    ]

    has_mulq6 = (
        op_idx in mul_q6_off
    )

    if has_mulq6:
        mul_off = int(
            mul_q6_off[
                op_idx
            ][0]
        )

        shift_off = int(
            mul_q6_off[
                op_idx
            ][1]
        )

    else:
        mul_off = 0
        shift_off = 0

    return {
        "label": label,

        "op_index": op_idx,
        "optype": "SOFTMAX",
        "op_type": OP_SOFTMAX,

        "act": ACT_NONE,
        "flags": 0,

        "in_slot": in_slot,
        "out_slot": out_slot,

        "in_h": int(in_h),
        "in_w": int(in_w),

        "cin": int(cin),
        "cout": int(cout),

        # SOFTMAX:
        #
        # kh = input_beta_mul
        # kw = input_beta_left_shift
        "kh": int(
            input_beta_mul
        ),

        "kw": int(
            input_beta_left_shift
        ),

        # Mantém exatamente o comportamento
        # do código original.
        "stride_h": int(
            diff_min
        ),

        "stride_w": int(
            input_left_shift
        ),

        "dil_h": 1,
        "dil_w": 1,

        # SOFTMAX:
        # pad_t = input pointer
        "pad_t": int(
            input_ptr
        ),

        "pad_b": 0,
        "pad_l": 0,
        "pad_r": 0,

        "out_h": int(out_h),
        "out_w": int(out_w),

        "w_off": 0,

        "has_bias": False,
        "b_off": 0,

        "has_mulq6": bool(
            has_mulq6
        ),

        "mul_off": int(
            mul_off
        ),

        "shift_off": int(
            shift_off
        ),

        "q6_off": 0,

        "zx": int(zp_x),
        "zw": 0,
        "zy": int(zp_y),

        "depth_mult": 1,

        "input_slots": [
            in_slot
        ],

        "input_ptrs": [
            int(input_ptr)
        ],

        "quant_params": {
            "sX": float(
                scale_x
            ),

            "sY": float(
                scale_y
            ),

            "zX": int(
                zp_x
            ),

            "zY": int(
                zp_y
            ),

            "beta": float(
                beta
            ),

            "integer_bits": int(
                integer_bits
            ),

            "internal_scale": float(
                internal_scale
            ),

            "real_multiplier": float(
                real_multiplier
            ),

            "input_beta_mul": int(
                input_beta_mul
            ),

            "input_beta_left_shift": int(
                input_beta_left_shift
            ),

            "input_left_shift": int(
                input_left_shift
            ),

            "diff_min": int(
                diff_min
            ),
        },
    }


def _build_weighted_params(
    subgraph,
    *,
    op_idx,
    op,
    op_type_name,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
):
    if len(input_ids) < 2:
        raise RuntimeError(
            f"{op_type_name} "
            f"op_index={op_idx}: "
            "menos de duas entradas"
        )

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

    bias_id = (
        int(input_ids[2])
        if len(input_ids) >= 3
        else -1
    )

    (
        _,
        in_h,
        in_w,
        cin,
    ) = tensor_hwc(
        input_tensor
    )

    (
        output_shape,
        out_h,
        out_w,
        _,
    ) = tensor_hwc(
        output_tensor
    )

    weight_shape = (
        tensor_shape_list(
            weight_tensor
        )
    )

    stride_h = 1
    stride_w = 1

    dil_h = 1
    dil_w = 1

    pad_t = 0
    pad_b = 0
    pad_l = 0
    pad_r = 0

    activation = ACT_NONE

    flags = 0
    depth_mult = 1

    # ========================================================
    # CONV_2D
    # ========================================================

    if op_type_name == "CONV_2D":
        op_type = OP_CONV

        cout = (
            int(weight_shape[0])
            if len(weight_shape) >= 1
            else int(
                output_shape[3]
                if len(output_shape) >= 4
                else 1
            )
        )

        kernel_h = (
            int(weight_shape[1])
            if len(weight_shape) >= 2
            else 1
        )

        kernel_w = (
            int(weight_shape[2])
            if len(weight_shape) >= 3
            else 1
        )

        (
            stride_h,
            stride_w,
            dil_h,
            dil_w,
            padding_kind,
            activation,
        ) = parse_conv2d_options(
            op
        )

        if padding_kind == 0:
            flags |= (
                FLAG_PADDING_SAME
            )

    # ========================================================
    # DEPTHWISE_CONV_2D
    # ========================================================

    elif (
        op_type_name
        == "DEPTHWISE_CONV_2D"
    ):
        op_type = OP_DW

        kernel_h = (
            int(weight_shape[1])
            if len(weight_shape) >= 2
            else 1
        )

        kernel_w = (
            int(weight_shape[2])
            if len(weight_shape) >= 3
            else 1
        )

        cout = (
            int(weight_shape[3])
            if len(weight_shape) >= 4
            else int(
                output_shape[3]
                if len(output_shape) >= 4
                else 1
            )
        )

        (
            stride_h,
            stride_w,
            dil_h,
            dil_w,
            padding_kind,
            activation,
            depth_mult,
        ) = parse_dwconv2d_options(
            op
        )

        if padding_kind == 0:
            flags |= (
                FLAG_PADDING_SAME
            )

    # ========================================================
    # FULLY_CONNECTED
    # ========================================================

    elif (
        op_type_name
        == "FULLY_CONNECTED"
    ):
        op_type = OP_FC

        cout = (
            int(weight_shape[0])
            if len(weight_shape) >= 1
            else int(
                output_shape[1]
                if len(output_shape) >= 2
                else 1
            )
        )

        kernel_h = 1
        kernel_w = 1

        activation = (
            parse_fc_options(
                op
            )
        )

    else:
        raise RuntimeError(
            f"Operação não suportada "
            f"em _build_weighted_params: "
            f"{op_type_name}"
        )

    # ========================================================
    # RELU6
    # ========================================================

    if activation == ACT_RELU6:
        flags |= FLAG_HAS_Q6

    # ========================================================
    # SAME PADDING
    # ========================================================

    if (
        flags
        & FLAG_PADDING_SAME
    ) != 0:
        (
            pad_t,
            pad_b,
            pad_l,
            pad_r,
            out_h,
            out_w,
        ) = same_padding(
            in_h,
            in_w,

            kernel_h,
            kernel_w,

            stride_h,
            stride_w,

            dil_h,
            dil_w,
        )

    # ========================================================
    # ZERO POINTS
    # ========================================================

    zp_x = zp_scalar(
        input_tensor
    )

    zp_w = zp_scalar(
        weight_tensor
    )

    zp_y = zp_scalar(
        output_tensor
    )

    # ========================================================
    # OFFSETS DE PESO E BIAS
    # ========================================================

    weight_tensor_id = (
        input_ids[1]
    )

    weight_offset = int(
        weight_tensor_off.get(
            weight_tensor_id,
            0,
        )
    )

    has_bias = (
        bias_id >= 0
        and bias_id
        in bias_tensor_off
    )

    bias_offset = int(
        bias_tensor_off.get(
            bias_id,
            0,
        )
    )

    # ========================================================
    # OFFSETS MUL / SHIFT / Q6
    # ========================================================

    has_mulq6 = (
        op_idx in mul_q6_off
    )

    if has_mulq6:
        mul_offset = int(
            mul_q6_off[
                op_idx
            ][0]
        )

        shift_offset = int(
            mul_q6_off[
                op_idx
            ][1]
        )

        q6_offset = int(
            mul_q6_off[
                op_idx
            ][2]
        )

    else:
        mul_offset = 0
        shift_offset = 0
        q6_offset = 0

    # ========================================================
    # SLOT DE ENTRADA
    # ========================================================

    input_tensor_id = (
        input_ids[0]
    )

    if (
        input_tensor_id
        not in tensor_to_slot
    ):
        raise RuntimeError(
            f"{op_type_name} "
            f"op_index={op_idx}: "
            "input tensor sem slot "
            f"(tensor_id="
            f"{input_tensor_id})"
        )

    in_slot = tensor_to_slot[
        input_tensor_id
    ]

    input_ptr = slot_bases[
        in_slot
    ]

    return {
        "label": label,

        "op_index": op_idx,
        "optype": op_type_name,
        "op_type": op_type,

        "act": activation,
        "flags": flags,

        "in_slot": in_slot,
        "out_slot": out_slot,

        "in_h": int(in_h),
        "in_w": int(in_w),

        "cin": int(cin),
        "cout": int(cout),

        "kh": int(
            kernel_h
        ),

        "kw": int(
            kernel_w
        ),

        "stride_h": int(
            stride_h
        ),

        "stride_w": int(
            stride_w
        ),

        "dil_h": int(
            dil_h
        ),

        "dil_w": int(
            dil_w
        ),

        "pad_t": int(
            pad_t
        ),

        "pad_b": int(
            pad_b
        ),

        "pad_l": int(
            pad_l
        ),

        "pad_r": int(
            pad_r
        ),

        "out_h": int(
            out_h
        ),

        "out_w": int(
            out_w
        ),

        "w_off": int(
            weight_offset
        ),

        "has_bias": bool(
            has_bias
        ),

        "b_off": int(
            bias_offset
        ),

        "has_mulq6": bool(
            has_mulq6
        ),

        "mul_off": int(
            mul_offset
        ),

        "shift_off": int(
            shift_offset
        ),

        "q6_off": int(
            q6_offset
        ),

        "zx": int(
            zp_x
        ),

        "zw": int(
            zp_w
        ),

        "zy": int(
            zp_y
        ),

        "depth_mult": (
            int(depth_mult)
            if (
                op_type_name
                == "DEPTHWISE_CONV_2D"
            )
            else 1
        ),

        "input_slots": [
            in_slot
        ],

        "input_ptrs": [
            int(input_ptr)
        ],
    }


# ============================================================
# CONSTRUÇÃO DAS LAYER PARAMS
# ============================================================


def build_layer_params(
    model,
    subgraph,
    *,
    old_idx_to_label,
    runtime_tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
    synthetic_layer="rgb565_to_rgb888",
):
    """
    Constrói os parâmetros de todas as camadas
    utilizadas pelo runtime.

    Opcionalmente adiciona RGB565_TO_RGB888 antes das operações
    reais provenientes do grafo TFLite.
    """

    layer_params = []

    # ========================================================
    # CAMADA SINTÉTICA RGB565 → RGB888
    # ========================================================

    if synthetic_layer == "rgb565_to_rgb888":
        layer_params.append(build_rgb565_layer(subgraph, slot_bases=slot_bases))
    elif synthetic_layer != "none":
        raise ValueError(f"Camada sintética desconhecida: {synthetic_layer}")

    # ========================================================
    # OPERAÇÕES DO MODELO
    # ========================================================

    supported_operations = {
        "CONV_2D",
        "DEPTHWISE_CONV_2D",
        "FULLY_CONNECTED",
        "ADD",
        "MEAN",
        "SOFTMAX",
        "QUANTIZE",
    }

    for op_idx in range(
        subgraph.OperatorsLength()
    ):
        # Operador não utilizado pelo grafo
        # considerado pelo extrator.
        if (
            op_idx
            not in old_idx_to_label
        ):
            continue

        op = subgraph.Operators(
            op_idx
        )

        op_type_name = op_name(
            model,
            op,
        )

        if (
            op_type_name
            not in supported_operations
        ):
            continue

        label = old_idx_to_label[
            op_idx
        ]

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

        if not output_ids:
            continue

        output_tensor_id = (
            output_ids[0]
        )

        if (
            output_tensor_id
            not in runtime_tensor_to_slot
        ):
            raise RuntimeError(
                f"{op_type_name} "
                f"op_index={op_idx}: "
                "output tensor sem slot "
                f"(tensor_id="
                f"{output_tensor_id})"
            )

        out_slot = (
            runtime_tensor_to_slot[
                output_tensor_id
            ]
        )

        # ====================================================
        # QUANTIZE
        # ====================================================

        if op_type_name == "QUANTIZE":
            params = (
                _build_quantize_params(
                    subgraph,

                    op_idx=op_idx,
                    label=label,

                    input_ids=input_ids,
                    output_ids=output_ids,

                    out_slot=out_slot,

                    tensor_to_slot=(
                        runtime_tensor_to_slot
                    ),

                    slot_bases=(
                        slot_bases
                    ),
                )
            )

        # ====================================================
        # ADD
        # ====================================================

        elif op_type_name == "ADD":
            params = (
                _build_add_params(
                    subgraph,

                    op_idx=op_idx,
                    op=op,
                    label=label,

                    input_ids=input_ids,
                    output_ids=output_ids,

                    out_slot=out_slot,

                    tensor_to_slot=(
                        runtime_tensor_to_slot
                    ),

                    slot_bases=(
                        slot_bases
                    ),
                )
            )

        # ====================================================
        # MEAN
        # ====================================================

        elif op_type_name == "MEAN":
            params = (
                _build_mean_params(
                    subgraph,

                    op_idx=op_idx,
                    label=label,

                    input_ids=input_ids,
                    output_ids=output_ids,

                    out_slot=out_slot,

                    tensor_to_slot=(
                        runtime_tensor_to_slot
                    ),

                    slot_bases=(
                        slot_bases
                    ),
                )
            )

        # ====================================================
        # SOFTMAX
        # ====================================================

        elif op_type_name == "SOFTMAX":
            params = (
                _build_softmax_params(
                    subgraph,

                    op_idx=op_idx,
                    label=label,

                    input_ids=input_ids,
                    output_ids=output_ids,

                    out_slot=out_slot,

                    tensor_to_slot=(
                        runtime_tensor_to_slot
                    ),

                    slot_bases=(
                        slot_bases
                    ),

                    mul_q6_off=(
                        mul_q6_off
                    ),
                )
            )

        # ====================================================
        # CONV / DEPTHWISE / FULLY CONNECTED
        # ====================================================

        else:
            params = (
                _build_weighted_params(
                    subgraph,

                    op_idx=op_idx,
                    op=op,

                    op_type_name=(
                        op_type_name
                    ),

                    label=label,

                    input_ids=input_ids,
                    output_ids=output_ids,

                    out_slot=out_slot,

                    tensor_to_slot=(
                        runtime_tensor_to_slot
                    ),

                    slot_bases=(
                        slot_bases
                    ),

                    weight_tensor_off=(
                        weight_tensor_off
                    ),

                    bias_tensor_off=(
                        bias_tensor_off
                    ),

                    mul_q6_off=(
                        mul_q6_off
                    ),
                )
            )

        layer_params.append(
            params
        )

    return layer_params

# ============================================================
# RELATÓRIO DAS LAYER PARAMS
# ============================================================


def layer_params_to_text(
    layer_params,
    *,
    lp_size,
    memory_layout,
    runtime_mapping,
):
    """
    Gera relatório textual das LayerParams.

    Este relatório substitui os comentários de debug
    que anteriormente eram escritos dentro do WAT.
    """

    lines = []

    # ========================================================
    # RESUMO
    # ========================================================

    lines.append(
        "LAYER PARAMS"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        f"LayerParam size: "
        f"{lp_size} bytes"
    )

    lines.append(
        f"Numero de layers: "
        f"{len(layer_params)}"
    )

    lines.append(
        f"Params bytes: "
        f"{memory_layout['params_bytes']}"
    )

    lines.append(
        f"Slot bases: "
        f"{memory_layout['slot_bases']}"
    )

    lines.append(
        f"Runtime slot shift: "
        f"{runtime_mapping['slot_shift']}"
    )

    lines.append("")

    # ========================================================
    # CONVENÇÃO DE SHIFT
    # ========================================================

    lines.append(
        "CONVENCAO DE SHIFT"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        "shift > 0: LEFT SHIFT "
        "(multiplicacao por 2^shift)"
    )

    lines.append(
        "shift < 0: RIGHT SHIFT "
        "(divisao por 2^(-shift))"
    )

    lines.append("")

    # ========================================================
    # SIGNIFICADO DOS CAMPOS ESPECIAIS
    # ========================================================

    lines.append(
        "MAPEAMENTO DE CAMPOS PARA OPERACOES ESPECIAIS"
    )

    lines.append(
        "=" * 80
    )

    lines.append("")
    lines.append(
        "ADD (op_type=4)"
    )

    lines.append(
        "  kh       = mul0"
    )

    lines.append(
        "  kw       = shift0"
    )

    lines.append(
        "  stride_h = mul1"
    )

    lines.append(
        "  stride_w = shift1"
    )

    lines.append(
        "  dil_h    = out_mul"
    )

    lines.append(
        "  dil_w    = out_shift"
    )

    lines.append(
        "  pad_t    = input_ptr[0]"
    )

    lines.append(
        "  pad_b    = input_ptr[1]"
    )

    lines.append(
        "  pad_l    = zero_point input A"
    )

    lines.append(
        "  pad_r    = zero_point input B"
    )

    lines.append("")

    lines.append(
        "MEAN (op_type=5)"
    )

    lines.append(
        "  kh       = multiplier"
    )

    lines.append(
        "  kw       = shift"
    )

    lines.append(
        "  stride_h = in_h * in_w"
    )

    lines.append(
        "  pad_t    = input_ptr"
    )

    lines.append("")

    lines.append(
        "SOFTMAX (op_type=6)"
    )

    lines.append(
        "  kh       = input_beta_mul"
    )

    lines.append(
        "  kw       = input_beta_left_shift"
    )

    lines.append(
        "  stride_h = diff_min"
    )

    lines.append(
        "  stride_w = input_left_shift"
    )

    lines.append(
        "  pad_t    = input_ptr"
    )

    lines.append("")

    lines.append(
        "QUANTIZE (op_type=7)"
    )

    lines.extend([
        "  flags bit 0: 0 = input UINT8, 1 = input INT8",
        "  flags bit 1: 0 = output INT8, 1 = output UINT8",
        "  flags = 0 -> input UINT8 / output INT8",
        "  flags = 1 -> input INT8  / output INT8",
        "  flags = 2 -> input UINT8 / output UINT8",
        "  flags = 3 -> input INT8  / output UINT8",
    ])

    lines.append(
        "  kh       = multiplier"
    )

    lines.append(
        "  kw       = shift"
    )

    lines.append(
        "  pad_t    = input_ptr"
    )

    lines.append(
        "  zx       = zero_point input"
    )

    lines.append(
        "  zy       = zero_point output"
    )

    lines.append("")

    lines.append(
        "RGB565_TO_RGB888 (op_type=8)"
    )

    lines.append(
        "  input slot  = SLOT0"
    )

    lines.append(
        "  output slot = SLOT1"
    )

    lines.append(
        "  kh          = 65 para RGB565"
    )

    lines.append("")

    # ========================================================
    # MAPEAMENTO TENSOR -> SLOT DE RUNTIME
    # ========================================================

    lines.append(
        "MAPEAMENTO DE SLOTS DE RUNTIME"
    )

    lines.append(
        "=" * 80
    )

    for record in runtime_mapping[
        "records"
    ]:
        lines.append(
            f"tensor={record['tensor_id']:4} "
            f"layer={record['layer']:5} "
            f"slot_original="
            f"{record['original_slot']} "
            f"slot_runtime="
            f"{record['runtime_slot']}"
        )

    lines.append("")

    # ========================================================
    # FULL DUMP DAS CAMADAS
    # ========================================================

    lines.append(
        "FULL LAYER DUMP"
    )

    lines.append(
        "=" * 80
    )

    for layer_index, params in enumerate(
        layer_params
    ):
        lines.append("")

        lines.append(
            "=" * 80
        )

        lines.append(
            f"L{layer_index}"
        )

        lines.append(
            "=" * 80
        )

        lines.append(
            f"op_index          : "
            f"{params.get('op_index')}"
        )

        lines.append(
            f"label             : "
            f"{params.get('label', '-')}"
        )

        lines.append(
            f"optype            : "
            f"{params.get('optype')}"
        )

        lines.append(
            f"op_type           : "
            f"{params.get('op_type')}"
        )

        lines.append(
            f"act               : "
            f"{params.get('act')}"
        )

        lines.append(
            f"flags             : "
            f"{params.get('flags')}"
        )

        lines.append(
            f"in_slot/out_slot  : "
            f"{params.get('in_slot')} "
            f"-> "
            f"{params.get('out_slot')}"
        )

        lines.append(
            f"input_slots       : "
            f"{params.get('input_slots', [])}"
        )

        lines.append(
            f"input_ptrs        : "
            f"{params.get('input_ptrs', [])}"
        )

        lines.append(
            f"in_h/in_w         : "
            f"{params.get('in_h')} "
            f"x "
            f"{params.get('in_w')}"
        )

        lines.append(
            f"cin/cout          : "
            f"{params.get('cin')} "
            f"-> "
            f"{params.get('cout')}"
        )

        lines.append(
            f"kh/kw             : "
            f"{params.get('kh')} "
            f"x "
            f"{params.get('kw')}"
        )

        lines.append(
            f"stride_h/stride_w : "
            f"{params.get('stride_h')} "
            f"x "
            f"{params.get('stride_w')}"
        )

        lines.append(
            f"dil_h/dil_w       : "
            f"{params.get('dil_h')} "
            f"x "
            f"{params.get('dil_w')}"
        )

        lines.append(
            f"pad t/b/l/r       : "
            f"{params.get('pad_t')} "
            f"{params.get('pad_b')} "
            f"{params.get('pad_l')} "
            f"{params.get('pad_r')}"
        )

        lines.append(
            f"out_h/out_w       : "
            f"{params.get('out_h')} "
            f"x "
            f"{params.get('out_w')}"
        )

        lines.append(
            f"w_off             : "
            f"{params.get('w_off')}"
        )

        lines.append(
            f"has_bias          : "
            f"{params.get('has_bias')}"
        )

        lines.append(
            f"b_off             : "
            f"{params.get('b_off')}"
        )

        lines.append(
            f"has_mulq6         : "
            f"{params.get('has_mulq6')}"
        )

        lines.append(
            f"mul_off           : "
            f"{params.get('mul_off')}"
        )

        lines.append(
            f"shift_off         : "
            f"{params.get('shift_off')}"
        )

        lines.append(
            f"q6_off            : "
            f"{params.get('q6_off')}"
        )

        lines.append(
            f"zx/zw/zy          : "
            f"{params.get('zx')} / "
            f"{params.get('zw')} / "
            f"{params.get('zy')}"
        )

        lines.append(
            f"depth_mult        : "
            f"{params.get('depth_mult')}"
        )

        quant_params = params.get(
            "quant_params"
        )

        if quant_params:
            lines.append("")

            lines.append(
                "QUANTIZATION PARAMETERS"
            )

            for (
                key,
                value,
            ) in quant_params.items():
                lines.append(
                    f"  {key:24}: "
                    f"{value}"
                )

    return "\n".join(
        lines
    )
