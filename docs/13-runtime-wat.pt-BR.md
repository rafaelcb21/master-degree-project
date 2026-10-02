[English](13-runtime-wat.md) | [Português (Brasil)](13-runtime-wat.pt-BR.md)

# 13 — Templates e runtime WebAssembly

[Índice](README.pt-BR.md) · [ABI](08-contrato-layerparam-v1.pt-BR.md) · [Gerador](32-extractor-wat-generator.pt-BR.md)

## Arquivos e seleção real

Há três templates fonte: [mobilenet_int8_v1.wat](../wat/templates/mobilenet_int8_v1.wat), selecionado por sonolência; [template local ImageNet](../models/mobilenetv2_alpha035/wat/model_template.wat), selecionado pelo outro pacote; e [model_template.wat legado](../wat/templates/model_template.wat), sem referência nos manifests atuais. Os dois ativos têm conteúdo idêntico na inspeção. A seleção vem de `runtime.wat_template`; não há factory de kernels por modelo.

O template é um módulo WebAssembly com memória linear exportada, globals de bases/tamanhos, funções de matemática inteira, kernels e dispatcher. Não importa WASI nem TensorFlow. Data segments são inseridos pelo gerador. O nome `run_mobilenetv2` é um nome de export fixo exigido pelo host, embora o corpo percorra uma lista de operações descrita pelos parâmetros.

## Memória e controle

```text
memory exportada
  │
  ├── endereço 0: marcador RGB565 do host (65)
  ├── endereço 4: FLAG_BASE; 1 durante run, 0 ao terminar
  ├── WEIGHTS / BIAS / MUL / SHIFT / Q6
  ├── PARAMS: base + layer_index × LP_SIZE
  └── SLOT0 / SLOT1 / SLOT2
                        │
                        ▼
                RESULT_BASE / RESULT_COUNT
```

Entram dados inicializados e imagem escrita pelo host. O runtime lê registros e escreve ativações nos slots; sai o vetor na base definida pelo gerador. Endereços e tamanhos são específicos do modelo; as flags e offsets de registro são compartilhados. O comentário junto a FLAG_BASE menciona endereço 0, mas o valor executado é 4; a documentação segue o código.

`layerparam_base(layer_idx)` calcula `PARAMS_BASE + layer_idx*LP_SIZE`. `run_layer` lê op_type e despacha 1–8. Código desconhecido simplesmente termina a função. `run_mobilenetv2` marca busy, percorre índices de 0 até NUM_LAYERS−1, chama `run_layer`, libera busy e retorna i32 0. Não há checagem de op_index original ou identidade do tensor de saída.

## Kernels executados

### CONV_2D

Lê os 29 campos, percorre H/W de saída, canal de saída, posições do kernel e canais de entrada. Índice de ativação é NHWC; pesos são OHWI, com bloco por canal de saída. Soma bias e produtos `(x-zx)*(w-zw)` em i32. Padding pula coordenadas fora da área válida; stride e dilatação entram no cálculo de linha/coluna. Aplica `multiply_by_quantized_multiplier_3`, soma zy, aplica RELU ou RELU6 quando act=1/3 e limita a INT8. Bias, multiplier e shift são lidos por canal sem uma validação semântica de ausência.

### DEPTHWISE_CONV_2D

Percorre pixels de saída e canal de saída; acessa ativação em `((row*in_w+col)*cin + oc)` e pesos em `((ki*kw+kj)*cout + oc)`. Essa associação direta de `oc` à entrada presume depth multiplier 1. O Python registra `depth_mult`, mas não o serializa; não há cálculo `input_channel=oc/depth_mult`. Requantização/ativação são semelhantes à convolução e a saída é INT8.

### FULLY_CONNECTED

Para cada oc, inicia acumulador com bias[oc], percorre ic de 0 a cin−1, lê `input[ic]` e `weight[oc*cin+ic]` como signed bytes, remove zero points, multiplica e soma. Requantiza, soma zy e limita INT8. O corpo não lê act; a ativação fundida registrada pelo Python não é aplicada. Também não implementa flatten arbitrário de H×W×C: depende de cin preparado corretamente para o tensor de entrada, como os vetores após MEAN nos modelos atuais.

### ADD

Lê ponteiros A/B dos campos pad_t/pad_b, zA/zB de pad_l/pad_r, pares de multiplicador/shift dos campos reaproveitados e zy. Para cada elemento de H×W×cin, dequantiza implicitamente os inteiros para uma escala comum, soma, aplica requantização de saída e clamp INT8. Não lê act, não verifica shapes nem faz broadcasting. A nomenclatura de campos de padding aqui não representa padding de imagem.

### MEAN

Para cada canal, soma `x-zX` nas H×W posições, divide a soma por H×W com `i32.div_s` (truncamento em direção a zero), requantiza com kh/kw, soma zY e limita INT8. Recalcula spatial_size por H×W, embora o Python também o registre em stride_h. Não lê axis/keep_dims; não é implementação de todos os casos de MEAN TFLite. A função auxiliar `div_round_nearest` existe no template, mas este kernel usa `i32.div_s` diretamente.

### QUANTIZE

Percorre out_h×out_w×cout. Bit 0 de flags escolhe load8_s ou load8_u; subtrai zx, aplica kh/kw, soma zy. Bit 1 escolhe clamp UINT8 `[0,255]` ou INT8 `[-128,127]`, então store8. Python aloca esse operador in-place. No template legado, o clamp depende de `layer_idx==67`; nos dois templates ativos depende de flags.

### SOFTMAX: implementação efetiva

```text
cin logits INT8
      │
      ▼
máximo dos logits
      │
      ▼
diff = ((val - max) × 7877) >> 16
      │
      ▼
exp_q15: tabela discreta para diff inteiro em [-11,0]
      │
      ▼
soma das aproximações exponenciais
      │
      ▼
q = (exp_val × 256) / soma + zY
      │ divisão inteira unsigned
      ▼
clamp INT8 e store8
```

Entram logits da camada anterior; o kernel usa um fator fixo, aproximações tabuladas e normalização inteira. Saem bytes INT8, posteriormente convertidos por QUANTIZE nos dois modelos. Cin e zY são dados do modelo; 7877, shift 16, fator 256 e tabela são constantes do runtime. `kh`, `kw`, `stride_h/w`, MUL e SHIFT produzidos para softmax não determinam esse cálculo. Portanto score de saída não deve ser apresentado como probabilidade calibrada ou reprodução exata do operador TFLite.

`exp_q15(x)` retorna zero abaixo de −11, limita positivos a zero e usa tabela para −11…0: `1,1,4,11,30,81,221,600,1631,4435,12055,32768`. São valores inteiros aproximados de exponencial escalada. A escala efetiva de logit usada é aproximadamente 7877/65536, não necessariamente `input_scale` do TFLite.

### RGB565_TO_RGB888

Lê flags como endereço do marcador e kh como sentinela. Se memória[flags]==kh, lê `load16_u` little-endian e extrai R5=(pixel>>11)&31, G6=(pixel>>5)&63, B5=pixel&31. Expande R/B por `(v<<3)|(v>>2)` e G por `(v<<2)|(v>>4)`. Escreve bytes R,G,B nessa ordem. Caso contrário, copia H×W×3 bytes RGB888 de input para output. O host atual só usa esse kernel com sentinela RGB565, e não expõe o ramo de cópia no manifest.

## Helpers de aritmética inteira

`multiply_by_quantized_multiplier_3` é chamado pelos kernels CONV, DW, FC, ADD, MEAN e QUANTIZE. Primeiro aplica left shift se shift>0, depois high multiply arredondado e, para shift<0, divide por potência de dois. `saturating_rounding_doubling_high_mul_3` usa produto i64, adiciona 2³⁰, faz shift aritmético 31 e retorna i32; trata explicitamente INT32_MIN×INT32_MIN como INT32_MAX. `rounding_divide_by_pot_3` retorna x para expoente≤0; nos demais, usa nudge=2^(exponent−1), adicionando nudge−1 para x≥0 e nudge para x<0 antes de shift aritmético. Os empates não devem ser presumidos iguais a todos os backends TFLite.

Também existem variantes `_2`, funções exportadas sem sufixo e `multiply_by_quantized_multiplier_softmax`. Não são todas equivalentes: a função exportada `multiply_by_quantized_multiplier` faz high multiply e divisão por `-shift`, sem o left shift prévio usado por `_3`. As variantes `_2` usam outra lógica de limiar/remainder para divisão. A presença desses exports não significa que o pipeline os use. Não há teste cobrindo a equivalência entre variantes.

## Exports e uso pelo host

| Família | Funções | Uso |
|---|---|---|
| Essenciais | `memory`, `run_mobilenetv2`, `get_result_ptr` | Exigidos pelo runner |
| Bases e tamanhos | `get_weights_base`, `get_bias_base`, `get_mul_base`, `get_shift_base`, `get_q6_base`, `get_params_base`, `get_slot0_base`, `get_slot1_base`, `get_slot2_base`, `get_result_count` | Diagnóstico; host principal usa seus próprios metadados |
| Controle | `get_flag_base`, `is_ready_for_image` | Busy flag em 4; não consultada pelo runner síncrono |
| Kernels | `conv2d`, `depthwise_conv2d`, `fully_connected`, `add`, `mean`, `softmax`, `quantize`, `rgb565_to_rgb888`, `run_layer` | Chamados pelo dispatcher; quantize também é testado isoladamente |
| Ranking | `get_top_class`, `get_top5` | Não usados pelos adapters; leem signed bytes |
| Matemática | três helpers exportados sem sufixo | Inspeção/uso externo, não a variante principal `_3` |
| Debug | `debug_memory(ptr,size)` | Soma quadrados de bytes assinados; não imprime a memória |

`get_top5` escreve cinco pares `(índice i32,valor i32)` em 40 bytes a partir do ponteiro fornecido, inicializando índices −1 e valores −128. Ambos os exports de ranking leem INT8, inadequado para interpretar diretamente as saídas UINT8 atuais. O Top-15 usado no projeto é calculado pelo adapter Python com dtype correto.

## Limitações de contrato versus implementação

Os 29 campos permitem descrever mais situações que os kernels efetivamente implementam. Bias_ptr=0 não é um bias opcional seguro em todos os kernels, pois há loads sem teste de presença. Os kernels não validam cada ponteiro contra o tamanho do slot. O WASM pode detectar acesso fora da memória inteira com trap, mas não detecta leitura da região errada que ainda está dentro dela. Essas restrições são registradas em [99](99-inconsistencias-e-limitacoes.pt-BR.md); nenhuma foi corrigida nesta tarefa documental.
