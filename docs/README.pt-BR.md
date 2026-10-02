[English](README.md) | [Português (Brasil)](README.pt-BR.md)

# Documentação técnica — índice

[README principal](../README.pt-BR.md)

Esta é a referência do comportamento atual, baseada no código e nos TFLite presentes. A ordem 00–14 cobre uso e arquitetura; 20–33 cobre cada módulo do extrator. O material anterior permanece em `historico/` com avisos de escopo. Recomendações futuras estão separadas do que já existe.

## Arquitetura, interfaces e operação

- [00 — Visão geral e arquitetura](00-visao-geral-arquitetura.pt-BR.md)
- [01 — CLI: main.py](01-cli-main.pt-BR.md)
- [02 — ModelPackage e resolução de caminhos](02-model-package.pt-BR.md)
- [03 — ModelConfig e referência de model.toml](03-model-config-manifesto.pt-BR.md)
- [04 — ModelPipeline: orquestração detalhada](04-model-pipeline.pt-BR.md)
- [05 — Adapters de teste e registry](05-adapters.pt-BR.md)
- [06 — Host de inferência Wasmtime](06-inferencia-wasm.pt-BR.md)
- [07 — Compilação WAT → WASM](07-compilacao-wat-wasm.pt-BR.md)
- [08 — Contrato binário layerparam-v1](08-contrato-layerparam-v1.pt-BR.md)
- [09 — Modelos e pacotes presentes](09-modelos-e-pacotes.pt-BR.md)
- [10 — Tutorial: cadastrar um terceiro modelo](10-como-adicionar-modelo.pt-BR.md)
- [11 — Testes e alcance da validação](11-testes.pt-BR.md)
- [12 — Fluxo completo e leitura dos relatórios](12-fluxo-completo.pt-BR.md)
- [13 — Templates e runtime WebAssembly](13-runtime-wat.pt-BR.md)
- [14 — Inventário e rastreabilidade](14-inventario-e-rastreabilidade.pt-BR.md)
- [20 — Constantes compartilhadas do extrator](20-extractor-config.pt-BR.md)
- [21 — Carregamento do FlatBuffer TFLite](21-extractor-model-loader.pt-BR.md)
- [22 — Utilitários de tensores e quantização TFLite](22-extractor-tflite-utils.pt-BR.md)
- [23 — Grafo de operadores e ordenação](23-extractor-graph.pt-BR.md)
- [24 — Alocação de slots e vida útil](24-extractor-slots.pt-BR.md)
- [25 — Mapeamento de tensores para slots](25-extractor-tensor-mapping.pt-BR.md)
- [26 — Extração de pesos e bias](26-extractor-weights.pt-BR.md)
- [27 — Quantização inteira e blobs por canal](27-extractor-quantization.pt-BR.md)
- [28 — Planejamento físico da memória](28-extractor-memory.pt-BR.md)
- [29 — Opções de operadores e geometria](29-extractor-operator-options.pt-BR.md)
- [30 — Construção das LayerParams e camada sintética](30-extractor-layer-params.pt-BR.md)
- [31 — Serialização e resolução de ponteiros](31-extractor-params-blob.pt-BR.md)
- [32 — Materialização WAT e data segments](32-extractor-wat-generator.pt-BR.md)
- [33 — Persistência dos relatórios](33-extractor-reporting.pt-BR.md)

## Pacotes

- [Drowsiness MobileNetV2](../models/drowsiness/README.pt-BR.md)
- [MobileNetV2 Alpha 0.35 ImageNet](../models/mobilenetv2_alpha035/README.pt-BR.md)
- [Host ESP32 independente](../ESP32/cnn_webassembly_esp32/README.pt-BR.md)
- [Configuração e medições do host](../ESP32/cnn_webassembly_esp32/HOST.pt-BR.md)
- [WASM → AOT usando WSL](../ESP32/cnn_webassembly_esp32/README_AOT_WSL.pt-BR.md)

## Auditoria e histórico

- [Verificação documental](98-verificacao-documental.pt-BR.md)
- [Inconsistências e limitações](99-inconsistencias-e-limitacoes.pt-BR.md)
- [Inventário, fontes e documentos preservados](14-inventario-e-rastreabilidade.pt-BR.md)

## Manutenção das traduções

Cada página inglesa `.md` tem uma correspondente em português brasileiro `.pt-BR.md`. Use os links de idioma no início das páginas. Atualize as duas versões ao alterar instruções, exemplos ou comportamento documentado. Preserve nomes de arquivos, identificadores, comandos executáveis e avisos históricos. Diferencie observações anteriores de verificações feitas hoje. Veja as [orientações de contribuição](../CONTRIBUTING.pt-BR.md).
