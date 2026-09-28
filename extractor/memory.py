from extractor.tflite_utils import (
    BYTES_PER_TYPE,
    TENSOR_TYPE_MAP,
    is_constant_tensor,
    tensor_shape_list,
)


def tensor_numel(
    shape,
    batch=1,
):
    """
    Calcula a quantidade de elementos de um tensor
    multiplicando suas dimensões.

    Mantém o comportamento do código original:
    dimensões negativas são substituídas por `batch`.
    """

    num_elements = 1

    for dimension in shape:
        dimension = int(
            dimension
        )

        if dimension < 0:
            dimension = batch

        num_elements *= dimension

    return num_elements


def align_up(
    value,
    alignment=16,
):
    """
    Arredonda um valor para cima para o próximo
    múltiplo do alinhamento informado.
    """

    return (
        value
        + (alignment - 1)
    ) & ~(alignment - 1)


def calculate_slot_bytes(
    model,
    subgraph,
    *,
    batch,
    alignment,
):
    """
    Descobre o maior tensor não constante do subgrafo
    e calcula o tamanho necessário para cada slot.

    Retorna informações detalhadas para relatório.
    """

    max_bytes = 0
    max_tensor = None

    tensor_records = []

    for tensor_id in range(
        subgraph.TensorsLength()
    ):
        tensor = subgraph.Tensors(
            tensor_id
        )

        # Pesos, bias e outros dados constantes
        # não ocupam os slots intermediários.
        if is_constant_tensor(
            model,
            subgraph,
            tensor_id,
        ):
            continue

        shape = tensor_shape_list(
            tensor
        )

        if not shape:
            continue

        tensor_type = int(
            tensor.Type()
        )

        bytes_per_element = (
            BYTES_PER_TYPE.get(
                tensor_type
            )
        )

        if bytes_per_element is None:
            continue

        num_elements = tensor_numel(
            shape,
            batch=batch,
        )

        num_bytes = (
            num_elements
            * bytes_per_element
        )

        tensor_name = (
            tensor
            .Name()
            .decode(
                "utf-8",
                "ignore",
            )
        )

        type_name = (
            TENSOR_TYPE_MAP.get(
                tensor_type,
                ("UNKNOWN", None),
            )[0]
        )

        record = {
            "tensor_id": tensor_id,

            "name": tensor_name,

            "shape": shape,

            "tensor_type": (
                tensor_type
            ),

            "type_name": type_name,

            "bytes_per_element": (
                bytes_per_element
            ),

            "num_elements": (
                num_elements
            ),

            "num_bytes": (
                num_bytes
            ),
        }

        tensor_records.append(
            record
        )

        if num_bytes > max_bytes:
            max_bytes = num_bytes
            max_tensor = record

    slot_bytes = align_up(
        max_bytes,
        alignment,
    )

    return {
        "max_bytes": max_bytes,

        "slot_bytes": slot_bytes,

        "alignment": alignment,

        "batch": batch,

        "max_tensor": max_tensor,

        "tensor_records": (
            tensor_records
        ),
    }

def calculate_parameter_layout(
    *,
    kernel_base_hint,
    alignment,
    weights_raw,
    bias_raw,
    mul_blob,
    shift_blob,
    q6_blob,
):
    """
    Calcula as bases dos blocos de parâmetros na memória.

    Layout:

        kernel
          ↓
        bias
          ↓
        multiplier
          ↓
        shift
          ↓
        q6
          ↓
        params

    Cada base é alinhada conforme `alignment`.
    """

    # ========================================================
    # KERNEL / WEIGHTS
    # ========================================================

    kernel_base = align_up(
        kernel_base_hint,
        alignment,
    )

    kernel_bytes = len(
        weights_raw
    )

    # ========================================================
    # BIAS
    # ========================================================

    bias_base = align_up(
        kernel_base + kernel_bytes,
        alignment,
    )

    bias_bytes = len(
        bias_raw
    )

    # ========================================================
    # MULTIPLIERS
    # ========================================================

    mul_base = align_up(
        bias_base + bias_bytes,
        alignment,
    )

    mul_bytes = len(
        mul_blob
    )

    # ========================================================
    # SHIFTS
    # ========================================================

    shift_base = align_up(
        mul_base + mul_bytes,
        alignment,
    )

    shift_bytes = len(
        shift_blob
    )

    # ========================================================
    # Q6
    # ========================================================

    q6_base = align_up(
        shift_base + shift_bytes,
        alignment,
    )

    q6_bytes = len(
        q6_blob
    )

    # ========================================================
    # PRÓXIMA ÁREA LIVRE
    # ========================================================

    params_base = align_up(
        q6_base + q6_bytes,
        alignment,
    )

    return {
        "kernel_base": kernel_base,
        "kernel_bytes": kernel_bytes,

        "bias_base": bias_base,
        "bias_bytes": bias_bytes,

        "mul_base": mul_base,
        "mul_bytes": mul_bytes,

        "shift_base": shift_base,
        "shift_bytes": shift_bytes,

        "q6_base": q6_base,
        "q6_bytes": q6_bytes,

        "params_base": params_base,

        "alignment": alignment,
        "kernel_base_hint": (
            kernel_base_hint
        ),
    }

def slot_memory_to_text(
    memory_info,
):
    lines = []

    lines.append(
        "TENSORES NÃO CONSTANTES"
    )

    lines.append(
        "=" * 80
    )

    for tensor in memory_info[
        "tensor_records"
    ]:
        lines.append(
            f"tensor={tensor['tensor_id']:4} "
            f"name={tensor['name']} "
            f"shape={tensor['shape']} "
            f"dtype={tensor['type_name']} "
            f"bpe={tensor['bytes_per_element']} "
            f"elements={tensor['num_elements']} "
            f"bytes={tensor['num_bytes']}"
        )

    lines.append("")
    lines.append(
        "MAIOR TENSOR"
    )

    lines.append(
        "=" * 80
    )

    max_tensor = memory_info[
        "max_tensor"
    ]

    if max_tensor is not None:
        lines.append(
            f"tensor_id: "
            f"{max_tensor['tensor_id']}"
        )

        lines.append(
            f"name: "
            f"{max_tensor['name']}"
        )

        lines.append(
            f"shape: "
            f"{max_tensor['shape']}"
        )

        lines.append(
            f"dtype: "
            f"{max_tensor['type_name']}"
        )

        lines.append(
            f"bytes por elemento: "
            f"{max_tensor['bytes_per_element']}"
        )

        lines.append(
            f"numero de elementos: "
            f"{max_tensor['num_elements']}"
        )

        lines.append(
            f"bytes sem alinhamento: "
            f"{max_tensor['num_bytes']}"
        )

    lines.append("")
    lines.append(
        "CALCULO DO SLOT"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        f"max_bytes = "
        f"{memory_info['max_bytes']}"
    )

    lines.append(
        f"alignment = "
        f"{memory_info['alignment']}"
    )

    lines.append(
        f"SLOT_BYTES = "
        f"{memory_info['slot_bytes']}"
    )

    return "\n".join(
        lines
    )

def parameter_layout_to_text(
    layout,
):
    lines = []

    lines.append(
        "LAYOUT DOS PARÂMETROS"
    )

    lines.append(
        "=" * 80
    )

    lines.append(
        f"alignment = "
        f"{layout['alignment']}"
    )

    lines.append(
        f"kernel_base_hint = "
        f"{layout['kernel_base_hint']}"
    )

    lines.append("")

    lines.append(
        f"KERNEL_BASE  = "
        f"{layout['kernel_base']}"
    )

    lines.append(
        f"KERNEL_BYTES = "
        f"{layout['kernel_bytes']}"
    )

    lines.append("")

    lines.append(
        f"BIAS_BASE    = "
        f"{layout['bias_base']}"
    )

    lines.append(
        f"BIAS_BYTES   = "
        f"{layout['bias_bytes']}"
    )

    lines.append("")

    lines.append(
        f"MUL_BASE     = "
        f"{layout['mul_base']}"
    )

    lines.append(
        f"MUL_BYTES    = "
        f"{layout['mul_bytes']}"
    )

    lines.append("")

    lines.append(
        f"SHIFT_BASE   = "
        f"{layout['shift_base']}"
    )

    lines.append(
        f"SHIFT_BYTES  = "
        f"{layout['shift_bytes']}"
    )

    lines.append("")

    lines.append(
        f"Q6_BASE      = "
        f"{layout['q6_base']}"
    )

    lines.append(
        f"Q6_BYTES     = "
        f"{layout['q6_bytes']}"
    )

    lines.append("")

    lines.append(
        f"PARAMS_BASE  = "
        f"{layout['params_base']}"
    )

    return "\n".join(
        lines
    )

# ============================================================
# FECHAMENTO DO LAYOUT DE MEMÓRIA
# ============================================================

WASM_PAGE_BYTES = 65536


def mem_pages_for(
    end_addr,
):
    """
    Calcula a quantidade mínima de páginas WebAssembly
    necessárias para cobrir o endereço final informado.

    Cada página WebAssembly possui 64 KiB.
    """

    return (
        end_addr
        + WASM_PAGE_BYTES
        - 1
    ) // WASM_PAGE_BYTES


def calculate_final_memory_layout(
    *,
    parameter_layout,
    params_blob,
    slot_bases,
    slot_bytes,
):
    """
    Calcula o endereço final ocupado pela memória
    e a quantidade mínima de páginas WebAssembly.

    Não gera WAT.
    Apenas fecha o planejamento de memória.
    """

    regions = []

    # ========================================================
    # WEIGHTS
    # ========================================================

    regions.append(
        {
            "name": "WEIGHTS",
            "base": parameter_layout[
                "kernel_base"
            ],
            "bytes": parameter_layout[
                "kernel_bytes"
            ],
        }
    )

    # ========================================================
    # BIAS
    # ========================================================

    regions.append(
        {
            "name": "BIAS",
            "base": parameter_layout[
                "bias_base"
            ],
            "bytes": parameter_layout[
                "bias_bytes"
            ],
        }
    )

    # ========================================================
    # MULTIPLIERS
    # ========================================================

    regions.append(
        {
            "name": "MUL",
            "base": parameter_layout[
                "mul_base"
            ],
            "bytes": parameter_layout[
                "mul_bytes"
            ],
        }
    )

    # ========================================================
    # SHIFTS
    # ========================================================

    regions.append(
        {
            "name": "SHIFT",
            "base": parameter_layout[
                "shift_base"
            ],
            "bytes": parameter_layout[
                "shift_bytes"
            ],
        }
    )

    # ========================================================
    # Q6
    # ========================================================

    regions.append(
        {
            "name": "Q6",
            "base": parameter_layout[
                "q6_base"
            ],
            "bytes": parameter_layout[
                "q6_bytes"
            ],
        }
    )

    # ========================================================
    # LAYER PARAMS
    # ========================================================

    regions.append(
        {
            "name": "PARAMS",
            "base": parameter_layout[
                "params_base"
            ],
            "bytes": len(
                params_blob
            ),
        }
    )

    # ========================================================
    # SLOTS
    # ========================================================

    for slot_index, slot_base in enumerate(
        slot_bases
    ):
        regions.append(
            {
                "name": (
                    f"SLOT{slot_index}"
                ),
                "base": int(
                    slot_base
                ),
                "bytes": int(
                    slot_bytes
                ),
            }
        )

    # ========================================================
    # ENDEREÇO FINAL DE CADA REGIÃO
    # ========================================================

    for region in regions:
        region["end"] = (
            region["base"]
            + region["bytes"]
        )

    # ========================================================
    # ÚLTIMO ENDEREÇO UTILIZADO
    # ========================================================

    mem_end = max(
        region["end"]
        for region in regions
    )

    # ========================================================
    # PÁGINAS WASM
    # ========================================================

    mem_pages = mem_pages_for(
        mem_end
    )

    allocated_memory_bytes = (
        mem_pages
        * WASM_PAGE_BYTES
    )

    unused_memory_bytes = (
        allocated_memory_bytes
        - mem_end
    )

    return {
        "regions": regions,

        "mem_end": int(
            mem_end
        ),

        "mem_pages": int(
            mem_pages
        ),

        "wasm_page_bytes": (
            WASM_PAGE_BYTES
        ),

        "allocated_memory_bytes": int(
            allocated_memory_bytes
        ),

        "unused_memory_bytes": int(
            unused_memory_bytes
        ),

        "slot_bases": [
            int(value)
            for value in slot_bases
        ],

        "slot_bytes": int(
            slot_bytes
        ),
    }


def final_memory_layout_to_text(
    memory_layout,
):
    """
    Gera o relatório final do planejamento de memória.
    """

    lines = []

    lines.append(
        "LAYOUT FINAL DE MEMORIA"
    )

    lines.append(
        "=" * 80
    )

    lines.append("")

    lines.append(
        f"{'REGIAO':12}"
        f"{'BASE':>12}"
        f"{'BYTES':>12}"
        f"{'END':>12}"
    )

    lines.append(
        "-" * 48
    )

    for region in memory_layout[
        "regions"
    ]:
        lines.append(
            f"{region['name']:12}"
            f"{region['base']:>12}"
            f"{region['bytes']:>12}"
            f"{region['end']:>12}"
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
        f"MEM_END = "
        f"{memory_layout['mem_end']}"
    )

    lines.append(
        f"WASM_PAGE_BYTES = "
        f"{memory_layout['wasm_page_bytes']}"
    )

    lines.append(
        f"MEM_PAGES = "
        f"{memory_layout['mem_pages']}"
    )

    lines.append(
        f"Memoria reservada = "
        f"{memory_layout['allocated_memory_bytes']} bytes"
    )

    lines.append(
        f"Espaco restante na ultima pagina = "
        f"{memory_layout['unused_memory_bytes']} bytes"
    )

    lines.append("")

    lines.append(
        f"SLOT_BYTES = "
        f"{memory_layout['slot_bytes']}"
    )

    for slot_index, slot_base in enumerate(
        memory_layout[
            "slot_bases"
        ]
    ):
        lines.append(
            f"SLOT{slot_index}_BASE = "
            f"{slot_base}"
        )

    return "\n".join(
        lines
    )