> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.md). O corpo original foi mantido.

# 12 — Serialização das LayerParams (`params_blob.py`)

## 1. Objetivo do módulo

O arquivo `extractor/params_blob.py` é responsável por transformar a representação estruturada produzida por `layer_params.py` em um bloco binário contínuo que será inserido diretamente na memória linear do módulo WebAssembly.

Até o módulo anterior, cada camada é representada por um dicionário Python semelhante a:

```python
{
    "op_type": ...,
    "act": ...,
    "flags": ...,

    "in_slot": ...,
    "out_slot": ...,

    "in_h": ...,
    "in_w": ...,

    "cin": ...,
    "cout": ...,

    "kh": ...,
    "kw": ...,

    "w_off": ...,
    "b_off": ...,

    "mul_off": ...,
    "shift_off": ...,
    "q6_off": ...,

    ...
}
```

Essa representação é excelente para:

```text
cálculo
validação
debug
relatório
```

mas o runtime WebAssembly não recebe dicionários Python.

Ele precisa de uma sequência binária fixa:

```text
LayerParam 0
LayerParam 1
LayerParam 2
...
```

Assim, este módulo executa:

```text
layer_params.py
      │
      ▼
dicts Python
      │
      ▼
params_blob.py
      │
      ├── valida slots
      ├── resolve ponteiros
      ├── empacota 29 int32
      ├── concatena estruturas
      └── adiciona padding
      │
      ▼
params_blob
      │
      ▼
wat_generator.py
      │
      ▼
memória WASM
```

---

# 2. Posição no pipeline

O fluxo completo próximo desta etapa é:

```text
weights.py
   │
   └── offsets dos pesos e bias

quantization.py
   │
   └── offsets de MUL / SHIFT / Q6

memory.py
   │
   └── bases absolutas dessas regiões

layer_params.py
   │
   └── representação lógica de cada operação

         │
         ▼

    params_blob.py

         │
         ├── base + offset
         ├── ponteiros
         ├── struct.pack()
         └── blob binário

         │
         ▼

   wat_generator.py
```

Este módulo é, portanto, a fronteira entre:

```text
representação estruturada
```

e:

```text
representação binária
```

---

# 3. Importações

O arquivo começa com:

```python
import struct
```

A biblioteca `struct` é utilizada para converter valores inteiros Python em bytes seguindo um layout binário exato.

Também são importados de `layer_params.py`:

```python
LP_FMT
LP_SIZE
```

e todos os códigos de operações e flags necessários para interpretar as estruturas.

---

# 4. `LP_FMT`

No módulo anterior:

```python
LP_FMT = "<" + "i" * 29
```

Portanto:

```text
<
    little-endian

i
    signed int32

29
    quantidade de valores
```

Cada `LayerParam` ocupa:

```text
29 × 4
=
116 bytes
```

---

# 5. `LP_SIZE`

Também importamos:

```python
LP_SIZE
```

que corresponde a:

```text
116 bytes
```

no formato atual.

Essa constante é utilizada para verificar que cada chamada a:

```python
struct.pack()
```

produziu exatamente o tamanho esperado.

---

# 6. Operações conhecidas

São importados:

```text
OP_CONV
OP_DW
OP_FC
OP_ADD
OP_MEAN
OP_SOFTMAX
OP_QUANTIZE
OP_RGB565_TO_RGB888
```

Esses códigos servem principalmente para tornar os relatórios legíveis.

---

# 7. Flags

Também são importados:

```text
FLAG_PADDING_SAME
FLAG_HAS_Q6
FLAG_QUANTIZE_INPUT_INT8
```

O relatório precisa interpretar:

```text
flags
```

de maneira contextual.

Isso é particularmente importante porque:

```text
FLAG_PADDING_SAME
```

e:

```text
FLAG_QUANTIZE_INPUT_INT8
```

utilizam o mesmo bit.

---

# 8. Ativações

De `operator_options.py` são importados:

```python
ACT_NONE
ACT_RELU
ACT_RELU6
```

Eles serão usados tanto na serialização quanto no relatório.

---

# 9. Separação das responsabilidades

O módulo possui quatro grupos principais de funções:

```text
1. nomes para relatório

op_type_name()
act_name()
flags_pretty()


2. serialização individual

pack_layerparam()


3. validação

validate_layer_params()


4. serialização completa

build_params_blob()
params_blob_to_text()
```

---

# 10. `op_type_name()`

A função:

```python
def op_type_name(op_type):
```

converte um código inteiro em nome legível.

Por exemplo:

```text
1 → CONV

2 → DW

3 → FC

4 → ADD

5 → MEAN

6 → SOFTMAX

7 → QUANTIZE

8 → RGB565_TO_RGB888
```

---

# 11. Valor desconhecido

O código utiliza:

```python
.get(
    op_type,
    str(op_type),
)
```

Portanto um código desconhecido, por exemplo:

```text
12
```

seria apresentado simplesmente como:

```text
"12"
```

O relatório não falha por causa disso.

---

# 12. `act_name()`

A função possui a mesma finalidade para ativações.

```text
0 → NONE

1 → RELU

3 → RELU6
```

---

# 13. `flags_pretty()`

Essa função merece atenção especial:

```python
def flags_pretty(
    flags,
    optype="",
):
```

porque a interpretação dos bits depende do tipo de operação.

---

# 14. Flags do `QUANTIZE`

Se:

```python
optype == "QUANTIZE"
```

o bit:

```text
FLAG_QUANTIZE_INPUT_INT8
```

é interpretado.

Se estiver ligado:

```text
INPUT_INT8
```

é mostrado.

Caso contrário:

```text
INPUT_UINT8
```

é mostrado.

---

# 15. Flags das demais operações

Para as outras operações:

```text
bit 0
    ↓
PADDING_SAME

bit 1
    ↓
HAS_Q6
```

podem ser registrados.

---

# 16. Importância do contexto

Isso evita interpretar:

```text
flags = 1
```

sempre como:

```text
PADDING_SAME
```

Quando:

```text
optype = QUANTIZE
```

o mesmo valor significa:

```text
INPUT_INT8
```

A função implementa exatamente essa distinção contextual.

---

# 17. Retorno sem flags

Se nenhuma descrição for aplicável:

```python
return "0"
```

Isso produz um relatório mais legível que uma string vazia.

---

# 18. `pack_layerparam()`

Esta é a função central de serialização individual:

```python
def pack_layerparam(
    ...
):
```

Ela recebe exatamente os campos que serão armazenados no runtime.

---

# 19. Ordem dos 29 campos

A ordem é fixa:

```text
 1  op_type
 2  act
 3  flags

 4  in_ptr
 5  out_ptr

 6  in_h
 7  in_w
 8  cin
 9  cout

10  kh
11  kw

12  stride_h
13  stride_w

14  dil_h
15  dil_w

16  pad_t
17  pad_b
18  pad_l
19  pad_r

20  wptr
21  bias_ptr

22  mul_ptr
23  shift_ptr
24  q6_ptr

25  zx
26  zw
27  zy

28  out_h
29  out_w
```

Essa ordem é parte do protocolo entre:

```text
Python extractor
```

e:

```text
WAT runtime
```

---

# 20. Ordem não pode mudar arbitrariamente

Imagine trocar:

```text
mul_ptr
```

por:

```text
shift_ptr
```

no Python, mas manter o leitor do WAT como está.

O resultado seria:

```text
runtime pede multiplier
        ↓
lê endereço de SHIFT
```

O WAT continuaria podendo ser sintaticamente válido, porém a inferência seria incorreta.

Portanto a ordem dos campos é um contrato binário.

---

# 21. Lista `values`

A função primeiro constrói:

```python
values = [
    ...
]
```

com todos os 29 valores na ordem exata.

Isso facilita verificar a quantidade antes da serialização.

---

# 22. Validação da quantidade

Existe:

```python
if len(values) != 29:
```

seguido por:

```text
RuntimeError
```

Caso a estrutura seja modificada incorretamente.

---

# 23. Por que validar?

Porque:

```text
LP_FMT
```

espera exatamente:

```text
29 int32
```

Uma diferença indicaria quebra no contrato.

---

# 24. Conversão explícita para `int`

Antes do `pack`:

```python
int(value)
```

é aplicado a todos os elementos.

Isso normaliza valores que possam estar em tipos como:

```text
np.int32
np.int64
bool
```

para inteiros Python.

---

# 25. Serialização

Finalmente:

```python
struct.pack(
    LP_FMT,
    *values,
)
```

produz:

```text
116 bytes
```

para uma camada.

---

# 26. Little-endian

Como:

```text
LP_FMT
```

começa com:

```text
<
```

cada inteiro de 32 bits é serializado em little-endian.

Por exemplo, conceitualmente:

```text
valor = 1
```

é armazenado como:

```text
01 00 00 00
```

---

# 27. Estrutura física de uma camada

```text
offset +0
┌────────────────────────┐
│ op_type      int32     │
├────────────────────────┤
│ act          int32     │
├────────────────────────┤
│ flags        int32     │
├────────────────────────┤
│ in_ptr       int32     │
├────────────────────────┤
│ out_ptr      int32     │
├────────────────────────┤
│ ...                    │
├────────────────────────┤
│ out_w        int32     │
└────────────────────────┘
offset +116
```

---

# 28. Offset de um campo

Como cada campo possui:

```text
4 bytes
```

o campo de índice `n`, começando em zero, está em:

```text
layer_base
+
n × 4
```

---

# 29. Exemplo

`op_type`:

```text
offset 0
```

`act`:

```text
offset 4
```

`flags`:

```text
offset 8
```

`in_ptr`:

```text
offset 12
```

`out_ptr`:

```text
offset 16
```

e assim por diante.

---

# 30. Função `validate_layer_params()`

Antes da serialização, o módulo executa validações estruturais.

```python
def validate_layer_params(
    layer_params,
    *,
    slot_bases,
):
```

---

# 31. Validação de `in_slot`

Para cada camada:

```python
in_slot = params["in_slot"]
```

precisa satisfazer:

```text
0 <= in_slot < número de slots
```

---

# 32. Exemplo

Com três slots:

```text
válidos:

0
1
2
```

Inválidos:

```text
-1
3
4
...
```

---

# 33. `out_slot`

A mesma regra é aplicada a:

```text
out_slot
```

---

# 34. Por que validar índices?

Porque posteriormente será feito:

```python
slot_bases[
    params["in_slot"]
]
```

Um índice inválido significaria:

```text
ponteiro inexistente
```

ou erro de acesso durante a construção.

---

# 35. Validação especial do ADD

A maior parte da validação adicional é dedicada ao:

```text
ADD
```

porque ele possui:

```text
duas entradas dinâmicas
```

enquanto a estrutura padrão contém apenas um:

```text
in_ptr
```

---

# 36. Exatamente dois `input_slots`

Para `ADD`:

```python
len(input_slots) == 2
```

é obrigatório.

Caso contrário:

```text
RuntimeError
```

---

# 37. Primeiro slot

Também:

```text
params["in_slot"]
==
input_slots[0]
```

deve ser verdadeiro.

---

# 38. Por que isso importa?

A convenção adotada é:

```text
primeira entrada
    ↓
in_slot
    ↓
in_ptr
```

A segunda entrada é transportada de outra maneira.

---

# 39. Ponteiro esperado da entrada A

O código calcula:

```python
expected_ptr_a = (
    slot_bases[
        slot_a
    ]
)
```

---

# 40. Ponteiro esperado da entrada B

Da mesma forma:

```python
expected_ptr_b = (
    slot_bases[
        slot_b
    ]
)
```

---

# 41. Convenção especial do ADD

Em `layer_params.py`:

```text
pad_t
```

foi reutilizado como:

```text
pointer da entrada A
```

e:

```text
pad_b
```

como:

```text
pointer da entrada B
```

---

# 42. Validação de `pad_t`

É exigido:

```text
params["pad_t"]
==
slot_bases[slot_a]
```

---

# 43. Validação de `pad_b`

Da mesma maneira:

```text
params["pad_b"]
==
slot_bases[slot_b]
```

---

# 44. Verificação adicional

O código ainda verifica:

```text
pad_t in slot_bases

pad_b in slot_bases
```

Assim os ponteiros precisam corresponder exatamente a alguma base física de slot conhecida.

---

# 45. Por que há verificações aparentemente redundantes?

Por exemplo:

```text
pad_t == expected_ptr_a
```

já implica que:

```text
pad_t
```

corresponde ao slot A.

Mas a verificação adicional:

```text
pad_t in slot_bases
```

torna a intenção explícita:

```text
os ponteiros especiais do ADD
precisam apontar para bases de slots
```

---

# 46. O que a validação não faz

Ela não verifica aqui:

```text
w_off dentro de weights_raw

b_off dentro de bias_raw

mul_off dentro de mul_blob

q6_off dentro de q6_blob
```

A função concentra-se principalmente em:

```text
integridade dos slots
+
convenção especial do ADD
```

A própria docstring declara esse foco.

---

# 47. Retorno

Se tudo estiver correto:

```python
return True
```

O retorno não carrega novos dados.

A principal função é:

```text
falhar cedo
```

quando existe inconsistência.

---

# 48. `build_params_blob()`

Esta é a função principal do módulo.

```python
def build_params_blob(
    layer_params,
    *,
    slot_bases,
    params_bytes,
    parameter_layout,
):
```

Ela serializa todas as camadas em um único bloco binário contínuo.

---

# 49. Entradas

A função recebe quatro grupos de informações.

### `layer_params`

Descrição lógica de todas as camadas.

### `slot_bases`

Endereços absolutos dos slots.

### `params_bytes`

Tamanho total reservado para a região PARAMS.

### `parameter_layout`

Bases absolutas das regiões:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

---

# 50. Primeira operação: validação

Antes de gerar qualquer byte:

```python
validate_layer_params(...)
```

é executada.

Assim:

```text
dados inconsistentes
    ↓
erro
```

ocorre antes de:

```text
struct.pack()
```

---

# 51. Bases absolutas

A função recupera:

```text
kernel_base

bias_base

mul_base

shift_base

q6_base
```

do:

```python
parameter_layout
```

---

# 52. Por que essas bases são necessárias?

`layer_params.py` guardava offsets relativos:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

Agora precisamos gerar:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

---

# 53. Transformação geral

A regra é:

```text
ponteiro absoluto
=
base da região
+
offset interno
```

---

# 54. Exemplo de peso

Suponha:

```text
kernel_base = 2048
w_off = 5000
```

Então:

```text
wptr =
2048 + 5000
=
7048
```

---

# 55. Exemplo de multiplier

```text
mul_base = 414832
mul_off = 128
```

Então:

```text
mul_ptr =
414960
```

---

# 56. Inicialização do blob

O código cria:

```python
params_blob = bytearray()
```

Novamente usamos uma estrutura mutável durante a construção.

---

# 57. Registros para relatório

Também:

```python
records = []
```

guardará informações detalhadas sobre cada camada serializada.

---

# 58. Loop das camadas

A função percorre:

```python
enumerate(
    layer_params
)
```

Portanto:

```text
layer_index = 0
1
2
3
...
```

corresponde diretamente à posição da estrutura dentro do blob.

---

# 59. Relação entre índice e offset

Como:

```text
LP_SIZE = 116
```

esperamos:

```text
L0 → offset 0

L1 → offset 116

L2 → offset 232

L3 → offset 348
```

desde que nenhuma informação adicional seja inserida entre as estruturas.

E é exatamente isso que o código faz.

---

# 60. Cálculo de `in_ptr`

Essa etapa possui uma exceção importante para:

```text
ADD
```

---

# 61. Operações comuns

Para qualquer operação diferente de `ADD`:

```python
in_ptr = (
    slot_bases[
        params["in_slot"]
    ]
)
```

Portanto:

```text
in_slot
    ↓
slot_bases
    ↓
in_ptr
```

---

# 62. Exemplo

Se:

```text
in_slot = 2

slot_bases[2] = 900464
```

então:

```text
in_ptr = 900464
```

---

# 63. ADD

Para `ADD`:

```python
in_ptr = int(
    params["pad_t"]
)
```

---

# 64. Por quê?

Porque em `layer_params.py`:

```text
pad_t
```

já foi definido como:

```text
ponteiro absoluto da entrada A
```

---

# 65. Segunda entrada do ADD

O comentário do código deixa explícito:

```text
o primeiro ponteiro vai em in_ptr

o segundo permanece em pad_b
```

Portanto a estrutura final contém:

```text
in_ptr
    → entrada A
```

e:

```text
pad_b
    → entrada B
```

---

# 66. Duplicação intencional no ADD

Para ADD, `pad_t` também continua sendo serializado posteriormente no próprio campo `pad_t`.

Assim a entrada A aparece:

```text
in_ptr = ptr A
```

e:

```text
pad_t = ptr A
```

Essa duplicação decorre do protocolo atual da estrutura.

---

# 67. `out_ptr`

O ponteiro de saída é sempre:

```python
out_ptr = (
    slot_bases[
        params["out_slot"]
    ]
)
```

---

# 68. Exemplo

```text
out_slot = 1

SLOT1_BASE = 703856
```

então:

```text
out_ptr = 703856
```

---

# 69. Peso: `wptr`

O código sempre executa:

```python
wptr = (
    kernel_base
    + params["w_off"]
)
```

Essa é uma característica importante.

---

# 70. Operações sem pesos

Operações como:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
RGB565_TO_RGB888
```

normalmente possuem:

```text
w_off = 0
```

Portanto seu:

```text
wptr
```

será:

```text
kernel_base
```

e não:

```text
0
```

---

# 71. Isso significa que elas usam pesos?

Não.

O significado do campo depende de:

```text
op_type
```

Os kernels dessas operações não devem interpretar `wptr` como um peso válido.

---

# 72. Importância dessa distinção

No relatório pode aparecer:

```text
wptr = 2048
```

para uma operação que não utiliza pesos.

Isso não significa que ela consome o primeiro tensor de pesos.

Significa apenas que a serialização atual sempre calcula:

```text
kernel_base + w_off
```

e:

```text
w_off = 0
```

para essas operações.

---

# 73. Bias

O comportamento é diferente.

O código primeiro verifica:

```python
params["has_bias"]
```

---

# 74. Bias presente

Quando verdadeiro:

```text
bias_ptr =
bias_base
+
b_off
```

---

# 75. Bias ausente

Caso contrário:

```python
bias_ptr = 0
```

Portanto `bias_ptr = 0` possui significado explícito:

```text
sem bias
```

---

# 76. Por que `b_off = 0` sozinho não basta?

Porque um bias real poderia perfeitamente estar no início do blob:

```text
b_off = 0
```

Assim precisamos do booleano:

```text
has_bias
```

para distinguir:

```text
bias existente no offset zero
```

de:

```text
bias inexistente
```

---

# 77. MUL e SHIFT

Também existe:

```python
params["has_mulq6"]
```

---

# 78. Quando verdadeiro

São calculados:

```text
mul_ptr =
mul_base + mul_off
```

e:

```text
shift_ptr =
shift_base + shift_off
```

---

# 79. Quando falso

O código define:

```text
mul_ptr = 0

shift_ptr = 0
```

---

# 80. Q6 possui uma condição adicional

Mesmo com:

```text
has_mulq6 = True
```

o `q6_ptr` só é materializado se:

```text
act == ACT_RELU6
```

---

# 81. Regra completa

```text
has_mulq6
AND
activation == RELU6
      │
      ├── sim
      │     ↓
      │ q6_ptr =
      │ Q6_BASE + q6_off
      │
      └── não
            ↓
         q6_ptr = 0
```

---

# 82. Por que essa diferença?

Os multipliers e shifts são necessários para requantização.

Já:

```text
Q6
```

é especificamente necessário para implementar o limite superior da:

```text
ReLU6
```

---

# 83. Consequência para SOFTMAX

O `SOFTMAX` pode possuir:

```text
has_mulq6 = True
```

porque existem `mul_off` e `shift_off`.

Mas:

```text
act = ACT_NONE
```

Logo:

```text
q6_ptr = 0
```

---

# 84. `blob_offset`

Antes de serializar a camada:

```python
blob_offset = len(
    params_blob
)
```

é calculado.

---

# 85. Significado

`blob_offset` é o início daquela `LayerParam` dentro de:

```text
params_blob
```

Ele não é o endereço absoluto da memória WASM.

---

# 86. Conversão para endereço absoluto

Posteriormente:

```text
LayerParam address
=
PARAMS_BASE
+
blob_offset
```

---

# 87. Exemplo

Se:

```text
PARAMS_BASE = 499360
```

e:

```text
blob_offset = 232
```

então:

```text
endereço da LayerParam
=
499592
```

---

# 88. Relação matemática do offset

Como cada camada ocupa:

```text
116 bytes
```

antes do padding final:

```text
blob_offset
=
layer_index × 116
```

---

# 89. Chamada a `pack_layerparam()`

Depois o módulo envia todos os valores na ordem definida pelo contrato.

Os primeiros são:

```text
op_type
act
flags
```

seguidos de:

```text
in_ptr
out_ptr
```

e finalmente todos os parâmetros de geometria, ponteiros auxiliares, zero points e shape de saída.

A chamada mantém a ordem exata dos 29 valores esperados.

---

# 90. Campos de ponteiro já resolvidos

Observe a diferença:

No dicionário original:

```text
w_off

b_off

mul_off
```

Na chamada a `pack_layerparam()`:

```text
wptr

bias_ptr

mul_ptr
```

Portanto o blob final não precisa conhecer a ideia de offset relativo.

Ele já recebe os endereços que o runtime utilizará.

---

# 91. Validação do tamanho da estrutura

Depois:

```python
if len(packed) != LP_SIZE:
```

o código lança erro.

---

# 92. Valor esperado

No formato atual:

```text
len(packed)
=
116
```

---

# 93. Por que verificar mesmo usando `struct.pack()`?

Porque isso cria um invariante explícito entre:

```text
LP_FMT
```

e:

```text
LP_SIZE
```

e torna uma futura alteração da estrutura mais fácil de diagnosticar.

---

# 94. Concatenação

Depois:

```python
params_blob.extend(
    packed
)
```

A camada é anexada imediatamente depois da anterior.

---

# 95. Layout do blob

```text
params_blob

offset 0
┌──────────────────────┐
│ LayerParam 0         │
│ 116 bytes            │
└──────────────────────┘

offset 116
┌──────────────────────┐
│ LayerParam 1         │
│ 116 bytes            │
└──────────────────────┘

offset 232
┌──────────────────────┐
│ LayerParam 2         │
│ 116 bytes            │
└──────────────────────┘

...
```

---

# 96. Metadados da camada serializada

Depois da serialização, um registro é criado contendo:

```text
layer_index

blob_offset

op_index

optype

op_type

act

flags

in_slot

out_slot

input_slots

in_ptr

out_ptr

wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr

params
```

---

# 97. Por que guardar `params` inteiro novamente?

O registro contém:

```python
"params": params
```

Isso permite que o relatório posterior tenha acesso tanto aos:

```text
valores antes da serialização
```

quanto aos:

```text
ponteiros absolutos calculados
```

---

# 98. Exemplo

Podemos mostrar simultaneamente:

```text
w_off = 5000
```

e:

```text
wptr = 7048
```

Assim fica clara a transformação:

```text
offset relativo
    ↓
endereço absoluto
```

---

# 99. Fim do loop

Ao terminar todas as camadas:

```python
used_bytes = len(
    params_blob
)
```

representa quantos bytes foram efetivamente utilizados pelas estruturas.

---

# 100. Fórmula esperada

Como cada camada possui exatamente `LP_SIZE`:

```text
used_bytes
=
layer_count
×
LP_SIZE
```

---

# 101. Exemplo

Para:

```text
68 layers
```

e:

```text
LP_SIZE = 116
```

temos:

```text
68 × 116
=
7888 bytes
```

---

# 102. Diferença entre `used_bytes` e `params_bytes`

`used_bytes` é:

```text
tamanho real das LayerParams
```

`params_bytes` é:

```text
área total reservada,
já considerando alinhamento
```

---

# 103. Exemplo

Suponha:

```text
used_bytes = 7888
```

Com alinhamento:

```text
params_bytes = 7888
```

se já estiver alinhado.

Ou poderia ocorrer:

```text
used_bytes = 7890

params_bytes = 7904
```

em outro cenário.

---

# 104. Validação da área reservada

Se:

```text
used_bytes > params_bytes
```

o código lança:

```text
RuntimeError
```

---

# 105. Significado

Isso indicaria que:

```text
memory planning
```

reservou menos memória do que a serialização efetivamente requer.

Essa seria uma inconsistência grave entre:

```text
calculate_layer_memory_layout()
```

e:

```text
build_params_blob()
```

---

# 106. Padding final

Se a região reservada for maior:

```python
padding_bytes = (
    params_bytes
    - used_bytes
)
```

---

# 107. Exemplo

```text
used_bytes = 7890

params_bytes = 7904
```

então:

```text
padding_bytes = 14
```

---

# 108. Conteúdo do padding

O código adiciona:

```python
b"\x00"
*
padding_bytes
```

Portanto o padding é preenchido com bytes zero.

---

# 109. Estrutura final

```text
PARAMS region

┌──────────────────────┐
│ LayerParam 0         │
├──────────────────────┤
│ LayerParam 1         │
├──────────────────────┤
│ ...                  │
├──────────────────────┤
│ última LayerParam    │
├──────────────────────┤
│ 00 00 00 ...         │
│ padding de alinhamento│
└──────────────────────┘
```

---

# 110. Por que incluir o padding dentro de `params_blob`?

Isso faz com que:

```text
len(params_blob)
==
params_bytes
```

ao final.

Consequentemente, o data segment gerado posteriormente já cobre exatamente toda a área reservada para `PARAMS`.

---

# 111. Relação com SLOT0

Como o planejamento calculou:

```text
SLOT0_BASE
```

depois de:

```text
PARAMS_BASE + params_bytes
```

o blob completo precisa respeitar exatamente esse tamanho reservado.

---

# 112. Invariante final

Ao retornar:

```text
len(serialization["params_blob"])
==
serialization["params_bytes"]
```

deve ser verdadeiro.

---

# 113. Retorno de `build_params_blob()`

A função retorna:

```python
{
    "params_blob": ...,
    "records": ...,
    "layer_count": ...,
    "layer_param_size": ...,
    "used_bytes": ...,
    "padding_bytes": ...,
    "params_bytes": ...,
}
```

---

# 114. `params_blob`

É o artefato binário que será efetivamente colocado na memória.

O tipo retornado é:

```text
bytes
```

e não mais:

```text
bytearray
```

---

# 115. `records`

São metadados para:

```text
debug
relatório
validação posterior
```

---

# 116. `layer_count`

Corresponde a:

```python
len(
    layer_params
)
```

e inclui a camada sintética.

---

# 117. `layer_param_size`

É:

```text
LP_SIZE
```

ou, atualmente:

```text
116
```

Esse campo também é consumido posteriormente pelo `wat_generator.py`.

---

# 118. `used_bytes`

Quantidade de bytes efetivamente ocupados pelas estruturas.

---

# 119. `padding_bytes`

Quantidade de bytes zero adicionados apenas para completar a área alinhada.

---

# 120. `params_bytes`

Tamanho físico final da região reservada.

O processo completo de construção, incluindo cálculo dos ponteiros, serialização e padding, está concentrado nessa função.

---

# 121. Offsets relativos versus ponteiros absolutos

Esse é provavelmente o conceito mais importante do módulo.

Antes:

```text
weights.py
    ↓
weight tensor → w_off
```

Depois:

```text
params_blob.py
    ↓
wptr =
WEIGHTS_BASE + w_off
```

---

# 122. Para bias

```text
b_off
    ↓
BIAS_BASE + b_off
    ↓
bias_ptr
```

---

# 123. Para multiplier

```text
mul_off
    ↓
MUL_BASE + mul_off
    ↓
mul_ptr
```

---

# 124. Para shift

```text
shift_off
    ↓
SHIFT_BASE + shift_off
    ↓
shift_ptr
```

---

# 125. Para Q6

```text
q6_off
    ↓
Q6_BASE + q6_off
    ↓
q6_ptr
```

apenas quando:

```text
has_mulq6
AND
activation == RELU6
```

---

# 126. Slots funcionam de forma diferente

O slot não possui offset por tensor.

Seu ponteiro é diretamente:

```text
slot_bases[
    slot_index
]
```

---

# 127. Exemplo completo de CONV

Suponha:

```text
in_slot = 1
out_slot = 2

slot_bases =
[
    507248,
    703856,
    900464
]
```

Então:

```text
in_ptr = 703856

out_ptr = 900464
```

---

# 128. Pesos da mesma CONV

Suponha:

```text
kernel_base = 2048

w_off = 5000
```

Então:

```text
wptr = 7048
```

---

# 129. Bias

```text
bias_base = 386656

b_off = 256
```

Então:

```text
bias_ptr = 386912
```

---

# 130. Quantização

```text
mul_base = 414832
mul_off = 128

shift_base = 443008
shift_off = 128

q6_base = 471184
q6_off = 128
```

Então:

```text
mul_ptr = 414960

shift_ptr = 443136

q6_ptr = 471312
```

se a camada utilizar `ReLU6`.

---

# 131. Estrutura final da CONV

O runtime receberá diretamente:

```text
in_ptr     = 703856
out_ptr    = 900464

wptr       = 7048
bias_ptr   = 386912

mul_ptr    = 414960
shift_ptr  = 443136
q6_ptr     = 471312
```

Ele não precisa conhecer:

```text
tensor IDs
offsets relativos
dicionários Python
```

---

# 132. Isso simplifica o runtime

Todo o trabalho de resolução de:

```text
grafo
slots
tensors
offsets
bases
```

é realizado antecipadamente no Python.

O WAT recebe uma estrutura já materializada.

---

# 133. Relação com AOT e interpretador

A mesma `LayerParam` binária pode ser consumida pela lógica do módulo independentemente de a execução do WebAssembly ocorrer posteriormente de forma:

```text
interpretada
```

ou:

```text
AOT
```

A estrutura dos dados permanece a mesma.

---

# 134. `params_blob_to_text()`

A segunda grande função gera um relatório da serialização.

Sua docstring diz explicitamente que ela substitui os antigos comentários e informações de debug que ficavam embutidos no próprio WAT.

---

# 135. Cabeçalho do relatório

O relatório começa com:

```text
PARAMS BLOB
================================================================================
```

e apresenta:

```text
LayerParam size

Layers

Bytes usados

Padding

Params bytes
```

---

# 136. Exemplo conceitual

```text
LayerParam size : 116 bytes
Layers          : 68
Bytes usados    : 7888
Padding         : 0
Params bytes    : 7888
```

---

# 137. Dump por camada

Depois cada:

```text
record
```

gera uma seção.

---

# 138. Identificação

São mostrados:

```text
L<layer_index>

blob_offset

op_index

optype

op_type
```

---

# 139. `layer_index` versus label TFLite

Assim como no relatório anterior:

```text
L0
```

nesse ponto representa:

```text
posição dentro do params_blob
```

e não necessariamente o label lógico `L0` de `graph.py`.

A primeira estrutura é a camada sintética.

---

# 140. `blob_offset`

Esse campo é especialmente útil para conferir:

```text
L0 → 0

L1 → 116

L2 → 232

L3 → 348
```

---

# 141. Nome da operação

O relatório apresenta:

```text
op_type = 1 (CONV)
```

por exemplo.

Isso mostra simultaneamente:

```text
código binário
+
interpretação humana
```

---

# 142. Ativação

Também:

```text
act = 3 (RELU6)
```

---

# 143. Flags

E:

```text
flags = 3 (PADDING_SAME|HAS_Q6)
```

ou, no caso de QUANTIZE:

```text
flags = 1 (INPUT_INT8)
```

---

# 144. Slots

Para operações com uma entrada:

```text
in_slot/out_slot
```

é mostrado.

Para operações com múltiplas entradas:

```text
in_slots/out_slot
```

é utilizado.

---

# 145. Ponteiros reais

Depois:

```text
in_ptr/out_ptr
```

mostra os endereços que foram efetivamente serializados.

Isso permite comparar:

```text
slot lógico
```

com:

```text
endereço físico
```

---

# 146. Parâmetros especiais de quantização

Se a camada possuir:

```text
quant_params
```

o relatório cria seções específicas para:

```text
ADD

SOFTMAX

QUANTIZE
```

---

# 147. ADD

São exibidos:

```text
sA / sB / sY

zA / zB / zY

s_common

mul0 / shift0

mul1 / shift1

out_mul / out_shift
```

---

# 148. SOFTMAX

São mostrados:

```text
sX / sY

zX / zY

beta

integer_bits

internal_scale

input_beta_mul

input_beta_left_shift

input_left_shift

diff_min
```

---

# 149. Distinção crítica do SOFTMAX

O relatório contém explicitamente o comentário:

```text
stride_w armazena input_left_shift,
não integer_bits
```

e imprime:

```text
stride_w input_left_shift
```

Essa é a interpretação correta do código atual.

---

# 150. QUANTIZE

São exibidos:

```text
input_dtype

scale_in / scale_out

zp_in / zp_out

ratio

mul / shift
```

---

# 151. Geometria tradicional

Para operações comuns, o relatório mostra:

```text
kh / kw

stride_h / stride_w

dil_h / dil_w

pad top/bottom/left/right
```

---

# 152. Operações especiais

Para:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
```

os rótulos mudam para refletir o significado real dos campos.

Isso evita imprimir, por exemplo:

```text
kernel 123456789 × -3
```

quando os campos na verdade significam:

```text
multiplier / shift
```

---

# 153. Relatório do ADD

O relatório mostra:

```text
kh/kw (mul0/sh0)

stride (mul1/sh1)

dil (outM/outSh)

pad_t/b (inPtr)

pad_l/r (zA/zB)
```

---

# 154. Relatório do MEAN

Mostra:

```text
kh/kw (mul/shift)

stride_h spatial

pad_t input_ptr
```

---

# 155. Relatório do SOFTMAX

Mostra:

```text
kh/kw beta

stride_h diff_min

stride_w input_left_shift

pad_t input_ptr
```

---

# 156. Relatório do QUANTIZE

Mostra:

```text
kh/kw (mul/shift)

pad_t input_ptr
```

---

# 157. Depthwise

Para:

```text
DEPTHWISE_CONV_2D
```

também é mostrado:

```text
depth_mult
```

---

# 158. Offsets e ponteiros

A parte final de cada camada compara:

```text
w_off / b_off

mul_off

shift_off

q6_off
```

com:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

---

# 159. Esse é um dos melhores pontos para depuração

Imagine:

```text
w_off = 12000
```

mas:

```text
wptr
```

não corresponder a:

```text
WEIGHTS_BASE + 12000
```

O relatório tornaria a inconsistência evidente.

---

# 160. Zero points

Também são exibidos:

```text
zx / zw / zy
```

permitindo verificar:

```text
input
weights
output
```

num mesmo ponto.

---

# 161. Representação completa das três fases

Para um parâmetro de peso, podemos acompanhar:

```text
TFLite tensor 42
        │
        ▼
weights.py

w_off = 5000
        │
        ▼
layer_params.py

"w_off": 5000
        │
        ▼
params_blob.py

wptr =
WEIGHTS_BASE + 5000
        │
        ▼
struct.pack()

bytes
        │
        ▼
WASM
```

---

# 162. Para uma ativação

```text
TFLite tensor
      │
      ▼
tensor_mapping.py

tensor → runtime slot
      │
      ▼
layer_params.py

in_slot = 1
      │
      ▼
params_blob.py

in_ptr =
slot_bases[1]
      │
      ▼
struct.pack()
```

---

# 163. Para multiplier

```text
op_index
   │
   ▼
quantization.py

mul_off
   │
   ▼
layer_params.py

mul_off
   │
   ▼
params_blob.py

MUL_BASE + mul_off
   │
   ▼
mul_ptr
```

---

# 164. Diferença entre `params_blob` e blobs anteriores

`weights_raw` contém:

```text
dados treinados
```

`mul_blob` contém:

```text
parâmetros de requantização
```

Já `params_blob` contém:

```text
descrição de como executar a rede
```

---

# 165. Pode-se pensar em três categorias

```text
DADOS
    ↓
weights
bias


TABELAS NUMÉRICAS AUXILIARES
    ↓
MUL
SHIFT
Q6


METADADOS DE EXECUÇÃO
    ↓
PARAMS
```

---

# 166. `PARAMS` como tabela de instruções de alto nível

Cada `LayerParam` informa ao runtime algo semelhante a:

```text
qual kernel executar?

onde está a entrada?

onde escrever a saída?

onde estão os pesos?

quais são as dimensões?

qual stride usar?

qual padding usar?

onde estão os parâmetros de requantização?

quais são os zero points?
```

---

# 167. Não é bytecode WASM

É importante distinguir.

`params_blob` não contém:

```text
instruções WebAssembly
```

Ele contém:

```text
dados
```

que o código WebAssembly lê para decidir como executar cada camada.

---

# 168. Modelo conceitual

```text
WASM
    ↓
código genérico dos kernels

PARAMS
    ↓
configuração de cada execução
```

Assim os kernels podem ser reutilizados para muitas camadas.

---

# 169. Exemplo

Um único kernel:

```text
conv2d
```

pode executar:

```text
CONV layer 1

CONV layer 5

CONV layer 17

CONV layer 42
```

porque cada `LayerParam` fornece:

```text
shape
stride
padding
pointers
quantization
```

diferentes.

---

# 170. Relação com portabilidade

Essa separação também ajuda a manter:

```text
algoritmo do runtime
```

separado de:

```text
dados específicos do modelo
```

O template WAT pode manter os kernels estáticos enquanto o extrator altera:

```text
weights
parameters
addresses
number of layers
```

---

# 171. Padding do `params_blob` não é LayerParam

Os bytes adicionais no final:

```text
00 00 00 ...
```

não representam uma camada.

O número real de camadas continua sendo:

```text
layer_count
```

---

# 172. Runtime deve respeitar `NUM_LAYERS`

O loop do runtime deve executar:

```text
0 .. NUM_LAYERS - 1
```

e não inferir quantidade de camadas pelo tamanho total de:

```text
PARAMS
```

porque o final pode conter padding.

---

# 173. Relação com `NUM_LAYERS`

Posteriormente:

```text
NUM_LAYERS
=
serialization["layer_count"]
```

pode ser usado pelo gerador WAT.

---

# 174. Relação com `LP_SIZE`

Também:

```text
LP_SIZE
=
serialization["layer_param_size"]
```

é consumido pelo template/runtime.

---

# 175. Endereço de uma LayerParam

Com:

```text
PARAMS_BASE
LP_SIZE
layer_index
```

temos:

```text
layer_ptr =
PARAMS_BASE
+
layer_index × LP_SIZE
```

---

# 176. Exemplo

```text
PARAMS_BASE = 499360

LP_SIZE = 116

layer_index = 10
```

Então:

```text
layer_ptr =
499360
+
1160
=
500520
```

---

# 177. O leitor do WAT

O runtime pode então carregar:

```text
op_type
act
flags
...
```

em offsets fixos dentro dessa estrutura.

---

# 178. Invariantes fundamentais

Depois de `build_params_blob()`, algumas propriedades devem ser verdadeiras.

### Cada camada

```text
len(packed) == LP_SIZE
```

---

### Quantidade de bytes úteis

```text
used_bytes
=
layer_count × LP_SIZE
```

---

### Área reservada suficiente

```text
used_bytes
<=
params_bytes
```

---

### Blob final

```text
len(params_blob)
=
params_bytes
```

---

### Slots

```text
0 <= in_slot < len(slot_bases)

0 <= out_slot < len(slot_bases)
```

---

### ADD

```text
len(input_slots) == 2
```

e:

```text
pad_t = base do slot A

pad_b = base do slot B
```

---

# 179. Validações que poderiam ser acrescentadas futuramente

O código atual poderia ser endurecido posteriormente para verificar também:

```text
wptr dentro de WEIGHTS

bias_ptr dentro de BIAS

mul_ptr dentro de MUL

shift_ptr dentro de SHIFT

q6_ptr dentro de Q6
```

quando esses ponteiros forem utilizados.

---

# 180. Outra validação possível

Poderíamos confirmar:

```text
blob_offset
==
layer_index × LP_SIZE
```

durante cada iteração.

Hoje isso decorre naturalmente da construção sequencial.

---

# 181. Outra validação possível

Também seria possível garantir:

```text
used_bytes
==
len(layer_params) × LP_SIZE
```

explicitamente.

Novamente, o código atual já produz essa relação pela construção.

---

# 182. Um detalhe importante sobre `wptr`

Diferentemente de:

```text
bias_ptr
mul_ptr
shift_ptr
q6_ptr
```

que podem ser zero explicitamente quando não existem,

`wptr` é sempre:

```text
kernel_base + w_off
```

---

# 183. Consequência no relatório

Portanto não devemos usar:

```text
wptr == 0
```

como teste de existência de peso.

Para saber se um operador realmente usa `wptr`, é necessário interpretar:

```text
op_type
```

---

# 184. Exemplo

`ADD` pode possuir:

```text
w_off = 0

wptr = KERNEL_BASE
```

Mas o kernel ADD simplesmente não utiliza esse campo como peso.

---

# 185. Estrutura fixa versus campos opcionais

Esse comportamento é consequência direta de utilizar:

```text
uma estrutura fixa
```

para operações heterogêneas.

Todos os 29 campos existem fisicamente em todas as `LayerParams`, mesmo quando alguns são irrelevantes.

---

# 186. Benefício

O runtime pode trabalhar com:

```text
LP_SIZE fixo
```

e offsets fixos.

Não precisa lidar com estruturas variáveis.

---

# 187. Custo

Alguns campos contêm:

```text
0
```

ou valores sem significado para determinada operação.

O runtime precisa interpretar cada campo com base em:

```text
op_type
```

---

# 188. Exemplo do protocolo

```text
op_type = CONV
    ↓
kh = kernel height

op_type = ADD
    ↓
kh = multiplier A

op_type = MEAN
    ↓
kh = multiplier

op_type = SOFTMAX
    ↓
kh = input_beta_mul

op_type = QUANTIZE
    ↓
kh = multiplier
```

`params_blob.py` não precisa reinterpretar tudo isso.

Ele apenas garante que o valor preparado pelo módulo anterior seja colocado na posição correta.

---

# 189. Separação de responsabilidades entre os dois módulos

`layer_params.py` responde:

```text
qual valor deve ir em cada campo?
```

`params_blob.py` responde:

```text
como transformar esses campos
em uma estrutura binária
com ponteiros absolutos?
```

---

# 190. Exemplo

`layer_params.py`:

```python
{
    "w_off": 5000,
    "has_bias": True,
    "b_off": 256,
}
```

`params_blob.py`:

```text
wptr =
WEIGHTS_BASE + 5000

bias_ptr =
BIAS_BASE + 256
```

e finalmente:

```text
struct.pack(...)
```

---

# 191. Relação com `memory.py`

`memory.py` decide:

```text
WEIGHTS_BASE

BIAS_BASE

MUL_BASE

SHIFT_BASE

Q6_BASE

PARAMS_BASE
```

`params_blob.py` utiliza essas bases, mas não decide onde elas ficam.

---

# 192. Relação com `wat_generator.py`

Depois desta etapa, o gerador recebe:

```text
params_blob
```

já completamente pronto.

Ele não precisa:

```text
calcular ponteiros

interpretar slots

calcular offset de pesos

montar LayerParam
```

---

# 193. O gerador apenas posiciona o blob

Conceitualmente:

```wat
(data
    (i32.const PARAMS_BASE)
    "...params_blob..."
)
```

---

# 194. Separação desejada

```text
params_blob.py
    ↓
produz bytes corretos

wat_generator.py
    ↓
coloca esses bytes
no endereço correto
```

---

# 195. Isso reduz acoplamento

Se futuramente quisermos armazenar:

```text
params_blob
```

em outro formato de artefato, a lógica de construção da estrutura não depende da sintaxe WAT.

---

# 196. Fluxo completo dos endereços

```text
weights.py
    ↓
w_off

quantization.py
    ↓
mul_off
shift_off
q6_off

memory.py
    ↓
WEIGHTS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE

layer_params.py
    ↓
estrutura lógica

params_blob.py
    ↓
wptr
mul_ptr
shift_ptr
q6_ptr

WASM
```

---

# 197. Fluxo completo dos slots

```text
slots.py
    ↓
slot lógico

tensor_mapping.py
    ↓
tensor → slot

layer_params.py
    ↓
runtime slot

memory layout
    ↓
slot_bases

params_blob.py
    ↓
in_ptr / out_ptr
```

---

# 198. Visão completa do `PARAMS`

```text
PARAMS_BASE
   │
   ▼

┌─────────────────────────────┐
│ LayerParam 0                │
│ RGB565_TO_RGB888            │
│ 116 bytes                   │
├─────────────────────────────┤
│ LayerParam 1                │
│ primeira operação TFLite    │
│ 116 bytes                   │
├─────────────────────────────┤
│ LayerParam 2                │
│ 116 bytes                   │
├─────────────────────────────┤
│ ...                         │
├─────────────────────────────┤
│ LayerParam N-1              │
│ 116 bytes                   │
├─────────────────────────────┤
│ padding opcional            │
│ 00 00 00 ...                │
└─────────────────────────────┘
   │
   ▼
SLOT0_BASE
```

---

# 199. Papel no pipeline completo

```text
┌─────────────────────────────┐
│       layer_params.py       │
│                             │
│ dicionários estruturados    │
│ offsets relativos           │
│ slots                       │
│ parâmetros especiais        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│       params_blob.py        │
│                             │
│ valida slots                │
│ resolve ponteiros           │
│ struct.pack 29 × int32      │
│ concatena LayerParams       │
│ adiciona padding            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         params_blob         │
│                             │
│ bytes finais de PARAMS      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      wat_generator.py       │
│                             │
│ data @ PARAMS_BASE          │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│           WASM              │
│                             │
│ runtime lê LayerParam[]     │
└─────────────────────────────┘
```

---

# 200. Síntese

`params_blob.py` transforma a descrição lógica das operações em uma representação binária diretamente consumível pelo runtime WebAssembly.

A primeira responsabilidade é validar o uso dos slots, com atenção especial ao `ADD`, que possui duas entradas e reutiliza:

```text
pad_t
pad_b
```

como ponteiros dessas entradas.

A segunda responsabilidade é converter informações relativas:

```text
w_off

b_off

mul_off

shift_off

q6_off
```

em endereços absolutos:

```text
wptr

bias_ptr

mul_ptr

shift_ptr

q6_ptr
```

utilizando:

```text
BASE + OFFSET
```

A terceira responsabilidade é organizar exatamente 29 valores em cada `LayerParam`, obedecendo a uma ordem fixa e serializando-os como:

```text
29 × int32 little-endian
=
116 bytes
```

A quarta responsabilidade é concatenar todas essas estruturas:

```text
LayerParam[0]
LayerParam[1]
LayerParam[2]
...
```

e completar a região com bytes zero até:

```text
params_bytes
```

garantindo que o tamanho final seja exatamente aquele utilizado pelo planejamento da memória.

Assim, este módulo realiza a transformação:

```text
descrição Python da rede
          ↓
endereços absolutos
          ↓
estrutura binária fixa
          ↓
PARAMS
```

Depois dele, praticamente toda a engenharia semântica da extração já terminou.

O `wat_generator.py` não precisa mais entender como uma convolução, um ADD ou um SOFTMAX foi construído. Ele recebe simplesmente um bloco binário pronto para ser colocado em:

```text
PARAMS_BASE
```

junto aos demais blocos do modelo.
