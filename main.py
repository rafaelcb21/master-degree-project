from pathlib import Path

from wasmtime import wat2wasm

from extractor.config import (
    MODEL_PATH,
    NUM_SLOTS,
    REPORTS_DIR,
    BATCH,
    ALIGN,
    KERNEL_BASE_HINT,
    WAT_TEMPLATE_PATH,
    OUT_WAT_PATH,
)

from extractor.wat_generator import (
    generate_wat,
)

from extractor.model_loader import (
    load_model,
    get_subgraph,
)

from extractor.graph import (
    build_graph,
)

from extractor.slots import (
    allocate_slots,
    slot_allocation_to_text,
)

from extractor.tensor_mapping import (
    build_tensor_slot_mapping,
    validate_tensor_slot_mapping,
    tensor_mapping_to_text,
)

from extractor.weights import (
    extract_weights_and_bias,
    weights_bias_to_text,
)

from extractor.quantization import (
    extract_quantization_parameters,
    quantization_to_text,
)

from extractor.memory import (
    calculate_slot_bytes,
    slot_memory_to_text,
    calculate_parameter_layout,
    parameter_layout_to_text,
    calculate_final_memory_layout,
    final_memory_layout_to_text,
)

from extractor.layer_params import (
    LP_SIZE,
    RGB888_SLOT,
    build_runtime_tensor_mapping,
    calculate_layer_memory_layout,
    build_layer_params,
    layer_params_to_text,
)

from extractor.params_blob import (
    build_params_blob,
    params_blob_to_text,
)

from extractor.wasm_inference import (
    run_wasm_inference,
    wasm_inference_to_text,
)

from extractor.reporting import (
    save_report,
)


INFERENCE_DATASETS = [
    {
        "dir": Path(
            "little/drowsy"
        ),
        "label": 1,
    },
    {
        "dir": Path(
            "little/non_drowsy"
        ),
        "label": 0,
    },
]

INFERENCE_CLASSES = [
    {
        "name": "drowsy",
        "label": 1,
    },
    {
        "name": "non_drowsy",
        "label": 0,
    },
]


OUT_WASM_PATH = Path(
    OUT_WAT_PATH
).with_suffix(
    ".wasm"
)


def compile_wat_to_wasm(
    wat_path,
    wasm_path,
):
    """
    Converte o WAT gerado para o binário WASM.

    A função utiliza o parser oficial do Wasmtime,
    portanto não depende do executável externo wat2wasm.
    """

    wat_path = Path(
        wat_path
    )

    wasm_path = Path(
        wasm_path
    )

    if not wat_path.is_file():
        raise FileNotFoundError(
            "Arquivo WAT não encontrado: "
            f"{wat_path}"
        )

    wat_source = (
        wat_path.read_text(
            encoding="utf-8"
        )
    )

    wasm_binary = bytes(
        wat2wasm(
            wat_source
        )
    )

    if not wasm_binary.startswith(
        b"\x00asm"
    ):
        raise RuntimeError(
            "O binário gerado não possui "
            "o magic number WebAssembly."
        )

    wasm_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    wasm_path.write_bytes(
        wasm_binary
    )

    return {
        "output_path": wasm_path,
        "wasm_bytes": len(
            wasm_binary
        ),
    }


def main():
    # ========================================================
    # PARTE 01 — CARREGAMENTO DO MODELO
    # ========================================================

    model = load_model(
        MODEL_PATH
    )

    subgraph = get_subgraph(
        model,
        index=0,
    )

    # ========================================================
    # PARTE 02 — EXTRAÇÃO DO GRAFO
    # ========================================================

    graph = build_graph(
        model,
        subgraph,
    )

    save_report(
        REPORTS_DIR / "02-grafo.txt",
        graph["data"],
    )

    # ========================================================
    # PARTE 03 — ALOCAÇÃO DOS SLOTS
    # ========================================================

    (
        slot_allocation,
        layer_output_slot,
    ) = allocate_slots(
        graph["layers"],
        num_slots=NUM_SLOTS,
    )

    slots_report = (
        slot_allocation_to_text(
            slot_allocation
        )
    )

    save_report(
        REPORTS_DIR
        / "03-alocacao-slots.txt",
        slots_report,
    )

    # ========================================================
    # PARTE 04 — MAPEAMENTO TENSOR_ID → SLOT
    # ========================================================

    mapping = build_tensor_slot_mapping(
        model,
        subgraph,

        slot_allocation=(
            slot_allocation
        ),

        layer_output_slot=(
            layer_output_slot
        ),

        label_to_op_idx=graph[
            "label_to_op_idx"
        ],

        old_idx_to_label=graph[
            "old_idx_to_label"
        ],

        producer_by_tensor=graph[
            "producer_by_tensor"
        ],
    )

    # ========================================================
    # VALIDAÇÃO DO MAPEAMENTO
    # ========================================================

    validate_tensor_slot_mapping(
        model,
        subgraph,

        tensor_to_slot=mapping[
            "tensor_to_slot"
        ],

        old_idx_to_label=graph[
            "old_idx_to_label"
        ],
    )

    mapping_report = (
        tensor_mapping_to_text(
            mapping
        )
    )

    save_report(
        REPORTS_DIR
        / "04-mapeamento-tensor-slot.txt",
        mapping_report,
    )

    # ========================================================
    # PARTE 05 — EXTRAÇÃO DE PESOS E BIAS
    # ========================================================

    weights_bias = (
        extract_weights_and_bias(
            model,
            subgraph,
        )
    )

    weights_bias_report = (
        weights_bias_to_text(
            weights_bias
        )
    )

    save_report(
        REPORTS_DIR
        / "05-pesos-bias.txt",
        weights_bias_report,
    )

    # ========================================================
    # PARTE 06 — PARÂMETROS DE QUANTIZAÇÃO
    # ========================================================

    quantization = (
        extract_quantization_parameters(
            model,
            subgraph,
        )
    )

    quantization_report = (
        quantization_to_text(
            quantization
        )
    )

    save_report(
        REPORTS_DIR
        / "06-quantizacao.txt",
        quantization_report,
    )

    # ========================================================
    # PARTE 07 — TAMANHO DOS SLOTS
    # ========================================================

    slot_memory = (
        calculate_slot_bytes(
            model,
            subgraph,
            batch=BATCH,
            alignment=ALIGN,
        )
    )

    slot_memory_report = (
        slot_memory_to_text(
            slot_memory
        )
    )

    save_report(
        REPORTS_DIR
        / "07-slot-bytes.txt",
        slot_memory_report,
    )

    # ========================================================
    # PARTE 08 — LAYOUT DOS PARÂMETROS NA MEMÓRIA
    # ========================================================

    parameter_layout = (
        calculate_parameter_layout(
            kernel_base_hint=(
                KERNEL_BASE_HINT
            ),

            alignment=ALIGN,

            weights_raw=weights_bias[
                "weights_raw"
            ],

            bias_raw=weights_bias[
                "bias_raw"
            ],

            mul_blob=quantization[
                "mul_blob"
            ],

            shift_blob=quantization[
                "shift_blob"
            ],

            q6_blob=quantization[
                "q6_blob"
            ],
        )
    )

    parameter_layout_report = (
        parameter_layout_to_text(
            parameter_layout
        )
    )

    save_report(
        REPORTS_DIR
        / "08-layout-parametros.txt",
        parameter_layout_report,
    )

    # ========================================================
    # PARTE 09 — LAYER PARAMS
    # ========================================================

    runtime_mapping = (
        build_runtime_tensor_mapping(
            subgraph,

            graph_inputs=mapping[
                "graph_inputs"
            ],

            slot_allocation=(
                slot_allocation
            ),

            label_to_op_idx=graph[
                "label_to_op_idx"
            ],

            num_slots=NUM_SLOTS,

            slot_shift=RGB888_SLOT,
        )
    )

    real_layer_count = len(
        graph["layers"]
    )

    layer_memory = (
        calculate_layer_memory_layout(
            real_layer_count=(
                real_layer_count
            ),

            synthetic_layer_count=1,

            layer_param_size=LP_SIZE,

            params_base=parameter_layout[
                "params_base"
            ],

            slot_bytes=slot_memory[
                "slot_bytes"
            ],

            num_slots=NUM_SLOTS,

            alignment=ALIGN,
        )
    )

    layer_params = (
        build_layer_params(
            model,
            subgraph,

            old_idx_to_label=graph[
                "old_idx_to_label"
            ],

            runtime_tensor_to_slot=(
                runtime_mapping[
                    "tensor_to_slot"
                ]
            ),

            slot_bases=layer_memory[
                "slot_bases"
            ],

            weight_tensor_off=(
                weights_bias[
                    "weight_tensor_off"
                ]
            ),

            bias_tensor_off=(
                weights_bias[
                    "bias_tensor_off"
                ]
            ),

            mul_q6_off=(
                quantization[
                    "mul_q6_off"
                ]
            ),
        )
    )

    layer_params_report = (
        layer_params_to_text(
            layer_params,

            lp_size=LP_SIZE,

            memory_layout=(
                layer_memory
            ),

            runtime_mapping=(
                runtime_mapping
            ),
        )
    )

    save_report(
        REPORTS_DIR
        / "09-layer-params.txt",
        layer_params_report,
    )

    # ========================================================
    # PARTE 10 — SERIALIZAÇÃO DAS LAYER PARAMS
    # ========================================================

    params_serialization = (
        build_params_blob(
            layer_params,

            slot_bases=layer_memory[
                "slot_bases"
            ],

            params_bytes=layer_memory[
                "params_bytes"
            ],

            parameter_layout=(
                parameter_layout
            ),
        )
    )

    params_blob_report = (
        params_blob_to_text(
            params_serialization
        )
    )

    save_report(
        REPORTS_DIR
        / "10-params-blob.txt",
        params_blob_report,
    )

    # ========================================================
    # PARTE 11 — FECHAMENTO DO LAYOUT DE MEMÓRIA
    # ========================================================

    final_memory = (
        calculate_final_memory_layout(
            parameter_layout=(
                parameter_layout
            ),

            params_blob=(
                params_serialization[
                    "params_blob"
                ]
            ),

            slot_bases=(
                layer_memory[
                    "slot_bases"
                ]
            ),

            slot_bytes=(
                slot_memory[
                    "slot_bytes"
                ]
            ),
        )
    )

    final_memory_report = (
        final_memory_layout_to_text(
            final_memory
        )
    )

    save_report(
        REPORTS_DIR
        / "11-layout-final-memoria.txt",
        final_memory_report,
    )

    # ========================================================
    # PARTE 12 — GERAÇÃO DO WAT
    # ========================================================

    wat_result = generate_wat(
        template_path=(
            WAT_TEMPLATE_PATH
        ),

        output_path=(
            OUT_WAT_PATH
        ),

        parameter_layout=(
            parameter_layout
        ),

        layer_memory=(
            layer_memory
        ),

        final_memory=(
            final_memory
        ),

        params_serialization=(
            params_serialization
        ),

        weights_bias=(
            weights_bias
        ),

        quantization=(
            quantization
        ),

        layer_params=(
            layer_params
        ),
    )

    print(
        f"WAT gerado: "
        f"{wat_result['output_path']}"
    )

    print(
        f"Layers: "
        f"{wat_result['num_layers']}"
    )

    print(
        f"Memory pages: "
        f"{wat_result['mem_pages']}"
    )

    print(
        f"Result base: "
        f"{wat_result['result_base']}"
    )

    print(
        f"Result count: "
        f"{wat_result['result_count']}"
    )

    # ========================================================
    # PARTE 13 — COMPILAÇÃO WAT → WASM
    # ========================================================

    wasm_result = (
        compile_wat_to_wasm(
            wat_path=wat_result[
                "output_path"
            ],
            wasm_path=OUT_WASM_PATH,
        )
    )

    print(
        f"WASM gerado: "
        f"{wasm_result['output_path']}"
    )

    print(
        f"WASM bytes: "
        f"{wasm_result['wasm_bytes']}"
    )

    # ========================================================
    # PARTE 14 — INFERÊNCIA DO WASM COM IMAGENS RAW
    # ========================================================

    if not layer_params:
        raise RuntimeError(
            "Nenhuma LayerParam disponível "
            "para determinar a entrada RGB565."
        )

    synthetic_input_layer = (
        layer_params[0]
    )

    rgb565_bytes = int(
        synthetic_input_layer[
            "in_h"
        ]
        * synthetic_input_layer[
            "in_w"
        ]
        * 2
    )

    input_ptr = int(
        layer_memory[
            "slot_bases"
        ][0]
    )

    result_count = int(
        wat_result[
            "result_count"
        ]
    )

    inference = (
        run_wasm_inference(
            wasm_path=wasm_result[
                "output_path"
            ],

            datasets=(
                INFERENCE_DATASETS
            ),

            classes=(
                INFERENCE_CLASSES
            ),

            input_ptr=input_ptr,

            input_bytes=(
                rgb565_bytes
            ),

            result_count=(
                result_count
            ),
        )
    )

    inference_report = (
        wasm_inference_to_text(
            inference
        )
    )

    save_report(
        REPORTS_DIR
        / "12-inferencia-wasm.txt",
        inference_report,
    )

    print(
        f"RAW processadas: "
        f"{inference['processed']}"
    )

    print(
        f"Erros de inferência: "
        f"{len(inference['errors'])}"
    )

    print(
        f"Inválidos/empates: "
        f"{inference['invalid']}"
    )

    print(
        f"Acertos: "
        f"{inference['correct']}"
    )

    print(
        f"Acurácia WASM: "
        f"{inference['accuracy']:.2f}%"
    )

    # ========================================================
    # RESUMO DA EXECUÇÃO
    # ========================================================

    print(
        "Extração, geração e inferência "
        "concluídas com sucesso."
    )

    print(
        f"Relatórios gerados em: "
        f"{REPORTS_DIR}"
    )


if __name__ == "__main__":
    main()