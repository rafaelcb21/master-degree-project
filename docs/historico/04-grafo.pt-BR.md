[English](04-graph.md) | [Português (Brasil)](04-grafo.pt-BR.md)

> **Documento histórico preservado.** Este texto pertence à arquitetura anterior e conserva exemplos técnicos úteis. Caminhos, orquestração em `main.py`, camada sintética obrigatória e descrições do runtime podem estar desatualizados. Para o comportamento atual, consulte o [índice](../README.pt-BR.md) e as [inconsistências verificadas](../99-inconsistencias-e-limitacoes.pt-BR.md). O corpo original foi mantido.

# 04 — Construção do grafo de operadores (`graph.py`)

## 1. Objetivo do módulo

O arquivo `extractor/graph.py` transforma o conjunto de operadores e tensors do `SubGraph` TFLite em uma representação explícita das dependências entre operações.

O código atual é:

```python
from collections import defaultdict, deque
from extractor.tflite_utils import op_name


def build_graph_for_subgraph(model, subgraph):
    n_ops = subgraph.OperatorsLength()

    producer_by_tensor = {}
    consumers_by_tensor = defaultdict(list)
    op_types = []

    for op_idx in range(n_ops):
        op = subgraph.Operators(op_idx)

        op_type = op_name(model, op)
        op_types.append(op_type)

        # Registra qual operador produz cada tensor.
        for j in range(op.OutputsLength()):
            tensor_id = int(op.Outputs(j))

            if tensor_id >= 0:
                producer_by_tensor[tensor_id] = op_idx

        # Registra quais operadores consomem cada tensor.
        for j in range(op.InputsLength()):
            tensor_id = int(op.Inputs(j))

            if tensor_id >= 0:
                consumers_by_tensor[tensor_id].append(op_idx)

    return (
        op_types,
        producer_by_tensor,
        consumers_by_tensor,
    )


def compute_useful_adjacency(
    subgraph,
    op_types,
    consumers_by_tensor,
    ignored_types=None,
):
    if ignored_types is None:
        ignored_types = set()

    n_ops = subgraph.OperatorsLength()

    ignored = {
        op_idx
        for op_idx, op_type in enumerate(op_types)
        if op_type in ignored_types
    }

    useful = [
        op_idx
        for op_idx in range(n_ops)
        if op_idx not in ignored
    ]

    # Relações:
    #
    # operador -> operadores seguintes
    forward = defaultdict(set)

    for op_idx in range(n_ops):
        op = subgraph.Operators(op_idx)

        for j in range(op.OutputsLength()):
            tensor_id = int(op.Outputs(j))

            if tensor_id < 0:
                continue

            for consumer in consumers_by_tensor.get(
                tensor_id,
                [],
            ):
                if consumer != op_idx:
                    forward[op_idx].add(consumer)

    # Relações:
    #
    # operador -> operadores anteriores
    backward = defaultdict(set)

    for source, destinations in forward.items():
        for destination in destinations:
            backward[destination].add(source)

    def next_useful_from(op_idx):
        result = set()
        stack = [op_idx]
        seen = set()

        while stack:
            current = stack.pop()

            for next_op in forward.get(current, []):
                if next_op in seen:
                    continue

                seen.add(next_op)

                if next_op in ignored:
                    stack.append(next_op)
                else:
                    result.add(next_op)

        return result

    def prev_useful_to(op_idx):
        result = set()
        stack = [op_idx]
        seen = set()

        while stack:
            current = stack.pop()

            for previous_op in backward.get(current, []):
                if previous_op in seen:
                    continue

                seen.add(previous_op)

                if previous_op in ignored:
                    stack.append(previous_op)
                else:
                    result.add(previous_op)

        return result

    useful_inputs = {
        op_idx: prev_useful_to(op_idx)
        for op_idx in useful
    }

    useful_outputs = {
        op_idx: next_useful_from(op_idx)
        for op_idx in useful
    }

    return (
        useful,
        useful_inputs,
        useful_outputs,
    )


def topo_order(
    nodes,
    in_edges,
    out_edges,
):
    indegree = {
        node: len(in_edges[node])
        for node in nodes
    }

    queue = deque(
        sorted(
            node
            for node in nodes
            if indegree[node] == 0
        )
    )

    order = []

    while queue:
        current = queue.popleft()

        order.append(current)

        for destination in sorted(
            out_edges[current]
        ):
            indegree[destination] -= 1

            if indegree[destination] == 0:
                queue.append(destination)

    if len(order) != len(nodes):
        raise RuntimeError(
            "Grafo possui ciclo "
            "(inesperado para TFLite)."
        )

    return order


def build_layers(
    op_types,
    useful,
    useful_inputs,
    useful_outputs,
    order,
):
    """
    Cria a representação estruturada das camadas.

    Exemplo:

    {
        "type": "ADD",
        "name": "L10",
        "above": ["L6", "L9"],
        "below": ["L11"],
        "op_index": 10
    }
    """

    new_label = {
        old_idx: f"L{i}"
        for i, old_idx in enumerate(useful)
    }

    layers = []

    for old_idx in order:
        above = sorted(
            [
                new_label[producer]
                for producer
                in useful_inputs[old_idx]
                if producer in new_label
            ],
            key=lambda label: int(label[1:]),
        )

        below = sorted(
            [
                new_label[consumer]
                for consumer
                in useful_outputs[old_idx]
                if consumer in new_label
            ],
            key=lambda label: int(label[1:]),
        )

        layers.append(
            {
                "type": op_types[old_idx],
                "name": new_label[old_idx],
                "above": above,
                "below": below,
                "op_index": old_idx,
            }
        )

    return layers, new_label


def graph_to_text(layers):
    """
    Converte o grafo estruturado para a representação textual
    utilizada nos relatórios.
    """

    lines = [
        (
            "nome_da_camada; "
            "camada_atual; "
            "camada_acima; "
            "camada_de_baixo"
        )
    ]

    for layer in layers:
        above = (
            "["
            + ", ".join(layer["above"])
            + "]"
            if layer["above"]
            else "[]"
        )

        below = (
            "["
            + ", ".join(layer["below"])
            + "]"
            if layer["below"]
            else "[]"
        )

        lines.append(
            f"{layer['type']}; "
            f"{layer['name']}; "
            f"{above}; "
            f"{below}"
        )

    return "\n".join(lines)


def build_graph(
    model,
    subgraph,
    ignored_types=None,
):
    """
    Executa todo o processo de construção do grafo.

    Retorna tanto as estruturas utilizadas pelas próximas
    etapas quanto a representação textual para relatório.
    """

    (
        op_types,
        producer_by_tensor,
        consumers_by_tensor,
    ) = build_graph_for_subgraph(
        model,
        subgraph,
    )

    (
        useful,
        useful_inputs,
        useful_outputs,
    ) = compute_useful_adjacency(
        subgraph,
        op_types,
        consumers_by_tensor,
        ignored_types=ignored_types,
    )

    order = topo_order(
        useful,
        useful_inputs,
        useful_outputs,
    )

    layers, new_label = build_layers(
        op_types,
        useful,
        useful_inputs,
        useful_outputs,
        order,
    )

    data = graph_to_text(layers)

    old_idx_to_label = {
        old_idx: label
        for old_idx, label
        in new_label.items()
    }

    label_to_op_idx = {
        label: old_idx
        for old_idx, label
        in new_label.items()
    }

    return {
        "op_types": op_types,

        "producer_by_tensor": (
            producer_by_tensor
        ),

        "consumers_by_tensor": (
            consumers_by_tensor
        ),

        "useful": useful,
        "useful_inputs": useful_inputs,
        "useful_outputs": useful_outputs,

        "order": order,

        "new_label": new_label,
        "old_idx_to_label": old_idx_to_label,
        "label_to_op_idx": label_to_op_idx,

        "layers": layers,

        # Somente para relatório/debug.
        "data": data,
    }
```

---

# 2. Papel arquitetural

O TFLite fornece operadores e tensors, mas o restante do extrator precisa responder perguntas como:

```text
qual camada produz o dado usado por esta camada?

quais camadas dependem da saída desta camada?

uma saída ainda será utilizada no futuro?

quando um slot pode ser reutilizado?

quais são as duas entradas de um ADD?

qual é a ordem válida de execução?
```

O objetivo de `graph.py` é construir as estruturas necessárias para responder essas perguntas.

Conceitualmente:

```text
TFLite SubGraph
      │
      ├── Operators
      └── Tensors
             │
             ▼
          graph.py
             │
             ├── producers
             ├── consumers
             ├── dependências
             ├── ordem topológica
             └── layers
                     │
                     ▼
              módulos posteriores
```

---

# 3. O grafo não é construído diretamente entre tensors

Uma característica importante é que a representação final utilizada pelo extrator é principalmente um **grafo entre operadores**.

No TFLite, a relação original ocorre por intermédio dos tensors:

```text
Operador A
    │
    │ produz
    ▼
Tensor 10
    │
    │ consumido por
    ▼
Operador B
```

O módulo converte essa estrutura para:

```text
Operador A
    │
    ▼
Operador B
```

Assim, os tensors funcionam como meio para descobrir as dependências entre operações.

---

# 4. Exemplo simples

Imagine três operações:

```text
Op 0: CONV_2D
   ↓ tensor 4

Op 1: DEPTHWISE_CONV_2D
   ↓ tensor 7

Op 2: CONV_2D
```

O TFLite descreve:

```text
Op0 output = tensor 4
Op1 input  = tensor 4

Op1 output = tensor 7
Op2 input  = tensor 7
```

O grafo lógico torna-se:

```text
Op0
 ↓
Op1
 ↓
Op2
```

Posteriormente:

```text
L0
 ↓
L1
 ↓
L2
```

---

# 5. Importações

O módulo começa com:

```python
from collections import defaultdict, deque
```

e:

```python
from extractor.tflite_utils import op_name
```

Cada uma possui uma função distinta.

---

# 6. `defaultdict`

`defaultdict` é utilizado para construir coleções nas quais uma chave inexistente recebe automaticamente um valor inicial.

Exemplo:

```python
consumers_by_tensor = defaultdict(list)
```

Assim:

```python
consumers_by_tensor[10].append(3)
```

funciona mesmo que:

```text
tensor 10
```

ainda não tenha aparecido no dicionário.

O valor inicial será:

```python
[]
```

---

# 7. Uso de `defaultdict(set)`

Mais tarde:

```python
forward = defaultdict(set)
```

e:

```python
backward = defaultdict(set)
```

utilizam conjuntos.

Isso é importante porque a mesma relação entre dois operadores não precisa aparecer mais de uma vez.

Por exemplo:

```python
forward[3].add(5)
```

executado duas vezes ainda resulta em:

```python
{5}
```

e não:

```python
[5, 5]
```

---

# 8. `deque`

A estrutura:

```python
deque
```

é usada em:

```python
topo_order()
```

para manter a fila de operadores que já não possuem dependências pendentes.

As operações:

```python
queue.append(...)
queue.popleft()
```

são apropriadas para implementar uma fila FIFO.

---

# 9. `op_name()`

A função:

```python
op_name(model, op)
```

vem de:

```text
tflite_utils.py
```

e converte o código interno TFLite em um nome como:

```text
CONV_2D
DEPTHWISE_CONV_2D
ADD
MEAN
SOFTMAX
QUANTIZE
```

Assim, `graph.py` trabalha com nomes legíveis.

---

# 10. Primeira fase: `build_graph_for_subgraph()`

A primeira função é:

```python
def build_graph_for_subgraph(
    model,
    subgraph,
):
```

Ela realiza uma varredura completa nos operadores do subgrafo.

Seu objetivo é descobrir três estruturas:

```text
op_types

producer_by_tensor

consumers_by_tensor
```

---

# 11. Quantidade de operadores

A primeira linha é:

```python
n_ops = subgraph.OperatorsLength()
```

Se o modelo possuir, por exemplo:

```text
67 operadores TFLite
```

teremos:

```python
n_ops = 67
```

Os índices serão:

```text
0
1
2
...
66
```

---

# 12. Estruturas iniciais

São criadas:

```python
producer_by_tensor = {}
```

```python
consumers_by_tensor = defaultdict(list)
```

```python
op_types = []
```

Cada uma responde a uma pergunta diferente.

---

# 13. `op_types`

Essa lista relaciona:

```text
índice do operador
        ↓
tipo do operador
```

Por exemplo:

```python
op_types = [
    "QUANTIZE",
    "CONV_2D",
    "DEPTHWISE_CONV_2D",
    "CONV_2D",
    "ADD",
]
```

Assim:

```python
op_types[3]
```

retorna:

```text
CONV_2D
```

---

# 14. Varredura dos operadores

O loop principal é:

```python
for op_idx in range(n_ops):
    op = subgraph.Operators(
        op_idx
    )
```

Para cada posição:

```text
0
1
2
...
n_ops - 1
```

é recuperado o operador correspondente.

---

# 15. Identificação do tipo

Depois:

```python
op_type = op_name(
    model,
    op
)
```

e:

```python
op_types.append(
    op_type
)
```

Assim, a posição da lista coincide com o índice original da operação no TFLite.

---

# 16. Identificação dos produtores

O código:

```python
for j in range(
    op.OutputsLength()
):
```

percorre todos os tensors produzidos pelo operador.

Cada saída é recuperada com:

```python
tensor_id = int(
    op.Outputs(j)
)
```

---

# 17. Estrutura `producer_by_tensor`

Se:

```python
tensor_id >= 0
```

é armazenado:

```python
producer_by_tensor[
    tensor_id
] = op_idx
```

Isso cria relações como:

```text
tensor 10 → op 3
tensor 11 → op 4
tensor 15 → op 7
```

Ou:

```python
{
    10: 3,
    11: 4,
    15: 7,
}
```

A interpretação é:

```text
o tensor 10 foi produzido pelo operador 3
```

---

# 18. Por que um dicionário simples é suficiente?

A estrutura assume que um tensor possui um produtor.

Isso corresponde à natureza do fluxo de dados:

```text
um tensor intermediário
        ↓
é resultado de uma determinada operação
```

Por isso:

```python
tensor_id → op_idx
```

é suficiente.

---

# 19. Identificação dos consumidores

Depois são percorridas as entradas:

```python
for j in range(
    op.InputsLength()
):
```

Cada tensor é obtido por:

```python
tensor_id = int(
    op.Inputs(j)
)
```

Se o ID for válido:

```python
consumers_by_tensor[
    tensor_id
].append(
    op_idx
)
```

---

# 20. Por que consumidores são uma lista?

Uma mesma saída pode ser consumida por mais de uma operação.

Exemplo:

```text
               ┌──→ Op B
Op A → tensor X
               └──→ Op C
```

Então:

```python
consumers_by_tensor[X]
```

pode ser:

```python
[B, C]
```

Por isso não é utilizado:

```python
tensor → único consumidor
```

mas:

```python
tensor → lista de consumidores
```

---

# 21. Exemplo de producer/consumer

Considere:

```text
Op 0
 │
 └── tensor 5
       │
       ├──→ Op 1
       └──→ Op 3
```

As estruturas serão:

```python
producer_by_tensor = {
    5: 0
}
```

e:

```python
consumers_by_tensor = {
    5: [1, 3]
}
```

---

# 22. IDs negativos

O código verifica:

```python
if tensor_id >= 0:
```

Tanto para inputs quanto outputs.

Isso impede que identificadores negativos sejam tratados como índices reais de tensor.

Portanto:

```text
tensor_id < 0
```

é ignorado na construção das relações.

---

# 23. Retorno da primeira fase

A função retorna:

```python
return (
    op_types,
    producer_by_tensor,
    consumers_by_tensor,
)
```

Neste momento ainda não existe:

```text
L0
L1
L2
```

nem ordenação topológica.

Existe apenas um mapeamento estrutural do subgrafo original.

---

# 24. Primeira representação

Após `build_graph_for_subgraph()` temos conceitualmente:

```text
                   tensor 5
                  /        \
                 /          \
             produz       consome
               /              \
            Op 0              Op 1
```

Convertido para estruturas:

```text
producer_by_tensor[5] = 0

consumers_by_tensor[5] = [1]
```

---

# 25. Segunda fase: `compute_useful_adjacency()`

A função:

```python
def compute_useful_adjacency(
    subgraph,
    op_types,
    consumers_by_tensor,
    ignored_types=None,
):
```

transforma as relações via tensors em relações diretas entre operadores.

Ela também suporta ignorar determinados tipos de operação sem quebrar o grafo lógico.

---

# 26. `ignored_types`

O parâmetro:

```python
ignored_types=None
```

permite definir tipos de operador que não devem aparecer como nós finais do grafo útil.

Se nada for informado:

```python
if ignored_types is None:
    ignored_types = set()
```

Portanto, por padrão:

```text
nenhuma operação é ignorada
```

---

# 27. Por que utilizar `set()`?

Um conjunto é apropriado para testes como:

```python
if op_type in ignored_types:
```

Exemplo:

```python
ignored_types = {
    "RESHAPE",
    "IDENTITY",
}
```

A consulta é direta:

```text
"RESHAPE" ∈ ignored_types?
```

---

# 28. Identificação dos operadores ignorados

O código:

```python
ignored = {
    op_idx
    for op_idx, op_type
    in enumerate(op_types)
    if op_type in ignored_types
}
```

converte:

```text
tipos ignorados
```

em:

```text
índices concretos de operadores ignorados
```

Exemplo:

```python
op_types = [
    "CONV_2D",
    "RESHAPE",
    "ADD",
]
```

e:

```python
ignored_types = {
    "RESHAPE"
}
```

resultam em:

```python
ignored = {
    1
}
```

---

# 29. Operadores úteis

Depois:

```python
useful = [
    op_idx
    for op_idx in range(n_ops)
    if op_idx not in ignored
]
```

No exemplo:

```text
op 0 = útil
op 1 = ignorado
op 2 = útil
```

Então:

```python
useful = [
    0,
    2,
]
```

---

# 30. Importante: ignorar não significa simplesmente apagar

Se fizéssemos apenas:

```text
Op 0 → Op 1 → Op 2
```

e removêssemos:

```text
Op 1
```

o resultado ingênuo seria:

```text
Op 0

Op 2
```

sem relação.

Mas a dependência lógica deveria continuar:

```text
Op 0 → Op 2
```

A função resolve exatamente esse problema.

---

# 31. Construção de `forward`

A estrutura:

```python
forward = defaultdict(set)
```

representa:

```text
operador
    ↓
operadores seguintes diretamente conectados
```

---

# 32. Percorrendo outputs

Para cada operador:

```python
for op_idx in range(n_ops):
```

é percorrido:

```python
op.OutputsLength()
```

Cada output fornece:

```python
tensor_id
```

---

# 33. Encontrando consumidores

Para cada tensor produzido:

```python
for consumer in (
    consumers_by_tensor.get(
        tensor_id,
        [],
    )
):
```

são encontrados todos os operadores que o utilizam.

---

# 34. Criando a aresta

Se:

```python
consumer != op_idx
```

é adicionada:

```python
forward[
    op_idx
].add(
    consumer
)
```

Ou seja:

```text
op_idx → consumer
```

---

# 35. Exemplo de `forward`

Suponha:

```text
Op 2 produz tensor 11
Op 4 consome tensor 11
```

Teremos:

```python
forward[2] = {
    4
}
```

Se Op 2 alimentar dois operadores:

```text
       ┌──→ Op 4
Op 2 ──┤
       └──→ Op 7
```

teremos:

```python
forward[2] = {
    4,
    7,
}
```

---

# 36. Por que `set`?

Imagine que dois tensors diferentes criem relação entre os mesmos operadores.

Mesmo assim, para a topologia basta saber:

```text
Op A depende de Op B
```

uma única vez.

O `set` elimina duplicação.

---

# 37. Estrutura `backward`

Depois:

```python
backward = defaultdict(set)
```

é construída invertendo todas as arestas.

O código é:

```python
for source, destinations in (
    forward.items()
):
    for destination in destinations:
        backward[
            destination
        ].add(
            source
        )
```

---

# 38. `forward` versus `backward`

Se:

```text
Op 3 → Op 8
```

temos:

```python
forward[3] = {
    8
}
```

e:

```python
backward[8] = {
    3
}
```

Portanto:

```text
forward
   pergunta:
   "quem vem depois?"

backward
   pergunta:
   "quem vem antes?"
```

---

# 39. Por que precisamos das duas direções?

Posteriormente queremos montar:

```text
above
below
```

para cada camada.

Por exemplo:

```text
       L3
       ↓
       L5
       ↓
       L8
```

Para L5:

```text
above = [L3]
below = [L8]
```

Uma única direção não seria tão conveniente.

---

# 40. `next_useful_from()`

Essa função interna é:

```python
def next_useful_from(op_idx):
```

Ela procura os próximos operadores **úteis**, atravessando automaticamente operadores ignorados.

---

# 41. Estruturas internas da busca

São criadas:

```python
result = set()
```

```python
stack = [
    op_idx
]
```

```python
seen = set()
```

Cada uma possui uma função.

### `result`

Armazena os próximos operadores úteis encontrados.

### `stack`

Controla os nós ainda a visitar.

### `seen`

Evita visitar repetidamente o mesmo operador.

---

# 42. Estratégia de busca

O código usa:

```python
current = stack.pop()
```

Portanto a estrutura funciona como uma pilha.

Conceitualmente, trata-se de uma travessia em profundidade.

---

# 43. Próximos operadores

Para cada operador atual:

```python
for next_op in forward.get(
    current,
    [],
):
```

são analisadas suas saídas lógicas.

---

# 44. Evitando revisitas

O código:

```python
if next_op in seen:
    continue
```

impede processar novamente um nó já encontrado.

Depois:

```python
seen.add(
    next_op
)
```

registra a visita.

---

# 45. Operador ignorado

O ponto principal é:

```python
if next_op in ignored:
    stack.append(
        next_op
    )
```

Ou seja:

```text
encontrei um operador ignorado
            ↓
não adiciono ao resultado
            ↓
continuo procurando depois dele
```

---

# 46. Operador útil

Caso contrário:

```python
else:
    result.add(
        next_op
    )
```

A busca para naquele caminho assim que encontra o próximo operador útil.

---

# 47. Exemplo sem ignorados

```text
Op0 → Op1 → Op2
```

Se todos forem úteis:

```python
next_useful_from(0)
```

retorna:

```python
{1}
```

Não retorna:

```python
{1, 2}
```

porque Op1 já é o próximo nó útil.

---

# 48. Exemplo com operador ignorado

Considere:

```text
Op0 → Op1 → Op2
```

onde:

```text
Op1 = ignorado
```

Então:

```python
next_useful_from(0)
```

faz:

```text
Op0
 ↓
Op1 ignorado
 ↓
continua busca
 ↓
Op2 útil
```

resultado:

```python
{2}
```

Portanto a relação útil torna-se:

```text
Op0 → Op2
```

---

# 49. Cadeia de vários ignorados

Também funciona com:

```text
Op0
 ↓
Op1 ignorado
 ↓
Op2 ignorado
 ↓
Op3 ignorado
 ↓
Op4 útil
```

Resultado:

```text
Op0 → Op4
```

---

# 50. Ramificações

Considere:

```text
            ┌→ Op2 ignorado → Op4
Op0 → Op1 ──┤
            └→ Op3 ignorado → Op5
```

A função pode retornar:

```python
{
    4,
    5,
}
```

permitindo preservar bifurcações.

---

# 51. `prev_useful_to()`

A segunda função interna:

```python
def prev_useful_to(op_idx):
```

faz a mesma operação na direção oposta.

Ela utiliza:

```python
backward
```

em vez de:

```python
forward
```

---

# 52. Objetivo

A pergunta respondida é:

```text
quais são os operadores úteis imediatamente anteriores?
```

atravessando operadores ignorados.

---

# 53. Exemplo

```text
Op0 útil
 ↓
Op1 ignorado
 ↓
Op2 útil
```

Então:

```python
prev_useful_to(2)
```

retorna:

```python
{0}
```

---

# 54. Relações úteis finais

Depois são construídos:

```python
useful_inputs = {
    op_idx: prev_useful_to(
        op_idx
    )
    for op_idx in useful
}
```

e:

```python
useful_outputs = {
    op_idx: next_useful_from(
        op_idx
    )
    for op_idx in useful
}
```

---

# 55. Significado de `useful_inputs`

Para uma operação:

```text
Op 10
```

poderíamos ter:

```python
useful_inputs[10] = {
    6,
    9,
}
```

Isso significa:

```text
Op6 ─┐
     ├→ Op10
Op9 ─┘
```

Esse tipo de situação ocorre, por exemplo, em operações com múltiplas entradas como `ADD`.

---

# 56. Significado de `useful_outputs`

Poderíamos ter:

```python
useful_outputs[10] = {
    11,
    15,
}
```

Representando:

```text
          ┌→ Op11
Op10 ─────┤
          └→ Op15
```

---

# 57. Retorno da segunda fase

A função retorna:

```python
return (
    useful,
    useful_inputs,
    useful_outputs,
)
```

Neste ponto o grafo já está representado diretamente entre operadores úteis.

---

# 58. Antes e depois da normalização

Antes:

```text
Op A
 ↓
Tensor X
 ↓
Op B
 ↓
Tensor Y
 ↓
Op C
```

Depois:

```text
Op A
 ↓
Op B
 ↓
Op C
```

Com ignorados:

```text
ANTES

Op A
 ↓
Tensor X
 ↓
Op B ignorado
 ↓
Tensor Y
 ↓
Op C


DEPOIS

Op A
 ↓
Op C
```

---

# 59. Terceira fase: ordenação topológica

A função:

```python
def topo_order(
    nodes,
    in_edges,
    out_edges,
):
```

calcula uma ordem válida para processar o grafo.

---

# 60. O que é uma ordenação topológica?

Em um grafo acíclico direcionado, uma ordenação topológica garante:

```text
se A precisa executar antes de B

A aparece antes de B
```

Exemplo:

```text
L0
 ↓
L1
 ↓
L2
```

ordem válida:

```text
L0, L1, L2
```

ordem inválida:

```text
L2, L0, L1
```

porque L2 depende de dados anteriores.

---

# 61. Exemplo com ramificação

```text
       L0
      /  \
     ↓    ↓
    L1    L2
      \  /
       ↓
       L3
```

Uma ordem possível é:

```text
L0
L1
L2
L3
```

Outra também poderia ser:

```text
L0
L2
L1
L3
```

porque L1 e L2 são independentes entre si.

---

# 62. `indegree`

O algoritmo começa calculando:

```python
indegree = {
    node: len(
        in_edges[node]
    )
    for node in nodes
}
```

O indegree representa:

```text
quantos predecessores ainda precisam ser processados
```

---

# 63. Exemplo de indegree

No grafo:

```text
       A
      / \
     ↓   ↓
     B   C
      \ /
       ↓
       D
```

temos:

```text
A = 0
B = 1
C = 1
D = 2
```

---

# 64. Fila inicial

O código:

```python
queue = deque(
    sorted(
        node
        for node in nodes
        if indegree[node] == 0
    )
)
```

coloca inicialmente na fila apenas nós que não possuem predecessores.

No exemplo:

```text
queue = [A]
```

---

# 65. Por que `sorted()`?

Pode haver mais de um nó sem dependências.

O uso de:

```python
sorted(...)
```

produz um comportamento determinístico.

Sem isso, a ordem poderia variar dependendo da ordem interna de conjuntos ou dicionários.

---

# 66. Processamento da fila

O loop principal:

```python
while queue:
```

remove:

```python
current = queue.popleft()
```

e adiciona:

```python
order.append(current)
```

---

# 67. Liberando dependências

Para cada sucessor:

```python
for destination in sorted(
    out_edges[current]
):
```

é decrementado:

```python
indegree[
    destination
] -= 1
```

Isso representa:

```text
uma dependência deste nó já foi resolvida
```

---

# 68. Quando um nó entra na fila?

Quando:

```python
indegree[
    destination
] == 0
```

ele pode ser executado.

Então:

```python
queue.append(
    destination
)
```

---

# 69. Exemplo passo a passo

Considere:

```text
A → B
A → C
B → D
C → D
```

Inicialmente:

```text
A=0
B=1
C=1
D=2
```

Fila:

```text
[A]
```

Processa A:

```text
B=0
C=0
```

Fila:

```text
[B,C]
```

Processa B:

```text
D=1
```

Processa C:

```text
D=0
```

D entra na fila.

Resultado:

```text
A,B,C,D
```

---

# 70. Detecção de ciclos

Depois do algoritmo:

```python
if len(order) != len(nodes):
```

significa que algum nó nunca conseguiu chegar a indegree zero.

Isso indica ciclo.

Exemplo:

```text
A → B
↑   ↓
└── C
```

Nesse caso não existe uma ordem topológica válida.

---

# 71. Exceção

O código lança:

```python
raise RuntimeError(
    "Grafo possui ciclo "
    "(inesperado para TFLite)."
)
```

A intenção é falhar cedo.

O restante do extrator pressupõe um fluxo acíclico de operações.

---

# 72. Quarta fase: `build_layers()`

Depois de descobrir as dependências e a ordem, o módulo cria uma representação mais conveniente para o restante do pipeline.

A função é:

```python
def build_layers(
    op_types,
    useful,
    useful_inputs,
    useful_outputs,
    order,
):
```

---

# 73. Objetivo de `build_layers()`

Ela converte:

```text
índices de operadores TFLite
```

em estruturas como:

```python
{
    "type": "ADD",
    "name": "L10",
    "above": ["L6", "L9"],
    "below": ["L11"],
    "op_index": 10,
}
```

---

# 74. Diferença entre `op_index` e `name`

Essa distinção é fundamental.

`op_index` é o índice original do operador no arquivo TFLite.

Exemplo:

```text
op_index = 37
```

Já:

```text
name = "L34"
```

é um identificador criado pelo extrator para a representação lógica.

Portanto:

```text
op_index
    ↓
identidade original no TFLite

name
    ↓
identidade usada pelo grafo do extrator
```

---

# 75. Criação de `new_label`

O código:

```python
new_label = {
    old_idx: f"L{i}"
    for i, old_idx
    in enumerate(useful)
}
```

cria o mapeamento:

```text
índice TFLite → label lógico
```

Exemplo:

```python
useful = [
    0,
    1,
    3,
    4,
]
```

Então:

```python
new_label = {
    0: "L0",
    1: "L1",
    3: "L2",
    4: "L3",
}
```

---

# 76. Por que renumerar?

Se determinadas operações forem ignoradas, os índices TFLite podem possuir lacunas:

```text
0
1
3
4
7
```

A representação lógica pode ficar:

```text
L0
L1
L2
L3
L4
```

Isso torna relatórios e estruturas posteriores mais compactos.

---

# 77. Detalhe importante sobre a numeração

Os labels são criados com:

```python
enumerate(useful)
```

e não com:

```python
enumerate(order)
```

Isso significa que os nomes:

```text
L0
L1
L2
...
```

seguem a ordem dos índices úteis originais do TFLite.

Já:

```python
layers
```

é construída percorrendo:

```python
order
```

ou seja, em ordem topológica.

Na maioria dos modelos em que a ordem original dos operadores já acompanha o fluxo do grafo, esses dois ordenamentos coincidem.

Mas conceitualmente são coisas diferentes:

```text
label
    ↓
baseado na lista useful

posição em layers
    ↓
baseada em order
```

Essa diferença deve ser preservada na interpretação do código.

---

# 78. Construção de `layers`

É criada:

```python
layers = []
```

Depois:

```python
for old_idx in order:
```

cada operação útil é processada na ordem topológica.

---

# 79. Construção de `above`

O código:

```python
above = sorted(
    [
        new_label[producer]
        for producer
        in useful_inputs[old_idx]
        if producer in new_label
    ],
    key=lambda label:
        int(label[1:]),
)
```

converte predecessores de:

```text
índice TFLite
```

para:

```text
labels Lx
```

---

# 80. Exemplo de `above`

Suponha:

```python
useful_inputs[10] = {
    6,
    9,
}
```

e:

```python
new_label = {
    6: "L6",
    9: "L9",
    10: "L10",
}
```

Então:

```python
above = [
    "L6",
    "L9",
]
```

---

# 81. Por que ordenar por número?

Uma ordenação textual comum poderia produzir:

```text
L1
L10
L11
L2
```

porque strings são comparadas caractere a caractere.

Por isso o código utiliza:

```python
key=lambda label:
    int(label[1:])
```

Para:

```text
L10
```

temos:

```python
label[1:]
```

igual a:

```text
"10"
```

e:

```python
int("10")
```

igual a:

```text
10
```

Assim a ordem torna-se numérica.

---

# 82. Construção de `below`

O mesmo processo é aplicado aos consumidores:

```python
below = sorted(
    [
        new_label[consumer]
        for consumer
        in useful_outputs[old_idx]
        if consumer in new_label
    ],
    key=lambda label:
        int(label[1:]),
)
```

Exemplo:

```text
L10
 ├→ L11
 └→ L15
```

gera:

```python
below = [
    "L11",
    "L15",
]
```

---

# 83. Estrutura de uma layer

Depois:

```python
layers.append(
    {
        "type": op_types[
            old_idx
        ],
        "name": new_label[
            old_idx
        ],
        "above": above,
        "below": below,
        "op_index": old_idx,
    }
)
```

Cada entrada possui cinco propriedades.

---

# 84. Campo `type`

Exemplo:

```python
"type": "CONV_2D"
```

Indica o tipo TFLite da operação.

---

# 85. Campo `name`

Exemplo:

```python
"name": "L15"
```

É o identificador lógico criado pelo extrator.

---

# 86. Campo `above`

Exemplo:

```python
"above": [
    "L12",
    "L14",
]
```

Lista as camadas das quais esta operação depende diretamente.

---

# 87. Campo `below`

Exemplo:

```python
"below": [
    "L16",
]
```

Lista as operações que dependem diretamente da saída atual.

---

# 88. Campo `op_index`

Exemplo:

```python
"op_index": 18
```

Preserva o vínculo com o operador original do TFLite.

Isso é essencial porque etapas posteriores precisam voltar ao:

```python
subgraph.Operators(
    op_index
)
```

para extrair parâmetros reais.

---

# 89. Exemplo de residual block

Uma estrutura como:

```text
L5 ───────────────┐
 ↓                │
L6                │
 ↓                │
L7                │
 ↓                │
L8 ───────────────┤
                  ↓
                 L9 ADD
```

pode gerar para `L9`:

```python
{
    "type": "ADD",
    "name": "L9",
    "above": [
        "L5",
        "L8",
    ],
    "below": [
        "L10",
    ],
    "op_index": ...,
}
```

Essa informação será especialmente importante para a alocação de memória.

---

# 90. Retorno de `build_layers()`

A função retorna:

```python
return (
    layers,
    new_label,
)
```

São mantidas tanto a representação completa quanto a tabela de conversão de índices.

---

# 91. Quinta fase: `graph_to_text()`

A função:

```python
def graph_to_text(
    layers
):
```

não participa dos cálculos posteriores.

Ela existe para transformar a estrutura em texto legível para relatório.

Essa separação é importante.

---

# 92. Estrutura versus relatório

O pipeline utiliza:

```python
layers
```

para cálculos.

Já:

```python
graph_to_text(
    layers
)
```

produz apenas uma visualização textual.

Portanto:

```text
layers
    ↓
fonte estruturada

data
    ↓
representação humana
```

O código não lê o relatório novamente para reconstruir o grafo.

---

# 93. Cabeçalho

O relatório começa com:

```text
nome_da_camada; camada_atual; camada_acima; camada_de_baixo
```

Apesar do nome histórico `nome_da_camada`, o primeiro campo corresponde atualmente a:

```python
layer["type"]
```

como:

```text
CONV_2D
ADD
SOFTMAX
```

---

# 94. Conversão de `above`

Se existirem predecessores:

```python
[
    "L5",
    "L8",
]
```

o texto será:

```text
[L5, L8]
```

Se não existirem:

```text
[]
```

---

# 95. Conversão de `below`

O mesmo ocorre com as saídas:

```text
[L10]
```

ou:

```text
[]
```

---

# 96. Linha final

A linha é construída como:

```python
f"{layer['type']}; "
f"{layer['name']}; "
f"{above}; "
f"{below}"
```

Exemplo:

```text
ADD; L9; [L5, L8]; [L10]
```

---

# 97. Exemplo de relatório

Poderíamos ter:

```text
nome_da_camada; camada_atual; camada_acima; camada_de_baixo
QUANTIZE; L0; []; [L1]
CONV_2D; L1; [L0]; [L2]
DEPTHWISE_CONV_2D; L2; [L1]; [L3]
CONV_2D; L3; [L2]; [L4, L6]
ADD; L6; [L3, L5]; [L7]
```

Essa representação é útil para inspeção humana.

---

# 98. Sexta fase: `build_graph()`

A função:

```python
def build_graph(
    model,
    subgraph,
    ignored_types=None,
):
```

é a função pública que coordena todas as etapas anteriores.

Ela evita que `main.py` precise conhecer os detalhes internos.

---

# 99. Orquestração

O fluxo interno é:

```text
build_graph_for_subgraph()
          │
          ▼
compute_useful_adjacency()
          │
          ▼
topo_order()
          │
          ▼
build_layers()
          │
          ▼
graph_to_text()
```

---

# 100. Primeira chamada

```python
(
    op_types,
    producer_by_tensor,
    consumers_by_tensor,
) = build_graph_for_subgraph(
    model,
    subgraph,
)
```

Resultado:

```text
operadores + relações via tensors
```

---

# 101. Segunda chamada

```python
(
    useful,
    useful_inputs,
    useful_outputs,
) = compute_useful_adjacency(...)
```

Resultado:

```text
grafo lógico entre operadores úteis
```

---

# 102. Terceira chamada

```python
order = topo_order(...)
```

Resultado:

```text
ordem válida de processamento
```

---

# 103. Quarta chamada

```python
layers, new_label = (
    build_layers(...)
)
```

Resultado:

```text
estrutura de camadas Lx
```

---

# 104. Quinta chamada

```python
data = graph_to_text(
    layers
)
```

Resultado:

```text
representação para relatório
```

---

# 105. `old_idx_to_label`

Depois é criado:

```python
old_idx_to_label = {
    old_idx: label
    for old_idx, label
    in new_label.items()
}
```

Na prática, isso contém o mesmo sentido de:

```python
new_label
```

Ou seja:

```text
índice original → label
```

---

# 106. Exemplo

```python
old_idx_to_label = {
    0: "L0",
    1: "L1",
    3: "L2",
}
```

Isso permite:

```python
old_idx_to_label[3]
```

obter:

```text
L2
```

---

# 107. `label_to_op_idx`

Depois é construída a relação inversa:

```python
label_to_op_idx = {
    label: old_idx
    for old_idx, label
    in new_label.items()
}
```

Exemplo:

```python
{
    "L0": 0,
    "L1": 1,
    "L2": 3,
}
```

Agora:

```python
label_to_op_idx[
    "L2"
]
```

retorna:

```text
3
```

---

# 108. Por que manter as duas direções?

Módulos diferentes usam identificadores diferentes.

Algumas estruturas trabalham com:

```text
L17
```

Enquanto a API TFLite exige:

```text
op_index
```

Assim:

```text
L17
 ↓
label_to_op_idx
 ↓
op_index
 ↓
subgraph.Operators(op_index)
```

No sentido inverso:

```text
op_index
 ↓
old_idx_to_label
 ↓
L17
```

---

# 109. Dicionário final

`build_graph()` retorna:

```python
{
    "op_types": ...,
    "producer_by_tensor": ...,
    "consumers_by_tensor": ...,
    "useful": ...,
    "useful_inputs": ...,
    "useful_outputs": ...,
    "order": ...,
    "new_label": ...,
    "old_idx_to_label": ...,
    "label_to_op_idx": ...,
    "layers": ...,
    "data": ...,
}
```

Isso cria uma interface única para os módulos posteriores.

---

# 110. Significado de cada item

| Campo                 | Significado                          |
| --------------------- | ------------------------------------ |
| `op_types`            | Tipo de cada operador TFLite         |
| `producer_by_tensor`  | Operador que produz cada tensor      |
| `consumers_by_tensor` | Operadores que consomem cada tensor  |
| `useful`              | Índices de operadores não ignorados  |
| `useful_inputs`       | Predecessores úteis de cada operador |
| `useful_outputs`      | Sucessores úteis de cada operador    |
| `order`               | Ordenação topológica                 |
| `new_label`           | Mapeamento `op_index → Lx`           |
| `old_idx_to_label`    | Mapeamento explícito `op_index → Lx` |
| `label_to_op_idx`     | Mapeamento `Lx → op_index`           |
| `layers`              | Representação estruturada do grafo   |
| `data`                | Representação textual para relatório |

---

# 111. `producer_by_tensor` ainda é importante

Embora `compute_useful_adjacency()` construa a relação `forward` usando principalmente:

```python
consumers_by_tensor
```

o mapa:

```python
producer_by_tensor
```

continua sendo mantido.

Ele é uma informação estrutural útil para etapas que precisem responder:

```text
quem produziu este tensor?
```

Isso é diferente de perguntar:

```text
quem consome este tensor?
```

---

# 112. Exemplo completo de transformação

Imagine:

```text
Op0: QUANTIZE
 output tensor 10

Op1: CONV_2D
 input tensor 10
 output tensor 11

Op2: DEPTHWISE_CONV_2D
 input tensor 11
 output tensor 12

Op3: CONV_2D
 input tensor 12
 output tensor 13

Op4: ADD
 inputs tensor 13 e tensor 11
 output tensor 14
```

---

# 113. Producers

```python
producer_by_tensor = {
    10: 0,
    11: 1,
    12: 2,
    13: 3,
    14: 4,
}
```

---

# 114. Consumers

```python
consumers_by_tensor = {
    10: [1],
    11: [2, 4],
    12: [3],
    13: [4],
}
```

---

# 115. Grafo derivado

```text
Op0
 ↓
Op1
 ├───────┐
 ↓       │
Op2      │
 ↓       │
Op3      │
 └──┐    │
    ↓    ↓
      Op4
```

---

# 116. Relações úteis

Para Op4:

```python
useful_inputs[4] = {
    1,
    3,
}
```

Para Op1:

```python
useful_outputs[1] = {
    2,
    4,
}
```

---

# 117. Layers

A representação pode se tornar:

```python
[
    {
        "type": "QUANTIZE",
        "name": "L0",
        "above": [],
        "below": ["L1"],
        "op_index": 0,
    },

    {
        "type": "CONV_2D",
        "name": "L1",
        "above": ["L0"],
        "below": ["L2", "L4"],
        "op_index": 1,
    },

    ...

    {
        "type": "ADD",
        "name": "L4",
        "above": ["L1", "L3"],
        "below": [],
        "op_index": 4,
    },
]
```

---

# 118. Por que o grafo é essencial para a memória

A alocação de slots não pode simplesmente alternar:

```text
slot0
slot1
slot0
slot1
```

porque uma saída antiga pode ainda ser utilizada posteriormente.

No exemplo:

```text
L1
 ├──→ L2 → L3
 └────────→ L4
```

A saída de L1 precisa permanecer disponível até L4.

Então o grafo informa a vida útil lógica desse resultado.

---

# 119. Exemplo de risco

Uma estratégia ingênua poderia fazer:

```text
L1 output → SLOT1
L2 output → SLOT2
L3 output → SLOT1
```

Mas isso destruiria o resultado de L1 antes do `ADD` em L4.

O grafo permite detectar:

```text
L1 ainda possui consumidor futuro
```

Portanto:

```text
SLOT1 ainda não pode ser reutilizado
```

Esse ponto conecta diretamente:

```text
graph.py
```

com:

```text
slots.py
```

---

# 120. Relação com `tensor_mapping.py`

Mais tarde, precisamos relacionar:

```text
tensor TFLite
```

a:

```text
slot de memória
```

Para isso são necessárias informações como:

```text
qual operação produziu este tensor?

qual label corresponde à operação?

qual slot foi atribuído a essa camada?
```

Fluxo:

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
slot_allocation
   ↓
slot
```

---

# 121. Relação com `layer_params.py`

`layer_params.py` também utiliza:

```text
old_idx_to_label
label_to_op_idx
```

para transitar entre:

```text
grafo lógico
```

e:

```text
operador original do TFLite
```

---

# 122. Separação entre grafo e tensors

É importante perceber que o projeto mantém duas representações complementares:

```text
graph.py
    ↓
dependências entre operações
```

e:

```text
tensor_mapping.py
    ↓
relação entre tensors e memória
```

Não é necessário transformar tudo em uma única estrutura gigante.

---

# 123. Por que não utilizar diretamente a ordem TFLite?

O arquivo TFLite possui operadores indexados, mas o extrator não depende apenas da suposição:

```text
op0
op1
op2
op3
```

como ordem semântica suficiente.

Ele reconstrói explicitamente as dependências e calcula:

```python
topo_order(...)
```

Isso torna a relação lógica explícita.

---

# 124. Vantagem para ramificações

Em uma cadeia linear:

```text
L0 → L1 → L2
```

a ordem parece óbvia.

Mas arquiteturas modernas possuem:

```text
        ┌──────────────┐
        │              ↓
L0 → L1 → L2 → L3 → ADD
```

O grafo é necessário para representar corretamente essas dependências.

MobileNetV2 possui justamente estruturas residuais em determinados blocos.

---

# 125. Relação com MobileNetV2

Blocos residuais podem possuir:

```text
entrada
  │
  ├─────────────────────┐
  │                     │
  ▼                     │
Conv                    │
  ↓                     │
Depthwise               │
  ↓                     │
Conv                    │
  │                     │
  └──────────┬──────────┘
             ▼
            ADD
```

Isso significa que uma ativação produzida anteriormente precisa sobreviver por várias camadas.

O grafo permite capturar essa estrutura.

---

# 126. Operadores ignorados e semântica

O suporte a:

```python
ignored_types
```

deve ser utilizado com cuidado.

Ignorar um operador na representação do grafo não significa que ele possa ser removido semanticamente da inferência.

A função apenas permite construir uma adjacência lógica atravessando operadores considerados transparentes para determinado propósito.

Ou seja:

```text
ignorar no grafo
```

não é automaticamente igual a:

```text
remover da execução
```

Essa distinção é importante.

---

# 127. Exemplo

Se tivermos:

```text
CONV
 ↓
RESHAPE
 ↓
CONV
```

e `RESHAPE` for ignorado para um determinado cálculo estrutural:

```text
CONV → CONV
```

isso não demonstra por si só que a operação `RESHAPE` pode ser eliminada da implementação.

A validade depende da semântica concreta dessa operação.

---

# 128. Situação atual

No uso atual do pipeline, `ignored_types` permite preservar essa capacidade de abstração.

A função é genérica, mas o conjunto efetivamente utilizado deve ser decidido conscientemente pelo pipeline.

---

# 129. Complexidade aproximada

A primeira varredura percorre:

```text
todos os operadores
+
todos os inputs
+
todos os outputs
```

Em termos conceituais:

```text
O(V + E)
```

onde:

```text
V = operadores
E = relações entre operadores/tensors
```

A ordenação topológica também opera aproximadamente em:

```text
O(V + E)
```

para um grafo dessa natureza.

Para uma rede como a utilizada neste projeto, esse custo é pequeno em comparação ao processo de inferência propriamente dito.

---

# 130. Estrutura de dados versus formato de relatório

Uma decisão importante da refatoração foi não utilizar mais o texto como estrutura intermediária.

A abordagem ruim seria:

```text
grafo
 ↓
gera texto
 ↓
parseia texto
 ↓
slots.py
```

A abordagem atual é:

```text
grafo
 ↓
layers
 ├────────────→ slots.py
 ├────────────→ tensor_mapping.py
 └────────────→ graph_to_text()
                         ↓
                    relatório
```

Assim:

```python
layers
```

é a fonte de verdade.

---

# 131. Por que isso melhora o projeto?

Porque estruturas Python preservam tipos reais.

Exemplo:

```python
{
    "above": [
        "L6",
        "L9",
    ]
}
```

é uma lista real.

No texto:

```text
[L6, L9]
```

seria necessário fazer parsing novamente.

A estrutura evita:

```text
split()
replace()
regex
conversões de string
```

desnecessárias.

---

# 132. Determinismo

Existem vários pontos em que o código aplica:

```python
sorted(...)
```

Isso é importante para produzir resultados reproduzíveis.

Mesmo que internamente sejam utilizados:

```python
set()
```

o relatório e a ordem processada não dependem da ordem interna arbitrária do conjunto.

---

# 133. Invariantes esperados

Depois de `build_graph()`, algumas condições importantes devem ser verdadeiras.

### Todo nó útil possui entrada em `useful_inputs`

Mesmo que seja:

```python
set()
```

### Todo nó útil possui entrada em `useful_outputs`

Mesmo que seja:

```python
set()
```

### Todo label aponta para um operador

```text
Lx → op_index
```

### Todo operador útil possui label

```text
op_index → Lx
```

### `order` contém exatamente os nós úteis

Caso contrário a ordenação topológica falha.

---

# 134. Nós de entrada do grafo

Um nó com:

```python
useful_inputs[op_idx] == set()
```

é uma raiz no grafo lógico.

Isso não significa necessariamente que ele não possua inputs TFLite.

Ele pode consumir:

```text
entrada externa do modelo
```

que não foi produzida por outro operador.

---

# 135. Nós de saída do grafo

Um nó com:

```python
useful_outputs[op_idx] == set()
```

é uma folha no grafo lógico.

Normalmente corresponde a uma operação cujo resultado:

```text
não é consumido por outra operação útil
```

e pode representar uma saída final do modelo.

---

# 136. Entrada do modelo versus produtor

Considere:

```text
Tensor 0
```

como entrada externa.

Nenhum operador produz esse tensor.

Então:

```text
tensor 0
```

não aparece necessariamente em:

```python
producer_by_tensor
```

mas aparece em:

```python
consumers_by_tensor
```

porque a primeira camada o utiliza.

---

# 137. Exemplo

```text
INPUT TENSOR 0
      │
      ▼
    Op0
      │
      ▼
 Tensor 5
      │
      ▼
    Op1
```

Temos:

```python
consumers_by_tensor[0] = [
    0
]
```

mas não:

```python
producer_by_tensor[0]
```

porque a origem é externa ao grafo de operadores.

---

# 138. Saída final do modelo

Da mesma maneira:

```text
Op67
 ↓
Tensor 100
 ↓
MODEL OUTPUT
```

Pode existir produtor:

```python
producer_by_tensor[100] = 67
```

mas nenhum consumidor operador:

```python
consumers_by_tensor[100]
```

pode estar vazio.

---

# 139. O grafo representa dependência computacional

Isso explica uma distinção importante.

O grafo não representa literalmente:

```text
todos os objetos do arquivo TFLite
```

Ele representa:

```text
dependência computacional entre operadores
```

Por isso:

```text
inputs externos
outputs externos
pesos constantes
bias
```

não precisam aparecer como nós `Lx`.

---

# 140. Grafo de operadores versus grafo completo de dados

Um grafo completo poderia ser bipartido:

```text
Operator
   ↓
Tensor
   ↓
Operator
   ↓
Tensor
```

O extrator simplifica para:

```text
Operator
   ↓
Operator
```

porque essa é a representação necessária para:

```text
ordem
liveness
slots
execução
```

---

# 141. O que este módulo deliberadamente não faz

`graph.py` não:

```text
extrai pesos
extrai bias
calcula quantização
calcula padding
calcula endereços
aloca bytes
gera LayerParams
serializa estruturas
gera WAT
```

Também não deveria conhecer detalhes de:

```text
ESP32
WAMR
WebAssembly
```

Seu problema é puramente estrutural:

```text
quem depende de quem?
```

---

# 142. Fronteira arquitetural

Podemos representar:

```text
TFLite
  │
  ▼
model_loader.py
  │
  ▼
tflite_utils.py
  │
  ▼
graph.py
  │
  ▼
grafo lógico
```

Depois:

```text
grafo lógico
  │
  ├──→ slots.py
  ├──→ tensor_mapping.py
  └──→ layer_params.py
```

---

# 143. Funções do módulo

| Função                       | Responsabilidade                                      |
| ---------------------------- | ----------------------------------------------------- |
| `build_graph_for_subgraph()` | Descobrir tipos, produtores e consumidores            |
| `compute_useful_adjacency()` | Construir dependências diretas entre operadores úteis |
| `topo_order()`               | Calcular uma ordenação topológica                     |
| `build_layers()`             | Criar representação estruturada `Lx`                  |
| `graph_to_text()`            | Converter estrutura para relatório                    |
| `build_graph()`              | Orquestrar todo o processo                            |

---

# 144. Estruturas produzidas

| Estrutura             | Exemplo                   |
| --------------------- | ------------------------- |
| `op_types`            | `["CONV_2D", "ADD", ...]` |
| `producer_by_tensor`  | `{10: 3}`                 |
| `consumers_by_tensor` | `{10: [4, 7]}`            |
| `useful`              | `[0, 1, 2, ...]`          |
| `useful_inputs`       | `{10: {6,9}}`             |
| `useful_outputs`      | `{10: {11}}`              |
| `order`               | `[0,1,2,...]`             |
| `new_label`           | `{10: "L8"}`              |
| `layers`              | lista de dicionários      |
| `data`                | texto do relatório        |

---

# 145. Visão completa da transformação

```text
                   TFLITE SUBGRAPH
                         │
                         ▼
              Operators + Tensors
                         │
                         ▼
          build_graph_for_subgraph()
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
      op_types       producers      consumers
                         │
                         ▼
          compute_useful_adjacency()
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
   useful_inputs                useful_outputs
          │                             │
          └──────────────┬──────────────┘
                         ▼
                   topo_order()
                         │
                         ▼
                 ordem topológica
                         │
                         ▼
                  build_layers()
                         │
                         ▼
                    layers
                         │
               ┌─────────┴─────────┐
               ▼                   ▼
       módulos seguintes     graph_to_text()
               │                   │
               ▼                   ▼
        alocação/memória       relatório
```

---

# 146. Relação com a execução final

Esse arquivo não executa inferência, mas sua saída influencia diretamente o runtime.

O encadeamento completo é:

```text
graph.py
   │
   ▼
dependências
   │
   ▼
slots.py
   │
   ▼
quem ocupa qual região
   │
   ▼
tensor_mapping.py
   │
   ▼
tensor → slot
   │
   ▼
layer_params.py
   │
   ▼
in_ptr / out_ptr
   │
   ▼
params_blob
   │
   ▼
WAT
   │
   ▼
WASM
```

Portanto um erro no grafo pode eventualmente produzir:

```text
slot incorreto
        ↓
ponteiro incorreto
        ↓
sobrescrita de tensor ainda vivo
        ↓
inferência incorreta
```

Isso demonstra por que essa etapa, apesar de não realizar cálculos neurais, é estruturalmente crítica.

---

# 147. Resumo conceitual

O `graph.py` responde essencialmente a quatro perguntas.

## 1. Quem produz cada tensor?

```text
tensor
  ↓
producer_by_tensor
  ↓
operador
```

## 2. Quem consome cada tensor?

```text
tensor
  ↓
consumers_by_tensor
  ↓
operadores
```

## 3. Quem depende de quem?

```text
operador
  ↓
useful_inputs / useful_outputs
  ↓
operadores relacionados
```

## 4. Em que ordem as operações podem ser processadas?

```text
grafo
  ↓
topo_order()
  ↓
ordem topológica
```

---

# 148. Papel no desenho geral do extrator

Até este ponto, o pipeline possui quatro níveis bem definidos:

```text
┌────────────────────────────────┐
│           config.py            │
│                                │
│ define entradas e políticas    │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       model_loader.py          │
│                                │
│ arquivo → Model → SubGraph     │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       tflite_utils.py          │
│                                │
│ interpreta e normaliza         │
│ estruturas TFLite              │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│           graph.py             │
│                                │
│ reconstrói dependências        │
│ entre operações                │
└───────────────┬────────────────┘
                │
                ▼
┌────────────────────────────────┐
│       engenharia de memória    │
│                                │
│ slots                          │
│ tensors                        │
│ parâmetros                     │
│ serialização                   │
└────────────────────────────────┘
```

A principal transformação introduzida por `graph.py` é:

```text
estrutura TFLite orientada a tensors

              ↓

grafo lógico orientado a operações
```

Essa representação intermediária será a base para decidir como os resultados intermediários da rede podem compartilhar a memória limitada disponibilizada pelos três slots do runtime.
