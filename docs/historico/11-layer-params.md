> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.md). O corpo original foi mantido.

# 11 — Construção das LayerParams (`layer_params.py`)

## 1. Objetivo do módulo

O arquivo `extractor/layer_params.py` é responsável por transformar todas as informações extraídas e calculadas nas etapas anteriores em uma representação uniforme das operações que serão executadas pelo runtime WebAssembly.

Até este ponto, as informações estão distribuídas entre vários módulos:

```text
graph.py
    ↓
estrutura do grafo

slots.py
    ↓
alocação lógica de slots

tensor_mapping.py
    ↓
tensor → slot

weights.py
    ↓
offsets de pesos e bias

quantization.py
    ↓
multipliers, shifts e Q6

memory.py
    ↓
endereços físicos das regiões

operator_options.py
    ↓
stride, dilation, padding,
ativação e depth multiplier
```

`layer_params.py` reúne tudo isso.

O resultado é uma lista:

```text
layer_params
```

na qual cada elemento descreve uma operação do runtime.

Conceitualmente:

```text
TFLite + extração + planejamento
              │
              ▼
        layer_params.py
              │
              ▼
       LayerParam lógico
              │
              ▼
        params_blob.py
              │
              ▼
       LayerParam[] binário
              │
              ▼
             WASM
```

---

# 2. Papel arquitetural

Este módulo é a fronteira entre:

```text
modelo TFLite
+
estruturas do extrator
```

e:

```text
formato esperado pelo runtime
```

Antes dele, os dados ainda possuem significados específicos:

```text
tensor_id
op_index
weight_offset
mul_offset
slot lógico
padding SAME
scale
zero point
```

Depois dele, essas informações passam a ocupar campos padronizados:

```text
op_type
act
flags

in_slot
out_slot

in_h
in_w
cin
cout

kh
kw

stride_h
stride_w

dil_h
dil_w

pad_t
pad_b
pad_l
pad_r

w_off
b_off

mul_off
shift_off
q6_off

zx
zw
zy

out_h
out_w
```

Esses campos serão posteriormente serializados em uma estrutura binária fixa.

---

# 3. Importações

O módulo começa com:

```python
import math
import struct
```

`math` é utilizado principalmente nos cálculos específicos do `SOFTMAX`.

`struct` é utilizado para determinar o tamanho da estrutura binária `LayerParam`.

Também são importados helpers TFLite:

```python
from extractor.tflite_utils import (
    op_name,
    scale_scalar,
    zp_scalar,
    tensor_shape_list,
)
```

Esses helpers fornecem:

```text
op_name()
    → nome da operação

scale_scalar()
    → scale do tensor

zp_scalar()
    → zero point do tensor

tensor_shape_list()
    → shape Python
```

O módulo também recebe cálculos de quantização:

```python
from extractor.quantization import (
    quantize_multiplier,
    compute_add_quantization_params,
)
```

e opções dos operadores:

```python
from extractor.operator_options import (
    ACT_NONE,
    ACT_RELU6,
    parse_add_options,
    parse_conv2d_options,
    parse_dwconv2d_options,
    parse_fc_options,
    same_padding,
)
```

Essa composição demonstra que `layer_params.py` não deve refazer os cálculos que já pertencem aos módulos especializados.

---

# 4. `LP_FMT`

A estrutura binária futura é definida por:

```python
LP_FMT = "<" + "i" * 29
```

Isso significa:

```text
<
    little-endian

i
    inteiro assinado de 32 bits

29
    quantidade de campos
```

Portanto a estrutura possui:

```text
29 × 4 bytes
=
116 bytes
```

---

# 5. `LP_SIZE`

O tamanho é calculado automaticamente:

```python
LP_SIZE = struct.calcsize(
    LP_FMT
)
```

Resultando em:

```text
LP_SIZE = 116
```

Esse valor não é escrito manualmente.

Assim, se o formato mudar futuramente, `struct.calcsize()` continua sendo a fonte de verdade para seu tamanho.

---

# 6. Por que estrutura fixa?

O runtime precisa iterar rapidamente pelas camadas.

Uma estrutura de tamanho constante permite calcular:

```text
endereço da camada i
=
PARAMS_BASE
+
i × LP_SIZE
```

Com:

```text
LP_SIZE = 116
```

temos:

```text
layer 0 → PARAMS_BASE

layer 1 → PARAMS_BASE + 116

layer 2 → PARAMS_BASE + 232

layer 3 → PARAMS_BASE + 348
...
```

---

# 7. Tipos internos de operação

O módulo define:

```python
OP_CONV = 1
OP_DW = 2
OP_FC = 3
OP_ADD = 4
OP_MEAN = 5
OP_SOFTMAX = 6
OP_QUANTIZE = 7
OP_RGB565_TO_RGB888 = 8
```

Esses códigos formam o protocolo entre:

```text
extrator
```

e:

```text
runtime WAT
```

O runtime não precisa manipular strings como:

```text
"CONV_2D"
```

Ele recebe:

```text
1
```

e executa o kernel correspondente.

---

# 8. Mapeamento das operações

| Código | Operação            |
| -----: | ------------------- |
|    `1` | `CONV_2D`           |
|    `2` | `DEPTHWISE_CONV_2D` |
|    `3` | `FULLY_CONNECTED`   |
|    `4` | `ADD`               |
|    `5` | `MEAN`              |
|    `6` | `SOFTMAX`           |
|    `7` | `QUANTIZE`          |
|    `8` | `RGB565_TO_RGB888`  |

A oitava operação não vem originalmente do modelo TFLite.

Ela é criada pelo próprio extrator.

---

# 9. Flags

São definidos:

```python
FLAG_PADDING_SAME = 1 << 0
FLAG_HAS_Q6 = 1 << 1
```

Logo:

```text
FLAG_PADDING_SAME = 1

FLAG_HAS_Q6 = 2
```

Em representação binária:

```text
bit 0 → padding SAME

bit 1 → presença/uso de Q6
```

---

# 10. Exemplo de combinação

Uma convolução com:

```text
padding SAME
+
ReLU6
```

pode possuir:

```text
flags = 1 | 2
```

resultando em:

```text
flags = 3
```

Binariamente:

```text
00000011
```

---

# 11. Reutilização do bit 0 para `QUANTIZE`

Existe uma decisão importante:

```python
FLAG_QUANTIZE_INPUT_INT8 = (
    FLAG_PADDING_SAME
)
```

Ou seja:

```text
FLAG_QUANTIZE_INPUT_INT8 = 1
```

e:

```text
FLAG_PADDING_SAME = 1
```

possuem exatamente o mesmo bit.

---

# 12. Isso não significa a mesma semântica

O significado depende de:

```text
op_type
```

Para uma convolução:

```text
bit 0 = 1
    ↓
padding SAME
```

Para `QUANTIZE`:

```text
bit 0 = 1
    ↓
input é int8
```

Portanto:

```text
flags
```

não deve ser interpretado isoladamente.

A interpretação correta é:

```text
(op_type, flags)
```

---

# 13. Tipos TFLite utilizados

O módulo define:

```python
TFLITE_UINT8 = 3
TFLITE_INT8 = 9
```

Esses códigos são usados para decidir o significado do input do `QUANTIZE`.

---

# 14. Constantes da camada RGB

Também existem:

```python
FORMAT_FLAG_ADDR = 0
FORMAT_RGB565 = 65
```

e:

```python
INPUT_FORMAT_SLOT = 0
RGB888_SLOT = 1
```

Esses valores pertencem à camada sintética de entrada.

---

# 15. Função `tensor_hwc()`

A primeira função auxiliar é:

```python
def tensor_hwc(tensor):
```

Ela transforma o shape de um tensor em:

```text
shape completo
height
width
channels
```

---

# 16. Shape original

Primeiro:

```python
shape = tensor_shape_list(
    tensor
)
```

Exemplo:

```text
[1, 128, 128, 3]
```

---

# 17. Altura

O código usa:

```text
shape[1]
```

quando existem pelo menos três dimensões.

Assim:

```text
[1, 128, 128, 3]
    ↑
    height
```

produz:

```text
height = 128
```

---

# 18. Largura

Quando possível:

```text
width = shape[2]
```

Exemplo:

```text
[1, 128, 128, 3]
         ↑
       width
```

---

# 19. Canais

Para tensores 4D:

```text
channels = shape[3]
```

---

# 20. Tensores 2D

Existe um tratamento especial:

```python
shape[1]
if len(shape) == 2
```

Assim um tensor como:

```text
[1, 1000]
```

resulta em:

```text
height = 1
width = 1
channels = 1000
```

Essa representação é útil para `FULLY_CONNECTED`.

---

# 21. Fallback

Quando não existe uma dimensão apropriada:

```text
height = 1

width = 1

channels = 1
```

A função normaliza diferentes shapes para uma representação HWC comum.

---

# 22. Primeiro problema especial: slots do runtime

Até `tensor_mapping.py`, o input do modelo estava associado logicamente a:

```text
SLOT0
```

Porém, o runtime agora introduz uma nova etapa antes do primeiro operador TFLite:

```text
RGB565_TO_RGB888
```

Isso exige reorganizar os slots.

---

# 23. Antes da camada sintética

Conceitualmente:

```text
input TFLite
    ↓
SLOT0
    ↓
QUANTIZE / primeira operação
```

---

# 24. Depois da camada sintética

O runtime passa a utilizar:

```text
dados recebidos
    ↓
SLOT0
    ↓
RGB565_TO_RGB888
    ↓
SLOT1
    ↓
modelo TFLite
```

Portanto a antiga saída lógica de SLOT0 precisa deslocar-se.

---

# 25. `build_runtime_tensor_mapping()`

Essa transformação é feita por:

```python
def build_runtime_tensor_mapping(
    subgraph,
    *,
    graph_inputs,
    slot_allocation,
    label_to_op_idx,
    num_slots,
    slot_shift,
):
```

A função cria um novo:

```text
tensor → slot
```

específico para o runtime.

---

# 26. Input original do grafo

Para cada:

```python
tensor_id in graph_inputs
```

o código faz:

```python
tensor_to_slot[
    tensor_id
] = slot_shift
```

Com o deslocamento atual:

```text
slot_shift = 1
```

isso significa:

```text
input TFLite
    ↓
runtime SLOT1
```

---

# 27. Por que SLOT1?

Porque:

```text
SLOT0
```

passa a representar a região de entrada usada pela camada sintética.

Depois da conversão:

```text
SLOT1
```

contém os dados RGB888 esperados pelo restante da rede.

---

# 28. Remapeamento das saídas reais

Para cada alocação original:

```python
original_slot = (
    alloc["output_slot"]
)
```

é calculado:

```python
runtime_slot = (
    original_slot
    + slot_shift
) % num_slots
```

---

# 29. Exemplo com três slots

Com:

```text
num_slots = 3
slot_shift = 1
```

temos:

```text
original SLOT0
    ↓
runtime SLOT1

original SLOT1
    ↓
runtime SLOT2

original SLOT2
    ↓
runtime SLOT0
```

---

# 30. Rotação circular

Portanto:

```text
0 → 1

1 → 2

2 → 0
```

Não estamos adicionando um quarto slot.

Estamos realizando uma rotação dos três slots existentes.

---

# 31. Por que usar módulo `%`?

Para:

```text
original_slot = 2
```

teríamos:

```text
2 + 1 = 3
```

Mas:

```text
3 % 3 = 0
```

faz a rotação retornar ao início.

---

# 32. Registro da conversão

Cada output recebe:

```python
{
    "tensor_id": ...,
    "layer": ...,
    "original_slot": ...,
    "runtime_slot": ...,
}
```

Isso permite gerar um relatório como:

```text
tensor=42
layer=L10
slot_original=2
slot_runtime=0
```

---

# 33. Resultado do runtime mapping

A função retorna:

```python
{
    "tensor_to_slot": ...,
    "records": ...,
    "slot_shift": ...,
}
```

A partir daqui, `layer_params.py` deve usar:

```text
runtime_tensor_to_slot
```

e não mais o mapeamento lógico anterior.

A rotação é feita explicitamente para acomodar a conversão sintética de entrada.

---

# 34. Planejamento da região `LayerParam[]`

A função:

```python
calculate_layer_memory_layout()
```

calcula quanto espaço as estruturas das camadas ocupam e onde começam os slots.

---

# 35. Quantidade total de camadas

É calculado:

```python
num_layers = (
    real_layer_count
    + synthetic_layer_count
)
```

---

# 36. Exemplo

Se o modelo possui:

```text
67 operações reais utilizadas
```

e adicionamos:

```text
1 camada sintética
```

teremos:

```text
num_layers = 68
```

---

# 37. Tamanho bruto de `PARAMS`

Com:

```text
LP_SIZE = 116
```

o tamanho bruto seria:

```text
68 × 116
=
7888 bytes
```

---

# 38. Alinhamento de `params_bytes`

O código utiliza:

```text
ceil(
    num_layers × LP_SIZE
    / alignment
)
× alignment
```

produzindo um tamanho alinhado.

---

# 39. Por que alinhar o bloco inteiro?

A próxima região:

```text
SLOT0
```

deve começar em uma fronteira coerente com a política de memória.

---

# 40. Base do primeiro slot

Depois:

```text
SLOT0_BASE
=
align_up(
    PARAMS_BASE
    +
    params_bytes
)
```

A implementação faz a fórmula diretamente, em vez de chamar `align_up()`.

---

# 41. Slots seguintes

Para cada slot seguinte:

```text
next_base
=
previous_slot_base
+
slot_bytes
```

e depois:

```text
next_base
=
align_up(next_base)
```

---

# 42. Resultado

A função retorna:

```python
{
    "num_layers": ...,
    "params_bytes": ...,
    "slot_bases": ...,
}
```

Assim, o layout nessa fase fica:

```text
PARAMS_BASE
    │
    ├── LayerParam 0
    ├── LayerParam 1
    ├── LayerParam 2
    ├── ...
    │
    ▼
fim de PARAMS
    │
    ▼
alinhamento
    │
    ▼
SLOT0
    │
    ▼
SLOT1
    │
    ▼
SLOT2
```

---

# 43. Camada sintética `RGB565_TO_RGB888`

Antes das operações reais é criada:

```python
build_rgb565_layer()
```

Essa camada não existe no TFLite.

---

# 44. Objetivo

Ela cria uma operação do runtime:

```text
RGB565_TO_RGB888
```

antes da rede.

A camada é identificada por:

```python
"op_index": -1
```

indicando que:

```text
não existe operador TFLite correspondente
```

---

# 45. Tipo interno

```python
"op_type": OP_RGB565_TO_RGB888
```

ou:

```text
op_type = 8
```

---

# 46. Slots

A camada usa:

```text
input = SLOT0
output = SLOT1
```

por meio de:

```python
"in_slot": INPUT_FORMAT_SLOT
```

e:

```python
"out_slot": RGB888_SLOT
```

---

# 47. Geometria

A altura, largura e canais vêm do tensor de entrada original do modelo:

```text
in_h
in_w
input_channels
```

---

# 48. Shape da saída

A conversão não altera:

```text
altura
largura
número de canais
```

Assim:

```text
out_h = in_h

out_w = in_w

cout = cin
```

---

# 49. Campo `kh`

A camada usa:

```python
"kh": FORMAT_RGB565
```

com:

```text
FORMAT_RGB565 = 65
```

Portanto:

```text
kh = 65
```

é um valor especial nesta operação.

Não representa altura de kernel.

---

# 50. Ausência de pesos

A camada possui:

```text
w_off = 0

has_bias = False

has_mulq6 = False
```

porque se trata de uma conversão de formato implementada diretamente pelo runtime.

---

# 51. Ponteiro de entrada

O campo auxiliar:

```python
"input_ptrs"
```

contém:

```text
slot_bases[0]
```

ou seja, o endereço físico do SLOT0.

A camada sintética é inserida explicitamente antes de qualquer operador real do modelo.

---

# 52. Builders especializados

Depois da camada sintética, cada tipo de operação possui um builder apropriado.

```text
QUANTIZE
    ↓
_build_quantize_params()

ADD
    ↓
_build_add_params()

MEAN
    ↓
_build_mean_params()

SOFTMAX
    ↓
_build_softmax_params()

CONV / DW / FC
    ↓
_build_weighted_params()
```

Essa divisão evita uma única função gigantesca cheia de condicionais.

---

# 53. `_build_quantize_params()`

Essa função constrói a representação da operação:

```text
QUANTIZE
```

---

# 54. Validação da entrada

A operação precisa de ao menos um input.

Se não houver:

```text
RuntimeError
```

é lançado.

---

# 55. Quantização de entrada e saída

São obtidos:

```text
scale_in
zp_in

scale_out
zp_out
```

---

# 56. Relação entre escalas

A requantização utiliza:

```text
ratio =
scale_in
─────────
scale_out
```

---

# 57. Multiplicador inteiro

Depois:

```text
ratio
    ↓
quantize_multiplier()
    ↓
multiplier
shift
```

---

# 58. Validação de `scale_out`

Se:

```text
scale_out = 0
```

a função interrompe a construção.

Isso evita uma divisão por zero.

---

# 59. Slot da entrada

A função exige que:

```text
input_tensor_id
```

esteja presente em:

```text
tensor_to_slot
```

Caso contrário, lança:

```text
RuntimeError
```

---

# 60. Ponteiro

Depois:

```text
input_ptr =
slot_bases[in_slot]
```

Assim:

```text
tensor
 ↓
runtime slot
 ↓
base física do slot
```

---

# 61. Tipo do input

O código inspeciona:

```python
input_tensor.Type()
```

---

# 62. Input INT8

Se:

```text
input_dtype = TFLITE_INT8
```

é definido:

```text
flags =
FLAG_QUANTIZE_INPUT_INT8
```

ou:

```text
flags = 1
```

---

# 63. Input UINT8

Se:

```text
input_dtype = TFLITE_UINT8
```

temos:

```text
flags = 0
```

---

# 64. Outros tipos

Tipos desconhecidos também recebem:

```text
flags = 0
```

mas são registrados no dicionário:

```text
quant_params
```

como:

```text
unknown(código)
```

---

# 65. `QUANTIZE` é in-place

A função explicitamente redefine:

```python
out_slot = in_slot
```

Portanto:

```text
entrada
    ↓
SLOTn
    ↓
QUANTIZE
    ↓
mesmo SLOTn
```

Isso preserva a decisão já existente em `slots.py`.

---

# 66. Reuso de campos no `QUANTIZE`

Para essa operação:

```text
kh = multiplier

kw = shift

pad_t = input_ptr

zx = zero point de entrada

zy = zero point de saída
```

Os campos deixam de possuir seus significados geométricos tradicionais.

---

# 67. Estrutura especial do QUANTIZE

```text
LayerParam
┌────────────────────────┐
│ op_type = 7            │
│ flags = tipo do input  │
│                        │
│ kh = multiplier        │
│ kw = shift             │
│                        │
│ pad_t = input_ptr      │
│                        │
│ zx = zp_in             │
│ zy = zp_out            │
└────────────────────────┘
```

A função mantém também um dicionário detalhado `quant_params` para relatório e diagnóstico.

---

# 68. `_build_add_params()`

`ADD` é mais complexo porque possui duas entradas dinâmicas.

---

# 69. Entradas

São carregados:

```text
input_tensor_a

input_tensor_b

output_tensor
```

---

# 70. Quantização

Para A:

```text
scale_a
zp_a
```

Para B:

```text
scale_b
zp_b
```

Para a saída:

```text
scale_y
zp_y
```

---

# 71. Parâmetros do ADD

A função chama:

```python
compute_add_quantization_params(
    scale_a,
    scale_b,
    scale_y,
)
```

recebendo:

```text
mul_a
shift_a

mul_b
shift_b

output_mul
output_shift

scale_common
```

---

# 72. Ativação fundida

É obtida por:

```python
parse_add_options(
    op
)
```

Assim um ADD pode carregar:

```text
NONE
RELU
RELU6
```

conforme suportado pelo parser.

---

# 73. Dois slots de entrada

O módulo exige que ambos os tensors estejam mapeados:

```text
tensor A → slot A

tensor B → slot B
```

Depois:

```text
input_ptr_a =
slot_bases[slot_a]

input_ptr_b =
slot_bases[slot_b]
```

---

# 74. Reuso dos campos no ADD

O `ADD` usa:

```text
kh       = multiplier A

kw       = shift A

stride_h = multiplier B

stride_w = shift B

dil_h    = multiplier da saída

dil_w    = shift da saída
```

---

# 75. Ponteiros do ADD

Os campos de padding são reutilizados:

```text
pad_t = ponteiro da entrada A

pad_b = ponteiro da entrada B
```

---

# 76. Zero points do ADD

Também:

```text
pad_l = zero point A

pad_r = zero point B
```

Além disso:

```text
zx = zp_a

zw = zp_b

zy = zp_y
```

---

# 77. Por que duplicar os zero points?

`pad_l` e `pad_r` fazem parte do protocolo especial utilizado pelo kernel ADD.

Já:

```text
zx
zw
zy
```

mantêm a representação padronizada dos zero points da operação.

---

# 78. Diagrama do ADD

```text
tensor A
   │
   ▼
SLOT A ────────────────┐
                       │
                       ▼
                    ADD
                       │
tensor B               │
   │                   │
   ▼                   │
SLOT B ────────────────┘
                       │
                       ▼
                  output SLOT
```

A `LayerParam` precisa, portanto, transportar dois ponteiros reais de entrada.

---

# 79. Campos especiais do ADD

```text
kh       → mul0
kw       → shift0

stride_h → mul1
stride_w → shift1

dil_h    → out_mul
dil_w    → out_shift

pad_t    → input_ptr A
pad_b    → input_ptr B

pad_l    → zero point A
pad_r    → zero point B
```

Esse mapeamento aparece tanto no builder quanto no relatório gerado pelo módulo.

---

# 80. `_build_mean_params()`

A operação:

```text
MEAN
```

também recebe uma representação especializada.

---

# 81. Quantização

A função obtém:

```text
scale_x
zp_x

scale_y
zp_y
```

---

# 82. Relação

É calculado:

```text
ratio =
scale_x / scale_y
```

e depois:

```text
multiplier
shift
```

---

# 83. `spatial_size`

A função calcula:

```python
spatial_size = (
    in_h
    * in_w
)
```

---

# 84. Exemplo

Para:

```text
input =
7 × 7 × 1280
```

temos:

```text
spatial_size =
7 × 7
=
49
```

O MEAN precisa usar esse valor para efetuar a média espacial.

---

# 85. Campos especiais

O mapeamento é:

```text
kh = multiplier

kw = shift

stride_h = spatial_size

pad_t = input_ptr
```

---

# 86. Demais parâmetros

Não existem:

```text
pesos
bias
MUL externo
SHIFT externo
Q6 externo
```

para essa representação.

Portanto:

```text
has_bias = False

has_mulq6 = False
```

---

# 87. Zero points

São registrados:

```text
zx = zp_x

zy = zp_y
```

---

# 88. Representação

```text
LayerParam MEAN

kh        → multiplier
kw        → shift
stride_h  → H × W
pad_t     → input pointer

zx        → input zero point
zy        → output zero point
```

---

# 89. `_build_softmax_params()`

O `SOFTMAX` possui uma preparação ainda mais específica.

---

# 90. Dados da entrada e saída

São obtidos:

```text
scale_x
zp_x

scale_y
zp_y
```

---

# 91. Constantes utilizadas

A implementação define:

```text
beta = 1.0

integer_bits = 5
```

---

# 92. `input_left_shift`

É calculado a partir de:

```text
integer_bits

127 × scale_x
```

utilizando:

```text
log2
floor
```

e limitado inferiormente a zero.

---

# 93. `internal_scale`

Também é calculado:

```text
internal_scale =
1 / 2^integer_bits
```

Com:

```text
integer_bits = 5
```

temos:

```text
internal_scale =
1 / 32
=
0.03125
```

Esse valor é preservado em:

```text
quant_params
```

para relatório.

---

# 94. Multiplicador beta

O cálculo usa:

```text
real_multiplier =
beta × scale_x
```

Depois:

```text
real_multiplier
    ↓
quantize_multiplier()
    ↓
input_beta_mul
input_beta_left_shift
```

---

# 95. `diff_min`

A implementação fixa:

```text
diff_min = -128
```

---

# 96. Slot e ponteiro

Assim como nas demais operações:

```text
input_tensor
    ↓
runtime tensor mapping
    ↓
in_slot
    ↓
slot_bases[in_slot]
    ↓
input_ptr
```

---

# 97. Relação com `mul_q6_off`

O `SOFTMAX` verifica:

```python
op_idx in mul_q6_off
```

Se houver registro:

```text
mul_off
shift_off
```

são preservados.

O `q6_off` permanece:

```text
0
```

---

# 98. Mapeamento correto do SOFTMAX

Na implementação atual:

```text
kh
=
input_beta_mul
```

```text
kw
=
input_beta_left_shift
```

```text
stride_h
=
diff_min
```

```text
stride_w
=
input_left_shift
```

```text
pad_t
=
input_ptr
```

Esse detalhe é especialmente importante: **`stride_w` armazena `input_left_shift`**.

Ele não armazena `integer_bits`.

O próprio código atual registra explicitamente esse comportamento.

---

# 99. Por que isso merece destaque?

Os nomes:

```text
kh
kw
stride_h
stride_w
```

não representam geometria para o `SOFTMAX`.

Eles são reutilizados para transportar parâmetros específicos do kernel.

Portanto não se deve interpretar:

```text
stride_w
```

como stride horizontal quando:

```text
op_type = OP_SOFTMAX
```

---

# 100. Zero points do SOFTMAX

São mantidos:

```text
zx = zp_x

zy = zp_y
```

e:

```text
zw = 0
```

porque não existe tensor de pesos.

---

# 101. Metadados de quantização

O `quant_params` do SOFTMAX registra:

```text
sX
sY

zX
zY

beta

integer_bits

internal_scale

real_multiplier

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

Isso fornece rastreabilidade completa da preparação matemática da operação.

---

# 102. `_build_weighted_params()`

Essa função reúne três operações estruturalmente relacionadas:

```text
CONV_2D

DEPTHWISE_CONV_2D

FULLY_CONNECTED
```

Todas possuem:

```text
input de ativação
pesos
bias opcional
```

e utilizam tabelas externas de requantização.

---

# 103. Estrutura mínima

A operação precisa possuir:

```text
input[0]
    → ativação

input[1]
    → pesos
```

Se houver:

```text
input[2]
```

ele é tratado como:

```text
bias
```

---

# 104. Dados comuns

Primeiro são recuperados:

```text
input_tensor

weight_tensor

output_tensor

bias_id
```

Além de:

```text
input HWC

output shape

weight shape
```

---

# 105. Defaults iniciais

A função começa com:

```text
stride = 1

dilation = 1

padding = 0

activation = NONE

flags = 0

depth_mult = 1
```

Depois cada tipo de operador modifica somente o necessário.

---

# 106. Caminho `CONV_2D`

Para:

```text
CONV_2D
```

é definido:

```text
op_type = OP_CONV
```

---

# 107. `cout` da CONV

Preferencialmente:

```text
cout =
weight_shape[0]
```

---

# 108. Kernel da CONV

A estrutura esperada fornece:

```text
kernel_h =
weight_shape[1]

kernel_w =
weight_shape[2]
```

---

# 109. Opções da CONV

Depois:

```python
parse_conv2d_options(
    op
)
```

fornece:

```text
stride_h
stride_w

dil_h
dil_w

padding_kind

activation
```

---

# 110. Flag `SAME`

Se:

```text
padding_kind == 0
```

é executado:

```text
flags |= FLAG_PADDING_SAME
```

---

# 111. Caminho `DEPTHWISE_CONV_2D`

Para depthwise:

```text
op_type = OP_DW
```

---

# 112. Kernel depthwise

Também são usados:

```text
weight_shape[1]
weight_shape[2]
```

como:

```text
kernel_h
kernel_w
```

---

# 113. `cout`

Para depthwise:

```text
cout =
weight_shape[3]
```

quando disponível.

---

# 114. Opções específicas

`parse_dwconv2d_options()` também fornece:

```text
depth_mult
```

além de stride, dilation, padding e activation.

---

# 115. Caminho `FULLY_CONNECTED`

Para:

```text
FULLY_CONNECTED
```

é utilizado:

```text
op_type = OP_FC
```

---

# 116. Número de saídas

Preferencialmente:

```text
cout =
weight_shape[0]
```

---

# 117. Kernel lógico do FC

O código define:

```text
kernel_h = 1

kernel_w = 1
```

Esses campos não descrevem uma convolução real nesse caso.

Eles são apenas valores coerentes para a estrutura uniforme.

---

# 118. Opções do FC

A única opção necessária aqui é:

```text
activation
```

obtida por:

```python
parse_fc_options(
    op
)
```

---

# 119. Operação inesperada

Se `_build_weighted_params()` receber um tipo diferente desses três:

```text
RuntimeError
```

é lançado.

Essa é uma validação importante porque impede usar o builder genérico para uma operação incompatível.

---

# 120. Flag de ReLU6

Depois da identificação da operação:

```python
if activation == ACT_RELU6:
    flags |= FLAG_HAS_Q6
```

Assim:

```text
ReLU6
    ↓
bit HAS_Q6
```

---

# 121. Cálculo de SAME

Se:

```text
flags & FLAG_PADDING_SAME
```

estiver ativo:

```python
same_padding(...)
```

é chamado.

---

# 122. Valores produzidos

São calculados:

```text
pad_t
pad_b
pad_l
pad_r

out_h
out_w
```

---

# 123. Zero points

Depois são extraídos:

```text
zp_x
    → entrada

zp_w
    → pesos

zp_y
    → saída
```

---

# 124. Offsets dos pesos

O tensor de peso é:

```text
input_ids[1]
```

e:

```python
weight_tensor_off.get(
    weight_tensor_id,
    0,
)
```

fornece o offset relativo no blob de pesos.

---

# 125. Importante sobre o fallback

Se não existir entrada em:

```text
weight_tensor_off
```

o valor será:

```text
0
```

Não existe aqui um booleano:

```text
has_weight
```

equivalente ao `has_bias`.

Portanto, a etapa anterior precisa ter extraído corretamente os pesos das operações suportadas.

---

# 126. Bias

O código calcula:

```text
has_bias =
bias_id >= 0
e
bias_id existe em bias_tensor_off
```

---

# 127. Offset do bias

Mesmo quando não há bias:

```text
bias_offset = 0
```

Mas:

```text
has_bias = False
```

permite à etapa de serialização distinguir:

```text
offset zero válido
```

de:

```text
bias inexistente
```

---

# 128. MUL, SHIFT e Q6

A função verifica:

```text
op_idx in mul_q6_off
```

---

# 129. Se existir

São recuperados:

```text
mul_offset

shift_offset

q6_offset
```

---

# 130. Se não existir

Todos ficam:

```text
0
```

e:

```text
has_mulq6 = False
```

---

# 131. Slot de entrada

O tensor de ativação:

```text
input_ids[0]
```

precisa existir em:

```text
runtime_tensor_to_slot
```

Caso contrário o extrator falha imediatamente.

---

# 132. Ponteiro

Depois:

```text
input_ptr =
slot_bases[in_slot]
```

Esse ponteiro ainda é mantido apenas como metadado auxiliar em:

```text
input_ptrs
```

A serialização final calculará os ponteiros necessários conforme a convenção da estrutura.

---

# 133. Estrutura resultante da CONV/DW/FC

O builder retorna campos com seus significados naturais:

```text
kh
kw
    → dimensões do kernel

stride_h
stride_w
    → stride

dil_h
dil_w
    → dilation

pad_t
pad_b
pad_l
pad_r
    → padding

w_off
    → offset dos pesos

b_off
    → offset do bias

mul_off
shift_off
q6_off
    → offsets das tabelas de quantização

zx
zw
zy
    → zero points
```

Nesse grupo de operações, ao contrário dos builders especiais, os campos permanecem majoritariamente alinhados aos seus nomes originais.

---

# 134. `depth_mult`

Somente:

```text
DEPTHWISE_CONV_2D
```

mantém o `depth_mult` lido do TFLite.

Nas demais:

```text
depth_mult = 1
```

---

# 135. Estrutura uniforme e polimorfismo por `op_type`

A principal decisão de projeto da `LayerParam` é utilizar uma estrutura fixa para operações muito diferentes.

Assim:

```text
op_type
```

define como interpretar os demais campos.

---

# 136. Exemplo

Para:

```text
op_type = OP_CONV
```

temos:

```text
kh = kernel height
```

Mas para:

```text
op_type = OP_ADD
```

temos:

```text
kh = multiplier da entrada A
```

E para:

```text
op_type = OP_SOFTMAX
```

temos:

```text
kh = input_beta_mul
```

---

# 137. Portanto

O significado correto de um campo é:

```text
significado =
função(
    op_type,
    campo
)
```

e não apenas:

```text
significado =
nome do campo
```

Essa é uma das características fundamentais do protocolo.

---

# 138. Tabela dos principais campos sobrecarregados

| Campo      | CONV/DW/FC     | ADD          | MEAN         | SOFTMAX          | QUANTIZE   |
| ---------- | -------------- | ------------ | ------------ | ---------------- | ---------- |
| `kh`       | kernel H       | mul A        | multiplier   | beta mul         | multiplier |
| `kw`       | kernel W       | shift A      | shift        | beta shift       | shift      |
| `stride_h` | stride H       | mul B        | spatial size | diff_min         | 0          |
| `stride_w` | stride W       | shift B      | 1            | input_left_shift | 0          |
| `dil_h`    | dilation H     | output mul   | 1            | 1                | 1          |
| `dil_w`    | dilation W     | output shift | 1            | 1                | 1          |
| `pad_t`    | top padding    | ptr A        | input ptr    | input ptr        | input ptr  |
| `pad_b`    | bottom padding | ptr B        | 0            | 0                | 0          |
| `pad_l`    | left padding   | zp A         | 0            | 0                | 0          |
| `pad_r`    | right padding  | zp B         | 0            | 0                | 0          |

Essa tabela é essencial para interpretar um dump de `LayerParam`.

---

# 139. `build_layer_params()`

Depois dos builders individuais vem a função que coordena a construção completa:

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
):
```

---

# 140. Primeiro elemento

A função começa com:

```python
layer_params = []
```

e imediatamente cria:

```text
RGB565_TO_RGB888
```

---

# 141. Consequência

A posição:

```text
layer_params[0]
```

não corresponde à primeira operação TFLite.

Ela corresponde à camada sintética.

---

# 142. Operações reais

Somente depois são adicionadas as operações do modelo.

Os tipos aceitos são:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
```

---

# 143. Filtro pelo grafo útil

O loop percorre todos os operadores TFLite, mas executa:

```python
if (
    op_idx
    not in old_idx_to_label
):
    continue
```

Portanto somente operações pertencentes ao grafo considerado pelo extrator geram `LayerParam`.

---

# 144. Segundo filtro

Mesmo entre essas operações:

```text
op_type_name
```

precisa estar em:

```text
supported_operations
```

Caso contrário, a operação é ignorada nesta etapa.

---

# 145. Inputs e outputs

São coletados:

```text
input_ids
output_ids
```

eliminando IDs negativos.

---

# 146. Operação sem output

Se:

```text
output_ids = []
```

a operação é ignorada.

---

# 147. Output precisa de runtime slot

O primeiro output deve estar em:

```text
runtime_tensor_to_slot
```

Caso contrário:

```text
RuntimeError
```

é lançado.

---

# 148. Por que validar aqui?

Porque toda operação precisa saber:

```text
onde escrever seu resultado
```

antes da construção da sua `LayerParam`.

---

# 149. Descoberta do `out_slot`

```text
output tensor
      ↓
runtime_tensor_to_slot
      ↓
out_slot
```

---

# 150. Dispatch por tipo

Depois:

```text
QUANTIZE
    ↓
_build_quantize_params()

ADD
    ↓
_build_add_params()

MEAN
    ↓
_build_mean_params()

SOFTMAX
    ↓
_build_softmax_params()

outros suportados
    ↓
_build_weighted_params()
```

---

# 151. Por que o `else` é seguro?

Antes do dispatch existe:

```text
supported_operations
```

e os quatro tipos especiais já foram tratados.

Portanto o `else` restante contém apenas:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

---

# 152. Resultado

Cada builder retorna um dicionário:

```python
params
```

que é adicionado por:

```python
layer_params.append(
    params
)
```

---

# 153. Ordem final

A lista possui:

```text
posição 0
    RGB565_TO_RGB888

posição 1
    primeira operação real considerada

posição 2
    segunda operação real

...
```

A função realiza explicitamente essa composição.

---

# 154. Importante sobre ordem

`build_layer_params()` percorre:

```python
range(
    subgraph.OperatorsLength()
)
```

ou seja, a ordem dos operadores no subgrafo TFLite.

Ela não percorre explicitamente:

```text
graph["order"]
```

A presença no grafo é determinada por:

```text
old_idx_to_label
```

mas a ordem de inserção segue o `op_idx` original.

Para o modelo atual isso é compatível com a execução utilizada.

---

# 155. `layer_params_to_text()`

A última grande função produz o relatório de todas as estruturas criadas.

Sua docstring deixa explícito que esse relatório substitui os antigos comentários de debug que eram escritos diretamente dentro do WAT.

---

# 156. Por que isso é uma melhoria arquitetural?

Antes poderíamos ter:

```text
WAT
 │
 ├── código executável
 ├── comentários de debug
 ├── dump das camadas
 ├── parâmetros
 └── explicações
```

Agora:

```text
WAT
    ↓
somente código necessário

reports/
    ↓
informações de diagnóstico
```

---

# 157. Resumo inicial do relatório

O relatório mostra:

```text
LayerParam size

número de layers

params bytes

slot bases

runtime slot shift
```

---

# 158. Convenção de shift

Também registra explicitamente:

```text
shift > 0
    → LEFT SHIFT

shift < 0
    → RIGHT SHIFT
```

Isso é essencial para interpretar os parâmetros de requantização.

---

# 159. Mapeamento dos campos especiais

O relatório documenta diretamente:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

e como cada um reutiliza os campos da estrutura.

---

# 160. ADD no relatório

É documentado:

```text
kh       = mul0

kw       = shift0

stride_h = mul1

stride_w = shift1

dil_h    = out_mul

dil_w    = out_shift

pad_t    = input_ptr[0]

pad_b    = input_ptr[1]

pad_l    = zero point input A

pad_r    = zero point input B
```

---

# 161. MEAN no relatório

```text
kh       = multiplier

kw       = shift

stride_h = in_h × in_w

pad_t    = input_ptr
```

---

# 162. SOFTMAX no relatório

O relatório atual documenta corretamente:

```text
kh       = input_beta_mul

kw       = input_beta_left_shift

stride_h = diff_min

stride_w = input_left_shift

pad_t    = input_ptr
```

---

# 163. QUANTIZE no relatório

```text
flags =
0 para uint8

1 para int8
```

e:

```text
kh = multiplier

kw = shift

pad_t = input_ptr

zx = zero point de entrada

zy = zero point de saída
```

---

# 164. RGB565 no relatório

A camada sintética é explicada como:

```text
input slot = SLOT0

output slot = SLOT1

kh = 65
```

---

# 165. Mapeamento de runtime

O relatório também mostra a transformação:

```text
slot_original
    ↓
slot_runtime
```

para cada tensor produzido.

Exemplo:

```text
tensor=45
layer=L12
slot_original=2
slot_runtime=0
```

---

# 166. Full layer dump

Depois é produzido um dump de todas as camadas.

Para cada uma são exibidos:

```text
op_index

label

optype

op_type

act

flags

in_slot / out_slot

input_slots

input_ptrs

in_h / in_w

cin / cout

kh / kw

stride_h / stride_w

dil_h / dil_w

padding

out_h / out_w

weight offset

bias offset

mul offset

shift offset

Q6 offset

zero points

depth multiplier
```

---

# 167. `quant_params`

Quando uma operação possui:

```python
quant_params
```

o relatório imprime também cada parâmetro calculado.

Isso ocorre, por exemplo, em:

```text
QUANTIZE
ADD
MEAN
SOFTMAX
```

---

# 168. Exemplo de QUANTIZE

Podem aparecer:

```text
scale_in
scale_out

zp_in
zp_out

ratio

mul
shift

input_dtype
```

---

# 169. Exemplo de ADD

```text
sA
sB
sY

zA
zB
zY

mul0
shift0

mul1
shift1

out_mul
out_shift

s_common
```

---

# 170. Exemplo de SOFTMAX

```text
sX
sY

zX
zY

beta

integer_bits

internal_scale

real_multiplier

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

---

# 171. Estruturas que são runtime e estruturas que são debug

Nem tudo no dicionário retornado será serializado.

Campos como:

```text
label

op_index

optype

has_bias

has_mulq6

input_slots

input_ptrs

quant_params
```

são principalmente metadados do extrator.

---

# 172. Campos serializados

Já os campos numéricos correspondentes à estrutura de 29 `int32` serão consumidos por:

```text
params_blob.py
```

Exemplos:

```text
op_type

act

flags

in_h
in_w

cin
cout

kh
kw

stride

dilation

padding

offsets

zero points

out_h
out_w
```

---

# 173. Separação importante

`layer_params.py` constrói:

```text
representação lógica estruturada
```

Mas ainda não produz:

```text
116 bytes por camada
```

Essa responsabilidade é do próximo módulo.

---

# 174. Portanto

```text
layer_params.py
       ↓
dict Python

params_blob.py
       ↓
struct.pack()

WAT
       ↓
data segment
```

---

# 175. Offsets versus ponteiros

Outro ponto importante é que este módulo ainda mantém:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

como offsets relativos.

Por exemplo:

```text
w_off = 5000
```

significa:

```text
5000 bytes dentro de WEIGHTS
```

e não endereço absoluto.

---

# 176. Conversão posterior

`params_blob.py` fará:

```text
wptr =
WEIGHTS_BASE
+
w_off
```

Da mesma forma:

```text
bias_ptr =
BIAS_BASE
+
b_off
```

```text
mul_ptr =
MUL_BASE
+
mul_off
```

```text
shift_ptr =
SHIFT_BASE
+
shift_off
```

```text
q6_ptr =
Q6_BASE
+
q6_off
```

---

# 177. Por que não calcular tudo aqui?

Porque separar:

```text
offset relativo
```

de:

```text
ponteiro absoluto serializado
```

mantém a responsabilidade de cada módulo mais clara.

---

# 178. Slots são diferentes

Para ativações, por outro lado, o endereço físico já é conhecido através de:

```text
slot_bases
```

Por isso builders especiais podem armazenar em seus metadados:

```text
input_ptrs
```

e reutilizar endereços em campos especiais como:

```text
pad_t
```

---

# 179. Dois sistemas de endereçamento coexistem

### Parâmetros constantes

```text
tensor
 ↓
offset
 ↓
base + offset
 ↓
ponteiro
```

### Ativações

```text
tensor
 ↓
runtime slot
 ↓
slot_bases[slot]
 ↓
ponteiro
```

---

# 180. `layer_params.py` é onde eles se encontram

Uma convolução precisa simultaneamente de:

```text
ativação
    → slot

peso
    → offset

bias
    → offset

multiplier
    → offset

zero points
    → valores inteiros
```

Essa combinação acontece neste módulo.

---

# 181. Visão de uma CONV completa

```text
input tensor
    │
    ▼
runtime slot
    │
    ▼
in_slot


weight tensor
    │
    ▼
weight_tensor_off
    │
    ▼
w_off


bias tensor
    │
    ▼
bias_tensor_off
    │
    ▼
b_off


op_index
    │
    ▼
mul_q6_off
    │
    ├── mul_off
    ├── shift_off
    └── q6_off


operator options
    │
    ├── stride
    ├── dilation
    ├── padding
    └── activation


tensor quantization
    │
    ├── zx
    ├── zw
    └── zy

        ↓
    LayerParam
```

---

# 182. Visão do ADD

```text
input tensor A ──→ SLOT A ──→ pointer A ──┐
                                          │
input tensor B ──→ SLOT B ──→ pointer B ──┤
                                          ▼
                                     LayerParam ADD

scales A/B/Y
      │
      ▼
ADD quantization
      │
      ├── mul A
      ├── shift A
      ├── mul B
      ├── shift B
      ├── out mul
      └── out shift
```

---

# 183. Visão do SOFTMAX

```text
input tensor
    │
    ├── scale
    ├── zero point
    └── slot
         │
         ▼
input pointer

scale
 │
 ▼
softmax preparation
 │
 ├── input_beta_mul
 ├── input_beta_left_shift
 ├── input_left_shift
 └── diff_min

         ↓
   LayerParam SOFTMAX
```

---

# 184. Camada sintética e portabilidade

A inserção de:

```text
RGB565_TO_RGB888
```

é uma característica da integração entre o modelo e a aplicação hospedeira.

O TFLite continua descrevendo apenas sua rede.

O extrator acrescenta uma etapa de runtime necessária à forma como os dados chegam ao módulo.

---

# 185. Separação conceitual

```text
modelo neural
    ↓
operações TFLite
```

não é exatamente igual a:

```text
pipeline completo do firmware
```

O segundo inclui uma etapa adicional de pré-processamento/formatação.

---

# 186. Consequência no número de layers

Por isso:

```text
NUM_LAYERS runtime
=
número de operações reais utilizadas
+
1 camada sintética
```

---

# 187. Consequência nos slots

Também por isso existe:

```text
slot_shift
```

A camada sintética muda o ponto em que o fluxo lógico original começa dentro do conjunto físico de slots.

---

# 188. Validações explícitas deste módulo

O código falha quando encontra situações como:

```text
QUANTIZE sem input

QUANTIZE com scale_out = 0

input sem runtime slot

ADD com menos de duas entradas

ADD com input A ou B sem slot

MEAN sem input

MEAN com scale_y = 0

SOFTMAX sem input

weighted op com menos de dois inputs

operação indevida enviada ao weighted builder

output sem runtime slot
```

---

# 189. Por que essas validações são importantes?

Porque a partir daqui estamos construindo diretamente o contrato do runtime.

É melhor falhar no extrator:

```text
input tensor sem slot
```

do que gerar:

```text
LayerParam inválida
        ↓
WAT válido sintaticamente
        ↓
WASM compila
        ↓
runtime lê endereço incorreto
```

---

# 190. Limitações atuais

Algumas situações ainda possuem fallback em vez de erro.

Por exemplo:

```text
weight_tensor_off.get(..., 0)
```

pode resultar em:

```text
w_off = 0
```

se o peso não estiver no mapa.

Isso pressupõe que `weights.py` tenha funcionado corretamente para todas as operações suportadas.

---

# 191. Outra característica

`build_layer_params()` ignora silenciosamente operações úteis cujo:

```text
op_type_name
```

não esteja em:

```text
supported_operations
```

Isso preserva o comportamento atual, mas em uma ferramenta genérica futura talvez seja melhor falhar explicitamente para evitar omissão silenciosa.

---

# 192. `input_ptrs` não substitui `in_slot`

O módulo guarda ambos:

```text
in_slot
```

e:

```text
input_ptrs
```

O primeiro preserva a identidade lógica da região.

O segundo permite auditar o endereço físico que foi associado.

---

# 193. Exemplo

```text
in_slot = 2

slot_bases[2] = 900464
```

Então:

```text
input_ptrs = [900464]
```

---

# 194. No ADD

Há dois elementos:

```text
input_slots =
[
    slot_a,
    slot_b
]
```

e:

```text
input_ptrs =
[
    ptr_a,
    ptr_b
]
```

Isso torna a operação de duas entradas completamente rastreável.

---

# 195. `label` versus índice da lista

Outro detalhe importante:

```text
label = Lx
```

vem do grafo original.

Mas:

```text
layer_index
```

do relatório começa na camada sintética.

Assim:

```text
FULL LAYER DUMP
L0
```

no relatório não significa necessariamente:

```text
graph label L0
```

A primeira entrada do dump é:

```text
RGB565_TO_RGB888
```

e seu:

```text
label
```

aparece como:

```text
-
```

---

# 196. Distinção importante

Existem portanto:

```text
label do grafo
```

e:

```text
posição dentro de layer_params
```

São identidades diferentes.

---

# 197. Exemplo

```text
layer_params[0]
    → RGB565 synthetic

layer_params[1]
    → label L0

layer_params[2]
    → label L1
```

em um modelo simples.

---

# 198. Relação com `LP_SIZE`

Depois da serialização:

```text
layer_params[0]
    ↓
PARAMS_BASE + 0 × 116

layer_params[1]
    ↓
PARAMS_BASE + 1 × 116

layer_params[2]
    ↓
PARAMS_BASE + 2 × 116
```

Portanto a posição nessa lista é operacionalmente importante.

---

# 199. Responsabilidade do módulo

`layer_params.py` não gera:

```text
WAT
```

e também ainda não gera:

```text
params_blob
```

Ele produz a descrição estruturada intermediária que será consumida pela etapa seguinte.

---

# 200. O que ele deliberadamente não faz

O módulo não:

```text
concatena bytes dos pesos

gera segmentos (data ...)

escreve arquivos .wat

executa inferência

implementa kernels

compila WASM
```

---

# 201. O que ele faz

Ele responde:

```text
para cada operação do runtime,
quais parâmetros inteiros,
endereços lógicos,
offsets,
flags,
dimensões e informações
o kernel precisará?
```

---

# 202. Fluxo completo até aqui

```text
                    TFLite
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      graph          tensors        options
        │              │              │
        ▼              │              ▼
      slots            │      operator_options
        │              │
        ▼              │
 tensor mapping        │
        │              │
        └──────┐       │
               ▼       ▼
             layer_params
               ▲
               │
      ┌────────┼─────────┐
      │        │         │
   weights  quantization memory
```

---

# 203. Depois deste módulo

```text
layer_params
      │
      ▼
params_blob.py
      │
      ▼
29 × int32
por camada
      │
      ▼
data segment do WAT
```

---

# 204. Síntese arquitetural

O `layer_params.py` funciona como o **adaptador final entre o modelo e o runtime**.

Ele recebe:

```text
estrutura do modelo
+
planejamento de slots
+
endereços de memória
+
offsets dos parâmetros
+
quantização
+
opções das operações
```

e produz:

```text
uma representação uniforme
para cada camada executável
```

A grande ideia é que todas as operações utilizem a mesma estrutura de tamanho fixo:

```text
29 × int32
=
116 bytes
```

mesmo quando suas necessidades são muito diferentes.

Para operações tradicionais como:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

os campos mantêm significados próximos de seus nomes:

```text
kh/kw
stride
dilation
padding
```

Para operações especiais:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

esses mesmos campos são deliberadamente reutilizados para transportar outros parâmetros.

Assim:

```text
op_type
```

é a chave que determina como cada campo deve ser interpretado pelo runtime.

---

# 205. Mapa final das operações especiais

```text
ADD
────────────────────────────────
kh       → multiplier input A
kw       → shift input A
stride_h → multiplier input B
stride_w → shift input B
dil_h    → multiplier output
dil_w    → shift output
pad_t    → pointer input A
pad_b    → pointer input B
pad_l    → zero point A
pad_r    → zero point B


MEAN
────────────────────────────────
kh       → multiplier
kw       → shift
stride_h → in_h × in_w
pad_t    → input pointer


SOFTMAX
────────────────────────────────
kh       → input_beta_mul
kw       → input_beta_left_shift
stride_h → diff_min
stride_w → input_left_shift
pad_t    → input pointer


QUANTIZE
────────────────────────────────
flags    → uint8/int8 input
kh       → multiplier
kw       → shift
pad_t    → input pointer
zx       → zero point input
zy       → zero point output


RGB565_TO_RGB888
────────────────────────────────
in_slot  → SLOT0
out_slot → SLOT1
kh       → 65
```

Esse mapa é, na prática, parte do protocolo binário entre o extrator e os kernels implementados no WAT.

---

# 206. Visão final do pipeline

```text
TFLITE MODEL
     │
     ▼
graph.py
     │
     ▼
slots.py
     │
     ▼
tensor_mapping.py
     │
     ├─────────────────────┐
     │                     │
     ▼                     ▼
weights.py          quantization.py
     │                     │
     └──────────┬──────────┘
                │
                ▼
             memory.py
                │
                │
operator_options.py
                │
                ▼
        ┌───────────────────┐
        │  layer_params.py  │
        └───────────────────┘
                │
                ▼
        list[LayerParam]
                │
                ▼
          params_blob.py
                │
                ▼
        binary LayerParam[]
                │
                ▼
        wat_generator.py
                │
                ▼
             WASM
```

`layer_params.py` é, portanto, a etapa em que todas as decisões independentes tomadas anteriormente deixam de ser fragmentadas e passam a constituir o contrato completo de execução de cada operação.
