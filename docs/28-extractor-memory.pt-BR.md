[English](28-extractor-memory.md) | [Português (Brasil)](28-extractor-memory.pt-BR.md)

# 28 — Planejamento físico da memória

[Índice](README.pt-BR.md) · Fonte: [extractor/memory.py](../extractor/memory.py)

## Separação de responsabilidades

Este módulo dimensiona slots, posiciona blobs e calcula páginas; não aloca memória Wasmtime nem escreve WAT. Recebe arrays/bytes e metadados do TFLite. O trecho que reserva LayerParams e posiciona os slots está em `calculate_layer_memory_layout`, em `layer_params.py`; ambos são necessários para entender o layout final.

## Contagem e alinhamento

`tensor_numel(shape,batch=1)` multiplica dimensões, substituindo cada dimensão negativa por batch. Shape vazio produz produto 1, embora `calculate_slot_bytes` pule shapes vazios. Dimensão zero produz zero. Isso não resolve semântica de shapes dinâmicos; é uma política local de estimativa.

`align_up(value,alignment=16)` implementa `(value + alignment - 1) & ~(alignment - 1)`. Requer potência de dois positiva, sem validar. Exemplo: 414824 alinhado a 16 resulta em 414832, criando oito bytes de intervalo. Não confunda padding de memória com padding espacial de convolução.

## calculate_slot_bytes

Percorre todos os tensores do subgrafo, pula constantes, shapes vazios e tipos sem `BYTES_PER_TYPE`. Calcula `num_elements × bytes_per_element`, registra ID, nome, shape, tipo, bytes/elemento, elementos e bytes. Mantém o primeiro máximo estrito encontrado. Retorna `max_bytes,slot_bytes,alignment,batch,max_tensor,tensor_records`, com `slot_bytes=align_up(max_bytes,alignment)`.

O tamanho usa todos os tensores não constantes reconhecidos, não somente os vivos de uma etapa. Os três slots têm a mesma capacidade. Não inclui workspace adicional de kernels externos, não conta constantes nessa capacidade e não implementa tamanhos diferentes por slot. O buffer RGB565 host é menor que RGB888 e ainda é verificado pelo runner contra o slot.

## calculate_parameter_layout

Recebe hint, alinhamento e cinco blobs de dados: pesos, bias e três arrays de quantização (PARAMS é reservado posteriormente). Define WEIGHTS em `align_up(hint)`, BIAS depois dos pesos alinhado, MUL depois do bias, SHIFT depois de MUL, Q6 depois de SHIFT e PARAMS depois de Q6. Retorna bases e comprimentos das cinco regiões anteriores a PARAMS, `params_base`, alignment e hint. Não recebe o tamanho dos LayerParams nessa fase.

```text
endereço baixo
      ▼
┌────────────────────────────────┐
│ reservado [0,2048)             │ formato em 0; busy flag em 4
├────────────────────────────────┤
│ WEIGHTS                        │ bytes originais de pesos
├────────────────────────────────┤
│ BIAS                           │ bias dos operadores
├────────────────────────────────┤
│ MUL                            │ int32 por canal
├────────────────────────────────┤
│ SHIFT                          │ int32 por canal
├────────────────────────────────┤
│ Q6                             │ limites quantizados
├────────────────────────────────┤
│ PARAMS                         │ N×116 + padding final
├────────────────────────────────┤
│ SLOT0                          │ slot_bytes
├────────────────────────────────┤
│ SLOT1                          │ slot_bytes
├────────────────────────────────┤
│ SLOT2                          │ slot_bytes
└────────────────────────────────┘
      ▼ MEM_END (exclusivo)
espaço até o final da última página
      ▼
endereço alto
```

Entram comprimentos específicos do modelo. `memory.py` e `layer_params.py` calculam bases e padding; saem regiões para o gerador. O layout e a página de 65536 bytes são convenções do runtime. Linhas da caixa não significam ausência de gaps: cada base pode ter alinhamento entre regiões. Os slots não recebem data segments; começam zerados pela memória WASM e são sobrescritos durante execução.

## Finalização

`mem_pages_for(end_addr)` calcula `ceil(end_addr/65536)` por divisão inteira. `calculate_final_memory_layout` monta `regions` para WEIGHTS, BIAS, MUL, SHIFT, Q6, PARAMS (comprimento real do blob com padding) e todos os slots recebidos. Acrescenta `end=base+bytes`, usa o maior fim como `mem_end`, calcula páginas, bytes alocados e espaço residual. Retorna também slots e tamanho de página. Não há teste explícito de sobreposição ou ordem das regiões, nem limite máximo de páginas.

Exemplo drowsiness: PARAMS começa em 499360; 68×116=7888, já múltiplo de 16. SLOT0 começa em 507248, seguido por três áreas de 196608. Fim 1097072; 17 páginas reservam 1114112, com 17040 bytes restantes. ImageNet: 67×116=7772, arredondado para 7776; fim 3606880 e 56 páginas, com 63136 bytes restantes.

## Formatação e falhas

`slot_memory_to_text` lista tensores, maior tensor e conta de alinhamento para 07. `parameter_layout_to_text` imprime bases e tamanhos para 08. `final_memory_layout_to_text` lista regiões, finais e resumo para 11. Todos retornam strings sem escrever arquivos. Entrada estrutural incompleta causa KeyError; parâmetros numéricos inválidos podem gerar layouts sem sentido sem erro imediato. Ausência de tipo reconhecido pode produzir slot de zero bytes; a função não rejeita esse caso.

## Relação com fonte e artefato

O tamanho do arquivo WASM não é `mem_pages×65536`: slots são memória reservada sem conteúdo embutido. O tamanho do WAT também é diferente por causa do escape textual dos blobs. O layout atual é estático por modelo; não há alocador de tensores durante a inferência.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from extractor.tflite_utils import BYTES_PER_TYPE, TENSOR_TYPE_MAP, is_constant_tensor, tensor_shape_list
```

### `tensor_numel` — assinatura

```python
def tensor_numel(shape, batch=1)
```

### `align_up` — assinatura

```python
def align_up(value, alignment=16)
```

### `calculate_slot_bytes` — assinatura

```python
def calculate_slot_bytes(model, subgraph, *, batch, alignment)
```

### `calculate_parameter_layout` — assinatura

```python
def calculate_parameter_layout(
    *,
    kernel_base_hint,
    alignment,
    weights_raw,
    bias_raw,
    mul_blob,
    shift_blob,
    q6_blob,
)
```

### `slot_memory_to_text` — assinatura

```python
def slot_memory_to_text(memory_info)
```

### `parameter_layout_to_text` — assinatura

```python
def parameter_layout_to_text(layout)
```

### `mem_pages_for` — assinatura

```python
def mem_pages_for(end_addr)
```

### `calculate_final_memory_layout` — assinatura

```python
def calculate_final_memory_layout(*, parameter_layout, params_blob, slot_bases, slot_bytes)
```

### `final_memory_layout_to_text` — assinatura

```python
def final_memory_layout_to_text(memory_layout)
```

## Material técnico preservado

A explicação anterior está em [09-memory-layout.md](historico/09-layout-memoria.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
