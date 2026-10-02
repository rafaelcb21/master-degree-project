[English](10-operacoes-opcoes.md) | [Português (Brasil)](10-operacoes-opcoes.pt-BR.md)

> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.pt-BR.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.pt-BR.md). O corpo original foi mantido.

# 10 — Leitura das opções dos operadores (`operator_operations.py`)

## 1. Objetivo do módulo

O arquivo `extractor/operator_operations.py` é responsável por interpretar as opções específicas armazenadas nos operadores TFLite.

O grafo informa que determinada operação é, por exemplo:

```text
CONV_2D
```

mas isso ainda não informa:

```text
stride vertical
stride horizontal
dilatação vertical
dilatação horizontal
padding
ativação fundida
```

Da mesma forma, saber que uma operação é:

```text
DEPTHWISE_CONV_2D
```

não informa automaticamente:

```text
depth multiplier
```

Esses valores estão armazenados dentro das `BuiltinOptions` de cada operador.

Este módulo faz a transformação:

```text
BuiltinOptions do TFLite
          │
          ▼
operator_operations.py
          │
          ├── stride_h
          ├── stride_w
          ├── dil_h
          ├── dil_w
          ├── padding_kind
          ├── activation
          └── depth_mult
```

Além disso, o módulo implementa:

```python
same_padding(...)
```

que calcula explicitamente o padding necessário para reproduzir a semântica `SAME`.

---

# 2. Código atual

O módulo trabalha com estas estruturas do binding TFLite:

```python
from tflite import (
    ActivationFunctionType,
    AddOptions,
    Padding,
    Conv2DOptions,
    DepthwiseConv2DOptions,
    FullyConnectedOptions,
)
```

E define três códigos internos de ativação:

```python
ACT_NONE = 0
ACT_RELU = 1
ACT_RELU6 = 3
```

As funções principais são:

```text
parse_fused_activation()

parse_add_options()

padding_is_same()

parse_conv2d_options()

parse_dwconv2d_options()

parse_fc_options()

same_padding()
```

---

# 3. Papel arquitetural

Esse módulo funciona como uma camada de tradução entre:

```text
representação TFLite
```

e:

```text
representação interna do runtime
```

O TFLite utiliza objetos como:

```text
Conv2DOptions
DepthwiseConv2DOptions
FullyConnectedOptions
AddOptions
```

Já o restante do extrator prefere trabalhar com valores simples:

```python
stride_h = 1
stride_w = 1

dil_h = 1
dil_w = 1

padding_kind = 0

activation = ACT_RELU6
```

Assim:

```text
TFLite FlatBuffer
       │
       ▼
operator_operations.py
       │
       ▼
inteiros e booleanos simples
       │
       ▼
layer_params.py
```

---

# 4. Por que separar essa lógica?

Sem este módulo, `layer_params.py` precisaria conter código semelhante a:

```text
ler BuiltinOptions
instanciar Conv2DOptions
inicializar FlatBuffer
ler stride
ler dilation
ler padding
ler fused activation
```

para cada operação.

Isso misturaria duas responsabilidades:

```text
como interpretar TFLite
```

e:

```text
como construir LayerParam
```

A divisão atual é:

```text
operator_operations.py
    ↓
interpreta opções TFLite

layer_params.py
    ↓
utiliza os valores já interpretados
```

---

# 5. Constantes de ativação

O módulo define:

```python
ACT_NONE = 0
ACT_RELU = 1
ACT_RELU6 = 3
```

Esses valores constituem a representação interna utilizada pelo runtime.

---

# 6. Significado

```text
ACT_NONE = 0
```

representa:

```text
nenhuma ativação fundida
```

---

```text
ACT_RELU = 1
```

representa:

```text
ReLU
```

---

```text
ACT_RELU6 = 3
```

representa:

```text
ReLU6
```

---

# 7. Ativação fundida

No TFLite, determinadas operações podem incorporar uma ativação diretamente.

Conceitualmente:

```text
CONV_2D
   ↓
ReLU6
```

pode estar representado como uma única operação:

```text
CONV_2D
fused_activation = RELU6
```

Em vez de aparecerem dois operadores independentes.

---

# 8. Por que isso importa para o runtime?

Se a operação possui:

```text
ReLU6
```

fundido, o kernel precisa aplicar a saturação apropriada antes de gravar a saída.

Logo a informação precisa chegar à `LayerParam`.

Fluxo:

```text
TFLite
   │
   └── FusedActivationFunction()
                │
                ▼
parse_fused_activation()
                │
                ▼
ACT_RELU6
                │
                ▼
LayerParam.act
                │
                ▼
kernel WASM
```

---

# 9. Função `parse_fused_activation()`

A primeira função é:

```python
def parse_fused_activation(
    activation_value,
):
```

Seu objetivo é normalizar diferentes formas pelas quais o binding pode representar uma ativação.

---

# 10. Primeira estratégia

Inicialmente a função tenta comparar com:

```python
ActivationFunctionType.NONE
```

```python
ActivationFunctionType.RELU
```

```python
ActivationFunctionType.RELU6
```

---

# 11. Exemplo

Se:

```python
activation_value == (
    ActivationFunctionType.RELU6
)
```

o retorno será:

```python
ACT_RELU6
```

---

# 12. Por que existe `try/except`?

O binding Python do TFLite pode apresentar diferenças de empacotamento ou estrutura dependendo da versão utilizada.

Por isso o código primeiro tenta trabalhar semanticamente com:

```text
ActivationFunctionType
```

mas possui um segundo caminho baseado diretamente nos valores inteiros.

---

# 13. Fallback numérico

Se a primeira tentativa não funcionar, o código testa:

```python
if activation_value == 0:
    return ACT_NONE

if activation_value == 1:
    return ACT_RELU

if activation_value == 3:
    return ACT_RELU6
```

---

# 14. Duas camadas de compatibilidade

Portanto:

```text
primeira tentativa
      ↓
enum do binding TFLite

segunda tentativa
      ↓
valor numérico
```

Isso torna a rotina menos dependente da forma exata como o pacote Python expõe o enum.

---

# 15. Ativação desconhecida

Se nenhum caso for reconhecido:

```python
return ACT_NONE
```

Ou seja, o comportamento atual é conservador:

```text
ativação desconhecida
        ↓
ACT_NONE
```

---

# 16. Consequência importante

Essa estratégia evita interromper o extrator.

Entretanto, em um modelo futuro contendo uma ativação fundida diferente, como outra opção suportada pelo TFLite mas não implementada pelo runtime, o código atual poderia convertê-la silenciosamente para:

```text
ACT_NONE
```

Isso é uma característica importante da implementação atual.

---

# 17. Possível evolução futura

Em uma ferramenta mais genérica, poderia ser preferível:

```text
ativação conhecida
    ↓
converter

ativação desconhecida
    ↓
RuntimeError
```

Isso impediria gerar um artefato semanticamente diferente do modelo original.

No código atual, porém, preserva-se o comportamento existente.

---

# 18. Função `parse_add_options()`

A função:

```python
def parse_add_options(op):
```

extrai a ativação fundida de um operador:

```text
ADD
```

---

# 19. Por que o ADD possui opções?

Um `ADD` pode conceitualmente representar:

```text
A + B
```

mas também pode possuir:

```text
A + B
  ↓
ReLU
```

ou:

```text
A + B
  ↓
ReLU6
```

como ativação fundida.

---

# 20. Obtendo `BuiltinOptions`

A função começa com:

```python
builtin_options = (
    op.BuiltinOptions()
)
```

Esse objeto representa a posição dos dados específicos daquele operador dentro do FlatBuffer.

---

# 21. Verificação de `Bytes` e `Pos`

Depois:

```python
if (
    hasattr(
        builtin_options,
        "Bytes",
    )
    and hasattr(
        builtin_options,
        "Pos",
    )
):
```

O parser precisa dessas duas informações para inicializar o objeto de opções correto.

---

# 22. Significado conceitual

O objeto:

```text
builtin_options
```

funciona como referência para uma região dentro do buffer TFLite.

Os campos:

```text
Bytes
Pos
```

permitem que:

```text
AddOptions
```

interprete aquela região segundo seu schema.

---

# 23. Compatibilidade na construção de `AddOptions`

O código:

```python
options = (
    AddOptions.AddOptions()
    if hasattr(
        AddOptions,
        "AddOptions",
    )
    else AddOptions()
)
```

suporta duas possíveis formas do binding.

---

# 24. Primeira forma

Em alguns ambientes:

```text
AddOptions
    │
    └── AddOptions
```

Então:

```python
AddOptions.AddOptions()
```

cria a estrutura.

---

# 25. Segunda forma

Em outros:

```python
AddOptions()
```

já é diretamente a classe instanciável.

---

# 26. Mesmo problema observado no carregamento do modelo

Essa lógica é semelhante àquela vista em:

```text
model_loader.py
```

onde o binding poderia expor:

```text
GetRootAsModel
```

em diferentes níveis.

O objetivo aqui é novamente reduzir dependência de uma única organização do pacote Python.

---

# 27. Inicialização das opções

Depois:

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

Agora:

```text
options
```

passa a interpretar aquela região do FlatBuffer como:

```text
AddOptions
```

---

# 28. Leitura da ativação

Então:

```python
options
.FusedActivationFunction()
```

é convertido para inteiro:

```python
int(...)
```

e passado para:

```python
parse_fused_activation(...)
```

---

# 29. Retorno do ADD

O resultado final é um dos códigos:

```text
ACT_NONE

ACT_RELU

ACT_RELU6
```

---

# 30. Falha de leitura

Se qualquer etapa gerar exceção:

```python
except Exception:
    pass
```

e a função retorna:

```python
ACT_NONE
```

---

# 31. Filosofia de fallback

O padrão deste módulo é:

```text
tentar extrair a opção real
        │
        ├── sucesso → usar valor
        │
        └── falha → usar default seguro
```

Para o ADD:

```text
default = ACT_NONE
```

---

# 32. Função `padding_is_same()`

A função:

```python
def padding_is_same(
    padding_value,
):
```

normaliza a identificação do padding:

```text
SAME
```

---

# 33. Primeira comparação

O código tenta:

```python
padding_value
==
Padding.SAME
```

---

# 34. Fallback numérico

Caso haja problema ao acessar o enum:

```python
except Exception:
    return padding_value == 0
```

Assim, a representação numérica:

```text
0
```

é tratada como:

```text
SAME
```

na implementação atual.

---

# 35. Resultado booleano

A função retorna:

```text
True
```

para `SAME`,

ou:

```text
False
```

para outro tipo de padding.

---

# 36. Por que usar uma função separada?

Sem ela, tanto:

```text
CONV_2D
```

quanto:

```text
DEPTHWISE_CONV_2D
```

teriam que repetir a lógica de compatibilidade com o enum.

Centralizar isso evita duplicação.

---

# 37. Convenção interna de padding

As funções de convolução transformam o booleano em:

```python
padding_kind = (
    0 if padding_same
    else 1
)
```

Assim:

```text
padding_kind = 0
    ↓
SAME

padding_kind = 1
    ↓
não-SAME
```

No fluxo atual, o segundo caso corresponde à alternativa utilizada pela operação para padding não `SAME`.

---

# 38. Importante

O valor:

```text
0
```

em `padding_kind`

não é necessariamente utilizado como o próprio enum TFLite.

É uma convenção interna do extrator/runtime.

A tradução é:

```text
TFLite padding
      ↓
padding_is_same()
      ↓
booleano
      ↓
padding_kind interno
```

---

# 39. Função `parse_conv2d_options()`

Essa função interpreta as opções de:

```text
CONV_2D
```

---

# 40. Valores retornados

O retorno normal possui:

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
)
```

---

# 41. Visualmente

```text
Conv2DOptions
      │
      ├── StrideH
      ├── StrideW
      ├── DilationHFactor
      ├── DilationWFactor
      ├── Padding
      └── FusedActivationFunction
             │
             ▼
      tuple Python simples
```

---

# 42. Obtenção das opções

Novamente:

```python
builtin_options = (
    op.BuiltinOptions()
)
```

seguido pela verificação de:

```text
Bytes
Pos
```

---

# 43. Compatibilidade do binding

A estrutura é criada com:

```python
options = (
    Conv2DOptions.Conv2DOptions()
    if hasattr(
        Conv2DOptions,
        "Conv2DOptions",
    )
    else Conv2DOptions()
)
```

O objetivo é suportar ambas as formas conhecidas do binding.

---

# 44. Inicialização

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

Depois dessa chamada, os métodos específicos podem ser consultados.

---

# 45. `stride_h`

O stride vertical é:

```python
stride_h = int(
    options.StrideH()
)
```

---

# 46. `stride_w`

O horizontal:

```python
stride_w = int(
    options.StrideW()
)
```

---

# 47. O que é stride?

O stride indica quanto o kernel avança entre duas posições consecutivas.

Exemplo:

```text
stride = 1
```

significa:

```text
posição 0
posição 1
posição 2
posição 3
...
```

---

# 48. Stride 2

Com:

```text
stride = 2
```

o kernel avança:

```text
posição 0
posição 2
posição 4
posição 6
...
```

Isso reduz espacialmente a saída.

---

# 49. Strides independentes

O formato permite:

```text
stride_h
```

e:

```text
stride_w
```

diferentes.

Embora arquiteturas comuns frequentemente utilizem:

```text
stride_h == stride_w
```

o extrator não impõe isso.

---

# 50. Dilatação

A função tenta ler:

```python
options.DilationHFactor()
```

e:

```python
options.DilationWFactor()
```

---

# 51. Fallback da dilatação

Se essa leitura falhar:

```python
dil_h = 1
dil_w = 1
```

---

# 52. Por que `1` é o valor padrão?

Dilatação 1 representa:

```text
kernel normal
```

sem espaçamento adicional entre seus elementos.

---

# 53. Exemplo com kernel 3

Para:

```text
kernel = 3
dilation = 1
```

os pontos utilizados são:

```text
x x x
```

---

# 54. Dilatação 2

Para:

```text
kernel = 3
dilation = 2
```

conceitualmente:

```text
x . x . x
```

O kernel possui três coeficientes, mas cobre uma região efetiva maior.

---

# 55. Padding

O código lê:

```python
options.Padding()
```

converte para inteiro e passa para:

```python
padding_is_same(...)
```

---

# 56. Resultado

```python
padding_same = (
    padding_is_same(...)
)
```

produz:

```text
True
```

ou:

```text
False
```

---

# 57. Conversão para `padding_kind`

Depois:

```python
padding_kind = (
    0 if padding_same
    else 1
)
```

---

# 58. Ativação

A ativação fundida é lida por:

```python
parse_fused_activation(
    int(
        options
        .FusedActivationFunction()
    )
)
```

---

# 59. Retorno normal

A função retorna:

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
)
```

---

# 60. Exemplo

Uma convolução pode resultar em:

```python
(
    2,
    2,
    1,
    1,
    0,
    ACT_RELU6,
)
```

Isso representa:

```text
stride = 2 × 2

dilation = 1 × 1

padding = SAME

activation = ReLU6
```

---

# 61. Fallback de `CONV_2D`

Se a leitura das opções falhar por completo:

```python
return (
    1,
    1,
    1,
    1,
    1,
    ACT_NONE,
)
```

---

# 62. Interpretação do fallback

```text
stride_h = 1

stride_w = 1

dil_h = 1

dil_w = 1

padding_kind = 1

activation = NONE
```

---

# 63. Característica importante

O fallback não representa necessariamente as opções originais do modelo.

Ele é apenas o conjunto padrão escolhido pela implementação quando as opções não podem ser interpretadas.

Isso evita falha imediata, mas pode esconder uma incompatibilidade em um modelo diferente.

---

# 64. Função `parse_dwconv2d_options()`

Essa função é equivalente à de `CONV_2D`, mas interpreta:

```text
DEPTHWISE_CONV_2D
```

e possui um parâmetro adicional:

```text
depth_multiplier
```

---

# 65. Retorno

```python
(
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    padding_kind,
    activation,
    depth_mult,
)
```

---

# 66. Construção das opções

A classe utilizada é:

```text
DepthwiseConv2DOptions
```

novamente com compatibilidade entre:

```python
DepthwiseConv2DOptions
.DepthwiseConv2DOptions()
```

e:

```python
DepthwiseConv2DOptions()
```

---

# 67. Stride e dilation

A leitura ocorre da mesma forma que em `CONV_2D`.

Logo:

```text
StrideH
StrideW
DilationHFactor
DilationWFactor
```

possuem a mesma interpretação.

---

# 68. `depth_mult`

O valor adicional é:

```python
depth_mult = int(
    options.DepthMultiplier()
)
```

---

# 69. O que representa o depth multiplier?

Na convolução depthwise, os filtros são aplicados separadamente sobre os canais de entrada.

O `depth_multiplier` informa quantos canais de saída são produzidos para cada canal de entrada.

Conceitualmente:

```text
Cout =
Cin × depth_multiplier
```

---

# 70. Exemplo

Se:

```text
Cin = 32
depth_multiplier = 1
```

então:

```text
Cout = 32
```

---

# 71. Exemplo com multiplier 2

Se:

```text
Cin = 32
depth_multiplier = 2
```

então:

```text
Cout = 64
```

---

# 72. MobileNetV2

No padrão de depthwise convolutions empregado por MobileNetV2, o caso comum é:

```text
depth_multiplier = 1
```

mas o parser preserva o valor que estiver no modelo.

---

# 73. Padding e ativação

São processados exatamente como em `CONV_2D`:

```text
Padding()
    ↓
padding_is_same()
    ↓
padding_kind
```

e:

```text
FusedActivationFunction()
    ↓
parse_fused_activation()
    ↓
activation
```

---

# 74. Fallback do depthwise

Se ocorrer falha:

```python
return (
    1,
    1,
    1,
    1,
    1,
    ACT_NONE,
    1,
)
```

---

# 75. Interpretação

```text
stride = 1

dilation = 1

padding_kind = 1

activation = NONE

depth_multiplier = 1
```

---

# 76. Função `parse_fc_options()`

Essa função interpreta as opções de:

```text
FULLY_CONNECTED
```

---

# 77. O que é extraído?

Na implementação atual, apenas:

```text
fused activation
```

é necessária.

---

# 78. Construção de `FullyConnectedOptions`

A mesma técnica de compatibilidade é utilizada:

```python
options = (
    FullyConnectedOptions
    .FullyConnectedOptions()
    if hasattr(
        FullyConnectedOptions,
        "FullyConnectedOptions",
    )
    else FullyConnectedOptions()
)
```

---

# 79. Inicialização

```python
options.Init(
    builtin_options.Bytes,
    builtin_options.Pos,
)
```

---

# 80. Retorno

Depois:

```python
return (
    parse_fused_activation(
        int(
            options
            .FusedActivationFunction()
        )
    )
)
```

---

# 81. Fallback

Em caso de falha:

```python
return ACT_NONE
```

---

# 82. Comparação das funções de parsing

| Operação            | Valores extraídos                                     |
| ------------------- | ----------------------------------------------------- |
| `ADD`               | ativação                                              |
| `CONV_2D`           | stride, dilation, padding, ativação                   |
| `DEPTHWISE_CONV_2D` | stride, dilation, padding, ativação, depth multiplier |
| `FULLY_CONNECTED`   | ativação                                              |

---

# 83. Por que `SOFTMAX`, `MEAN` e `QUANTIZE` não aparecem aqui?

Porque suas informações necessárias são tratadas em outras partes do pipeline.

Este arquivo concentra as opções específicas das operações que realmente exigem esses objetos `BuiltinOptions`.

---

# 84. Função `same_padding()`

A última função é matematicamente diferente das anteriores.

Ela não lê o FlatBuffer.

Recebe diretamente:

```text
dimensões da entrada
kernel
stride
dilation
```

e calcula:

```text
padding explícito
+
shape da saída
```

---

# 85. Assinatura

```python
def same_padding(
    in_h,
    in_w,
    kernel_h,
    kernel_w,
    stride_h,
    stride_w,
    dil_h=1,
    dil_w=1,
):
```

---

# 86. Entradas

### `in_h`

Altura da entrada.

### `in_w`

Largura da entrada.

### `kernel_h`

Altura do kernel.

### `kernel_w`

Largura do kernel.

### `stride_h`

Stride vertical.

### `stride_w`

Stride horizontal.

### `dil_h`

Dilatação vertical.

### `dil_w`

Dilatação horizontal.

---

# 87. Saídas

A função retorna:

```python
(
    pad_top,
    pad_bottom,
    pad_left,
    pad_right,
    out_h,
    out_w,
)
```

---

# 88. Por que calcular explicitamente o padding?

No TFLite, saber apenas:

```text
padding = SAME
```

não informa diretamente quantas posições precisam ser adicionadas em:

```text
top
bottom
left
right
```

O kernel WASM precisa dos valores concretos.

Portanto:

```text
SAME
   ↓
same_padding()
   ↓
pad_top
pad_bottom
pad_left
pad_right
```

---

# 89. Cálculo da altura da saída

Primeiro:

```python
out_h = (
    in_h + stride_h - 1
) // stride_h
```

Isso equivale a:

```text
out_h =
ceil(
    in_h / stride_h
)
```

para inteiros positivos.

---

# 90. Por que essa fórmula implementa `ceil`?

Considere:

```text
in_h = 5
stride_h = 2
```

Então:

```text
(5 + 2 - 1) // 2
=
6 // 2
=
3
```

E:

```text
ceil(5 / 2)
=
3
```

---

# 91. Largura da saída

O mesmo é feito:

```python
out_w = (
    in_w + stride_w - 1
) // stride_w
```

---

# 92. Exemplo com entrada 128 × 128 e stride 2

```text
out_h =
ceil(128 / 2)
=
64
```

```text
out_w =
ceil(128 / 2)
=
64
```

---

# 93. Kernel efetivo

A dilatação altera a área efetivamente coberta pelo kernel.

O código calcula:

```python
effective_kernel_h = (
    (kernel_h - 1)
    * dil_h
    + 1
)
```

---

# 94. Largura efetiva

Da mesma maneira:

```python
effective_kernel_w = (
    (kernel_w - 1)
    * dil_w
    + 1
)
```

---

# 95. Kernel 3 com dilatação 1

```text
effective_kernel =
(3 - 1) × 1 + 1
=
3
```

Nenhuma mudança.

---

# 96. Kernel 3 com dilatação 2

```text
effective_kernel =
(3 - 1) × 2 + 1
=
5
```

Visualmente:

```text
x . x . x
```

São três coeficientes cobrindo cinco posições.

---

# 97. Kernel 3 com dilatação 3

```text
effective_kernel =
(3 - 1) × 3 + 1
=
7
```

Visualmente:

```text
x . . x . . x
```

---

# 98. Padding total vertical

Depois:

```python
pad_h_total = max(
    0,
    (
        (out_h - 1)
        * stride_h
        + effective_kernel_h
        - in_h
    ),
)
```

---

# 99. Intuição da fórmula

O termo:

```text
(out_h - 1) × stride_h
```

representa a posição inicial do último kernel.

Ao adicionar:

```text
effective_kernel_h
```

obtemos até onde esse kernel precisa alcançar.

Subtrair:

```text
in_h
```

revela quanto falta fora da entrada original.

---

# 100. Uso de `max(0, ...)`

Isso garante que:

```text
padding total
```

nunca seja negativo.

Se a geometria não exigir preenchimento:

```text
padding = 0
```

---

# 101. Padding horizontal

O mesmo cálculo ocorre:

```python
pad_w_total = max(
    0,
    (
        (out_w - 1)
        * stride_w
        + effective_kernel_w
        - in_w
    ),
)
```

---

# 102. Divisão vertical

Depois:

```python
pad_top = (
    pad_h_total // 2
)
```

e:

```python
pad_bottom = (
    pad_h_total - pad_top
)
```

---

# 103. Padding par

Se:

```text
pad_h_total = 2
```

então:

```text
pad_top = 1

pad_bottom = 1
```

---

# 104. Padding ímpar

Se:

```text
pad_h_total = 1
```

então:

```text
pad_top = 0

pad_bottom = 1
```

---

# 105. Consequência

Quando o padding total é ímpar, o elemento extra fica no:

```text
bottom
```

na dimensão vertical.

---

# 106. Divisão horizontal

A mesma lógica é usada:

```python
pad_left = (
    pad_w_total // 2
)
```

```python
pad_right = (
    pad_w_total - pad_left
)
```

---

# 107. Padding ímpar horizontal

Se:

```text
pad_w_total = 1
```

então:

```text
pad_left = 0

pad_right = 1
```

---

# 108. Exemplo 1 — kernel 3×3, stride 1

Considere:

```text
entrada = 128 × 128

kernel = 3 × 3

stride = 1 × 1

dilation = 1 × 1
```

---

# 109. Saída

```text
out_h =
ceil(128 / 1)
=
128
```

```text
out_w =
128
```

---

# 110. Kernel efetivo

```text
effective_kernel_h = 3

effective_kernel_w = 3
```

---

# 111. Padding vertical

```text
pad_h_total =
(128 - 1) × 1
+ 3
- 128

=
127 + 3 - 128

=
2
```

---

# 112. Divisão

```text
pad_top = 1

pad_bottom = 1
```

---

# 113. Horizontal

Da mesma forma:

```text
pad_left = 1

pad_right = 1
```

---

# 114. Resultado

```python
(
    1,
    1,
    1,
    1,
    128,
    128,
)
```

---

# 115. Visualmente

```text
entrada 128×128
       │
       │ SAME
       ▼

padding:
top    = 1
bottom = 1
left   = 1
right  = 1

       │
       ▼
saída 128×128
```

---

# 116. Exemplo 2 — kernel 3×3, stride 2

Considere:

```text
entrada = 128 × 128

kernel = 3 × 3

stride = 2 × 2
```

---

# 117. Shape da saída

```text
out_h =
ceil(128 / 2)
=
64
```

e:

```text
out_w = 64
```

---

# 118. Padding total

```text
pad_h_total =
(64 - 1) × 2
+ 3
- 128

=
126 + 3 - 128

=
1
```

---

# 119. Divisão vertical

```text
pad_top = 0

pad_bottom = 1
```

---

# 120. Horizontal

```text
pad_left = 0

pad_right = 1
```

---

# 121. Resultado

```python
(
    0,
    1,
    0,
    1,
    64,
    64,
)
```

---

# 122. Assimetria é esperada

Nesse exemplo:

```text
top ≠ bottom
```

e:

```text
left ≠ right
```

Isso não representa erro.

Quando o padding necessário é ímpar, a distribuição precisa necessariamente ser assimétrica.

---

# 123. Exemplo 3 — dilatação

Considere:

```text
entrada = 10 × 10

kernel = 3 × 3

stride = 1

dilation = 2
```

---

# 124. Kernel efetivo

```text
effective_kernel =
(3 - 1) × 2 + 1

=
5
```

---

# 125. Saída SAME

```text
out_h = 10

out_w = 10
```

---

# 126. Padding total

```text
pad_total =
(10 - 1)
+ 5
- 10

=
4
```

---

# 127. Divisão

```text
top = 2

bottom = 2

left = 2

right = 2
```

A dilatação aumenta o padding necessário porque aumenta o tamanho efetivo do kernel.

---

# 128. Relação com `padding_kind`

`same_padding()` não recebe:

```text
padding_kind
```

Ela é chamada apenas quando o código superior já determinou que a operação precisa de `SAME`.

A lógica posterior é conceitualmente:

```text
padding_kind == SAME?
        │
        ├── sim
        │    ↓
        │ same_padding(...)
        │    ↓
        │ top/bottom/left/right
        │
        └── não
             ↓
           padding zero
           ou tratamento correspondente
```

---

# 129. Relação com `layer_params.py`

`layer_params.py` utiliza esses valores para preencher campos como:

```text
stride_h
stride_w

dil_h
dil_w

pad_t
pad_b
pad_l
pad_r

act
```

---

# 130. Exemplo de transformação

TFLite fornece:

```text
CONV_2D

StrideH = 2
StrideW = 2

Dilation = 1

Padding = SAME

FusedActivation = RELU6
```

`operator_operations.py` devolve:

```text
stride_h = 2
stride_w = 2

dil_h = 1
dil_w = 1

padding_kind = 0

activation = ACT_RELU6
```

Depois:

```text
same_padding()
```

pode produzir:

```text
pad_t = 0
pad_b = 1
pad_l = 0
pad_r = 1
```

Finalmente `layer_params.py` reúne tudo.

---

# 131. Fluxo completo

```text
TFLite Operator
      │
      ▼
BuiltinOptions
      │
      ▼
operator_operations.py
      │
      ├── stride
      ├── dilation
      ├── padding kind
      ├── activation
      └── depth multiplier
      │
      ▼
same_padding()
      │
      ├── pad_top
      ├── pad_bottom
      ├── pad_left
      ├── pad_right
      ├── out_h
      └── out_w
      │
      ▼
layer_params.py
```

---

# 132. Por que calcular `out_h` e `out_w` aqui?

O shape de saída existe no próprio TFLite, mas o runtime precisa que a geometria utilizada pelo kernel seja coerente com:

```text
input
kernel
stride
dilation
padding
```

A função retorna:

```text
out_h
out_w
```

como parte do cálculo matemático do `SAME`.

Isso permite utilizar a mesma lógica para preencher a estrutura de execução.

---

# 133. Distinção entre shape do tensor e shape calculado

Existem portanto duas possíveis fontes:

```text
Tensor.ShapeAsNumpy()
```

e:

```text
same_padding(...)
```

A primeira descreve o modelo.

A segunda deriva a geometria a partir dos parâmetros da operação.

Essa redundância também pode servir como mecanismo de validação futura.

---

# 134. Possível validação futura

Poderíamos verificar:

```text
out_h calculado
==
altura do tensor de saída
```

e:

```text
out_w calculado
==
largura do tensor de saída
```

Caso contrário:

```text
RuntimeError
```

Isso permitiria detectar inconsistências de parsing ou implementação.

---

# 135. Tratamento de exceções

Uma característica marcante deste módulo é o uso de:

```python
except Exception:
    pass
```

em vários parsers.

---

# 136. Benefício

Isso aumenta a compatibilidade com diferenças entre versões do binding.

O pipeline não depende de cada método estar disponível exatamente da mesma forma.

---

# 137. Custo dessa estratégia

Por outro lado, uma exceção inesperada também pode ser convertida silenciosamente em um valor padrão.

Exemplo:

```text
erro ao interpretar Conv2DOptions
       ↓
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
```

---

# 138. Implicação

Para o modelo atual, cuja saída foi validada, essa estratégia preserva o comportamento do código original.

Para uma ferramenta genérica futura, será interessante separar:

```text
diferença conhecida do binding
```

de:

```text
erro real no modelo
```

---

# 139. Estratégia futura possível

Em vez de:

```python
except Exception:
    pass
```

poderíamos capturar apenas exceções específicas.

Ou utilizar validações explícitas:

```text
BuiltinOptions ausente
    ↓
fallback permitido

campo obrigatório ausente
    ↓
erro
```

---

# 140. Por que não alterar agora?

O objetivo desta etapa de refatoração e documentação é primeiro:

```text
preservar o comportamento
```

e tornar explícitas as decisões existentes.

Modificar simultaneamente todos os fallbacks dificultaria saber se diferenças posteriores vêm de:

```text
refatoração
```

ou:

```text
mudança semântica
```

---

# 141. Separação entre parsing e semântica do kernel

Este módulo conhece:

```text
StrideH
StrideW
Dilation
Padding
Activation
DepthMultiplier
```

mas não conhece:

```text
como fazer uma convolução em WAT
```

Essa separação é importante.

---

# 142. Ele não executa a convolução

`parse_conv2d_options()` apenas produz:

```text
parâmetros
```

Não existe aqui:

```text
loop em H
loop em W
loop em canais
multiplicação peso × entrada
acumulador
requantização
```

Essas operações pertencem ao runtime WAT.

---

# 143. Da mesma forma para depthwise

Este módulo descobre:

```text
depth_multiplier
```

mas não decide como indexar:

```text
input channel
output channel
weight channel
```

Isso pertence ao kernel `DEPTHWISE_CONV_2D`.

---

# 144. E para ativação

O módulo retorna:

```text
ACT_RELU6
```

mas não calcula:

```text
min(max(x, 0), 6)
```

nem sua versão quantizada.

A execução pertence ao runtime.

---

# 145. Relação com `quantization.py`

Quando:

```text
activation = ACT_RELU6
```

a execução também depende do:

```text
Q6
```

calculado por `quantization.py`.

Portanto:

```text
operator_operations.py
        │
        └── "esta camada usa ReLU6"

quantization.py
        │
        └── "este é o valor quantizado correspondente a 6"

layer_params.py
        │
        └── combina ambos
```

---

# 146. Exemplo

Uma camada pode receber:

```text
activation = ACT_RELU6
```

e:

```text
q6_ptr = endereço da tabela Q6
```

Então o kernel sabe:

```text
aplicar limite superior
usando Q6 correspondente
```

---

# 147. Relação com flags

O módulo não define diretamente:

```text
FLAG_PADDING_SAME
```

Essa representação pertence à camada de `LayerParam`.

Aqui é produzido apenas:

```text
padding_kind
```

---

# 148. Conversão posterior

Conceitualmente:

```text
padding_kind == 0
       ↓
SAME
       ↓
FLAG_PADDING_SAME
```

Essa transformação pertence à construção da camada.

---

# 149. Por que não retornar diretamente o flag?

Porque este módulo deve permanecer o mais próximo possível do conceito da operação:

```text
qual é o tipo de padding?
```

A escolha de bits dentro de:

```text
LayerParam.flags
```

é específica da representação do runtime.

---

# 150. Estrutura modular

```text
operator_operations.py
      ↓
semântica da opção

layer_params.py
      ↓
codificação da opção

params_blob.py
      ↓
serialização da codificação

WAT
      ↓
execução
```

---

# 151. Fallbacks atuais resumidos

## Ativação desconhecida

```text
ACT_NONE
```

## ADD não interpretável

```text
ACT_NONE
```

## CONV não interpretável

```text
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
```

## DEPTHWISE não interpretável

```text
stride = 1
dilation = 1
padding_kind = 1
activation = NONE
depth_multiplier = 1
```

## FC não interpretável

```text
ACT_NONE
```

---

# 152. Por que documentar os defaults?

Porque eles influenciam diretamente o artefato gerado.

Se uma opção não for lida corretamente, o runtime não recebe:

```text
None
```

Ele recebe valores concretos.

Portanto o comportamento resultante continua definido, embora possa não corresponder ao modelo pretendido.

---

# 153. Invariantes esperados

Para operações suportadas do modelo atual, espera-se:

```text
stride_h >= 1

stride_w >= 1

dil_h >= 1

dil_w >= 1
```

---

# 154. Para depthwise

Também:

```text
depth_mult >= 1
```

---

# 155. Ativação

O runtime atual espera um dos valores:

```text
ACT_NONE

ACT_RELU

ACT_RELU6
```

---

# 156. Padding

O código atual reduz o estado relevante a:

```text
SAME
```

ou:

```text
não-SAME
```

através de:

```python
padding_is_same()
```

---

# 157. `same_padding()` e valores positivos

A função pressupõe dimensionalidades coerentes como:

```text
in_h > 0

in_w > 0

kernel_h > 0

kernel_w > 0

stride_h > 0

stride_w > 0

dil_h > 0

dil_w > 0
```

O código não valida explicitamente essas condições.

---

# 158. Stride zero

Por exemplo, se:

```text
stride_h = 0
```

a função acabaria tentando uma divisão por zero.

Isso não é esperado em um modelo TFLite válido utilizado pelo projeto.

---

# 159. Kernel zero

Da mesma maneira, um kernel com dimensão zero produziria uma geometria sem sentido.

Essa validação não pertence à implementação atual.

---

# 160. Exemplo completo de uma CONV

Suponha:

```text
input:
1 × 128 × 128 × 3

kernel:
3 × 3

stride:
2 × 2

dilation:
1 × 1

padding:
SAME

activation:
ReLU6
```

---

# 161. Parsing

`parse_conv2d_options()` retorna:

```python
(
    2,
    2,
    1,
    1,
    0,
    ACT_RELU6,
)
```

---

# 162. Padding

`same_padding()` recebe:

```python
same_padding(
    128,
    128,
    3,
    3,
    2,
    2,
    1,
    1,
)
```

---

# 163. Resultado

```text
pad_top = 0

pad_bottom = 1

pad_left = 0

pad_right = 1

out_h = 64

out_w = 64
```

---

# 164. Informações entregues para `LayerParam`

Conceitualmente:

```text
stride_h = 2
stride_w = 2

dil_h = 1
dil_w = 1

pad_t = 0
pad_b = 1
pad_l = 0
pad_r = 1

activation = ACT_RELU6

out_h = 64
out_w = 64
```

---

# 165. Runtime

Essas informações permitem que o kernel WAT saiba:

```text
onde posicionar o kernel

quanto avançar

quando acessar padding

quantas posições produzir

qual ativação aplicar
```

---

# 166. Exemplo completo de Depthwise

Suponha:

```text
input:
1 × 64 × 64 × 32

kernel:
3 × 3

stride:
1

dilation:
1

padding:
SAME

depth_multiplier:
1

activation:
ReLU6
```

---

# 167. Parsing

```python
(
    1,
    1,
    1,
    1,
    0,
    ACT_RELU6,
    1,
)
```

---

# 168. Padding

```text
top = 1
bottom = 1
left = 1
right = 1
```

---

# 169. Saída espacial

```text
64 × 64
```

---

# 170. Número de canais

Com:

```text
Cin = 32

depth_multiplier = 1
```

temos:

```text
Cout = 32
```

---

# 171. Exemplo de FC

Uma `FULLY_CONNECTED` pode possuir:

```text
fused activation = NONE
```

Então:

```python
parse_fc_options(...)
```

retorna:

```python
ACT_NONE
```

Não há stride, dilation ou padding para essa representação.

---

# 172. Exemplo de ADD

Se:

```text
ADD
+
ReLU6
```

estiver fundido:

```python
parse_add_options(...)
```

retorna:

```python
ACT_RELU6
```

Essa informação será usada junto aos parâmetros específicos de quantização calculados para o ADD.

---

# 173. O que este módulo deliberadamente não faz

`operator_operations.py` não:

```text
lê pesos

lê bias

calcula quantização

calcula multiplier

calcula shift

calcula Q6

aloca slots

calcula endereços de memória

serializa LayerParam

gera WAT
```

---

# 174. Responsabilidade exata

Ele responde:

```text
quais são as opções operacionais
que descrevem como esta camada deve executar?
```

---

# 175. Tipos de informação tratados

```text
geometria
    ↓
stride
dilation
padding

ativação
    ↓
NONE
RELU
RELU6

depthwise
    ↓
depth_multiplier
```

---

# 176. Relação com outros módulos

```text
TFLite
  │
  ▼
operator_operations.py
  │
  ├── geometry
  ├── activation
  └── padding
  │
  ▼
layer_params.py
```

Enquanto:

```text
quantization.py
  │
  ├── multiplier
  ├── shift
  └── Q6
  │
  ▼
layer_params.py
```

E:

```text
memory.py
  │
  └── addresses
       │
       ▼
layer_params.py
```

---

# 177. `layer_params.py` como ponto de convergência

Isso mostra por que o próximo módulo será especialmente importante.

Ele reúne:

```text
graph
slots
tensor mapping
weights
quantization
memory
operator options
```

em uma estrutura única.

Visualmente:

```text
                graph.py
                   │
                slots.py
                   │
           tensor_mapping.py
                   │
                   ▼
weights.py ───► layer_params.py ◄── operator_operations.py
                   ▲
                   │
quantization.py ───┤
                   │
memory.py ─────────┘
```

---

# 178. Possível questão de nomenclatura

O nome:

```text
operator_operations.py
```

funciona, mas semanticamente o módulo faz principalmente parsing de:

```text
operator options
```

e cálculo de padding.

Por isso um nome como:

```text
operator_options.py
```

também descreveria bem sua função.

Entretanto, a documentação deve seguir o nome efetivamente utilizado no projeto enquanto ele permanecer:

```text
operator_operations.py
```

---

# 179. Resumo das funções

| Função                     | Responsabilidade                              |
| -------------------------- | --------------------------------------------- |
| `parse_fused_activation()` | Converter ativação TFLite para código interno |
| `parse_add_options()`      | Extrair ativação do ADD                       |
| `padding_is_same()`        | Identificar padding SAME                      |
| `parse_conv2d_options()`   | Extrair opções da CONV_2D                     |
| `parse_dwconv2d_options()` | Extrair opções da DEPTHWISE_CONV_2D           |
| `parse_fc_options()`       | Extrair ativação da FULLY_CONNECTED           |
| `same_padding()`           | Calcular padding explícito e shape de saída   |

---

# 180. Resumo das constantes

| Constante   | Significado              |
| ----------- | ------------------------ |
| `ACT_NONE`  | Nenhuma ativação fundida |
| `ACT_RELU`  | ReLU                     |
| `ACT_RELU6` | ReLU6                    |

---

# 181. Resumo do parsing de CONV

```text
Conv2DOptions
      │
      ├── StrideH
      ├── StrideW
      ├── DilationH
      ├── DilationW
      ├── Padding
      └── Activation
             │
             ▼
(
 stride_h,
 stride_w,
 dil_h,
 dil_w,
 padding_kind,
 activation
)
```

---

# 182. Resumo do parsing de Depthwise

```text
DepthwiseConv2DOptions
          │
          ├── StrideH
          ├── StrideW
          ├── DilationH
          ├── DilationW
          ├── Padding
          ├── Activation
          └── DepthMultiplier
                 │
                 ▼
(
 stride_h,
 stride_w,
 dil_h,
 dil_w,
 padding_kind,
 activation,
 depth_mult
)
```

---

# 183. Resumo de `same_padding()`

```text
entrada
kernel
stride
dilation
    │
    ▼
kernel efetivo
    │
    ▼
shape SAME da saída
    │
    ▼
padding total
    │
    ├── top
    ├── bottom
    ├── left
    └── right
```

---

# 184. Fórmulas principais

## Shape da saída

```text
out_h =
ceil(in_h / stride_h)

out_w =
ceil(in_w / stride_w)
```

Implementadas como:

```text
(in + stride - 1) // stride
```

---

## Kernel efetivo

```text
effective_kernel_h =
(kernel_h - 1) × dil_h + 1
```

```text
effective_kernel_w =
(kernel_w - 1) × dil_w + 1
```

---

## Padding total

```text
pad_h_total =
max(
    0,
    (out_h - 1) × stride_h
    + effective_kernel_h
    - in_h
)
```

```text
pad_w_total =
max(
    0,
    (out_w - 1) × stride_w
    + effective_kernel_w
    - in_w
)
```

---

## Distribuição

```text
pad_top =
pad_h_total // 2
```

```text
pad_bottom =
pad_h_total - pad_top
```

```text
pad_left =
pad_w_total // 2
```

```text
pad_right =
pad_w_total - pad_left
```

---

# 185. Síntese

`operator_operations.py` transforma a configuração específica armazenada nos operadores TFLite em uma representação simples utilizada pelo restante do extrator.

Sua primeira responsabilidade é interpretar:

```text
ativação fundida
```

normalizando:

```text
NONE
RELU
RELU6
```

para os códigos internos:

```text
ACT_NONE
ACT_RELU
ACT_RELU6
```

Sua segunda responsabilidade é interpretar as opções geométricas das convoluções:

```text
stride
dilation
padding
```

e, no caso da convolução depthwise:

```text
depth_multiplier
```

Sua terceira responsabilidade é transformar a descrição abstrata:

```text
padding = SAME
```

em valores concretos:

```text
pad_top
pad_bottom
pad_left
pad_right
out_h
out_w
```

que podem ser utilizados diretamente pelo kernel WebAssembly.

Assim, o módulo atua como fronteira entre:

```text
schema específico do TFLite
```

e:

```text
representação operacional do runtime
```

sem conhecer pesos, quantização, memória ou o código WAT propriamente dito.

O resultado é que `layer_params.py` não precisa compreender os detalhes do FlatBuffer. Ele recebe valores já normalizados e pode concentrar-se exclusivamente em montar a estrutura binária que será consumida pelo runtime.
