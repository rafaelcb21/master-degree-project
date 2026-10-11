# Estatísticas das diferenças quantizadas

| Comparação | Máx. Δq | Média Δq | Mediana | P95 | P99 | Δq = 0 | Δq = 0 (%) | Componentes comparáveis |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| WASM ESP32 × TFLite ESP32 | 243 | 4,014 | 0 | 12 | 128,26 | 3487 | 87,18% | 4000 |
| WASM desktop × TFLite desktop | 247 | 3,936 | 0 | 12 | 150,01 | 3493 | 87,33% | 4000 |
| WASM ESP32 × TFLite desktop | 255 | 4,063 | 0 | 12 | 152,23 | 3492 | 87,30% | 4000 |
| WASM desktop × TFLite ESP32 | 253 | 4,140 | 0 | 12 | 155,03 | 3487 | 87,18% | 4000 |
| WASM ESP32 × WASM desktop | 254 | 0,127 | 0 | 0 | 0 | 3998 | 99,95% | 4000 |
| TFLite desktop × TFLite ESP32 | 253 | 0,772 | 0 | 1 | 22,01 | 3794 | 94,85% | 4000 |

Diferenças absolutas por componente quantizado, incluindo zeros. São dois componentes por imagem comparável no Drowsiness. Percentis usam interpolação linear. Contagens e percentual de Δq=0 usam o total de componentes comparáveis. Os números são derivados dos relatórios salvos; os vetores originais e valores sem arredondamento permanecem no JSON detalhado.
