# 00 — Visão geral e arquitetura

[Índice da documentação](README.md) · [Fluxo completo](12-fluxo-completo.md) · [Limitações](99-inconsistencias-e-limitacoes.md)

## Escopo e evidência

Esta documentação descreve os arquivos presentes na revisão local de 28/09/2026. Foram lidos os módulos Python, manifests, templates e relatórios; shapes, tipos e quantização foram extraídos dos dois FlatBuffers TFLite. Os resultados publicados são observações dos relatórios existentes, não garantias de equivalência com um interpretador TFLite. A tarefa documental não altera kernels, modelos, manifests ou testes.

O projeto transforma **modelos TFLite compatíveis** em módulos WebAssembly especializados. Python extrai a descrição da rede e seus parâmetros; um template WAT fornece os kernels; Wasmtime converte o texto em WASM e executa os testes RAW. Não há treinamento, conversão de imagens PNG/JPEG, execução em ESP32 ou servidor web neste fluxo.

TFLite é o FlatBuffer de origem, contendo tensores, operadores e buffers. WAT é a representação textual de WebAssembly, com código e segmentos de dados. WASM é o binário compilado desse WAT. O arquivo WASM resultante não contém um interpretador TFLite: contém o runtime descrito pelo template e os dados extraídos daquele pacote.

## Visão do sistema

```text
                         USUÁRIO
                            │
                            ▼
               python main.py --model X
                            │
                            ▼
               ModelPackage / ModelConfig
                    models/X/model.toml
                            │
           ┌────────────────┼───────────────────┐
           ▼                ▼                   ▼
      TFLite original   template WAT      configuração de teste
           │                │                   │
           ▼                │                   ▼
     ModelPipeline          │              registry.py
           │                │                   │
           │ valida fontes e descobre casos ◄── adapter
           ▼                │                   │
        EXTRACTOR           │                   │
           ├── grafo / slots / tensor→slot       │
           ├── pesos / quantização / memória    │
           └── LayerParams / params_blob        │
           │                │                   │
           └───────┬────────┘                   │
                   ▼                            │
             wat_generator                      │
                   ▼                            │
       models/X/generated/model.wat             │
                   ▼                            │
        wasmtime.wat2wasm (compilação)           │
                   ▼                            │
       models/X/generated/model.wasm            │
                   └───────────┬────────────────┘
                               ▼
                    inference/wasm_inference.py
                               │
           prepare_input → memory.write → run → memory.read
                               │
                     evaluate_output por caso
                               ▼
                    build_report + lista de erros
                               ▼
                models/X/reports/12-inferencia-wasm.txt
```

Entram o nome do pacote, suas fontes e os testes. `ModelPipeline` transforma os dados do TFLite em estruturas do runtime e coordena os dois ramos. Saem WAT, WASM e relatórios. Caminhos, classes, formato e pesos são específicos do modelo; serialização, alocação e protocolo de execução são compartilhados. Os relatórios 02–11 são gravados durante a extração, antes da inferência; a posição de `reports/` ao final não significa uma gravação única.

## Árvore observada

```text
master-degree-project/
├── main.py                         CLI
├── requirements.txt                dependências Python
├── setup_env.ps1                    criação/ativação de .venv
├── README.md
├── .gitignore
├── adapters/                       base, binary_folders, imagenet_topk, registry
├── extractor/                      15 arquivos Python, incluindo __init__.py
├── inference/
│   └── wasm_inference.py            host Wasmtime
├── pipeline/                       config, package, pipeline, compiler
├── models/
│   ├── drowsiness/
│   │   ├── model.toml
│   │   ├── model_int8_esp32.tflite
│   │   ├── test/{drowsy,non_drowsy}/
│   │   ├── generated/{model.wat,model.wasm}
│   │   └── reports/                11 relatórios
│   └── mobilenetv2_alpha035/
│       ├── model.toml
│       ├── mobilenetv2_alpha035_quant.tflite
│       ├── labels/imagenet_class_index.json
│       ├── test/img/aviao_uint8.raw
│       ├── wat/model_template.wat
│       ├── generated/{model.wat,model.wasm}
│       └── reports/                11 relatórios
├── img_mobilenetv2/aviao_uint8.raw   cópia fora do pacote
├── wat/templates/
│   ├── mobilenet_int8_v1.wat        selecionado por drowsiness
│   └── model_template.wat          legado, sem manifest apontando para ele
├── tests/test_model_packages.py
├── docs/                           referência atual e material histórico
├── .venv/                          ambiente local antigo
├── .venv-models/                    ambiente usado nas verificações
└── __pycache__/                    cache local; também existe em módulos
```

Esta árvore agrupa arquivos repetitivos; o [inventário](14-inventario-e-rastreabilidade.md) relaciona cada módulo e os conjuntos de dados. Entra a configuração de cada diretório `models/`; o pipeline lê suas fontes e escreve nas duas pastas de artefatos. `img_mobilenetv2/` não é consultado pelo manifesto atual. `.git/`, caches e ambientes são infraestrutura local, não parte do runtime gerado.

## Responsabilidades e fronteiras

| Camada | Decide | Não decide |
|---|---|---|
| CLI | Nome e listagem dos pacotes | Arquitetura da rede |
| ModelPackage | Resolução de fontes e destinos | Layout binário |
| ModelConfig | Leitura TOML e validações explícitas | Compatibilidade numérica completa |
| ModelPipeline | Ordem das etapas e persistência | Classes ImageNet ou labels binários |
| extractor | Grafo, blobs e parâmetros de operadores | Seleção do adapter |
| wat_generator | Placeholders e data segments | Implementação matemática dos kernels |
| wasm_compiler | Conversão textual para binário | Inferência e métricas |
| inference | Instância, memória, chamada e coleta de erros | Ranking e acurácia |
| adapters | Descoberta, preparação e interpretação | Compilação WAT |

`ModelPipeline` é uma orquestração sequencial fixa, semelhante à ideia de pipeline/Template Method, mas não implementa uma classe-base com hooks de subclasses. `TestAdapter` usa Strategy/Adapter por composição. `ADAPTERS` e `create_adapter` formam Registry/Simple Factory. Não existe descoberta automática de plugins.

## Fontes e artefatos

Fontes: Python, `model.toml`, TFLite, template, labels e RAWs. Artefatos: `generated/model.wat`, `generated/model.wasm`, `reports/02-...` até `12-...`. O pipeline pode recriar esses arquivos se fontes, dependências e testes forem válidos. Não limpa arquivos extras, não cria versões, não escreve atomicamente e pode deixar resultados de execuções distintas após uma falha. Não modifica o TFLite durante uma execução normal.

## Ordem recomendada de leitura

Comece por CLI, pacote e manifesto (01–03); acompanhe a orquestração (04) e as interfaces de teste (05–07); leia o ABI (08) antes de editar templates; consulte modelos, tutorial, testes e fluxo (09–12). Os capítulos 20–33 descrevem cada módulo do extrator. O capítulo 99 separa limitações atuais de propostas de evolução.
