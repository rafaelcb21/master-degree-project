# 08 — Contrato binário layerparam-v1

[Índice](README.md) · [LayerParams](30-extractor-layer-params.md) · [Serialização](31-extractor-params-blob.md) · [Runtime WAT](13-runtime-wat.md)

## O que o nome significa

`layerparam-v1` **não é um arquivo**. É o nome aceito no manifest para o acordo entre construtor de parâmetros, serializador e kernels WAT. O loader valida a string; não lê uma versão exportada do WASM e não prova que um template personalizado segue o acordo.

```text
                        layerparam-v1
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
    layer_params.py     params_blob.py       template WAT
    cria dicts          resolve ponteiros   lê offsets fixos
    por operador        e serializa         e executa kernels
           └──────────────────┬──────────────────┘
                              ▼
                      runtime WebAssembly
```

Entram operadores e atributos do TFLite. Os três componentes concordam sobre valores, ordem e interpretação. Sai uma rede executável no runtime. Geometria, pesos e quantização variam por modelo; códigos de operação, campos e tamanho do registro são compartilhados.

## Representação e percurso

`LP_FMT = "<" + "i" * 29`; `LP_SIZE = struct.calcsize(LP_FMT) = 116`. Cada campo é inteiro com sinal de 32 bits, little-endian, sem padding interno. `pack_layerparam` converte valores com `int` e chama `struct.pack`; valores fora da faixa de int32 falham. Ponteiros também ocupam esses campos; esta implementação não usa memory64.

```text
TFLite Operator
      │
      ▼
layer_params.py
      │ dict com slots, geometria, offsets e quantização
      ▼
┌────────────────────────────────┐
│ LayerParam Python              │
│ op_type / act / flags          │
│ in_slot / out_slot             │
│ w_off / b_off / mul_off / ...  │
└──────────────┬─────────────────┘
               ▼
params_blob.py: slot→ponteiro; base+offset→ponteiro
               ▼
struct.pack("<29i")  (formato equivalente ao LP_FMT)
               ▼
┌─────────────────────────────────┐
│ 29 × int32 = 116 bytes          │
└──────────────┬──────────────────┘
               ▼
PARAMS_BASE + layer_index × 116
               ▼
campo k em base_da_layer + 4 × k
               ▼
template WAT: i32.load / kernel
```

Entram dicts, bases e offsets; o serializador transforma referências lógicas em endereços e bytes. Saem registros consecutivos na região PARAMS, seguidos de padding final. O layout do modelo determina bases; a regra 4×k e os 116 bytes são invariantes do ABI. `struct.pack("<29i")` ilustra o mesmo formato que `"<" + "i"*29`.

## Tabela completa dos 29 campos

Offsets abaixo são relativos ao início de uma LayerParam, em bytes. Os nomes são os argumentos de `pack_layerparam`.

| Índice | Offset | Campo | Significado básico |
|---:|---:|---|---|
| 0 | 0 | `op_type` | Código do kernel |
| 1 | 4 | `act` | Ativação fundida |
| 2 | 8 | `flags` | Bits ou endereço, conforme operação |
| 3 | 12 | `in_ptr` | Ponteiro absoluto da entrada principal |
| 4 | 16 | `out_ptr` | Ponteiro absoluto da saída |
| 5 | 20 | `in_h` | Altura de entrada |
| 6 | 24 | `in_w` | Largura de entrada |
| 7 | 28 | `cin` | Canais de entrada / tamanho do vetor em certos kernels |
| 8 | 32 | `cout` | Canais/unidades de saída |
| 9 | 36 | `kh` | Altura de kernel ou parâmetro especial |
| 10 | 40 | `kw` | Largura de kernel ou parâmetro especial |
| 11 | 44 | `stride_h` | Stride vertical ou parâmetro especial |
| 12 | 48 | `stride_w` | Stride horizontal ou parâmetro especial |
| 13 | 52 | `dil_h` | Dilatação vertical ou multiplicador especial |
| 14 | 56 | `dil_w` | Dilatação horizontal ou shift especial |
| 15 | 60 | `pad_t` | Padding superior ou ponteiro da entrada A |
| 16 | 64 | `pad_b` | Padding inferior ou ponteiro da entrada B |
| 17 | 68 | `pad_l` | Padding esquerdo ou zero point A |
| 18 | 72 | `pad_r` | Padding direito ou zero point B |
| 19 | 76 | `wptr` | Base WEIGHTS + offset dos pesos |
| 20 | 80 | `bias_ptr` | Base BIAS + offset; zero se ausente |
| 21 | 84 | `mul_ptr` | Base MUL + offset; zero se ausente |
| 22 | 88 | `shift_ptr` | Base SHIFT + offset; zero se ausente |
| 23 | 92 | `q6_ptr` | Base Q6 + offset somente com dados e RELU6 |
| 24 | 96 | `zx` | Zero point da entrada |
| 25 | 100 | `zw` | Zero point de peso; em ADD também registra zB |
| 26 | 104 | `zy` | Zero point da saída |
| 27 | 108 | `out_h` | Altura de saída |
| 28 | 112 | `out_w` | Largura de saída |

`depth_mult`, `quant_params`, `op_index`, `label`, listas de slots e booleanos de presença existem nos dicts/relatórios, mas **não** são campos adicionais no blob. `op_index` é o índice TFLite; `layer_index` é a posição serializada e inclui a sintética quando presente.

## Códigos de operação e ativação

| op_type | Operação | Origem |
|---:|---|---|
| 1 | CONV_2D | TFLite |
| 2 | DEPTHWISE_CONV_2D | TFLite |
| 3 | FULLY_CONNECTED | TFLite |
| 4 | ADD | TFLite |
| 5 | MEAN | TFLite |
| 6 | SOFTMAX | TFLite |
| 7 | QUANTIZE | TFLite |
| 8 | RGB565_TO_RGB888 | Sintética Python |

`ACT_NONE=0`, `ACT_RELU=1`, `ACT_RELU6=3`. O parser retorna NONE para ativações desconhecidas. Nem todo kernel usa o campo `act`: ADD e FULLY_CONNECTED, por exemplo, não aplicam a ativação fundida nos templates observados; ver limitações. `run_layer` despacha códigos 1–8 e não lança erro explícito para código desconhecido.

## Campos reutilizados

| Operação | Reinterpretação produzida pelo Python |
|---|---|
| ADD | `kh/kw=mulA/shiftA`; `stride_h/w=mulB/shiftB`; `dil_h/w=out_mul/out_shift`; `pad_t/b=ptrA/ptrB`; `pad_l/r=zA/zB` |
| MEAN | `kh/kw=mul/shift` para `sX/sY`; `stride_h=H×W`; `stride_w=1`; `pad_t=input_ptr` |
| SOFTMAX | `kh/kw=input_beta_mul/input_beta_left_shift`; `stride_h=diff_min=-128`; `stride_w=input_left_shift`; `pad_t=input_ptr` |
| QUANTIZE | `kh/kw=mul/shift` para `scale_in/scale_out`; `pad_t=input_ptr`; `zx/zy=zp_in/zp_out` |
| RGB565_TO_RGB888 | `flags=FORMAT_FLAG_ADDR=0`; `kh=FORMAT_RGB565=65`; slots 0→1 |

Produzir um campo não significa que o WAT o usa. MEAN recalcula H×W; SOFTMAX usa `7877` e shift 16 em vez dos multiplicadores produzidos; RGB565 usa `flags` como endereço, não máscara. A tabela descreve a produção Python e deve ser lida junto do capítulo do runtime.

## Flags de QUANTIZE

Bit 0: 0 = input UINT8, 1 = input INT8. Bit 1: 0 = output INT8, 1 = output UINT8.

| flags | Entrada | Saída |
|---:|---|---|
| 0 | UINT8 | INT8 |
| 1 | INT8 | INT8 |
| 2 | UINT8 | UINT8 |
| 3 | INT8 | UINT8 |

Para convoluções, os mesmos bits significam `PADDING_SAME` (1) e `HAS_Q6` (2). A interpretação depende de `op_type`; ler a máscara sem conhecer a operação é incorreto. O template legado não selecionado ainda decide a saída UINT8 pelo índice fixo 67, divergindo desse contrato atual.

## Ponteiros e offsets

```text
w_off     + WEIGHTS_BASE ──► wptr
b_off     + BIAS_BASE    ──► bias_ptr  (se has_bias)
mul_off   + MUL_BASE     ──► mul_ptr   (se has_mulq6)
shift_off + SHIFT_BASE   ──► shift_ptr (se has_mulq6)
q6_off    + Q6_BASE      ──► q6_ptr    (se has_mulq6 e act=RELU6)

in_slot ──► slot_bases[in_slot] ──► in_ptr
out_slot ─► slot_bases[out_slot] ─► out_ptr
ADD: in_ptr vem de pad_t, validado contra a base do slot A
```

Entram offsets relativos e bases do layout; `params_blob.py` resolve endereços absolutos. Saem campos que o WAT pode usar diretamente. Tamanhos e bases são específicos; a regra de endereçamento é comum. `wptr` é calculado mesmo em operações sem pesos; nesses casos o kernel deve ignorá-lo. Ponteiro zero não é tratado como ausência por todos os kernels.

## Slots, shifts e exigências do host

Há três slots com o mesmo tamanho, alinhados em 16 bytes. Slot lógico não é tensor nem região exclusiva por camada: a área é reutilizada. `slot_shift` muda a associação lógica para acomodar a sintética. O shift de quantização é outra coisa: `real_multiplier ≈ multiplier / 2³¹ × 2^shift`; positivo indica deslocamento à esquerda, negativo à direita. Não confunda ambos.

Exports obrigatórios: memória `memory`, função `run_mobilenetv2` chamada sem argumentos e `get_result_ptr` retornando endereço. O template atual retorna i32 zero de `run_mobilenetv2`, ignorado pelo host. A saída é lida como elementos de um byte. Formato host RGB565 usa byte 65 em endereço 0; flag de execução do WAT fica em endereço 4.

Trocar somente o template funciona apenas se ele preservar campos, semântica, endianness, data segments, exports e regras numéricas compatíveis. Manter 116 bytes mas alterar a ordem já quebra o contrato. O código atual não negocia ABI nem confirma equivalência numérica do template.
