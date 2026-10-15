# Parecer 7(a) — inclusão do TensorFlow Lite Micro nas Tabelas 5.2 e 5.3

[English](report.md) | [Português (Brasil)](relatorio.pt-BR.md)

**Data:** 15/10/2026. **Finalidade:** fornecer dados verificados e alterações prontas para transferir ao projeto da dissertação. Nenhuma inferência foi executada e o arquivo original da dissertação não foi alterado.

## 1. Conclusão e alteração recomendada

O experimento com **TensorFlow Lite Micro (TFLM), ESP-NN habilitado, ESP32-CAM a 240 MHz** já possui duas coletas completas de 2.000 imagens, com CSV e metadata. É possível apresentar o tempo exato e a acurácia **da mesma coleta**, sem novos experimentos para obter esses números.

Recomenda-se usar a coleta **`20261009T120557541292Z`** como fonte única da linha TFLM nas duas tabelas. É a coleta completa mais recente entre as duas examinadas; a escolha não foi feita pelo menor tempo entre amostras ou por maior acurácia. As coletas posteriores de quatro imagens não substituem a avaliação de 2.000 imagens.

| Tabela | Alteração |
|---|---|
| **5.2**, `tab:tempos-inferencia-aceleracao` | Substituir a linha aproximada TFLM por média **1,777 s**, mínimo **1,761 s**, máximo **1,793 s** e aceleração descritiva **81,06×** conforme a referência da própria tabela. |
| **5.3**, `tab:acuracia-configuracoes` | Identificar a linha como **TFLM + ESP-NN, ESP32-CAM, 240 MHz**, mantendo **1.990 acertos, 9 erros, 1 sem predição válida, 99,50%**; atribuir esses números à mesma coleta usada na Tabela 5.2. |

**Estado da versão consultada:** a linha TFLM já existe na Tabela 5.2, com `≈ 1,7 s` e campos mínimo, máximo e aceleração vazios. Portanto, basta substituí-la, sem adicionar uma segunda linha TFLM. A Tabela 5.3 já possui os números acima sob o nome genérico `TFLite ESP32-CAM`; é necessário tornar explícito o runtime e documentar a fonte. Os números de tabela foram conferidos no `.aux`; os rótulos LaTeX são a referência mais estável se a numeração mudar.

## 2. Fonte escolhida e identidade do modelo

No repositório de origem:

```text
ESP32/cnn_tflite_esp32/reports/20261009T120557541292Z/report.csv
ESP32/cnn_tflite_esp32/reports/20261009T120557541292Z/metadata.json
```

Cópias incluídas neste pacote: [CSV](fontes/20261009T120557541292Z/report.csv) e [metadata](fontes/20261009T120557541292Z/metadata.json).

| Configuração | Evidência registrada |
|---|---|
| Runtime | `TensorFlow Lite Micro` |
| Componente TFLM | `1.3.5` |
| Kernels | `ESP-NN enabled` |
| CPU | `240 MHz` |
| ESP-IDF | `v5.3.1-dirty` |
| Entrada | 128 × 128; duas classes; formato 1, correspondente a RGB565 little-endian no host |
| Saída | `uint8`, escala `0.00390625`, zero-point `0` |
| Arena reservada / utilizada | 1.048.576 / 312.380 bytes |
| Warm-up | `0` execuções declaradas |
| Processadas / sucesso / falha | 2.000 / 2.000 / 0 |
| Resultados restaurados | `resumed=0` |
| Classes de referência | 1.000 imagens de cada classe |

O SHA-256 informado no metadata coincide com o calculado sobre `models/drowsiness/model_int8_esp32.tflite` no repositório atual:

```text
b4521f926f0133355f970f237ca2c372af36dcae5265766a5f42f717954f02b0
```

SHA-256 do CSV selecionado:

```text
315281d10ac4cb369bead77faef47d4ff788ab85c1a4416e59275ebda4afbeae
```

SHA-256 do metadata selecionado:

```text
1ec223db5d33be36f64f1ced05734d1d40aaf900efd5c87f7b1c62ede0687aa0
```

As versões e a configuração acima são as registradas no metadata da coleta. Não se atribuem retroativamente a ela novas configurações do firmware. `ESP-NN enabled` indica a configuração declarada, sem demonstrar que todos os operadores usam kernels otimizados.

## 3. Valores calculados a partir do CSV

As estatísticas de tempo usam as 2.000 linhas bem-sucedidas da coleta selecionada. A acurácia usa todas as 2.000 imagens, incluindo a ocorrência sem decisão válida.

| Medida | Valor derivado dos dados gravados | Apresentação sugerida |
|---|---:|---:|
| Tempo médio de inferência | **1.776,7145665 ms = 1,7767145665 s** | **1,777 s** |
| Tempo mínimo | **1.760,819 ms = 1,760819 s** | **1,761 s** |
| Tempo máximo | **1.792,774 ms = 1,792774 s** | **1,793 s** |
| Pré-processamento médio | 11,7326165 ms | 11,733 ms |
| `Invoke` médio | 1.764,98195 ms | 1.764,982 ms |
| Acertos | **1.990** | **1.990** |
| Predições válidas incorretas | **9** | **9** |
| Sem predição válida | **1**, por empate | **1** |
| Falhas de processamento | **0** | **0** |
| Acurácia | **1.990 / 2.000 × 100 = 99,50%** | **99,50%** |

O empate não constitui falha de processamento: a inferência foi concluída, mas não produziu uma classe única. Por isso, os 2.000 tempos são utilizados e a ocorrência entra no denominador da acurácia como não correta. Não somar novamente o empate aos nove erros da coluna de predições válidas incorretas.

Os valores extensos são resultados aritméticos sobre tempos gravados com três casas decimais em milissegundos; não representam resolução adicional do instrumento.

## 4. Intervalo de medição e comparação com WASM

O metadata define `inference_ms_scope` como **`prepare_input + Invoke; download, checkpoint and output reading excluded`**. Portanto, o tempo inclui o preparo da entrada, incluindo RGB565 → RGB888 no host, e a execução TFLM. Exclui download, persistência dos checkpoints e leitura da saída.

Conforme o host, o intervalo é medido com `esp_timer_get_time()` imediatamente antes de `model_prepare_input(...)` e após `model_invoke()`. A especificação histórica do intervalo está preservada no metadata; o código atual permite conferir a implementação, sem substituir o registro da coleta.

O valor a incluir na comparação é **`inference_ms`**, não somente `invoke_ms`. Usar apenas `Invoke` retiraria do TFLM o pré-processamento incluído na chamada de inferência WASM. A comparação integral continua sendo entre implementações com fronteiras e estruturas diferentes; incluir o mesmo tipo de etapa não elimina todos os fatores de confusão.

Usando os **6,195 s do WASM AOT a 240 MHz já apresentados na dissertação**:

```text
6,195 / 1,7767145665 = 3,4867727866 ≈ 3,49
```

Assim, a latência média WASM AOT apresentada na dissertação é aproximadamente **3,49 vezes** a latência média TFLM desta coleta. O valor WASM não foi recalculado neste relatório: trata-se de uma comparação contextual com a tabela existente, não de uma nova medição pareada ou demonstração de identidade do firmware das duas coletas.

Na coluna de aceleração da Tabela 5.2, cuja referência é a interpretação WAMR a 160 MHz:

```text
144,019 / 1,7767145665 = 81,0591654481 ≈ 81,06×
```

Essa razão é descritiva e envolve também diferença de frequência e de tamanho da amostra: a referência interpretada tem seis imagens, enquanto o TFLM tem 2.000. Se o texto reservar a aceleração estritamente às estratégias WAMR, pode manter `---` nessa célula e informar **3,49×** no parágrafo comparativo. Nesse caso, explicar que a célula foi omitida por delimitação da comparação, e não por ausência de tempos TFLM.

**Interpretação:** a diferença mede o desempenho relativo de **WAMR AOT com operadores implementados em WAT** e **TFLM com ESP-NN habilitado**. Não isola um custo exclusivo de portabilidade: kernels, otimizações, organização de memória e runtimes diferem. Evitar as expressões “sobrecusto exclusivo do WebAssembly” e “custo puro da portabilidade”.

## 5. Verificação da condição “mesma coleta”

As duas coletas completas examinadas produziram:

| Coleta | Imagens | Média (s) | Mínimo (s) | Máximo (s) | Acertos / válidas incorretas / sem classe |
|---|---:|---:|---:|---:|---:|
| `20261008T215503505222Z` | 2.000 | 1,7797058455 | 1,759206 | 1,791081 | 1.990 / 9 / 1 |
| **`20261009T120557541292Z` — selecionada** | **2.000** | **1,7767145665** | **1,760819** | **1,792774** | **1.990 / 9 / 1** |

As duas têm o mesmo hash do modelo e da lista de imagens. O pareamento dos CSVs confirmou **2.000 nomes, rótulos e hashes das entradas iguais**, além das mesmas decisões de classe nas 2.000 imagens. Os vetores de saída são iguais em 1.996 imagens; há diferenças numéricas em quatro imagens, sem mudança da decisão.

O [relatório representativo de acurácia](fontes/acuracia-representativa.csv) atualmente salvo combina **1.999 registros da primeira coleta e um da segunda**. Ele não deve ser tratado como um benchmark temporal único. Suas 2.000 decisões coincidem com as da coleta selecionada, e ele também apresenta 1.990 acertos e um empate.

**Solução:** atribuir explicitamente as duas linhas TFLM das Tabelas 5.2 e 5.3 ao CSV bruto `20261009T120557541292Z`. Os números de acurácia permanecem iguais aos já apresentados, agora com origem na mesma coleta dos tempos. Não substituir automaticamente os vetores dos estudos de fidelidade por esse CSV: essa análise utiliza fontes e regras próprias.

## 6. Texto sugerido para a dissertação

> Como referência embarcada, o mesmo modelo de sonolência foi executado no ESP32-CAM a 240 MHz com TensorFlow Lite Micro, componente versão 1.3.5, e ESP-NN habilitado. Na coleta identificada por `20261009T120557541292Z`, foram processadas 2.000 imagens, com tempo médio de 1,776715 s, mínimo de 1,760819 s e máximo de 1,792774 s. O intervalo compreende a preparação da entrada e a execução de `Invoke`, excluindo download, gravação de checkpoints e leitura da saída. Não houve aquecimento explícito, conforme o metadata da coleta. Foram obtidos 1.990 acertos, nove predições válidas incorretas e um empate, correspondendo a 99,50% de acurácia sobre as 2.000 imagens. Os tempos e a acurácia apresentados para TFLM nas Tabelas 5.2 e 5.3 foram calculados a partir dessa mesma coleta.

> Comparado ao tempo médio de 6,195 s do WASM AOT a 240 MHz apresentado na Tabela 5.2, o TFLM apresentou latência média aproximadamente 3,49 vezes menor. Essa razão caracteriza o desempenho relativo das implementações avaliadas e não um custo exclusivo da portabilidade, pois diferem os kernels, as otimizações e a organização da execução. A comparação entre interpretação e AOT do WAMR a 160 MHz permanece a avaliação específica do efeito da estratégia de execução WebAssembly no mesmo hardware e frequência.

**Texto sugerido para responder ao parecer:**

> A recomendação foi atendida com a inclusão dos resultados detalhados da referência TensorFlow Lite Micro com ESP-NN no ESP32-CAM a 240 MHz. A Tabela 5.2 passou a apresentar média, mínimo e máximo calculados sobre 2.000 imagens, e a Tabela 5.3 identifica explicitamente esse runtime. As duas linhas utilizam a mesma coleta, com 1.990 acertos e 99,50% de acurácia. A discussão esclarece que a razão de latências mede o desempenho relativo das implementações, sem isolar o custo exclusivo da portabilidade.

Usar a resposta no passado **após aplicar as alterações** ao projeto da dissertação. Neste trabalho foi preparado o relatório e os trechos, sem editar o `.tex` externo.

## 7. Arquivos para transferir e instrução ao outro projeto

- [alteracoes-sugeridas.tex](alteracoes-sugeridas.tex): linhas e textos LaTeX prontos para integração; não é um documento compilável isoladamente.
- [evidencias-report.json](evidencias-report.json): estatísticas, metadata, hashes e reconciliação.
- [coletas.csv](coletas.csv): resumo comparativo das duas coletas.
- `fontes/`: CSVs e metadata preservados, relatório representativo e cópia das três tabelas consultadas.
- [analyze.py](analyze.py): cálculo reproduzível no repositório de origem, sem executar modelos.
- [verificar_pacote.py](verificar_pacote.py): verifica as cópias e os cálculos após extrair o pacote, sem depender do repositório original.

**Instrução para o projeto da dissertação:** “Aplicar o item 7(a) usando este relatório. Substituir a linha aproximada da Tabela `tab:tempos-inferencia-aceleracao`, explicitar TFLM + ESP-NN na Tabela `tab:acuracia-configuracoes` e vincular as duas linhas à coleta `20261009T120557541292Z`. Atualizar a nota que afirma indisponibilidade de mínimo e máximo. Não alterar os números ou fontes das outras configurações nem recomputar fidelidade a partir desta coleta sem uma análise separada.”

O documento examinado foi `C:/Users/rafae/Downloads/latex-mestrado-2/Dissertacao_Rafael_Braga_UNICO.tex`. Seu hash no momento da auditoria está no JSON de evidências. Os números deste relatório foram derivados dos arquivos preservados; não foram estimados a partir de “≈ 1,7 s”.
