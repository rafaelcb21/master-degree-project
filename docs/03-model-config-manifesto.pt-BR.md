[English](03-model-config-manifest.md) | [Português (Brasil)](03-model-config-manifesto.pt-BR.md)

# 03 — ModelConfig e referência de model.toml

[Índice](README.pt-BR.md) · Fonte: [pipeline/model_config.py](../pipeline/model_config.py)

## Leitura e representação

`ModelConfig.load(path)` abre o TOML em modo binário e usa `tomllib` (Python 3.11+) ou `tomli` como fallback. Lê as quatro tabelas `model`, `runtime`, `input`, `test` e constrói uma dataclass congelada. Os campos planos são `name`, `tflite`, `wat_template`, `contract`, `num_slots`, `input_format`, `synthetic_layer`, `test`, `classes`. `test` e `classes` permanecem coleções mutáveis, sem conversão para objetos especializados.

```text
model.toml (bytes)
        │
        ▼
tomllib.load / tomli.load
        │  dict de tabelas
        ▼
campos obrigatórios + defaults
        │
        ├── contrato == layerparam-v1?
        ├── num_slots == 3?
        └── par formato/camada permitido?
        │
        ▼
ModelConfig ──► ModelPackage ──► pipeline + adapter
```

Entra o arquivo do pacote; o loader extrai valores e aplica três verificações explícitas; sai a dataclass. Caminhos, classes e testes são específicos do modelo; os valores admitidos representam os limites comuns do runtime e dos adapters atuais.

## Campos: tipos esperados, defaults e consumidores

Os tipos desta tabela são os tipos esperados para uso correto. Type hints não validam tipos em runtime; o loader não implementa um schema TOML completo.

| Campo TOML | Tipo esperado | Obrigatoriedade/default | Quem usa / valores e exemplo |
|---|---|---|---|
| `[model].name` | string | Obrigatório | CLI na listagem; `"Drowsiness MobileNetV2"` |
| `[model].tflite` | string de caminho | Obrigatório | Package valida, loader lê; `"model_int8_esp32.tflite"` |
| `[runtime].wat_template` | string de caminho | Obrigatório | Package valida, gerador lê; `"wat/model_template.wat"` |
| `[runtime].contract` | string | Obrigatório | Config exige exatamente `"layerparam-v1"` |
| `[runtime].num_slots` | inteiro | Opcional: `3` | Config exige igualdade com 3; alocação, mapeamento e memória |
| `[input].format` | string | Obrigatório | `rgb565`, `bgr888`, `rgb888`, nas combinações abaixo; usado pelo adapter |
| `[input].synthetic_layer` | string | Obrigatório | `rgb565_to_rgb888` ou `none`; pipeline, LayerParams e runner |
| `[test].adapter` | string | Obrigatório | Registry: `binary-folders` ou `imagenet-topk` |
| `[test].datasets` | lista de tabelas | Exigida pelo adapter binário; default interno `[]` rejeitado | Cada tabela tem `path` e `label` |
| `[[test.datasets]].path` | string de caminho | Obrigatório no dataset | `raw_files`, ex.: `"test/drowsy"` |
| `[[test.datasets]].label` | inteiro esperado | Obrigatório no dataset | Deve pertencer aos labels das classes; ex.: `1` |
| `[test].path` | string de caminho | Obrigatório para ImageNet | `raw_files`, ex.: `"test/img"` |
| `[test].labels` | string de caminho | Obrigatório para ImageNet | JSON objeto índice → `[wnid, class_name]` |
| `[test].top_k` | inteiro positivo | Opcional: `15` | ImageNet valida no discovery e usa no slice do ranking |
| `[[classes]]` | lista de tabelas | Default `[]`; binário exige tamanho 2 | Ordem dos elementos corresponde à ordem da saída |
| `[[classes]].name` | string esperada | Usada nos manifests atuais | Aparece no relatório da lista de classes; o código não a exige para decidir o vencedor |
| `[[classes]].label` | inteiro esperado | Obrigatório para o adapter binário | Valor retornado ao vencer aquele índice |

Não existem campos configuráveis de batch, alinhamento, kernel base, normalização, endereço de entrada, caminho de saída ou nome do export de execução. `BATCH`, `ALIGN` e `KERNEL_BASE_HINT` vêm de `extractor/config.py`.

## Combinações realmente aceitas

| `format` | `synthetic_layer` | Count/shift | Adapter que atualmente implementa a preparação |
|---|---|---|---|
| `rgb565` | `rgb565_to_rgb888` | 1 | `binary-folders` |
| `bgr888` | `none` | 0 | `imagenet-topk`, troca B/R |
| `rgb888` | `none` | 0 | `imagenet-topk`, mantém canais |

A propriedade `synthetic_layer_count` retorna `int(self.synthetic_layer != "none")`; depende da validação anterior para que qualquer valor diferente de `none` represente precisamente uma camada. O loader valida o par formato/camada, mas não o cruzamento com o adapter. Por exemplo, `binary-folders` com BGR/none passa pela configuração e falha em `prepare_input`.

## Exemplos completos e mínimos

Consulte os manifests reais [drowsiness](../models/drowsiness/model.toml) e [ImageNet](../models/mobilenetv2_alpha035/model.toml). Exemplo de um terceiro pacote binário compatível, com nomes meramente ilustrativos:

```toml
[model]
name = "Experimento binário"
tflite = "model.tflite"
[runtime]
contract = "layerparam-v1"
wat_template = "../../wat/templates/mobilenet_int8_v1.wat"
num_slots = 3
[input]
format = "rgb565"
synthetic_layer = "rgb565_to_rgb888"
[test]
adapter = "binary-folders"
[[test.datasets]]
path = "test/positivo"
label = 1
[[test.datasets]]
path = "test/negativo"
label = 0
[[classes]]
name = "positivo"
label = 1
[[classes]]
name = "negativo"
label = 0
```

Esse exemplo só é correto se o índice 0 da saída do TFLite significar positivo e o índice 1 negativo. O código não infere a semântica das classes a partir do modelo ou da ordem alfabética das pastas.

## Validações e limites

Faltas de chaves e alguns tipos inválidos durante a construção viram `ValueError("Manifesto incompleto...")`. Erro de sintaxe TOML é levantado pelo parser; ausência do arquivo vem do filesystem. Chaves desconhecidas são ignoradas, não rejeitadas. A propriedade `contract` não seleciona implementações diferentes: hoje ela apenas aceita ou rejeita o único nome conhecido.

`num_slots=3.0` pode passar pela comparação de igualdade, mas falhar adiante quando usado em `range`; `top_k=true` é um `bool`, subclasse de `int`, e passa na checagem do adapter. Esses são limites da validação atual, não formatos recomendados. Labels duplicados, conjuntos incompletos de datasets e tipos de labels não são auditados de forma abrangente. A existência dos caminhos é verificada em fases posteriores, conforme o consumidor.
