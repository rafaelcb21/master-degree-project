# 12 — Fluxo completo e leitura dos relatórios

[Índice](README.md) · [Orquestração](04-model-pipeline.md) · [Comparação dos pacotes](09-modelos-e-pacotes.md)

## Exemplo acompanhado: sonolência

```text
python main.py --model drowsiness
                │
                ▼
model.toml → ModelPackage → BinaryFoldersAdapter
                │           2000 TestCase com label por pasta
                ▼
model_int8_esp32.tflite
                │ 67 operadores / 175 tensores
                ▼
grafo → 3 slots lógicos → tensor_to_slot
                │
                ├── pesos = 384608 bytes
                ├── bias  = 28168 bytes
                └── MUL/SHIFT/Q6
                ▼
slot_bytes = 196608; PARAMS_BASE = 499360
                │ synthetic_count=1, slot_shift=1
                ▼
68 LayerParams → 7888 bytes de PARAMS
                ▼
SLOT0=507248  SLOT1=703856  SLOT2=900464
                ▼
MEM_END=1097072 → 17 páginas
                ▼
template compartilhado → generated/model.wat → model.wasm
                │
                ▼
RAW 32768 bytes → SLOT0 → RGB565_TO_RGB888 → SLOT1
                ▼
67 operações reais → vetor UINT8 com 2 elementos
                ▼
adapter: índice 0=label 1; índice 1=label 0
                ▼
reports/12-inferencia-wasm.txt
```

Entram o pacote de sonolência e seus RAWs. O pipeline calcula os números indicados a partir das fontes; os valores foram confirmados nos relatórios existentes. Saem artefatos para 68 kernels, incluindo a sintética. Pesos, dimensões e número de casos são específicos; ABI, três slots e páginas de 65536 bytes são compartilhados.

## Variante ImageNet

O outro pacote tem os mesmos 67 tipos/quantidades de operações TFLite, mas sem sintética. `PARAMS_BASE=1792768`, área de parâmetros 7776 bytes, `slot_bytes=602112`; slots em 1800544, 2402656 e 3004768. `MEM_END=3606880`, 56 páginas. O adapter converte BGR para RGB antes de escrever 150528 bytes em SLOT0. A saída tem 1000 elementos e produz Top-15. Não existe label esperado por pasta nesse adapter.

## Catálogo dos 11 relatórios

Todos ficam em `models/<nome>/reports/`; não existe relatório 01 produzido pelo pipeline atual.

| Arquivo | Conteúdo | Pergunta de diagnóstico |
|---|---|---|
| `02-grafo.txt` | Tipo, label e vizinhos acima/abaixo | As dependências do residual estão presentes? |
| `03-alocacao-slots.txt` | Slots lógicos de entrada/saída e marca in-place | Uma área está sendo reutilizada enquanto ainda possui leitores? |
| `04-mapeamento-tensor-slot.txt` | Tensor IDs, produtores, pendências e fechamento | Todos os tensores usados têm armazenamento? |
| `05-pesos-bias.txt` | Offsets, shapes, dtypes e tamanhos | O tensor constante esperado foi extraído? |
| `06-quantizacao.txt` | Scales, zero points, multiplicadores, shifts, Q6 e offsets | A razão de escalas/quantização por canal corresponde ao modelo? |
| `07-slot-bytes.txt` | Tensores não constantes e maior necessidade de bytes | Qual tensor determina a memória de cada slot? |
| `08-layout-parametros.txt` | Bases e comprimentos dos blobs | Os blocos começam nos endereços esperados? |
| `09-layer-params.txt` | Campos por operação, slots e parâmetros especiais | ADD, QUANTIZE e sintética estão codificados corretamente? |
| `10-params-blob.txt` | Registros serializados, ponteiros e padding | Qual endereço o WAT realmente lerá? |
| `11-layout-final-memoria.txt` | Regiões, finais, páginas e espaço residual | Há memória suficiente para os slots e dados? |
| `12-inferencia-wasm.txt` | Resultado por RAW, resumo do adapter e erros | Quais casos foram processados e como foram interpretados? |

## Da hipótese ao erro localizado

```text
resultado inesperado
        │
        ├── RAW rejeitado? ──────► 12: tamanho/caminho/preparação
        ├── trap? ──────────────► 10/11: ponteiros e regiões
        ├── classes trocadas? ──► manifest classes/JSON/ordem dos canais
        ├── saturação? ─────────► 06/09: dtype, scale, zero point, flags
        └── valor divergente? ──► kernel WAT + tensores intermediários
```

Entra um sintoma; os relatórios permitem seguir do host até a representação binária. Sai uma etapa candidata para investigação, não uma prova automática da causa. Fontes do modelo determinam os dados esperados; o runtime determina a matemática e o endereçamento. Ausência de erro no relatório 12 não significa equivalência numérica com TFLite.

## Recriar e interpretar com cuidado

Uma execução bem-sucedida pode recriar os 11 relatórios e os dois artefatos. Não há histórico nem remoção de arquivos antigos. Caminhos absolutos nos registros tornam o texto diferente entre máquinas, mesmo quando os bytes inferidos coincidem. Alterações somente na documentação não regeneram os relatórios; um cabeçalho antigo em 09 pode ser apenas um artefato anterior, não o texto emitido pelo código atual.
