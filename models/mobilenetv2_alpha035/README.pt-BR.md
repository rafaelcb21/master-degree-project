[English](README.md) | [Português (Brasil)](README.pt-BR.md)

# MobileNetV2 Alpha 0.35 ImageNet

[Documentação principal](../../README.pt-BR.md) · [Comparação dos pacotes](../../docs/09-modelos-e-pacotes.pt-BR.md)

## Objetivo

O manifest identifica este pacote como MobileNetV2 Alpha 0.35 para classificação ImageNet. O TFLite expõe 1000 saídas, associadas ao JSON de classes. O teste atual usa uma imagem RAW de avião e produz Top-15, sem calcular acurácia por ground-truth. A largura alpha 0.35 é indicada pelo nome do modelo/arquivo; não há receita de treinamento neste fluxo que permita reconstituir sua origem completa.

## Arquivos

```text
models/mobilenetv2_alpha035/
├── README.md
├── model.toml
│   ├── mobilenetv2_alpha035_quant.tflite
│   ├── wat/model_template.wat
│   ├── input: bgr888 + none
│   └── test: imagenet-topk / top_k=15
├── mobilenetv2_alpha035_quant.tflite
├── labels/imagenet_class_index.json
├── test/img/aviao_uint8.raw
├── wat/model_template.wat
├── generated/
│   ├── model.wat
│   └── model.wasm
└── reports/          11 arquivos, listados abaixo
```

Entram as fontes locais do pacote; o pipeline escreve generated e reports. O manifest escolhe o template local, que tem conteúdo idêntico ao template ativo compartilhado na revisão atual. Labels e imagem pertencem ao pacote; ABI e geração são comuns. Existe outra cópia do RAW em `img_mobilenetv2/` na raiz, não usada pelo manifest.

## Execução

Na raiz:

```powershell
python main.py --model mobilenetv2_alpha035
```

O top_k é configurado no TOML, não por argumento da CLI. A descoberta encontra exatamente **um arquivo**, `test/img/aviao_uint8.raw`, de **150528 bytes**. Não há label esperado atribuído à pasta ou ao caso.

## Formato de entrada e ausência de sintética

RAW de 224×224, três canais UINT8, 3 bytes por pixel, ordem **B,G,R**, sem cabeçalho: 224×224×3=150528 bytes. O adapter não decodifica imagem comprimida e não redimensiona. O nome `uint8` do RAW descreve seus bytes; o campo `input.format=bgr888` determina a ordem assumida. O arquivo sozinho não carrega metadados capazes de confirmar essa ordem.

```text
RAW BGR888
    │
    ▼
ImageNetTopKAdapter.prepare_input
    │ reshape(-1,3)[:,::-1].copy()
    ▼
RGB888 UINT8
    │ memory.write
    ▼
  SLOT0
    ▼
primeira operação REAL: QUANTIZE
    ▼
restante do TFLite traduzido para WAT
```

Entram bytes BGR; o adapter troca os canais B/R e sai RGB para SLOT0. O manifest usa `synthetic_layer="none"`, count=0 e shift=0: nenhuma operação extra é inserida. A preparação é específica do teste; a execução usa o runtime comum. Como a entrada deste TFLite é UINT8, o ramo de normalização INT8 do adapter não é executado.

## Adapter e labels

`discover_cases()` lê o JSON, valida que cada valor seja `[wnid,class_name]`, valida top_k e lista os RAWs. O JSON contém 1000 índices de classe; por exemplo, `"404": ["n02690373", "airliner"]`. `prepare_input()` verifica comprimento e troca B/R. `evaluate_output()` lê a saída segundo UINT8, dequantiza, exige cobertura de todos os índices e ordena scores. `build_report()` mostra classe, wnid, q e score em linhas separadas.

A documentação anterior registra a obtenção dos labels em `https://storage.googleapis.com/download.tensorflow.org/data/imagenet_class_index.json`. Não há download automático durante a inferência. O JSON é fonte local; o código não valida semanticamente sua correspondência com o treinamento do modelo.

## Saída e Top-15

Saída `[1,1000]` UINT8, scale=1/256, zero point=0. Cada score é q/256. Não há aplicação de softmax em Python: o adapter apenas decodifica e ordena os valores produzidos pelo runtime.

```text
1000 bytes de saída
        │ dtype UINT8
        ▼
1000 valores quantizados q
        │ score=(q-zp)×scale
        ▼
1000 scores reais
        │ argsort(-scores, stable)
        ▼
ordem decrescente; empates preservam índices
        │ [:top_k], atualmente 15
        ▼
┌───────────────────────────┐
│ Top-1                     │
│ Top-2                     │
│ ...                       │
│ Top-15                    │
└───────────────────────────┘
```

Entram saída completa e labels. A Strategy seleciona K maiores scores e produz o relatório, sem ground-truth. N e nomes de classe são específicos; ordenação/dequantização são compartilhadas. K maior que N retorna N itens. Score não é chamado de probabilidade calibrada: o kernel softmax atual usa constantes e aproximações específicas, descritas nas limitações.

## Resultado observado

```text
1. [404] airliner
   wnid=n02690373
   q=226
   score=0.88281250
```

O relatório existente também traz space_shuttle e wing com q=11/score=0,04296875 nas posições seguintes. A execução registrada processou um caso sem erros. Esse teste de uma imagem não mede acurácia ImageNet e não comprova equivalência numérica com TFLite.

## Entrada e saída medidas no TFLite

Os valores abaixo foram lidos do subgrafo 0 com os bindings do projeto; não foram inferidos pelo nome do arquivo.

| Propriedade | Entrada | Saída |
|---|---|---|
| Shape | `[1, 224, 224, 3]` | `[1, 1000]` |
| Elementos | `150528` | `1000` |
| Dtype | `uint8` | `uint8` |
| Scale | `0.007843137718737125` | `0.00390625` |
| Zero point | `127` | `0` |

O pipeline interpreta a entrada como NHWC: batch 1, altura e largura nas posições 1 e 2, três canais na posição 3. O FlatBuffer guarda shape e tipo; a interpretação RGB/BGR vem do manifest e dos kernels. Ambos os modelos expõem UINT8, mesmo tendo operações internas INT8.

## Manifesto selecionado

```toml
[model]
name = "MobileNetV2 Alpha 0.35 ImageNet"
tflite = "mobilenetv2_alpha035_quant.tflite"
[runtime]
contract = "layerparam-v1"
wat_template = "wat/model_template.wat"
num_slots = 3
[input]
format = "bgr888"
synthetic_layer = "none"
[test]
adapter = "imagenet-topk"
path = "test/img"
top_k = 15
labels = "labels/imagenet_class_index.json"
```

Os caminhos são resolvidos a partir desta pasta. O significado e a validação de cada campo estão na [referência TOML](../../docs/03-model-config-manifesto.pt-BR.md).

## Arquitetura encontrada no FlatBuffer

O arquivo tem 1925904 bytes, 1 subgrafo e 175 tensores. Foram encontrados 67 operadores:

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
mobilenetv2_alpha035_quant.tflite
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
WEIGHTS             2048     1662048     1664096
BIAS             1664096       32160     1696256
MUL              1696256       32164     1728420
SHIFT            1728432       32164     1760596
Q6               1760608       32160     1792768
PARAMS           1792768        7776     1800544
SLOT0            1800544      602112     2402656
SLOT1            2402656      602112     3004768
SLOT2            3004768      602112     3606880
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
