from pathlib import Path
import re


PLACEHOLDER_PATTERN = re.compile(r"@@[A-Z0-9_]+@@")


def _as_bytes(value):
    if isinstance(value, bytes):
        return value

    if isinstance(value, bytearray):
        return bytes(value)

    if isinstance(value, memoryview):
        return value.tobytes()

    if hasattr(value, "tobytes"):
        return value.tobytes()

    raise TypeError(
        f"Valor não pode ser convertido para bytes: {type(value)!r}"
    )


def wat_data_from_bytes(data, base):
    """
    Gera um active data segment WAT.

    Todos os bytes são escritos como escapes hexadecimais,
    evitando problemas com caracteres especiais.
    """
    raw = _as_bytes(data)

    if len(raw) == 0:
        return ""

    encoded = "".join(
        f"\\{byte:02x}"
        for byte in raw
    )

    return (
        f'(data (i32.const {int(base)}) '
        f'"{encoded}")'
    )


def build_data_segments(
    *,
    parameter_layout,
    weights_bias,
    quantization,
    params_serialization,
):
    segments = []

    sources = [
        (
            parameter_layout["kernel_base"],
            weights_bias["weights_raw"],
        ),
        (
            parameter_layout["bias_base"],
            weights_bias["bias_raw"],
        ),
        (
            parameter_layout["mul_base"],
            quantization["mul_blob"],
        ),
        (
            parameter_layout["shift_base"],
            quantization["shift_blob"],
        ),
        (
            parameter_layout["q6_base"],
            quantization["q6_blob"],
        ),
        (
            parameter_layout["params_base"],
            params_serialization["params_blob"],
        ),
    ]

    for base, data in sources:
        raw = _as_bytes(data)

        if not raw:
            continue

        segments.append(
            "  " + wat_data_from_bytes(
                raw,
                base,
            )
        )

    return "\n\n".join(segments)


def generate_wat(
    *,
    template_path,
    output_path,
    parameter_layout,
    layer_memory,
    final_memory,
    params_serialization,
    weights_bias,
    quantization,
    layer_params,
):
    """
    Preenche o template WAT somente com valores que dependem
    do modelo extraído.

    Os parâmetros específicos de cada camada já estão contidos
    no params_blob e não são inseridos diretamente nas funções WAT.
    """

    template_path = Path(template_path)
    output_path = Path(output_path)

    wat = template_path.read_text(
        encoding="utf-8"
    )

    if not layer_params:
        raise RuntimeError(
            "Nenhuma LayerParam foi gerada."
        )

    records = params_serialization[
        "records"
    ]

    if not records:
        raise RuntimeError(
            "params_serialization não possui records."
        )

    final_layer = layer_params[-1]
    final_record = records[-1]

    result_base = int(
        final_record["out_ptr"]
    )

    result_count = int(
        final_layer["out_h"]
        * final_layer["out_w"]
        * final_layer["cout"]
    )

    slot_bases = layer_memory[
        "slot_bases"
    ]

    if len(slot_bases) != 3:
        raise RuntimeError(
            "O template atual espera exatamente "
            f"3 slots, recebeu {len(slot_bases)}."
        )

    replacements = {
        "@@MEM_PAGES@@":
            final_memory["mem_pages"],

        "@@PARAMS_BASE@@":
            parameter_layout["params_base"],

        "@@LP_SIZE@@":
            params_serialization[
                "layer_param_size"
            ],

        "@@NUM_LAYERS@@":
            len(layer_params),

        "@@WEIGHTS_BASE@@":
            parameter_layout["kernel_base"],

        "@@BIAS_BASE@@":
            parameter_layout["bias_base"],

        "@@MUL_BASE@@":
            parameter_layout["mul_base"],

        "@@SHIFT_BASE@@":
            parameter_layout["shift_base"],

        "@@Q6_BASE@@":
            parameter_layout["q6_base"],

        "@@SLOT0_BASE@@":
            slot_bases[0],

        "@@SLOT1_BASE@@":
            slot_bases[1],

        "@@SLOT2_BASE@@":
            slot_bases[2],

        "@@RESULT_BASE@@":
            result_base,

        "@@RESULT_COUNT@@":
            result_count,
    }

    for placeholder, value in replacements.items():
        wat = wat.replace(
            placeholder,
            str(int(value)),
        )

    data_segments = build_data_segments(
        parameter_layout=parameter_layout,
        weights_bias=weights_bias,
        quantization=quantization,
        params_serialization=params_serialization,
    )

    wat = wat.replace(
        "@@DATA_SEGMENTS@@",
        data_segments,
    )

    unresolved = sorted(
        set(
            PLACEHOLDER_PATTERN.findall(
                wat
            )
        )
    )

    if unresolved:
        raise RuntimeError(
            "Placeholders WAT não resolvidos: "
            + ", ".join(unresolved)
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        wat,
        encoding="utf-8",
    )

    return {
        "output_path": output_path,
        "mem_pages": int(
            final_memory["mem_pages"]
        ),
        "num_layers": len(
            layer_params
        ),
        "result_base": result_base,
        "result_count": result_count,
        "wat_bytes": output_path.stat().st_size,
    }
