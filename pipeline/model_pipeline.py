from datetime import datetime, timezone

from extractor.config import BATCH, ALIGN, KERNEL_BASE_HINT
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
    build_runtime_tensor_mapping,
    calculate_layer_memory_layout,
    build_layer_params,
    layer_params_to_text,
)

from extractor.params_blob import (
    build_params_blob,
    params_blob_to_text,
)

from extractor.reporting import (
    save_report,
)


from pipeline.wasm_compiler import compile_wat_to_wasm
from adapters.registry import create_adapter
from inference.wasm_inference import run_wasm_inference, tensor_info

class ModelPipeline:
    def __init__(self, package):
        self.package = package

    def run(self):
        package = self.package
        config = package.config
        package.validate_sources()
        reports_dir = package.reports_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        reports_dir.mkdir(parents=True, exist_ok=False)
        print(f"Relatórios desta execução: {reports_dir}")
        adapter = create_adapter(package)
        cases = list(adapter.discover_cases())

        # ========================================================
        # PARTE 01 — CARREGAMENTO DO MODELO
        # ========================================================

        model = load_model(
            package.resolve(config.tflite)
        )

        subgraph = get_subgraph(
            model,
            index=0,
        )

        if subgraph.InputsLength() != 1 or subgraph.OutputsLength() != 1:
            raise ValueError("O pipeline atual requer uma entrada e uma saída.")
        input_info = tensor_info(subgraph.Tensors(subgraph.Inputs(0)))
        output_info = tensor_info(subgraph.Tensors(subgraph.Outputs(0)))
        if len(input_info["shape"]) != 4 or input_info["shape"][0] != 1 or input_info["shape"][-1] != 3:
            raise ValueError("Os formatos de imagem atuais requerem entrada NHWC, batch 1 e três canais.")
        if config.synthetic_layer_count and input_info["dtype"] != "uint8":
            raise ValueError("A conversão RGB565 atual requer entrada TFLite UINT8.")

        # ========================================================
        # PARTE 02 — EXTRAÇÃO DO GRAFO
        # ========================================================

        graph = build_graph(
            model,
            subgraph,
        )

        save_report(
            reports_dir / "02-grafo.txt",
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
            num_slots=config.num_slots,
        )

        slots_report = (
            slot_allocation_to_text(
                slot_allocation
            )
        )

        save_report(
            reports_dir
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
            reports_dir
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
            reports_dir
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
            reports_dir
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
            reports_dir
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
            reports_dir
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

                num_slots=config.num_slots,

                slot_shift=config.synthetic_layer_count,
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

                synthetic_layer_count=config.synthetic_layer_count,

                layer_param_size=LP_SIZE,

                params_base=parameter_layout[
                    "params_base"
                ],

                slot_bytes=slot_memory[
                    "slot_bytes"
                ],

                num_slots=config.num_slots,

                alignment=ALIGN,
            )
        )

        layer_params = (
            build_layer_params(
                model,
                subgraph,

                synthetic_layer=config.synthetic_layer,

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
            reports_dir
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
            reports_dir
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
            reports_dir
            / "11-layout-final-memoria.txt",
            final_memory_report,
        )

        # ========================================================
        # PARTE 12 — GERAÇÃO DO WAT
        # ========================================================

        wat_result = generate_wat(
            template_path=(
                package.resolve(config.wat_template)
            ),

            output_path=(
                package.wat_path
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
                wasm_path=package.wasm_path,
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


        if output_info["elements"] != wat_result["result_count"]:
            raise ValueError("Saída gerada incompatível com o tensor de saída TFLite.")
        inference = run_wasm_inference(
            wasm_path=package.wasm_path, adapter=adapter, cases=cases,
            input_info=input_info, output_info=output_info,
            input_ptr=layer_memory["slot_bases"][0], slot_bytes=slot_memory["slot_bytes"],
        )
        report = adapter.build_report(inference)
        report += f"\nErros de processamento: {len(inference['errors'])}\n"
        report += "\n".join(f"{e['file']} | {e['error']}" for e in inference["errors"])
        save_report(reports_dir / "12-inferencia-wasm.txt", report)
        print(f"Inferências: {inference['processed']}; erros: {len(inference['errors'])}")
        print(f"Relatórios: {reports_dir}")
        if inference["errors"]:
            raise RuntimeError("Inferência concluída com erros; consulte 12-inferencia-wasm.txt.")
        return inference
