# 22 — Utilitários de tensores e quantização TFLite

[Índice](README.md) · Fonte: [extractor/tflite_utils.py](../extractor/tflite_utils.py)

## Responsabilidade e estruturas

Este módulo normaliza consultas repetidas ao schema. É usado pelo grafo, pesos, quantização, memória, LayerParams e `tensor_info`. Não decide diretórios ou classes. `TENSOR_TYPE_MAP` relaciona códigos TFLite a nome/NumPy dtype; `BYTES_PER_TYPE` informa o armazenamento. A existência de um dtype nessa tabela não significa que os kernels o executem.

| Código | Nome | Bytes |
|---:|---|---:|
| 0 | float32 | 4 |
| 1 | float16 | 2 |
| 2 | int32 | 4 |
| 3 | uint8 | 1 |
| 4 | int64 | 8 |
| 6 | bool | 1 |
| 7 | int16 | 2 |
| 9 | int8 | 1 |

## Funções, decisões e retornos

`op_name(model,op)` consulta `OperatorCodes(op.OpcodeIndex()).BuiltinCode()` e procura o valor no `__dict__` de `tflite.BuiltinOperator`. Retorna o nome encontrado ou `CUSTOM`. Não interpreta `CustomCode` nem o versionamento do operador; dois operadores com o mesmo builtin e versões diferentes têm o mesmo nome aqui.

`is_constant_tensor(model,subgraph,tensor_id)` considera constante um tensor cujo buffer `DataAsNumpy()` tem comprimento maior que zero. Captura apenas `AttributeError` desse acesso e retorna False. Não consulta o atributo variable nem analisa escrita por operadores; é uma definição por presença de bytes, usada por alocação e mapeamento.

`safe_bytes_from_tensor` obtém tensor/buffer e retorna `(tensor,array,raw)`. Ausência de dados, buffer vazio ou dtype desconhecido produz `(None,None,None)`. Converte com `np.frombuffer`, tenta reshape para o shape TFLite e ignora qualquer exceção do reshape, mantendo o vetor original. Por fim, achata e retorna bytes. Logo, o nome “safe” não significa validação completa de tamanho/shape; chamadas inválidas ao schema e `frombuffer` ainda podem falhar.

`scale_scalar(tensor)` retorna o primeiro scale como float; sem quantização/scales, retorna 1. `zp_scalar` retorna o primeiro zero point como int, ou 0. Esses defaults evitam algumas ausências, mas podem mascarar dados insuficientes. Não calculam médias nem escolhem valores por canal.

`tensor_shape_list` converte `ShapeAsNumpy()` em lista de ints, ou `[]` se for None. Não resolve shape signature, valida dimensões nem materializa batch.

`qparams_np` retorna `{scales: float64 array, zps: int64 array, qdim}` com arrays pelo menos unidimensionais. Sem quantização/scales, retorna None. Preserva múltiplas escalas para o extrator por canal. O binding pode representar ausência de array de formas diferentes; os helpers pressupõem as formas tratadas explicitamente no código.

```text
tensor_id
   │
   ├──► Tensors(id) ──► Type / Shape / Quantization
   │                        │             │
   │                        ▼             ├── scalar: primeiro valor
   │                   dtype/shape        └── qparams_np: arrays
   ▼
Buffers(tensor.Buffer())
   │ dados não vazios?
   ├── não ──► não constante / sem bytes extraíveis
   └── sim ──► NumPy → reshape tentado → raw
```

Entram IDs ou objetos do modelo. Os helpers extraem representações simples; saem nomes, arrays, escalares e bytes. Shapes/scales são específicos; convenções de dtype são compartilhadas. Os consumidores precisam distinguir None de dados válidos, pois ausência não é sempre exceção.

## Endianness e limites

Os dtypes NumPy básicos no mapa são nativos. Os bytes dos buffers vêm do TFLite; em um host little-endian como o ambiente observado, os tipos multibyte correspondem ao armazenamento esperado. O módulo não normaliza explicitamente todos os buffers para little-endian. Já os blobs de MUL/SHIFT/Q6 e LayerParam usam formatos little-endian explícitos em seus módulos. Não extrapole portabilidade para hosts big-endian sem verificar essa diferença.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
import tflite
import numpy as np
```

### `op_name` — assinatura

```python
def op_name(model, op)
```

### `is_constant_tensor` — assinatura

```python
def is_constant_tensor(model, subgraph, tensor_id)
```

### `safe_bytes_from_tensor` — assinatura

```python
def safe_bytes_from_tensor(model, subgraph, tensor_id)
```

### `scale_scalar` — assinatura

```python
def scale_scalar(tensor)
```

### `zp_scalar` — assinatura

```python
def zp_scalar(tensor)
```

### `tensor_shape_list` — assinatura

```python
def tensor_shape_list(tensor)
```

### `qparams_np` — assinatura

```python
def qparams_np(tensor)
```

## Material técnico preservado

A explicação anterior está em [03-utilitarios-tflite.md](historico/03-utilitarios-tflite.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.md).
