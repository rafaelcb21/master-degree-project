# Resumo de concordância

Gerado em: 11/10/2026 11:22:51 (UTC−03:00)

| Comparação | Vetores diferentes | Vetores idênticos | Concordância vetorial | Trocas de classe | Concordância de classe |
| --- | --- | --- | --- | --- | --- |
| WASM ESP32 × TFLite ESP32 | 266 | 1734 | 86,70% | 23 | 98,85% |
| WASM desktop × TFLite desktop | 263 | 1737 | 86,85% | 23 | 98,85% |
| WASM ESP32 × TFLite desktop | 263 | 1737 | 86,85% | 24 | 98,80% |
| WASM desktop × TFLite ESP32 | 266 | 1734 | 86,70% | 24 | 98,80% |
| WASM ESP32 × WASM desktop | 1 | 1999 | 99,95% | 1 | 99,95% |
| TFLite desktop × TFLite ESP32 | 122 | 1878 | 93,90% | 2 | 99,90% |

Concordância vetorial = vetores numericamente idênticos / vetores comparáveis. Compara quantized e scores, independentemente da decisão registrada.
Concordância de classe = classes idênticas / pares com vetores comparáveis e classes válidas nos dois lados. Saídas inválidas, empates e pares não comparáveis são excluídos desse denominador.

## Cobertura e fontes

| Comparação | Vetores comparáveis | Classes comparáveis | Classes não comparáveis | Execução esquerda | Execução direita |
| --- | --- | --- | --- | --- | --- |
| WASM ESP32 × TFLite ESP32 | 2000 | 1994 | 6 | 51 | 50 |
| WASM desktop × TFLite desktop | 2000 | 1993 | 7 | 9 | 12 |
| WASM ESP32 × TFLite desktop | 2000 | 1993 | 7 | 51 | 12 |
| WASM desktop × TFLite ESP32 | 2000 | 1994 | 6 | 9 | 50 |
| WASM ESP32 × WASM desktop | 2000 | 1995 | 5 | 51 | 9 |
| TFLite desktop × TFLite ESP32 | 2000 | 1997 | 3 | 12 | 50 |
