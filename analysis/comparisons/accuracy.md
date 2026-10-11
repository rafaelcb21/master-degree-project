# Acertos por classe de referência

| Ambiente e formato | Classe de referência | Imagens rotuladas | Acertos | Erros com classe válida | Sem predição válida | Acertos (%) | Predições válidas | Acertos entre predições válidas (%) | Sem rótulo conhecido | Registros ausentes/duplicados | Execução |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WASM ESP32 | Geral | 2000 | 1966 | 29 | 5 | 98,30% | 1995 | 98,55% | 0 | 0 | 51 |
| WASM ESP32 | 0 (non_drowsy) | 1000 | 966 | 29 | 5 | 96,60% | 995 | 97,09% | 0 | 0 | 51 |
| WASM ESP32 | 1 (drowsy) | 1000 | 1000 | 0 | 0 | 100,00% | 1000 | 100,00% | 0 | 0 | 51 |
| TFLite ESP32 | Geral | 2000 | 1990 | 9 | 1 | 99,50% | 1999 | 99,55% | 0 | 0 | 50 |
| TFLite ESP32 | 0 (non_drowsy) | 1000 | 990 | 9 | 1 | 99,00% | 999 | 99,10% | 0 | 0 | 50 |
| TFLite ESP32 | 1 (drowsy) | 1000 | 1000 | 0 | 0 | 100,00% | 1000 | 100,00% | 0 | 0 | 50 |
| WASM desktop | Geral | 2000 | 1965 | 30 | 5 | 98,25% | 1995 | 98,50% | 0 | 0 | 9 |
| WASM desktop | 0 (non_drowsy) | 1000 | 965 | 30 | 5 | 96,50% | 995 | 96,98% | 0 | 0 | 9 |
| WASM desktop | 1 (drowsy) | 1000 | 1000 | 0 | 0 | 100,00% | 1000 | 100,00% | 0 | 0 | 9 |
| TFLite desktop | Geral | 2000 | 1990 | 8 | 2 | 99,50% | 1998 | 99,60% | 0 | 0 | 12 |
| TFLite desktop | 0 (non_drowsy) | 1000 | 990 | 8 | 2 | 99,00% | 998 | 99,20% | 0 | 0 | 12 |
| TFLite desktop | 1 (drowsy) | 1000 | 1000 | 0 | 0 | 100,00% | 1000 | 100,00% | 0 | 0 | 12 |

Acerto = classe predita igual ao rótulo de referência registrado. Cada fonte/imagem é contada uma única vez, mesmo aparecendo em três comparações. O percentual principal é acertos / todas as imagens com rótulo conhecido da classe (ou de ambas as classes em Geral); falhas, empates e saídas inválidas não contam como acerto. O percentual complementar usa apenas predições válidas. Sem rótulo conhecido e registros ausentes/duplicados ficam identificados e fora do denominador. As classes são 0 = non_drowsy e 1 = drowsy. Usa as execuções já escolhidas nas comparações; não calcula concordância entre implementações.
