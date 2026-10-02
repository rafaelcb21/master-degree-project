[English](26-extractor-weights.md) | [Português (Brasil)](26-extractor-weights.pt-BR.md)

# 26 — Extração de pesos e bias

[Índice](README.pt-BR.md) · Fonte: [extractor/weights.py](../extractor/weights.py)

## Responsabilidade

`extract_weights_and_bias(model,subgraph)` identifica constantes das operações em `WEIGHT_OPERATORS`: CONV_2D, DEPTHWISE_CONV_2D e FULLY_CONNECTED. É chamado depois do mapa lógico e antes da quantização. Não dequantiza, transpõe kernels ou dobra batch normalization. Preserva a ordem dos bytes extraídos pelo helper.

## Algoritmo e estruturas

Percorre operadores na ordem TFLite e filtra IDs negativos. Se houver pelo menos duas entradas, a segunda é considerada peso. `safe_bytes_from_tensor` devolve tensor/array/raw; se houver array e o ID ainda não foi extraído, registra o offset atual, concatena raw e adiciona metadados. Se houver terceira entrada, ela é candidata a bias; só é extraída quando o array existe, tem uma dimensão e ainda não foi registrado. IDs compartilhados são deduplicados separadamente nos mapas de pesos e bias.

Retorna seis campos: `weights_raw` e `bias_raw` como bytes; `weight_tensor_off` e `bias_tensor_off` como dicts ID→offset; `weight_records` e `bias_records` com op_index, op_type, tensor_id, offset, nbytes, shape e dtype. O offset é relativo ao início do respectivo blob, não ao arquivo TFLite nem à memória WASM.

```text
op inputs: [ativação, peso, bias opcional]
                          │       │
                          ▼       ▼
                 safe_bytes_from_tensor
                          │       │
                    dedup por tensor_id
                          │       │
                          ▼       ▼
                  weights_raw   bias_raw
                          │       │
                  offset relativo por tensor
                          └───┬───┘
                              ▼
                   memory → LayerParams → blob
```

Entram constantes do modelo. O extrator concatena e registra sua localização. Saem bytes e offsets, consumidos pelo layout físico e pelos builders de camadas. Pesos e shapes são específicos; as regras de armazenamento compartilhadas exigem que o WAT interprete o layout TFLite preservado.

## Layouts esperados pelo runtime

CONV usa pesos indexados como `[cout,kh,kw,cin]`; depthwise como `[1,kh,kw,cout]`; FC usa matriz `[cout,cin]`. O módulo não valida todas essas dimensões antes de copiar. Bias deve ser int32 para os kernels que fazem `i32.load`, mas este extrator não restringe o dtype do bias; apenas verifica dimensionalidade. O suporte declarado a um operador depende também dos builders e kernels.

## Falhas e comportamento permissivo

Tensor ilegível/sem buffer/dtype desconhecido pode ser pulado pelo helper sem exceção. Menos entradas também é motivo de skip. Os offsets faltantes são usados com defaults em builders posteriores; isso pode ocultar dados obrigatórios ausentes. Não há alinhamento entre cada tensor deste blob; o alinhamento é aplicado às bases de regiões em `memory.py`. Tamanhos típicos mantêm offsets int32 de bias alinhados, mas não há checagem de alinhamento por registro.

`weights_bias_to_text` lista registros de pesos e bias, seguidos de número de tensores e total de bytes. Recebe o dict de extração e retorna string para 05. Não inclui os valores completos dos pesos nem reconstitui os arrays. Use os offsets e os comprimentos para localizar o trecho no data segment.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from extractor.tflite_utils import op_name, safe_bytes_from_tensor
```

### `extract_weights_and_bias` — assinatura

```python
def extract_weights_and_bias(model, subgraph)
```

### `weights_bias_to_text` — assinatura

```python
def weights_bias_to_text(extraction)
```

## Material técnico preservado

A explicação anterior está em [07-extracao-pesos-bias.md](historico/07-extracao-pesos-bias.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
