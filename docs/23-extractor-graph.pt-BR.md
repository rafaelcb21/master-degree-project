[English](23-extractor-graph.md) | [Português (Brasil)](23-extractor-graph.pt-BR.md)

# 23 — Grafo de operadores e ordenação

[Índice](README.pt-BR.md) · Fonte: [extractor/graph.py](../extractor/graph.py)

## Contrato de entrada e posição

Recebe model/subgraph do binding. Produz dependências entre operadores para `allocate_slots` e mapas de produtores para `tensor_mapping`. Não lê testes nem conhece a sintética: essa operação é adicionada depois. `ignored_types` existe na API, mas o pipeline não o fornece; por default nenhum tipo é ignorado.

## Fases e funções

1. `build_graph_for_subgraph` percorre todos os operadores, obtém seu nome, associa cada output não negativo a um produtor e acrescenta cada input não negativo à lista de consumidores. Retorna `(op_types,producer_by_tensor,consumers_by_tensor)`. Um produtor posterior para o mesmo tensor sobrescreve o anterior; não há validação de unicidade.
2. `compute_useful_adjacency` monta `forward` como conjuntos de consumidores por operador, removendo autoarestas, e `backward` como inverso. Separa índices ignorados por tipo. As funções internas `next_useful_from` e `prev_useful_to` usam pilha e `seen` para atravessar operadores ignorados e encontrar os primeiros úteis em cada direção. Retorna úteis e suas arestas. A busca não executa nem reproduz semanticamente uma operação ignorada.
3. `topo_order` implementa Kahn: indegree por nó, fila inicial ordenada, retirada da esquerda, destinos ordenados, inclusão quando indegree chega a zero. Se quantidade produzida diverge de `nodes`, levanta `RuntimeError` por ciclo.
4. `build_layers` cria nomes `L0,L1,...` enumerando a lista `useful` (ordem original), mas entrega a lista `layers` na ordem topológica. Cada dict contém `type,name,above,below,op_index`; vizinhos são ordenados pelo número do label.
5. `graph_to_text` emite cabeçalho e uma linha `tipo; label; [acima]; [abaixo]`. A primeira coluna chama-se `nome_da_camada` no cabeçalho, mas recebe o tipo da operação.
6. `build_graph` compõe essas funções e retorna todas as estruturas: tipos, produtores, consumidores, úteis, adjacências, `order`, `new_label`, dois mapas inversos de labels, `layers` e texto `data`.

```text
tensor T0 ──► CONV A ──► tensor T1 ──┬──► CONV B ──► T2 ──┐
                                    │                    ▼
                                    └──────────────────► ADD C

producer_by_tensor: T1 → A, T2 → B
consumers_by_tensor: T1 → [B,C], T2 → [C]
arestas úteis: A → B, A → C, B → C
ordem possível: A, B, C
```

Entram relações de leitura/escrita do FlatBuffer. `graph.py` transforma dependências de tensores em dependências de operadores; sai uma ordem e uma representação adequada à contagem de leitores. IDs e tipos são específicos; o algoritmo de grafo é genérico. Constantes também aparecem nas listas de inputs, mas sem produtor interno não criam arestas por si sós.

## Invariantes e limitações

Todo nó útil tem conjuntos de entrada/saída, e os mapas de labels são inversos. Um nó sem predecessor computacional recebe entrada lógica SLOT0 no alocador, hipótese que merece revisão para grafos com múltiplas raízes independentes. Não há poda por alcançabilidade até outputs: “útil” significa apenas “não ignorado”. Operações desconectadas podem continuar na lista.

As arestas usam sets: várias leituras do mesmo produtor por um consumidor resultam em uma dependência de operador, não necessariamente uma contagem por tensor. Isso importa para grafos com múltiplas saídas ou inputs repetidos. O label Lk não é garantidamente igual ao op_index quando há tipos ignorados. O runtime serializa operadores na ordem original, portanto ordenação topológica do relatório não determina sozinha a ordem final de execução.

Sem ignorados, a construção é próxima de O(operadores + referências + arestas), além de ordenações. Com cadeias ignoradas, buscas repetidas por nó podem revisitar partes do grafo; não há cache dessas travessias. O relatório 02 é diagnóstico e não é relido para controlar a execução.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from collections import defaultdict, deque
from extractor.tflite_utils import op_name
```

### `build_graph_for_subgraph` — assinatura

```python
def build_graph_for_subgraph(model, subgraph)
```

### `compute_useful_adjacency` — assinatura

```python
def compute_useful_adjacency(subgraph, op_types, consumers_by_tensor, ignored_types=None)
```

### `topo_order` — assinatura

```python
def topo_order(nodes, in_edges, out_edges)
```

### `build_layers` — assinatura

```python
def build_layers(op_types, useful, useful_inputs, useful_outputs, order)
```

### `graph_to_text` — assinatura

```python
def graph_to_text(layers)
```

### `build_graph` — assinatura

```python
def build_graph(model, subgraph, ignored_types=None)
```

## Material técnico preservado

A explicação anterior está em [04-graph.md](historico/04-grafo.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
