# Distribuição das diferenças quantizadas

| Comparação | Δq=0 | Δq=1 | Δq=2–5 | Δq=6–10 | Δq>10 | Componentes comparáveis |
| --- | --- | --- | --- | --- | --- | --- |
| WASM ESP32 × TFLite ESP32 | 3487 | 141 | 130 | 6 | 236 | 4000 |
| WASM desktop × TFLite desktop | 3493 | 140 | 126 | 17 | 224 | 4000 |
| WASM ESP32 × TFLite desktop | 3492 | 139 | 126 | 17 | 226 | 4000 |
| WASM desktop × TFLite ESP32 | 3487 | 140 | 129 | 6 | 238 | 4000 |
| WASM ESP32 × WASM desktop | 3998 | 0 | 0 | 0 | 2 | 4000 |
| TFLite desktop × TFLite ESP32 | 3794 | 63 | 59 | 30 | 54 | 4000 |

Diferenças absolutas por componente quantizado, incluindo zeros. São dois componentes por imagem comparável no Drowsiness. Percentis usam interpolação linear. Contagens e percentual de Δq=0 usam o total de componentes comparáveis. Os números são derivados dos relatórios salvos; os vetores originais e valores sem arredondamento permanecem no JSON detalhado.
