[English](25-extractor-tensor-mapping.md) | [Português (Brasil)](25-extractor-tensor-mapping.pt-BR.md)

# 25 — Mapeamento de tensores para slots

[Índice](README.pt-BR.md) · Fonte: [extractor/tensor_mapping.py](../extractor/tensor_mapping.py)

## Entrada, saída e consumidores

O módulo cruza IDs TFLite com labels do grafo e alocação lógica. `build_tensor_slot_mapping` retorna `tensor_to_slot`, `graph_inputs`, `mapped_from_layers`, `graph_input_mappings`, `pending_before_resolution`, `unmapped_after`. O pipeline valida e relata esse mapa; o conjunto `graph_inputs` participa do mapa runtime com shift, mas esse último é reconstruído em `layer_params.py`, não uma simples mutação do mapa validado.

## Construção em três passagens

Primeiro, percorre cada registro de alocação, obtém `op_idx` por `label_to_op_idx` e associa todos os outputs não negativos ao `output_slot`. Depois, percorre tensores ainda não mapeados, ignora constantes e atribui slot 0 às entradas declaradas do subgrafo; os demais entram nas pendências. Na terceira passagem, tenta resolver cada não constante restante por sua cadeia de produtores. Por fim enumera os ainda ausentes, sem levantar erro nesse próprio método.

`resolve_slot_from_producer` usa `visiting` para impedir ciclos; retorna None se revisitar um tensor ou não houver produtor. Se o tensor já tem mapa, retorna o slot. Se seu produtor possui label e saída alocada, grava esse slot. Caso contrário, segue recursivamente os inputs não negativos e não constantes do produtor, usando cópia do conjunto de visita por ramo; o primeiro slot encontrado é propagado ao tensor de saída. A função modifica `tensor_to_slot` como cache.

```text
allocation: L7 → SLOT2
          │
          ▼
label_to_op_idx[L7] → operador original
          │
          ▼
outputs: tensor 42, tensor 43
          │
          ├──► tensor_to_slot[42] = 2
          └──► tensor_to_slot[43] = 2

tensor pendente → produtor sem label → input não constante
                                              │
                                              ▼
                                     resolver slot recursivamente
```

Entram registros de alocação e ligações de tensores. O módulo associa IDs a armazenamento e tenta fechar lacunas. Sai o mapa lógico. IDs/labels são dados do modelo; a política de resolução é compartilhada. A associação de múltiplos outputs ao mesmo slot e a propagação pelo primeiro input são hipóteses, não implementação de kernels de transformação.

## Validação

`validate_tensor_slot_mapping` percorre somente operadores presentes em `old_idx_to_label`. Para entradas, ignora IDs negativos e constantes; exige todos os demais mapeados. Para saídas, ignora apenas IDs negativos e exige presença no mapa. Falhas levantam `RuntimeError` com `[MAP-ERROR]`, direção, op_index, tensor_id e nome de operação. Retorna True se passar.

Não valida que cada índice de slot esteja na faixa, que haja capacidade física, que duas entradas vivas não colidam nem que os ponteiros resultantes sejam os corretos. Isso é tratado parcialmente em etapas seguintes; completar o dicionário não prova liveness.

## Relatório

`tensor_mapping_to_text` lista associações vindas de layers, inputs, pendências iniciais e resumo de fechamento. Não imprime necessariamente todas as resoluções recursivas individualmente; a quantidade total reflete o dicionário final. O relatório 04 descreve slots lógicos antes do deslocamento sintético. Para conferir os endereços realmente usados, compare 09 e 10.

## Armadilhas

Ignorar um operador no grafo e herdar o slot de sua entrada só é semanticamente válido quando a transformação pode realmente ser tratada como alias naquele layout. O código não prova essa condição. `runtime_mapping` não reutiliza essa busca recursiva; modelos dependentes de aliases resolvidos apenas aqui podem falhar ou divergir mais adiante. Nos manifests atuais não há configuração para ignorar operadores.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from extractor.tflite_utils import is_constant_tensor, op_name
```

### `resolve_slot_from_producer` — assinatura

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
)
```

### `build_tensor_slot_mapping` — assinatura

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
)
```

### `validate_tensor_slot_mapping` — assinatura

```python
def validate_tensor_slot_mapping(model, subgraph, *, tensor_to_slot, old_idx_to_label)
```

### `tensor_mapping_to_text` — assinatura

```python
def tensor_mapping_to_text(mapping)
```

## Material técnico preservado

A explicação anterior está em [06-tensor-slot-mapping.md](historico/06-mapeamento-tensor-slot.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
