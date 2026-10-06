# 15 — Executar os modelos TFLite originais

[English](15-tflite-baseline.md) | [Português (Brasil)](15-referencia-tflite.pt-BR.md)

`run_tflite.py` executa os arquivos `.tflite` originais e grava relatórios separados para comparar depois com o WASM. Usa os mesmos manifestos, imagens de teste, ordem das classes e adaptadores de avaliação. Não regenera o WASM nem sobrescreve `models/<modelo>/reports/`.

## Instalar e executar

Use um ambiente separado com Python 3.11. Na raiz do repositório, em PowerShell:

```powershell
python -m venv .venv-tflite
.\.venv-tflite\Scripts\python.exe -m pip install -r requirements-tflite.txt
.\.venv-tflite\Scripts\python.exe run_tflite.py
```

Por padrão, executa os dois pacotes cadastrados. Para escolher apenas um:

```powershell
.\.venv-tflite\Scripts\python.exe run_tflite.py --model drowsiness
.\.venv-tflite\Scripts\python.exe run_tflite.py --model mobilenetv2_alpha035
```

O runner usa `tf.lite.Interpreter` do TensorFlow 2.20.0, uma thread de CPU por padrão e kernels internos sem os delegates padrão. `--threads N` altera a quantidade de threads. O interpretador aloca os tensores, recebe a entrada, executa `invoke()` e devolve a saída. Consulte a [API oficial do interpretador](https://www.tensorflow.org/api_docs/python/tf/lite/Interpreter). O TensorFlow pode emitir um aviso de descontinuação dessa API; a dependência está fixada na versão utilizada aqui.

## Correspondência das entradas

| Pacote | Preparação da entrada |
|---|---|
| Drowsiness | Lê RGB565 little-endian e expande para RGB888 com a mesma replicação de bits do conversor WAT. Entrega RGB uint8 à entrada original do TFLite; o operador QUANTIZE do próprio modelo continua sendo executado. |
| MobileNetV2 Alpha 0.35 | Reutiliza a preparação BGR888→RGB888 do adaptador WASM, incluindo sua normalização e quantização se o tensor de entrada for int8. |

Não há redimensionamento nem geração de novas imagens. O runner exige uma entrada RGB NHWC com batch 1 e tensores de entrada/saída quantizados uint8/int8. Formatos, tipos e quantizações incompatíveis são rejeitados, sem presumir outro pré-processamento.

## Arquivos gerados

Cada execução cria uma pasta com data e hora UTC:

```text
models/<modelo>/reports_tflite/<data e hora UTC>/
  inference-report.txt
  samples-report.csv
  results-report.json
```

- **TXT:** a mesma estrutura legível de classificação binária ou Top-K do relatório WASM, identificada como TFLite.
- **CSV:** uma linha por imagem, sucesso/falha, predição, rótulo/acerto quando disponíveis, tempo de inferência, saídas quantizadas e scores. Falhas têm `ok=0` e descrição do erro. ImageNet não possui rótulos de referência nesse teste; os campos de acurácia ficam vazios.
- **JSON:** vetores completos de saída, Top-K quando aplicável, registros e erros por imagem, hashes do modelo/manifesto, hashes do RAW e da entrada preparada, shapes e quantização dos tensores, versões do runtime, horários e métricas resumidas.

Os caminhos são relativos ao pacote do modelo, como `test/drowsy/A0001.raw`. Execuções anteriores ficam preservadas. Quando uma amostra falha, os relatórios ainda são gravados e a CLI retorna um código de erro. Falhas de inicialização/configuração interrompem a execução antes da geração de relatórios.

No Research Explorer, clique em **Atualizar índice** e filtre pelo modelo. Os arquivos aparecem em `reports_tflite/`; TXT e CSV usam as visualizações existentes, enquanto o JSON aparece como texto original.

## Comparação posterior com WASM

Use `models/<modelo>/reports/12-inferencia-wasm.txt` como resultado WASM existente e o novo relatório TFLite como referência. Relacione as imagens pelo caminho relativo ao pacote, sem depender da posição da linha ou do prefixo absoluto da máquina nos relatórios WASM antigos. Compare saídas quantizadas, scores desquantizados, classes previstas, empates e erros. O JSON ImageNet mantém todas as 1.000 saídas; o TXT mostra Top-15.

O mesmo pré-processamento não garante saídas idênticas: implementações de kernels e arredondamentos inteiros podem diferir. Os relatórios WASM existentes não registram hashes do modelo e das entradas; sua origem precisa ser verificada antes de uma comparação numérica formal. Este comando não valida nem reexecuta esses relatórios anteriores.

Os tempos medem apenas `interpreter.invoke()`, excluindo leitura de arquivos, preparação e cópia dos tensores. Não há execução de aquecimento, e a primeira inferência entra na média. Esses tempos de CPU não equivalem diretamente às medições do ESP32 ou a execuções WASM com outro critério de medição. A acurácia binária considera amostras com rótulo processadas com sucesso; empates contam como erro de classificação, e falhas de processamento são informadas separadamente.
