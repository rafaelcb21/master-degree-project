# 05 — Adapters de teste e registry

[Índice](README.md) · Fontes: [base.py](../adapters/base.py), [binary_folders.py](../adapters/binary_folders.py), [imagenet_topk.py](../adapters/imagenet_topk.py), [registry.py](../adapters/registry.py)

## Fronteira de responsabilidade

O adapter é a Strategy de teste: adapta uma organização de arquivos e uma semântica de saída à interface do runner. Não carrega TFLite, não compila e não acessa a memória Wasmtime. Recebe o pacote e metadados dos tensores, devolve bytes ou registros Python. O runner não conhece nomes de classes nem decide acertos.

```text
                  model.toml
                      │ test.adapter
                      ▼
                  registry.py
                      │ create_adapter(package)
          ┌───────────┴─────────────┐
          ▼                         ▼
    binary-folders             imagenet-topk
          ▼                         ▼
 BinaryFoldersAdapter      ImageNetTopKAdapter
          │                         │
   label por pasta           labels por índice
   acerto / empate           ranking de scores
          └────────────┬────────────┘
                       ▼
                  TestAdapter
```

Entra a string do manifesto. A factory consulta `ADAPTERS` e instancia a classe com o pacote. Sai uma Strategy com interface comum; os dados das pastas e classes são específicos do modelo, enquanto o protocolo de métodos é compartilhado. Nome desconhecido levanta `ValueError` com as alternativas disponíveis. O registry é explícito: não varre módulos nem usa entry points.

## base.py: tipos e métodos

`TestCase` é dataclass congelada com `path: Path` e `label: int | None = None`. Não abre arquivos e não valida o label. `TestAdapter(ABC)` guarda `package` e `config` no construtor. Os quatro métodos abstratos impedem instanciar uma implementação incompleta.

| Método | Entrada | Saída e responsabilidade |
|---|---|---|
| `raw_files(path)` | Caminho relativo/absoluto aceito pelo pacote | Lista ordenada de arquivos do diretório imediato, extensão `.raw` sem diferenciar maiúsculas; erro se pasta ausente ou sem RAW |
| `discover_cases()` | Configuração armazenada | Iterable de `TestCase`; pipeline materializa com `list` |
| `prepare_input(case, input_info)` | Caso e metadados | Bytes na representação que será escrita no slot |
| `evaluate_output(case, output, output_info)` | Bytes lidos do WASM | Registro de resultado para o relatório |
| `build_report(results)` | Dicionário com registros/erros | String do relatório de domínio |
| `decode_output(output, info)` | Bytes, dtype, scale, zero point | Par `(values, scores)` como arrays NumPy |

`decode_output` usa `np.frombuffer(..., dtype=info["dtype"])` e `scores = (values.astype(float) - zero_point) * scale`. Não aplica softmax, não divide pela soma e não verifica a quantidade de classes. A interpretação INT8 é diferente de UINT8: o byte `0xff` representa −1 ou 255. A escala escalar positiva preserva a ordenação dos valores quantizados.

```text
discover_cases() ──► lista de TestCase
                           │ para cada caso
                           ▼
                  prepare_input(case, info)
                           │ bytes
                           ▼
                 runner escreve / executa / lê
                           │ bytes da saída
                           ▼
                 evaluate_output(case, output, info)
                           │ registro
                           ▼
                      results.records
                           ▼
                    build_report(results)
```

Entram arquivos e metadados; o adapter prepara e interpreta, o runner executa. Saem registros e texto. O formato de imagem e a semântica do resultado são específicos; a passagem de bytes é comum. Exceções por caso são coletadas pelo runner; falhas no discovery ocorrem antes dele.

## binary_folders.py: classificação binária

`discover_cases` é um gerador. Ao iterá-lo, exige exatamente duas classes, ao menos um dataset e labels dos datasets presentes nas classes. Percorre datasets na ordem do TOML e arquivos em ordem de `Path`. Não exige um dataset para cada classe, labels distintos ou quantidades balanceadas. Cada caso recebe o label de sua pasta.

`prepare_input` exige `config.input_format == "rgb565"` e lê o arquivo integralmente. Não converte nem troca bytes. A dimensão e o comprimento são verificados no runner. A conversão RGB565 fica na camada sintética WAT, não no adapter.

`evaluate_output` decodifica a saída e exige `len(values) == len(classes)`. Encontra todos os índices cujo valor é o máximo. É inválido se houver mais de um vencedor ou se a soma dos scores for menor ou igual a zero. Nesse caso `result=None`, `invalid=True`, `right=False`; não existe classe −1 no registro atual. Em um vencedor único, o resultado é `classes[winner_index]["label"]`, independentemente do valor numérico do índice.

```text
bytes de saída + dtype/scale/zero point
                  │
                  ▼
           values e scores
                  │
          máximo / índices empatados
                  │
       ┌──────────┴───────────────────┐
       ▼                              ▼
empate ou soma <= 0              vencedor único
       │                              │
result=None                   classes[índice].label
right=False                          │
       │                       compara com case.label
       └──────────────┬───────────────┘
                      ▼
        registro + acurácia no relatório
```

Entram dois scores e o label esperado da pasta; o adapter decide validade e acerto. Saem `file`, `label`, `result`, `invalid`, `right`, `quantized`, `scores`. A ordem/semântica das classes pertence ao modelo; dequantização e critério binário pertencem à Strategy.

`build_report` lista classes, todos os registros e resumo. `accuracy = 100 * correct / len(records)`, ou zero se não houver registros. Casos inválidos entram no denominador; erros que impediram criar um registro não entram. O pipeline acrescenta a lista de erros ao texto; o adapter não faz isso. Exemplo real: `[200,55]`, scale `1/256`, zp 0, produz scores `0,78125` e `0,21484375`; no pacote atual o índice 0 significa label 1 (`drowsy`).

## imagenet_topk.py: descoberta e labels

`discover_cases` carrega o JSON em UTF-8 antes de listar RAWs. Exige objeto não vazio e, em cada entrada, uma lista de exatamente duas strings não vazias: `[wnid, class_name]`. A cobertura de todos os índices de saída só é verificada em `evaluate_output`. O código não valida formato de synset, coerência semântica com o TFLite ou exclusividade de nomes. O caso não recebe ground-truth.

`top_k` é lido com default 15, deve ser inteiro positivo segundo `isinstance(..., int)`. Não há teto explícito: K maior que o número de classes retorna todos os índices pelo slice. Um detalhe de Python é que `True` passa nesse teste de tipo. Use inteiro TOML normal.

## Preparação BGR/RGB

O RAW é lido como `np.uint8`; tamanho deve ser `input_info["elements"]`. BGR usa `reshape(-1,3)[:,::-1].copy().reshape(-1)`, invertendo canais em cada pixel; RGB mantém a ordem. Não há resize, rotação, recorte, leitura de cabeçalho ou metadados. Não use PNG renomeado para `.raw`.

Para tensor UINT8, os pixels RGB são escritos diretamente. Para INT8, a regra fixa é MobileNet: `real = pixel/127.5 - 1`; `q = clip(rint(real/scale + zero_point), -128,127)`, seguido de conversão para `np.int8`. Portanto o adapter não serve automaticamente para qualquer normalização INT8. `np.rint` resolve meios para o inteiro par.

## Ranking e relatório

```text
saída WASM: N bytes / N classes
                │
                ▼
     decode_output: dtype correto
                │
                ▼
   score[i] = (q[i] - zp) × scale
                │
                ▼
 np.argsort(-scores, kind="stable")
                │
                ▼
           primeiros K índices
                │
                ▼
       ┌───────────────────────┐
       │ índice / class_name   │
       │ wnid                  │
       │ quantized / score     │
       └───────────────────────┘
```

Entram scores de todas as classes e labels do JSON. O adapter ordena em ordem decrescente; empates mantêm a ordem original dos índices. Sai uma lista Top-K, atualmente Top-15. N e labels são específicos do modelo; a operação de ranking é genérica. Não há cálculo de acurácia ImageNet, pois falta ground-truth por caso.

Cada registro tem `file` e `top`; cada item tem `index`, `wnid`, `class_name`, `quantized`, `score`. O relatório usa o nome da classe na primeira linha e os demais valores em linhas indentadas. Score é o valor dequantizado do runtime; a implementação atual do softmax não justifica tratá-lo como probabilidade calibrada ou exatamente equivalente ao TFLite.

## Novo adapter

Implemente os quatro métodos, registre a classe em `ADAPTERS`, configure `test.adapter` e adicione os dados necessários ao TOML. O loader guarda `test` como dict, permitindo novos campos nesse bloco sem mudar o pipeline. Ainda é preciso respeitar as validações de imagem, dtype, slots e número de entradas/saídas do pipeline. `adapters/__init__.py` está vazio e não registra adapters por efeitos de importação.
