[English](13-geracao-wat.md) | [Português (Brasil)](13-geracao-wat.pt-BR.md)

> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.pt-BR.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.pt-BR.md). O corpo original foi mantido.

# 13 — Geração do módulo WAT (`wat_generator.py`)

## 1. Objetivo do módulo

O arquivo `extractor/wat_generator.py` é responsável pela última etapa do pipeline de extração: transformar um template WAT estático em um arquivo WAT completamente configurado para o modelo processado.

Até este momento, todas as informações dependentes do modelo já foram calculadas:

```text
pesos
bias
multipliers
shifts
Q6

LayerParams

layout de memória

bases dos slots

número de camadas

tamanho da memória

endereço da saída
```

O gerador não precisa mais interpretar o TFLite.

Ele apenas realiza:

```text
template WAT
    +
valores calculados
    +
blobs binários
        │
        ▼
WAT final
```

O fluxo geral é:

```text
model.tflite
     │
     ▼
extração e cálculos
     │
     ├── weights_raw
     ├── bias_raw
     ├── mul_blob
     ├── shift_blob
     ├── q6_blob
     ├── params_blob
     │
     ├── endereços
     ├── slots
     └── MEM_PAGES
             │
             ▼
       wat_generator.py
             │
             ▼
       generated/model.wat
```

---

# 2. Responsabilidade arquitetural

A principal decisão arquitetural deste módulo é que ele **não calcula parâmetros do modelo**.

Ele não decide:

```text
quanto ocupa um slot

onde começam os pesos

qual é o multiplier de uma convolução

como calcular SAME padding

qual tensor vai para qual slot

qual é o zero point

como montar uma LayerParam
```

Todas essas decisões já foram tomadas anteriormente.

O gerador responde apenas:

```text
como inserir os resultados já calculados
no template WAT?
```

Isso cria uma separação clara entre:

```text
CÁLCULO
   ↓
extractor/*

MATERIALIZAÇÃO
   ↓
wat_generator.py
```

---

# 3. Importações

O arquivo começa com:

```python
from pathlib import Path
import re
```

São necessárias apenas duas funcionalidades externas à biblioteca padrão.

---

# 4. `Path`

`Path` é utilizado para:

```text
ler o template

criar o diretório de saída

escrever o WAT gerado

obter o tamanho final do arquivo
```

Assim os caminhos permanecem representados como objetos `Path`.

---

# 5. `re`

O módulo `re` é utilizado para localizar placeholders que permaneceram no WAT depois das substituições.

Isso funciona como uma validação final do template.

---

# 6. `PLACEHOLDER_PATTERN`

A expressão regular é:

```python
PLACEHOLDER_PATTERN = re.compile(
    r"@@[A-Z0-9_]+@@"
)
```

Ela reconhece placeholders no formato:

```text
@@NOME@@
```

onde `NOME` pode conter:

```text
A-Z

0-9

_
```

---

# 7. Exemplos reconhecidos

```text
@@MEM_PAGES@@

@@PARAMS_BASE@@

@@LP_SIZE@@

@@NUM_LAYERS@@

@@SLOT0_BASE@@

@@RESULT_COUNT@@
```

---

# 8. Exemplos não reconhecidos

Por essa regex, formas como:

```text
@@mem_pages@@
```

ou:

```text
@MEM_PAGES@
```

não correspondem ao padrão.

Portanto a convenção do projeto é:

```text
@@PLACEHOLDER_EM_MAIÚSCULAS@@
```

---

# 9. Por que validar placeholders?

Sem essa verificação, seria possível gerar algo como:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

e somente descobrir o problema posteriormente durante a compilação.

O código prefere detectar isso no próprio gerador.

---

# 10. Função `_as_bytes()`

A primeira função auxiliar é:

```python
def _as_bytes(value):
```

Sua responsabilidade é normalizar diferentes objetos binários para:

```python
bytes
```

---

# 11. Entrada já `bytes`

Se:

```python
isinstance(
    value,
    bytes,
)
```

a função simplesmente retorna:

```python
return value
```

Nenhuma cópia explícita é necessária.

---

# 12. Entrada `bytearray`

Se o objeto for:

```python
bytearray
```

é convertido por:

```python
bytes(value)
```

---

# 13. Por que converter `bytearray`?

Durante etapas de construção, os blobs são frequentemente montados como estruturas mutáveis:

```text
bytearray
```

Depois de prontos, é conveniente tratá-los como:

```text
bytes
```

imutáveis.

---

# 14. Entrada `memoryview`

Se:

```python
isinstance(
    value,
    memoryview,
)
```

é utilizado:

```python
value.tobytes()
```

---

# 15. Objetos com `.tobytes()`

Depois existe uma regra mais genérica:

```python
if hasattr(
    value,
    "tobytes",
):
    return value.tobytes()
```

Isso permite aceitar objetos binários que forneçam esse método.

Um exemplo comum no ecossistema científico Python seria um objeto NumPy.

---

# 16. Por que essa flexibilidade?

Os diferentes módulos podem trabalhar com:

```text
bytes

bytearray

memoryview

arrays com tobytes()
```

`_as_bytes()` cria uma fronteira única:

```text
qualquer representação binária suportada
            ↓
          bytes
```

---

# 17. Tipo incompatível

Se nenhuma das condições for satisfeita:

```python
raise TypeError(...)
```

---

# 18. Exemplo

Passar algo como:

```python
"abc"
```

não é interpretado automaticamente como:

```text
UTF-8
```

A função gera erro.

Isso é importante porque o gerador espera:

```text
dados binários
```

e não texto arbitrário.

---

# 19. Mensagem de erro

A exceção inclui:

```python
type(value)
```

permitindo descobrir qual tipo inesperado chegou ao gerador.

---

# 20. Responsabilidade de `_as_bytes()`

Podemos resumir:

```text
bytes ───────────────┐
                     │
bytearray ───────────┤
                     │
memoryview ──────────┤
                     ▼
                _as_bytes()
                     │
objeto.tobytes() ────┤
                     │
                     ▼
                   bytes
```

---

# 21. Função `wat_data_from_bytes()`

A segunda função é:

```python
def wat_data_from_bytes(
    data,
    base,
):
```

Seu objetivo é transformar um blob binário em um:

```text
active data segment
```

da sintaxe WAT.

---

# 22. Conceito de data segment

No WebAssembly, um data segment permite inicializar a memória linear com bytes definidos no módulo.

Conceitualmente:

```text
arquivo WASM é carregado
        │
        ▼
bytes do segmento
        │
        ▼
copiados para a memória
a partir do endereço configurado
```

---

# 23. Forma gerada

A função produz:

```wat
(data
    (i32.const BASE)
    "BYTES"
)
```

Na implementação a representação fica em uma única string:

```wat
(data (i32.const BASE) "...")
```

---

# 24. `base`

O argumento:

```python
base
```

representa o endereço inicial da memória linear no qual os dados devem ser colocados.

---

# 25. Exemplo conceitual

Se:

```text
base = 2048
```

o segmento terá forma:

```wat
(data
    (i32.const 2048)
    "..."
)
```

---

# 26. Normalização dos dados

Primeiro:

```python
raw = _as_bytes(
    data
)
```

Assim todo o restante da função trabalha exclusivamente com:

```text
bytes
```

---

# 27. Blob vazio

Se:

```python
len(raw) == 0
```

o retorno é:

```python
""
```

---

# 28. Por que não gerar um segmento vazio?

Algo como:

```wat
(data
    (i32.const 1234)
    ""
)
```

não acrescentaria dados à memória.

A função simplesmente não produz segmento.

---

# 29. Codificação dos bytes

A parte central é:

```python
encoded = "".join(
    f"\\{byte:02x}"
    for byte in raw
)
```

---

# 30. O que `byte` representa?

Ao iterar sobre um objeto `bytes` em Python, cada item é um inteiro:

```text
0 ... 255
```

Por exemplo:

```python
raw = bytes([
    0,
    1,
    127,
    255,
])
```

produz valores:

```text
0
1
127
255
```

durante o loop.

---

# 31. Formatação hexadecimal

O especificador:

```text
02x
```

gera:

```text
hexadecimal minúsculo
com dois dígitos
```

Exemplos:

```text
0   → 00

1   → 01

10  → 0a

127 → 7f

255 → ff
```

---

# 32. Escape WAT

Cada byte recebe uma barra invertida:

```text
\00

\01

\7f

\ff
```

Assim:

```python
bytes([
    0x01,
    0x7F,
    0xFF,
])
```

produz conceitualmente:

```text
\01\7f\ff
```

---

# 33. Por que codificar todos os bytes?

A própria docstring explica a decisão:

```text
Todos os bytes são escritos como escapes hexadecimais,
evitando problemas com caracteres especiais.
```

Isso significa que o gerador não tenta decidir:

```text
este byte pode ser escrito como caractere?

este precisa escapar?

aspas precisam escapar?

barra precisa escapar?
```

Todos seguem a mesma regra.

---

# 34. Vantagem

Um blob pode conter qualquer byte:

```text
00

22

5c

ff
```

sem risco de o conteúdo binário ser confundido com:

```text
aspas

barra

newline

caractere textual
```

dentro da string WAT.

---

# 35. Resultado final

A função retorna:

```python
f'(data (i32.const {int(base)}) '
f'"{encoded}")'
```

---

# 36. Conversão da base

O uso de:

```python
int(base)
```

normaliza tipos inteiros externos, como valores NumPy, antes de escrevê-los no WAT.

---

# 37. Exemplo simples

Entrada:

```python
data = bytes([
    1,
    2,
    255,
])

base = 2048
```

Saída:

```wat
(data (i32.const 2048) "\01\02\ff")
```

---

# 38. Relação com o layout

Essa função não sabe se os bytes representam:

```text
pesos

bias

multipliers

LayerParams
```

Ela apenas sabe:

```text
dados

+

endereço
```

---

# 39. Separação importante

```text
weights.py
    ↓
define conteúdo

memory.py
    ↓
define endereço

wat_data_from_bytes()
    ↓
combina ambos em sintaxe WAT
```

---

# 40. Função `build_data_segments()`

A função seguinte:

```python
def build_data_segments(
    *,
    parameter_layout,
    weights_bias,
    quantization,
    params_serialization,
):
```

constrói todos os data segments dependentes do modelo.

---

# 41. Lista `segments`

Inicialmente:

```python
segments = []
```

Cada blob não vazio produzirá um elemento dessa lista.

---

# 42. Estrutura `sources`

O código monta uma lista explícita:

```python
sources = [
    ...
]
```

contendo pares:

```text
(base, dados)
```

---

# 43. Primeiro segmento: WEIGHTS

```python
(
    parameter_layout[
        "kernel_base"
    ],
    weights_bias[
        "weights_raw"
    ],
)
```

Assim:

```text
weights_raw
    ↓
WEIGHTS_BASE
```

---

# 44. Segundo: BIAS

```text
bias_raw
    ↓
BIAS_BASE
```

---

# 45. Terceiro: MUL

```text
mul_blob
    ↓
MUL_BASE
```

---

# 46. Quarto: SHIFT

```text
shift_blob
    ↓
SHIFT_BASE
```

---

# 47. Quinto: Q6

```text
q6_blob
    ↓
Q6_BASE
```

---

# 48. Sexto: PARAMS

```text
params_blob
    ↓
PARAMS_BASE
```

---

# 49. Ordem dos segmentos

Portanto a ordem textual atual é:

```text
WEIGHTS

BIAS

MUL

SHIFT

Q6

PARAMS
```

Isso acompanha a organização lógica utilizada no layout de memória.

---

# 50. A ordem textual define os endereços?

Não.

Os endereços são explicitamente definidos por:

```wat
(i32.const BASE)
```

Portanto é o:

```text
base
```

de cada segmento que determina onde seus bytes serão inicializados.

A ordem textual apenas torna o arquivo mais previsível e legível.

---

# 51. Iteração

O código executa:

```python
for base, data in sources:
```

---

# 52. Normalização novamente

Cada:

```python
data
```

é passado por:

```python
_as_bytes()
```

antes da criação do segmento.

---

# 53. Segmentos vazios

Se:

```python
if not raw:
    continue
```

o segmento é omitido completamente.

---

# 54. Exemplo

Se hipoteticamente:

```text
bias_raw = b""
```

nenhum:

```wat
(data ... bias ...)
```

será escrito.

---

# 55. Região de memória ainda pode existir logicamente

A ausência do data segment não implica necessariamente que o layout não possua uma base associada.

Significa apenas:

```text
não existem bytes para inicializar
naquela região
```

---

# 56. Geração do segmento

Para dados não vazios:

```python
wat_data_from_bytes(
    raw,
    base,
)
```

é chamada.

---

# 57. Indentação

O código adiciona:

```python
"  "
```

antes de cada segmento.

Assim o texto inserido dentro do módulo WAT fica visualmente indentado.

---

# 58. Separação visual

Finalmente:

```python
"\n\n".join(
    segments
)
```

coloca uma linha em branco entre os segmentos.

O resultado fica conceitualmente:

```wat
  (data ... WEIGHTS ...)

  (data ... BIAS ...)

  (data ... MUL ...)

  (data ... SHIFT ...)

  (data ... Q6 ...)

  (data ... PARAMS ...)
```

---

# 59. Por que um segmento por grande região?

O gerador não cria um data segment individual para cada:

```text
tensor de peso

tensor de bias

LayerParam
```

porque os módulos anteriores já concatenaram esses dados em blobs.

---

# 60. Comparação

Sem os blobs:

```text
peso 0 → data segment

peso 1 → data segment

peso 2 → data segment

bias 0 → data segment

...
```

Com a arquitetura atual:

```text
todos os pesos
    ↓
weights_raw
    ↓
1 data segment
```

---

# 61. Vantagem

Isso mantém o WAT mais simples.

Também preserva a abstração:

```text
WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
```

como grandes regiões contíguas.

---

# 62. O que `build_data_segments()` não faz?

A função não:

```text
calcula bases

verifica sobreposição

calcula tamanho da memória

interpreta os bytes

alinha regiões
```

Ela pressupõe que:

```text
parameter_layout
```

já contém endereços corretos.

---

# 63. Função `generate_wat()`

Essa é a função principal do arquivo:

```python
def generate_wat(
    *,
    template_path,
    output_path,
    parameter_layout,
    layer_memory,
    final_memory,
    params_serialization,
    weights_bias,
    quantization,
    layer_params,
):
```

Ela reúne todas as informações anteriores e produz o arquivo final.

---

# 64. Entradas

### `template_path`

Caminho para:

```text
wat/model_template.wat
```

ou outro template equivalente.

---

### `output_path`

Caminho no qual o WAT final será salvo.

Exemplo:

```text
generated/model.wat
```

---

### `parameter_layout`

Contém:

```text
WEIGHTS_BASE

BIAS_BASE

MUL_BASE

SHIFT_BASE

Q6_BASE

PARAMS_BASE
```

---

### `layer_memory`

Fornece:

```text
slot_bases
```

e demais informações de memória das camadas.

---

### `final_memory`

Fornece principalmente:

```text
MEM_PAGES
```

já calculado.

---

### `params_serialization`

Contém:

```text
params_blob

records

LP_SIZE

informações da serialização
```

---

### `weights_bias`

Contém:

```text
weights_raw

bias_raw
```

---

### `quantization`

Contém:

```text
mul_blob

shift_blob

q6_blob
```

---

### `layer_params`

Lista estruturada das operações.

É utilizada principalmente para:

```text
número de camadas

identificação da última camada

shape da saída final
```

---

# 65. Conversão dos caminhos

Primeiro:

```python
template_path = Path(
    template_path
)

output_path = Path(
    output_path
)
```

Assim a função aceita caminhos compatíveis com `Path`.

---

# 66. Leitura do template

O arquivo é carregado por:

```python
wat = template_path.read_text(
    encoding="utf-8"
)
```

---

# 67. O template permanece textual

Nesse momento:

```text
wat
```

é uma string contendo:

```text
código WAT

+

placeholders
```

Exemplo conceitual:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

---

# 68. Validação das LayerParams

Antes de realizar substituições:

```python
if not layer_params:
```

gera:

```text
RuntimeError
```

com:

```text
"Nenhuma LayerParam foi gerada."
```

---

# 69. Por que isso é necessário?

Sem camadas, o código posterior tentaria:

```python
layer_params[-1]
```

o que não teria significado.

Além disso, um modelo executável nesse pipeline precisa possuir ao menos a camada sintética e/ou operações reais.

---

# 70. Registros da serialização

Depois:

```python
records = (
    params_serialization[
        "records"
    ]
)
```

---

# 71. Validação dos records

Se estiver vazio:

```text
RuntimeError
```

é lançado.

---

# 72. Por que `records` é necessário?

O gerador precisa recuperar:

```text
out_ptr
```

da última camada serializada.

Essa informação está em:

```text
final_record
```

---

# 73. Última camada

O código utiliza:

```python
final_layer = (
    layer_params[-1]
)
```

e:

```python
final_record = (
    records[-1]
)
```

---

# 74. Suposição importante

A implementação presume que:

```text
último layer_params
```

e:

```text
último record
```

representam a mesma operação.

Isso é verdadeiro no fluxo normal porque:

```text
params_blob.py
```

serializa `layer_params` sequencialmente.

---

# 75. Não existe comparação explícita de tamanhos

O código atual não verifica diretamente:

```text
len(records)
==
len(layer_params)
```

Essa igualdade é produzida naturalmente por `build_params_blob()` no pipeline esperado.

Uma validação explícita poderia ser adicionada futuramente.

---

# 76. `RESULT_BASE`

O endereço da saída final é obtido por:

```python
result_base = int(
    final_record[
        "out_ptr"
    ]
)
```

---

# 77. Significado

`result_base` é:

```text
base física do slot
no qual a última camada
gravou sua saída
```

---

# 78. Exemplo

Se a última camada escreve em:

```text
SLOT2
```

e:

```text
SLOT2_BASE = 900464
```

então:

```text
RESULT_BASE = 900464
```

---

# 79. Importante

`RESULT_BASE` não é uma nova região de memória.

Ele aponta para:

```text
um slot já existente
```

que contém o resultado da última operação.

---

# 80. Fluxo

```text
última LayerParam
      │
      ▼
out_slot
      │
      ▼
out_ptr
      │
      ▼
RESULT_BASE
```

---

# 81. `RESULT_COUNT`

A quantidade de valores da saída é calculada por:

```python
result_count = int(
    final_layer["out_h"]
    * final_layer["out_w"]
    * final_layer["cout"]
)
```

---

# 82. Fórmula

```text
RESULT_COUNT
=
out_h
×
out_w
×
cout
```

---

# 83. Exemplo classificatório

Se a saída for representada como:

```text
1 × 1 × 1000
```

então:

```text
RESULT_COUNT
=
1 × 1 × 1000
=
1000
```

---

# 84. Vantagem sobre valor hardcoded

O runtime não precisa ter:

```text
1000
```

fixado manualmente.

Se outro modelo compatível produzir:

```text
10 classes
```

teremos:

```text
RESULT_COUNT = 10
```

automaticamente.

---

# 85. Saída espacial

Se hipoteticamente a última camada produzir:

```text
7 × 7 × 32
```

teríamos:

```text
RESULT_COUNT
=
7 × 7 × 32
=
1568
```

---

# 86. Hipótese atual sobre batch

A fórmula utiliza apenas:

```text
H × W × C
```

e não multiplica explicitamente por batch.

Isso está coerente com o pipeline atual, que trabalha com:

```text
batch = 1
```

como convenção.

Para suporte genérico a batch maior que 1, essa parte precisaria ser revisitada.

---

# 87. Recuperação dos slots

O código obtém:

```python
slot_bases = (
    layer_memory[
        "slot_bases"
    ]
)
```

---

# 88. Validação de três slots

Depois:

```python
if len(slot_bases) != 3:
```

gera erro.

---

# 89. Por que exatamente três?

O template WAT atual possui placeholders explícitos:

```text
@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@
```

Logo existe uma dependência concreta:

```text
template atual
    ↕
3 slots
```

---

# 90. Isso não é uma limitação teórica do WebAssembly

É uma decisão do:

```text
template atual
+
runtime atual
```

O extrator poderia futuramente suportar outra quantidade, mas o template precisaria ser adaptado.

---

# 91. Mensagem de erro

O código informa:

```text
"O template atual espera exatamente 3 slots..."
```

Isso é importante porque deixa claro que:

```text
o problema não é NUM_SLOTS em abstrato
```

mas:

```text
compatibilidade com o template atual
```

---

# 92. Dicionário `replacements`

A etapa central seguinte é:

```python
replacements = {
    ...
}
```

Ele relaciona:

```text
placeholder textual
        ↓
valor calculado
```

---

# 93. `@@MEM_PAGES@@`

Recebe:

```python
final_memory[
    "mem_pages"
]
```

Esse valor define a quantidade inicial de páginas WebAssembly.

---

# 94. Origem

```text
memory.py
    ↓
MEM_END
    ↓
ceil(MEM_END / 65536)
    ↓
MEM_PAGES
```

---

# 95. `@@PARAMS_BASE@@`

Recebe:

```python
parameter_layout[
    "params_base"
]
```

---

# 96. Uso no runtime

Permite ao WAT localizar:

```text
LayerParam[0]
```

e subsequentemente:

```text
LayerParam[i]
=
PARAMS_BASE
+
i × LP_SIZE
```

---

# 97. `@@LP_SIZE@@`

Recebe:

```python
params_serialization[
    "layer_param_size"
]
```

---

# 98. Valor atual

Com a estrutura atual:

```text
LP_SIZE = 116
```

---

# 99. Por que pegar da serialização?

Isso mantém o gerador dependente do resultado real do pipeline e não de um número:

```text
116
```

hardcoded dentro dele.

---

# 100. `@@NUM_LAYERS@@`

Recebe:

```python
len(
    layer_params
)
```

---

# 101. Inclui camada sintética

Como `layer_params` começa com:

```text
RGB565_TO_RGB888
```

esse total já inclui a operação sintética.

---

# 102. Exemplo

```text
67 operações reais
+
1 sintética
=
68 layers
```

Logo:

```text
@@NUM_LAYERS@@
    ↓
68
```

---

# 103. `@@WEIGHTS_BASE@@`

Recebe:

```text
kernel_base
```

do layout.

---

# 104. `@@BIAS_BASE@@`

Recebe:

```text
bias_base
```

---

# 105. `@@MUL_BASE@@`

Recebe:

```text
mul_base
```

---

# 106. `@@SHIFT_BASE@@`

Recebe:

```text
shift_base
```

---

# 107. `@@Q6_BASE@@`

Recebe:

```text
q6_base
```

---

# 108. Por que o template recebe essas bases se as LayerParams já contêm ponteiros?

As LayerParams já contêm muitos ponteiros absolutos.

Mesmo assim, o template também pode precisar das bases globais para:

```text
debug

globals

rotinas auxiliares

documentação estrutural

ou lógica específica do runtime
```

O gerador apenas fornece os valores esperados pelo template.

---

# 109. Bases dos slots

São substituídos:

```text
@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@
```

---

# 110. Valores

```python
slot_bases[0]

slot_bases[1]

slot_bases[2]
```

respectivamente.

---

# 111. `@@RESULT_BASE@@`

Recebe:

```text
out_ptr da última camada
```

---

# 112. `@@RESULT_COUNT@@`

Recebe:

```text
out_h × out_w × cout
```

da última camada.

---

# 113. Tabela dos placeholders

| Placeholder        | Origem                                     |
| ------------------ | ------------------------------------------ |
| `@@MEM_PAGES@@`    | `final_memory["mem_pages"]`                |
| `@@PARAMS_BASE@@`  | `parameter_layout["params_base"]`          |
| `@@LP_SIZE@@`      | `params_serialization["layer_param_size"]` |
| `@@NUM_LAYERS@@`   | `len(layer_params)`                        |
| `@@WEIGHTS_BASE@@` | `parameter_layout["kernel_base"]`          |
| `@@BIAS_BASE@@`    | `parameter_layout["bias_base"]`            |
| `@@MUL_BASE@@`     | `parameter_layout["mul_base"]`             |
| `@@SHIFT_BASE@@`   | `parameter_layout["shift_base"]`           |
| `@@Q6_BASE@@`      | `parameter_layout["q6_base"]`              |
| `@@SLOT0_BASE@@`   | `slot_bases[0]`                            |
| `@@SLOT1_BASE@@`   | `slot_bases[1]`                            |
| `@@SLOT2_BASE@@`   | `slot_bases[2]`                            |
| `@@RESULT_BASE@@`  | `final_record["out_ptr"]`                  |
| `@@RESULT_COUNT@@` | `out_h × out_w × cout`                     |

Além deles existe:

```text
@@DATA_SEGMENTS@@
```

que é tratado separadamente.

---

# 114. Substituição dos valores

O código percorre:

```python
for placeholder, value
in replacements.items():
```

---

# 115. Conversão

Cada valor é transformado em:

```python
str(
    int(value)
)
```

---

# 116. Por que primeiro `int()`?

Assim valores que venham de tipos inteiros externos são normalizados.

---

# 117. Por que depois `str()`?

Porque:

```python
wat.replace()
```

opera sobre strings.

---

# 118. Exemplo

Template:

```wat
(memory
    (export "memory")
    @@MEM_PAGES@@
)
```

Com:

```text
MEM_PAGES = 17
```

torna-se:

```wat
(memory
    (export "memory")
    17
)
```

---

# 119. `str.replace()`

A função utiliza:

```python
wat = wat.replace(
    placeholder,
    replacement,
)
```

---

# 120. Consequência

Se o mesmo placeholder aparecer várias vezes no template, todas as ocorrências serão substituídas.

---

# 121. Isso é útil

Por exemplo:

```text
@@SLOT0_BASE@@
```

pode aparecer em:

```text
um global

um comentário

ou outra expressão
```

e todas as ocorrências recebem o mesmo valor.

---

# 122. `@@DATA_SEGMENTS@@`

Os blobs não são inseridos pelo dicionário numérico.

Primeiro:

```python
data_segments = (
    build_data_segments(...)
)
```

é chamado.

---

# 123. Entradas da função

São fornecidos:

```text
parameter_layout

weights_bias

quantization

params_serialization
```

Assim ela consegue unir:

```text
BASE
+
BLOB
```

para cada região.

---

# 124. Resultado

`data_segments` é uma string semelhante a:

```wat
  (data
      (i32.const WEIGHTS_BASE)
      "...")

  (data
      (i32.const BIAS_BASE)
      "...")

  ...
```

na representação compacta produzida pela função.

---

# 125. Inserção

Depois:

```python
wat = wat.replace(
    "@@DATA_SEGMENTS@@",
    data_segments,
)
```

---

# 126. Por que tratar separadamente?

Os demais placeholders recebem:

```text
um número inteiro
```

Já:

```text
@@DATA_SEGMENTS@@
```

recebe:

```text
um grande bloco de código WAT
```

---

# 127. Relação com os blobs

```text
weights_raw
     ↓
hex escapes
     ↓
WAT data segment

bias_raw
     ↓
hex escapes
     ↓
WAT data segment

mul_blob
     ↓
hex escapes
     ↓
WAT data segment

...
```

---

# 128. Exemplo conceitual de memória inicializada

Suponha:

```text
WEIGHTS_BASE = 2048

BIAS_BASE = 10000

PARAMS_BASE = 20000
```

O WAT poderia receber:

```wat
(data
    (i32.const 2048)
    "\01\02..."
)

(data
    (i32.const 10000)
    "\0a\00..."
)

(data
    (i32.const 20000)
    "\01\00\00\00..."
)
```

---

# 129. O gerador não interpreta esses bytes

Para ele:

```text
"\01\02..."
```

é apenas conteúdo binário.

A semântica foi definida anteriormente.

---

# 130. Validação de placeholders não resolvidos

Depois de todas as substituições:

```python
unresolved = sorted(
    set(
        PLACEHOLDER_PATTERN.findall(
            wat
        )
    )
)
```

---

# 131. `findall()`

A regex procura qualquer trecho restante do tipo:

```text
@@NOME@@
```

---

# 132. Uso de `set`

Se o mesmo placeholder aparecer várias vezes:

```text
@@FOO@@
@@FOO@@
@@FOO@@
```

o relatório de erro mostrará apenas:

```text
@@FOO@@
```

uma vez.

---

# 133. Uso de `sorted()`

Os placeholders restantes são ordenados.

Isso torna a mensagem de erro determinística e mais fácil de ler.

---

# 134. Erro

Se a lista não estiver vazia:

```python
raise RuntimeError(
    "Placeholders WAT não resolvidos: "
    + ", ".join(unresolved)
)
```

---

# 135. Exemplo

Se o template ganhar:

```text
@@SOMETHING_NEW@@
```

mas `generate_wat()` não for atualizado, o resultado será:

```text
Placeholders WAT não resolvidos:
@@SOMETHING_NEW@@
```

em vez de gerar silenciosamente um template incompleto.

---

# 136. Importância para evolução do template

Esse mecanismo cria um contrato entre:

```text
model_template.wat
```

e:

```text
wat_generator.py
```

Se o template exigir uma nova variável:

```text
@@NEW_VALUE@@
```

o gerador precisa aprender a preenchê-la.

---

# 137. Limite dessa validação

A regex detecta apenas placeholders no padrão definido.

Ela não verifica:

```text
sintaxe WAT completa

tipos WebAssembly

índices de funções

validade de imports

correção dos kernels
```

---

# 138. Portanto

Temos duas validações distintas:

```text
wat_generator.py
    ↓
template completamente materializado
```

e posteriormente:

```text
wat2wasm
    ↓
sintaxe e estrutura WebAssembly válidas
```

---

# 139. O gerador não compila WAT

Esse é um ponto importante.

A função:

```python
generate_wat()
```

gera:

```text
.wat
```

Ela não chama:

```text
wat2wasm
```

e não produz diretamente:

```text
.wasm
```

---

# 140. Separação de responsabilidades

```text
wat_generator.py
      ↓
source WAT

wat2wasm
      ↓
binary WASM
```

Essa divisão mantém o extrator independente da ferramenta de compilação.

---

# 141. Diretório de saída

Antes de escrever o arquivo:

```python
output_path.parent.mkdir(
    parents=True,
    exist_ok=True,
)
```

é executado.

---

# 142. `parents=True`

Permite criar toda a cadeia de diretórios necessária.

Por exemplo:

```text
generated/models/esp32/model.wat
```

pode ter seus diretórios intermediários criados.

---

# 143. `exist_ok=True`

Se o diretório já existir, isso não é tratado como erro.

---

# 144. Escrita

O arquivo é salvo por:

```python
output_path.write_text(
    wat,
    encoding="utf-8",
)
```

---

# 145. Consequência

Se o arquivo já existir:

```text
generated/model.wat
```

ele será sobrescrito com o WAT atual.

---

# 146. Fonte de verdade

Isso reforça que:

```text
generated/model.wat
```

é um artefato gerado.

Não deve ser editado manualmente como fonte primária das configurações dependentes do modelo.

A fonte está em:

```text
wat/model_template.wat
```

*

```text
dados calculados pelo extrator
```

---

# 147. Retorno da função

Depois da escrita, a função retorna metadados:

```python
{
    "output_path": ...,
    "mem_pages": ...,
    "num_layers": ...,
    "result_base": ...,
    "result_count": ...,
    "wat_bytes": ...,
}
```

---

# 148. `output_path`

É o próprio objeto:

```python
Path
```

do arquivo gerado.

---

# 149. `mem_pages`

É:

```python
int(
    final_memory[
        "mem_pages"
    ]
)
```

Isso permite ao chamador registrar a memória configurada sem reler o WAT.

---

# 150. `num_layers`

É:

```python
len(
    layer_params
)
```

---

# 151. `result_base`

É o endereço absoluto no qual começa a saída da última camada.

---

# 152. `result_count`

É a quantidade de elementos dessa saída segundo:

```text
out_h × out_w × cout
```

---

# 153. `wat_bytes`

É obtido por:

```python
output_path.stat().st_size
```

---

# 154. Significado

Esse valor representa o tamanho real do arquivo WAT gravado no sistema de arquivos:

```text
em bytes
```

---

# 155. Não confundir com tamanho do WASM

```text
wat_bytes
```

é:

```text
tamanho do arquivo textual .wat
```

Não representa:

```text
tamanho do .wasm compilado
```

nem:

```text
quantidade de memória linear
```

---

# 156. Por que o WAT pode ficar grande?

Os blobs são codificados textualmente.

Um único byte binário:

```text
0xff
```

vira textualmente:

```text
\ff
```

ou seja, vários caracteres no arquivo WAT.

Assim o `.wat` pode ser significativamente maior que a soma dos blobs binários.

---

# 157. Isso não significa que a memória WASM usa esse tamanho textual

Depois da compilação:

```text
\ff
```

representa novamente:

```text
um byte
```

no data segment binário.

---

# 158. Fluxo completo de `generate_wat()`

```text
template_path
      │
      ▼
read_text()
      │
      ▼
template WAT
      │
      ├── validar layers
      │
      ├── validar records
      │
      ▼
identificar última camada
      │
      ├── RESULT_BASE
      └── RESULT_COUNT
      │
      ▼
validar 3 slots
      │
      ▼
substituir placeholders numéricos
      │
      ▼
build_data_segments()
      │
      ▼
substituir @@DATA_SEGMENTS@@
      │
      ▼
procurar placeholders restantes
      │
      ├── encontrou
      │       ↓
      │   RuntimeError
      │
      └── nenhum
              ↓
       criar diretório
              ↓
         write_text()
              ↓
        generated WAT
```

---

# 159. Relação com `config.py`

`config.py` fornece:

```text
WAT_TEMPLATE_PATH

OUT_WAT_PATH
```

Esses caminhos podem ser passados diretamente como:

```text
template_path

output_path
```

---

# 160. Relação com `weights.py`

`weights.py` produz:

```text
weights_raw

bias_raw
```

O gerador transforma esses blobs em:

```wat
(data ...)
```

---

# 161. Relação com `quantization.py`

O módulo anterior produz:

```text
mul_blob

shift_blob

q6_blob
```

que também viram:

```wat
(data ...)
```

---

# 162. Relação com `params_blob.py`

Esse módulo produz:

```text
params_blob
```

já contendo:

```text
LayerParam[0]
LayerParam[1]
...
```

em formato binário.

`wat_generator.py` simplesmente o posiciona em:

```text
PARAMS_BASE
```

---

# 163. Relação com `memory.py`

`memory.py` determina:

```text
onde cada blob começa

quantas páginas são necessárias

onde ficam os slots
```

O gerador apenas materializa esses valores.

---

# 164. Relação com `layer_params.py`

`layer_params.py` ainda é usado diretamente para:

```text
NUM_LAYERS

shape da última saída
```

---

# 165. Relação com o template

O template contém:

```text
algoritmos
kernels
funções
controle de execução
```

que não dependem diretamente dos valores de um modelo específico.

---

# 166. O Python injeta apenas o que varia

Por exemplo:

```text
endereços

quantidade de memória

quantidade de camadas

blobs

saída
```

---

# 167. Separação central da arquitetura

```text
model_template.wat
    ↓
LÓGICA ESTÁTICA

wat_generator.py
    ↓
DADOS DINÂMICOS DO MODELO
```

---

# 168. Exemplo conceitual

Template:

```wat
(module

  (memory
      (export "memory")
      @@MEM_PAGES@@
  )

  (global $PARAMS_BASE
      i32
      (i32.const @@PARAMS_BASE@@)
  )

  ...

  @@DATA_SEGMENTS@@
)
```

---

# 169. Depois da geração

```wat
(module

  (memory
      (export "memory")
      17
  )

  (global $PARAMS_BASE
      i32
      (i32.const 499360)
  )

  ...

  (data
      (i32.const 2048)
      "\..."
  )

  ...
)
```

Os valores acima são apenas ilustrativos.

---

# 170. Por que essa arquitetura é melhor que gerar todo o WAT em Python?

Uma alternativa seria fazer:

```python
sections.append(
    "(func ..."
)
```

para cada função, loop e kernel.

Isso misturaria:

```text
algoritmo WASM

+

geração Python
```

---

# 171. Com template

Os kernels permanecem escritos diretamente em:

```text
WAT
```

onde podem ser:

```text
lidos

editados

testados

otimizados
```

como código WebAssembly.

---

# 172. Python fica responsável apenas pela especialização

```text
template genérico
      +
modelo específico
      ↓
módulo específico
```

---

# 173. Benefício para manutenção

Se quisermos alterar:

```text
implementação da convolução
```

modificamos:

```text
model_template.wat
```

Se quisermos alterar:

```text
como os pesos são extraídos
```

modificamos:

```text
weights.py
```

Se quisermos alterar:

```text
layout de memória
```

modificamos:

```text
memory.py
```

Isso reduz o acoplamento.

---

# 174. Benefício para depuração

Quando surge um erro, podemos separar:

```text
extração errada?

layout errado?

params_blob errado?

template errado?

compilação errada?
```

em vez de tudo estar misturado num único gerador monolítico.

---

# 175. Data segments como imagem inicial da memória

Uma forma útil de pensar nos data segments é:

```text
antes de executar a primeira inferência

memória WASM já contém:

WEIGHTS
BIAS
MUL
SHIFT
Q6
PARAMS
```

Os slots, por outro lado, são regiões de trabalho.

---

# 176. Visualização

```text
inicialização do módulo
        │
        ▼

┌──────────────────────┐
│ região inicial       │
├──────────────────────┤
│ WEIGHTS              │ ← data segment
├──────────────────────┤
│ BIAS                 │ ← data segment
├──────────────────────┤
│ MUL                  │ ← data segment
├──────────────────────┤
│ SHIFT                │ ← data segment
├──────────────────────┤
│ Q6                   │ ← data segment
├──────────────────────┤
│ PARAMS               │ ← data segment
├──────────────────────┤
│ SLOT0                │ ← runtime
├──────────────────────┤
│ SLOT1                │ ← runtime
├──────────────────────┤
│ SLOT2                │ ← runtime
└──────────────────────┘
```

---

# 177. Por que os slots não viram data segments?

Eles representam memória de trabalho.

Não precisam conter parâmetros persistentes específicos do modelo na inicialização.

Seus valores serão preenchidos durante:

```text
entrada

conversão RGB

inferência
```

---

# 178. `RESULT_BASE` também não cria data segment

Ele apenas informa:

```text
onde procurar o resultado
depois da execução
```

---

# 179. `RESULT_COUNT` também é metadado

Ele indica:

```text
quantos valores devem ser lidos
a partir de RESULT_BASE
```

---

# 180. Exemplo de classificação

```text
RESULT_BASE = 900464

RESULT_COUNT = 5
```

poderia significar:

```text
900464 → score classe 0

900465 → score classe 1

900466 → score classe 2

900467 → score classe 3

900468 → score classe 4
```

dependendo do tipo de saída.

---

# 181. Tipo da saída

O gerador não calcula:

```text
quantos bytes cada resultado ocupa
```

Ele calcula:

```text
quantidade de elementos
```

A interpretação do tipo permanece determinada pelo modelo/runtime.

No modelo atual, o fluxo de classificação quantizada utiliza a representação esperada pelos kernels.

---

# 182. Suposição sobre a última camada

O gerador assume:

```text
resultado da rede
=
saída da última LayerParam
```

---

# 183. Isso é adequado ao pipeline atual

A sequência de execução produzida é linearizada de modo que a última operação representa o resultado final utilizado pelo host.

---

# 184. Possível generalização futura

Um modelo com:

```text
múltiplos outputs independentes
```

poderia exigir:

```text
RESULT_BASE_0
RESULT_COUNT_0

RESULT_BASE_1
RESULT_COUNT_1
...
```

O código atual suporta apenas um resultado final selecionado pela última camada.

---

# 185. Outra hipótese: exatamente três slots

A função possui uma verificação explícita.

Portanto não existe ambiguidade:

```text
2 slots → erro

3 slots → aceito

4 slots → erro
```

para o template atual.

---

# 186. Isso protege contra inconsistência silenciosa

Sem essa verificação poderíamos ter:

```text
NUM_SLOTS = 4
```

mas o template ainda só conhecer:

```text
SLOT0
SLOT1
SLOT2
```

O quarto slot nunca seria configurado corretamente.

---

# 187. Placeholders como interface do template

Podemos considerar o conjunto:

```text
@@MEM_PAGES@@
@@PARAMS_BASE@@
@@LP_SIZE@@
@@NUM_LAYERS@@
...
```

como uma espécie de:

```text
API textual
```

entre:

```text
Python
```

e:

```text
template WAT
```

---

# 188. Se a interface mudar

Por exemplo, se o template passar a precisar:

```text
@@SLOT_BYTES@@
```

será necessário atualizar:

```python
replacements
```

---

# 189. Detecção automática

Se esquecermos:

```text
@@SLOT_BYTES@@
```

continuará no texto e será capturado por:

```text
PLACEHOLDER_PATTERN
```

---

# 190. Isso torna o template autochecking parcialmente

Não é uma validação semântica completa, mas impede uma classe importante de erros:

```text
variável dependente do modelo
não preenchida
```

---

# 191. Uma limitação da regex

Ela só detecta placeholders que respeitem exatamente:

```text
@@[A-Z0-9_]+@@
```

Portanto um erro de digitação como:

```text
@@mem_pages@@
```

não seria reconhecido pela regex como placeholder pendente.

A compilação WAT posterior provavelmente revelaria o problema, dependendo de onde esse texto aparecesse.

---

# 192. Possível melhoria futura

Uma política de template mais rígida poderia exigir que:

```text
qualquer sequência iniciada por @@
```

fosse validada.

Mas a implementação atual utiliza uma convenção simples e explícita.

---

# 193. Outra validação futura possível

O gerador poderia verificar:

```text
len(records)
==
len(layer_params)
```

antes de escolher:

```text
records[-1]
```

---

# 194. Outra possível validação

Poderia conferir:

```text
params_serialization["layer_count"]
==
len(layer_params)
```

---

# 195. Outra possível validação

Também:

```text
RESULT_BASE
+
bytes da saída
<=
MEM_END
```

poderia ser verificado.

Hoje isso é consequência esperada do planejamento anterior.

---

# 196. Outra possível validação

`build_data_segments()` poderia conferir:

```text
base + len(blob)
```

contra o início da próxima região.

Isso detectaria sobreposição diretamente antes da geração.

No pipeline atual essa responsabilidade permanece em:

```text
memory.py
```

e na coerência das estruturas anteriores.

---

# 197. Outra possível validação

Depois de escrever o WAT, uma etapa externa pode chamar:

```text
wat2wasm
```

para confirmar:

```text
sintaxe válida

tipagem válida

estrutura WASM válida
```

Isso permanece fora da função atual.

---

# 198. O gerador não modifica blobs

É importante observar que:

```text
weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
params_blob
```

não sofrem transformação numérica.

A única transformação é:

```text
bytes binários
      ↓
escapes hexadecimais WAT
```

---

# 199. Fidelidade dos blobs

Se:

```text
weights_raw
```

contém:

```text
01 ff 80
```

o WAT contém:

```text
\01\ff\80
```

e o data segment representa os mesmos três bytes.

---

# 200. Não há recomputação

`wat_generator.py` não deve:

```text
recalcular multiplier

reordenar pesos

recalcular offsets

alterar zero points

reinterpretar LayerParam
```

Essa ausência de lógica de modelo é uma característica desejável.

---

# 201. Caminho dos pesos até o WAT

```text
TFLite
   │
   ▼
weights.py
   │
   ▼
weights_raw
   │
   ▼
memory.py
   │
   └── WEIGHTS_BASE
          │
          ▼
wat_generator.py
          │
          ▼
(data
  (i32.const WEIGHTS_BASE)
  "...weights..."
)
```

---

# 202. Caminho da quantização

```text
TFLite scales
      │
      ▼
quantization.py
      │
      ├── mul_blob
      ├── shift_blob
      └── q6_blob
              │
              ▼
          memory.py
              │
              ▼
        wat_generator.py
```

---

# 203. Caminho das LayerParams

```text
layer_params.py
      │
      ▼
params_blob.py
      │
      ▼
params_blob
      │
      ▼
PARAMS_BASE
      │
      ▼
wat_generator.py
      │
      ▼
data segment PARAMS
```

---

# 204. Caminho da memória

```text
memory.py
    │
    ├── MEM_PAGES
    ├── WEIGHTS_BASE
    ├── BIAS_BASE
    ├── MUL_BASE
    ├── SHIFT_BASE
    ├── Q6_BASE
    ├── PARAMS_BASE
    └── SLOT_BASES
              │
              ▼
        wat_generator.py
```

---

# 205. Caminho do resultado

```text
última LayerParam
      │
      ▼
out_ptr
      │
      ▼
RESULT_BASE


última LayerParam
      │
      ├── out_h
      ├── out_w
      └── cout
             │
             ▼
        RESULT_COUNT
```

---

# 206. Visão arquitetural completa

```text
                        TFLite
                           │
                           ▼
                  ┌─────────────────┐
                  │    extractor    │
                  └─────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       BLOBS           LAYOUT          LAYER INFO
          │                │                │
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  wat_generator.py   │
                └─────────────────────┘
                           │
                           │
               ┌───────────┴───────────┐
               ▼                       ▼
       substituir números        inserir blobs
               │                       │
               └───────────┬───────────┘
                           ▼
                  validar template
                           │
                           ▼
                    model.wat
                           │
                           ▼
                      wat2wasm
                           │
                           ▼
                     model.wasm
```

---

# 207. O template como código e os blobs como dados

Essa arquitetura cria uma separação muito clara:

```text
model_template.wat
        ↓
código


weights_raw
bias_raw
mul_blob
shift_blob
q6_blob
params_blob
        ↓
dados
```

---

# 208. Especialização do template

O gerador transforma:

```text
WAT genérico
```

em:

```text
WAT específico do modelo
```

sem reconstruir os algoritmos.

---

# 209. Comparação com o extrator antigo

Uma abordagem monolítica poderia ter:

```text
Python
 │
 ├── calcula pesos
 ├── calcula memória
 ├── calcula quantização
 ├── escreve função conv WAT
 ├── escreve função add WAT
 ├── escreve debug
 ├── escreve data segments
 └── salva arquivo
```

A arquitetura atual possui:

```text
Python extractor
      ↓
dados estruturados

template WAT
      ↓
algoritmos estáticos

wat_generator.py
      ↓
união final
```

---

# 210. Benefício científico

Essa separação também facilita explicar o artefato.

O runtime pode ser descrito como:

```text
conjunto fixo de kernels WAT
```

enquanto o modelo é representado por:

```text
dados
+
LayerParams
```

injetados durante a geração.

---

# 211. `params_blob` como descrição da rede

Em vez de gerar uma função WAT diferente para cada convolução:

```text
conv_layer_1()
conv_layer_2()
conv_layer_3()
...
```

o runtime pode possuir um kernel genérico:

```text
conv()
```

e receber diferentes `LayerParams`.

---

# 212. O gerador preserva essa ideia

Ele não produz código específico por camada.

Os parâmetros específicos já estão em:

```text
params_blob
```

como a própria docstring de `generate_wat()` registra:

```text
Os parâmetros específicos de cada camada
já estão contidos no params_blob
e não são inseridos diretamente
nas funções WAT.
```

---

# 213. Essa frase resume a arquitetura

```text
modelo
    ↓
dados

runtime
    ↓
código
```

e não:

```text
modelo
    ↓
gerar centenas de funções diferentes
```

---

# 214. Invariantes esperados antes da chamada

Quando `generate_wat()` é executado, espera-se que:

```text
layer_params não esteja vazio

params_serialization.records não esteja vazio

slot_bases tenha exatamente 3 elementos

todos os layouts já estejam calculados

todos os blobs já estejam serializados

MEM_PAGES já esteja fechado
```

---

# 215. Invariantes depois da chamada

Se a função retornar normalmente:

```text
arquivo WAT foi escrito

nenhum placeholder reconhecido permaneceu

MEM_PAGES foi inserido

NUM_LAYERS foi inserido

bases foram inseridas

result metadata foi inserida

data segments foram inseridos
```

---

# 216. O que o retorno não garante

Ele não garante por si só que:

```text
o WAT compila

a inferência é correta

os pesos estão corretos

os kernels são corretos

os ponteiros não se sobrepõem

a saída bate com o TFLite
```

Essas garantias pertencem a outras validações e testes.

---

# 217. O que o módulo deliberadamente não faz

`wat_generator.py` não:

```text
carrega TFLite

percorre operadores

calcula slots

extrai pesos

calcula quantização

calcula SAME padding

constrói LayerParams

serializa LayerParams

calcula MEM_END

compila WAT para WASM

executa inferência
```

---

# 218. Responsabilidade exata

Ele responde apenas:

```text
dado um template WAT
e todos os artefatos já calculados,

como produzir o WAT final
correspondente a esse modelo?
```

---

# 219. Resumo das funções

| Função                  | Responsabilidade                                                   |
| ----------------------- | ------------------------------------------------------------------ |
| `_as_bytes()`           | Normalizar diferentes representações binárias para `bytes`         |
| `wat_data_from_bytes()` | Converter bytes em um active data segment WAT                      |
| `build_data_segments()` | Construir os segmentos WEIGHTS, BIAS, MUL, SHIFT, Q6 e PARAMS      |
| `generate_wat()`        | Substituir placeholders, inserir segmentos, validar e gravar o WAT |

---

# 220. Resumo dos data segments

```text
weights_raw
    +
WEIGHTS_BASE
    ↓
DATA WEIGHTS


bias_raw
    +
BIAS_BASE
    ↓
DATA BIAS


mul_blob
    +
MUL_BASE
    ↓
DATA MUL


shift_blob
    +
SHIFT_BASE
    ↓
DATA SHIFT


q6_blob
    +
Q6_BASE
    ↓
DATA Q6


params_blob
    +
PARAMS_BASE
    ↓
DATA PARAMS
```

---

# 221. Resumo dos valores numéricos

```text
MEM_PAGES
    ← final_memory

PARAMS_BASE
    ← parameter_layout

LP_SIZE
    ← params_serialization

NUM_LAYERS
    ← layer_params

WEIGHTS_BASE
BIAS_BASE
MUL_BASE
SHIFT_BASE
Q6_BASE
    ← parameter_layout

SLOT0_BASE
SLOT1_BASE
SLOT2_BASE
    ← layer_memory

RESULT_BASE
    ← última LayerParam serializada

RESULT_COUNT
    ← shape da última camada
```

---

# 222. Síntese

`wat_generator.py` representa a última etapa da construção do artefato WebAssembly.

Todos os módulos anteriores trabalham para transformar o TFLite em estruturas independentes:

```text
weights.py
    → pesos e bias

quantization.py
    → MUL, SHIFT e Q6

memory.py
    → endereços

layer_params.py
    → descrição das operações

params_blob.py
    → representação binária das operações
```

O `wat_generator.py` recebe esses resultados prontos e realiza duas operações fundamentais.

A primeira é substituir os placeholders numéricos do template:

```text
@@MEM_PAGES@@

@@PARAMS_BASE@@

@@LP_SIZE@@

@@NUM_LAYERS@@

@@WEIGHTS_BASE@@

@@BIAS_BASE@@

@@MUL_BASE@@

@@SHIFT_BASE@@

@@Q6_BASE@@

@@SLOT0_BASE@@

@@SLOT1_BASE@@

@@SLOT2_BASE@@

@@RESULT_BASE@@

@@RESULT_COUNT@@
```

A segunda é transformar os blobs binários:

```text
weights_raw

bias_raw

mul_blob

shift_blob

q6_blob

params_blob
```

em data segments WAT posicionados em seus respectivos endereços.

Assim:

```text
template estático
        +
dados específicos do modelo
        +
layout específico do modelo
        │
        ▼
WAT completo
```

Ao final, o módulo ainda verifica se algum placeholder reconhecido permanece sem resolução e somente então grava:

```text
generated/model.wat
```

Essa arquitetura mantém uma separação muito importante:

```text
EXTRAÇÃO / CÁLCULO
        ↓
Python

ALGORITMOS DE INFERÊNCIA
        ↓
template WAT

MATERIALIZAÇÃO
        ↓
wat_generator.py
```

O gerador, portanto, não é responsável por “entender” novamente a rede neural. Quando ele é chamado, toda a engenharia de interpretação do TFLite já terminou. Sua função é apenas transformar os artefatos validados em um módulo WAT autocontido e específico para aquele modelo.
