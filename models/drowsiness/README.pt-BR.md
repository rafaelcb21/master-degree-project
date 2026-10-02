[English](README.md) | [Português (Brasil)](README.pt-BR.md)

# Drowsiness MobileNetV2

[Documentação principal](../../README.pt-BR.md) · [Comparação dos pacotes](../../docs/09-modelos-e-pacotes.pt-BR.md)

## Objetivo

Pacote de classificação binária de sonolência. O manifest nomeia a rede como MobileNetV2 e define duas classes: `drowsy` (label 1) e `non_drowsy` (label 0). O projeto usa essa rede para testar a extração TFLite, conversão RGB565 e execução quantizada no runtime WAT. O arquivo chama-se `model_int8_esp32.tflite`, mas o fluxo Python aqui executa Wasmtime no host, não um ESP32.

## Arquivos e dependências do pacote

```text
models/drowsiness/
├── README.md
├── model.toml
│   ├── model_int8_esp32.tflite
│   ├── ../../wat/templates/mobilenet_int8_v1.wat
│   ├── input: rgb565 + rgb565_to_rgb888
│   └── test: binary-folders + datasets/classes
├── model_int8_esp32.tflite
├── test/
│   ├── drowsy/       1000 RAWs
│   └── non_drowsy/   1000 RAWs
├── generated/
│   ├── model.wat
│   └── model.wasm
└── reports/          11 arquivos, listados abaixo
```

Entram o manifest, TFLite, template externo e RAWs; `ModelPackage` os resolve e o pipeline escreve os artefatos locais. Os arquivos de teste e as classes são específicos deste modelo; o template é compartilhado. O pacote depende desse arquivo fora da pasta e não pode ser distribuído isoladamente sem incluí-lo ou ajustar a configuração. Não há pasta labels ou template local neste pacote.

## Execução

Na raiz do repositório:

```powershell
python main.py
python main.py --model drowsiness
```

Os comandos são equivalentes, pois drowsiness é o default. No ambiente local usado na validação também é possível usar `.venv-models/Scripts/python.exe` no lugar de `python`.

## Formato RAW e synthetic layer

Cada imagem é 128×128, 2 bytes por pixel, total **32768 bytes**, sem cabeçalho. O WAT lê little-endian com `i32.load16_u`: bits 15–11 são R, 10–5 são G e 4–0 são B. Não existe troca de endianness no adapter. Pixel vermelho máximo é valor 0xf800, representado por bytes `00 f8`. O arquivo deve estar previamente redimensionado; nenhum módulo faz resize.

```text
RAW RGB565 (32768 bytes)
             │ BinaryFoldersAdapter lê sem alterar
             ▼
           SLOT0
             │ host grava memory[0]=65
             ▼
┌─────────────────────────────┐
│ camada sintética            │
│ RGB565_TO_RGB888            │
│ R5/G6/B5 → R8/G8/B8         │
└─────────────┬───────────────┘
              ▼
            SLOT1 (49152 bytes RGB888)
              ▼
      QUANTIZE real do TFLite
              ▼
        restante da rede
```

Entram bytes RGB565 do dataset; a sintética WAT expande canais por replicação de bits. Sai RGB888 UINT8 para a primeira operação do grafo real. Formato/dimensões são do pacote; OP8 e as flags são do runtime. `synthetic_layer_count=1` e `slot_shift=1`: reserva-se mais um registro e o mapa lógico de slots é rotacionado em 1. O TFLite original tem 67 operadores; o runtime tem 68 registros.

## Adapter e dados de teste

`discover_cases()` exige duas classes e datasets não vazios, percorre primeiro `test/drowsy` (1000 RAWs, label 1), depois `test/non_drowsy` (1000 RAWs, label 0), com arquivos ordenados dentro de cada pasta. Todos os RAWs encontrados têm 32768 bytes. `prepare_input()` apenas lê os bytes RGB565. `evaluate_output()` usa dois valores UINT8 e o zero point/scale do TFLite. `build_report()` lista cada caso e agrega acertos, inválidos e acurácia; erros por caso são acrescentados pelo pipeline.

## Saída e interpretação binária

A ordem é `output[0] → drowsy → label 1`, `output[1] → non_drowsy → label 0`. Não é a ordem crescente de labels. `score=q/256`, pois scale=1/256 e zp=0. A classe vencedora tem o maior valor único; empate ou soma de scores≤0 é inválido. Um inválido tem result=None e não conta como acerto. Erros que impedem gerar um registro são excluídos do denominador; inválidos permanecem.

```text
2 bytes UINT8
      │
      ▼
valores e scores dequantizados
      │
      ├── empate/soma zero ──► inválido, right=False
      └── máximo único ─────► índice → classes[index].label
                                       │
                                       ▼
                               compara com label da pasta
                                       ▼
                              acertos / casos processados
```

Entram vetor de saída e ground-truth da pasta. O adapter calcula validade e acerto; sai um registro e a métrica agregada. Labels pertencem ao pacote; o critério binário pertence ao adapter compartilhável. O resultado observado no relatório atual é **1965/2000 = 98,25%**, com **5 inválidos/empates e 0 erros**. Isso é desempenho nesse conjunto, sem inferência sobre outros datasets.

## Entrada e saída medidas no TFLite

Os valores abaixo foram lidos do subgrafo 0 com os bindings do projeto; não foram inferidos pelo nome do arquivo.

| Propriedade | Entrada | Saída |
|---|---|---|
| Shape | `[1, 128, 128, 3]` | `[1, 2]` |
| Elementos | `49152` | `2` |
| Dtype | `uint8` | `uint8` |
| Scale | `0.003921508323401213` | `0.00390625` |
| Zero point | `0` | `0` |

O pipeline interpreta a entrada como NHWC: batch 1, altura e largura nas posições 1 e 2, três canais na posição 3. O FlatBuffer guarda shape e tipo; a interpretação RGB/BGR vem do manifest e dos kernels. Ambos os modelos expõem UINT8, mesmo tendo operações internas INT8.

## Manifesto selecionado

```toml
[model]
name = "Drowsiness MobileNetV2"
tflite = "model_int8_esp32.tflite"
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
path = "test/drowsy"
label = 1
[[test.datasets]]
path = "test/non_drowsy"
label = 0
[[classes]]
name = "drowsy"
label = 1
[[classes]]
name = "non_drowsy"
label = 0
```

Os caminhos são resolvidos a partir desta pasta. O significado e a validação de cada campo estão na [referência TOML](../../docs/03-model-config-manifesto.pt-BR.md).

## Arquitetura encontrada no FlatBuffer

O arquivo tem 618376 bytes, 1 subgrafo e 175 tensores. Foram encontrados 67 operadores:

| Operador | Quantidade |
|---|---:|
| QUANTIZE | 2 |
| CONV_2D | 35 |
| DEPTHWISE_CONV_2D | 17 |
| ADD | 10 |
| MEAN | 1 |
| FULLY_CONNECTED | 1 |
| SOFTMAX | 1 |

O primeiro operador é QUANTIZE. O final é FULLY_CONNECTED → SOFTMAX → QUANTIZE. O runtime usa os kernels WAT próprios descritos no [capítulo 13](../../docs/13-runtime-wat.pt-BR.md); não executa um interpretador TFLite.

## Geração e execução

```text
model_int8_esp32.tflite
             │
             ▼
ModelPipeline: grafo / slots / parâmetros / memória
             │ + template do manifest
             ▼
generated/model.wat
             │ wasmtime.wat2wasm
             ▼
generated/model.wasm
             │ host Wasmtime + adapter
             ▼
reports/12-inferencia-wasm.txt
```

Entra o TFLite original e a configuração deste pacote; o pipeline materializa dados e código, compila e testa. Saem dois artefatos e onze relatórios. Modelo, template selecionado e RAWs são fontes específicas; extração, ABI e compilação são compartilhados. Uma falha pode deixar artefatos parciais ou antigos, pois não há transação. O TFLite não é reescrito.

## Memória registrada

```text
REGIAO              BASE       BYTES         END
------------------------------------------------
WEIGHTS             2048      384608      386656
BIAS              386656       28168      414824
MUL               414832       28172      443004
SHIFT             443008       28172      471180
Q6                471184       28168      499352
PARAMS            499360        7888      507248
SLOT0             507248      196608      703856
SLOT1             703856      196608      900464
SLOT2             900464      196608     1097072
```

Entram os comprimentos dos blobs e o maior tensor. O extrator calcula bases alinhadas; saem regiões físicas usadas pelo WAT. Esses números pertencem ao pacote; páginas de 65536 bytes, três slots e registros de 116 bytes são convenções compartilhadas. END é exclusivo e não é o último byte ocupado.

## Relatórios produzidos

| Arquivo | Conteúdo |
|---|---|
| [02-grafo.txt](reports/02-grafo.txt) | Tipos, labels e dependências de operadores. |
| [03-alocacao-slots.txt](reports/03-alocacao-slots.txt) | Slots lógicos e operações in-place. |
| [04-mapeamento-tensor-slot.txt](reports/04-mapeamento-tensor-slot.txt) | IDs de tensores associados a slots e pendências. |
| [05-pesos-bias.txt](reports/05-pesos-bias.txt) | Shapes, offsets e bytes dos pesos/bias. |
| [06-quantizacao.txt](reports/06-quantizacao.txt) | Scales, multiplicadores, shifts e limites Q6. |
| [07-slot-bytes.txt](reports/07-slot-bytes.txt) | Maior tensor não constante e capacidade de cada slot. |
| [08-layout-parametros.txt](reports/08-layout-parametros.txt) | Bases de WEIGHTS, BIAS, MUL, SHIFT, Q6 e PARAMS. |
| [09-layer-params.txt](reports/09-layer-params.txt) | Campos por camada, mapa runtime e parâmetros especiais. |
| [10-params-blob.txt](reports/10-params-blob.txt) | Registros serializados, ponteiros absolutos e padding. |
| [11-layout-final-memoria.txt](reports/11-layout-final-memoria.txt) | Regiões físicas, fim, páginas e espaço residual. |
| [12-inferencia-wasm.txt](reports/12-inferencia-wasm.txt) | Resultados por imagem e erros de processamento. |

Os relatórios existentes são uma fotografia de execuções anteriores à tarefa documental. Com fontes/dependências válidas, uma execução completa os recria e sobrescreve; arquivos extras não são limpos. 09 descreve valores Python, 10 os campos serializados, e 12 a interpretação do adapter. Um campo relatado nem sempre é consumido pelo kernel, especialmente no softmax atual.

## Limitações e procedência

O objetivo da rede é indicado pelo nome/configuração e confirmado pela forma da saída; o repositório não fornece a história completa de treinamento, origem/licença dos RAWs ou script original de conversão. O teste atual não prova equivalência completa com TFLite. Consulte as [limitações verificadas](../../docs/99-inconsistencias-e-limitacoes.pt-BR.md), especialmente softmax fixo, kernels especializados e cobertura dos testes.
