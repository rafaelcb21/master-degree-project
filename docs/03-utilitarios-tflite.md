# 03 — Utilitários para leitura do TFLite (`tflite_utils.py`)

## 1. Objetivo do módulo

O arquivo `extractor/tflite_utils.py` concentra funções auxiliares utilizadas por vários módulos durante a leitura da estrutura TFLite.

Seu papel principal é transformar informações expostas pelo binding TFLite em representações Python mais simples e previsíveis.

O código atual é:

```python
import tflite
import numpy as np


TENSOR_TYPE_MAP = {
    0: ("float32", np.float32),
    1: ("float16", np.float16),
    2: ("int32", np.int32),
    3: ("uint8", np.uint8),
    4: ("int64", np.int64),
    6: ("bool", np.bool_),
    7: ("int16", np.int16),
    9: ("int8", np.int8),
}

BYTES_PER_TYPE = {
    0: 4,  # float32
    1: 2,  # float16
    2: 4,  # int32
    3: 1,  # uint8
    4: 8,  # int64
    6: 1,  # bool
    7: 2,  # int16
    9: 1,  # int8
}


def op_name(model, op):
    code = model.OperatorCodes(
        op.OpcodeIndex()
    ).BuiltinCode()

    for name, value in tflite.BuiltinOperator.__dict__.items():
        if isinstance(value, int) and value == code:
            return name

    return "CUSTOM"


def is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        tensor_id
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data = buffer.DataAsNumpy()
    except AttributeError:
        return False

    return (
        hasattr(data, "__len__")
        and len(data) > 0
    )


def safe_bytes_from_tensor(
    model,
    subgraph,
    tensor_id,
):
    tensor = subgraph.Tensors(
        int(tensor_id)
    )

    buffer = model.Buffers(
        tensor.Buffer()
    )

    try:
        data_bytes = buffer.DataAsNumpy()
    except AttributeError:
        return None, None, None

    if (
        not hasattr(data_bytes, "__len__")
        or len(data_bytes) == 0
    ):
        return None, None, None

    shape = tensor.ShapeAsNumpy()
    dtype = int(tensor.Type())

    _, numpy_dtype = TENSOR_TYPE_MAP.get(
        dtype,
        (None, None),
    )

    if numpy_dtype is None:
        return None, None, None

    array = np.frombuffer(
        data_bytes.tobytes(),
        dtype=numpy_dtype,
    )

    try:
        array = array.reshape(shape)
    except Exception:
        pass

    raw = array.flatten().tobytes()

    return tensor, array, raw


def scale_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 1.0

    scales = quantization.ScaleAsNumpy()

    if scales is None or len(scales) == 0:
        return 1.0

    return float(
        np.array(
            scales,
            dtype=np.float64,
        ).flatten()[0]
    )


def zp_scalar(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return 0

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if (
        zero_points is None
        or len(zero_points) == 0
    ):
        return 0

    return int(
        np.array(
            zero_points,
            dtype=np.int64,
        ).flatten()[0]
    )


def tensor_shape_list(tensor):
    shape = tensor.ShapeAsNumpy()

    if shape is None:
        return []

    return [
        int(value)
        for value in shape.tolist()
    ]


def qparams_np(tensor):
    quantization = tensor.Quantization()

    if quantization is None:
        return None

    scales = (
        quantization.ScaleAsNumpy()
    )

    zero_points = (
        quantization.ZeroPointAsNumpy()
    )

    if scales is None:
        return None

    scales = np.atleast_1d(
        np.array(
            scales,
            dtype=np.float64,
        )
    )

    zero_points = np.atleast_1d(
        np.array(
            (
                zero_points
                if zero_points is not None
                else []
            ),
            dtype=np.int64,
        )
    )

    if scales.size == 0:
        return None

    return {
        "scales": scales,
        "zps": zero_points,
        "qdim": (
            quantization
            .QuantizedDimension()
        ),
    }
```

---

# 2. Responsabilidade arquitetural

Esse módulo não executa uma etapa completa do pipeline.

Ele funciona como uma biblioteca de apoio.

Diversos módulos precisam fazer operações repetitivas como:

```text
converter código do operador em nome
identificar tensor constante
ler bytes de um tensor
obter shape
obter scale
obter zero point
obter parâmetros de quantização por canal
```

Sem esse módulo, essa lógica ficaria duplicada em:

```text
graph.py
weights.py
quantization.py
memory.py
layer_params.py
```

A função de `tflite_utils.py` é centralizar essas operações.

---

# 3. Posição no projeto

Uma visão simplificada é:

```text
                     Model + SubGraph
                           │
                           ▼
                  tflite_utils.py
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      graph.py         weights.py     quantization.py
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                    layer_params.py
```

Ele não controla o fluxo.

Ele fornece funções reutilizáveis.

---

# 4. Importação do módulo `tflite`

```python
import tflite
```

Esse import é utilizado principalmente em:

```python
tflite.BuiltinOperator
```

A estrutura `BuiltinOperator` contém os identificadores numéricos dos operadores conhecidos pelo formato TFLite.

Por exemplo, conceitualmente:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
QUANTIZE
```

Cada nome corresponde internamente a um código inteiro.

A função `op_name()` utiliza essa tabela para recuperar o nome textual.

---

# 5. Importação do NumPy

```python
import numpy as np
```

O NumPy é utilizado neste módulo para três finalidades principais:

```text
1. mapear tipos TFLite para tipos NumPy
2. reconstruir arrays a partir de bytes
3. normalizar parâmetros de quantização
```

Por exemplo:

```python
np.int8
np.int32
np.float32
```

permitem interpretar corretamente os bytes armazenados nos buffers do modelo.

---

# 6. `TENSOR_TYPE_MAP`

A primeira estrutura importante é:

```python
TENSOR_TYPE_MAP = {
    0: ("float32", np.float32),
    1: ("float16", np.float16),
    2: ("int32", np.int32),
    3: ("uint8", np.uint8),
    4: ("int64", np.int64),
    6: ("bool", np.bool_),
    7: ("int16", np.int16),
    9: ("int8", np.int8),
}
```

Ela relaciona:

```text
código TFLite
      ↓
nome legível
      +
dtype NumPy
```

Exemplo:

```python
9: ("int8", np.int8)
```

significa:

```text
tensor.Type() == 9
        ↓
tipo lógico = int8
        ↓
NumPy dtype = np.int8
```

---

# 7. Por que precisamos desse mapa?

Quando o binding fornece:

```python
tensor.Type()
```

o retorno é um número inteiro.

Por exemplo:

```text
9
```

Esse número isoladamente não informa diretamente ao restante do código:

```text
quantos bytes cada elemento possui
como interpretar os bytes
como reconstruir um ndarray
```

O mapa resolve isso.

Exemplo:

```python
dtype = int(tensor.Type())

name, numpy_dtype = TENSOR_TYPE_MAP[dtype]
```

Resultado:

```text
name = "int8"
numpy_dtype = np.int8
```

---

# 8. Tipos utilizados no projeto

A tabela atual contempla:

| Código | Tipo      | NumPy        |
| -----: | --------- | ------------ |
|    `0` | `float32` | `np.float32` |
|    `1` | `float16` | `np.float16` |
|    `2` | `int32`   | `np.int32`   |
|    `3` | `uint8`   | `np.uint8`   |
|    `4` | `int64`   | `np.int64`   |
|    `6` | `bool`    | `np.bool_`   |
|    `7` | `int16`   | `np.int16`   |
|    `9` | `int8`    | `np.int8`    |

Esses são os tipos que o extrator atual sabe transformar diretamente em arrays NumPy.

Um tipo fora dessa tabela será considerado não suportado por `safe_bytes_from_tensor()`.

---

# 9. `BYTES_PER_TYPE`

A segunda tabela é:

```python
BYTES_PER_TYPE = {
    0: 4,
    1: 2,
    2: 4,
    3: 1,
    4: 8,
    6: 1,
    7: 2,
    9: 1,
}
```

Essa estrutura responde outra pergunta:

```text
quantos bytes ocupa um elemento deste tensor?
```

Exemplo:

```text
int8
 ↓
1 byte
```

```text
int32
 ↓
4 bytes
```

```text
float32
 ↓
4 bytes
```

---

# 10. Por que existem dois mapas?

Poderíamos teoricamente manter uma única estrutura com:

```text
nome
dtype NumPy
bytes
```

Mas o código atual separa duas responsabilidades.

`TENSOR_TYPE_MAP` é usado para interpretar o conteúdo:

```text
bytes → array
```

Já `BYTES_PER_TYPE` é útil para planejamento de memória:

```text
número de elementos × bytes por elemento
```

Por exemplo:

```text
shape = [1, 128, 128, 3]

elementos =
1 × 128 × 128 × 3
= 49152
```

Para `int8`:

```text
49152 × 1
= 49152 bytes
```

Para `float32`:

```text
49152 × 4
= 196608 bytes
```

---

# 11. Função `op_name()`

A função:

```python
def op_name(model, op):
```

transforma o identificador interno de um operador em seu nome textual.

Seu fluxo é:

```text
Operator
   ↓
OpcodeIndex
   ↓
OperatorCodes
   ↓
BuiltinCode
   ↓
nome
```

---

# 12. Obtendo o código da operação

A primeira parte é:

```python
code = model.OperatorCodes(
    op.OpcodeIndex()
).BuiltinCode()
```

Podemos decompor isso.

Primeiro:

```python
op.OpcodeIndex()
```

obtém o índice da entrada correspondente na tabela global de operadores do modelo.

Depois:

```python
model.OperatorCodes(...)
```

obtém essa entrada.

Finalmente:

```python
.BuiltinCode()
```

obtém o código inteiro que identifica o operador.

---

# 13. Estrutura conceitual

Imagine:

```text
Operator
   │
   └── OpcodeIndex = 3
             │
             ▼
Model.OperatorCodes(3)
             │
             └── BuiltinCode = X
```

Agora é necessário descobrir qual nome corresponde a `X`.

---

# 14. Busca em `BuiltinOperator`

A função percorre:

```python
for name, value in (
    tflite.BuiltinOperator
    .__dict__
    .items()
):
```

Isso significa que ela inspeciona os atributos definidos dentro de:

```text
tflite.BuiltinOperator
```

Quando encontra:

```python
isinstance(value, int)
and value == code
```

retorna:

```python
return name
```

Por exemplo:

```text
code = código correspondente a CONV_2D
        ↓
"CONV_2D"
```

---

# 15. Por que verificar `isinstance(value, int)`?

O dicionário interno de uma classe ou módulo contém outros atributos além das constantes dos operadores.

Por isso:

```python
isinstance(
    value,
    int
)
```

filtra apenas valores inteiros.

Sem isso, a função poderia comparar o código contra atributos que não representam operadores.

---

# 16. Retorno `"CUSTOM"`

Se nenhum operador conhecido for encontrado:

```python
return "CUSTOM"
```

Isso funciona como fallback.

Ou seja:

```text
BuiltinCode conhecido
       ↓
nome correspondente

BuiltinCode não encontrado
       ↓
"CUSTOM"
```

O retorno não significa necessariamente que todo operador desconhecido esteja corretamente implementado como operador customizado.

Ele apenas indica que não foi possível associá-lo a um nome conhecido na tabela percorrida.

---

# 17. Uso posterior de `op_name()`

Outros módulos podem fazer:

```python
optype = op_name(
    model,
    op
)
```

e obter:

```text
"CONV_2D"
"DEPTHWISE_CONV_2D"
"FULLY_CONNECTED"
"ADD"
"MEAN"
"SOFTMAX"
"QUANTIZE"
```

Isso permite utilizar código legível como:

```python
if optype == "CONV_2D":
```

em vez de comparar números diretamente.

---

# 18. Função `is_constant_tensor()`

A função:

```python
def is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
```

determina se determinado tensor possui dados armazenados em um buffer do modelo.

O critério atual é:

```text
buffer possui conteúdo?
     │
     ├── sim → tensor constante
     └── não → tensor não constante
```

---

# 19. Localizando o tensor

Primeiro:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

O identificador recebido é um índice dentro da tabela de tensors do subgrafo.

---

# 20. Localizando o buffer

Depois:

```python
buffer = model.Buffers(
    tensor.Buffer()
)
```

Cada tensor possui uma referência para um buffer.

Estrutura conceitual:

```text
Tensor
  │
  └── Buffer ID
          │
          ▼
    Model.Buffers(ID)
          │
          ▼
        Buffer
```

---

# 21. Tentativa de leitura

A função tenta:

```python
data = buffer.DataAsNumpy()
```

Caso o binding não exponha esse método:

```python
except AttributeError:
    return False
```

Assim, a função considera que não foi possível confirmar que existe conteúdo constante.

---

# 22. Critério de tensor constante

O retorno final é:

```python
return (
    hasattr(data, "__len__")
    and len(data) > 0
)
```

Portanto, para o extrator atual:

```text
buffer vazio
    ↓
não constante

buffer com bytes
    ↓
constante
```

---

# 23. Exemplo com peso de convolução

Uma entrada dinâmica da rede pode possuir:

```text
Tensor input
   │
   └── buffer vazio
```

Logo:

```python
is_constant_tensor(...)
```

retorna:

```text
False
```

Já os pesos:

```text
Tensor weights
   │
   └── buffer contendo milhares de bytes
```

retornam:

```text
True
```

---

# 24. Importância para o grafo

Essa distinção é importante porque os pesos não devem ser tratados como tensors temporários produzidos por outra camada.

Por exemplo:

```text
           input activation
                  │
                  ▼
             CONV_2D
                  ▲
                  │
               weights
```

O tensor de entrada é um fluxo de dados do grafo.

O tensor de pesos é constante.

Isso afeta:

```text
dependências
slot allocation
mapeamento tensor→slot
```

---

# 25. Função `safe_bytes_from_tensor()`

Essa função possui uma responsabilidade maior:

```text
tensor constante
     ↓
localizar bytes
     ↓
descobrir dtype
     ↓
converter para NumPy
     ↓
aplicar shape
     ↓
produzir bytes normalizados
```

Ela retorna três valores:

```python
tensor, array, raw
```

---

# 26. Entrada da função

```python
def safe_bytes_from_tensor(
    model,
    subgraph,
    tensor_id,
):
```

Recebe:

```text
Model
SubGraph
tensor_id
```

Ela própria localiza tanto o tensor quanto seu buffer.

---

# 27. Normalização do `tensor_id`

O código usa:

```python
int(tensor_id)
```

antes de acessar:

```python
subgraph.Tensors(...)
```

Isso é útil porque alguns índices fornecidos por arrays NumPy podem ser tipos como:

```text
np.int32
np.int64
```

A conversão garante um `int` Python normal.

---

# 28. Leitura do buffer

O processo é:

```python
tensor = subgraph.Tensors(
    int(tensor_id)
)

buffer = model.Buffers(
    tensor.Buffer()
)
```

Depois:

```python
data_bytes = buffer.DataAsNumpy()
```

Se o método não estiver disponível:

```python
return None, None, None
```

---

# 29. Buffer vazio

A função também verifica:

```python
if (
    not hasattr(
        data_bytes,
        "__len__"
    )
    or len(data_bytes) == 0
):
    return None, None, None
```

Isso impede tentar interpretar um tensor que não possui dados constantes.

---

# 30. Leitura do shape

Em seguida:

```python
shape = tensor.ShapeAsNumpy()
```

Exemplo:

```text
[32, 3, 3, 3]
```

para um conjunto hipotético de pesos de convolução.

---

# 31. Leitura do tipo

Depois:

```python
dtype = int(
    tensor.Type()
)
```

Suponha:

```text
dtype = 9
```

Pelo mapa:

```python
TENSOR_TYPE_MAP[9]
```

temos:

```text
("int8", np.int8)
```

---

# 32. Resolução do dtype NumPy

O código:

```python
_, numpy_dtype = (
    TENSOR_TYPE_MAP.get(
        dtype,
        (None, None),
    )
)
```

ignora o nome textual e recupera apenas o dtype NumPy.

Para `int8`:

```text
numpy_dtype = np.int8
```

---

# 33. Tipo não suportado

Se:

```python
numpy_dtype is None
```

a função retorna:

```python
None, None, None
```

Portanto, ela não tenta interpretar bytes de um tipo para o qual não existe mapeamento conhecido.

Isso evita atribuir um significado incorreto ao conteúdo binário.

---

# 34. `np.frombuffer()`

A transformação principal é:

```python
array = np.frombuffer(
    data_bytes.tobytes(),
    dtype=numpy_dtype,
)
```

Essa função interpreta os mesmos bytes segundo o tipo correto.

Exemplo simples.

Suponha quatro bytes:

```text
01 FF 02 FE
```

interpretados como `int8`:

```text
[1, -1, 2, -2]
```

Os bytes não são alterados.

O que muda é sua interpretação.

---

# 35. Por que o dtype é essencial?

Os mesmos bytes podem significar valores diferentes dependendo do tipo.

Exemplo simplificado:

```text
byte FF
```

Como `uint8`:

```text
255
```

Como `int8`:

```text
-1
```

Portanto:

```python
dtype=numpy_dtype
```

é fundamental para preservar os valores do modelo.

---

# 36. Array inicialmente linear

`np.frombuffer()` produz inicialmente uma sequência linear.

Por exemplo:

```text
[1, 2, 3, 4, 5, 6]
```

Mesmo que o tensor original tenha shape:

```text
[2, 3]
```

Por isso a etapa seguinte tenta restaurar a forma original.

---

# 37. `reshape(shape)`

O código:

```python
try:
    array = array.reshape(
        shape
    )
except Exception:
    pass
```

tenta reconstruir as dimensões originais do tensor.

Exemplo:

```text
array linear:
[1, 2, 3, 4, 5, 6]

shape:
[2, 3]

resultado:
[
  [1, 2, 3],
  [4, 5, 6]
]
```

---

# 38. Por que existe `try/except` no reshape?

Se o número de elementos não for compatível com o shape informado, `reshape()` gera uma exceção.

O código atual opta por não interromper a extração nesse ponto.

Ele mantém o array linear.

Portanto:

```text
reshape funcionou
    ↓
array com shape original

reshape falhou
    ↓
array permanece linear
```

---

# 39. Caveat importante sobre o `reshape`

Esse comportamento foi preservado da implementação original, mas merece documentação.

O trecho:

```python
except Exception:
    pass
```

oculta o motivo da falha.

Em uma versão futura voltada a validação rigorosa, pode ser melhor transformar uma incompatibilidade entre:

```text
buffer
e
shape
```

em erro explícito.

Por enquanto, a decisão atual privilegia compatibilidade com o extrator existente.

---

# 40. Geração de `raw`

Depois:

```python
raw = (
    array
    .flatten()
    .tobytes()
)
```

Isso cria uma versão linear em bytes.

Fluxo:

```text
buffer original
     ↓
NumPy array
     ↓
reshape
     ↓
flatten
     ↓
bytes
```

---

# 41. Por que fazer `flatten()`?

Mesmo que o array tenha várias dimensões:

```text
[O, H, W, I]
```

a memória linear do WASM será um bloco sequencial de bytes.

Por isso:

```python
array.flatten()
```

remove a estrutura dimensional antes da serialização.

Exemplo:

```text
[
 [1, 2],
 [3, 4]
]
```

vira:

```text
[1, 2, 3, 4]
```

e depois:

```text
bytes
```

---

# 42. Retorno de `safe_bytes_from_tensor()`

O retorno é:

```python
return tensor, array, raw
```

Cada elemento possui uma função diferente.

### `tensor`

Mantém acesso aos metadados TFLite:

```text
shape
tipo
quantização
buffer ID
```

### `array`

Fornece os valores já interpretados pelo NumPy.

É útil para:

```text
inspeção
transformações
cálculos
validação
```

### `raw`

Fornece os bytes lineares.

É útil para:

```text
serialização
weights blob
bias blob
data segments do WAT
```

---

# 43. Exemplo completo

Considere um tensor:

```text
shape = [2, 2]
dtype = int8
```

e bytes:

```text
01 02 FF FE
```

O processo seria:

```text
bytes
01 02 FF FE
      │
      ▼
np.frombuffer(..., int8)
      │
      ▼
[1, 2, -1, -2]
      │
      ▼
reshape([2,2])
      │
      ▼
[
 [ 1,  2],
 [-1, -2]
]
      │
      ▼
flatten()
      │
      ▼
[1, 2, -1, -2]
      │
      ▼
tobytes()
```

Os valores mantêm sua representação binária apropriada.

---

# 44. Função `scale_scalar()`

A função:

```python
def scale_scalar(tensor):
```

obtém uma única escala de quantização associada ao tensor.

Seu objetivo é simplificar casos onde a quantização é per-tensor.

---

# 45. Obtendo a estrutura de quantização

Primeiro:

```python
quantization = (
    tensor.Quantization()
)
```

Essa estrutura contém informações como:

```text
Scale
ZeroPoint
QuantizedDimension
```

---

# 46. Tensor sem quantização

Se:

```python
quantization is None
```

a função retorna:

```python
1.0
```

Esse valor funciona como escala neutra.

Ou seja:

```text
x × 1.0 = x
```

---

# 47. Tensor sem `Scale`

Depois:

```python
scales = (
    quantization
    .ScaleAsNumpy()
)
```

Se:

```text
scales == None
```

ou:

```text
len(scales) == 0
```

a função também retorna:

```python
1.0
```

---

# 48. Conversão para `float64`

O retorno normal é:

```python
return float(
    np.array(
        scales,
        dtype=np.float64,
    ).flatten()[0]
)
```

A operação faz:

```text
scales
   ↓
np.array(... float64)
   ↓
flatten()
   ↓
primeiro elemento
   ↓
float Python
```

---

# 49. Por que pegar apenas `[0]`?

Porque essa função representa explicitamente:

```text
scale escalar
```

Ela é adequada para quantização per-tensor.

Exemplo:

```text
Scale = [0.0039215689]
```

resultado:

```text
0.0039215689
```

---

# 50. Quantização per-tensor

Na quantização per-tensor existe um único par:

```text
scale
zero_point
```

para todo o tensor.

A conversão conceitual é:

```text
valor_real =
scale × (valor_quantizado - zero_point)
```

Exemplo:

```text
scale = 0.1
zero_point = -128
q = -118
```

Então:

```text
real =
0.1 × (-118 - (-128))

= 0.1 × 10

= 1.0
```

---

# 51. Função `zp_scalar()`

A função:

```python
def zp_scalar(tensor):
```

é equivalente a `scale_scalar()`, mas retorna o zero point.

---

# 52. Tensor sem quantização

Se:

```python
quantization is None
```

o retorno é:

```python
0
```

Zero funciona como offset neutro.

---

# 53. Tensor sem zero point

A função lê:

```python
zero_points = (
    quantization
    .ZeroPointAsNumpy()
)
```

Se não existir valor:

```python
return 0
```

---

# 54. Conversão para inteiro

O retorno é:

```python
return int(
    np.array(
        zero_points,
        dtype=np.int64,
    ).flatten()[0]
)
```

Assim como no scale:

```text
array
  ↓
flatten
  ↓
primeiro elemento
```

Mas o tipo final é:

```text
int
```

---

# 55. `scale_scalar()` e `zp_scalar()` juntos

Os dois helpers permitem:

```python
scale = scale_scalar(
    tensor
)

zp = zp_scalar(
    tensor
)
```

produzindo:

```text
(scale, zero_point)
```

Exemplo:

```text
scale = 0.0039215689
zp = -128
```

---

# 56. Uso em operações especiais

Esses valores são utilizados posteriormente em operações como:

```text
QUANTIZE
ADD
MEAN
SOFTMAX
```

e também para:

```text
zx
zw
zy
```

nos `LayerParams`.

Por exemplo:

```text
zx = zero point da entrada
zw = zero point dos pesos
zy = zero point da saída
```

---

# 57. Limitação deliberada dos helpers escalares

`scale_scalar()` e `zp_scalar()` sempre pegam:

```text
primeiro elemento
```

Por isso eles não substituem a leitura completa de quantização per-channel.

Se um tensor possuir:

```text
32 escalas
```

esses helpers retornariam apenas:

```text
scales[0]
```

Para esse caso existe:

```python
qparams_np()
```

---

# 58. Função `tensor_shape_list()`

A função:

```python
def tensor_shape_list(tensor):
```

normaliza o shape para uma lista Python.

Ela recebe:

```text
Tensor TFLite
```

e retorna algo como:

```python
[1, 128, 128, 3]
```

---

# 59. Shape vindo do binding

Primeiro:

```python
shape = (
    tensor.ShapeAsNumpy()
)
```

O resultado normalmente é um ndarray NumPy.

Exemplo:

```text
array([1, 128, 128, 3])
```

---

# 60. Tensor sem shape

Se:

```python
shape is None
```

a função retorna:

```python
[]
```

Assim, os módulos consumidores podem trabalhar sempre com uma lista.

---

# 61. Conversão para lista Python

O retorno normal é:

```python
return [
    int(value)
    for value
    in shape.tolist()
]
```

A transformação é:

```text
NumPy array
    ↓
.tolist()
    ↓
lista
    ↓
int(value)
    ↓
lista de ints Python
```

---

# 62. Por que converter cada valor para `int`?

Sem essa conversão, os elementos podem continuar sendo tipos NumPy como:

```text
np.int32
np.int64
```

Ao produzir:

```python
int(value)
```

o restante do projeto recebe tipos Python comuns.

Isso simplifica:

```text
serialização
comparações
relatórios
struct.pack
```

---

# 63. Exemplo

Entrada:

```text
tensor.ShapeAsNumpy()

→ np.array([1, 128, 128, 3])
```

Saída:

```python
[1, 128, 128, 3]
```

---

# 64. Função `qparams_np()`

A função:

```python
def qparams_np(tensor):
```

é a leitura completa dos parâmetros de quantização.

Ao contrário de:

```text
scale_scalar()
zp_scalar()
```

ela preserva vetores inteiros de escalas e zero points.

---

# 65. Por que essa função é necessária?

Pesos quantizados podem utilizar quantização por canal.

Nesse caso, em vez de:

```text
1 scale
```

podemos ter:

```text
uma scale para cada canal de saída
```

Exemplo:

```text
32 filtros
     ↓
32 scales
```

Nesse cenário, pegar apenas:

```text
scales[0]
```

seria insuficiente.

---

# 66. Obtendo a estrutura de quantização

Primeiro:

```python
quantization = (
    tensor.Quantization()
)
```

Se não existir:

```python
return None
```

---

# 67. Leitura de `scales`

Depois:

```python
scales = (
    quantization
    .ScaleAsNumpy()
)
```

Se:

```python
scales is None
```

o retorno também é:

```python
None
```

A função considera que não existe informação de quantização utilizável.

---

# 68. Leitura de `zero_points`

Também é feita:

```python
zero_points = (
    quantization
    .ZeroPointAsNumpy()
)
```

Aqui existe uma diferença.

Se os zero points não estiverem presentes, a função não retorna imediatamente.

Ela posteriormente cria um array vazio.

---

# 69. Normalização de `scales`

O código:

```python
scales = np.atleast_1d(
    np.array(
        scales,
        dtype=np.float64,
    )
)
```

garante que:

```text
scale escalar
```

e:

```text
vetor de scales
```

tenham sempre uma representação de pelo menos uma dimensão.

---

# 70. O que faz `np.atleast_1d()`?

Exemplo:

```python
np.array(0.5)
```

possui shape:

```text
()
```

Depois:

```python
np.atleast_1d(...)
```

vira:

```text
[0.5]
```

Isso permite ao restante do código tratar escala única e múltiplas escalas de forma uniforme.

---

# 71. Normalização de `zero_points`

O mesmo é feito com:

```python
zero_points = np.atleast_1d(
    np.array(
        (
            zero_points
            if zero_points is not None
            else []
        ),
        dtype=np.int64,
    )
)
```

Assim:

```text
zero_points existente
       ↓
array int64
```

ou:

```text
zero_points ausente
       ↓
[]
```

---

# 72. Verificação final de escalas

Depois:

```python
if scales.size == 0:
    return None
```

Sem escala, a quantização não é considerada válida para os cálculos posteriores.

---

# 73. Retorno de `qparams_np()`

A função retorna:

```python
{
    "scales": scales,
    "zps": zero_points,
    "qdim": (
        quantization
        .QuantizedDimension()
    ),
}
```

Ou seja:

```text
scales
zero points
quantized dimension
```

---

# 74. `QuantizedDimension`

O campo:

```python
quantization.QuantizedDimension()
```

indica qual dimensão do tensor está associada à quantização por canal.

Esse valor é importante porque um vetor de scales precisa ser interpretado em relação a uma dimensão específica.

Exemplo conceitual:

```text
weights shape:
[32, 3, 3, 3]

scales:
[32 valores]

qdim:
0
```

Isso indica que as 32 escalas correspondem à dimensão:

```text
shape[0]
```

que possui 32 elementos.

---

# 75. Quantização per-tensor versus per-channel

Podemos representar os dois casos assim.

## Per-tensor

```text
Tensor inteiro
    │
    ├── scale = 0.05
    └── zp = -3
```

Um único conjunto de parâmetros vale para todo o tensor.

---

## Per-channel

```text
Tensor
│
├── canal 0 → scale[0]
├── canal 1 → scale[1]
├── canal 2 → scale[2]
├── ...
└── canal N → scale[N]
```

Por isso:

```python
qparams_np()
```

preserva o vetor inteiro.

---

# 76. Exemplo de `qparams_np()`

Suponha:

```text
scales =
[
  0.0012,
  0.0015,
  0.0011,
  0.0017
]

zero_points =
[
  0,
  0,
  0,
  0
]

qdim = 0
```

O retorno é conceitualmente:

```python
{
    "scales": np.array([
        0.0012,
        0.0015,
        0.0011,
        0.0017,
    ]),
    "zps": np.array([
        0,
        0,
        0,
        0,
    ]),
    "qdim": 0,
}
```

Esse conteúdo será utilizado posteriormente para calcular multiplicadores de requantização por canal.

---

# 77. Relação entre `qparams_np()` e requantização

Em uma camada quantizada temos conceitualmente:

```text
input scale = Sx
weight scale = Sw
output scale = Sy
```

Para cada canal pode ser necessário um fator proporcional a:

```text
Sx × Sw
───────
   Sy
```

Se `Sw` possuir um valor diferente por canal:

```text
Sw[0]
Sw[1]
Sw[2]
...
```

o multiplicador também será diferente para cada canal.

Esse é um dos motivos pelos quais a quantização completa precisa ser preservada.

---

# 78. Diferença entre helpers escalares e vetoriais

Podemos resumir:

```text
scale_scalar()
    ↓
um único scale

zp_scalar()
    ↓
um único zero point

qparams_np()
    ↓
todos os scales
todos os zero points
quantized dimension
```

Portanto:

```text
scale_scalar / zp_scalar
```

são convenientes para quantização per-tensor,

enquanto:

```text
qparams_np
```

é adequado para cálculos que precisam preservar quantização por canal.

---

# 79. Relação com `weights.py`

`weights.py` utiliza funções desse módulo para:

```text
localizar tensors constantes
interpretar buffers
obter dtype
obter bytes
```

Fluxo simplificado:

```text
Tensor de pesos
      │
      ▼
safe_bytes_from_tensor()
      │
      ├── tensor
      ├── ndarray
      └── raw bytes
               │
               ▼
          weights_raw
```

---

# 80. Relação com `quantization.py`

`quantization.py` necessita principalmente:

```text
scale_scalar
zp_scalar
qparams_np
```

Fluxo:

```text
Tensor
   │
   ▼
qparams_np()
   │
   ├── scales
   ├── zero points
   └── quantized dimension
           │
           ▼
cálculo de multiplier / shift / Q6
```

---

# 81. Relação com `graph.py`

`graph.py` precisa distinguir:

```text
tensor constante
```

de:

```text
tensor produzido dinamicamente por operador
```

Para isso pode utilizar:

```python
is_constant_tensor(...)
```

Isso impede que pesos e bias sejam interpretados como arestas normais entre operadores do grafo.

---

# 82. Relação com `layer_params.py`

`layer_params.py` utiliza diretamente helpers como:

```text
op_name
scale_scalar
zp_scalar
tensor_shape_list
```

Por exemplo:

```text
TFLite Tensor
      ↓
tensor_shape_list()
      ↓
[1, H, W, C]
      ↓
in_h
in_w
cin
```

e:

```text
Tensor quantizado
      ↓
scale_scalar()
zp_scalar()
      ↓
zx / zy
```

---

# 83. Por que `tensor_hwc()` não está aqui?

Um detalhe importante da arquitetura atual é que:

```python
tensor_hwc()
```

foi mantido em:

```text
layer_params.py
```

e não em:

```text
tflite_utils.py
```

O motivo é semântico.

`tensor_shape_list()` apenas responde:

```text
qual é o shape?
```

Por exemplo:

```text
[1, 128, 128, 3]
```

Já `tensor_hwc()` interpreta esse shape segundo a convenção esperada pela implementação das `LayerParams`:

```text
shape[1] → altura
shape[2] → largura
shape[3] → canais
```

Ou seja:

```text
tflite_utils.py
        ↓
representação genérica

layer_params.py
        ↓
interpretação específica da aplicação
```

Essa separação é intencional.

---

# 84. O módulo como camada de normalização

Podemos entender este arquivo como uma camada de normalização.

O binding TFLite fornece:

```text
inteiros de enumeração
ndarrays
objetos FlatBuffer
arrays opcionais
métodos específicos
```

O restante do extrator prefere receber:

```text
nomes de operadores
ints Python
floats Python
listas Python
arrays NumPy normalizados
bytes
```

Portanto:

```text
Binding TFLite
      │
      ▼
tflite_utils.py
      │
      ▼
representação mais conveniente
      │
      ▼
restante do extrator
```

---

# 85. Política atual para valores ausentes

O módulo utiliza valores padrão em alguns casos.

### Scale ausente

```python
1.0
```

### Zero point ausente

```python
0
```

### Shape ausente

```python
[]
```

### Buffer inexistente

```python
None, None, None
```

### Quantização inexistente

```python
None
```

Essas decisões evitam que todos os módulos consumidores precisem repetir as mesmas verificações.

---

# 86. Significado dos valores neutros

Os defaults:

```text
scale = 1.0
zero point = 0
```

são matematicamente neutros na expressão:

```text
real =
scale × (q - zero_point)
```

Substituindo:

```text
real =
1 × (q - 0)

= q
```

Isso explica por que esses valores são convenientes quando não há informação de quantização.

---

# 87. Caveat dos valores padrão

Apesar de matematicamente neutros, esses valores também podem esconder ausência inesperada de metadados.

Por exemplo, se uma operação quantizada deveria possuir escala mas o modelo não fornecer:

```text
scale_scalar()
        ↓
1.0
```

o pipeline pode continuar.

Em uma versão futura mais rigorosa, certas chamadas poderiam diferenciar:

```text
tensor realmente não quantizado
```

de:

```text
tensor que deveria ser quantizado, mas possui metadados incompletos
```

No extrator atual, o comportamento foi mantido simples e compatível com o modelo utilizado.

---

# 88. Política de retorno de `safe_bytes_from_tensor()`

A função retorna três `None` simultaneamente em situações de falha ou ausência:

```python
return None, None, None
```

Isso permite ao chamador fazer:

```python
tensor, array, raw = (
    safe_bytes_from_tensor(...)
)

if raw is None:
    ...
```

A alternativa seria levantar exceção em todos os casos.

A implementação atual prefere:

```text
ausência esperada
      ↓
None

erro estrutural crítico
      ↓
tratado em etapas posteriores
```

---

# 89. Serialização e endianness

`safe_bytes_from_tensor()` não realiza reordenação manual dos bytes.

Ela utiliza:

```python
np.frombuffer(...)
```

seguido por:

```python
.tobytes()
```

O objetivo é preservar a sequência lógica dos dados segundo o dtype interpretado.

Posteriormente, estruturas específicas como `LayerParam` são serializadas explicitamente com formato little-endian:

```text
<i
```

mas isso pertence ao módulo de serialização, não a este utilitário.

---

# 90. Diferença entre buffer de peso e `params_blob`

É importante distinguir dois tipos de bytes utilizados pelo projeto.

## Bytes vindos diretamente do TFLite

Produzidos por:

```python
safe_bytes_from_tensor()
```

Exemplo:

```text
weights_raw
bias_raw
```

Eles representam dados do modelo.

## Bytes construídos pelo extrator

Produzidos posteriormente por:

```text
quantization.py
params_blob.py
```

Exemplo:

```text
mul_blob
shift_blob
q6_blob
params_blob
```

Esses não existiam dessa forma no TFLite.

Foram calculados ou reorganizados pelo pipeline.

---

# 91. Fluxo completo de um tensor constante

Um peso passa aproximadamente pelo seguinte caminho:

```text
TFLite Tensor
      │
      ├── Type()
      ├── ShapeAsNumpy()
      └── Buffer()
             │
             ▼
        TFLite Buffer
             │
             ▼
        DataAsNumpy()
             │
             ▼
safe_bytes_from_tensor()
             │
             ├── ndarray
             │
             └── raw bytes
                     │
                     ▼
               weights.py
                     │
                     ▼
               weights_raw
                     │
                     ▼
             wat_generator.py
                     │
                     ▼
             data segment WASM
```

---

# 92. Fluxo de informações de quantização

Para um tensor quantizado:

```text
Tensor
  │
  └── Quantization()
         │
         ├── ScaleAsNumpy()
         ├── ZeroPointAsNumpy()
         └── QuantizedDimension()
                │
                ▼
          tflite_utils.py
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
scale_scalar()       qparams_np()
zp_scalar()              │
        │                │
        ▼                ▼
operações especiais   per-channel
```

---

# 93. O que este módulo não deve fazer

Este arquivo não deve conter lógica específica de:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
ADD
MEAN
SOFTMAX
```

Também não deve calcular:

```text
multipliers
shifts
Q6
padding
slots
endereços de memória
LayerParams
```

Essas responsabilidades pertencem a módulos especializados.

---

# 94. Por que isso é importante?

Imagine colocar dentro de:

```python
safe_bytes_from_tensor()
```

uma regra específica para reorganizar pesos de `DEPTHWISE_CONV_2D`.

Isso faria uma função genérica começar a conhecer semântica de operador.

A arquitetura atual evita isso.

A divisão é:

```text
tflite_utils.py
    ↓
"como ler o TFLite"

weights.py
    ↓
"como organizar pesos"

quantization.py
    ↓
"como calcular parâmetros quantizados"

layer_params.py
    ↓
"como representar cada operação no runtime"
```

---

# 95. Dependência central, mas de baixo nível

`tflite_utils.py` é um módulo de baixo nível.

Ele conhece:

```text
binding TFLite
NumPy
```

mas não deveria conhecer:

```text
WAT
slots
layout de memória
execução WASM
```

Isso reduz acoplamento.

---

# 96. Benefício para uma futura API/backend

Quando o extrator for utilizado como backend, esse módulo provavelmente precisará de poucas mudanças.

A entrada continuará sendo:

```text
Model + SubGraph
```

independentemente de o arquivo ter vindo de:

```text
linha de comando
upload web
API
interface Angular
```

Portanto, o utilitário permanece reutilizável.

---

# 97. Resumo das funções

| Função                     | Responsabilidade                                     |
| -------------------------- | ---------------------------------------------------- |
| `op_name()`                | Converter código interno de operador em nome textual |
| `is_constant_tensor()`     | Verificar se tensor possui buffer constante          |
| `safe_bytes_from_tensor()` | Ler e interpretar bytes de um tensor constante       |
| `scale_scalar()`           | Obter primeira escala de quantização                 |
| `zp_scalar()`              | Obter primeiro zero point                            |
| `tensor_shape_list()`      | Converter shape para lista de `int`                  |
| `qparams_np()`             | Obter parâmetros completos de quantização            |

---

# 98. Resumo das constantes

| Constante         | Responsabilidade                           |
| ----------------- | ------------------------------------------ |
| `TENSOR_TYPE_MAP` | Relacionar tipo TFLite, nome e dtype NumPy |
| `BYTES_PER_TYPE`  | Informar tamanho em bytes de cada elemento |

---

# 99. Resumo conceitual

O módulo pode ser resumido por:

```text
            Binding TFLite
                  │
                  ▼
        ┌───────────────────┐
        │ tflite_utils.py   │
        └───────────────────┘
                  │
        ┌─────────┼───────────┐
        │         │           │
        ▼         ▼           ▼
   operadores   tensors   quantização
        │         │           │
        ▼         ▼           ▼
     nomes      arrays      scales
                bytes       zero points
                shapes      qdim
        │         │           │
        └─────────┼───────────┘
                  ▼
          módulos superiores
```

A responsabilidade central é:

```text
transformar estruturas de baixo nível
do binding TFLite

em informações simples e consistentes
para o restante do extrator
```

---

# 100. Papel no projeto completo

Até este ponto, a arquitetura pode ser visualizada assim:

```text
┌─────────────────────────────┐
│          config.py          │
│                             │
│ caminhos                    │
│ políticas                   │
│ alinhamento                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      model_loader.py        │
│                             │
│ arquivo → Model             │
│ Model → SubGraph            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      tflite_utils.py        │
│                             │
│ normaliza tipos             │
│ lê buffers                  │
│ lê shapes                   │
│ lê quantização              │
│ resolve nomes de ops        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ módulos de engenharia       │
│                             │
│ graph                       │
│ weights                     │
│ quantization                │
│ memory                      │
│ layer_params                │
└─────────────────────────────┘
```

`model_loader.py` torna o arquivo TFLite navegável.

`tflite_utils.py` torna essa estrutura navegável **conveniente de usar**.

Essa distinção é importante:

```text
model_loader
    ↓
abre a estrutura

tflite_utils
    ↓
traduz e normaliza a estrutura

demais módulos
    ↓
aplicam a lógica específica do extrator
```

Por isso, apesar de ser um módulo de utilidades, ele ocupa uma posição central na arquitetura do pipeline.
