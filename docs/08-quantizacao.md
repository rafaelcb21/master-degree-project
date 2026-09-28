# 08 — Extração e preparação dos parâmetros de quantização (`quantization.py`)

## 1. Objetivo do módulo

O arquivo `extractor/quantization.py` transforma os metadados de quantização armazenados no modelo TFLite em parâmetros inteiros que poderão ser utilizados diretamente pelos kernels implementados em WebAssembly.

Até esta etapa, o modelo fornece informações como:

```text
scale
zero_point
quantized_dimension
```

Porém, o runtime não realiza diretamente operações em ponto flutuante para converter cada acumulador de uma camada.

Em vez disso, o extrator prepara estruturas como:

```text
multiplier
shift
Q6
```

que serão utilizadas posteriormente pelos kernels quantizados.

O fluxo conceitual é:

```text
TFLite

scale de entrada
scale dos pesos
scale de saída
zero point
        │
        ▼
quantization.py
        │
        ├── real_multiplier
        │
        ├── multiplier Q31
        │
        ├── shift
        │
        └── Q6
        │
        ▼
tabelas int32
        │
        ├── mul_blob
        ├── shift_blob
        └── q6_blob
        │
        ▼
memória WASM
```

---

# 2. Código e responsabilidades principais

O módulo possui quatro grandes responsabilidades:

```text
quantize_multiplier()
        ↓
converter multiplicador real
para representação inteira

extract_quantization_parameters()
        ↓
extrair parâmetros das operações

compute_add_quantization_params()
        ↓
calcular parâmetros específicos do ADD

quantization_to_text()
        ↓
gerar relatório
```

---

# 3. Importações

O arquivo começa com:

```python
import math
import numpy as np
```

e:

```python
from extractor.tflite_utils import (
    op_name,
    qparams_np,
    scale_scalar,
    tensor_shape_list,
    zp_scalar,
)
```

Cada helper possui uma função específica.

---

# 4. `op_name()`

É utilizado para descobrir se o operador atual é:

```text
SOFTMAX
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

ou outro tipo que não deve ser tratado por esta rotina.

---

# 5. `qparams_np()`

Retorna a quantização completa de um tensor:

```python
{
    "scales": ...,
    "zps": ...,
    "qdim": ...,
}
```

Isso é particularmente importante para pesos quantizados por canal.

---

# 6. `scale_scalar()`

Obtém uma única escala.

É utilizado, por exemplo, no tratamento específico do `SOFTMAX`.

---

# 7. `zp_scalar()`

Obtém um único zero point.

É utilizado principalmente para calcular o valor quantizado correspondente ao limite superior do `ReLU6`.

---

# 8. `tensor_shape_list()`

Transforma o shape do tensor em uma lista Python.

Neste módulo é utilizado para descobrir quantos canais ou features precisam de parâmetros de requantização.

---

# 9. Limites `INT32`

O módulo define:

```python
INT32_MIN = -(1 << 31)
INT32_MAX = (1 << 31) - 1
```

O que corresponde a:

```text
INT32_MIN = -2147483648

INT32_MAX =  2147483647
```

Esses são os limites de um inteiro assinado de 32 bits.

---

# 10. Por que esses limites aparecem aqui?

O multiplicador quantizado é armazenado em uma representação inteira de 32 bits.

Portanto, depois de calculado, o valor precisa permanecer no intervalo:

```text
-2³¹
até
2³¹ - 1
```

---

# 11. Operadores com pesos quantizados

O conjunto:

```python
QUANTIZED_WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}
```

identifica as operações cuja requantização depende simultaneamente de:

```text
scale da entrada
scale dos pesos
scale da saída
```

---

# 12. Relação básica da requantização

Uma operação quantizada normalmente calcula um acumulador inteiro.

De forma simplificada:

```text
input quantizado
      ×
peso quantizado
      ↓
acumulador int32
```

Mas esse acumulador está associado a uma escala diferente da escala desejada para a saída.

Por isso é necessário um fator de conversão.

Conceitualmente:

```text
real_multiplier =
input_scale × weight_scale
──────────────────────────
       output_scale
```

Esse fator aparece diretamente no código das operações com pesos.

---

# 13. Por que não usar `float` diretamente no kernel?

Seria possível conceitualmente fazer:

```text
accumulator × real_multiplier
```

utilizando ponto flutuante.

Mas o runtime desenvolvido trabalha com requantização inteira.

Assim:

```text
real_multiplier
```

é convertido em:

```text
multiplier inteiro
+
shift
```

---

# 14. Função `quantize_multiplier()`

A função central é:

```python
def quantize_multiplier(
    real_multiplier: float,
):
```

Ela recebe um número real e retorna:

```python
(
    q31,
    exponent,
)
```

que no restante do projeto são interpretados como:

```text
multiplier
shift
```

---

# 15. Entrada da função

Primeiro:

```python
rm = float(
    real_multiplier
)
```

A entrada é explicitamente convertida para `float`.

Isso evita carregar tipos NumPy específicos para o restante da função.

---

# 16. Caso zero

Se:

```python
rm == 0.0
```

o retorno é:

```python
return 0, 0
```

Porque:

```text
multiplicador real = 0
```

pode ser representado diretamente por:

```text
multiplier = 0
shift = 0
```

---

# 17. Decomposição com `frexp()`

Para valores diferentes de zero:

```python
q, exponent = math.frexp(
    rm
)
```

A função `frexp()` decompõe o número aproximadamente na forma:

```text
rm = q × 2^exponent
```

---

# 18. Propriedade de `q`

Para números positivos normais, `q` fica normalmente no intervalo:

```text
0,5 ≤ q < 1
```

Assim, o valor real é separado em:

```text
parte fracionária normalizada
+
potência de dois
```

---

# 19. Exemplo com `0.75`

Para:

```text
real_multiplier = 0.75
```

podemos ter:

```text
q = 0.75
exponent = 0
```

porque:

```text
0.75 =
0.75 × 2⁰
```

---

# 20. Exemplo com `0.375`

Para:

```text
real_multiplier = 0.375
```

podemos representar:

```text
0.375 =
0.75 × 2⁻¹
```

Então:

```text
q = 0.75
exponent = -1
```

---

# 21. Exemplo com `1.5`

Da mesma forma:

```text
1.5 =
0.75 × 2¹
```

Então:

```text
q = 0.75
exponent = 1
```

---

# 22. Conversão para Q31

Depois:

```python
q31 = int(
    round(
        q * (1 << 31)
    )
)
```

O valor:

```text
1 << 31
```

corresponde a:

```text
2³¹
```

Assim, `q` é representado em uma escala inteira de aproximadamente 31 bits fracionários.

---

# 23. Exemplo

Para:

```text
q = 0.75
```

temos:

```text
q31 ≈
0.75 × 2147483648
```

resultando em:

```text
1610612736
```

Portanto:

```text
0.75
```

pode ser representado aproximadamente por:

```text
multiplier = 1610612736
shift = 0
```

---

# 24. Mesmo multiplier, shifts diferentes

Os exemplos:

```text
0.375
0.75
1.5
```

podem compartilhar o mesmo `q31`:

```text
1610612736
```

mas usar shifts diferentes:

```text
0.375 → shift -1
0.75  → shift  0
1.5   → shift +1
```

É o par:

```text
(multiplier, shift)
```

que representa o fator completo.

---

# 25. Convenção de shift do projeto

No runtime atual:

```text
shift > 0
    ↓
left shift

shift < 0
    ↓
right shift
```

Assim, o expoente retornado por `frexp()` é preservado como parte da representação da requantização.

---

# 26. Caso limite de arredondamento

Depois do arredondamento existe:

```python
if q31 == (1 << 31):
    q31 //= 2
    exponent += 1
```

Isso trata o caso em que o arredondamento produz exatamente:

```text
2³¹
```

que ultrapassaria o maior `int32` positivo.

---

# 27. Por que dividir por dois?

Se:

```text
q31
```

é reduzido pela metade, podemos compensar aumentando o expoente em 1.

Conceitualmente:

```text
q × 2^e

é equivalente a

(q/2) × 2^(e+1)
```

Assim o valor representado permanece equivalente.

---

# 28. Saturação de segurança

Depois:

```python
if q31 > INT32_MAX:
    q31 = INT32_MAX
```

e:

```python
if q31 < INT32_MIN:
    q31 = INT32_MIN
```

garantem que o resultado permaneça representável em 32 bits.

---

# 29. Retorno

Finalmente:

```python
return (
    int(q31),
    int(exponent),
)
```

Ou seja:

```text
real_multiplier
      ↓
quantize_multiplier()
      ↓
multiplier int32
+
shift
```

---

# 30. Função `extract_quantization_parameters()`

A função principal da etapa é:

```python
def extract_quantization_parameters(
    model,
    subgraph,
):
```

Ela percorre os operadores do modelo e constrói três tabelas:

```text
MUL
SHIFT
Q6
```

---

# 31. Estruturas inicialmente vazias

São criadas:

```python
mul_vals = []
shift_vals = []
q6_vals = []
```

Essas listas armazenam valores inteiros.

Depois serão convertidas em blobs binários.

---

# 32. Mapeamento de offsets

Também é criado:

```python
mul_q6_off = {}
```

Ele associa:

```text
op_index
    ↓
offset da tabela MUL
offset da tabela SHIFT
offset da tabela Q6
quantidade de features
```

---

# 33. Formato de `mul_q6_off`

Para uma operação poderemos ter:

```python
mul_q6_off[15] = (
    128,
    128,
    128,
    32,
)
```

representando:

```text
op 15

mul_offset   = 128
shift_offset = 128
q6_offset    = 128
nfeat        = 32
```

---

# 34. Offsets em bytes

Esses offsets são medidos em bytes.

Isso ocorre porque cada valor será serializado como:

```text
int32
```

portanto:

```text
4 bytes
```

---

# 35. Cálculo do offset

O código utiliza:

```python
mul_offset = (
    len(mul_vals) * 4
)
```

Se já existem:

```text
10 multipliers
```

então:

```text
offset =
10 × 4
=
40 bytes
```

---

# 36. Mesma lógica para SHIFT e Q6

```python
shift_offset = (
    len(shift_vals) * 4
)
```

e:

```python
q6_offset = (
    len(q6_vals) * 4
)
```

---

# 37. `records`

Também é criada:

```python
records = []
```

Ela contém informações detalhadas para relatório.

Assim como em `weights.py`, existe uma separação entre:

```text
dados usados pelo runtime
```

e:

```text
metadados usados para análise
```

---

# 38. Varredura dos operadores

O módulo percorre:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

e identifica:

```python
op_type = op_name(
    model,
    op,
)
```

---

# 39. Dois caminhos principais

Depois disso existem dois tratamentos.

```text
SOFTMAX
```

possui lógica própria.

Já:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

compartilham a lógica principal de quantização por peso.

---

# 40. Tratamento do `SOFTMAX`

O primeiro caso especial é:

```python
if op_type == "SOFTMAX":
```

O `SOFTMAX` não possui um tensor de pesos como uma convolução.

Logo não faz sentido utilizar:

```text
input_scale × weight_scale / output_scale
```

A preparação é diferente.

---

# 41. Inputs do `SOFTMAX`

São coletados:

```python
input_ids = [
    int(tensor_id)
    for tensor_id
    in op.InputsAsNumpy()
    if int(tensor_id) >= 0
]
```

É necessário pelo menos:

```text
1 input
```

Caso contrário:

```python
continue
```

---

# 42. Tensor de entrada

A entrada principal é:

```python
input_tensor = (
    subgraph.Tensors(
        input_ids[0]
    )
)
```

---

# 43. Scale da entrada

Depois:

```python
input_scale = scale_scalar(
    input_tensor
)
```

Assim o `SOFTMAX` conhece a escala dos valores quantizados recebidos.

---

# 44. `beta`

O código atual define:

```python
beta = 1.0
```

Esse é o valor utilizado pelo runtime implementado.

---

# 45. `integer_bits`

Também é definido:

```python
integer_bits = 5
```

Esse valor participa do cálculo de:

```text
input_left_shift
```

---

# 46. `input_left_shift`

O cálculo é:

```python
input_left_shift = max(
    0,
    (
        integer_bits
        - floor(log2(
            127.0 * input_scale
            + 1e-9
        ))
        - 1
    ),
)
```

---

# 47. Papel do `input_left_shift`

Esse valor determina quanto o `diff` utilizado internamente pelo `SOFTMAX` poderá ser deslocado à esquerda antes da multiplicação.

No runtime atual esse valor é preservado separadamente dos parâmetros:

```text
input_beta_mul
input_beta_left_shift
```

---

# 48. O termo `127 × input_scale`

Para um tensor `int8`, a magnitude positiva aproximadamente máxima é:

```text
127
```

Multiplicar por:

```text
input_scale
```

produz uma estimativa da magnitude real máxima representável.

---

# 49. Uso de `log2`

O código utiliza:

```python
math.log2(
    127.0 * input_scale
    + 1e-9
)
```

para estimar quantos bits são necessários para representar essa magnitude.

---

# 50. Papel de `1e-9`

O pequeno valor:

```text
0.000000001
```

evita problemas numéricos com:

```text
log2(0)
```

ou valores extremamente próximos de zero.

---

# 51. Limite inferior zero

O uso de:

```python
max(
    0,
    ...
)
```

garante que:

```text
input_left_shift
```

não seja negativo.

---

# 52. `real_multiplier` do SOFTMAX

Depois:

```python
real_multiplier = (
    beta * input_scale
)
```

Com:

```text
beta = 1
```

isso se reduz a:

```text
real_multiplier =
input_scale
```

---

# 53. Conversão para inteiro

Esse fator é passado para:

```python
quantize_multiplier(
    real_multiplier
)
```

produzindo:

```text
multiplier
shift
```

---

# 54. Importante sobre o `SOFTMAX`

O módulo preserva duas informações relacionadas a deslocamento:

```text
input_left_shift
```

e:

```text
shift
```

retornado por `quantize_multiplier()`.

Eles não são a mesma variável.

---

# 55. Mapeamento posterior

No `LayerParam` utilizado pelo runtime, a implementação atual armazena:

```text
kh       = multiplier
kw       = shift
stride_h = diff_min
stride_w = input_left_shift
```

Portanto:

```text
kw
```

e:

```text
stride_w
```

representam informações diferentes no `SOFTMAX`.

---

# 56. Registro nas tabelas

O `SOFTMAX` adiciona apenas um valor em:

```python
mul_vals
```

e:

```python
shift_vals
```

porque:

```text
nfeat = 1
```

para esse registro de parâmetros.

---

# 57. Offsets do SOFTMAX

Antes da inserção:

```python
mul_offset = (
    len(mul_vals) * 4
)
```

e:

```python
shift_offset = (
    len(shift_vals) * 4
)
```

são calculados.

Depois:

```python
mul_vals.append(
    multiplier
)
```

e:

```python
shift_vals.append(
    shift
)
```

---

# 58. Entrada em `mul_q6_off`

O código registra:

```python
mul_q6_off[
    op_idx
] = (
    mul_offset,
    shift_offset,
    0,
    1,
)
```

Ou seja:

```text
mul offset
shift offset
q6 offset = 0
nfeat = 1
```

O `SOFTMAX` não gera uma tabela Q6.

---

# 59. Registro do SOFTMAX

O relatório preserva:

```text
input_tensor_id
input_scale
beta
integer_bits
input_left_shift
real_multiplier
multiplier
shift
offsets
```

Isso permite reconstruir exatamente os valores usados.

---

# 60. Fim do caso SOFTMAX

Depois:

```python
continue
```

impede que o operador caia no tratamento destinado a convoluções e fully connected.

---

# 61. Filtragem das operações com pesos

Depois do caso `SOFTMAX`:

```python
if (
    op_type
    not in QUANTIZED_WEIGHT_OPERATORS
):
    continue
```

Assim, apenas:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

continuam.

---

# 62. Inputs e outputs

São coletados:

```python
input_ids
```

e:

```python
output_ids
```

filtrando IDs negativos.

---

# 63. Estrutura mínima

A operação precisa possuir:

```text
pelo menos 2 inputs
pelo menos 1 output
```

Caso contrário:

```python
continue
```

---

# 64. Tensors principais

O código identifica:

```text
input_ids[0]
    ↓
ativação de entrada
```

```text
input_ids[1]
    ↓
pesos
```

```text
output_ids[0]
    ↓
ativação de saída
```

---

# 65. Objetos TFLite

São recuperados:

```python
input_tensor
weight_tensor
output_tensor
```

Esses três tensors fornecem as escalas necessárias para calcular a requantização.

---

# 66. Shape dos pesos

O código obtém:

```python
weight_shape = tensor_shape_list(
    weight_tensor
)
```

Esse shape é utilizado para determinar:

```text
nfeat
```

---

# 67. O que é `nfeat`?

Neste módulo, `nfeat` representa quantos conjuntos de:

```text
multiplier
shift
Q6
```

devem existir para aquela operação.

Normalmente corresponde ao número de canais/features de saída.

---

# 68. `nfeat` em `CONV_2D`

Para:

```text
CONV_2D
```

é utilizado:

```python
weight_shape[0]
```

Logo:

```text
shape dos pesos
[O, H, W, I]
```

produz:

```text
nfeat = O
```

onde `O` é o número de canais de saída.

---

# 69. Exemplo

Pesos:

```text
[32, 3, 3, 3]
```

Então:

```text
nfeat = 32
```

Serão preparados:

```text
32 multipliers
32 shifts
32 valores Q6
```

---

# 70. `nfeat` em `DEPTHWISE_CONV_2D`

Para depthwise:

```python
weight_shape[3]
```

é utilizado.

Assim, para o layout esperado pelo modelo:

```text
nfeat =
última dimensão dos pesos
```

---

# 71. Exemplo

Shape:

```text
[1, 3, 3, 32]
```

resulta em:

```text
nfeat = 32
```

---

# 72. `nfeat` em `FULLY_CONNECTED`

No terceiro caso:

```python
weight_shape[0]
```

é utilizado novamente.

Para uma matriz:

```text
[1000, 1280]
```

teríamos:

```text
nfeat = 1000
```

---

# 73. Shape inválido

Se não for possível determinar:

```text
nfeat
```

a função executa:

```python
continue
```

---

# 74. Leitura completa da quantização

Depois:

```python
q_input = qparams_np(
    input_tensor
)
```

```python
q_weights = qparams_np(
    weight_tensor
)
```

```python
q_output = qparams_np(
    output_tensor
)
```

---

# 75. Requisito de quantização

Se qualquer uma retornar:

```text
None
```

a operação é ignorada nesta etapa.

O mesmo ocorre se algum vetor de scales estiver vazio.

---

# 76. `input_scale`

Para a entrada:

```python
input_scale = float(
    q_input["scales"][0]
)
```

O código utiliza uma única escala de entrada.

---

# 77. `weight_scales`

Já os pesos são mantidos como vetor:

```python
weight_scales = (
    q_weights["scales"]
    .astype(np.float64)
)
```

Isso permite suportar:

```text
per-tensor
```

ou:

```text
per-channel
```

---

# 78. `output_scales`

A saída também é preservada inicialmente como vetor:

```python
output_scales = (
    q_output["scales"]
    .astype(np.float64)
)
```

---

# 79. `output_scale`

Para o cálculo principal dos multipliers:

```python
output_scale = float(
    output_scales[0]
)
```

Portanto, o denominador utilizado no cálculo principal é a primeira escala da saída.

---

# 80. Início dos offsets

Antes de inserir os valores da operação:

```text
mul_offset
shift_offset
q6_offset
```

são calculados com base no comprimento atual das tabelas.

Isso registra onde os dados daquela operação começarão.

---

# 81. Listas locais da operação

São criadas:

```python
operation_multipliers = []
operation_shifts = []
real_multipliers = []
```

Essas listas contêm apenas os dados da operação atual.

Depois serão adicionadas às tabelas globais.

---

# 82. Caso de uma única `weight_scale`

Se:

```python
weight_scales.size == 1
```

a quantização dos pesos é tratada como per-tensor.

---

# 83. Fórmula do multiplicador real

É calculado:

```text
real_multiplier =

weight_scale
×
input_scale
────────────
output_scale
```

No código:

```python
real_multiplier = (
    weight_scales[0]
    * input_scale
    / output_scale
)
```

---

# 84. Origem matemática

A entrada quantizada representa aproximadamente:

```text
real_x =
Sx × (qx - Zx)
```

O peso:

```text
real_w =
Sw × (qw - Zw)
```

O produto possui escala:

```text
Sx × Sw
```

Mas a saída deve possuir escala:

```text
Sy
```

Portanto é necessário converter:

```text
Sx × Sw
```

para:

```text
Sy
```

utilizando:

```text
Sx × Sw
───────
   Sy
```

---

# 85. Conversão em multiplier + shift

Esse valor é passado para:

```python
quantize_multiplier(
    real_multiplier
)
```

produzindo:

```text
multiplier
shift
```

---

# 86. Replicação por feature

Como existe apenas uma escala de peso:

```python
operation_multipliers = [
    multiplier
] * nfeat
```

e:

```python
operation_shifts = [
    shift
] * nfeat
```

---

# 87. Exemplo

Se:

```text
nfeat = 32
```

e:

```text
multiplier = 1234567890
shift = -2
```

serão armazenados:

```text
32 cópias do multiplier
32 cópias do shift
```

---

# 88. Por que replicar?

O runtime pode acessar os parâmetros utilizando o índice do canal.

Manter:

```text
um valor por feature
```

simplifica o kernel, mesmo quando todos os canais compartilham o mesmo valor.

---

# 89. `real_multipliers`

A mesma replicação é feita para:

```python
real_multipliers
```

mas esses valores são utilizados principalmente no relatório.

Eles não formam um blob usado pelo runtime.

---

# 90. Caso per-channel

Se:

```python
weight_scales.size > 1
```

cada canal pode possuir uma escala diferente.

---

# 91. Número de escalas utilizadas

O código calcula:

```python
use = min(
    nfeat,
    weight_scales.size,
)
```

Isso impede acessar posições inexistentes.

---

# 92. Multiplicadores reais vetoriais

São calculados:

```python
rm_values = (
    weight_scales[:use]
    * input_scale
    / output_scale
)
```

Agora cada canal pode possuir um:

```text
real_multiplier diferente
```

---

# 93. Exemplo

Suponha:

```text
input_scale = 0.02
output_scale = 0.04

weight_scales =
[
    0.10,
    0.20,
    0.30
]
```

Então:

```text
canal 0:
0.10 × 0.02 / 0.04
= 0.05

canal 1:
0.20 × 0.02 / 0.04
= 0.10

canal 2:
0.30 × 0.02 / 0.04
= 0.15
```

---

# 94. Conversão canal por canal

O loop:

```python
for rm in rm_values:
```

executa:

```python
quantize_multiplier(
    rm
)
```

individualmente.

---

# 95. Resultado

Serão formadas listas como:

```text
multipliers:
[M0, M1, M2, ...]

shifts:
[S0, S1, S2, ...]
```

---

# 96. Padding quando faltam escalas

Se:

```python
nfeat > use
```

o código calcula:

```python
missing = (
    nfeat - use
)
```

e replica o último parâmetro calculado.

---

# 97. Exemplo

Se:

```text
nfeat = 32
```

mas foram encontradas:

```text
30 weight_scales
```

o código utiliza:

```text
canal 29
```

como referência para preencher os dois últimos.

---

# 98. Multipliers

```python
operation_multipliers.extend(
    [
        operation_multipliers[-1]
    ] * missing
)
```

---

# 99. Shifts

O mesmo é feito para:

```python
operation_shifts
```

---

# 100. Multiplicadores reais

E também para:

```python
real_multipliers
```

para manter as listas com o mesmo tamanho.

---

# 101. Observação sobre o legado

O próprio código registra que o arquivo antigo possuía esse bloco de preenchimento duplicado.

Na versão modularizada ele existe apenas uma vez.

Assim preservamos a intenção do código sem repetir desnecessariamente a mesma operação.

---

# 102. Inserção nas tabelas globais

Depois de calculados:

```python
mul_vals.extend(
    operation_multipliers
)
```

e:

```python
shift_vals.extend(
    operation_shifts
)
```

---

# 103. Estrutura da tabela MUL

Depois de várias operações:

```text
MUL

op 0:
[M0 M1 M2 ...]

op 1:
[M0 M1 M2 ...]

op 2:
[M0 M1 M2 ...]
```

Todos ficam concatenados em uma única tabela.

---

# 104. Estrutura da tabela SHIFT

Da mesma maneira:

```text
SHIFT

op 0:
[S0 S1 S2 ...]

op 1:
[S0 S1 S2 ...]

op 2:
[S0 S1 S2 ...]
```

Os offsets indicam onde começa cada grupo.

---

# 105. Cálculo de Q6

Depois dos multiplicadores vem o cálculo:

```text
Q6
```

---

# 106. O que representa Q6?

`Q6` representa a forma quantizada do valor real:

```text
6.0
```

na escala da saída da operação.

Esse valor é utilizado para implementar a saturação correspondente a:

```text
ReLU6
```

---

# 107. Quantização de um valor real

A relação básica é:

```text
q =
round(
    real / scale
)
+
zero_point
```

Para:

```text
real = 6
```

obtemos:

```text
q6 =
round(
    6 / output_scale
)
+
output_zero_point
```

Essa é exatamente a fórmula utilizada pelo código.

---

# 108. Zero point da saída

Primeiro:

```python
output_zero_point = zp_scalar(
    output_tensor
)
```

---

# 109. Output com uma única escala

Se:

```python
output_scales.size == 1
```

é calculado:

```python
q6 = (
    round(
        6.0
        / output_scales[0]
    )
    + output_zero_point
)
```

---

# 110. Exemplo

Suponha:

```text
output_scale = 0.05
output_zero_point = -128
```

Então:

```text
6 / 0.05
=
120
```

Logo:

```text
q6 =
120 - 128
=
-8
```

Portanto:

```text
valor quantizado -8
```

representa aproximadamente o valor real:

```text
6
```

para aquela quantização.

---

# 111. Replicação do Q6

Se a operação possui:

```text
nfeat = 32
```

então:

```python
operation_q6 = [
    q6
] * nfeat
```

---

# 112. Por que uma tabela por feature?

Novamente, o runtime pode indexar diretamente:

```text
q6[channel]
```

independentemente de a escala ser realmente única ou por canal.

---

# 113. Output com múltiplas escalas

Se:

```python
output_scales.size > 1
```

o código calcula um Q6 para cada escala disponível.

---

# 114. Quantização vetorizada

```python
q6_values = (
    np.round(
        6.0
        / output_scales[:use]
    )
    .astype(np.int64)
    + output_zero_point
)
```

---

# 115. Conversão para inteiros Python

Os valores são adicionados com:

```python
operation_q6.extend(
    int(value)
    for value
    in q6_values
)
```

---

# 116. Padding de Q6

Se houver menos escalas que `nfeat`, o último valor é repetido.

Assim:

```text
len(operation_q6)
```

termina igual a:

```text
nfeat
```

---

# 117. Inserção na tabela global

Depois:

```python
q6_vals.extend(
    operation_q6
)
```

---

# 118. Organização conjunta das três tabelas

Para uma determinada operação, idealmente existem:

```text
nfeat multipliers
nfeat shifts
nfeat Q6
```

Então, para canal `c`:

```text
multiplier[c]
shift[c]
q6[c]
```

formam o conjunto utilizado naquele canal de saída.

---

# 119. Registro dos offsets

Depois:

```python
mul_q6_off[
    op_idx
] = (
    mul_offset,
    shift_offset,
    q6_offset,
    nfeat,
)
```

Esse é um dos resultados mais importantes da função.

---

# 120. Exemplo

Suponha:

```python
mul_q6_off[12] = (
    256,
    256,
    256,
    32,
)
```

Então a operação 12 possui:

```text
multipliers começando em MUL + 256

shifts começando em SHIFT + 256

Q6 começando em Q6_BASE + 256

32 features
```

---

# 121. Offset novamente não é endereço absoluto

Assim como em `weights.py`:

```text
256
```

não é o endereço final na memória WASM.

Posteriormente:

```text
mul_ptr =
MUL_BASE + mul_offset
```

---

# 122. Exemplo

Se:

```text
MUL_BASE = 414832
mul_offset = 256
```

então:

```text
mul_ptr =
415088
```

---

# 123. Mesmo princípio para SHIFT

```text
shift_ptr =
SHIFT_BASE
+
shift_offset
```

---

# 124. E para Q6

```text
q6_ptr =
Q6_BASE
+
q6_offset
```

quando a operação efetivamente utilizar ReLU6.

---

# 125. Registros para relatório

Para cada operação é armazenado um dicionário contendo:

```text
op_index
op_type
input_tensor_id
weight_tensor_id
output_tensor_id
nfeat

input_scale
weight_scales
output_scales
output_zero_point

real_multipliers
multipliers
shifts
q6

offsets
quantized_dimension
```

---

# 126. Por que armazenar `real_multipliers`?

Eles permitem comparar:

```text
valor matemático desejado
```

contra:

```text
representação inteira gerada
```

Isso é muito útil para depuração da requantização.

---

# 127. `weight_quantized_dimension`

O relatório também registra:

```python
q_weights["qdim"]
```

Isso informa qual dimensão do tensor de pesos está associada à quantização por canal.

---

# 128. `output_quantized_dimension`

Da mesma forma:

```python
q_output["qdim"]
```

é preservado.

Mesmo que o cálculo atual utilize principalmente:

```text
output_scales[0]
```

essa informação continua disponível para análise.

---

# 129. Final da varredura

Depois que todos os operadores foram processados, temos três listas Python:

```text
mul_vals
shift_vals
q6_vals
```

Mas o runtime precisa de bytes.

---

# 130. Serialização de `mul_blob`

O código usa:

```python
mul_blob = np.array(
    mul_vals,
    dtype="<i4",
).tobytes()
```

---

# 131. Significado de `<i4`

A especificação:

```text
<
```

significa:

```text
little-endian
```

e:

```text
i4
```

significa:

```text
inteiro assinado de 4 bytes
```

ou seja:

```text
int32
```

---

# 132. Portanto

Cada multiplier ocupa exatamente:

```text
4 bytes
```

no blob.

---

# 133. `shift_blob`

É construído da mesma forma:

```python
shift_blob = np.array(
    shift_vals,
    dtype="<i4",
).tobytes()
```

---

# 134. `q6_blob`

E:

```python
q6_blob = np.array(
    q6_vals,
    dtype="<i4",
).tobytes()
```

---

# 135. Por que serializar como `int32`?

O runtime WebAssembly utiliza operações inteiras e lê esses parâmetros como valores de 32 bits.

Além disso, os offsets foram calculados assumindo:

```text
4 bytes por entrada
```

Logo existe uma relação direta:

```text
len(lista) × 4
=
len(blob)
```

---

# 136. Exemplo

Se:

```text
mul_vals possui 7044 valores
```

então:

```text
mul_blob =
7044 × 4
=
28176 bytes
```

---

# 137. Estrutura binária

Conceitualmente:

```text
mul_blob

[M0 4 bytes]
[M1 4 bytes]
[M2 4 bytes]
...
```

O mesmo vale para `shift_blob` e `q6_blob`.

---

# 138. Retorno da extração

A função retorna:

```python
{
    "mul_vals": ...,
    "shift_vals": ...,
    "q6_vals": ...,

    "mul_blob": ...,
    "shift_blob": ...,
    "q6_blob": ...,

    "mul_q6_off": ...,

    "records": ...,
}
```

---

# 139. Valores versus blobs

Existe uma duplicação deliberada de representação.

```text
mul_vals
```

é conveniente para:

```text
cálculo
debug
relatório
```

Enquanto:

```text
mul_blob
```

é conveniente para:

```text
serialização
WAT
memória WASM
```

---

# 140. O mesmo vale para SHIFT e Q6

```text
shift_vals
    ↓
forma estruturada

shift_blob
    ↓
forma binária
```

e:

```text
q6_vals
    ↓
forma estruturada

q6_blob
    ↓
forma binária
```

---

# 141. Função `compute_add_quantization_params()`

O `ADD` não é tratado dentro das tabelas principais da mesma maneira que uma convolução.

Ele possui uma função própria:

```python
def compute_add_quantization_params(
    scale_a,
    scale_b,
    scale_y,
):
```

---

# 142. Por que o `ADD` é diferente?

O `ADD` combina duas ativações possivelmente com escalas diferentes:

```text
A
+
B
```

Se:

```text
A usa scale_a
```

e:

```text
B usa scale_b
```

os dois valores precisam ser colocados em uma escala compatível antes da soma.

---

# 143. Entradas

A função recebe:

```text
scale_a
scale_b
scale_y
```

onde:

```text
scale_a = escala da primeira entrada

scale_b = escala da segunda entrada

scale_y = escala da saída
```

---

# 144. Escala comum

Primeiro:

```python
scale_common = max(
    scale_a,
    scale_b,
) * 2.0
```

Assim é criada uma escala intermediária comum.

---

# 145. Exemplo

Se:

```text
scale_a = 0.02

scale_b = 0.03
```

então:

```text
max = 0.03
```

e:

```text
scale_common =
0.03 × 2
=
0.06
```

---

# 146. Casos degenerados

A função verifica vários casos com escala zero.

Se:

```text
scale_a == 0
e
scale_b == 0
```

retorna multiplicadores e shifts zero.

---

# 147. Saída com escala zero

Da mesma maneira:

```python
if scale_y == 0.0:
```

retorna zeros.

---

# 148. Escala comum zero

Existe também:

```python
if scale_common == 0.0:
```

como proteção.

---

# 149. Razão da entrada A

Em um caso normal:

```python
ratio_a = (
    scale_a
    / scale_common
)
```

---

# 150. Conversão da entrada A

Depois:

```python
mul_a, shift_a = (
    quantize_multiplier(
        ratio_a
    )
)
```

---

# 151. Entrada B

Da mesma forma:

```text
ratio_b =
scale_b / scale_common
```

e:

```text
mul_b
shift_b
```

---

# 152. Conversão da soma para a saída

Depois que A e B são representados na escala comum, a saída precisa ser convertida para:

```text
scale_y
```

Por isso:

```python
output_ratio = (
    scale_common
    / scale_y
)
```

---

# 153. Parâmetros da saída

```python
output_mul,
output_shift
=
quantize_multiplier(
    output_ratio
)
```

---

# 154. Retorno do ADD

A função retorna sete valores:

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

# 155. Fluxo conceitual do ADD

```text
A quantizado
   │
   └─ scale_a
        │
        ▼
  mul_a / shift_a
        │
        ▼
    escala comum
        │
        │
        ├────────┐
        │        │
        ▼        ▼
       A'   +   B'
            │
            ▼
          soma
            │
            ▼
output_mul / output_shift
            │
            ▼
       scale_y
```

---

# 156. Onde os parâmetros do ADD são armazenados?

Diferentemente das convoluções, os parâmetros do ADD são posteriormente colocados diretamente em campos reutilizados da `LayerParam`.

No runtime atual:

```text
kh       = mul0
kw       = shift0

stride_h = mul1
stride_w = shift1

dil_h    = out_mul
dil_w    = out_shift
```

Portanto o ADD não precisa necessariamente criar entradas nas tabelas globais MUL/SHIFT desta função.

---

# 157. Por que isso é possível?

A quantidade de parâmetros do ADD é fixa:

```text
3 multipliers
3 shifts
```

Já uma convolução pode possuir:

```text
32
64
96
160
...
```

multipliers por canal.

Por isso a convolução utiliza tabelas externas enquanto o ADD pode armazenar seus parâmetros diretamente na estrutura da camada.

---

# 158. Relação com `layer_params.py`

Posteriormente:

```text
quantization.py
     │
     ├── mul_q6_off
     │
     └── compute_add_quantization_params()
     │
     ▼
layer_params.py
```

O primeiro é utilizado por:

```text
CONV
DEPTHWISE
FC
SOFTMAX
```

enquanto a função específica é utilizada pelo:

```text
ADD
```

---

# 159. Função `quantization_to_text()`

A última função transforma:

```python
extraction
```

em relatório detalhado.

Ela não participa dos cálculos.

---

# 160. Relatório por operação

Para cada entrada em:

```python
extraction["records"]
```

o relatório começa com:

```text
================================================================================
OP_INDEX: ...
TIPO: ...
NFEAT: ...
```

---

# 161. `INPUT_SCALE`

Todas as operações registram:

```text
INPUT_SCALE
```

porque esse valor participa diretamente da requantização.

---

# 162. Relatório do `SOFTMAX`

Quando:

```text
TIPO = SOFTMAX
```

também são mostrados:

```text
BETA
INTEGER_BITS
INPUT_LEFT_SHIFT
REAL_MULTIPLIER
```

---

# 163. Relatório das operações com peso

Para:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

são mostrados:

```text
WEIGHT_SCALES
OUTPUT_SCALES
OUTPUT_ZERO_POINT
REAL_MULTIPLIERS
```

---

# 164. Parâmetros inteiros

Depois, independentemente do tipo registrado, o relatório mostra:

```text
MULTIPLIERS
SHIFTS
Q6
```

---

# 165. Offsets

Também são apresentados:

```text
MUL
SHIFT
Q6
```

como offsets em bytes.

---

# 166. Exemplo conceitual

```text
OP_INDEX: 12
TIPO: CONV_2D
NFEAT: 32

INPUT_SCALE: 0.023...

WEIGHT_SCALES:
[...]

OUTPUT_SCALES:
[...]

OUTPUT_ZERO_POINT: -128

REAL_MULTIPLIERS:
[...]

MULTIPLIERS:
[...]

SHIFTS:
[...]

Q6:
[...]

OFFSETS:
  MUL   = 128
  SHIFT = 128
  Q6    = 128
```

---

# 167. Resumo final

O relatório termina com:

```text
Quantidade de multipliers
Quantidade de shifts
Quantidade de Q6

mul_blob em bytes
shift_blob em bytes
q6_blob em bytes
```

---

# 168. Relação entre quantidade e tamanho

Como cada valor possui:

```text
4 bytes
```

deve existir:

```text
len(mul_blob)
=
len(mul_vals) × 4
```

Da mesma maneira:

```text
len(shift_blob)
=
len(shift_vals) × 4
```

e:

```text
len(q6_blob)
=
len(q6_vals) × 4
```

---

# 169. Essa é uma propriedade útil para validação

Por exemplo:

```text
multipliers = 7000
```

deve resultar em:

```text
28000 bytes
```

Se isso não ocorrer, há uma inconsistência de serialização.

---

# 170. Relação com `weights.py`

`weights.py` produz:

```text
weights_raw
bias_raw
```

Já `quantization.py` produz:

```text
mul_blob
shift_blob
q6_blob
```

Todos serão colocados posteriormente na mesma memória linear, mas em regiões diferentes.

---

# 171. Comparação

```text
weights_raw
    ↓
parâmetros treinados

bias_raw
    ↓
bias treinado

mul_blob
    ↓
parâmetros derivados de requantização

shift_blob
    ↓
parâmetros derivados de requantização

q6_blob
    ↓
limites derivados da quantização da saída
```

---

# 172. Dados extraídos versus derivados

Essa distinção é importante.

Os pesos vêm diretamente do modelo:

```text
TFLite buffer
    ↓
weights_raw
```

Já:

```text
multiplier
shift
Q6
```

são calculados pelo extrator a partir dos metadados do modelo.

---

# 173. Fluxo completo de uma `CONV_2D`

Considere:

```text
input_scale = Sx

weight_scale[c] = Sw[c]

output_scale = Sy
```

Para cada canal:

```text
real_multiplier[c]
=
Sx × Sw[c] / Sy
```

Depois:

```text
real_multiplier[c]
      ↓
quantize_multiplier()
      ↓
multiplier[c]
shift[c]
```

Em paralelo:

```text
6.0
 ↓
quantização da saída
 ↓
Q6[c]
```

---

# 174. Resultado por canal

Para um canal `c`:

```text
multiplier[c]
shift[c]
Q6[c]
```

serão utilizados pelo kernel na requantização da saída acumulada.

---

# 175. Caminho até o WAT

```text
quantization.py
      │
      ├── mul_blob
      ├── shift_blob
      └── q6_blob
      │
      ▼
memory.py
      │
      ├── MUL_BASE
      ├── SHIFT_BASE
      └── Q6_BASE
      │
      ▼
layer_params.py
      │
      ├── mul_ptr
      ├── shift_ptr
      └── q6_ptr
      │
      ▼
params_blob
      │
      ▼
WAT
```

---

# 176. Exemplo de endereço final

Suponha:

```text
MUL_BASE = 414832

mul_offset = 128
```

Então:

```text
mul_ptr =
414832 + 128
=
414960
```

Esse endereço será inserido na `LayerParam`.

---

# 177. O mesmo para SHIFT

```text
SHIFT_BASE = 443008

shift_offset = 128

shift_ptr =
443136
```

---

# 178. E Q6

```text
Q6_BASE = 471184

q6_offset = 128

q6_ptr =
471312
```

Os números são apenas exemplos.

---

# 179. Q6 e ativação

O blob Q6 pode ser preparado para todas as features das operações quantizadas, mas o ponteiro correspondente é utilizado posteriormente de acordo com a ativação da camada.

Para uma operação com:

```text
ReLU6
```

o limite superior é necessário.

Para uma camada sem essa ativação, o runtime pode não utilizar `q6_ptr`.

---

# 180. Por que Q6 é `int32`?

Mesmo que a saída final da operação seja `int8`, armazenar o limite em `int32` mantém uma representação uniforme nas tabelas auxiliares e simplifica o acesso no runtime.

---

# 181. Relação com zero points

A requantização completa não depende apenas de:

```text
multiplier
shift
```

Também existem:

```text
zx
zw
zy
```

que representam zero points de:

```text
entrada
peso
saída
```

Esses valores são armazenados posteriormente na `LayerParam`.

---

# 182. Divisão de responsabilidades

Portanto:

```text
quantization.py
```

produz principalmente:

```text
multiplier
shift
Q6
```

Enquanto:

```text
layer_params.py
```

reúne:

```text
multiplier pointers
zero points
geometria da camada
endereços
flags
```

---

# 183. Por que não colocar tudo neste módulo?

Porque este arquivo deve responder:

```text
quais parâmetros numéricos de quantização
preciso para executar a operação?
```

e não:

```text
onde eles ficarão na memória?
```

Essa segunda pergunta pertence a `memory.py` e `layer_params.py`.

---

# 184. Offset relativo versus ponteiro

Assim como em `weights.py`:

```text
mul_offset
shift_offset
q6_offset
```

são relativos.

Posteriormente:

```text
base + offset
```

gera o ponteiro final.

---

# 185. Tabelas independentes

Os offsets são independentes porque existem três blobs separados.

Assim:

```text
mul_offset = 100
shift_offset = 100
q6_offset = 100
```

não significa que os três dados ocupem a mesma memória.

Eles pertencem respectivamente a:

```text
MUL_BASE + 100

SHIFT_BASE + 100

Q6_BASE + 100
```

---

# 186. Quantização per-tensor

Quando os pesos possuem uma única escala:

```text
Sw
```

o mesmo:

```text
multiplier
shift
```

é replicado por todos os canais.

---

# 187. Quantização per-channel

Quando existem:

```text
Sw[0]
Sw[1]
Sw[2]
...
```

cada canal recebe seus próprios:

```text
multiplier[c]
shift[c]
```

---

# 188. Por que isso é importante para MobileNetV2?

As convoluções quantizadas podem utilizar escalas específicas por canal nos pesos.

Então uma única constante global de requantização seria insuficiente.

O runtime precisa acessar o parâmetro correspondente ao canal de saída que está calculando.

---

# 189. Exemplo conceitual no kernel

Para canal:

```text
c
```

o runtime pode efetivamente consultar:

```text
mul_ptr + c × 4
```

e:

```text
shift_ptr + c × 4
```

para carregar os parâmetros daquele canal.

---

# 190. Relação direta com `nfeat`

É justamente por isso que:

```text
nfeat
```

precisa corresponder ao número de conjuntos de parâmetros disponíveis para aquela operação.

---

# 191. O que o módulo deliberadamente não faz

`quantization.py` não:

```text
extrai bytes dos pesos

organiza weights_raw

calcula bases absolutas

aloca slots

calcula padding espacial

gera LayerParam

gera WAT
```

---

# 192. Sua responsabilidade exata

Ele responde:

```text
como converter os fatores de escala
do modelo quantizado

em parâmetros inteiros
utilizáveis pelo runtime?
```

---

# 193. Validações atuais

O módulo verifica, entre outras condições:

```text
inputs e outputs suficientes

quantização existente

vetores de scales não vazios

shape suficiente para determinar nfeat
```

Quando uma dessas condições falha:

```python
continue
```

é utilizado.

---

# 194. Consequência de usar `continue`

Uma operação com metadados inesperados pode simplesmente não receber uma entrada em:

```python
mul_q6_off
```

Por isso as etapas posteriores precisam pressupor que as operações suportadas do modelo atual possuem quantização válida.

---

# 195. Possível evolução futura

Em uma ferramenta mais genérica, pode ser interessante substituir determinados:

```python
continue
```

por exceções explícitas como:

```text
operação quantizada sem scale

shape incompatível

quantized dimension inesperada
```

Isso tornaria falhas em modelos externos mais fáceis de diagnosticar.

---

# 196. Preservação do comportamento atual

Na modularização atual, a prioridade foi:

```text
preservar o comportamento
do extrator validado
```

antes de endurecer todas as verificações.

Esse princípio também explica o preenchimento pelo último valor quando existe diferença entre:

```text
nfeat
```

e:

```text
quantidade de scales disponíveis
```

---

# 197. Relação com a fidelidade numérica

Esse módulo é um dos pontos mais sensíveis para a fidelidade entre:

```text
TFLite
```

e:

```text
implementação WASM
```

Porque uma diferença pequena em:

```text
multiplier
shift
zero point
saturação
```

pode alterar a saída quantizada de uma camada.

---

# 198. Cadeia de propagação

Uma diferença em um multiplier pode produzir:

```text
valor de ativação diferente
       ↓
entrada diferente da próxima camada
       ↓
novo acumulador diferente
       ↓
diferença propagada pela rede
```

Por isso esse módulo merece relatórios detalhados.

---

# 199. Papel do relatório na depuração

Quando a saída de uma camada diverge, é possível verificar:

```text
input_scale

weight_scale

output_scale

real_multiplier

multiplier

shift

Q6
```

antes de investigar o kernel WebAssembly.

---

# 200. Exemplo de investigação

Se TFLite e WASM divergem em uma convolução:

```text
1. verificar scales
2. verificar real_multiplier
3. verificar quantize_multiplier()
4. verificar multiplier serializado
5. verificar shift serializado
6. verificar ponteiros
7. verificar algoritmo de requantização no WAT
```

Assim o problema pode ser isolado.

---

# 201. Separação entre fórmula e armazenamento

O módulo possui duas fases conceituais:

```text
CÁLCULO
   ↓
multipliers
shifts
Q6

SERIALIZAÇÃO
   ↓
mul_blob
shift_blob
q6_blob
```

Isso é melhor do que misturar diretamente cálculo com geração de WAT.

---

# 202. Benefício arquitetural

O resultado poderia, em princípio, ser consumido por outro backend que não fosse WAT.

Por exemplo:

```text
quantization.py
       │
       ├──→ WAT generator
       ├──→ gerador C
       └──→ ferramenta de análise
```

porque sua saída não é uma string específica de WebAssembly.

---

# 203. Visão completa do módulo

```text
                    TFLite
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
    tensor metadata          op metadata
          │                       │
          └───────────┬───────────┘
                      ▼
             quantization.py
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
   multiplier        shift           Q6
       │              │              │
       ▼              ▼              ▼
   mul_vals       shift_vals      q6_vals
       │              │              │
       ▼              ▼              ▼
   mul_blob       shift_blob      q6_blob
       │              │              │
       └──────────────┼──────────────┘
                      ▼
                 memory.py
                      │
                      ▼
              layer_params.py
                      │
                      ▼
                  params_blob
                      │
                      ▼
                     WASM
```

---

# 204. Síntese

`quantization.py` converte a representação matemática de quantização do TFLite em uma representação adequada à execução inteira do runtime WebAssembly.

Para operações como:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

o ponto central é:

```text
real_multiplier[c]
=
input_scale
×
weight_scale[c]
÷
output_scale
```

Esse valor é convertido em:

```text
multiplier[c]
+
shift[c]
```

por:

```python
quantize_multiplier()
```

Também é calculada a representação quantizada de:

```text
6.0
```

produzindo:

```text
Q6[c]
```

para uso com `ReLU6`.

Os parâmetros são organizados em três tabelas contínuas:

```text
MUL
SHIFT
Q6
```

e cada operação recebe offsets que indicam onde seus valores começam.

Para `SOFTMAX`, o módulo utiliza uma preparação própria envolvendo:

```text
input_scale
beta
integer_bits
input_left_shift
multiplier
shift
```

enquanto o `ADD` utiliza uma função independente que transforma as escalas das duas entradas e da saída em:

```text
mul_a / shift_a
mul_b / shift_b
output_mul / output_shift
```

Assim, ao final desta etapa, o pipeline deixou de possuir apenas metadados abstratos de quantização e passou a possuir **tabelas inteiras serializáveis**, diretamente apropriadas para serem colocadas na memória linear do WebAssembly e utilizadas pelos kernels de inferência.
