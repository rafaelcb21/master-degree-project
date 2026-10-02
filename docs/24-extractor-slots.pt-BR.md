[English](24-extractor-slots.md) | [Português (Brasil)](24-extractor-slots.pt-BR.md)

# 24 — Alocação de slots e vida útil

[Índice](README.pt-BR.md) · Fonte: [extractor/slots.py](../extractor/slots.py)

## Objetivo e contrato

`allocate_slots(layers,num_slots)` recebe a lista de dicts do grafo em ordem topológica e devolve `(allocation,layer_output_slot)`. O primeiro contém `layer,type,input_slots,output_slot,in_place`; o segundo associa nome de layer ao slot lógico. Não há endereços nem bytes aqui. O pipeline fornece três slots, mas a função isolada não valida positividade de `num_slots`.

## Estado e algoritmo exato

`layer_output_slot` lembra onde ficou a saída de cada camada. `slot_readers_count` conta consumidores ainda pendentes por slot. `next_slot` começa em 1 e define uma preferência de rotação; não significa que a alternância seja suficiente para preservar residuais.

Para cada camada normal: sem predecessores, usa input `[0]` e reseta preferência para 1; com predecessores, consulta os slots de suas saídas. Monta todos os índices `[0,num_slots)`, excluindo slots com contagem positiva. Se não sobrar nenhum, lança `RuntimeError("Sem slots livres em ...")`. Escolhe `next_slot` se livre, senão o menor índice livre. Só então decrementa os leitores dos inputs e remove entradas que chegam a zero. Registra o número de consumidores de saída quando `below` não é vazio; acrescenta o registro e avança preferência circular.

A seleção ocorre **antes** de liberar inputs consumidos nessa própria operação. Portanto a função pode exigir um slot adicional mesmo quando um planejamento mais agressivo permitiria escrever sobre uma entrada. Ela não verifica individualmente se o kernel suporta overlap.

```text
Layer A → SLOT1 ───────────────────────────┐
             │                            │ atalho residual
             ▼                            │
Layer B → SLOT2                            │
             │                            │
             └──────────┬─────────────────┘
                        ▼
                       ADD
                        ▼
                      SLOT0

slot ocupado
     │
     ▼
ainda existem consumidores pendentes?
     │
  ┌──┴───────────┐
  ▼              ▼
 sim            não
  │              │
mantém       volta a ser candidato
```

Entra a dependência A→B→ADD com A também consumido por ADD. O alocador mantém SLOT1 até o atalho ser lido e escolhe SLOT0 para a saída. Saem slots reutilizáveis, não cópias de tensores. O padrão residual depende do grafo; contagem de leitores e escolha de área são genéricas. O exemplo é ilustrativo do algoritmo, não a transcrição de uma layer específica dos modelos.

## Exceção QUANTIZE

Para QUANTIZE, a função toma SLOT0 se não houver predecessor, senão o slot do primeiro predecessor. Define o mesmo slot de saída, marca `in_place=True` e executa `continue`. Esse ramo **não atualiza** `slot_readers_count`, não decrementa leituras e não avança `next_slot`. Funciona nos caminhos observados de entrada/saída, mas não constitui um algoritmo geral de liveness para QUANTIZE no meio de ramificações. Não trate essa simplificação como otimização formalmente segura para qualquer grafo.

## Formatação, erros e invariantes

`slot_allocation_to_text` recebe a lista, imprime tipo e label com `[inputs -> output]`, usa ` e ` para vários inputs e acrescenta `(in-place)` quando indicado. Retorna string; não modifica a alocação. IDs de predecessor ausentes causam `KeyError`; ausência de slot causa `RuntimeError`; não existe spill para uma quarta área ou realocação automática.

Um slot é uma área de capacidade uniforme calculada posteriormente pelo maior tensor, não uma variável de dimensão fixa no grafo. O mesmo slot pode conter shapes diferentes em momentos diferentes. A contagem por consumidores de operador pressupõe que o grafo represente adequadamente o tempo de vida dos valores. Sem essa hipótese, um mapa tensor→slot completo ainda pode estar numericamente incorreto.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python

```

### `allocate_slots` — assinatura

```python
def allocate_slots(layers, num_slots)
```

### `slot_allocation_to_text` — assinatura

```python
def slot_allocation_to_text(allocation)
```

## Material técnico preservado

A explicação anterior está em [05-slot-allocation.md](historico/05-alocacao-slots.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
