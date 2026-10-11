# Resultados consolidados dos benchmarks

[English](README.md)

Abra **Análise consolidada** no menu lateral da web. **Gerar / atualizar tabela** refaz os arquivos salvos. A navegação, os filtros e a paginação somente leem esses dados. Nenhum modelo é executado.

Pelo terminal, na raiz: `python consolidate_reports.py`.

## MobileNetV2 Top-15 (tabela separada)

Abra a aba **MobileNetV2 · Top-15**. Seu botão refaz somente `mobilenet_top15.csv`; o botão do Drowsiness refaz somente `consolidated.csv`. O MobileNetV2 não entra na tabela do Drowsiness.

Colunas: `model;execution;score;q;name`, com nomes como `[404] airliner`. Cada execução possui 15 linhas na ordem original do ranking. Ambos os formatos utilizam os TXT: `reports/**/12-inferencia-wasm.txt` e `reports_tflite/**/inference-report.txt`. Cada relatório deve conter exatamente um Top-15 completo; rankings incompletos ou múltiplos interrompem a geração e preservam o arquivo anterior.

`mobilenet_executions.csv` associa os IDs a WASM/TFLite, pastas e arquivos de origem. Os IDs são estáveis dentro desta tabela e independentes dos IDs do Drowsiness. O seletor de execução da web também mostra o formato e a pasta. Os dados salvos ficam em `mobilenet_top15.json`. Pelo terminal: `python consolidate_mobilenet.py`.

## Arquivos

- `consolidated.csv`: uma linha por imagem/execução; UTF-8 com BOM, separado por ponto e vírgula, vetores JSON dentro das células.
- `executions.csv`: associação dos IDs de execução às pastas e arquivos de origem.
- `consolidated.json`: dados salvos e registro persistente dos IDs. Preserve esse arquivo para manter os IDs nas atualizações.
- `config.json`: associação host/modelo/formato do ESP32 e quantização alternativa. Atualize ao trocar o modelo embarcado. A quantização do metadata tem preferência; o uso da alternativa aparece nas observações das fontes.

No desktop, cada pasta representa uma execução distinta. No ESP32, a consolidação usa um novo relatório representativo por modelo/formato. As execuções originais permanecem em `raw_rows` e `raw_executions` no JSON para a análise de determinismo. Renomear uma pasta cria outra identidade.

## Relatórios representativos do ESP32

Abra **Análises → Relatórios representativos · ESP32** e clique em **Gerar / atualizar relatórios**. A geração também atualiza a análise consolidada. O botão de gerar a tabela consolidada e `python consolidate_reports.py` fazem a mesma seleção.

Para cada imagem, saídas iguais são mantidas e saídas diferentes são agrupadas pelo vetor completo (`quantized`, `scores`, índices e resultado). Cada execução fornece um voto. Escolhe-se a variante com maior frequência única; não é exigida maioria absoluta. Empates, conflitos de identidade e ausência de saída completa ficam sem predição utilizável. Falhas, imagens ignoradas e registros duplicados da mesma imagem/execução não votam. Uma única observação é mantida e identificada. A normalização do nome preserva maiúsculas e minúsculas.

Os novos CSVs ficam em `esp32_consensus/<modelo>/<wasm|tflite>/report.csv`. A linha e seus tempos são copiados da primeira execução que contém o vetor escolhido. `consensus_status`, `consensus_votes`, `consensus_observations` e `selected_execution` identificam a seleção na consolidação. `esp32_consensus/report.json` registra todas as variantes, votos, exclusões e fontes; `images.csv` resume a seleção. Hashes e configurações são conferidos quando registrados; nomes iguais sem hashes não comprovam igualdade dos bytes. Os relatórios originais não são alterados. A análise de determinismo continua usando todas as execuções originais.

## Interpretação

- ESP32: `A0001_pngxcr.raw` vira `A0001.raw`, preservando maiúsculas e minúsculas. Nomes do desktop, incluindo `aviao_uint8.raw`, permanecem iguais.
- No ESP32: `scores = (quantized - zero_point) * scale`. No desktop, os scores vêm do relatório.
- `output_indices` identifica as posições/classes dos vetores. No Drowsiness, as posições `[0,1]` correspondem aos labels `[1,0]`.
- O MobileNetV2 utiliza a tabela Top-15 separada descrita acima; classes ausentes não são necessariamente zero.
- `inference_ms=0` no desktop indica tempo não utilizado. Os tempos do ESP32 preservam o intervalo medido na origem, que pode variar entre os formatos.
- `invalid` e campos de recuperação ausentes ficam vazios. Vazio significa desconhecido, não falso.
- Linhas com falhas/imagens ignoradas permanecem, com vetores, resultado e acerto vazios. `prediction_usable=1` exclui falhas, imagens ignoradas e saídas explicitamente inválidas; não comprova validade quando `invalid` é desconhecido.

Fontes: `models/*/reports/**/12-inferencia-wasm.txt`, `models/*/reports_tflite/**/results-report.json` (alternativa TXT) e `ESP32/*/reports/**/report.csv` dos hosts configurados. Utiliza somente uma representação desktop por pasta. Relatórios vazios e nomes normalizados repetidos geram observações. Erros de leitura interrompem a atualização e preservam os arquivos existentes.
