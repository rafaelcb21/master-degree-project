# 30 — Construção das LayerParams e camada sintética

[Índice](README.md) · Fonte: [extractor/layer_params.py](../extractor/layer_params.py)

## Responsabilidade e dados de entrada

É a ponte entre semântica TFLite e o ABI. Recebe modelo/subgrafo, mapas de slots runtime, bases físicas, offsets de pesos/bias e mapa de quantização por operador. Produz uma lista de dicts; ainda não escreve os 116 bytes. Constantes definem OP_CONV=1 até OP_RGB565_TO_RGB888=8, flags e LP_FMT/LP_SIZE. A tabela de campos serializados está no [contrato](08-contrato-layerparam-v1.md).

## Helpers de shape, mapeamento e memória

`tensor_hwc` retorna `(shape,height,width,channels)`: H=shape[1] e W=shape[2] para rank≥3; para rank 2 usa H=W=1,C=shape[1]; rank≥4 usa C=shape[3]. Não é um normalizador universal de layout e não valida rank. Rank 3 cai em C=1.

`build_runtime_tensor_mapping` associa inputs ao `slot_shift`; para cada saída alocada usa `(original_slot+slot_shift)%num_slots`. Retorna `tensor_to_slot,records,slot_shift`. Não faz a resolução recursiva de `tensor_mapping.py`, nem valida colisões; usa os outputs da alocação original.

`calculate_layer_memory_layout` calcula `num_layers=real+synthetic`, `params_bytes=ceil(num_layers*layer_param_size/alignment)*alignment`, `slot0=align(params_base+params_bytes)`, e as demais bases somando slot_bytes e alinhando. Retorna num_layers, params_bytes, slot_bases. A função tem um slot inicial mesmo se num_slots fosse zero, mas o pipeline admite apenas 3.

## Sintética: transformação que não veio do TFLite

`build_rgb565_layer` usa a primeira entrada do subgrafo e cria dict com op_index −1, optype RGB565_TO_RGB888, flags=0 (endereço do marcador), kh=65 (sentinela), input_slot 0 e output_slot 1. Não cria pesos/bias; usa as dimensões da imagem. O label textual não é uma camada original L0. O runtime lê um uint16 little-endian e expande R5/G6/B5 por replicação dos bits altos.

```text
RAW RGB565                           RAW BGR888
    │                                    │
    ▼                                    ▼
  SLOT0                         ImageNet adapter: BGR→RGB
    │                                    │
    ▼                                    ▼
┌──────────────────────┐               SLOT0
│ RGB565_TO_RGB888     │                 │
│ operação sintética 8 │                 │
└──────────┬───────────┘                 │
           ▼                            │
         SLOT1                          │
           ▼                            ▼
 primeira operação real          primeira operação real
 count=1 / shift=1               count=0 / shift=0
```

Entram bytes preparados segundo o pacote. Com sintética, Python adiciona um kernel e desloca os slots; sem ela, o adapter prepara RGB diretamente. Sai a representação da entrada lógica do TFLite. Dimensões são específicas; OP8 e o protocolo de formato são do runtime. O host sempre escreve em SLOT0, independentemente de slot_shift.

## build_layer_params: dispatcher Python

Inicia lista vazia, opcionalmente acrescenta RGB565. Valor sintético desconhecido causa ValueError. Percorre operadores na ordem original, pula os que não estão em `old_idx_to_label`, pula tipos fora da lista de sete suportados e pula operadores sem outputs válidos. Para o primeiro output exige mapa runtime; chama o builder apropriado e acrescenta o dict. Retorna lista. Não usa `graph.order` para ordenar esses registros e não lança erro por todo operador não suportado.

## Builders individuais

### _build_quantize_params

Exige ao menos uma entrada e slot conhecido. Lê shapes, primeira scale/zp de input/output, rejeita scale_out zero e quantiza a razão scale_in/scale_out para kh/kw. Bit 0 marca input INT8; desconhecido recebe flags de UINT8 e nome `unknown(code)` em metadados, sem rejeição imediata. Bit 1 marca output UINT8; output diferente de INT8/UINT8 é rejeitado. Força out_slot=in_slot, mesmo que o argumento trouxesse outro. Registra pad_t=input_ptr, zx/zy, input_dtype e quant_params. O kernel QUANTIZE usa cout×out_h×out_w como comprimento.

### _build_add_params

Exige duas entradas e slots de ambas. Lê geometria da primeira e saída, scales/zps A,B,Y; calcula três pares multiplier/shift com `compute_add_quantization_params`. Coloca-os em kh/kw, stride_h/w, dil_h/w. Usa pad_t/pad_b para ponteiros A/B e pad_l/pad_r para zero points A/B. Lê ativação fundida e a registra em act. Retorna input_slots com duas posições, input_ptrs e quant_params detalhados. Não verifica shapes iguais nem implementa broadcast; o WAT percorre o comprimento da primeira entrada e lê ambas no mesmo índice.

### _build_mean_params

Exige entrada e mapa; rejeita scale_y zero. Quantiza sX/sY, registra spatial_size=H×W e ponteiro da entrada. Fixa ACT_NONE, não lê o tensor de axis nem ReducerOptions. O comportamento efetivo do runtime é média espacial por canal, com divisão inteira truncada antes da requantização. Não é MEAN arbitrário em qualquer eixo.

### _build_softmax_params

Exige entrada e mapa. Fixa beta=1, integer_bits=5, diff_min=−128; calcula internal_scale=1/32, input_left_shift e multiplier de beta*sX. Armazena os valores em campos especiais e nos metadados; se op_idx estiver em mul_q6_off, habilita ponteiros MUL/SHIFT. O kernel atual ignora esses multiplicadores em favor de constante fixa; ver capítulo 13. O builder não lê beta do FlatBuffer.

### _build_weighted_params

Trata CONV_2D, DEPTHWISE_CONV_2D e FULLY_CONNECTED; exige duas entradas e slot da ativação. Obtém geometria por shape de pesos: CONV cout=dim0, kh=dim1, kw=dim2; depthwise cout=dim3; FC cout=dim0, kernel 1×1. Lê opções de stride/dilatação/padding/ativação; marca SAME e RELU6 e recalcula padding/out_h/out_w para SAME. Lê zps escalares, offsets por tensor e por operador. Peso ausente usa offset 0; bias e quantização ausentes desabilitam respectivos ponteiros. `depth_mult` fica no dict, mas não entra nos 29 campos e o kernel atual indexa input pelo canal de saída, presumindo multiplicador 1. FC não achata explicitamente H×W×C no builder.

## Estrutura comum e metadados

Os dicts incluem identidade (`op_index`, `optype`, `op_type`, e label para operações reais), slots, geometria, offsets e booleanos has_bias/has_mulq6, zero points, depth_mult, input_slots e input_ptrs. Builders especiais acrescentam `quant_params` para relatório. Nenhum desses campos auxiliares aumenta o LP_SIZE: o serializador escolhe exatamente 29 valores.

## layer_params_to_text

Recebe a lista e os argumentos obrigatórios keyword-only lp_size, memory_layout e runtime_mapping. Emite tamanho do registro, contagem de camadas, bases, shift runtime, legenda de campos especiais e todos os valores por camada. Inclui parâmetros de quantização, convenção de shifts e a tabela atual de flags QUANTIZE 0–3. Não recalcula kernels nem serializa; o relatório pode conter campos que o WAT não lê.

## Invariantes e riscos

Inputs/outputs dos builders precisam estar no mapa runtime; ADD precisa de dois ponteiros coerentes. O tamanho da reserva usa a quantidade de camadas do grafo, enquanto a lista efetiva pode ser menor por skips. O gerador usa o tamanho da lista efetiva para NUM_LAYERS; não rejeita automaticamente que o grafo tenha perdido uma operação. `real_layer_count` e identidade do último output merecem auditoria para modelos novos. A validação do contrato na configuração não detecta essas divergências semânticas.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
import math
import struct
from extractor.tflite_utils import op_name, scale_scalar, zp_scalar, tensor_shape_list
from extractor.quantization import quantize_multiplier, compute_add_quantization_params
from extractor.operator_options import ACT_NONE, ACT_RELU6, parse_add_options, parse_conv2d_options, parse_dwconv2d_options, parse_fc_options, same_padding
```

### `tensor_hwc` — assinatura

```python
def tensor_hwc(tensor)
```

### `build_runtime_tensor_mapping` — assinatura

```python
def build_runtime_tensor_mapping(
    subgraph,
    *,
    graph_inputs,
    slot_allocation,
    label_to_op_idx,
    num_slots,
    slot_shift,
)
```

### `calculate_layer_memory_layout` — assinatura

```python
def calculate_layer_memory_layout(
    *,
    real_layer_count,
    synthetic_layer_count,
    layer_param_size,
    params_base,
    slot_bytes,
    num_slots,
    alignment,
)
```

### `build_rgb565_layer` — assinatura

```python
def build_rgb565_layer(subgraph, *, slot_bases)
```

### `_build_quantize_params` — assinatura

```python
def _build_quantize_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_add_params` — assinatura

```python
def _build_add_params(
    subgraph,
    *,
    op_idx,
    op,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_mean_params` — assinatura

```python
def _build_mean_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
)
```

### `_build_softmax_params` — assinatura

```python
def _build_softmax_params(
    subgraph,
    *,
    op_idx,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    mul_q6_off,
)
```

### `_build_weighted_params` — assinatura

```python
def _build_weighted_params(
    subgraph,
    *,
    op_idx,
    op,
    op_type_name,
    label,
    input_ids,
    output_ids,
    out_slot,
    tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
)
```

### `build_layer_params` — assinatura

```python
def build_layer_params(
    model,
    subgraph,
    *,
    old_idx_to_label,
    runtime_tensor_to_slot,
    slot_bases,
    weight_tensor_off,
    bias_tensor_off,
    mul_q6_off,
    synthetic_layer='rgb565_to_rgb888',
)
```

### `layer_params_to_text` — assinatura

```python
def layer_params_to_text(layer_params, *, lp_size, memory_layout, runtime_mapping)
```

## Material técnico preservado

A explicação anterior está em [11-layer-params.md](historico/11-layer-params.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.md).
