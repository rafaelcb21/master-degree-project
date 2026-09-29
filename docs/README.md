# Documentação técnica — índice

[README principal](../README.md)

Esta é a referência do comportamento atual, baseada no código e nos TFLite presentes. A ordem 00–14 cobre uso e arquitetura; 20–33 cobre cada módulo do extrator. O material anterior permanece em `historico/` com avisos de escopo. Recomendações futuras estão separadas do que já existe.

## Arquitetura, interfaces e operação

- [00 — Visão geral e arquitetura](00-visao-geral-arquitetura.md)
- [01 — CLI: main.py](01-cli-main.md)
- [02 — ModelPackage e resolução de caminhos](02-model-package.md)
- [03 — ModelConfig e referência de model.toml](03-model-config-manifesto.md)
- [04 — ModelPipeline: orquestração detalhada](04-model-pipeline.md)
- [05 — Adapters de teste e registry](05-adapters.md)
- [06 — Host de inferência Wasmtime](06-inferencia-wasm.md)
- [07 — Compilação WAT → WASM](07-compilacao-wat-wasm.md)
- [08 — Contrato binário layerparam-v1](08-contrato-layerparam-v1.md)
- [09 — Modelos e pacotes presentes](09-modelos-e-pacotes.md)
- [10 — Tutorial: cadastrar um terceiro modelo](10-como-adicionar-modelo.md)
- [11 — Testes e alcance da validação](11-testes.md)
- [12 — Fluxo completo e leitura dos relatórios](12-fluxo-completo.md)
- [13 — Templates e runtime WebAssembly](13-runtime-wat.md)
- [14 — Inventário e rastreabilidade](14-inventario-e-rastreabilidade.md)
- [20 — Constantes compartilhadas do extrator](20-extractor-config.md)
- [21 — Carregamento do FlatBuffer TFLite](21-extractor-model-loader.md)
- [22 — Utilitários de tensores e quantização TFLite](22-extractor-tflite-utils.md)
- [23 — Grafo de operadores e ordenação](23-extractor-graph.md)
- [24 — Alocação de slots e vida útil](24-extractor-slots.md)
- [25 — Mapeamento de tensores para slots](25-extractor-tensor-mapping.md)
- [26 — Extração de pesos e bias](26-extractor-weights.md)
- [27 — Quantização inteira e blobs por canal](27-extractor-quantization.md)
- [28 — Planejamento físico da memória](28-extractor-memory.md)
- [29 — Opções de operadores e geometria](29-extractor-operator-options.md)
- [30 — Construção das LayerParams e camada sintética](30-extractor-layer-params.md)
- [31 — Serialização e resolução de ponteiros](31-extractor-params-blob.md)
- [32 — Materialização WAT e data segments](32-extractor-wat-generator.md)
- [33 — Persistência dos relatórios](33-extractor-reporting.md)

## Pacotes

- [Drowsiness MobileNetV2](../models/drowsiness/README.md)
- [MobileNetV2 Alpha 0.35 ImageNet](../models/mobilenetv2_alpha035/README.md)

## Auditoria e histórico

- [Verificação documental](98-verificacao-documental.md)
- [Inconsistências e limitações](99-inconsistencias-e-limitacoes.md)
- [Inventário, fontes e documentos preservados](14-inventario-e-rastreabilidade.md)
