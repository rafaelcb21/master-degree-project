[English](31-extractor-params-blob.md) | [Português (Brasil)](31-extractor-params-blob.pt-BR.md)

# 31 — Serialização e resolução de ponteiros

[Índice](README.pt-BR.md) · Fonte: [extractor/params_blob.py](../extractor/params_blob.py)

## Entrada e posição

Recebe LayerParams em dicts, bases dos slots, reserva params_bytes e parameter_layout. Devolve bytes da região PARAMS e registros de diagnóstico. É chamado após construção de camadas e antes do cálculo final da memória. Não escolhe templates nem roda kernels.

## Helpers de nomes e flags

`op_type_name` mapeia os oito códigos para nomes curtos (CONV, DW, FC etc.), retornando `str(op_type)` no desconhecido. `act_name` faz o mesmo para NONE/RELU/RELU6. `flags_pretty` trata QUANTIZE separadamente: OUTPUT_UINT8 ou OUTPUT_INT8 pelo bit 1 e INPUT_INT8 ou INPUT_UINT8 pelo bit 0. Nas outras operações usa PADDING_SAME e HAS_Q6, ou string 0. Flags da sintética são um endereço e atualmente zero; esse formatter não descreve seu significado sem o contexto do optype.

## pack_layerparam

Recebe 29 argumentos posicionais na ordem ABI, monta uma lista, verifica comprimento 29 e chama `struct.pack(LP_FMT,*[int(value) ...])`. O teste de comprimento é defensivo, já que a própria assinatura define a quantidade. Retorna 116 bytes. Não restringe campos geométricos a valores positivos nem distingue ponteiros de números; `struct.error` pode ocorrer por overflow de int32.

## validate_layer_params

Para todas as camadas verifica faixa de in_slot/out_slot. Em ADD exige duas entradas, que in_slot coincida com a primeira, que pad_t e pad_b sejam as bases dos dois slots e pertençam à lista de bases. Retorna True, ou RuntimeError com contexto. Os slots auxiliares de ADD são usados para indexar a lista antes de uma validação individual de faixa; dados muito malformados podem produzir IndexError. Não verifica capacidade de cada tensor, sobreposição de blobs, validade dos offsets de pesos ou alinhamento de cada ponteiro.

## build_params_blob

Primeiro chama a validação. Para cada camada resolve entrada/saída, pesos, bias e arrays de quantização. Entrada ADD vem de pad_t; nas demais vem de slot_bases[in_slot]. wptr é sempre kernel_base+w_off. bias_ptr só é não zero com has_bias. mul_ptr/shift_ptr só com has_mulq6. q6_ptr só com has_mulq6 **e** act=RELU6. Chama pack_layerparam, exige comprimento LP_SIZE, concatena e cria um record com camada, offset no blob, ponteiros e referência ao dict original.

```text
offset relativo                 base física
       │                             │
       └──────────────┬──────────────┘
                      ▼ soma
      ┌──────────────────────────────────────────┐
      │ WEIGHTS_BASE + w_off   → wptr            │
      │ BIAS_BASE + b_off      → bias_ptr        │
      │ MUL_BASE + mul_off     → mul_ptr         │
      │ SHIFT_BASE + shift_off → shift_ptr       │
      │ Q6_BASE + q6_off       → q6_ptr          │
      └──────────────────┬───────────────────────┘
                         ▼
                 pack_layerparam
                         ▼
PARAMS: [L0:116][L1:116] ... [Ln:116][padding zero]
```

Entram offsets específicos do modelo e bases calculadas. O serializador resolve referências, aplica condições de presença e produz registros consecutivos. Saem bytes e records consumidos por memória/gerador/relatório. O stride 116 e endianness são genéricos; os ponteiros variam por pacote. O desenho mostra as somas apenas quando a condição de presença se aplica, exceto wptr, sempre calculado.

Ao final, `used_bytes=len(params_blob)`. Se exceder params_bytes, levanta RuntimeError; caso contrário acrescenta zeros até a reserva exata. Retorna `params_blob,records,layer_count,layer_param_size,used_bytes,padding_bytes,params_bytes`. O padding é somente no final do bloco; não existe alinhamento 16 entre registros. Como 116 é múltiplo de 4, cada registro continua alinhado para i32 quando PARAMS_BASE está alinhado.

## Exemplos numéricos

ImageNet tem 67 registros: 67×116=7772; a reserva alinhada é 7776, logo quatro zeros finais. O registro i começa em `PARAMS_BASE+i×116`, e seu out_ptr está 16 bytes adiante. Sonolência tem 68×116=7888 e padding zero. `depth_mult` não aparece após out_w: não há trigésimo inteiro.

## params_blob_to_text e diagnóstico

Emite contagem/tamanho/padding e, para cada record, códigos/nome, flags, slots, ponteiros, parâmetros de quantização e reinterpretações dos campos especiais. Recebe a serialização e retorna string para 10. Essa representação distingue offset relativo de ponteiro absoluto e ajuda a verificar ADD. A presença de um endereço não garante que o kernel o ignore quando ausente: alguns kernels carregam bias_ptr sem checar zero, limitação do runtime registrada separadamente.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
import struct
from extractor.layer_params import LP_FMT, LP_SIZE, OP_CONV, OP_DW, OP_FC, OP_ADD, OP_MEAN, OP_SOFTMAX, OP_QUANTIZE, OP_RGB565_TO_RGB888, FLAG_PADDING_SAME, FLAG_HAS_Q6, FLAG_QUANTIZE_INPUT_INT8, FLAG_QUANTIZE_OUTPUT_UINT8
from extractor.operator_options import ACT_NONE, ACT_RELU, ACT_RELU6
```

### `op_type_name` — assinatura

```python
def op_type_name(op_type)
```

### `act_name` — assinatura

```python
def act_name(act)
```

### `flags_pretty` — assinatura

```python
def flags_pretty(flags, optype='')
```

### `pack_layerparam` — assinatura

```python
def pack_layerparam(
    op_type,
    act,
    flags,
    in_ptr,
    out_ptr,
    in_h,
    in_w,
    cin,
    cout,
    kh,
    kw,
    stride_h,
    stride_w,
    dil_h,
    dil_w,
    pad_t,
    pad_b,
    pad_l,
    pad_r,
    wptr,
    bias_ptr,
    mul_ptr,
    shift_ptr,
    q6_ptr,
    zx,
    zw,
    zy,
    out_h,
    out_w,
)
```

### `validate_layer_params` — assinatura

```python
def validate_layer_params(layer_params, *, slot_bases)
```

### `build_params_blob` — assinatura

```python
def build_params_blob(layer_params, *, slot_bases, params_bytes, parameter_layout)
```

### `params_blob_to_text` — assinatura

```python
def params_blob_to_text(serialization)
```

## Material técnico preservado

A explicação anterior está em [12-params-blob.md](historico/12-params-blob.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
