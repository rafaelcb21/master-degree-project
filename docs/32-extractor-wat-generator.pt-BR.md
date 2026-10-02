[English](32-extractor-wat-generator.md) | [Português (Brasil)](32-extractor-wat-generator.pt-BR.md)

# 32 — Materialização WAT e data segments

[Índice](README.pt-BR.md) · Fonte: [extractor/wat_generator.py](../extractor/wat_generator.py)

## Objetivo e entradas

Recebe template_path/output_path e os resultados de layout, LayerParams, serialização, pesos e quantização. Não compila. A implementação de kernels permanece no template; o gerador apenas substitui constantes e insere dados. Não faz parsing estrutural de WAT.

## Conversão de bytes

`_as_bytes` aceita bytes, bytearray, memoryview ou objeto com método tobytes. Retorna bytes nos três primeiros casos e o resultado de tobytes no último; não valida que esse método realmente devolveu bytes. Outros tipos geram TypeError.

`wat_data_from_bytes(data,base)` retorna string vazia para blob vazio. Para cada byte gera escape `\xx` hexadecimal de dois dígitos e retorna `(data (i32.const BASE) "...")`. Exemplo: bytes 0,65,255 em base 2048 viram `(data (i32.const 2048) "\00\41\ff")`. Não interpreta os números internos do blob.

```text
weights_raw ──────┐
bias_raw ─────────┤
mul_blob ─────────┤
shift_blob ───────┤
q6_blob ──────────┤
params_blob ──────┘
                 │ + bases do parameter_layout
                 ▼
          build_data_segments()
                 │
                 ▼
  (data (i32.const BASE) "\xx\xx...")
                 │ instanciação
                 ▼
       memória WASM inicializada
```

Entram seis blobs e suas bases. O gerador escapa todos os bytes e omite segmentos vazios; saem active data segments, aplicados na instanciação. Dados e endereços são específicos; sintaxe do segmento é compartilhada. Slots não têm segmentos próprios e são inicialmente zerados pela memória WebAssembly.

`build_data_segments` preserva a ordem WEIGHTS, BIAS, MUL, SHIFT, Q6, PARAMS, indenta e separa segmentos por linhas vazias. O endereço explícito, não a ordem textual, determina a posição na memória.

## generate_wat

Lê UTF-8; rejeita lista vazia de LayerParams ou records de serialização. Toma a última camada e o último record como saída: result_base=out_ptr e result_count=out_h×out_w×cout. Exige exatamente três bases de slots. Substitui strings com `str.replace`, converte números por int→str, acrescenta os data segments e procura tokens ainda casando `@@[A-Z0-9_]+@@`. Tokens remanescentes causam RuntimeError. Cria a pasta e escreve UTF-8 no destino.

```text
template WAT com placeholders
                 │
                 ▼
            generate_wat ◄─────────────┐
                 ▲                    │
                 │                    │
 parameter_layout / layer_memory / final_memory
                 │                    │
         params_serialization + blobs + última layer
                 │
                 ▼
      substituições + data segments
                 │ valida tokens restantes
                 ▼
        generated/model.wat
                 ▼ etapa independente
       compilador → model.wasm
```

Entram template e estruturas do extrator; saem texto e metadados. O código do template é específico da implementação escolhida pelo pacote; placeholders e ABI são convenções compartilhadas. O gerador não transforma uma implementação incompatível em runtime correto.

## Todos os placeholders fornecidos

| Token (entre `@@`) | Origem |
|---|---|
| MEM_PAGES | final_memory.mem_pages |
| PARAMS_BASE | parameter_layout.params_base |
| LP_SIZE | params_serialization.layer_param_size |
| NUM_LAYERS | len(layer_params) |
| WEIGHTS_BASE, BIAS_BASE | kernel_base, bias_base |
| MUL_BASE, SHIFT_BASE, Q6_BASE | respectivas bases |
| SLOT0_BASE, SLOT1_BASE, SLOT2_BASE | três bases de slots |
| RESULT_BASE | out_ptr do último record |
| RESULT_COUNT | produto espacial/canais da última camada |
| DATA_SEGMENTS | string dos seis blocos não vazios |

Retorna output_path, mem_pages, num_layers, result_base, result_count, wat_bytes. Esse último é medido no arquivo, não na memória linear.

## Limitações e invariantes

O teste de tokens só encontra o padrão em maiúsculas e números/underscore. Não verifica se cada placeholder esperado estava presente; um template com endereço hardcoded pode passar. Não prova limites dos data segments ou correspondência dos exports. O uso da última camada como output pressupõe grafo/ordem compatíveis; o pipeline compara somente a quantidade de elementos, depois da compilação. UTF-8 inválido e falhas de disco propagam. A escrita sobrescreve o destino sem transação; template e output devem ser distintos por configuração.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from pathlib import Path
import re
```

### `_as_bytes` — assinatura

```python
def _as_bytes(value)
```

### `wat_data_from_bytes` — assinatura

```python
def wat_data_from_bytes(data, base)
```

### `build_data_segments` — assinatura

```python
def build_data_segments(*, parameter_layout, weights_bias, quantization, params_serialization)
```

### `generate_wat` — assinatura

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
)
```

## Material técnico preservado

A explicação anterior está em [13-geracao-wat.md](historico/13-geracao-wat.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
