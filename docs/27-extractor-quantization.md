# 27 — Quantização inteira e blobs por canal

[Índice](README.md) · Fonte: [extractor/quantization.py](../extractor/quantization.py)

## Conceitos e representação

Um valor quantizado q representa `real = (q - zero_point) × scale`. Para acumuladores de convolução, a razão desejada por canal é `M[c] = input_scale × weight_scale[c] / output_scale`. O módulo produz multiplicadores inteiros, shifts e limites de RELU6 para que o WAT opere sem escalas float na interface.

## quantize_multiplier

Recebe um número real convertido a float. Para zero retorna `(0,0)`. Usa `math.frexp` para decompor `M = q × 2^exponent`, arredonda `q × 2^31` com `round` de Python e corrige o caso igual a 2^31 dividindo por 2 e incrementando expoente. Limita o inteiro a `[INT32_MIN,INT32_MAX]`. Retorna `(q31,exponent)`.

Exemplo: M=0,25 produz q=0,5 e exponent=−1; q31=1073741824. A reconstrução é `(1073741824/2^31)×2^-1=0,25`. M=1 produz o mesmo q31 com shift=1. Shift positivo significa amplificação por potência de dois; negativo significa redução. A forma de arredondar e saturar a multiplicação é implementada no WAT e não é completamente determinada por esse par.

Não há validação prévia de finitude ou positividade de M. NaN/inf e escalas inválidas podem causar exceções ou resultados sem significado; não se trata de um schema de quantização completo.

## extract_quantization_parameters: operadores com pesos

Percorre os operadores originais. Em CONV e FC, `nfeat` vem de `weight_shape[0]`; em depthwise, de `[3]`. Operador sem entradas/saída suficientes, shape insuficiente ou qparams ausentes é pulado. Usa o primeiro scale de entrada/saída e o primeiro zero point de saída; preserva o array de scales dos pesos.

Com uma scale de peso, replica o mesmo M por todos os canais. Com várias, usa até `min(nfeat,quantidade)` e, se faltarem escalas, repete a última. Não valida que `QuantizedDimension` corresponda ao eixo assumido; qdim fica no relatório. Calcula `q6[c] = round(6/scale_out[c]) + zp_out`, com `np.round`; pode replicar ou completar o array da mesma forma. Q6 é produzido para esses operadores mesmo quando a ativação não é RELU6, embora o ponteiro só seja habilitado para essa ativação.

Os offsets são calculados antes de acrescentar valores: `len(mul_vals)*4`, `len(shift_vals)*4`, `len(q6_vals)*4`. O mapa `mul_q6_off[op_idx]` contém `(mul_offset,shift_offset,q6_offset,nfeat)`. Não é indexado por label ou tensor de peso: dois operadores que compartilham pesos podem ter parâmetros de requantização diferentes.

## Caminho SOFTMAX

Lê a escala da entrada, fixa beta=1 e integer_bits=5. Calcula `input_left_shift = max(0,5-floor(log2(127*scale+1e-9))-1)`, quantiza `beta*scale`, acrescenta um MUL e SHIFT, sem Q6, e registra offsets com nfeat=1. Esses dados também são calculados no builder de softmax.

**Limitação real:** o kernel WAT observado não usa esses parâmetros para o cálculo exponencial; usa `(val-max)*7877 >> 16` e tabela fixa Q15. Assim, o relatório 06 documenta valores extraídos, não comprova que o kernel os aplica. Não interprete uma tabela de multiplicadores correta como garantia de softmax equivalente ao TFLite.

```text
scales TFLite por operador/canal
                 │
                 ▼
 M = sX × sW / sY        q6 = round(6/sY) + zY
                 │                     │
                 ▼                     │
       quantize_multiplier             │
                 │                     │
          ┌──────┴──────┐              │
          ▼             ▼              ▼
       mul_vals      shift_vals      q6_vals
          │             │              │
          ▼             ▼              ▼
       dtype='<i4': 4 bytes little-endian por valor
          │             │              │
          └─────────────┼──────────────┘
                        ▼
          blobs + mul_q6_off + records
```

Entram metadados específicos do modelo; o módulo calcula parâmetros inteiros e serializa arrays. Saem blobs para regiões MUL/SHIFT/Q6 e offsets para LayerParams. Formato int32 e convenção de shift são do runtime. Para SOFTMAX, a ligação entre parâmetro calculado e kernel é incompleta, conforme descrito acima.

## compute_add_quantization_params

Recebe scales A, B e Y. Define `scale_common = 2*max(scale_a,scale_b)`. Se ambas as entradas forem zero, a saída for zero ou common for zero, devolve seis zeros e common. Caso normal: quantiza A/common, B/common e common/Y. Retorna sete valores `(mul_a,shift_a,mul_b,shift_b,out_mul,out_shift,scale_common)`. O builder os coloca em campos geométricos reaproveitados. Não escreve nos blobs globais.

## Retorno e relatório

`extract_quantization_parameters` retorna listas `mul_vals,shift_vals,q6_vals`, bytes `mul_blob,shift_blob,q6_blob`, mapa `mul_q6_off` e `records`. Os três arrays são serializados com `np.array(...,dtype='<i4').tobytes()`. `quantization_to_text` mostra escalas, razões, arrays, offsets e totais por operação; retorna string para 06. Não efetua operações na rede.

## Invariantes e armadilhas

MUL e SHIFT devem corresponder canal a canal; offsets em bytes devem apontar para inteiros de 4 bytes. Escalas de saída nulas podem causar divisão por zero neste extrator mesmo quando outra função tem fallback. Escalas faltantes podem omitir registros sem erro imediato. Repetir a última escala é o comportamento atual, não uma validação de quantização per-axis arbitrária. Os kernels acumulam em i32 e têm regras de arredondamento próprias; overflow e divergência de arredondamento exigem testes numéricos específicos.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
import math
import numpy as np
from extractor.tflite_utils import op_name, qparams_np, scale_scalar, tensor_shape_list, zp_scalar
```

### `quantize_multiplier` — assinatura

```python
def quantize_multiplier(real_multiplier: float)
```

### `extract_quantization_parameters` — assinatura

```python
def extract_quantization_parameters(model, subgraph)
```

### `compute_add_quantization_params` — assinatura

```python
def compute_add_quantization_params(scale_a, scale_b, scale_y)
```

### `quantization_to_text` — assinatura

```python
def quantization_to_text(extraction)
```

## Material técnico preservado

A explicação anterior está em [08-quantizacao.md](historico/08-quantizacao.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.md).
