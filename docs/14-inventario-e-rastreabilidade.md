# 14 — Inventário e rastreabilidade

[Índice](README.md)

## Critério de inspeção

Inventário dos arquivos relevantes presentes, com conjuntos repetitivos de RAWs agrupados. Ambientes virtuais, `.git/` e caches Python foram identificados e excluídos da análise de código da aplicação. Scripts temporários da tarefa documental não fazem parte do produto. Todos os módulos abaixo foram lidos; as assinaturas do extrator também constam nos capítulos individuais.

## Arquivos Python e referência de cada API

| Fonte | Classes/funções encontradas | Capítulo atual |
|---|---|---|
| [main.py](../main.py) | `main` | [01-cli-main.md](01-cli-main.md) |
| [extractor/__init__.py](../extractor/__init__.py) | Sem funções/classes; inicialização ou constantes | [33-extractor-reporting.md](33-extractor-reporting.md) |
| [extractor/config.py](../extractor/config.py) | Sem funções/classes; inicialização ou constantes | [20-extractor-config.md](20-extractor-config.md) |
| [extractor/graph.py](../extractor/graph.py) | `build_graph_for_subgraph`, `compute_useful_adjacency`, `topo_order`, `build_layers`, `graph_to_text`, `build_graph`, `next_useful_from`, `prev_useful_to` | [23-extractor-graph.md](23-extractor-graph.md) |
| [extractor/layer_params.py](../extractor/layer_params.py) | `tensor_hwc`, `build_runtime_tensor_mapping`, `calculate_layer_memory_layout`, `build_rgb565_layer`, `_build_quantize_params`, `_build_add_params`, `_build_mean_params`, `_build_softmax_params`, `_build_weighted_params`, `build_layer_params`, `layer_params_to_text` | [30-extractor-layer-params.md](30-extractor-layer-params.md) |
| [extractor/memory.py](../extractor/memory.py) | `tensor_numel`, `align_up`, `calculate_slot_bytes`, `calculate_parameter_layout`, `slot_memory_to_text`, `parameter_layout_to_text`, `mem_pages_for`, `calculate_final_memory_layout`, `final_memory_layout_to_text` | [28-extractor-memory.md](28-extractor-memory.md) |
| [extractor/model_loader.py](../extractor/model_loader.py) | `load_model`, `get_subgraph` | [21-extractor-model-loader.md](21-extractor-model-loader.md) |
| [extractor/operator_options.py](../extractor/operator_options.py) | `parse_fused_activation`, `parse_add_options`, `padding_is_same`, `parse_conv2d_options`, `parse_dwconv2d_options`, `parse_fc_options`, `same_padding` | [29-extractor-operator-options.md](29-extractor-operator-options.md) |
| [extractor/params_blob.py](../extractor/params_blob.py) | `op_type_name`, `act_name`, `flags_pretty`, `pack_layerparam`, `validate_layer_params`, `build_params_blob`, `params_blob_to_text` | [31-extractor-params-blob.md](31-extractor-params-blob.md) |
| [extractor/quantization.py](../extractor/quantization.py) | `quantize_multiplier`, `extract_quantization_parameters`, `compute_add_quantization_params`, `quantization_to_text` | [27-extractor-quantization.md](27-extractor-quantization.md) |
| [extractor/reporting.py](../extractor/reporting.py) | `save_report` | [33-extractor-reporting.md](33-extractor-reporting.md) |
| [extractor/slots.py](../extractor/slots.py) | `allocate_slots`, `slot_allocation_to_text` | [24-extractor-slots.md](24-extractor-slots.md) |
| [extractor/tensor_mapping.py](../extractor/tensor_mapping.py) | `resolve_slot_from_producer`, `build_tensor_slot_mapping`, `validate_tensor_slot_mapping`, `tensor_mapping_to_text` | [25-extractor-tensor-mapping.md](25-extractor-tensor-mapping.md) |
| [extractor/tflite_utils.py](../extractor/tflite_utils.py) | `op_name`, `is_constant_tensor`, `safe_bytes_from_tensor`, `scale_scalar`, `zp_scalar`, `tensor_shape_list`, `qparams_np` | [22-extractor-tflite-utils.md](22-extractor-tflite-utils.md) |
| [extractor/wat_generator.py](../extractor/wat_generator.py) | `_as_bytes`, `wat_data_from_bytes`, `build_data_segments`, `generate_wat` | [32-extractor-wat-generator.md](32-extractor-wat-generator.md) |
| [extractor/weights.py](../extractor/weights.py) | `extract_weights_and_bias`, `weights_bias_to_text` | [26-extractor-weights.md](26-extractor-weights.md) |
| [pipeline/__init__.py](../pipeline/__init__.py) | Sem funções/classes; inicialização ou constantes | [33-extractor-reporting.md](33-extractor-reporting.md) |
| [pipeline/model_config.py](../pipeline/model_config.py) | `ModelConfig`, `synthetic_layer_count`, `load` | [03-model-config-manifesto.md](03-model-config-manifesto.md) |
| [pipeline/model_package.py](../pipeline/model_package.py) | `ModelPackage`, `load`, `resolve`, `reports_dir`, `wat_path`, `wasm_path`, `validate_sources`, `available` | [02-model-package.md](02-model-package.md) |
| [pipeline/model_pipeline.py](../pipeline/model_pipeline.py) | `ModelPipeline`, `__init__`, `run` | [04-model-pipeline.md](04-model-pipeline.md) |
| [pipeline/wasm_compiler.py](../pipeline/wasm_compiler.py) | `compile_wat_to_wasm` | [07-compilacao-wat-wasm.md](07-compilacao-wat-wasm.md) |
| [adapters/__init__.py](../adapters/__init__.py) | Sem funções/classes; inicialização ou constantes | [05-adapters.md](05-adapters.md) |
| [adapters/base.py](../adapters/base.py) | `TestCase`, `TestAdapter`, `decode_output`, `__init__`, `raw_files`, `discover_cases`, `prepare_input`, `evaluate_output`, `build_report` | [05-adapters.md](05-adapters.md) |
| [adapters/binary_folders.py](../adapters/binary_folders.py) | `BinaryFoldersAdapter`, `discover_cases`, `prepare_input`, `evaluate_output`, `build_report` | [05-adapters.md](05-adapters.md) |
| [adapters/imagenet_topk.py](../adapters/imagenet_topk.py) | `ImageNetTopKAdapter`, `discover_cases`, `prepare_input`, `evaluate_output`, `build_report` | [05-adapters.md](05-adapters.md) |
| [adapters/registry.py](../adapters/registry.py) | `create_adapter` | [05-adapters.md](05-adapters.md) |
| [inference/wasm_inference.py](../inference/wasm_inference.py) | `_instantiate_wasm`, `tensor_info`, `run_wasm_inference` | [06-inferencia-wasm.md](06-inferencia-wasm.md) |
| [tests/test_model_packages.py](../tests/test_model_packages.py) | `ModelPackagesTests`, `test_wasm_quantize_uses_output_type_at_any_layer_index`, `test_paths_are_relative_to_package`, `test_unknown_contract_rejected`, `test_synthetic_layer_optional`, `test_bgr_conversion_and_invalid_size`, `test_signed_output_and_stable_topk`, `test_binary_class_order_and_ties` | [11-testes.md](11-testes.md) |

## Dados, fontes e artefatos

| Caminho/conjunto | Natureza | Uso observado |
|---|---|---|
| [models/drowsiness/model.toml](../models/drowsiness/model.toml) | Fonte | Seleção/configuração do pacote |
| [models/drowsiness/model_int8_esp32.tflite](../models/drowsiness/model_int8_esp32.tflite) | Fonte binária | 618376 bytes, subgrafo 0 |
| `models/drowsiness/test/drowsy/` | Fonte de teste | 1000 RAWs; tamanhos/quantidades: {'32768': 1000} |
| `models/drowsiness/test/non_drowsy/` | Fonte de teste | 1000 RAWs; tamanhos/quantidades: {'32768': 1000} |
| `models/drowsiness/generated/model.wat`, `model.wasm` | Artefatos | Recriados pelo pipeline |
| `models/drowsiness/reports/` | Artefatos | 11 relatórios 02–12 |
| [models/mobilenetv2_alpha035/model.toml](../models/mobilenetv2_alpha035/model.toml) | Fonte | Seleção/configuração do pacote |
| [models/mobilenetv2_alpha035/mobilenetv2_alpha035_quant.tflite](../models/mobilenetv2_alpha035/mobilenetv2_alpha035_quant.tflite) | Fonte binária | 1925904 bytes, subgrafo 0 |
| `models/mobilenetv2_alpha035/test/img/` | Fonte de teste | 1 RAWs; tamanhos/quantidades: {'150528': 1} |
| `models/mobilenetv2_alpha035/generated/model.wat`, `model.wasm` | Artefatos | Recriados pelo pipeline |
| `models/mobilenetv2_alpha035/reports/` | Artefatos | 11 relatórios 02–12 |
| [labels ImageNet](../models/mobilenetv2_alpha035/labels/imagenet_class_index.json) | Fonte | JSON com 1000 índices e pares wnid/nome |
| `img_mobilenetv2/aviao_uint8.raw` | Fonte duplicada fora do pacote | Não é lida pelos manifests atuais |

## Templates e identidade do conteúdo

| Template | SHA-256 na inspeção | Selecionado? |
|---|---|---|
| [wat/templates/mobilenet_int8_v1.wat](../wat/templates/mobilenet_int8_v1.wat) | `eaf7cfdb902ac483cf33574b9627e8940b861d265afe234dbcfd9a149aaf0be3` | Sim |
| [wat/templates/model_template.wat](../wat/templates/model_template.wat) | `cec158f513e043535d1c20c6b15907991dc73660df4e5c1e94f59ec7ad4f0faf` | Não; legado com índice 67 |
| [models/mobilenetv2_alpha035/wat/model_template.wat](../models/mobilenetv2_alpha035/wat/model_template.wat) | `eaf7cfdb902ac483cf33574b9627e8940b861d265afe234dbcfd9a149aaf0be3` | Sim |

## Arquivos auxiliares

`requirements.txt` fixa flatbuffers, NumPy e tflite, limita a série de Wasmtime e instala tomli condicionalmente. `setup_env.ps1` altera a política de execução somente no processo, cria `.venv` se ausente, tenta ativá-la, atualiza pip e instala requirements. Não corrige uma venv quebrada já existente e não valida inferência ao imprimir sucesso. `.gitignore` define exclusões, incluindo o ambiente `.venv-models`; não participa do pipeline.

O arquivo antigo `extractor/wasm_inference.py` está ausente: os imports atuais apontam para `inference/wasm_inference.py`. Não há servidor Node/JavaScript, conversor de PNG ou código de firmware no fluxo inventariado. Referências históricas a outras árvores não devem ser tratadas como arquivos atuais.

## Documentação anterior preservada

Os 14 documentos numerados anteriores foram mantidos em `historico/`, com seus corpos preservados e um aviso de escopo. Não são exigidos para executar o projeto. Os capítulos atuais substituem suas afirmações sobre arquitetura/caminhos e registram diferenças do runtime.

- [01-configuracao.md](historico/01-configuracao.md)
- [02-carregamento-modelo.md](historico/02-carregamento-modelo.md)
- [03-utilitarios-tflite.md](historico/03-utilitarios-tflite.md)
- [04-grafo.md](historico/04-grafo.md)
- [05-alocacao-slots.md](historico/05-alocacao-slots.md)
- [06-mapeamento-tensor-slot.md](historico/06-mapeamento-tensor-slot.md)
- [07-extracao-pesos-bias.md](historico/07-extracao-pesos-bias.md)
- [08-quantizacao.md](historico/08-quantizacao.md)
- [09-layout-memoria.md](historico/09-layout-memoria.md)
- [10-operacoes-opcoes.md](historico/10-operacoes-opcoes.md)
- [11-layer-params.md](historico/11-layer-params.md)
- [12-params-blob.md](historico/12-params-blob.md)
- [13-geracao-wat.md](historico/13-geracao-wat.md)
- [14-relatorios.md](historico/14-relatorios.md)
