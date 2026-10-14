# Teste de consistência dos resultados — parecer 4.2

Base: relatório de comparações gerado em 2026-10-11T14:22:51.392900+00:00. 2000 imagens por par.

Processamento exclusivo de resultados armazenados, sem repetir inferências.

## Fontes

| Implementação | Execução | Arquivo |
| --- | --- | --- |
| WASM ESP32 | 51 | analysis/esp32_consensus/drowsiness/wasm/report.csv |
| TFLite ESP32 | 50 | analysis/esp32_consensus/drowsiness/tflite/report.csv |
| WASM desktop | 9 | models/drowsiness/reports/20261008T150239050848Z/12-inferencia-wasm.txt |
| TFLite desktop | 12 | models/drowsiness/reports_tflite/20261008T152221459939Z/results-report.json |

As execuções ESP32 51 e 50 são relatórios representativos derivados por consenso; o teste preserva essas fontes.

## Acertos recalculados por implementação

| Implementação | Total | Acertos | Erros com classe válida | SEM_PREDICAO | Registros ausentes |
| --- | ---: | ---: | ---: | ---: | ---: |
| WASM ESP32 | 2000 | 1966 | 29 | 5 | 0 |
| TFLite ESP32 | 2000 | 1990 | 9 | 1 | 0 |
| WASM desktop | 2000 | 1965 | 30 | 5 | 0 |
| TFLite desktop | 2000 | 1990 | 8 | 2 | 0 |

## Critérios

Identificadores são relacionados exatamente, preservando maiúsculas e minúsculas: A0001.raw e a0001.raw são imagens distintas. Classes: 0 = non_drowsy; 1 = drowsy. Saída sem classe utilizável, falha ou registro ausente recebe SEM_PREDICAO; a classe registrada não é substituída pelo argmax.

“Ambas não acertaram” inclui ausências; “ambas erraram com classes válidas” é apresentada separadamente. Os quatro resultados de acerto somam as imagens com rótulo conhecido e consistente. Mesma classe válida + classes válidas diferentes + pelo menos uma SEM_PREDICAO = total.

Os relatórios armazenam vetores quantizados de saída em UINT8 (0–255), apesar do modelo ter quantização interna INT8. Os valores são preservados, sem reinterpretá-los como INT8. Ordem completa: índice 0 = drowsy; índice 1 = non_drowsy. Igualdade quantizada compara os dois componentes alinhados, independentemente dos scores e da existência de classe válida. Vetores incompletos/ausentes não contam como idênticos.

A concordância válida exclui SEM_PREDICAO; a concordância por categoria inclui SEM_PREDICAO e usa todas as imagens. Duas ausências iguais são concordância de categoria, nunca uma classe válida.

## WASM ESP32 × TFLite ESP32

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1964 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 8 |
| Ambas erraram com classes válidas | 7 |
| Esquerda acertou e direita não acertou | 2 |
| Direita acertou e esquerda não acertou | 26 |
| Mesma classe predita (ambas válidas) | 1971 |
| Classes diferentes (ambas válidas) | 23 |
| Pelo menos uma SEM_PREDICAO | 6 |
| Ambas SEM_PREDICAO | 0 |
| Esquerda SEM_PREDICAO | 5 |
| Direita SEM_PREDICAO | 1 |
| Mesma categoria (inclui SEM_PREDICAO) | 1971 |
| Categorias diferentes (inclui SEM_PREDICAO) | 29 |
| Vetores quantizados completos idênticos | 1734 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 26 − 2 = 24.
Trocas de classe na tabela anterior: 23; recalculadas entre classes válidas: 23; mudanças incluindo SEM_PREDICAO: 29.

Concordância de classes válidas: 98,8465%; concordância de categorias: 98,5500%; igualdade dos vetores quantizados: 86,7000%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 964 | 2 | 0 |
| 1 | 21 | 1007 | 1 |
| SEM_PREDICAO | 5 | 0 | 0 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0007.raw | 0 | 1 | 0 | [225, 30] | [2, 254] | False | True |
| a0053.raw | 0 | 1 | 0 | [187, 68] | [113, 143] | False | True |
| a0240.raw | 0 | 1 | 0 | [225, 30] | [1, 255] | False | True |
| a0373.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0385.raw | 0 | 0 | 1 | [30, 225] | [227, 29] | True | False |
| a0388.raw | 0 | 1 | 0 | [187, 68] | [2, 254] | False | True |
| a0408.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0409.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [1, 255] | False | True |
| a0439.raw | 0 | 1 | 0 | [225, 30] | [1, 255] | False | True |
| a0477.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0510.raw | 0 | 1 | 0 | [251, 4] | [24, 232] | False | True |
| a0515.raw | 0 | 1 | 0 | [187, 68] | [4, 252] | False | True |
| a0559.raw | 0 | 1 | 0 | [187, 68] | [3, 253] | False | True |
| a0561.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0599.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0723.raw | 0 | 1 | 0 | [187, 68] | [29, 227] | False | True |
| a0738.raw | 0 | 1 | 0 | [251, 4] | [9, 247] | False | True |
| a0740.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0769.raw | 0 | 1 | 0 | [225, 30] | [5, 251] | False | True |
| a0815.raw | 0 | 1 | 0 | [187, 68] | [12, 244] | False | True |
| a0819.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0889.raw | 0 | 1 | 0 | [187, 68] | [33, 223] | False | True |
| a0895.raw | 0 | 1 | 0 | [187, 68] | [65, 191] | False | True |
| a0898.raw | 0 | 0 | 1 | [68, 187] | [151, 105] | True | False |
| a0944.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0960.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0963.raw | 0 | 1 | 0 | [187, 68] | [9, 247] | False | True |
| a0965.raw | 0 | 1 | 0 | [187, 68] | [24, 232] | False | True |
| a0968.raw | 0 | 1 | SEM_PREDICAO | [254, 1] | [128, 128] | False | False |

## WASM desktop × TFLite desktop

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1963 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 8 |
| Ambas erraram com classes válidas | 7 |
| Esquerda acertou e direita não acertou | 2 |
| Direita acertou e esquerda não acertou | 27 |
| Mesma classe predita (ambas válidas) | 1970 |
| Classes diferentes (ambas válidas) | 23 |
| Pelo menos uma SEM_PREDICAO | 7 |
| Ambas SEM_PREDICAO | 0 |
| Esquerda SEM_PREDICAO | 5 |
| Direita SEM_PREDICAO | 2 |
| Mesma categoria (inclui SEM_PREDICAO) | 1970 |
| Categorias diferentes (inclui SEM_PREDICAO) | 30 |
| Vetores quantizados completos idênticos | 1737 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 27 − 2 = 25.
Trocas de classe na tabela anterior: 23; recalculadas entre classes válidas: 23; mudanças incluindo SEM_PREDICAO: 30.

Concordância de classes válidas: 98,8460%; concordância de categorias: 98,5000%; igualdade dos vetores quantizados: 86,8500%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 963 | 1 | 1 |
| 1 | 22 | 1007 | 1 |
| SEM_PREDICAO | 5 | 0 | 0 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0007.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0053.raw | 0 | 1 | 0 | [187, 68] | [36, 220] | False | True |
| a0240.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0373.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0385.raw | 0 | 0 | 1 | [30, 225] | [151, 105] | True | False |
| a0388.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0391.raw | 0 | 0 | SEM_PREDICAO | [30, 225] | [128, 128] | True | False |
| a0408.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0409.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [1, 255] | False | True |
| a0439.raw | 0 | 1 | 0 | [225, 30] | [0, 255] | False | True |
| a0477.raw | 0 | 1 | 0 | [187, 68] | [11, 245] | False | True |
| a0510.raw | 0 | 1 | 0 | [251, 4] | [10, 246] | False | True |
| a0515.raw | 0 | 1 | 0 | [187, 68] | [7, 249] | False | True |
| a0559.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0561.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0599.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0723.raw | 0 | 1 | 0 | [187, 68] | [11, 245] | False | True |
| a0738.raw | 0 | 1 | 0 | [251, 4] | [5, 251] | False | True |
| a0740.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0769.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0815.raw | 0 | 1 | 0 | [187, 68] | [40, 216] | False | True |
| a0819.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0889.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0895.raw | 0 | 1 | 0 | [187, 68] | [12, 244] | False | True |
| a0944.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0960.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [3, 253] | False | True |
| a0963.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0965.raw | 0 | 1 | 0 | [187, 68] | [7, 249] | False | True |
| a0967.raw | 0 | 1 | SEM_PREDICAO | [255, 0] | [128, 128] | False | False |
| a0968.raw | 0 | 1 | 0 | [254, 1] | [105, 151] | False | True |

## WASM ESP32 × TFLite desktop

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1963 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 7 |
| Ambas erraram com classes válidas | 6 |
| Esquerda acertou e direita não acertou | 3 |
| Direita acertou e esquerda não acertou | 27 |
| Mesma classe predita (ambas válidas) | 1969 |
| Classes diferentes (ambas válidas) | 24 |
| Pelo menos uma SEM_PREDICAO | 7 |
| Ambas SEM_PREDICAO | 0 |
| Esquerda SEM_PREDICAO | 5 |
| Direita SEM_PREDICAO | 2 |
| Mesma categoria (inclui SEM_PREDICAO) | 1969 |
| Categorias diferentes (inclui SEM_PREDICAO) | 31 |
| Vetores quantizados completos idênticos | 1737 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 27 − 3 = 24.
Trocas de classe na tabela anterior: 24; recalculadas entre classes válidas: 24; mudanças incluindo SEM_PREDICAO: 31.

Concordância de classes válidas: 98,7958%; concordância de categorias: 98,4500%; igualdade dos vetores quantizados: 86,8500%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 963 | 2 | 1 |
| 1 | 22 | 1006 | 1 |
| SEM_PREDICAO | 5 | 0 | 0 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0007.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0053.raw | 0 | 1 | 0 | [187, 68] | [36, 220] | False | True |
| a0240.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0373.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0385.raw | 0 | 0 | 1 | [30, 225] | [151, 105] | True | False |
| a0388.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0391.raw | 0 | 0 | SEM_PREDICAO | [30, 225] | [128, 128] | True | False |
| a0397.raw | 0 | 0 | 1 | [0, 255] | [255, 1] | True | False |
| a0408.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0409.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [1, 255] | False | True |
| a0439.raw | 0 | 1 | 0 | [225, 30] | [0, 255] | False | True |
| a0477.raw | 0 | 1 | 0 | [187, 68] | [11, 245] | False | True |
| a0510.raw | 0 | 1 | 0 | [251, 4] | [10, 246] | False | True |
| a0515.raw | 0 | 1 | 0 | [187, 68] | [7, 249] | False | True |
| a0559.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0561.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0599.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0723.raw | 0 | 1 | 0 | [187, 68] | [11, 245] | False | True |
| a0738.raw | 0 | 1 | 0 | [251, 4] | [5, 251] | False | True |
| a0740.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0769.raw | 0 | 1 | 0 | [225, 30] | [3, 253] | False | True |
| a0815.raw | 0 | 1 | 0 | [187, 68] | [40, 216] | False | True |
| a0819.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0889.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0895.raw | 0 | 1 | 0 | [187, 68] | [12, 244] | False | True |
| a0944.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0960.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [3, 253] | False | True |
| a0963.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0965.raw | 0 | 1 | 0 | [187, 68] | [7, 249] | False | True |
| a0967.raw | 0 | 1 | SEM_PREDICAO | [255, 0] | [128, 128] | False | False |
| a0968.raw | 0 | 1 | 0 | [254, 1] | [105, 151] | False | True |

## WASM desktop × TFLite ESP32

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1963 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 8 |
| Ambas erraram com classes válidas | 7 |
| Esquerda acertou e direita não acertou | 2 |
| Direita acertou e esquerda não acertou | 27 |
| Mesma classe predita (ambas válidas) | 1970 |
| Classes diferentes (ambas válidas) | 24 |
| Pelo menos uma SEM_PREDICAO | 6 |
| Ambas SEM_PREDICAO | 0 |
| Esquerda SEM_PREDICAO | 5 |
| Direita SEM_PREDICAO | 1 |
| Mesma categoria (inclui SEM_PREDICAO) | 1970 |
| Categorias diferentes (inclui SEM_PREDICAO) | 30 |
| Vetores quantizados completos idênticos | 1734 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 27 − 2 = 25.
Trocas de classe na tabela anterior: 24; recalculadas entre classes válidas: 24; mudanças incluindo SEM_PREDICAO: 30.

Concordância de classes válidas: 98,7964%; concordância de categorias: 98,5000%; igualdade dos vetores quantizados: 86,7000%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 963 | 2 | 0 |
| 1 | 22 | 1007 | 1 |
| SEM_PREDICAO | 5 | 0 | 0 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0007.raw | 0 | 1 | 0 | [225, 30] | [2, 254] | False | True |
| a0053.raw | 0 | 1 | 0 | [187, 68] | [113, 143] | False | True |
| a0240.raw | 0 | 1 | 0 | [225, 30] | [1, 255] | False | True |
| a0373.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0385.raw | 0 | 0 | 1 | [30, 225] | [227, 29] | True | False |
| a0388.raw | 0 | 1 | 0 | [187, 68] | [2, 254] | False | True |
| a0397.raw | 0 | 1 | 0 | [254, 1] | [2, 254] | False | True |
| a0408.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0409.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [1, 255] | False | True |
| a0439.raw | 0 | 1 | 0 | [225, 30] | [1, 255] | False | True |
| a0477.raw | 0 | 1 | 0 | [187, 68] | [5, 251] | False | True |
| a0510.raw | 0 | 1 | 0 | [251, 4] | [24, 232] | False | True |
| a0515.raw | 0 | 1 | 0 | [187, 68] | [4, 252] | False | True |
| a0559.raw | 0 | 1 | 0 | [187, 68] | [3, 253] | False | True |
| a0561.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0599.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0723.raw | 0 | 1 | 0 | [187, 68] | [29, 227] | False | True |
| a0738.raw | 0 | 1 | 0 | [251, 4] | [9, 247] | False | True |
| a0740.raw | 0 | 1 | 0 | [187, 68] | [1, 255] | False | True |
| a0769.raw | 0 | 1 | 0 | [225, 30] | [5, 251] | False | True |
| a0815.raw | 0 | 1 | 0 | [187, 68] | [12, 244] | False | True |
| a0819.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [0, 255] | False | True |
| a0889.raw | 0 | 1 | 0 | [187, 68] | [33, 223] | False | True |
| a0895.raw | 0 | 1 | 0 | [187, 68] | [65, 191] | False | True |
| a0898.raw | 0 | 0 | 1 | [68, 187] | [151, 105] | True | False |
| a0944.raw | 0 | 1 | 0 | [187, 68] | [0, 255] | False | True |
| a0960.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [2, 254] | False | True |
| a0963.raw | 0 | 1 | 0 | [187, 68] | [9, 247] | False | True |
| a0965.raw | 0 | 1 | 0 | [187, 68] | [24, 232] | False | True |
| a0968.raw | 0 | 1 | SEM_PREDICAO | [254, 1] | [128, 128] | False | False |

## WASM ESP32 × WASM desktop

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1965 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 34 |
| Ambas erraram com classes válidas | 29 |
| Esquerda acertou e direita não acertou | 1 |
| Direita acertou e esquerda não acertou | 0 |
| Mesma classe predita (ambas válidas) | 1994 |
| Classes diferentes (ambas válidas) | 1 |
| Pelo menos uma SEM_PREDICAO | 5 |
| Ambas SEM_PREDICAO | 5 |
| Esquerda SEM_PREDICAO | 5 |
| Direita SEM_PREDICAO | 5 |
| Mesma categoria (inclui SEM_PREDICAO) | 1999 |
| Categorias diferentes (inclui SEM_PREDICAO) | 1 |
| Vetores quantizados completos idênticos | 1999 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 0 − 1 = -1.
Trocas de classe na tabela anterior: 1; recalculadas entre classes válidas: 1; mudanças incluindo SEM_PREDICAO: 1.

Concordância de classes válidas: 99,9499%; concordância de categorias: 99,9500%; igualdade dos vetores quantizados: 99,9500%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 965 | 1 | 0 |
| 1 | 0 | 1029 | 0 |
| SEM_PREDICAO | 0 | 0 | 5 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0373.raw | 0 | SEM_PREDICAO | SEM_PREDICAO | [128, 128] | [128, 128] | False | False |
| a0397.raw | 0 | 0 | 1 | [0, 255] | [254, 1] | True | False |
| a0409.raw | 0 | SEM_PREDICAO | SEM_PREDICAO | [128, 128] | [128, 128] | False | False |
| a0599.raw | 0 | SEM_PREDICAO | SEM_PREDICAO | [128, 128] | [128, 128] | False | False |
| a0819.raw | 0 | SEM_PREDICAO | SEM_PREDICAO | [128, 128] | [128, 128] | False | False |
| a0960.raw | 0 | SEM_PREDICAO | SEM_PREDICAO | [128, 128] | [128, 128] | False | False |

## TFLite desktop × TFLite ESP32

| Resultado | Quantidade |
| --- | ---: |
| Imagens | 2000 |
| Ambas acertaram | 1988 |
| Ambas não acertaram (inclui SEM_PREDICAO) | 8 |
| Ambas erraram com classes válidas | 7 |
| Esquerda acertou e direita não acertou | 2 |
| Direita acertou e esquerda não acertou | 2 |
| Mesma classe predita (ambas válidas) | 1995 |
| Classes diferentes (ambas válidas) | 2 |
| Pelo menos uma SEM_PREDICAO | 3 |
| Ambas SEM_PREDICAO | 0 |
| Esquerda SEM_PREDICAO | 2 |
| Direita SEM_PREDICAO | 1 |
| Mesma categoria (inclui SEM_PREDICAO) | 1995 |
| Categorias diferentes (inclui SEM_PREDICAO) | 5 |
| Vetores quantizados completos idênticos | 1878 |
| Pares com vetores completos comparáveis | 2000 |
| Rótulos ausentes ou conflitantes | 0 |

Diferença de acertos (direita − esquerda): 2 − 2 = 0.
Trocas de classe na tabela anterior: 2; recalculadas entre classes válidas: 2; mudanças incluindo SEM_PREDICAO: 5.

Concordância de classes válidas: 99,8998%; concordância de categorias: 99,7500%; igualdade dos vetores quantizados: 93,9000%.

### Matriz de concordância

Linhas = esquerda; colunas = direita.

| Predição | 0 | 1 | SEM_PREDICAO |
| --- | ---: | ---: | ---: |
| 0 | 988 | 1 | 1 |
| 1 | 1 | 1007 | 0 |
| SEM_PREDICAO | 1 | 1 | 0 |

### Imagens com categorias diferentes ou ausência de predição

| Imagem | Rótulo | Esquerda | Direita | Vetor esquerda | Vetor direita | Acertou esquerda | Acertou direita |
| --- | --- | --- | --- | --- | --- | --- | --- |
| a0391.raw | 0 | SEM_PREDICAO | 0 | [128, 128] | [98, 158] | False | True |
| a0397.raw | 0 | 1 | 0 | [255, 1] | [2, 254] | False | True |
| a0898.raw | 0 | 0 | 1 | [65, 191] | [151, 105] | True | False |
| a0967.raw | 0 | SEM_PREDICAO | 1 | [128, 128] | [179, 77] | False | False |
| a0968.raw | 0 | 0 | SEM_PREDICAO | [105, 151] | [128, 128] | True | False |

## Conclusão sobre a diferença no desktop

A diferença de 25 acertos corresponde a 27 imagens acertadas somente pelo TFLite menos 2 acertadas somente pelo WASM. Há 23 trocas entre classes válidas, 7 imagens com pelo menos uma ausência e 0 com ausência em ambas. Contando SEM_PREDICAO, há 30 mudanças de categoria.

Entre as trocas válidas, o TFLite acertou 22 e o WASM 1: saldo 21. Entre as imagens com ausência, o TFLite acertou 5 e o WASM 1: saldo 4. Logo, (22 − 1) + (5 − 1) = 25.

A tabela anterior pode manter as trocas entre classes válidas, desde que explicite o denominador e as ausências. Diferença líquida de acertos não é a mesma métrica que número de mudanças de classe. As imagens e matrizes acima permitem verificar ambas.
