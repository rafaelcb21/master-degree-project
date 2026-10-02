[English](04-model-pipeline.md) | [Português (Brasil)](04-model-pipeline.pt-BR.md)

# 04 — ModelPipeline: orquestração detalhada

[Índice](README.pt-BR.md) · Fonte: [pipeline/model_pipeline.py](../pipeline/model_pipeline.py)

## Contrato do objeto

`ModelPipeline.__init__(package)` apenas guarda o pacote. `run()` executa uma sequência fixa e retorna o dicionário de inferência `{records, errors, processed}` somente quando termina sem erros por caso. As estruturas intermediárias são variáveis locais; não ficam expostas como atributos nem são carregadas de relatórios anteriores. A classe não possui cache, hooks de subclassificação ou mecanismo de retomar uma execução.

Dependências: todos os estágios de `extractor`, a factory dos adapters, o compilador e o runner Wasmtime. As constantes compartilhadas são batch 1, alinhamento 16 e base sugerida de pesos 2048. O nome do modelo nunca decide um `if` de comportamento dentro de `run`; o manifest e a forma dos tensores fornecem os dados variáveis.

## Etapas na ordem real

| Ordem | Chamada / entrada | Saída e consumidor | Efeito em disco |
|---|---|---|---|
| 1 | `package.validate_sources()` | Confirma TFLite/template não vazios | Nenhum |
| 2 | `create_adapter(package)`; `list(adapter.discover_cases())` | Lista materializada de `TestCase`; ImageNet carrega labels aqui | Nenhum |
| 3 | `load_model`; `get_subgraph(index=0)` | FlatBuffer e subgrafo | Nenhum |
| 4 | Quantidade de inputs/outputs e `tensor_info` | Uma entrada e saída INT8/UINT8, escala positiva; entrada `[1,H,W,3]` | Nenhum |
| 5 | `build_graph(model, subgraph)` | Camadas, arestas, ordens, índices | `02-grafo.txt` |
| 6 | `allocate_slots(graph["layers"], num_slots)` | Lista de alocação e `layer_output_slot` | `03-alocacao-slots.txt` |
| 7 | `build_tensor_slot_mapping` e `validate_tensor_slot_mapping` | Mapa lógico e conjunto de inputs | `04-mapeamento-tensor-slot.txt` |
| 8 | `extract_weights_and_bias` | Bytes e offsets por tensor | `05-pesos-bias.txt` |
| 9 | `extract_quantization_parameters` | MUL/SHIFT/Q6 e offsets por operador | `06-quantizacao.txt` |
| 10 | `calculate_slot_bytes` | Maior tensor e tamanho alinhado de cada slot | `07-slot-bytes.txt` |
| 11 | `calculate_parameter_layout` | Bases de pesos/bias/quantização/PARAMS | `08-layout-parametros.txt` |
| 12 | `build_runtime_tensor_mapping` | Mapa com `slot_shift` aplicado | Incluído em 09 |
| 13 | `calculate_layer_memory_layout` | Área de parâmetros e bases dos slots | Incluído em 09 |
| 14 | `build_layer_params` | Lista de dicts para kernels, camada sintética opcional | `09-layer-params.txt` |
| 15 | `build_params_blob` | Bytes de registros, padding e ponteiros resolvidos | `10-params-blob.txt` |
| 16 | `calculate_final_memory_layout` | Regiões, endereço final e páginas | `11-layout-final-memoria.txt` |
| 17 | `generate_wat` | Metadados do WAT, saída final e contagem | `generated/model.wat` |
| 18 | `compile_wat_to_wasm` | Caminho e tamanho binário | `generated/model.wasm` |
| 19 | Compara `output_info.elements` e `result_count` | Rejeita contagem divergente | Nenhum novo arquivo |
| 20 | `run_wasm_inference` | Registros e erros por RAW | Mensagens a cada 100 casos |
| 21 | `adapter.build_report`; acrescenta erros; `save_report` | Relatório do domínio + falhas | `12-inferencia-wasm.txt` |
| 22 | Verifica `errors` | Retorna resultados ou levanta `RuntimeError` | Arquivos já persistidos |

## Dependências entre estruturas

```text
TFLite/subgrafo
   │
   ├──► grafo ──► slots ──► mapping lógico ──► validação
   │                │              │
   │                └──────────────┴──► runtime_mapping (shift)
   │
   ├──► pesos/bias ──────┐
   ├──► MUL/SHIFT/Q6 ────┼──► parameter_layout ──► PARAMS_BASE
   └──► slot_bytes ──────┘                              │
                       real_count + synthetic_count ───┤
                                                       ▼
                                                   layer_memory
                                                       │
runtime_mapping + offsets + opções TFLite ──────────────┤
                                                       ▼
                                                  layer_params
                                                       ▼
                                                  params_blob
                                                       ▼
                                                final_memory
                                                       ▼
                                    template + dados → WAT → WASM
```

Entram tensores, grafo e opções do modelo. O pipeline combina resultados de módulos sem reimplementar seus algoritmos. Saem um layout físico e os bytes necessários ao gerador. Quantidades, offsets e shapes variam por modelo; tamanho de registro, ordem das regiões e interpretação dos campos vêm do runtime.

## Validações: o que se verifica e o que não se verifica

A entrada deve ter quatro dimensões, batch 1 e três canais. Com RGB565 sintético, o dtype TFLite de entrada deve ser UINT8. Esses controles não validam que H e W sejam positivos, nem provam que o layout original é NHWC: o pipeline exige e interpreta esse formato. `tensor_info` usa o primeiro scale/zero point. A contagem de saída é comparada **depois** da compilação; não há comparação de identidade entre o tensor de saída e a última operação serializada.

O grafo ordena camadas topologicamente para os slots, mas `build_layer_params` percorre a ordem original dos operadores do FlatBuffer. O sucesso nos modelos atuais depende da compatibilidade dessas ordens. Operadores não suportados podem ser pulados pelo construtor de LayerParams: não existe um bloqueio global de todos os opcodes incompatíveis antes da geração.

## Erros, efeitos parciais e reexecução

Uma pasta de testes vazia impede inclusive gerar WAT, pois discovery vem primeiro. Falhas em grafo, memória, serialização, escrita ou compilação interrompem a execução imediatamente. Falhas dentro de cada caso são coletadas, permitindo tentar os seguintes, e reportadas antes do erro final. `build_report` também pode falhar; o pipeline não o protege com um fallback.

Relatórios são substituídos a cada etapa, não numa transação. Uma falha em 08 pode deixar 02–07 novos e 08–12 antigos. Não use a simples existência de `generated/model.wasm` como evidência de sucesso da última execução. Confirme código de saída e o relatório 12. Não existe limpeza de artefatos obsoletos.

## Relação com o modelo e com o runtime

O pacote define template, TFLite, formato e adapter. O extrator recebe dados concretos e produz um contrato comum. Um novo adapter não exige mudar esta sequência, desde que opere com uma entrada NHWC de três canais e saída de 8 bits conforme as validações atuais. Áudio, detecção com múltiplas saídas ou batch maior exigem alterar contratos, não somente adicionar um nome ao registry.
