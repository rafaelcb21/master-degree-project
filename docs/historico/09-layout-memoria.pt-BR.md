[English](09-layout-memoria.md) | [Português (Brasil)](09-layout-memoria.pt-BR.md)

> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.pt-BR.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.pt-BR.md). O corpo original foi mantido.

# 09 — Planejamento da memória linear (`memory.py`)

## 1. Objetivo do módulo

O arquivo `extractor/memory.py` é responsável pelo planejamento da memória linear utilizada pelo módulo WebAssembly.

Até as etapas anteriores, o pipeline já conhece informações como:

```text
weights_raw
bias_raw

mul_blob
shift_blob
q6_blob

tensors intermediários
quantidade de slots
```

Mas ainda falta responder:

```text
quanto cada slot deve ocupar?

onde começam os pesos?

onde começa o bias?

onde ficam MUL, SHIFT e Q6?

onde começam as LayerParams?

onde começam os slots?

qual é o último endereço utilizado?

quantas páginas WebAssembly são necessárias?
```

Essas decisões são realizadas neste módulo.

A transformação geral é:

```text
tamanhos dos dados
       │
       ▼
planejamento das regiões
       │
       ▼
endereços absolutos
       │
       ▼
tamanho final da memória
       │
       ▼
quantidade de páginas WASM
```

---

# 2. Responsabilidades do arquivo

O módulo possui cinco funções principais de cálculo:

```text
tensor_numel()
        ↓
número de elementos

align_up()
        ↓
alinhamento de endereços

calculate_slot_bytes()
        ↓
tamanho físico de cada slot

calculate_parameter_layout()
        ↓
bases de WEIGHTS/BIAS/MUL/SHIFT/Q6/PARAMS

calculate_final_memory_layout()
        ↓
layout completo + MEM_END + MEM_PAGES
```

Também existem três funções destinadas exclusivamente aos relatórios:

```text
slot_memory_to_text()

parameter_layout_to_text()

final_memory_layout_to_text()
```

---

# 3. Importações

O arquivo utiliza:

```python
from extractor.tflite_utils import (
    BYTES_PER_TYPE,
    TENSOR_TYPE_MAP,
    is_constant_tensor,
    tensor_shape_list,
)
```

Cada elemento possui função específica.

---

# 4. `BYTES_PER_TYPE`

Permite transformar:

```text
tipo do tensor
```

em:

```text
quantidade de bytes por elemento
```

Exemplo:

```text
int8
 ↓
1 byte

int32
 ↓
4 bytes

float32
 ↓
4 bytes
```

Essa informação é necessária para calcular quanto um tensor intermediário ocupa.

---

# 5. `TENSOR_TYPE_MAP`

É utilizado principalmente no relatório para converter:

```text
9
```

em:

```text
int8
```

ou:

```text
2
```

em:

```text
int32
```

---

# 6. `is_constant_tensor()`

Permite excluir da análise dos slots:

```text
pesos
bias
outros tensors constantes
```

Esses dados não compartilham os buffers de ativações intermediárias.

---

# 7. `tensor_shape_list()`

Converte o shape TFLite em uma lista Python.

Exemplo:

```text
[1, 128, 128, 3]
```

Esse shape será utilizado para calcular o número total de elementos.

---

# 8. Três categorias de memória

É útil dividir o planejamento deste módulo em três categorias.

## 8.1 Parâmetros constantes

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

Essas regiões permanecem válidas durante toda a inferência.

---

## 8.2 Descrição das operações

```text
PARAMS
```

Contém o array serializado de `LayerParam`.

---

## 8.3 Memória de trabalho

```text
SLOT0
SLOT1
SLOT2
```

Essas regiões são reutilizadas por diferentes ativações durante a execução.

---

# 9. Visão geral da memória

Conceitualmente:

```text
endereço baixo
      │
      ▼

┌──────────────────────────┐
│ região inicial reservada │
├──────────────────────────┤
│ WEIGHTS                  │
├──────────────────────────┤
│ padding/alinhamento      │
├──────────────────────────┤
│ BIAS                     │
├──────────────────────────┤
│ padding/alinhamento      │
├──────────────────────────┤
│ MUL                      │
├──────────────────────────┤
│ padding/alinhamento      │
├──────────────────────────┤
│ SHIFT                    │
├──────────────────────────┤
│ padding/alinhamento      │
├──────────────────────────┤
│ Q6                       │
├──────────────────────────┤
│ padding/alinhamento      │
├──────────────────────────┤
│ PARAMS                   │
├──────────────────────────┤
│ SLOT0                    │
├──────────────────────────┤
│ SLOT1                    │
├──────────────────────────┤
│ SLOT2                    │
└──────────────────────────┘

      │
      ▼
   MEM_END
```

---

# 10. Função `tensor_numel()`

A primeira função é:

```python
def tensor_numel(
    shape,
    batch=1,
):
```

Seu objetivo é calcular:

```text
quantidade total de elementos
```

de um tensor.

---

# 11. Cálculo básico

Para:

```text
shape = [1, 128, 128, 3]
```

o cálculo é:

```text
1 × 128 × 128 × 3
```

resultando em:

```text
49.152 elementos
```

---

# 12. Implementação

A função começa com:

```python
num_elements = 1
```

e percorre cada dimensão:

```python
for dimension in shape:
```

fazendo:

```python
num_elements *= dimension
```

---

# 13. Por que começar com `1`?

Porque `1` é o elemento neutro da multiplicação.

Por exemplo:

```text
1 × 128
    ↓
128

128 × 128
    ↓
16384

16384 × 3
    ↓
49152
```

---

# 14. Conversão para `int`

Cada dimensão é convertida:

```python
dimension = int(
    dimension
)
```

Isso normaliza tipos NumPy como:

```text
np.int32
np.int64
```

para um inteiro Python comum.

---

# 15. Dimensões negativas

O código contém:

```python
if dimension < 0:
    dimension = batch
```

Essa regra preserva o comportamento da implementação original.

---

# 16. Exemplo

Para:

```text
shape = [-1, 128, 128, 3]
batch = 1
```

a função interpreta:

```text
-1 → 1
```

e calcula:

```text
1 × 128 × 128 × 3
=
49152
```

---

# 17. Significado pretendido

Normalmente uma dimensão:

```text
-1
```

pode representar uma dimensão dinâmica.

No modelo utilizado pelo projeto, a regra adotada é tratá-la como:

```text
batch
```

---

# 18. Limitação importante

Essa regra não é universal.

Por exemplo:

```text
[1, -1, 128, 3]
```

poderia representar:

```text
altura dinâmica
```

e não batch.

A implementação atual substituiria mesmo assim:

```text
-1 → batch
```

Portanto, essa regra é adequada ao comportamento esperado do modelo atual, mas não deve ser considerada uma resolução genérica de qualquer shape dinâmico.

---

# 19. Retorno

A função retorna:

```python
return num_elements
```

Ou seja:

```text
shape
  ↓
tensor_numel()
  ↓
quantidade de elementos
```

---

# 20. Relação entre elementos e bytes

Depois teremos:

```text
num_bytes =
num_elements
×
bytes_per_element
```

Por exemplo:

```text
49152 elementos
×
1 byte
=
49152 bytes
```

---

# 21. Função `align_up()`

A segunda função é:

```python
def align_up(
    value,
    alignment=16,
):
```

Seu objetivo é arredondar um endereço para cima até o próximo múltiplo do alinhamento.

---

# 22. Exemplo

Considere:

```text
value = 1001
alignment = 16
```

Os múltiplos próximos são:

```text
992
1008
1024
```

O primeiro valor válido maior ou igual a `1001` é:

```text
1008
```

Portanto:

```text
align_up(1001, 16)
=
1008
```

---

# 23. Valor já alinhado

Se:

```text
value = 2048
alignment = 16
```

temos:

```text
2048 % 16 = 0
```

Logo:

```text
align_up(2048, 16)
=
2048
```

Nenhum padding é necessário.

---

# 24. Implementação bit a bit

O código é:

```python
return (
    value
    + (alignment - 1)
) & ~(alignment - 1)
```

Essa é uma forma eficiente de alinhamento quando:

```text
alignment
```

é potência de dois.

---

# 25. Condição importante

Com:

```text
ALIGN = 16
```

temos:

```text
16 = 2⁴
```

portanto a fórmula é adequada.

Outros alinhamentos compatíveis seriam:

```text
1
2
4
8
16
32
64
...
```

---

# 26. Valores arbitrários

A mesma expressão não deve ser considerada genericamente correta para:

```text
10
12
20
```

porque não são potências de dois.

No projeto atual:

```text
ALIGN = 16
```

satisfaz a condição necessária.

---

# 27. Por que alinhar a memória?

O alinhamento cria fronteiras previsíveis entre os blocos.

Exemplo:

```text
fim dos pesos = 386651
```

Com alinhamento 16:

```text
BIAS_BASE =
386656
```

Assim existem:

```text
5 bytes
```

não utilizados entre as regiões.

---

# 28. Padding de alinhamento

Visualmente:

```text
WEIGHTS
│
│ último byte útil
▼
386650

386651 ─┐
386652  │
386653  ├── padding
386654  │
386655 ─┘

386656
▲
│
BIAS_BASE
```

O padding não contém um tensor.

Ele existe apenas para posicionamento.

---

# 29. Função `calculate_slot_bytes()`

Essa função responde:

```text
qual deve ser o tamanho de cada slot?
```

O código procura o maior tensor não constante do subgrafo e reserva para cada slot espaço suficiente para armazená-lo.

---

# 30. Estratégia utilizada

A regra é:

```text
SLOT_BYTES
=
tamanho alinhado
do maior tensor não constante
```

Como qualquer slot pode receber diferentes ativações durante a execução, todos os slots possuem o mesmo tamanho.

---

# 31. Inicialização

A função começa com:

```python
max_bytes = 0
max_tensor = None
```

Também cria:

```python
tensor_records = []
```

para relatório.

---

# 32. Varredura dos tensors

São examinados todos os tensors:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

---

# 33. Recuperação

Para cada ID:

```python
tensor = subgraph.Tensors(
    tensor_id
)
```

---

# 34. Exclusão de constantes

O código executa:

```python
if is_constant_tensor(
    model,
    subgraph,
    tensor_id,
):
    continue
```

Portanto:

```text
peso
bias
constantes auxiliares
```

não participam do cálculo do tamanho dos slots.

---

# 35. Por que excluir constantes?

Porque os slots representam:

```text
ativações intermediárias
```

e não parâmetros permanentes.

Pesos têm:

```text
WEIGHTS
```

Bias têm:

```text
BIAS
```

e não precisam caber nos slots.

---

# 36. Shape

Depois:

```python
shape = tensor_shape_list(
    tensor
)
```

Se o shape estiver vazio:

```python
if not shape:
    continue
```

---

# 37. Tipo do tensor

É obtido:

```python
tensor_type = int(
    tensor.Type()
)
```

---

# 38. Bytes por elemento

O código consulta:

```python
bytes_per_element = (
    BYTES_PER_TYPE.get(
        tensor_type
    )
)
```

---

# 39. Tipo não conhecido

Se:

```python
bytes_per_element is None
```

o tensor é ignorado.

Isso significa que o planejamento atual depende dos tipos reconhecidos por:

```text
BYTES_PER_TYPE
```

---

# 40. Número de elementos

Depois:

```python
num_elements = tensor_numel(
    shape,
    batch=batch,
)
```

---

# 41. Tamanho em bytes

Então:

```python
num_bytes = (
    num_elements
    * bytes_per_element
)
```

---

# 42. Exemplo `int8`

Shape:

```text
[1, 128, 128, 3]
```

Elementos:

```text
49152
```

Tipo:

```text
int8
```

Bytes por elemento:

```text
1
```

Resultado:

```text
49152 bytes
```

---

# 43. Exemplo `int32`

Shape:

```text
[1, 1000]
```

Elementos:

```text
1000
```

Bytes por elemento:

```text
4
```

Resultado:

```text
4000 bytes
```

---

# 44. Nome do tensor

Para fins de relatório:

```python
tensor_name = (
    tensor
    .Name()
    .decode(
        "utf-8",
        "ignore",
    )
)
```

---

# 45. Por que `decode()`?

O binding TFLite normalmente fornece o nome como:

```text
bytes
```

e o relatório precisa de:

```text
str
```

---

# 46. `"ignore"`

A opção:

```text
ignore
```

faz com que bytes inválidos para UTF-8 sejam descartados em vez de interromper a geração do relatório.

---

# 47. Nome do tipo

O código também converte:

```text
tensor_type
```

para algo legível:

```python
type_name = (
    TENSOR_TYPE_MAP.get(
        tensor_type,
        ("UNKNOWN", None),
    )[0]
)
```

---

# 48. Exemplo

```text
tensor_type = 9
```

gera:

```text
int8
```

---

# 49. Registro do tensor

Cada tensor não constante válido gera:

```python
{
    "tensor_id": ...,
    "name": ...,
    "shape": ...,
    "tensor_type": ...,
    "type_name": ...,
    "bytes_per_element": ...,
    "num_elements": ...,
    "num_bytes": ...,
}
```

---

# 50. Objetivo de `tensor_records`

Essa lista não participa diretamente do cálculo posterior.

Ela serve para explicar:

```text
quais tensors foram considerados?

quanto cada um ocupa?

qual foi o maior?
```

---

# 51. Identificação do maior tensor

O código compara:

```python
if num_bytes > max_bytes:
```

e atualiza:

```python
max_bytes = num_bytes
max_tensor = record
```

---

# 52. Uso de `>`

Observe que a condição é:

```text
>
```

e não:

```text
>=
```

Logo, se dois tensors possuírem exatamente o mesmo tamanho máximo, o primeiro encontrado permanecerá registrado como:

```text
max_tensor
```

Isso não afeta `SLOT_BYTES`.

Apenas determina qual tensor será mostrado como representante do maior tamanho.

---

# 53. Exemplo

Suponha:

```text
tensor 10 = 120000 bytes

tensor 20 = 196608 bytes

tensor 30 = 40000 bytes
```

Ao final:

```text
max_bytes = 196608
```

e:

```text
max_tensor = tensor 20
```

---

# 54. Alinhamento do slot

Depois:

```python
slot_bytes = align_up(
    max_bytes,
    alignment,
)
```

---

# 55. Exemplo já alinhado

Se:

```text
max_bytes = 196608
alignment = 16
```

e `196608` já for múltiplo de 16:

```text
SLOT_BYTES = 196608
```

---

# 56. Exemplo com padding

Se:

```text
max_bytes = 196601
```

o próximo múltiplo de 16 será:

```text
196608
```

Então:

```text
SLOT_BYTES = 196608
```

---

# 57. Por que todos os slots usam o maior tamanho?

Como `slots.py` pode reutilizar qualquer slot para diferentes tensors ao longo da inferência:

```text
SLOT0 hoje armazena tensor A

depois armazena tensor D

depois tensor H
```

é necessário garantir:

```text
cada slot comporta qualquer tensor
que possa ser associado a ele
```

A estratégia atual resolve isso de forma simples:

```text
todos os slots têm o tamanho
do maior tensor não constante
```

---

# 58. Consequência

Se:

```text
SLOT_BYTES = 196608
```

e:

```text
NUM_SLOTS = 3
```

a memória reservada exclusivamente aos slots será:

```text
3 × 196608
=
589824 bytes
```

---

# 59. Simplicidade versus otimização

Essa estratégia pode reservar mais memória do que o mínimo teórico.

Por exemplo:

```text
SLOT0 nunca recebe tensor maior que 50 KiB

SLOT1 precisa de 192 KiB

SLOT2 nunca passa de 80 KiB
```

Mesmo assim:

```text
todos = 192 KiB
```

na implementação atual.

---

# 60. Vantagem

A vantagem é a simplicidade:

```text
SLOT_BYTES único
```

e:

```text
slot_base =
base inicial
+
slot_index × SLOT_BYTES
```

podem ser utilizados.

---

# 61. Possível otimização futura

Uma versão mais sofisticada poderia calcular:

```text
tamanho máximo específico
para cada slot
```

de acordo com a alocação real.

Mas isso aumentaria a complexidade do planejamento.

A implementação atual privilegia:

```text
simplicidade
previsibilidade
```

---

# 62. Retorno de `calculate_slot_bytes()`

A função retorna:

```python
{
    "max_bytes": ...,
    "slot_bytes": ...,
    "alignment": ...,
    "batch": ...,
    "max_tensor": ...,
    "tensor_records": ...,
}
```

---

# 63. Campo `max_bytes`

É o tamanho real do maior tensor antes do alinhamento.

---

# 64. Campo `slot_bytes`

É o tamanho final reservado para cada slot após alinhamento.

---

# 65. Campo `max_tensor`

Contém todos os metadados do tensor que determinou o maior tamanho.

---

# 66. `tensor_records`

Permite auditar todos os tensors considerados no cálculo.

---

# 67. Função `calculate_parameter_layout()`

Depois de calcular os tamanhos dos parâmetros nos módulos anteriores, esta função posiciona cada bloco na memória.

Ela recebe:

```text
kernel_base_hint

alignment

weights_raw
bias_raw

mul_blob
shift_blob
q6_blob
```

---

# 68. Por que `kernel`?

No projeto, a região de pesos é chamada em alguns pontos de:

```text
KERNEL
```

e em outros de:

```text
WEIGHTS
```

Assim:

```text
kernel_base
```

é a base do bloco:

```text
weights_raw
```

---

# 69. Layout produzido

A sequência é:

```text
KERNEL/WEIGHTS
      ↓
BIAS
      ↓
MUL
      ↓
SHIFT
      ↓
Q6
      ↓
PARAMS
```

Cada nova base é alinhada.

---

# 70. Base dos pesos

Primeiro:

```python
kernel_base = align_up(
    kernel_base_hint,
    alignment,
)
```

---

# 71. Configuração atual

Com:

```text
KERNEL_BASE_HINT = 2048
ALIGN = 16
```

como `2048` já é múltiplo de 16:

```text
kernel_base = 2048
```

---

# 72. Tamanho dos pesos

```python
kernel_bytes = len(
    weights_raw
)
```

Portanto não existe um tamanho manual hardcoded.

Ele vem diretamente do blob extraído.

---

# 73. Intervalo dos pesos

A região lógica é:

```text
[kernel_base,
 kernel_base + kernel_bytes)
```

A notação:

```text
[a, b)
```

significa:

```text
inclui a
não inclui b
```

---

# 74. Exemplo

Se:

```text
kernel_base = 2048
kernel_bytes = 384608
```

então:

```text
WEIGHTS =
[2048, 386656)
```

O último byte utilizado é:

```text
386655
```

---

# 75. Base do bias

O próximo bloco começa em:

```python
bias_base = align_up(
    kernel_base + kernel_bytes,
    alignment,
)
```

---

# 76. Exemplo sem padding

Se:

```text
kernel_base + kernel_bytes
=
386656
```

e esse valor já está alinhado:

```text
bias_base = 386656
```

---

# 77. Exemplo com padding

Se o fim dos pesos fosse:

```text
386651
```

teríamos:

```text
bias_base = 386656
```

Criando cinco bytes de padding.

---

# 78. Tamanho do bias

```python
bias_bytes = len(
    bias_raw
)
```

---

# 79. Base dos multipliers

Depois:

```python
mul_base = align_up(
    bias_base + bias_bytes,
    alignment,
)
```

---

# 80. Tamanho de MUL

```python
mul_bytes = len(
    mul_blob
)
```

---

# 81. Base de SHIFT

```python
shift_base = align_up(
    mul_base + mul_bytes,
    alignment,
)
```

---

# 82. Base de Q6

```python
q6_base = align_up(
    shift_base + shift_bytes,
    alignment,
)
```

---

# 83. `params_base`

Depois de Q6:

```python
params_base = align_up(
    q6_base + q6_bytes,
    alignment,
)
```

Esse endereço representa:

```text
onde a futura região PARAMS poderá começar
```

---

# 84. Importante: `PARAMS` ainda não foi colocado

Nesta função, ainda não temos:

```text
params_blob
```

Portanto:

```text
params_base
```

é apenas a próxima área livre alinhada depois de Q6.

O tamanho real das `LayerParams` será conhecido posteriormente.

---

# 85. Por isso esta função para em `params_base`

O layout parcial é:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6

PARAMS_BASE
    ↓
próximo endereço disponível
```

Ainda faltam:

```text
PARAMS bytes
SLOT0
SLOT1
SLOT2
```

---

# 86. Retorno do layout parcial

A função retorna:

```python
{
    "kernel_base": ...,
    "kernel_bytes": ...,

    "bias_base": ...,
    "bias_bytes": ...,

    "mul_base": ...,
    "mul_bytes": ...,

    "shift_base": ...,
    "shift_bytes": ...,

    "q6_base": ...,
    "q6_bytes": ...,

    "params_base": ...,

    "alignment": ...,
    "kernel_base_hint": ...,
}
```

---

# 87. Bases versus tamanhos

Cada região possui conceitualmente:

```text
BASE
+
BYTES
=
END
```

Por exemplo:

```text
BIAS_BASE
+
BIAS_BYTES
=
fim do bias
```

---

# 88. Como evitar sobreposição

A função utiliza sempre:

```text
próxima_base =
align_up(
    base_anterior + tamanho_anterior
)
```

Logo a próxima região começa depois do final da anterior.

---

# 89. Exemplo encadeado

Considere:

```text
kernel_base = 2048
kernel_bytes = 1000
```

Fim:

```text
3048
```

Com alinhamento 16:

```text
bias_base = 3056
```

Suponha:

```text
bias_bytes = 100
```

Fim:

```text
3156
```

Próximo alinhamento:

```text
mul_base = 3168
```

E assim sucessivamente.

---

# 90. O padding pertence à região anterior?

Não.

Conceitualmente:

```text
dados da região
       ↓
fim lógico
       ↓
padding
       ↓
próxima base
```

O padding é espaço não utilizado entre regiões.

---

# 91. `slot_memory_to_text()`

Essa função gera o relatório da primeira parte do planejamento.

Ela não modifica nenhuma informação.

---

# 92. Primeira seção

O relatório lista:

```text
TENSORES NÃO CONSTANTES
```

mostrando, para cada tensor:

```text
tensor ID
nome
shape
dtype
bytes por elemento
número de elementos
bytes totais
```

---

# 93. Exemplo

```text
tensor=  12
name=activation_4
shape=[1, 64, 64, 24]
dtype=int8
bpe=1
elements=98304
bytes=98304
```

---

# 94. Seção `MAIOR TENSOR`

Depois é exibido o tensor que determinou:

```text
max_bytes
```

---

# 95. Informação registrada

O relatório mostra:

```text
tensor_id

name

shape

dtype

bytes por elemento

número de elementos

bytes sem alinhamento
```

---

# 96. Cálculo final do slot

A última seção mostra:

```text
max_bytes
alignment
SLOT_BYTES
```

Portanto é possível verificar:

```text
tamanho real
      ↓
alinhamento
      ↓
tamanho reservado
```

---

# 97. `parameter_layout_to_text()`

Essa função produz o relatório do layout dos parâmetros constantes.

Mostra:

```text
alignment
kernel_base_hint

KERNEL_BASE
KERNEL_BYTES

BIAS_BASE
BIAS_BYTES

MUL_BASE
MUL_BYTES

SHIFT_BASE
SHIFT_BYTES

Q6_BASE
Q6_BYTES

PARAMS_BASE
```

---

# 98. Utilidade

Esse relatório permite verificar diretamente:

```text
onde começa cada região?

quanto ocupa?

qual será a próxima área livre?
```

antes de construir os slots.

---

# 99. Ponto intermediário do pipeline

Até esse ponto temos:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
```

com endereços absolutos.

Mas ainda não temos o layout completo.

---

# 100. Constante `WASM_PAGE_BYTES`

O arquivo define:

```python
WASM_PAGE_BYTES = 65536
```

Uma página de memória WebAssembly possui:

```text
65536 bytes
```

ou:

```text
64 KiB
```

---

# 101. Diferença entre KB e KiB

Tecnicamente:

```text
64 KiB
=
64 × 1024
=
65536 bytes
```

Essa é a unidade utilizada pelas páginas WebAssembly.

---

# 102. Memória WebAssembly

Quando o WAT declara:

```wat
(memory (export "memory") N)
```

o número:

```text
N
```

representa:

```text
quantidade inicial de páginas
```

e não quantidade de bytes.

---

# 103. Exemplo

```wat
(memory (export "memory") 17)
```

significa:

```text
17 × 65536 bytes
```

resultando em:

```text
1.114.112 bytes
```

de memória linear inicialmente disponível.

---

# 104. Função `mem_pages_for()`

A função:

```python
def mem_pages_for(
    end_addr,
):
```

calcula o número mínimo de páginas necessárias para cobrir um determinado endereço final.

---

# 105. Fórmula

```python
return (
    end_addr
    + WASM_PAGE_BYTES
    - 1
) // WASM_PAGE_BYTES
```

É uma divisão inteira arredondada para cima.

---

# 106. Forma matemática

Podemos representar como:

```text
MEM_PAGES =
ceil(
    MEM_END / 65536
)
```

---

# 107. Exemplo exato

Se:

```text
MEM_END = 65536
```

então:

```text
MEM_PAGES = 1
```

---

# 108. Um byte além

Se:

```text
MEM_END = 65537
```

uma única página não é suficiente.

Então:

```text
MEM_PAGES = 2
```

---

# 109. Exemplo maior

Se:

```text
MEM_END = 1.096.000
```

teríamos aproximadamente:

```text
1.096.000 / 65.536
≈ 16,72
```

portanto:

```text
MEM_PAGES = 17
```

---

# 110. Por que arredondar para cima?

O runtime não pode reservar:

```text
16,72 páginas
```

Somente páginas inteiras.

Logo:

```text
16,01 → 17
16,99 → 17
17,00 → 17
17,01 → 18
```

---

# 111. Função `calculate_final_memory_layout()`

Esta função fecha definitivamente o planejamento.

Ela recebe:

```text
parameter_layout

params_blob

slot_bases

slot_bytes
```

---

# 112. Por que ela é posterior?

Agora já conhecemos:

```text
params_blob
```

e:

```text
slot_bases
```

que ainda não existiam em:

```python
calculate_parameter_layout()
```

---

# 113. Responsabilidade

Ela responde:

```text
qual é o intervalo de cada região?

qual é o último endereço?

quantas páginas WASM preciso?

quanto espaço sobra na última página?
```

---

# 114. Lista `regions`

A função começa com:

```python
regions = []
```

Cada bloco da memória será representado por um dicionário.

---

# 115. Região WEIGHTS

É adicionada:

```python
{
    "name": "WEIGHTS",
    "base": kernel_base,
    "bytes": kernel_bytes,
}
```

---

# 116. Região BIAS

Depois:

```text
BIAS
```

com:

```text
bias_base
bias_bytes
```

---

# 117. Região MUL

Em seguida:

```text
MUL
```

com sua base e tamanho.

---

# 118. Região SHIFT

Da mesma maneira:

```text
SHIFT
```

---

# 119. Região Q6

Depois:

```text
Q6
```

---

# 120. Região PARAMS

Agora finalmente conhecemos:

```python
len(
    params_blob
)
```

Assim podemos registrar:

```python
{
    "name": "PARAMS",
    "base": params_base,
    "bytes": len(params_blob),
}
```

---

# 121. Diferença para o layout parcial

Antes sabíamos somente:

```text
PARAMS_BASE
```

Agora sabemos:

```text
PARAMS_BASE
+
PARAMS_BYTES
```

e portanto também:

```text
PARAMS_END
```

---

# 122. Inclusão dos slots

Depois:

```python
for slot_index, slot_base in enumerate(
    slot_bases
):
```

cada slot é adicionado.

---

# 123. Exemplo

Se:

```python
slot_bases = [
    507248,
    703856,
    900464,
]
```

e:

```text
slot_bytes = 196608
```

são criadas:

```text
SLOT0

base = 507248
bytes = 196608
```

```text
SLOT1

base = 703856
bytes = 196608
```

```text
SLOT2

base = 900464
bytes = 196608
```

Os números são apenas um exemplo do formato produzido.

---

# 124. Cálculo de `end`

Depois cada região recebe:

```python
region["end"] = (
    region["base"]
    + region["bytes"]
)
```

---

# 125. Convenção de `end`

Esse valor representa:

```text
primeiro endereço depois da região
```

e não o último byte válido.

---

# 126. Exemplo

Se:

```text
base = 100
bytes = 20
```

a região ocupa:

```text
100 ... 119
```

e:

```text
end = 120
```

---

# 127. Intervalo semiaberto

Portanto:

```text
[base, end)
```

é a representação correta.

---

# 128. Por que essa convenção é útil?

Porque:

```text
bytes =
end - base
```

diretamente.

Também permite colocar uma próxima região exatamente em:

```text
end
```

quando nenhum alinhamento adicional é necessário.

---

# 129. Cálculo de `mem_end`

O código faz:

```python
mem_end = max(
    region["end"]
    for region in regions
)
```

---

# 130. Por que usar `max()`?

Em vez de assumir simplesmente:

```text
último slot = última região
```

o código calcula explicitamente qual região termina no maior endereço.

Isso torna o fechamento mais robusto à ordem da lista.

---

# 131. Exemplo

Se os fins forem:

```text
WEIGHTS → 386656

BIAS → 414832

PARAMS → 507248

SLOT0 → 703856

SLOT1 → 900464

SLOT2 → 1097072
```

então:

```text
MEM_END = 1097072
```

---

# 132. Significado de `MEM_END`

`MEM_END` representa:

```text
o primeiro endereço após
o último byte utilizado
```

---

# 133. Não confundir com índice do último byte

Se:

```text
MEM_END = 1097072
```

o último byte efetivamente utilizado é:

```text
1097071
```

---

# 134. Cálculo de `MEM_PAGES`

Depois:

```python
mem_pages = mem_pages_for(
    mem_end
)
```

---

# 135. Memória efetivamente reservada

O total de bytes reservados será:

```python
allocated_memory_bytes = (
    mem_pages
    * WASM_PAGE_BYTES
)
```

---

# 136. Exemplo

Se:

```text
MEM_PAGES = 17
```

temos:

```text
17 × 65536
=
1114112 bytes
```

---

# 137. Espaço não utilizado

O código calcula:

```python
unused_memory_bytes = (
    allocated_memory_bytes
    - mem_end
)
```

---

# 138. Significado

É o espaço restante entre:

```text
MEM_END
```

e:

```text
fim da última página reservada
```

---

# 139. Exemplo

Se:

```text
mem_end = 1097072

allocated_memory_bytes = 1114112
```

então:

```text
unused =
17040 bytes
```

---

# 140. Isso é desperdício?

É um efeito natural da granularidade de memória WebAssembly.

A memória não pode ser reservada byte a byte.

Ela é reservada em páginas de:

```text
64 KiB
```

Logo sempre pode existir uma fração não utilizada da última página.

---

# 141. Retorno final

A função retorna:

```python
{
    "regions": ...,

    "mem_end": ...,

    "mem_pages": ...,

    "wasm_page_bytes": ...,

    "allocated_memory_bytes": ...,

    "unused_memory_bytes": ...,

    "slot_bases": ...,

    "slot_bytes": ...,
}
```

---

# 142. `regions`

É particularmente útil para:

```text
relatório

validação

visualização futura
```

porque contém todas as regiões em formato uniforme.

---

# 143. Exemplo de região

```python
{
    "name": "MUL",
    "base": 414832,
    "bytes": 28176,
    "end": 443008,
}
```

---

# 144. Representação uniforme

Isso permite tratar:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOT0
SLOT1
SLOT2
```

da mesma maneira.

---

# 145. `final_memory_layout_to_text()`

Essa função produz o relatório final.

Ela começa com uma tabela:

```text
REGIAO              BASE       BYTES         END
------------------------------------------------
...
```

---

# 146. Exemplo conceitual

```text
REGIAO              BASE       BYTES         END
------------------------------------------------
WEIGHTS             2048      384608      386656
BIAS              386656       28176      414832
MUL               414832       28176      443008
SHIFT             443008       28176      471184
Q6                471184       28176      499360
PARAMS            499360        7888      507248
SLOT0             507248      196608      703856
SLOT1             703856      196608      900464
SLOT2             900464      196608     1097072
```

Os valores acima servem apenas para ilustrar o formato.

---

# 147. Por que essa tabela é tão útil?

Com uma única visualização é possível verificar:

```text
ordem das regiões

tamanho de cada bloco

possíveis lacunas

último endereço

posição dos slots
```

---

# 148. Seção `RESUMO`

Depois são exibidos:

```text
MEM_END

WASM_PAGE_BYTES

MEM_PAGES

memória reservada

espaço restante

SLOT_BYTES

SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
```

---

# 149. Relação com o template WAT

O resultado:

```python
memory_layout[
    "mem_pages"
]
```

é utilizado para preencher:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

---

# 150. Exemplo

Se:

```python
final_memory[
    "mem_pages"
] = 17
```

o WAT gerado conterá:

```wat
(memory
    (export "memory")
    17
)
```

---

# 151. Bases dos slots

Os valores calculados anteriormente também aparecem no WAT:

```wat
(global $SLOT0_BASE
    i32
    (i32.const ...)
)

(global $SLOT1_BASE
    i32
    (i32.const ...)
)

(global $SLOT2_BASE
    i32
    (i32.const ...)
)
```

---

# 152. Relação com `weights.py`

`weights.py` produz:

```text
weights_raw
bias_raw
```

`memory.py` transforma os tamanhos desses blobs em:

```text
kernel_base
bias_base
```

---

# 153. Relação com `quantization.py`

`quantization.py` produz:

```text
mul_blob
shift_blob
q6_blob
```

`memory.py` transforma seus tamanhos em:

```text
mul_base
shift_base
q6_base
```

---

# 154. Relação com `params_blob.py`

`params_blob.py` produz:

```text
params_blob
```

e esta etapa final registra:

```text
PARAMS_BASE
PARAMS_BYTES
PARAMS_END
```

---

# 155. Relação com `slots.py`

`slots.py` decidiu:

```text
qual camada usa SLOT0, SLOT1 ou SLOT2
```

Mas não sabia:

```text
onde esses slots ficam fisicamente
```

Essa decisão física acontece no planejamento de memória utilizado pelas etapas posteriores.

---

# 156. Relação com `layer_params.py`

Uma `LayerParam` precisa de ponteiros como:

```text
wptr
bias_ptr
mul_ptr
shift_ptr
q6_ptr

in_ptr
out_ptr
```

Esses ponteiros dependem das bases calculadas neste módulo.

---

# 157. Exemplo de peso

`weights.py`:

```text
tensor 30
offset = 5000
```

`memory.py`:

```text
WEIGHTS_BASE = 2048
```

Resultado posterior:

```text
wptr =
2048 + 5000
=
7048
```

---

# 158. Exemplo de multiplier

`quantization.py`:

```text
mul_offset = 128
```

`memory.py`:

```text
MUL_BASE = 414832
```

Resultado:

```text
mul_ptr =
414832 + 128
=
414960
```

---

# 159. Exemplo de ativação

`tensor_mapping.py`:

```text
tensor → SLOT1
```

Planejamento físico:

```text
SLOT1_BASE = 703856
```

Resultado:

```text
in_ptr = 703856
```

---

# 160. Portanto este módulo é a ponte para endereços reais

Antes:

```text
offset relativo
slot lógico
```

Depois:

```text
base absoluta
```

E finalmente:

```text
ponteiro utilizado pelo WASM
```

---

# 161. `kernel_base_hint` versus `kernel_base`

Essa distinção é importante.

O primeiro:

```text
KERNEL_BASE_HINT
```

é uma configuração.

O segundo:

```text
kernel_base
```

é o endereço efetivo depois do alinhamento.

---

# 162. Exemplo

Se:

```text
KERNEL_BASE_HINT = 2050
ALIGN = 16
```

então:

```text
kernel_base =
2064
```

Portanto:

```text
hint ≠ necessariamente base
```

---

# 163. `params_base` versus `PARAMS_END`

Outra distinção importante:

```text
params_base
```

indica o início.

Já:

```text
params_base
+
len(params_blob)
```

indica o final.

---

# 164. Fases do planejamento

O projeto realiza o planejamento em etapas porque alguns tamanhos só existem depois de outras transformações.

### Fase 1

```text
weights/bias/quantização
        ↓
calculate_parameter_layout()
```

Produz:

```text
PARAMS_BASE
```

---

### Fase 2

`LayerParam` é construída.

Então:

```text
params_blob
```

passa a ter tamanho conhecido.

---

### Fase 3

São conhecidas também:

```text
slot_bases
```

Então:

```text
calculate_final_memory_layout()
```

fecha a memória inteira.

---

# 165. Por que não calcular tudo em uma única função?

Porque isso criaria dependências circulares.

Por exemplo:

```text
slot_bases
```

dependem da posição final de `PARAMS`.

Mas:

```text
params_blob
```

só existe depois que as `LayerParams` foram construídas.

Logo faz sentido ter:

```text
layout parcial
      ↓
construção das LayerParams
      ↓
layout final
```

---

# 166. Relação temporal

```text
weights.py
quantization.py
      │
      ▼
calculate_parameter_layout()
      │
      ▼
PARAMS_BASE
      │
      ▼
layer_params.py
      │
      ▼
params_blob.py
      │
      ▼
PARAMS_BYTES
      │
      ▼
calculate_final_memory_layout()
```

---

# 167. Um detalhe importante sobre `slot_bases`

A função:

```python
calculate_final_memory_layout()
```

não calcula os `slot_bases`.

Ela os recebe já calculados.

Seu papel é:

```text
incorporá-los ao layout final
```

e não decidir novamente suas posições.

---

# 168. Separação de responsabilidade

Assim:

```text
cálculo das bases dos slots
```

acontece na fase em que o layout das `LayerParams` é definido.

Já:

```text
memory.py
```

fecha e valida conceitualmente o mapa global utilizando essas bases.

---

# 169. O arquivo não gera WAT

A docstring deixa isso explícito:

```text
Não gera WAT.
Apenas fecha o planejamento de memória.
```

Essa separação é importante.

---

# 170. Arquitetura correta

```text
memory.py
   ↓
dados estruturados

wat_generator.py
   ↓
transforma esses dados
em código WAT
```

---

# 171. Abordagem que foi evitada

Não fazemos aqui:

```python
wat_lines.append(
    f"(memory ... {mem_pages})"
)
```

Isso misturaria:

```text
engenharia de memória
```

com:

```text
geração de código
```

---

# 172. Benefício

`memory.py` pode ser testado e analisado independentemente do WAT.

Por exemplo:

```text
qual é MEM_END?

há memória suficiente?

quanto cada slot ocupa?

quantas páginas seriam necessárias?
```

podem ser estudados sem gerar nenhum módulo WebAssembly.

---

# 173. Invariante de não sobreposição

O objetivo estrutural do layout é que duas regiões distintas não ocupem os mesmos bytes.

Para duas regiões consecutivas:

```text
A
B
```

deveríamos ter:

```text
A.end <= B.base
```

---

# 174. Nas regiões calculadas sequencialmente

Isso é garantido pela construção:

```text
next_base =
align_up(
    previous_base
    +
    previous_bytes
)
```

---

# 175. Para `PARAMS` e slots

A correção depende das bases calculadas na etapa de `layer_params.py`.

`calculate_final_memory_layout()` atualmente registra e resume essas regiões, mas não executa uma validação explícita de sobreposição entre todos os pares.

---

# 176. Possível validação futura

Poderia ser implementada:

```text
ordenar regiões por base

para cada par consecutivo:

previous.end <= current.base
```

Caso contrário:

```text
RuntimeError
```

---

# 177. Por que seria útil?

Porque um erro em:

```text
params_bytes
slot_bases
slot_bytes
```

poderia produzir sobreposição sem que:

```text
MEM_END
```

sozinho revelasse o problema.

---

# 178. Estado atual

No fluxo atual, as bases são produzidas sequencialmente e o WAT compilou corretamente, mas uma validação explícita seria uma boa melhoria futura para robustez.

---

# 179. Outro invariante

Toda região deve satisfazer:

```text
bytes >= 0
```

e:

```text
end =
base + bytes
```

---

# 180. Região vazia

Caso algum blob tenha:

```text
0 bytes
```

teríamos:

```text
base == end
```

Isso representa uma região vazia.

---

# 181. Quantidade mínima de páginas

`mem_pages_for()` retorna exatamente a quantidade mínima necessária para cobrir:

```text
[0, MEM_END)
```

---

# 182. Se MEM_END estiver alinhado à página

Se:

```text
MEM_END = N × 65536
```

então:

```text
MEM_PAGES = N
```

Não é necessária uma página extra.

---

# 183. Se faltar apenas um byte

Se:

```text
MEM_END =
N × 65536 + 1
```

então:

```text
MEM_PAGES = N + 1
```

---

# 184. Relação com o ESP32

Embora o cálculo seja feito segundo a memória linear WebAssembly, o número final de páginas também influencia diretamente o consumo de memória necessário ao carregar o módulo no ambiente embarcado.

Quanto maior:

```text
MEM_PAGES
```

maior é a região linear que o runtime precisa disponibilizar.

---

# 185. O maior consumidor pode ser o conjunto de slots

Uma característica importante do layout é que:

```text
weights
```

não necessariamente são a maior categoria de memória.

Como existem vários slots:

```text
NUM_SLOTS × SLOT_BYTES
```

pode representar uma parcela significativa.

---

# 186. Exemplo

Se:

```text
SLOT_BYTES = 196608
NUM_SLOTS = 3
```

temos:

```text
589824 bytes
```

somente para ativações.

Isso equivale a aproximadamente:

```text
576 KiB
```

---

# 187. Vantagem da reutilização

Sem slots reutilizáveis, seria necessário potencialmente reservar espaço para muitas ativações simultaneamente.

O planejamento reduz isso para um número fixo de grandes regiões.

---

# 188. Relação com liveness

`memory.py` não calcula liveness.

Isso já foi feito conceitualmente por:

```text
graph.py
slots.py
```

Aqui assumimos que:

```text
3 slots
```

são suficientes para a estratégia determinada anteriormente.

---

# 189. Separação novamente

```text
slots.py
    ↓
quando uma região pode ser reutilizada?
```

```text
memory.py
    ↓
quanto essa região ocupa e onde começa?
```

---

# 190. `SLOT_BYTES` não é tamanho de um tensor específico

Mesmo que seja determinado pelo maior tensor:

```text
SLOT_BYTES
```

é uma propriedade da região física.

Ao longo da execução ela recebe diversos tensors menores ou do mesmo tamanho.

---

# 191. Exemplo

```text
SLOT1 = 196608 bytes
```

pode armazenar em momentos diferentes:

```text
tensor A = 49152 bytes

tensor B = 98304 bytes

tensor C = 196608 bytes
```

Todos cabem na mesma região.

---

# 192. Espaço residual dentro de um slot

Se um tensor ocupa:

```text
49152 bytes
```

dentro de um slot de:

```text
196608 bytes
```

os bytes restantes não são utilizados por aquele tensor.

Isso é esperado.

---

# 193. O slot não é particionado dinamicamente

A implementação atual não tenta colocar simultaneamente:

```text
tensor A
+
tensor B
```

dentro de partes diferentes do mesmo slot.

Cada slot é tratado como um buffer único reutilizável.

---

# 194. Consequência para simplicidade

Isso facilita muito o runtime.

Uma operação recebe:

```text
in_ptr = SLOTn_BASE
```

sem precisar calcular offsets internos variáveis de ativação.

---

# 195. Tamanho dos blobs de quantização

Como:

```text
MUL
SHIFT
Q6
```

são arrays de `int32`, seus tamanhos normalmente são múltiplos de:

```text
4
```

Mas mesmo assim a próxima região é alinhada para:

```text
16 bytes
```

pela política global.

---

# 196. Dois alinhamentos diferentes conceitualmente

Temos:

```text
estrutura interna do blob
    ↓
int32 = 4 bytes
```

e:

```text
início das grandes regiões
    ↓
ALIGN = 16 bytes
```

Não são a mesma coisa.

---

# 197. Exemplo

Um `mul_blob` pode possuir:

```text
28.180 bytes
```

que não é múltiplo de 16.

Então:

```text
SHIFT_BASE
```

será arredondado para o próximo múltiplo de 16.

---

# 198. Por que não alinhar cada multiplier a 16 bytes?

Isso seria extremamente desperdicioso.

Cada valor ocupa naturalmente:

```text
4 bytes
```

A região como um todo é alinhada; os elementos permanecem contíguos dentro dela.

---

# 199. Mesma lógica para pesos

Pesos `int8` continuam:

```text
1 byte por valor
```

contíguos no blob.

O alinhamento de 16 é aplicado à:

```text
base da região
```

e não a cada peso.

---

# 200. Hierarquia de endereçamento

Podemos visualizar:

```text
memória WASM
   │
   ├── região
   │      │
   │      └── offset interno
   │
   ▼
endereço
```

Exemplo:

```text
MUL_BASE
    +
mul_offset
    +
channel × 4
```

---

# 201. Três níveis

Para um multiplier:

```text
nível 1:
MUL_BASE

nível 2:
mul_offset da operação

nível 3:
channel × 4
```

Então:

```text
endereço =
MUL_BASE
+
mul_offset
+
channel × 4
```

---

# 202. Para pesos

Da mesma forma:

```text
WEIGHTS_BASE
+
weight_tensor_off
+
offset interno do kernel
```

---

# 203. Para slots

Já as ativações normalmente começam diretamente em:

```text
SLOTn_BASE
```

e o kernel calcula internamente os offsets de:

```text
pixel
canal
linha
coluna
```

---

# 204. Resumo das funções de cálculo

| Função                            | Resultado                         |
| --------------------------------- | --------------------------------- |
| `tensor_numel()`                  | Número de elementos do tensor     |
| `align_up()`                      | Próximo endereço alinhado         |
| `calculate_slot_bytes()`          | Tamanho de cada slot              |
| `calculate_parameter_layout()`    | Bases dos parâmetros constantes   |
| `mem_pages_for()`                 | Quantidade mínima de páginas WASM |
| `calculate_final_memory_layout()` | Mapa completo da memória          |

---

# 205. Resumo das funções de relatório

| Função                          | Relatório                            |
| ------------------------------- | ------------------------------------ |
| `slot_memory_to_text()`         | Tensors e cálculo do tamanho do slot |
| `parameter_layout_to_text()`    | Bases e tamanhos dos parâmetros      |
| `final_memory_layout_to_text()` | Layout completo e páginas WASM       |

---

# 206. Dados que entram neste módulo

Vindos de `config.py`:

```text
BATCH
ALIGN
KERNEL_BASE_HINT
```

Vindos de `weights.py`:

```text
weights_raw
bias_raw
```

Vindos de `quantization.py`:

```text
mul_blob
shift_blob
q6_blob
```

Mais tarde:

```text
params_blob
slot_bases
```

---

# 207. Dados que saem

Entre outros:

```text
SLOT_BYTES

WEIGHTS_BASE
BIAS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE
PARAMS_BASE

MEM_END
MEM_PAGES
```

---

# 208. Configuração versus cálculo

É importante reforçar:

```text
ALIGN = 16
```

é uma política de configuração.

Já:

```text
BIAS_BASE
```

é um resultado calculado.

---

# 209. Da mesma maneira

```text
KERNEL_BASE_HINT = 2048
```

é configuração.

Mas:

```text
kernel_base
```

é resultado do alinhamento.

---

# 210. E

```text
NUM_SLOTS = 3
```

é configuração.

Enquanto:

```text
SLOT_BYTES
```

é derivado do modelo.

---

# 211. Nenhum endereço dependente do modelo deve ser hardcoded

O princípio arquitetural é:

```text
modelo muda
   ↓
tamanhos podem mudar
   ↓
bases são recalculadas
   ↓
WAT recebe novos valores
```

Não:

```text
modelo muda
   ↓
editar endereços manualmente
```

---

# 212. Relação com o template WAT

O WAT passa a ser apenas consumidor desses resultados.

Exemplo:

```wat
(global $WEIGHTS_BASE
    i32
    (i32.const @@WEIGHTS_BASE@@)
)
```

O extrator substitui:

```text
@@WEIGHTS_BASE@@
```

pelo valor produzido pelo planejamento.

---

# 213. Mesmo princípio para a memória

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

O template não precisa saber previamente quantas páginas o modelo requer.

---

# 214. Benefício para novos modelos

Ao trocar:

```text
model_int8_esp32.tflite
```

por outro modelo compatível, podem mudar:

```text
quantidade de pesos
bias
multipliers
shifts
Q6
LayerParams
tamanho máximo das ativações
```

e, consequentemente:

```text
todas as bases
MEM_END
MEM_PAGES
```

O pipeline recalcula esses valores.

---

# 215. Responsabilidade central

Podemos resumir `memory.py` com a pergunta:

```text
como transformar tamanhos
e offsets lógicos

em um mapa físico coerente
da memória linear WebAssembly?
```

---

# 216. Fluxo completo do módulo

```text
                MODEL + BLOBS
                     │
                     ▼
          calculate_slot_bytes()
                     │
                     ▼
                SLOT_BYTES


weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
      │
      ▼
calculate_parameter_layout()
      │
      ├── WEIGHTS_BASE
      ├── BIAS_BASE
      ├── MUL_BASE
      ├── SHIFT_BASE
      ├── Q6_BASE
      └── PARAMS_BASE
              │
              ▼
       LayerParams geradas
              │
              ▼
         params_blob
              │
              ▼
      bases dos slots
              │
              ▼
calculate_final_memory_layout()
              │
              ├── regions
              ├── MEM_END
              ├── MEM_PAGES
              └── memória reservada
```

---

# 217. Papel no pipeline completo

```text
┌─────────────────────────────┐
│         weights.py          │
│                             │
│ weights_raw                 │
│ bias_raw                    │
└──────────────┬──────────────┘
               │
               │
┌──────────────▼──────────────┐
│      quantization.py        │
│                             │
│ mul_blob                    │
│ shift_blob                  │
│ q6_blob                     │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         memory.py           │
│                             │
│ bases                       │
│ tamanhos                    │
│ SLOT_BYTES                  │
│ PARAMS_BASE                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      layer_params.py        │
│                             │
│ LayerParams                 │
│ slot_bases                  │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│       params_blob.py        │
│                             │
│ params_blob                 │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│         memory.py           │
│                             │
│ fechamento final            │
│ MEM_END                     │
│ MEM_PAGES                   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      wat_generator.py       │
│                             │
│ injeta os valores no WAT    │
└─────────────────────────────┘
```

---

# 218. Síntese

`memory.py` transforma as estruturas produzidas pelas etapas anteriores em um mapa físico da memória linear WebAssembly.

A primeira responsabilidade é encontrar o maior tensor não constante:

```text
maior tensor
     ↓
align_up()
     ↓
SLOT_BYTES
```

Isso garante que qualquer ativação intermediária compatível com o modelo possa ser armazenada em qualquer um dos slots reutilizáveis.

A segunda responsabilidade é organizar os parâmetros constantes:

```text
KERNEL/WEIGHTS
      ↓
BIAS
      ↓
MUL
      ↓
SHIFT
      ↓
Q6
      ↓
PARAMS_BASE
```

Cada base é calculada a partir do final da região anterior e alinhada segundo:

```text
ALIGN = 16
```

A terceira responsabilidade ocorre depois que as `LayerParams` e os slots já foram posicionados. Nesse momento, todas as regiões são reunidas:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
SLOT0
SLOT1
SLOT2
```

e cada uma recebe:

```text
base
bytes
end
```

O maior `end` determina:

```text
MEM_END
```

e então:

```text
MEM_PAGES =
ceil(
    MEM_END / 65536
)
```

determina a quantidade mínima de páginas de 64 KiB que o módulo WebAssembly precisa declarar.

Assim, este módulo é responsável por transformar:

```text
tamanhos abstratos
offsets
e slots lógicos
```

em:

```text
endereços absolutos
e capacidade concreta
da memória linear WASM
```

sem gerar código WebAssembly diretamente.

Essa separação permite que `wat_generator.py` funcione apenas como etapa de materialização: ele recebe um layout já calculado e validado conceitualmente e simplesmente injeta esses valores no template.
