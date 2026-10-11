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

### Comparação entre ambientes e formatos

As áreas **Estatísticas das diferenças quantizadas**, **Distribuição das diferenças quantizadas** e **Acertos por classe de referência** consultam os mesmos dados salvos e oferecem downloads CSV/Markdown: `quantized_stats.*`, `quantized_buckets.*` e `accuracy.*`. A primeira reúne máximo, média, mediana, P95/P99 e contagem/percentual de Δq=0; a segunda reúne as cinco faixas de Δq. Cada imagem comparável contribui com dois componentes, portanto cada comparação completa de 2.000 imagens possui N=4.000 diferenças. Arredondamento decimal usa metade para cima, como a interface; os valores sem arredondamento permanecem no JSON detalhado.

O relatório de acertos possui linhas Geral, classe 0 (non_drowsy) e classe 1 (drowsy) para cada uma das quatro fontes selecionadas. Acerto é `result == label`, recalculado dos rótulos de referência, contando cada fonte/imagem apenas uma vez apesar dos três pares em que aparece. O percentual principal é acertos / imagens com rótulo conhecido da classe; falhas, saídas inválidas e empates contam como ausência de acerto. A cobertura mostra também acertos / predições válidas, imagens sem rótulo conhecido e registros ausentes/duplicados, que ficam fora do denominador. Isso mede desempenho contra a referência, separadamente da concordância entre implementações. Não exige novas inferências. Gerar as comparações atualiza todos esses arquivos e inclui os acertos no JSON.

A área **Resumo de concordância** exibe as seis comparações com vetores diferentes/idênticos, concordância vetorial, trocas de classe e concordância de classe. Ela consulta os dados salvos, sem novas inferências ou regeneração das comparações. Os botões baixam `agreement.csv` (UTF-8 com BOM, separador `;`) e `agreement.md` (tabela pronta para copiar), com denominadores e IDs das execuções. Esses arquivos também são atualizados quando as comparações são geradas.

Concordância vetorial = vetores numericamente idênticos (quantized e scores) / vetores comparáveis, independentemente da decisão. Concordância de classe = classes idênticas / pares com vetores comparáveis e classes válidas nos dois lados. Saídas inválidas, empates e pares não comparáveis não contam nesse denominador. **Denominadores e cobertura** mostra as quantidades excluídas. Percentuais sem observações comparáveis ficam vazios (—), nunca 100%.

Abra **Análises → Comparação entre ambientes e formatos**. **Gerar / atualizar comparações** atualiza a consolidação, refaz os relatórios representativos do ESP32 e gera seis pares: WASM ESP32 × TFLite ESP32; WASM desktop × TFLite desktop; WASM ESP32 × TFLite desktop; WASM desktop × TFLite ESP32; WASM ESP32 × WASM desktop; TFLite desktop × TFLite ESP32. No desktop, a execução mais recente é o padrão; os seletores permitem escolher outra execução. Cada comparação usa somente a execução escolhida de cada lado, sem misturar execuções do desktop.

As imagens são pareadas pelo nome exato, preservando maiúsculas e minúsculas, e as saídas pelo índice. Cada imagem mostra scores e classe predita lado a lado, vetores quantizados, fontes, diferenças absolutas por componente, máximo, média, mediana, P95 e P99 tanto em quantized quanto em scores. As contagens `0`, `1`, `2–5`, `6–10` e `>10` referem-se às diferenças quantizadas. No Drowsiness, cada imagem comparável possui dois componentes; índice 0 corresponde à classe 1 (drowsy), e índice 1 à classe 0 (non_drowsy).

As estatísticas incluem zeros e os percentis usam interpolação linear. O resumo usa todos os componentes das imagens comparáveis, sem médias de médias. Uma imagem ausente, falha, seleção não resolvida, registro duplicado ou vetor incompleto é identificada como não comparável, com estatísticas vazias; não vira diferença zero. Saídas concluídas inválidas podem ser comparadas numericamente, mas não contam como troca entre classes válidas. A tela separa troca de classe e mudança de decisão. Igualdade exige valores e decisão iguais.

Os arquivos ficam em `analysis/comparisons/`: um CSV por par, `images.csv` com todas as imagens dos seis pares, `summary.csv` com o resumo e `report.json` com os detalhes e execuções escolhidas. Os CSVs têm UTF-8 com BOM e delimitador `;`. A navegação lê os arquivos salvos e avisa se a consolidação mudou. Pelo terminal: `python compare_environments.py`, que atualiza as fontes e usa as execuções mais recentes do desktop. A comparação é limitada aos valores registrados; igualdade de nomes não comprova igualdade dos bytes nem explica a causa das divergências.

- ESP32: `A0001_pngxcr.raw` vira `A0001.raw`, preservando maiúsculas e minúsculas. Nomes do desktop, incluindo `aviao_uint8.raw`, permanecem iguais.
- No ESP32: `scores = (quantized - zero_point) * scale`. No desktop, os scores vêm do relatório.
- `output_indices` identifica as posições/classes dos vetores. No Drowsiness, as posições `[0,1]` correspondem aos labels `[1,0]`.
- O MobileNetV2 utiliza a tabela Top-15 separada descrita acima; classes ausentes não são necessariamente zero.
- `inference_ms=0` no desktop indica tempo não utilizado. Os tempos do ESP32 preservam o intervalo medido na origem, que pode variar entre os formatos.
- `invalid` e campos de recuperação ausentes ficam vazios. Vazio significa desconhecido, não falso.
- Linhas com falhas/imagens ignoradas permanecem, com vetores, resultado e acerto vazios. `prediction_usable=1` exclui falhas, imagens ignoradas e saídas explicitamente inválidas; não comprova validade quando `invalid` é desconhecido.

Fontes: `models/*/reports/**/12-inferencia-wasm.txt`, `models/*/reports_tflite/**/results-report.json` (alternativa TXT) e `ESP32/*/reports/**/report.csv` dos hosts configurados. Utiliza somente uma representação desktop por pasta. Relatórios vazios e nomes normalizados repetidos geram observações. Erros de leitura interrompem a atualização e preservam os arquivos existentes.
