> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.md). O corpo original foi mantido.

# 06 — Mapeamento de tensors para slots (`tensor_mapping.py`)

## 1. Objetivo do módulo

O arquivo `extractor/tensor_mapping.py` cria a associação entre os identificadores de tensors existentes no modelo TFLite e os slots lógicos previamente calculados por `slots.py`.

Até a etapa anterior, o projeto possui informações como:

```text
L0 → SLOT0
L1 → SLOT1
L2 → SLOT2
```

Porém, o restante da extração frequentemente precisa responder:

```text
em qual slot está o tensor TFLite 37?
```

Assim, este módulo constrói:

```text
tensor_id → slot
```

Por exemplo:

```python
{
    0: 0,
    17: 1,
    23: 2,
    31: 0,
}
```

A interpretação é:

```text
tensor 0  → SLOT0
tensor 17 → SLOT1
tensor 23 → SLOT2
tensor 31 → SLOT0
```

---

# 2. Código atual

O módulo contém quatro funções principais:

```text
resolve_slot_from_producer()
build_tensor_slot_mapping()
validate_tensor_slot_mapping()
tensor_mapping_to_text()
```

Suas responsabilidades são:

| Função                           | Responsabilidade                                          |
| -------------------------------- | --------------------------------------------------------- |
| `resolve_slot_from_producer()`   | Resolver recursivamente o slot de um tensor               |
| `build_tensor_slot_mapping()`    | Construir o mapeamento completo                           |
| `validate_tensor_slot_mapping()` | Verificar se os operadores úteis possuem tensors mapeados |
| `tensor_mapping_to_text()`       | Gerar relatório textual                                   |

---

# 3. Posição no pipeline

O módulo aparece depois de:

```text
graph.py
   ↓
dependências entre camadas

slots.py
   ↓
camada → slot
```

e antes de:

```text
layer_params.py
   ↓
tensor → slot → ponteiro
```

Fluxo:

```text
TFLite
  │
  ▼
graph.py
  │
  │ camada → predecessores
  ▼
slots.py
  │
  │ camada → slot
  ▼
tensor_mapping.py
  │
  │ tensor → slot
  ▼
layer_params.py
  │
  │ slot → endereço
  ▼
LayerParam
```

---

# 4. Por que esse módulo é necessário?

`slots.py` conhece:

```text
L8 → SLOT2
```

Mas uma operação TFLite possui algo semelhante a:

```text
input tensor = 57
output tensor = 61
```

Logo precisamos relacionar:

```text
tensor 61
    ↓
foi produzido por L8
    ↓
L8 usa SLOT2
    ↓
tensor 61 → SLOT2
```

É exatamente essa transformação que o módulo realiza.

---

# 5. Importações

O arquivo começa com:

```python
from extractor.tflite_utils import (
    is_constant_tensor,
    op_name,
)
```

São necessárias duas informações.

### `is_constant_tensor()`

Permite distinguir:

```text
ativação intermediária
```

de:

```text
peso
bias
outro tensor constante
```

Somente tensors de dados dinâmicos precisam de slots.

### `op_name()`

É usado nas mensagens de erro da etapa de validação.

---

# 6. Três identidades diferentes

Até esta fase existem três formas diferentes de identificar elementos da rede.

### Operador TFLite

```text
op_index = 17
```

### Camada lógica

```text
L15
```

### Tensor TFLite

```text
tensor_id = 43
```

O módulo precisa navegar entre essas três representações.

---

# 7. Relações disponíveis antes desta etapa

De `graph.py` temos:

```text
producer_by_tensor
```

que responde:

```text
tensor_id → op_index produtor
```

Exemplo:

```python
producer_by_tensor[43] = 17
```

Também temos:

```text
old_idx_to_label
```

que responde:

```text
op_index → camada lógica
```

Exemplo:

```python
old_idx_to_label[17] = "L15"
```

E de `slots.py`:

```text
layer_output_slot
```

que responde:

```text
camada → slot
```

Exemplo:

```python
layer_output_slot["L15"] = 2
```

Combinando:

```text
tensor 43
   ↓
op 17
   ↓
L15
   ↓
SLOT2
```

Logo:

```text
tensor 43 → SLOT2
```

---

# 8. Função `resolve_slot_from_producer()`

A primeira função é:

```python
def resolve_slot_from_producer(
    tensor_id,
    *,
    model,
    subgraph,
    tensor_to_slot,
    producer_by_tensor,
    old_idx_to_label,
    layer_output_slot,
    visiting=None,
):
```

Ela tenta descobrir o slot de um tensor seguindo sua origem.

A lógica conceitual é:

```text
tensor
  ↓
já possui slot?
  │
  ├── sim → retorna
  │
  └── não
       ↓
qual operador o produziu?
       ↓
produtor está no grafo útil?
  │
  ├── sim → usa slot da camada
  │
  └── não
       ↓
segue entradas do produtor
       ↓
tenta encontrar origem com slot
```

---

# 9. Por que a função é recursiva?

Nem todo operador intermediário precisa estar representado diretamente no grafo utilizado pelo extrator.

Pode existir conceitualmente:

```text
L4
 ↓
operação não representada
 ↓
tensor X
 ↓
L5
```

Nesse caso, não existe necessariamente:

```text
operação intermediária → Lx → slot
```

Então a função segue a cadeia para trás.

---

# 10. Exemplo conceitual

Considere:

```text
tensor 20
   ↓
Op 8 útil
   ↓
tensor 21
   ↓
Op 9 ignorado
   ↓
tensor 22
```

Suponha:

```text
Op8 → L7 → SLOT1
```

Mas:

```text
Op9
```

não possui label lógico.

Quando queremos descobrir:

```text
tensor 22 → ?
```

a função encontra:

```text
tensor 22
   ↓
produtor = Op9
   ↓
Op9 não possui Lx
   ↓
input de Op9 = tensor 21
   ↓
produtor de tensor 21 = Op8
   ↓
Op8 → L7
   ↓
L7 → SLOT1
```

Resultado:

```text
tensor 22 → SLOT1
```

---

# 11. Parâmetro `visiting`

A função possui:

```python
visiting=None
```

Quando nenhuma coleção é fornecida:

```python
if visiting is None:
    visiting = set()
```

Esse conjunto registra quais tensors já estão sendo visitados durante a resolução atual.

---

# 12. Objetivo de `visiting`

Mesmo que o grafo esperado seja acíclico, uma rotina recursiva defensiva precisa impedir:

```text
tensor A
  ↓
tensor B
  ↓
tensor C
  ↓
tensor A
  ↓
...
```

caso alguma relação inesperada produza um ciclo durante a busca.

---

# 13. Detecção de repetição

O código:

```python
if tensor_id in visiting:
    return None
```

impede repetir indefinidamente a mesma busca.

Depois:

```python
visiting.add(tensor_id)
```

marca o tensor atual.

---

# 14. Diferença entre o ciclo do grafo e o ciclo da busca

`graph.py` já verifica ciclos na estrutura dos operadores úteis.

Mas aqui a função pode atravessar:

```text
operadores não representados
tensors intermediários
```

Portanto existe uma proteção local própria.

---

# 15. Primeiro caso: tensor já conhecido

A primeira tentativa é:

```python
if tensor_id in tensor_to_slot:
    return tensor_to_slot[tensor_id]
```

Isso funciona como cache.

Se já sabemos:

```python
tensor_to_slot[43] = 2
```

não é necessário refazer toda a cadeia de produtores.

---

# 16. Benefício do cache

Sem essa verificação, diferentes tensors poderiam provocar repetidas travessias sobre a mesma parte do grafo.

Com cache:

```text
primeira resolução
    ↓
calcula slot
    ↓
grava tensor_to_slot
    ↓
próximas consultas retornam diretamente
```

---

# 17. Descobrindo o produtor

Se o tensor ainda não possui slot:

```python
producer_op_idx = (
    producer_by_tensor.get(
        tensor_id
    )
)
```

Essa estrutura veio de `graph.py`.

---

# 18. Tensor sem produtor

Se:

```python
producer_op_idx is None
```

a função retorna:

```python
None
```

Isso pode ocorrer, por exemplo, quando o tensor é:

```text
entrada externa
```

e não é produzido por nenhuma operação.

As entradas do grafo são tratadas separadamente em `build_tensor_slot_mapping()`.

---

# 19. Produtor diretamente representado

O primeiro cenário útil é:

```python
if producer_op_idx in old_idx_to_label:
```

Isso significa que o operador produtor participa do grafo lógico.

---

# 20. Conversão para label

É obtido:

```python
layer_name = (
    old_idx_to_label[
        producer_op_idx
    ]
)
```

Exemplo:

```text
producer_op_idx = 17
```

torna-se:

```text
L15
```

---

# 21. Conversão de label para slot

Depois:

```python
output_slot = (
    layer_output_slot.get(
        layer_name
    )
)
```

Exemplo:

```python
layer_output_slot["L15"] = 2
```

Então:

```text
output_slot = 2
```

---

# 22. Registro no cache

Se o slot foi encontrado:

```python
tensor_to_slot[tensor_id] = (
    output_slot
)
```

e:

```python
return output_slot
```

Assim, aquela relação passa a ser conhecida diretamente.

---

# 23. Fluxo direto completo

```text
tensor_id
    ↓
producer_by_tensor
    ↓
op_index
    ↓
old_idx_to_label
    ↓
Lx
    ↓
layer_output_slot
    ↓
slot
    ↓
tensor_to_slot[tensor_id] = slot
```

---

# 24. Produtor não representado diretamente

Se:

```python
producer_op_idx
```

não estiver em:

```python
old_idx_to_label
```

a função não desiste imediatamente.

Ela recupera o operador:

```python
producer_op = (
    subgraph.Operators(
        producer_op_idx
    )
)
```

e passa a examinar suas entradas.

---

# 25. Ideia dessa etapa

A hipótese utilizada é:

```text
se o produtor não possui um slot próprio no grafo lógico,
talvez seu tensor possa ser associado ao mesmo fluxo
de uma entrada dinâmica anterior.
```

Essa lógica é especialmente útil para operadores que foram atravessados durante a simplificação do grafo.

---

# 26. Percorrendo as entradas

O código:

```python
for j in range(
    producer_op.InputsLength()
):
```

obtém:

```python
input_tensor_id = int(
    producer_op.Inputs(j)
)
```

---

# 27. Inputs negativos

Se:

```python
input_tensor_id < 0
```

o input é ignorado:

```python
continue
```

Isso mantém o mesmo padrão adotado em outros módulos para IDs inválidos/opcionais.

---

# 28. Tensores constantes são ignorados

A função executa:

```python
if is_constant_tensor(
    model,
    subgraph,
    input_tensor_id,
):
    continue
```

Isso é fundamental.

Suponha uma operação:

```text
entrada dinâmica
+
peso constante
```

A busca pelo slot deve seguir:

```text
entrada dinâmica
```

e não:

```text
peso
```

porque pesos não vivem nos slots de ativação.

---

# 29. Chamada recursiva

Para uma entrada dinâmica:

```python
slot = resolve_slot_from_producer(
    input_tensor_id,
    ...
)
```

A função tenta resolver novamente a cadeia.

---

# 30. `visiting.copy()`

A chamada utiliza:

```python
visiting=visiting.copy()
```

Isso cria uma cópia do conjunto de nós visitados para aquele ramo.

---

# 31. Por que copiar?

Imagine um operador com duas entradas:

```text
           input A
          /
op atual
          \
           input B
```

Cada ramo de busca recebe seu próprio estado derivado.

Assim, visitar determinado tensor no ramo A não bloqueia necessariamente sua análise independente no ramo B.

---

# 32. Quando um slot é encontrado

Se:

```python
slot is not None
```

o resultado é associado ao tensor original:

```python
tensor_to_slot[
    tensor_id
] = slot
```

e a função retorna imediatamente.

---

# 33. Primeiro caminho resolvível

É importante registrar exatamente o comportamento atual:

```text
a função percorre as entradas do produtor
e retorna o primeiro slot que conseguir resolver
```

Ela não compara múltiplos slots.

---

# 34. Implicação dessa decisão

Para operadores intermediários considerados transparentes, isso pode ser adequado.

Mas para um operador não representado que combine duas entradas dinâmicas semanticamente diferentes, como:

```text
input A em SLOT1
input B em SLOT2
```

a função retornaria o primeiro slot resolvido.

Logo, a resolução recursiva pressupõe que a travessia por operadores não representados seja semanticamente compatível com essa simplificação.

Essa é uma característica importante do algoritmo atual.

---

# 35. Falha de resolução

Se nenhum input permitir descobrir um slot:

```python
return None
```

Esse tensor permanecerá sem mapeamento.

Posteriormente será incluído em:

```text
unmapped_after
```

e, se for necessário por um operador útil, a validação falhará.

---

# 36. Função `build_tensor_slot_mapping()`

Essa é a função principal de construção:

```python
def build_tensor_slot_mapping(
    model,
    subgraph,
    *,
    slot_allocation,
    layer_output_slot,
    label_to_op_idx,
    old_idx_to_label,
    producer_by_tensor,
):
```

Ela executa quatro etapas:

```text
1. mapear outputs das camadas
2. mapear inputs do subgrafo
3. resolver intermediários
4. listar o que permaneceu sem mapeamento
```

Essa organização aparece explicitamente no código.

---

# 37. Estruturas iniciais

No começo:

```python
tensor_to_slot = {}
```

Essa será a estrutura principal.

Além dela:

```python
mapped_from_layers = []
graph_input_mappings = []
pending_before_resolution = []
```

são mantidas informações adicionais para relatório e diagnóstico.

---

# 38. `tensor_to_slot`

Essa é a fonte de verdade.

Exemplo:

```python
{
    0: 0,
    5: 0,
    9: 1,
    14: 2,
    17: 0,
}
```

Os módulos posteriores usam esse dicionário para descobrir slots.

---

# 39. `mapped_from_layers`

Essa lista registra os tensors associados diretamente às saídas das camadas.

Exemplo:

```python
{
    "tensor_id": 17,
    "layer": "L4",
    "op_index": 4,
    "slot": 2,
}
```

Ela é principalmente uma estrutura de rastreabilidade.

---

# 40. `graph_input_mappings`

Registra explicitamente os inputs externos do subgrafo que foram associados ao slot 0.

Exemplo:

```python
{
    "tensor_id": 0,
    "slot": 0,
}
```

---

# 41. `pending_before_resolution`

Registra os tensors dinâmicos que inicialmente:

```text
não eram saída já mapeada
não eram constantes
não eram input do subgrafo
```

Eles serão candidatos à resolução recursiva posterior.

---

# 42. Primeira etapa: mapear outputs das camadas

O código percorre:

```python
for alloc in slot_allocation:
```

Ou seja, utiliza diretamente o resultado produzido por `slots.py`.

---

# 43. Obtendo o label

Cada registro possui:

```python
layer_name = alloc["layer"]
```

Exemplo:

```text
L12
```

---

# 44. Voltando ao operador TFLite

Para descobrir quais tensors a camada produz:

```python
op_idx = (
    label_to_op_idx.get(
        layer_name
    )
)
```

Exemplo:

```text
L12 → op_index 14
```

---

# 45. Label sem operador

Se:

```python
op_idx is None
```

o registro é ignorado:

```python
continue
```

No fluxo normal, os labels produzidos por `graph.py` devem ter correspondência.

---

# 46. Obtendo o operador

```python
op = subgraph.Operators(
    op_idx
)
```

Agora é possível consultar seus outputs reais.

---

# 47. Percorrendo todos os outputs

O código usa:

```python
for j in range(
    op.OutputsLength()
):
```

Portanto não pressupõe que uma operação possua necessariamente apenas uma saída.

---

# 48. ID do tensor de saída

Cada saída é obtida por:

```python
tensor_id = int(
    op.Outputs(j)
)
```

IDs negativos são ignorados.

---

# 49. Slot da camada

O slot vem diretamente da alocação:

```python
output_slot = (
    alloc["output_slot"]
)
```

---

# 50. Associação tensor → slot

Então:

```python
tensor_to_slot[
    tensor_id
] = output_slot
```

Exemplo:

```text
L12 → SLOT2
L12 produz tensor 48
```

resulta em:

```text
tensor 48 → SLOT2
```

---

# 51. Registro para relatório

Além do mapeamento principal, é guardado:

```python
{
    "tensor_id": tensor_id,
    "layer": layer_name,
    "op_index": op_idx,
    "slot": output_slot,
}
```

Isso permitirá explicar posteriormente de onde cada relação veio.

---

# 52. Resultado da primeira fase

Depois dessa etapa, todos os outputs dos operadores úteis devem estar associados aos slots das respectivas camadas.

Exemplo:

```text
L0 output tensor 3  → SLOT0
L1 output tensor 10 → SLOT1
L2 output tensor 15 → SLOT2
L3 output tensor 21 → SLOT0
```

---

# 53. Segunda etapa: entradas do subgrafo

Agora o módulo identifica as entradas externas:

```python
graph_inputs = {
    int(subgraph.Inputs(i))
    for i in range(
        subgraph.InputsLength()
    )
}
```

---

# 54. Por que utilizar um `set`?

A operação principal posterior é:

```python
if tensor_id in graph_inputs:
```

Um conjunto é uma estrutura apropriada para testes de pertencimento.

---

# 55. Exemplo

Se o modelo possuir:

```text
input tensor = 0
```

teremos:

```python
graph_inputs = {
    0
}
```

---

# 56. Varredura de todos os tensors

O código percorre:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

Ou seja, nesta fase ele examina toda a tabela de tensors.

---

# 57. Tensor já mapeado

Se:

```python
tensor_id in tensor_to_slot
```

a função executa:

```python
continue
```

Isso evita sobrescrever uma associação produzida na primeira fase.

---

# 58. Tensor constante

Se:

```python
is_constant_tensor(...)
```

retornar `True`, ele também é ignorado.

Pesos e bias não precisam de slot de ativação.

---

# 59. Input do subgrafo

Se:

```python
tensor_id in graph_inputs
```

o código define:

```python
tensor_to_slot[
    tensor_id
] = 0
```

---

# 60. Por que SLOT0?

Na convenção lógica utilizada antes da introdução da camada sintética RGB565→RGB888, o input externo é inicialmente associado ao slot lógico 0.

Posteriormente, `layer_params.py` aplica a transformação necessária para o layout efetivamente utilizado pelo runtime.

Portanto, neste módulo:

```text
input do grafo → SLOT0 lógico
```

---

# 61. Registro do input

Também é inserido:

```python
{
    "tensor_id": tensor_id,
    "slot": 0,
}
```

em:

```python
graph_input_mappings
```

---

# 62. Tensor não resolvido imediatamente

Caso o tensor:

```text
não esteja mapeado
não seja constante
não seja input
```

é adicionado a:

```python
pending_before_resolution
```

---

# 63. Significado de “pendente”

Pendente não significa necessariamente erro.

Significa apenas:

```text
esse tensor não pôde ser mapeado pelas duas regras diretas
```

A etapa recursiva ainda tentará resolvê-lo.

---

# 64. Exemplo

Considere:

```text
L3
 ↓
operação ignorada
 ↓
tensor 27
 ↓
L4
```

O tensor 27:

```text
não é output de uma camada Lx diretamente
não é input do modelo
não é constante
```

Então inicialmente:

```text
tensor 27 = pendente
```

Mas a resolução recursiva poderá descobrir que ele pertence ao mesmo fluxo do slot da saída de L3.

---

# 65. Terceira etapa: fechamento recursivo

Depois:

```python
for tensor_id in range(
    subgraph.TensorsLength()
):
```

todos os tensors são novamente percorridos.

---

# 66. Tensores já conhecidos

Se já estiverem em:

```python
tensor_to_slot
```

são ignorados.

---

# 67. Constantes

Também são novamente ignoradas.

---

# 68. Tentativa de resolução

Para os demais:

```python
resolve_slot_from_producer(
    tensor_id,
    ...
)
```

é executada.

---

# 69. Por que percorrer todos novamente?

Porque a função recursiva pode adicionar novos mapeamentos ao:

```python
tensor_to_slot
```

durante a busca.

Isso funciona como uma etapa de fechamento das relações ainda faltantes.

---

# 70. Exemplo do fechamento

Antes:

```python
tensor_to_slot = {
    10: 1,
    20: 2,
}
```

Pendente:

```text
tensor 21
```

A resolução encontra:

```text
tensor 21
 ↓
produtor ignorado
 ↓
input tensor 20
 ↓
SLOT2
```

Depois:

```python
tensor_to_slot = {
    10: 1,
    20: 2,
    21: 2,
}
```

---

# 71. Quarta etapa: encontrar o que restou

Depois da resolução, é criada:

```python
unmapped_after = []
```

---

# 72. Nova varredura

Todos os tensors são verificados novamente.

Constantes são ignoradas.

Se um tensor dinâmico não estiver em:

```python
tensor_to_slot
```

ele é adicionado a:

```python
unmapped_after
```

---

# 73. Diferença entre `pending_before_resolution` e `unmapped_after`

Essa diferença é importante.

### `pending_before_resolution`

Tensors que não foram resolvidos imediatamente.

### `unmapped_after`

Tensors que continuam sem slot mesmo depois da resolução recursiva.

---

# 74. Exemplo

Inicialmente:

```python
pending_before_resolution = [
    21,
    22,
    30,
]
```

Depois da busca:

```text
21 resolvido
22 resolvido
30 não resolvido
```

Resultado:

```python
unmapped_after = [
    30
]
```

---

# 75. Por que manter os dois?

Eles ajudam a responder perguntas diferentes.

```text
pending_before_resolution
```

mostra:

```text
quais tensors exigiram tratamento indireto?
```

Já:

```text
unmapped_after
```

mostra:

```text
quais tensors continuaram problemáticos?
```

---

# 76. Retorno de `build_tensor_slot_mapping()`

A função retorna:

```python
{
    "tensor_to_slot": ...,
    "graph_inputs": ...,
    "mapped_from_layers": ...,
    "graph_input_mappings": ...,
    "pending_before_resolution": ...,
    "unmapped_after": ...,
}
```

---

# 77. Significado de cada campo

| Campo                       | Significado                                       |
| --------------------------- | ------------------------------------------------- |
| `tensor_to_slot`            | Mapeamento principal tensor → slot                |
| `graph_inputs`              | IDs dos tensors de entrada do subgrafo            |
| `mapped_from_layers`        | Tensors mapeados diretamente a partir das camadas |
| `graph_input_mappings`      | Entradas externas associadas ao SLOT0             |
| `pending_before_resolution` | Tensors que inicialmente não tinham mapeamento    |
| `unmapped_after`            | Tensors ainda sem slot após a resolução           |

---

# 78. Qual estrutura é usada pelos cálculos?

A principal é:

```python
mapping["tensor_to_slot"]
```

As demais ajudam principalmente em:

```text
rastreamento
diagnóstico
relatórios
```

---

# 79. Exemplo completo

Suponha:

```text
input tensor 0

L0 produz tensor 5 → SLOT0
L1 produz tensor 8 → SLOT1

op ignorado recebe tensor 8
e produz tensor 9

L2 recebe tensor 9
e produz tensor 12 → SLOT2
```

---

# 80. Fase 1

Outputs das camadas:

```python
tensor_to_slot = {
    5: 0,
    8: 1,
    12: 2,
}
```

---

# 81. Fase 2

Entrada externa:

```python
tensor_to_slot = {
    0: 0,
    5: 0,
    8: 1,
    12: 2,
}
```

Tensor 9 entra em:

```python
pending_before_resolution = [
    9
]
```

---

# 82. Fase 3

Resolver tensor 9:

```text
tensor 9
 ↓
produtor ignorado
 ↓
input tensor 8
 ↓
tensor 8 → SLOT1
```

Então:

```python
tensor_to_slot[9] = 1
```

---

# 83. Resultado

```python
{
    0: 0,
    5: 0,
    8: 1,
    9: 1,
    12: 2,
}
```

E:

```python
unmapped_after = []
```

---

# 84. Função `validate_tensor_slot_mapping()`

Construir o mapeamento não é suficiente.

O pipeline precisa garantir que todo tensor dinâmico realmente utilizado pelos operadores do grafo tenha slot.

A função de validação começa na linha 289 do arquivo e examina somente os operadores que fazem parte do grafo usado pelo extrator.

---

# 85. Assinatura

```python
def validate_tensor_slot_mapping(
    model,
    subgraph,
    *,
    tensor_to_slot,
    old_idx_to_label,
):
```

Ela retorna:

```python
True
```

se todas as verificações passarem.

Caso contrário, lança uma exceção.

---

# 86. Percorrendo os operadores

```python
for op_idx in range(
    subgraph.OperatorsLength()
):
```

A princípio são visitados todos os operadores.

Mas existe um filtro importante.

---

# 87. Apenas operadores úteis

O código:

```python
if op_idx not in old_idx_to_label:
    continue
```

significa:

```text
se o operador não participa do grafo lógico,
não é validado aqui
```

---

# 88. Por que isso faz sentido?

Operadores atravessados/ignorados podem possuir tensors que não recebem slots próprios.

O objetivo da validação é garantir que as operações efetivamente representadas para execução possuem todas as entradas dinâmicas necessárias.

---

# 89. Recuperando o operador

Para cada operador útil:

```python
op = subgraph.Operators(
    op_idx
)
```

---

# 90. Validação das entradas

A primeira parte percorre:

```python
op.InputsLength()
```

e obtém cada:

```python
tensor_id
```

---

# 91. Input negativo

Se:

```python
tensor_id < 0
```

é ignorado.

---

# 92. Input constante

Se:

```python
is_constant_tensor(...)
```

é verdadeiro, também é ignorado.

Isso ocorre porque constantes são acessadas pelos blocos:

```text
WEIGHTS
BIAS
```

e não pelos slots de ativação.

---

# 93. Input dinâmico sem slot

Se:

```python
tensor_id not in tensor_to_slot
```

é gerado:

```python
RuntimeError
```

com uma mensagem do tipo:

```text
[MAP-ERROR] input tensor sem slot:
op_index=...
tensor_id=...
op=...
```

---

# 94. Por que incluir `op_name()` na mensagem?

Apenas:

```text
op_index=37
```

pode ser pouco informativo.

Adicionar:

```text
op=ADD
```

facilita localizar semanticamente o problema.

---

# 95. Validação das saídas

Depois são percorridas:

```python
op.OutputsLength()
```

---

# 96. Output negativo

IDs negativos são ignorados.

---

# 97. Output sem slot

Se:

```python
tensor_id not in tensor_to_slot
```

também ocorre:

```python
RuntimeError
```

com:

```text
[MAP-ERROR] output tensor sem slot
```

---

# 98. Diferença no tratamento de inputs e outputs

Para inputs, o código explicitamente ignora constantes.

Para outputs, não existe a mesma chamada a:

```python
is_constant_tensor()
```

O comportamento atual pressupõe que as saídas dos operadores úteis que interessam à execução precisam estar mapeadas.

Essa é a implementação efetiva e deve ser considerada na leitura do código.

---

# 99. O que essa validação garante?

Ela garante:

```text
para cada operador útil:

todo input dinâmico possui slot

todo output válido possui slot
```

---

# 100. O que ela não garante?

Ela não prova, por si só, que:

```text
o slot escolhido é semanticamente correto
a vida útil foi calculada perfeitamente
os ponteiros físicos não se sobrepõem
os parâmetros de quantização são corretos
```

Essas são responsabilidades de outras etapas.

---

# 101. Exemplo de erro detectado

Considere:

```text
L10 ADD
inputs:
tensor 40
tensor 55
```

Mapeamento:

```python
tensor_to_slot = {
    40: 1
}
```

Tensor 55 está ausente.

A validação produz erro antes que seja criada uma `LayerParam` incorreta.

---

# 102. Importância de falhar cedo

Sem essa validação, o erro poderia aparecer muito depois:

```text
tensor sem slot
   ↓
ponteiro inválido
   ↓
LayerParam errada
   ↓
WAT gerado
   ↓
WASM compilado
   ↓
inferência errada
```

A validação transforma isso em:

```text
tensor sem slot
   ↓
erro imediato no extrator
```

---

# 103. Função `tensor_mapping_to_text()`

A última função transforma o resultado em texto.

Ela é exclusivamente para:

```text
relatório
debug
rastreabilidade
```

e não participa da lógica do mapeamento.

---

# 104. Tensors mapeados por camadas

Primeiro são listados:

```python
mapping[
    "mapped_from_layers"
]
```

Cada entrada gera algo semelhante a:

```text
tensor 25 (produzido por L8) -> slot 2
```

---

# 105. Benefício do formato

Esse texto registra três identidades de uma vez:

```text
tensor 25
   ↓
L8
   ↓
slot 2
```

Isso facilita conferir o vínculo entre TFLite, grafo e memória.

---

# 106. Inputs do subgrafo

Depois são listados:

```python
mapping[
    "graph_input_mappings"
]
```

Exemplo:

```text
tensor 0 (input do subgrafo) -> slot 0
```

---

# 107. Tensors inicialmente pendentes

A função recupera:

```python
pending = mapping[
    "pending_before_resolution"
]
```

Se houver conteúdo:

```text
Tensores inicialmente pendentes:
  tensor 17
  tensor 31
```

---

# 108. Importante: pendente não significa não resolvido

Um tensor presente nessa seção pode ter sido resolvido posteriormente.

Essa lista representa seu estado **antes** do fechamento recursivo.

---

# 109. Total mapeado

Depois:

```python
len(
    mapping[
        "tensor_to_slot"
    ]
)
```

é exibido.

Exemplo:

```text
Total de tensores mapeados: 71
```

---

# 110. Tensors ainda não resolvidos

Se:

```python
unmapped_after
```

não estiver vazio:

```text
Tensores sem slot após fechamento: [...]
```

Caso contrário:

```text
Fechamento de mapeamento:
nenhum tensor não-constante pendente.
```

---

# 111. Relatório versus validação

É importante distinguir:

```text
tensor_mapping_to_text()
```

de:

```text
validate_tensor_slot_mapping()
```

O primeiro apenas informa.

O segundo realmente interrompe o pipeline em caso de inconsistência relevante.

---

# 112. Exemplo conceitual de relatório

```text
tensor 5 (produzido por L0) -> slot 0
tensor 8 (produzido por L1) -> slot 1
tensor 12 (produzido por L2) -> slot 2
tensor 15 (produzido por L3) -> slot 0

tensor 0 (input do subgrafo) -> slot 0

Tensores inicialmente pendentes:
  tensor 9
  tensor 10

Total de tensores mapeados: 7

Fechamento de mapeamento:
nenhum tensor não-constante pendente.
```

---

# 113. Relação com `slots.py`

`slots.py` gera:

```text
camada → slot
```

Exemplo:

```python
{
    "L4": 1,
    "L5": 2,
}
```

`tensor_mapping.py` transforma isso em:

```text
tensor → slot
```

Exemplo:

```python
{
    31: 1,
    37: 2,
}
```

---

# 114. Relação estrutural

```text
L4
 │
 │ produz
 ▼
tensor 31
```

e:

```text
L4 → SLOT1
```

implicam:

```text
tensor 31 → SLOT1
```

---

# 115. Por que não usar apenas camada → slot?

Porque `layer_params.py` analisa diretamente operadores TFLite.

Quando encontra:

```python
input_ids = [...]
```

ele precisa responder:

```text
qual slot corresponde ao tensor input_ids[0]?
```

Não necessariamente começa com um label de camada.

---

# 116. Exemplo no `ADD`

Um `ADD` TFLite pode possuir:

```text
input tensor A = 42
input tensor B = 57
```

Para construir a operação no runtime precisamos:

```text
tensor 42 → SLOT1
tensor 57 → SLOT2
```

Não basta saber genericamente que:

```text
L6 e L9
```

são suas predecessoras.

---

# 117. Relação com ponteiros físicos

Depois de descobrir:

```text
tensor 42 → SLOT1
```

e:

```text
SLOT1_BASE = 703856
```

podemos obter:

```text
input_ptr = 703856
```

Portanto:

```text
tensor_id
   ↓
tensor_to_slot
   ↓
slot
   ↓
slot_bases
   ↓
endereço físico
```

---

# 118. Relação com `layer_params.py`

Esse fluxo é utilizado para construir campos como:

```text
in_slot
out_slot
pad_t
pad_b
input_ptrs
```

dependendo do tipo de operação.

Especialmente para:

```text
ADD
```

é necessário saber onde estão as duas entradas.

---

# 119. Exemplo completo com `ADD`

Suponha:

```text
L6 output
  ↓
tensor 50
  ↓
SLOT1
```

e:

```text
L9 output
  ↓
tensor 61
  ↓
SLOT2
```

O operador `ADD` possui:

```text
inputs = [50, 61]
```

O mapeamento fornece:

```python
tensor_to_slot[50] = 1
tensor_to_slot[61] = 2
```

Depois:

```text
slot_bases[1] → input_ptr A
slot_bases[2] → input_ptr B
```

---

# 120. Tensors constantes não usam slots

Essa é uma separação arquitetural fundamental.

Ativações:

```text
tensor → slot
```

Pesos:

```text
tensor → offset no weights blob
```

Bias:

```text
tensor → offset no bias blob
```

Logo:

```text
slot memory
```

e:

```text
parameter memory
```

são sistemas distintos.

---

# 121. Exemplo de CONV_2D

Uma convolução pode receber:

```text
input[0] = ativação
input[1] = pesos
input[2] = bias
```

Somente:

```text
input[0]
```

precisa de slot.

Os outros são constantes e são ignorados por:

```python
is_constant_tensor()
```

---

# 122. Fluxo da CONV

```text
tensor ativação
     ↓
tensor_to_slot
     ↓
SLOT1
     ↓
in_ptr

tensor pesos
     ↓
weight_tensor_off
     ↓
wptr

tensor bias
     ↓
bias_tensor_off
     ↓
bias_ptr
```

Os três inputs são tratados de maneiras diferentes.

---

# 123. O módulo como ponte

Pode-se considerar `tensor_mapping.py` como a ponte entre:

```text
representação de grafo
```

e:

```text
representação TFLite concreta
```

Porque:

```text
slots.py conhece Lx
```

enquanto:

```text
TFLite conhece tensor IDs
```

Este módulo une os dois universos.

---

# 124. Diferença para `producer_by_tensor`

Pode parecer que:

```python
producer_by_tensor
```

já resolve tudo.

Mas ele apenas fornece:

```text
tensor → operador
```

Ainda faltam:

```text
operador → label
label → slot
```

Assim:

```text
producer_by_tensor
```

é apenas a primeira relação da cadeia.

---

# 125. Cadeia completa

```text
tensor_id
   │
   ▼
producer_by_tensor
   │
   ▼
op_index
   │
   ▼
old_idx_to_label
   │
   ▼
layer_name
   │
   ▼
layer_output_slot
   │
   ▼
slot
```

---

# 126. Cadeia inversa na fase inicial

Para outputs das camadas, o código faz parcialmente o caminho contrário:

```text
layer_name
   ↓
label_to_op_idx
   ↓
op_index
   ↓
op.Outputs(...)
   ↓
tensor_id
   ↓
associa output_slot
```

Ou seja, o módulo trabalha nas duas direções.

---

# 127. `old_idx_to_label` versus `label_to_op_idx`

Esses dois mapas são inversos.

### `old_idx_to_label`

```text
op_index → Lx
```

É usado principalmente na resolução do produtor.

### `label_to_op_idx`

```text
Lx → op_index
```

É usado ao mapear os outputs das camadas.

---

# 128. Por que manter ambos?

Porque evita buscas lineares.

Sem `label_to_op_idx`, descobrir o operador de:

```text
L17
```

exigiria percorrer todo o dicionário contrário.

Com os dois mapas:

```text
conversão em qualquer direção é direta
```

---

# 129. Cache recursivo

Outro detalhe importante é que:

```python
tensor_to_slot
```

não é apenas resultado final.

Ele também atua como cache durante:

```python
resolve_slot_from_producer()
```

Isso significa que a estrutura é construída incrementalmente.

---

# 130. Exemplo de cache

Resolver tensor 40:

```text
40
 ↓
39
 ↓
38
 ↓
SLOT2
```

Durante o processo podem ser adicionados:

```python
tensor_to_slot[38] = 2
tensor_to_slot[39] = 2
tensor_to_slot[40] = 2
```

Depois, resolver outro tensor que dependa de 39 termina imediatamente.

---

# 131. Complexidade prática

A resolução recursiva pode percorrer cadeias de produtores.

Mas o cache reduz bastante a repetição.

Além disso, o modelo utilizado possui uma quantidade relativamente pequena de operadores e tensors.

Logo o custo dessa fase é irrelevante comparado à inferência.

---

# 132. Limitação da resolução recursiva

A principal suposição conceitual do algoritmo é:

```text
um tensor produzido por uma operação não representada
pode herdar o slot de algum caminho dinâmico de entrada
```

Isso faz sentido para operações tratadas como transparentes pela abstração.

Não é uma transformação universalmente válida para qualquer operador.

---

# 133. Exemplo problemático hipotético

Suponha um operador ignorado:

```text
A ─┐
   ├→ OP_X → C
B ─┘
```

com:

```text
A → SLOT1
B → SLOT2
```

Se `OP_X` combina semanticamente A e B, não existe necessariamente uma resposta correta do tipo:

```text
C → SLOT1
```

ou:

```text
C → SLOT2
```

Mas o algoritmo atual retornaria o primeiro caminho resolvido.

---

# 134. Consequência arquitetural

Portanto, `ignored_types` e esta rotina precisam permanecer coerentes.

Não se deve simplesmente adicionar qualquer operação a:

```text
ignored_types
```

sem verificar se ela pode ser atravessada dessa forma.

---

# 135. Operação transparente

Um operador conceitualmente transparente para o armazenamento poderia ser algo que:

```text
não cria necessidade de um novo buffer independente
```

ou cuja saída possa ser relacionada ao mesmo fluxo lógico de uma entrada.

Mas essa propriedade precisa ser analisada por tipo de operação.

---

# 136. Por que registrar essa limitação?

Porque futuramente o extrator pode receber modelos diferentes.

Se aparecer novo operador:

```text
TRANSPOSE
RESHAPE
CONCATENATION
SPLIT
```

não devemos concluir automaticamente que a mesma resolução recursiva é apropriada.

---

# 137. Relação com portabilidade

Esse tipo de separação é importante para o objetivo maior do projeto.

O TFLite descreve o modelo usando seu próprio esquema de tensors e operadores.

O runtime WASM utiliza:

```text
slots
ponteiros
LayerParams
```

O extrator precisa traduzir de uma representação para a outra.

`tensor_mapping.py` é uma das etapas dessa tradução.

---

# 138. Representações sucessivas

```text
TFLite:

tensor 42
tensor 57
operator 18


grafo:

L12
L15


slots:

L12 → SLOT1
L15 → SLOT2


tensor mapping:

tensor 42 → SLOT1
tensor 57 → SLOT2


runtime:

tensor 42 → endereço de SLOT1
tensor 57 → endereço de SLOT2
```

---

# 139. Separação entre slot lógico e runtime slot

Existe ainda uma etapa posterior importante.

O mapeamento produzido aqui é o:

```text
slot lógico original
```

Depois, `layer_params.py` cria um mapeamento de runtime com deslocamento por causa da camada sintética:

```text
RGB565_TO_RGB888
```

Portanto:

```text
tensor_mapping.py
    ↓
slot lógico

layer_params.py
    ↓
runtime slot
```

Esses conceitos não devem ser confundidos.

---

# 140. Exemplo

Aqui:

```text
tensor 10 → SLOT0
```

Depois da reorganização para o runtime, ele pode acabar em:

```text
runtime SLOT1
```

porque o SLOT0 físico inicial é reservado para a imagem recebida do host.

Essa transformação pertence à etapa posterior.

---

# 141. `graph_inputs`

O conjunto:

```python
graph_inputs
```

também é retornado porque será reutilizado na construção do mapeamento de runtime.

Assim não é necessário consultar novamente o subgrafo.

---

# 142. Por que retornar metadados adicionais?

Poderíamos retornar somente:

```python
tensor_to_slot
```

Mas os campos adicionais fornecem rastreabilidade.

Isso é útil em um projeto de pesquisa porque permite explicar:

```text
como aquele slot foi obtido?
```

---

# 143. Exemplo de rastreabilidade

Para um tensor:

```text
tensor 73 → SLOT2
```

podemos descobrir se ele foi:

```text
mapeado diretamente como output de Lx
```

ou se foi:

```text
resolvido indiretamente
```

Mesmo que o relatório atual não registre todos os passos recursivos individualmente, as listas ajudam a delimitar o processo.

---

# 144. Possível evolução futura

Uma versão futura poderia registrar uma origem explícita:

```python
{
    "tensor_id": 73,
    "slot": 2,
    "source": "recursive",
    "via_tensor": 71,
}
```

Isso aumentaria a rastreabilidade.

Não é necessário para o comportamento atual.

---

# 145. Validação versus `unmapped_after`

Um detalhe importante:

```text
unmapped_after não vazio
```

não significa necessariamente que a execução falhará.

A validação final verifica apenas tensors utilizados pelos operadores úteis.

Pode existir um tensor não constante no subgrafo que não seja relevante para o grafo considerado.

---

# 146. Portanto

```text
unmapped_after
```

é uma informação global sobre o subgrafo.

Já:

```text
validate_tensor_slot_mapping()
```

responde uma questão mais específica:

```text
todo tensor necessário pelas operações úteis está mapeado?
```

---

# 147. Exemplo

Suponha:

```python
unmapped_after = [
    99
]
```

Mas tensor 99 pertence apenas a um operador ignorado que não alimenta nenhuma operação útil.

A validação pode ainda passar.

---

# 148. Por que isso é útil?

Evita confundir:

```text
não mapeei absolutamente todos os tensors
```

com:

```text
não consigo executar o grafo selecionado
```

São problemas diferentes.

---

# 149. Invariantes esperados

Após construção e validação, esperamos:

### Inputs externos conhecidos

```text
graph input → SLOT0 lógico
```

### Outputs de operadores úteis conhecidos

```text
output tensor → slot da camada
```

### Inputs dinâmicos de operadores úteis conhecidos

```text
todo input dinâmico → algum slot
```

### Constantes excluídas

```text
peso/bias → não dependem de tensor_to_slot
```

---

# 150. Invariante de intervalo

Os slots encontrados devem pertencer ao conjunto configurado:

```text
0 <= slot < NUM_SLOTS
```

Essa função não verifica explicitamente essa condição porque os valores vêm da alocação anterior.

A validade depende portanto de `slots.py`.

---

# 151. Dependência entre módulos

Essa etapa demonstra uma característica importante da arquitetura modular:

```text
graph.py
```

garante produtores e labels.

```text
slots.py
```

garante camada → slot.

```text
tensor_mapping.py
```

combina as duas estruturas.

Cada módulo possui responsabilidade diferente.

---

# 152. Cadeia de erro possível

Se:

```text
graph.py errar o produtor
```

então:

```text
tensor_mapping.py pode apontar para camada errada
```

Se:

```text
slots.py errar o slot
```

então:

```text
tensor_mapping.py propagará o slot errado
```

Logo esta etapa depende da correção das anteriores.

---

# 153. Porém também funciona como barreira

A função:

```python
validate_tensor_slot_mapping()
```

introduz uma barreira de consistência.

Antes de construir parâmetros de execução:

```text
todos os tensors necessários devem ter slot
```

Isso reduz a possibilidade de erros silenciosos.

---

# 154. O que este módulo não faz

`tensor_mapping.py` não:

```text
calcula endereço dos slots
calcula tamanho dos slots
extrai pesos
extrai bias
calcula quantização
serializa LayerParam
gera WAT
```

Ele trabalha exclusivamente com:

```text
IDs de tensor
IDs de operador
labels de camada
slots lógicos
```

---

# 155. Por que não calcular endereço aqui?

Porque isso criaria dependência de:

```text
params_base
SLOT_BYTES
ALIGN
slot_bases
```

Essas informações pertencem ao planejamento físico de memória.

Aqui queremos apenas:

```text
tensor 42 → slot 1
```

e não:

```text
tensor 42 → endereço 703856
```

---

# 156. Separação lógica/física

```text
tensor_mapping.py
      ↓
tensor → SLOT1

memory.py
      ↓
SLOT1 → 703856

layer_params.py
      ↓
tensor → SLOT1 → 703856
```

Essa divisão reduz o acoplamento.

---

# 157. Relação com o relatório seguinte

O arquivo de relatório desta etapa pode ser utilizado para conferir manualmente:

```text
outputs das camadas
inputs do grafo
tensors pendentes
tensors não resolvidos
```

Antes de avançar para:

```text
pesos
quantização
memória
LayerParams
```

---

# 158. Resumo da resolução direta

```text
tensor
  ↓
producer
  ↓
op útil
  ↓
Lx
  ↓
slot da camada
  ↓
tensor → slot
```

---

# 159. Resumo da resolução indireta

```text
tensor
  ↓
producer
  ↓
op não representado
  ↓
input não constante
  ↓
resolver recursivamente
  ↓
slot conhecido
  ↓
tensor → mesmo slot
```

---

# 160. Resumo da construção completa

```text
                  slot_allocation
                        │
                        ▼
          mapear outputs das camadas
                        │
                        ▼
                  tensor_to_slot
                        │
                        ▼
              mapear graph inputs
                        │
                        ▼
                 SLOT0 lógico
                        │
                        ▼
             localizar pendentes
                        │
                        ▼
          resolução recursiva por produtor
                        │
                        ▼
                 fechamento
                        │
                        ▼
              listar não mapeados
                        │
                        ▼
                  validação
```

---

# 161. Resumo da validação

```text
para cada operador útil
       │
       ├── inputs
       │     │
       │     ├── constante → ignora
       │     └── dinâmico → precisa de slot
       │
       └── outputs
             │
             └── precisam de slot
```

---

# 162. Resumo arquitetural

Neste ponto o projeto já possui três níveis de representação de memória:

```text
NÍVEL 1 — GRAFO

L6 → L9 → L10


NÍVEL 2 — SLOT POR CAMADA

L6  → SLOT1
L9  → SLOT2
L10 → SLOT0


NÍVEL 3 — SLOT POR TENSOR

tensor 41 → SLOT1
tensor 52 → SLOT2
tensor 60 → SLOT0
```

Ainda falta:

```text
NÍVEL 4 — ENDEREÇO FÍSICO

SLOT0 → base X
SLOT1 → base Y
SLOT2 → base Z
```

Essa etapa será resolvida posteriormente pelo planejamento de memória.

---

# 163. Papel no pipeline completo

```text
┌──────────────────────────────┐
│          graph.py            │
│                              │
│ tensor → produtor            │
│ op → Lx                      │
└──────────────┬───────────────┘
               │
               │
┌──────────────▼───────────────┐
│          slots.py            │
│                              │
│ Lx → slot                    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│    tensor_mapping.py         │
│                              │
│ tensor → slot                │
│                              │
│ + resolução recursiva        │
│ + validação                  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      layer_params.py         │
│                              │
│ tensor → runtime slot        │
│ runtime slot → ponteiro      │
└──────────────────────────────┘
```

---

# 164. Síntese

O problema central resolvido por `tensor_mapping.py` é a diferença entre a maneira como o planejamento de memória foi feito e a maneira como o modelo TFLite referencia seus dados.

O planejamento trabalha com:

```text
camadas
```

O TFLite trabalha com:

```text
tensors
```

Logo é necessária a transformação:

```text
camada
   ↓
slot

tensor
   ↓
produtor
   ↓
camada
   ↓
slot
```

Para outputs diretamente ligados a uma camada útil, essa associação é simples.

Para tensors produzidos por operações não representadas diretamente, o módulo tenta preservar a continuidade do fluxo seguindo recursivamente os produtores anteriores.

Finalmente, uma validação garante que todos os inputs dinâmicos e outputs exigidos pelos operadores efetivamente utilizados pelo extrator possuam slot conhecido antes que o pipeline avance.

A saída principal:

```python
tensor_to_slot
```

é, portanto, a conexão fundamental entre:

```text
estrutura TFLite
```

e:

```text
planejamento lógico de memória
```

e será utilizada posteriormente para transformar IDs de tensors em slots de runtime e, finalmente, em endereços concretos na memória linear do módulo WebAssembly.
