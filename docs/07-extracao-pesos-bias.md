# 07 — Extração e serialização de pesos e bias (`weights.py`)

## 1. Objetivo do módulo

O arquivo `extractor/weights.py` extrai do modelo TFLite os tensors constantes correspondentes aos pesos e bias das operações que possuem parâmetros treináveis.

Seu objetivo é transformar diversos buffers separados do arquivo TFLite em dois blocos binários contínuos:

```text
weights_raw
bias_raw
```

Além disso, o módulo registra onde cada tensor foi colocado dentro desses blocos.

O resultado conceitual é:

```text
TFLite

peso tensor 10 ──┐
peso tensor 20 ──┼──► weights_raw
peso tensor 35 ──┘

bias tensor 11 ──┐
bias tensor 21 ──┼──► bias_raw
bias tensor 36 ──┘
```

Cada tensor recebe um offset relativo:

```text
tensor 10 → offset 0
tensor 20 → offset 864
tensor 35 → offset 1728
```

Esses offsets serão utilizados posteriormente para calcular os endereços reais dentro da memória linear do WebAssembly.

---

# 2. Código atual

```python
from extractor.tflite_utils import (
    op_name,
    safe_bytes_from_tensor,
)


WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}


def extract_weights_and_bias(
    model,
    subgraph,
):
    """
    Extrai os pesos e bias das operações que possuem
    parâmetros treináveis.

    Retorna:
        weights_raw:
            bloco contínuo contendo os bytes dos pesos.

        bias_raw:
            bloco contínuo contendo os bytes dos bias.

        weight_tensor_off:
            tensor_id -> offset do peso dentro de weights_raw.

        bias_tensor_off:
            tensor_id -> offset do bias dentro de bias_raw.

        weight_records:
            metadados utilizados para relatório.

        bias_records:
            metadados utilizados para relatório.
    """

    weights_raw = bytearray()
    bias_raw = bytearray()

    weight_tensor_off = {}
    bias_tensor_off = {}

    weight_records = []
    bias_records = []

    for op_idx in range(
        subgraph.OperatorsLength()
    ):
        op = subgraph.Operators(
            op_idx
        )

        op_type = op_name(
            model,
            op,
        )

        if op_type not in WEIGHT_OPERATORS:
            continue

        input_ids = [
            int(tensor_id)
            for tensor_id
            in op.InputsAsNumpy()
            if int(tensor_id) >= 0
        ]

        # Essas operações precisam de pelo menos:
        #
        # input[0] = ativação
        # input[1] = pesos
        #
        if len(input_ids) < 2:
            continue

        # ====================================================
        # PESOS
        # ====================================================

        weight_tensor_id = input_ids[1]

        (
            weight_tensor,
            weight_array,
            weight_raw,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            weight_tensor_id,
        )

        if (
            weight_array is not None
            and weight_tensor_id
            not in weight_tensor_off
        ):
            offset = len(
                weights_raw
            )

            weight_tensor_off[
                weight_tensor_id
            ] = offset

            weights_raw.extend(
                weight_raw
            )

            weight_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        weight_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        weight_raw
                    ),
                    "shape": list(
                        weight_array.shape
                    ),
                    "dtype": str(
                        weight_array.dtype
                    ),
                }
            )

        # ====================================================
        # BIAS
        # ====================================================

        if len(input_ids) < 3:
            continue

        bias_tensor_id = input_ids[2]

        (
            bias_tensor,
            bias_array,
            bias_raw_tensor,
        ) = safe_bytes_from_tensor(
            model,
            subgraph,
            bias_tensor_id,
        )

        if (
            bias_array is not None
            and bias_array.ndim == 1
            and bias_tensor_id
            not in bias_tensor_off
        ):
            offset = len(
                bias_raw
            )

            bias_tensor_off[
                bias_tensor_id
            ] = offset

            bias_raw.extend(
                bias_raw_tensor
            )

            bias_records.append(
                {
                    "op_index": op_idx,
                    "op_type": op_type,
                    "tensor_id": (
                        bias_tensor_id
                    ),
                    "offset": offset,
                    "nbytes": len(
                        bias_raw_tensor
                    ),
                    "shape": list(
                        bias_array.shape
                    ),
                    "dtype": str(
                        bias_array.dtype
                    ),
                }
            )

    return {
        "weights_raw": bytes(
            weights_raw
        ),

        "bias_raw": bytes(
            bias_raw
        ),

        "weight_tensor_off": (
            weight_tensor_off
        ),

        "bias_tensor_off": (
            bias_tensor_off
        ),

        "weight_records": (
            weight_records
        ),

        "bias_records": (
            bias_records
        ),
    }


def weights_bias_to_text(
    extraction,
):
    ...
```

---

# 3. Posição no pipeline

O fluxo até esta etapa é:

```text
model.tflite
     │
     ▼
model_loader.py
     │
     ▼
Model + SubGraph
     │
     ├── graph.py
     ├── slots.py
     ├── tensor_mapping.py
     │
     ▼
weights.py
     │
     ├── weights_raw
     ├── bias_raw
     ├── weight_tensor_off
     └── bias_tensor_off
```

Esse módulo não trabalha com ativações temporárias.

Ele trabalha com parâmetros constantes da rede.

---

# 4. Duas grandes categorias de memória

Neste ponto do projeto torna-se importante separar:

```text
ATIVAÇÕES
```

de:

```text
PARÂMETROS CONSTANTES
```

As ativações utilizam:

```text
SLOT0
SLOT1
SLOT2
```

Já pesos e bias utilizam regiões próprias:

```text
WEIGHTS
BIAS
```

Conceitualmente:

```text
memória WASM

┌──────────────────────┐
│ região inicial       │
├──────────────────────┤
│ WEIGHTS              │ ← este módulo
├──────────────────────┤
│ BIAS                 │ ← este módulo
├──────────────────────┤
│ MUL                  │
├──────────────────────┤
│ SHIFT                │
├──────────────────────┤
│ Q6                   │
├──────────────────────┤
│ LayerParams          │
├──────────────────────┤
│ SLOT0                │
├──────────────────────┤
│ SLOT1                │
└──────────────────────┘
```

---

# 5. Importação de `op_name()`

O módulo importa:

```python
op_name
```

de:

```text
tflite_utils.py
```

Essa função transforma o código interno TFLite em nomes como:

```text
CONV_2D
DEPTHWISE_CONV_2D
FULLY_CONNECTED
```

O módulo precisa disso para decidir quais operações possuem pesos e bias que devem ser extraídos.

---

# 6. Importação de `safe_bytes_from_tensor()`

Também é importada:

```python
safe_bytes_from_tensor
```

Sua função é transformar:

```text
tensor_id
```

em:

```text
Tensor TFLite
+
array NumPy
+
bytes lineares
```

Fluxo:

```text
tensor_id
    │
    ▼
safe_bytes_from_tensor()
    │
    ├── tensor
    ├── ndarray
    └── raw bytes
```

`weights.py` utiliza principalmente:

```text
ndarray
raw bytes
```

---

# 7. `WEIGHT_OPERATORS`

O módulo define:

```python
WEIGHT_OPERATORS = {
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "FULLY_CONNECTED",
}
```

Isso delimita explicitamente quais operações serão examinadas para extração de pesos e bias.

A regra atual é:

```text
op_type ∈ WEIGHT_OPERATORS
          │
          ├── sim → analisar parâmetros
          │
          └── não → ignorar
```

---

# 8. Operações consideradas

O conjunto atual contém:

```text
CONV_2D

DEPTHWISE_CONV_2D

FULLY_CONNECTED
```

Outras operações presentes na rede, como:

```text
ADD
MEAN
SOFTMAX
QUANTIZE
```

não passam por essa rotina de extração de pesos e bias.

---

# 9. Por que manter explicitamente um conjunto?

Poderíamos escrever:

```python
if op_type == "CONV_2D":
```

e depois repetir regras.

Mas:

```python
WEIGHT_OPERATORS
```

torna explícito que essas três operações compartilham a mesma convenção estrutural usada pelo extrator:

```text
input[0] = ativação
input[1] = pesos
input[2] = bias, quando presente
```

---

# 10. Função `extract_weights_and_bias()`

A função principal é:

```python
def extract_weights_and_bias(
    model,
    subgraph,
):
```

Ela recebe:

```text
Model
SubGraph
```

e retorna todos os blocos e índices necessários para localizar os parâmetros posteriormente.

---

# 11. Estruturas de bytes

No início são criados:

```python
weights_raw = bytearray()
bias_raw = bytearray()
```

---

# 12. Por que `bytearray`?

`bytearray` é uma estrutura binária mutável.

Ela permite fazer:

```python
weights_raw.extend(
    weight_raw
)
```

repetidamente.

Isso é conveniente porque o tamanho final ainda não é conhecido.

O bloco cresce à medida que os tensors são encontrados.

---

# 13. Exemplo

Inicialmente:

```text
weights_raw = vazio
```

Depois do primeiro tensor:

```text
[ PESO A ]
```

Depois do segundo:

```text
[ PESO A ][ PESO B ]
```

Depois do terceiro:

```text
[ PESO A ][ PESO B ][ PESO C ]
```

Não existe uma região separada por camada.

Todos os tensors são concatenados.

---

# 14. Dicionários de offsets

Também são criados:

```python
weight_tensor_off = {}
bias_tensor_off = {}
```

Eles relacionam:

```text
tensor_id
    ↓
offset dentro do blob
```

---

# 15. Exemplo de `weight_tensor_off`

Suponha:

```text
tensor 10:
400 bytes

tensor 20:
800 bytes

tensor 30:
100 bytes
```

A concatenação será:

```text
offset
0
│
├── tensor 10
│   400 bytes
│
400
│
├── tensor 20
│   800 bytes
│
1200
│
├── tensor 30
│   100 bytes
│
1300
```

Então:

```python
weight_tensor_off = {
    10: 0,
    20: 400,
    30: 1200,
}
```

---

# 16. Offset não é endereço absoluto

Essa distinção é fundamental.

Quando temos:

```python
weight_tensor_off[20] = 400
```

isso NÃO significa:

```text
endereço WASM = 400
```

Significa:

```text
400 bytes depois do início de WEIGHTS
```

---

# 17. Conversão futura

Posteriormente:

```text
WEIGHTS_BASE
+
weight_tensor_off[tensor_id]
=
endereço absoluto
```

Exemplo:

```text
WEIGHTS_BASE = 2048

offset = 400
```

Então:

```text
wptr =
2048 + 400
=
2448
```

---

# 18. Mesmo conceito para bias

Se:

```python
bias_tensor_off[21] = 128
```

e:

```text
BIAS_BASE = 386656
```

então:

```text
bias_ptr =
386656 + 128
```

O offset continua relativo ao seu próprio bloco.

---

# 19. Registros para relatório

Também são criados:

```python
weight_records = []
bias_records = []
```

Essas listas não armazenam o conteúdo binário.

Armazenam metadados:

```text
qual operação
qual tipo
qual tensor
offset
quantidade de bytes
shape
dtype
```

---

# 20. Separação entre dados e metadados

Temos:

```text
weights_raw
    ↓
dados efetivamente utilizados no runtime
```

e:

```text
weight_records
    ↓
informações para rastreabilidade
```

Da mesma maneira:

```text
bias_raw
```

versus:

```text
bias_records
```

---

# 21. Varredura dos operadores

A função percorre:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

Portanto examina todos os operadores do subgrafo, na ordem em que aparecem nele.

---

# 22. Recuperando o operador

```python
op = subgraph.Operators(
    op_idx
)
```

Assim temos acesso às entradas daquela operação.

---

# 23. Identificando o tipo

Depois:

```python
op_type = op_name(
    model,
    op,
)
```

produz algo como:

```text
CONV_2D
```

---

# 24. Filtragem

Se:

```python
op_type not in WEIGHT_OPERATORS
```

é executado:

```python
continue
```

Portanto aquela operação não participa da extração.

---

# 25. Exemplo

Uma sequência:

```text
CONV_2D
DEPTHWISE_CONV_2D
ADD
CONV_2D
MEAN
FULLY_CONNECTED
SOFTMAX
```

resulta em processamento apenas de:

```text
CONV_2D
DEPTHWISE_CONV_2D
CONV_2D
FULLY_CONNECTED
```

---

# 26. Coleta dos IDs de entrada

Para uma operação aceita:

```python
input_ids = [
    int(tensor_id)
    for tensor_id
    in op.InputsAsNumpy()
    if int(tensor_id) >= 0
]
```

Essa expressão converte as entradas para uma lista comum de inteiros Python.

---

# 27. Exemplo

Se:

```text
op.InputsAsNumpy()
=
[12, 30, 31]
```

o resultado será:

```python
input_ids = [
    12,
    30,
    31,
]
```

---

# 28. Entradas negativas

IDs negativos são descartados:

```python
if int(tensor_id) >= 0
```

Assim, apenas referências válidas permanecem.

---

# 29. Convenção de inputs

O módulo trabalha com a convenção:

```text
input[0] = ativação

input[1] = pesos

input[2] = bias
```

quando o terceiro input existe.

Essa convenção é central para a implementação.

---

# 30. Exemplo

Uma operação pode possuir:

```python
input_ids = [
    45,
    46,
    47,
]
```

O módulo interpreta:

```text
tensor 45 → ativação

tensor 46 → pesos

tensor 47 → bias
```

---

# 31. Operação sem peso suficiente

Antes de tentar acessar:

```python
input_ids[1]
```

existe:

```python
if len(input_ids) < 2:
    continue
```

Isso evita:

```text
IndexError
```

e também indica que aquela operação não possui a estrutura mínima esperada para extração de pesos.

---

# 32. Extração do tensor de pesos

O peso é identificado por:

```python
weight_tensor_id = (
    input_ids[1]
)
```

---

# 33. Leitura do peso

Depois:

```python
(
    weight_tensor,
    weight_array,
    weight_raw,
) = safe_bytes_from_tensor(
    model,
    subgraph,
    weight_tensor_id,
)
```

São recebidas três representações.

---

# 34. `weight_tensor`

É o próprio objeto TFLite.

Na implementação atual ele é atribuído à variável:

```python
weight_tensor
```

mas não é utilizado posteriormente dentro da função.

Sua presença decorre da interface uniforme de:

```python
safe_bytes_from_tensor()
```

---

# 35. `weight_array`

É o array NumPy contendo os valores dos pesos.

Ele fornece informações como:

```text
shape
dtype
ndim
```

Exemplo:

```python
weight_array.shape
```

e:

```python
weight_array.dtype
```

---

# 36. `weight_raw`

É o bloco de bytes linear correspondente ao tensor.

É essa representação que será concatenada em:

```python
weights_raw
```

---

# 37. Condição de inserção

O tensor só é incluído se:

```python
weight_array is not None
```

e:

```python
weight_tensor_id
not in weight_tensor_off
```

---

# 38. Primeira condição

```python
weight_array is not None
```

significa que:

```text
safe_bytes_from_tensor()
```

conseguiu efetivamente recuperar e interpretar o buffer.

---

# 39. Segunda condição

```python
weight_tensor_id
not in weight_tensor_off
```

evita inserir o mesmo tensor mais de uma vez.

---

# 40. Por que a deduplicação é importante?

Pode existir uma situação em que mais de uma operação faça referência ao mesmo tensor constante.

Sem a verificação:

```text
tensor X
```

poderia aparecer duas vezes em:

```text
weights_raw
```

desperdiçando memória.

---

# 41. Exemplo de compartilhamento

Suponha:

```text
Op10 utiliza tensor 50

Op20 também utiliza tensor 50
```

Na primeira ocorrência:

```text
tensor 50 → extraído
```

Na segunda:

```text
tensor 50 já existe em weight_tensor_off
```

Logo:

```text
não é duplicado
```

Ambas as operações poderão utilizar o mesmo offset.

---

# 42. Determinação do offset

Antes de inserir os bytes:

```python
offset = len(
    weights_raw
)
```

O comprimento atual do bloco é exatamente o próximo endereço relativo livre.

---

# 43. Exemplo

Se:

```text
weights_raw contém 15.000 bytes
```

então o próximo tensor começa em:

```text
offset = 15000
```

---

# 44. Registro do offset

Depois:

```python
weight_tensor_off[
    weight_tensor_id
] = offset
```

Exemplo:

```python
weight_tensor_off[50] = 15000
```

---

# 45. Inserção dos bytes

```python
weights_raw.extend(
    weight_raw
)
```

Os bytes são concatenados imediatamente após o conteúdo anterior.

---

# 46. Layout progressivo

Antes:

```text
weights_raw

[ A ][ B ]
```

Depois:

```text
weights_raw

[ A ][ B ][ NOVO PESO ]
```

---

# 47. Não existe alinhamento entre tensors aqui

Um detalhe importante da implementação atual é que `weights.py` simplesmente concatena os tensors.

Não existe:

```text
align_up()
```

entre um tensor de pesos e o seguinte.

Portanto:

```text
offset seguinte =
offset atual + número de bytes atual
```

---

# 48. Alinhamento ocorre em outro nível

O `ALIGN = 16` utilizado pelo projeto participa posteriormente do posicionamento das grandes regiões:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOTS
```

Este módulo não insere padding de alinhamento entre os tensors individuais de pesos.

---

# 49. Registro de metadados

Depois da inserção é criado:

```python
{
    "op_index": op_idx,
    "op_type": op_type,
    "tensor_id": weight_tensor_id,
    "offset": offset,
    "nbytes": len(weight_raw),
    "shape": list(
        weight_array.shape
    ),
    "dtype": str(
        weight_array.dtype
    ),
}
```

---

# 50. Campo `op_index`

Exemplo:

```text
op_index = 12
```

informa qual operação levou à descoberta daquele tensor.

---

# 51. Campo `op_type`

Exemplo:

```text
CONV_2D
```

permite identificar semanticamente a operação.

---

# 52. Campo `tensor_id`

Identifica o tensor original no TFLite.

Exemplo:

```text
tensor_id = 78
```

---

# 53. Campo `offset`

É a posição relativa dentro de:

```text
weights_raw
```

Exemplo:

```text
offset = 25856
```

---

# 54. Campo `nbytes`

```python
len(
    weight_raw
)
```

informa quantos bytes aquele tensor ocupa.

---

# 55. Campo `shape`

O código utiliza:

```python
list(
    weight_array.shape
)
```

produzindo algo como:

```python
[
    32,
    3,
    3,
    3,
]
```

---

# 56. Por que usar `list(weight_array.shape)`?

`NumPy.shape` é uma tupla.

Por exemplo:

```python
(32, 3, 3, 3)
```

O relatório utiliza uma lista comum:

```python
[32, 3, 3, 3]
```

Essa transformação também padroniza a estrutura retornada.

---

# 57. Campo `dtype`

```python
str(
    weight_array.dtype
)
```

produz uma representação textual como:

```text
int8
```

---

# 58. Forma dos pesos

O módulo não interpreta semanticamente as dimensões do peso.

Ele apenas registra:

```python
weight_array.shape
```

e preserva a ordem dos bytes produzida por:

```python
safe_bytes_from_tensor()
```

Ou seja, `weights.py` não faz aqui:

```text
transposição
reordenação de canais
conversão de layout
```

---

# 59. Consequência

O código WAT que posteriormente lê os pesos precisa ser compatível com a disposição serializada pelo pipeline.

Este módulo apenas:

```text
lê
concatena
registra offset
```

---

# 60. Início da extração de bias

Depois dos pesos:

```python
if len(input_ids) < 3:
    continue
```

Se não existir um terceiro input, a operação não possui bias tratado por esta função.

---

# 61. Isso não cancela a extração do peso

É importante observar a posição dessa verificação.

O peso já foi processado antes.

Logo:

```text
2 inputs
```

pode resultar em:

```text
peso extraído
bias inexistente
```

---

# 62. Identificação do bias

Quando existe terceiro input:

```python
bias_tensor_id = (
    input_ids[2]
)
```

---

# 63. Leitura do bias

```python
(
    bias_tensor,
    bias_array,
    bias_raw_tensor,
) = safe_bytes_from_tensor(
    model,
    subgraph,
    bias_tensor_id,
)
```

---

# 64. Nomenclatura `bias_raw_tensor`

Aqui o nome é diferente de:

```python
bias_raw
```

porque:

```text
bias_raw_tensor
```

representa apenas o tensor atualmente extraído,

enquanto:

```text
bias_raw
```

é o blob completo acumulado.

---

# 65. Exemplo

```text
bias_raw_tensor
=
bytes de um único bias
```

Enquanto:

```text
bias_raw
=
[bias A][bias B][bias C][...]
```

---

# 66. `bias_tensor`

Assim como:

```python
weight_tensor
```

a variável:

```python
bias_tensor
```

é recebida de `safe_bytes_from_tensor()` mas não é utilizada posteriormente na função atual.

---

# 67. Condições para inserir bias

A condição é:

```python
if (
    bias_array is not None
    and bias_array.ndim == 1
    and bias_tensor_id
    not in bias_tensor_off
):
```

Existem três verificações.

---

# 68. Bias precisa existir

```python
bias_array is not None
```

indica que o buffer pôde ser recuperado.

---

# 69. Bias precisa ser unidimensional

```python
bias_array.ndim == 1
```

é uma validação estrutural adicional.

Exemplo aceito:

```text
shape = [32]
```

---

# 70. Exemplo não aceito

Algo como:

```text
shape = [1, 32]
```

possui:

```text
ndim = 2
```

e portanto não seria inserido por esta implementação.

---

# 71. Por que essa verificação é útil?

Ela garante que a estrutura utilizada pelo runtime para bias corresponda ao formato que o restante do projeto espera.

O módulo não tenta corrigir ou remodelar um bias com shape inesperado.

---

# 72. Deduplicação do bias

A terceira condição:

```python
bias_tensor_id
not in bias_tensor_off
```

possui a mesma finalidade usada nos pesos:

```text
não armazenar duas vezes o mesmo tensor constante
```

---

# 73. Offset do bias

O offset é:

```python
offset = len(
    bias_raw
)
```

Exemplo:

```text
bias_raw atual = 1024 bytes
```

Então:

```text
novo bias começa no offset 1024
```

---

# 74. Registro

```python
bias_tensor_off[
    bias_tensor_id
] = offset
```

---

# 75. Concatenação

```python
bias_raw.extend(
    bias_raw_tensor
)
```

---

# 76. Registro de metadados

A estrutura é equivalente à dos pesos:

```python
{
    "op_index": op_idx,
    "op_type": op_type,
    "tensor_id": bias_tensor_id,
    "offset": offset,
    "nbytes": len(
        bias_raw_tensor
    ),
    "shape": list(
        bias_array.shape
    ),
    "dtype": str(
        bias_array.dtype
    ),
}
```

---

# 77. Exemplo de bias

Suponha:

```text
shape = [32]
dtype = int32
```

Como:

```text
32 × 4 bytes = 128 bytes
```

o registro pode conter:

```text
bytes = 128
```

O tamanho real é obtido diretamente do buffer serializado.

---

# 78. Dois blobs independentes

Pesos e bias não são misturados.

Temos:

```text
weights_raw

[W0][W1][W2][W3]...
```

e separadamente:

```text
bias_raw

[B0][B1][B2][B3]...
```

---

# 79. Por que separar?

Posteriormente o layout de memória possui:

```text
WEIGHTS_BASE
```

e:

```text
BIAS_BASE
```

independentes.

Isso permite calcular:

```text
wptr =
WEIGHTS_BASE + weight_offset
```

e:

```text
bias_ptr =
BIAS_BASE + bias_offset
```

---

# 80. Relação com `LayerParam`

Mais tarde uma convolução pode possuir:

```text
wptr
bias_ptr
```

Esses ponteiros são calculados usando os mapas gerados aqui.

Fluxo:

```text
weight tensor_id
      ↓
weight_tensor_off
      ↓
offset
      ↓
WEIGHTS_BASE + offset
      ↓
wptr
```

E:

```text
bias tensor_id
      ↓
bias_tensor_off
      ↓
offset
      ↓
BIAS_BASE + offset
      ↓
bias_ptr
```

---

# 81. Retorno da função

Ao final:

```python
return {
    ...
}
```

é criada uma estrutura única contendo dados e metadados.

---

# 82. Conversão de `bytearray` para `bytes`

O retorno utiliza:

```python
"bytes_raw": bytes(...)
```

mais especificamente:

```python
"weights_raw": bytes(
    weights_raw
)
```

e:

```python
"bias_raw": bytes(
    bias_raw
)
```

---

# 83. Por que converter?

Durante a construção precisamos de mutabilidade:

```text
bytearray
```

Depois que a extração terminou, o blob pode ser tratado como dados binários prontos:

```text
bytes
```

---

# 84. Ciclo de vida

```text
início
  ↓
bytearray mutável
  ↓
extend()
extend()
extend()
  ↓
extração concluída
  ↓
bytes imutáveis
```

---

# 85. Estrutura retornada

O resultado possui:

```python
{
    "weights_raw": ...,
    "bias_raw": ...,
    "weight_tensor_off": ...,
    "bias_tensor_off": ...,
    "weight_records": ...,
    "bias_records": ...,
}
```

---

# 86. Dados necessários para execução

Os campos diretamente utilizados posteriormente na geração do artefato são principalmente:

```text
weights_raw
bias_raw

weight_tensor_off
bias_tensor_off
```

---

# 87. Dados para relatório

Principalmente:

```text
weight_records
bias_records
```

Embora também seja possível utilizar os blobs para calcular os totais de bytes.

---

# 88. Exemplo de saída completa

Considere duas operações.

```text
Op0 CONV
peso tensor 10
bias tensor 11

Op1 CONV
peso tensor 20
bias tensor 21
```

Suponha:

```text
tensor 10 = 100 bytes
tensor 20 = 200 bytes

tensor 11 = 16 bytes
tensor 21 = 32 bytes
```

---

# 89. `weights_raw`

```text
offset 0
│
├── tensor 10
│   100 bytes
│
offset 100
│
├── tensor 20
│   200 bytes
│
offset 300
```

---

# 90. `weight_tensor_off`

```python
{
    10: 0,
    20: 100,
}
```

---

# 91. `bias_raw`

```text
offset 0
│
├── tensor 11
│   16 bytes
│
offset 16
│
├── tensor 21
│   32 bytes
│
offset 48
```

---

# 92. `bias_tensor_off`

```python
{
    11: 0,
    21: 16,
}
```

---

# 93. Endereços futuros

Se depois:

```text
WEIGHTS_BASE = 2048
BIAS_BASE = 10000
```

teremos:

```text
tensor 10:
wptr = 2048 + 0

tensor 20:
wptr = 2048 + 100
```

e:

```text
tensor 11:
bias_ptr = 10000 + 0

tensor 21:
bias_ptr = 10000 + 16
```

---

# 94. Offsets independentes

Note que:

```text
weight offset = 0
```

e:

```text
bias offset = 0
```

podem coexistir.

Não há conflito porque pertencem a regiões diferentes.

---

# 95. Importante: offset lógico por blob

Portanto:

```text
offset 128 em weights_raw
```

e:

```text
offset 128 em bias_raw
```

são posições completamente diferentes.

Sempre é necessário interpretar o offset junto com sua base.

---

# 96. Relação com o TFLite

No arquivo TFLite, cada tensor constante pode apontar para seu próprio buffer.

Conceitualmente:

```text
Tensor W0 → Buffer X
Tensor B0 → Buffer Y
Tensor W1 → Buffer Z
...
```

O módulo reorganiza isso para:

```text
WEIGHTS

W0 | W1 | W2 | W3 | ...


BIAS

B0 | B1 | B2 | B3 | ...
```

---

# 97. Transformação estrutural

Portanto este módulo realiza uma verdadeira transformação de representação:

```text
buffers distribuídos no TFLite
          ↓
blobs contínuos do runtime
```

---

# 98. Ele não altera os valores

Apesar de reorganizar a localização, o código não modifica numericamente os valores extraídos.

Ele recebe:

```python
weight_raw
```

e faz:

```python
weights_raw.extend(
    weight_raw
)
```

---

# 99. Ausência de conversão de tipo

Não há aqui:

```text
int8 → float32
int32 → int8
```

nem qualquer outra conversão numérica explícita.

O dtype original interpretado por `safe_bytes_from_tensor()` é preservado na representação serializada retornada por essa função.

---

# 100. Ausência de quantização neste módulo

Embora os pesos sejam quantizados no modelo utilizado, `weights.py` não calcula:

```text
scale
zero point
multiplier
shift
Q6
```

Essa responsabilidade pertence a:

```text
quantization.py
```

---

# 101. Separação importante

```text
weights.py
    ↓
quais são os bytes dos pesos?
onde cada tensor fica no blob?


quantization.py
    ↓
como a saída acumulada deve ser requantizada?
```

São problemas diferentes.

---

# 102. Ausência de endereço absoluto

Também não são calculados:

```text
WEIGHTS_BASE
BIAS_BASE
```

Essa responsabilidade pertence ao planejamento de memória.

---

# 103. Separação

```text
weights.py
   ↓
offset relativo

memory.py
   ↓
base absoluta

layer_params.py
   ↓
base + offset
```

---

# 104. Relação com `memory.py`

`memory.py` utiliza os tamanhos:

```python
len(
    weights_raw
)
```

e:

```python
len(
    bias_raw
)
```

para planejar onde cada região será colocada.

Exemplo:

```text
KERNEL_BASE
   │
   ├── weights_raw
   │
   ▼
fim dos pesos
   │
   ▼
align_up()
   │
   ▼
BIAS_BASE
   │
   ├── bias_raw
```

---

# 105. Relação com `wat_generator.py`

Na geração final:

```text
weights_raw
```

é convertido em um data segment no endereço:

```text
WEIGHTS_BASE
```

E:

```text
bias_raw
```

no endereço:

```text
BIAS_BASE
```

Conceitualmente:

```wat
(data
    (i32.const WEIGHTS_BASE)
    "...bytes..."
)
```

---

# 106. Blobs como artefatos intermediários

Isso permite enxergar:

```text
weights_raw
bias_raw
```

como artefatos binários intermediários independentes do WAT.

O gerador WAT apenas os consome.

---

# 107. Benefício arquitetural

Antes poderíamos ter:

```text
extração de peso
      ↓
imediatamente gera string WAT
```

Agora temos:

```text
extração
   ↓
bytes estruturados
   ↓
layout de memória
   ↓
gerador
   ↓
WAT
```

Isso facilita validação e reutilização.

---

# 108. Função `weights_bias_to_text()`

A segunda função:

```python
def weights_bias_to_text(
    extraction,
):
```

transforma os metadados em relatório legível.

Ela não participa da extração.

---

# 109. Primeira seção: PESOS

Começa com:

```python
lines.append(
    "PESOS"
)
```

e:

```python
lines.append(
    "=" * 80
)
```

---

# 110. Percorrendo `weight_records`

```python
for item in extraction[
    "weight_records"
]:
```

Cada tensor extraído gera uma linha.

---

# 111. Conteúdo da linha

O relatório imprime:

```text
op
tipo da operação
tensor
offset
bytes
shape
dtype
```

---

# 112. Exemplo

Algo semelhante a:

```text
op=  3 CONV_2D                  tensor=  12 offset=       0 bytes=     864 shape=[32, 3, 3, 3] dtype=int8
```

---

# 113. Campo `op`

```python
f"op={item['op_index']:3}"
```

O especificador:

```text
:3
```

serve apenas para alinhamento visual.

---

# 114. Campo `op_type`

```python
f"{item['op_type']:25}"
```

reserva 25 posições no relatório.

---

# 115. Campo `tensor`

```python
f"tensor={item['tensor_id']:4}"
```

permite localizar o tensor no modelo.

---

# 116. Campo `offset`

```python
f"offset={item['offset']:8}"
```

é o deslocamento relativo dentro de `weights_raw`.

Não é endereço absoluto.

---

# 117. Campo `bytes`

```python
f"bytes={item['nbytes']:8}"
```

indica o tamanho daquele tensor.

---

# 118. Campo `shape`

```python
f"shape={item['shape']}"
```

mostra as dimensões interpretadas.

---

# 119. Campo `dtype`

```python
f"dtype={item['dtype']}"
```

mostra a interpretação dos elementos.

---

# 120. Segunda seção: BIAS

Depois é gerada:

```text
BIAS
================================================================================
```

utilizando:

```python
bias_records
```

com a mesma estrutura de campos.

---

# 121. Benefício da simetria

O relatório permite comparar facilmente:

```text
operação
peso
bias
```

mesmo que ambos estejam em blocos diferentes.

---

# 122. Seção de resumo

A última parte é:

```text
RESUMO
================================================================================
```

Ela apresenta quatro totais.

---

# 123. Quantidade de tensors de peso

```python
len(
    extraction[
        "weight_records"
    ]
)
```

---

# 124. Quantidade total de bytes dos pesos

```python
len(
    extraction[
        "weights_raw"
    ]
)
```

---

# 125. Quantidade de tensors de bias

```python
len(
    extraction[
        "bias_records"
    ]
)
```

---

# 126. Quantidade total de bytes dos bias

```python
len(
    extraction[
        "bias_raw"
    ]
)
```

---

# 127. Exemplo de resumo

```text
RESUMO
================================================================================
Total de tensors de pesos: 54
Total de bytes de pesos: 384608
Total de tensors de bias: 52
Total de bytes de bias: 28176
```

Os números acima são apenas ilustrativos; o relatório real utiliza os valores da execução.

---

# 128. Por que contagem de registros e contagem de operadores podem diferir?

A quantidade de:

```text
weight_records
```

não precisa obrigatoriamente ser igual ao número de operações examinadas.

Isso ocorre porque o código deduplica por:

```text
tensor_id
```

---

# 129. Exemplo

```text
Op10 → peso tensor 50
Op20 → peso tensor 50
```

Existem:

```text
2 referências operacionais
```

mas apenas:

```text
1 tensor armazenado
```

Logo:

```text
weight_records = 1
```

---

# 130. Ordem dos blobs

A ordem dos tensors em:

```text
weights_raw
```

é determinada pela primeira vez em que cada tensor é encontrado durante a varredura:

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

---

# 131. Consequência

O layout não é ordenado por:

```text
tensor_id
```

e nem por:

```text
tamanho
```

Ele segue essencialmente:

```text
ordem dos operadores
+
primeira ocorrência de cada tensor
```

---

# 132. Exemplo

Se a varredura encontrar:

```text
tensor 50
tensor 12
tensor 90
```

nessa ordem, o blob será:

```text
[ tensor 50 ][ tensor 12 ][ tensor 90 ]
```

mesmo que numericamente:

```text
12 < 50 < 90
```

---

# 133. Por que isso não é problema?

Porque o runtime não pressupõe a ordem pelo ID.

Ele utiliza:

```text
tensor_id → offset
```

Logo a localização real é explicitamente registrada.

---

# 134. Invariante importante dos offsets

Para cada tensor armazenado:

```text
offset + nbytes
```

não deve ultrapassar:

```text
len(blob)
```

Exemplo:

```text
offset = 1000
nbytes = 200
```

Então os bytes ocupam:

```text
1000 ... 1199
```

e:

```text
1200 <= len(weights_raw)
```

ao final da construção.

---

# 135. Contiguidade

Como a inserção sempre utiliza:

```python
offset = len(blob)
blob.extend(data)
```

os tensors ficam contíguos.

Não existem lacunas internas criadas por este módulo.

---

# 136. Exemplo

```text
tensor A:
offset = 0
size = 100

tensor B:
offset = 100
size = 50

tensor C:
offset = 150
size = 20
```

Logo:

```text
[0..........99][100....149][150...169]
```

---

# 137. Último offset

Se o último tensor começa em:

```text
offset = 150
```

e possui:

```text
20 bytes
```

o tamanho total é:

```text
170 bytes
```

---

# 138. Por que offsets relativos são melhores?

Se `weights.py` calculasse diretamente:

```text
wptr = 2448
```

ficaria acoplado ao layout físico atual.

Com offset relativo:

```text
tensor → 400
```

podemos mudar:

```text
WEIGHTS_BASE
```

sem reextrair ou reorganizar internamente os pesos.

---

# 139. Exemplo

Hoje:

```text
WEIGHTS_BASE = 2048
offset = 400
wptr = 2448
```

Amanhã:

```text
WEIGHTS_BASE = 4096
offset = 400
wptr = 4496
```

O blob permanece o mesmo.

---

# 140. Separação entre conteúdo e posicionamento

Essa é uma decisão arquitetural importante:

```text
weights.py
   ↓
conteúdo + offsets internos
```

```text
memory.py
   ↓
onde o bloco inteiro começa
```

```text
layer_params.py
   ↓
endereço final usado pela operação
```

---

# 141. Relação com `params_blob`

Posteriormente a `LayerParam` de uma convolução contém:

```text
wptr
bias_ptr
```

Não contém apenas:

```text
tensor_id
```

Por isso os offsets deste módulo precisam ser convertidos em ponteiros antes da serialização.

---

# 142. Fluxo completo dos pesos

```text
TFLite tensor de peso
        │
        ▼
safe_bytes_from_tensor()
        │
        ├── array
        └── raw
             │
             ▼
weights.py
        │
        ├── weights_raw
        └── weight_tensor_off
             │
             ▼
memory.py
        │
        └── WEIGHTS_BASE
             │
             ▼
layer_params / params_blob
        │
        └── wptr
             │
             ▼
WAT/WASM
```

---

# 143. Fluxo completo do bias

```text
TFLite tensor de bias
        │
        ▼
safe_bytes_from_tensor()
        │
        ├── array
        └── raw
             │
             ▼
weights.py
        │
        ├── bias_raw
        └── bias_tensor_off
             │
             ▼
memory.py
        │
        └── BIAS_BASE
             │
             ▼
LayerParam
        │
        └── bias_ptr
             │
             ▼
WAT/WASM
```

---

# 144. Diferença para `tensor_mapping.py`

`tensor_mapping.py` trata tensors de ativação:

```text
tensor → SLOT
```

`weights.py` trata tensors constantes:

```text
tensor → OFFSET
```

Essa distinção é fundamental.

---

# 145. Comparação

| Tipo de tensor | Estrutura           |
| -------------- | ------------------- |
| Ativação       | `tensor_to_slot`    |
| Peso           | `weight_tensor_off` |
| Bias           | `bias_tensor_off`   |

Posteriormente todos serão convertidos em endereços de memória.

---

# 146. Exemplo completo de uma convolução

Suponha:

```text
CONV_2D

input[0] = tensor 100
input[1] = tensor 101
input[2] = tensor 102
```

Após etapas anteriores:

```text
tensor 100 → SLOT1
```

Após `weights.py`:

```text
tensor 101 → weight offset 5000
tensor 102 → bias offset 256
```

Depois do layout:

```text
SLOT1_BASE = 700000

WEIGHTS_BASE = 2048

BIAS_BASE = 386656
```

Os ponteiros tornam-se:

```text
in_ptr =
700000
```

```text
wptr =
2048 + 5000
=
7048
```

```text
bias_ptr =
386656 + 256
=
386912
```

Essa é a informação que finalmente será serializada para o runtime.

---

# 147. Por que pesos não precisam de slot?

Pesos não são produzidos durante a inferência.

Eles já existem antes da primeira imagem.

Portanto sua vida útil é conceitualmente:

```text
início do módulo
        ↓
toda a inferência
        ↓
fim
```

Não faz sentido tratá-los como ativações temporárias reutilizáveis.

---

# 148. Por que bias também não precisa de slot?

Pelo mesmo motivo.

O bias é constante durante a execução.

Ele reside em sua região permanente:

```text
BIAS
```

---

# 149. Custo de memória

O tamanho de:

```text
weights_raw
```

contribui diretamente para o consumo de memória linear.

Portanto esta etapa também produz uma das principais informações necessárias ao cálculo posterior de:

```text
MEM_END
MEM_PAGES
```

---

# 150. Dados extraídos versus dados calculados

Os bytes de:

```text
weights_raw
bias_raw
```

vêm do modelo.

Já os offsets:

```text
weight_tensor_off
bias_tensor_off
```

são construídos pelo extrator.

Portanto temos:

```text
dados extraídos
    ↓
raw bytes
```

e:

```text
dados derivados
    ↓
offsets
```

---

# 151. O que este módulo deliberadamente não faz

`weights.py` não:

```text
calcula scales
calcula zero points
calcula multiplier
calcula shift
calcula Q6

calcula WEIGHTS_BASE
calcula BIAS_BASE

calcula slots
calcula ponteiros finais

gera LayerParam
gera WAT
```

---

# 152. Responsabilidade exata

Ele responde apenas:

```text
quais bytes pertencem aos pesos?

quais bytes pertencem aos bias?

em que offset interno cada tensor foi colocado?
```

---

# 153. Validação atual

O módulo possui algumas validações implícitas.

Para pesos:

```text
operação suportada
mínimo 2 inputs
buffer recuperável
tensor ainda não armazenado
```

Para bias:

```text
mínimo 3 inputs
buffer recuperável
array unidimensional
tensor ainda não armazenado
```

---

# 154. O que não é validado aqui?

O módulo não verifica explicitamente:

```text
se o dtype do peso é exatamente o esperado pelo runtime

se o dtype do bias é exatamente o esperado

se o número de elementos do bias coincide com o número de canais

se o shape dos pesos é semanticamente compatível com a operação
```

Ele registra:

```text
shape
dtype
```

para inspeção, mas não impõe essas propriedades aqui.

---

# 155. Por que isso importa?

Se futuramente o extrator aceitar modelos mais variados, poderá ser desejável transformar essas expectativas em validações formais.

No estado atual, a responsabilidade está concentrada em extrair corretamente o modelo utilizado pelo projeto.

---

# 156. Variáveis `weight_tensor` e `bias_tensor`

O código possui:

```python
weight_tensor
```

e:

```python
bias_tensor
```

mas elas não são usadas após a chamada.

Isso não representa erro funcional.

A função:

```python
safe_bytes_from_tensor()
```

retorna sempre três componentes:

```text
tensor
array
raw
```

e `weights.py` utiliza apenas os dois últimos.

---

# 157. Poderiam ser substituídas por `_`?

Tecnicamente seria possível escrever:

```python
(
    _,
    weight_array,
    weight_raw,
) = safe_bytes_from_tensor(...)
```

Mas a implementação atual mantém os nomes explícitos.

Para a documentação é importante apenas registrar que:

```text
o objeto Tensor é recuperado,
mas não participa dos cálculos desta função.
```

---

# 158. Ordem determinística

Como a varredura ocorre por:

```python
range(
    subgraph.OperatorsLength()
)
```

e a primeira ocorrência determina o offset, a execução com o mesmo modelo produz a mesma ordem de blobs, desde que a estrutura do modelo permaneça a mesma.

Isso contribui para a reprodutibilidade do artefato.

---

# 159. Duplicação evitada

A deduplicação ocorre por:

```text
tensor_id
```

e não por comparação dos bytes.

Portanto dois tensors diferentes com conteúdo idêntico continuam sendo armazenados separadamente.

---

# 160. Exemplo

Se:

```text
tensor 10 = [1,2,3]

tensor 20 = [1,2,3]
```

mas os IDs são diferentes:

```text
10 ≠ 20
```

então ambos são armazenados.

O módulo não realiza deduplicação por conteúdo.

---

# 161. Por que essa decisão é simples e segura?

Do ponto de vista estrutural do modelo:

```text
tensor 10
```

e:

```text
tensor 20
```

são objetos distintos.

Compartilhar memória apenas porque os bytes coincidem introduziria uma otimização adicional que o código atual não tenta realizar.

---

# 162. Relatório como mecanismo de auditoria

Os campos:

```text
op_index
op_type
tensor_id
offset
nbytes
shape
dtype
```

permitem verificar praticamente toda a decisão deste módulo sem imprimir os próprios milhares de bytes.

---

# 163. Exemplo de auditoria

Diante de:

```text
op=15 CONV_2D tensor=89 offset=15200 bytes=2048 shape=[...] dtype=int8
```

podemos verificar:

```text
qual operação usa o peso?

qual tensor era?

onde foi colocado?

quanto ocupa?

qual shape foi lido?

como seus bytes foram interpretados?
```

---

# 164. Por que não imprimir os valores dos pesos?

Uma rede pode possuir centenas de milhares de parâmetros.

Gerar:

```text
peso[0] = ...
peso[1] = ...
peso[2] = ...
```

tornaria o relatório enorme e pouco útil.

Por isso o relatório trabalha em nível de tensor.

---

# 165. Blobs e eficiência

Armazenar os parâmetros em blocos contínuos também simplifica a geração do WAT.

Em vez de gerar um segmento por peso:

```text
data W0
data W1
data W2
...
```

o gerador pode inserir um único bloco:

```text
WEIGHTS
```

e utilizar offsets internos.

---

# 166. Representação conceitual final

```text
                      TFLite
                         │
                         ▼
               operadores suportados
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
       input[1]                    input[2]
        pesos                        bias
           │                           │
           ▼                           ▼
safe_bytes_from_tensor()   safe_bytes_from_tensor()
           │                           │
           ▼                           ▼
      weight_raw                bias_raw_tensor
           │                           │
           ▼                           ▼
     weights_raw                  bias_raw
           │                           │
           ▼                           ▼
 weight_tensor_off            bias_tensor_off
           │                           │
           └─────────────┬─────────────┘
                         ▼
                 layout de memória
```

---

# 167. Papel no pipeline completo

```text
┌────────────────────────────┐
│       TFLite Model         │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│       weights.py           │
│                            │
│ weights_raw                │
│ bias_raw                   │
│ weight_tensor_off          │
│ bias_tensor_off            │
└─────────────┬──────────────┘
              │
       ┌──────┴───────┐
       │              │
       ▼              ▼
quantization.py    memory.py
       │              │
       │              ├── WEIGHTS_BASE
       │              └── BIAS_BASE
       │              │
       └──────┬───────┘
              ▼
       layer_params.py
              │
              ├── wptr
              └── bias_ptr
              │
              ▼
        params_blob.py
              │
              ▼
       wat_generator.py
```

---

# 168. Síntese

O `weights.py` transforma os parâmetros treináveis originalmente distribuídos entre vários buffers do modelo TFLite em uma representação adequada ao runtime desenvolvido no projeto.

A transformação principal é:

```text
TFLite

tensor de peso
tensor de peso
tensor de peso
tensor de bias
tensor de bias

        ↓

runtime

weights_raw
[W0][W1][W2]...

bias_raw
[B0][B1][B2]...
```

Cada tensor recebe um offset:

```text
tensor_id → offset
```

que posteriormente será combinado com uma base de memória:

```text
endereço =
base + offset
```

Essa separação é importante porque permite que este módulo cuide exclusivamente do **conteúdo e da organização interna dos parâmetros**, enquanto `memory.py` decide onde os blocos serão posicionados e `layer_params.py` converte os offsets em ponteiros consumidos pelo WebAssembly.

O módulo também preserva a rastreabilidade por meio de registros contendo:

```text
operação
tensor
offset
tamanho
shape
dtype
```

sem misturar esses metadados com o conteúdo binário efetivamente utilizado na inferência.

Assim, depois de `weights.py`, o pipeline deixa de possuir apenas referências aos buffers TFLite e passa a possuir dois artefatos binários contínuos e diretamente utilizáveis pelo runtime:

```text
weights_raw
bias_raw
```

acompanhados dos mapas necessários para localizar cada tensor dentro deles.
