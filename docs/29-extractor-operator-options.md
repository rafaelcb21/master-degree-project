# 29 — Opções de operadores e geometria

[Índice](README.md) · Fonte: [extractor/operator_options.py](../extractor/operator_options.py)

## Objetivo e contrato

Decodifica `BuiltinOptions` do binding para os builders de LayerParams. Não descobre operadores nem valida redes completas. Usa classes tflite e tolera tanto import de classe direta quanto módulo contendo classe. Em vários métodos, captura qualquer `Exception` e retorna defaults: esse comportamento deve ser levado em conta ao depurar um modelo incompatível.

## Funções

`parse_fused_activation` reconhece NONE, RELU e RELU6 usando enum, depois valores numéricos 0,1,3. Qualquer outra ativação retorna NONE. Os códigos são os usados pelo ABI, não uma lista de tudo que o TFLite suporta.

`parse_add_options` e `parse_fc_options` acessam Bytes/Pos de BuiltinOptions, inicializam a classe apropriada e devolvem a ativação normalizada. Falha ou forma inesperada resulta em ACT_NONE.

`padding_is_same` compara com Padding.SAME; se houver exceção, compara com zero. `parse_conv2d_options` retorna `(stride_h,stride_w,dil_h,dil_w,padding_kind,activation)`; dilatação ausente recebe 1; padding_kind é 0 para SAME e 1 para outro. Fallback integral é `(1,1,1,1,1,ACT_NONE)`, ou seja, caminho tratado como VALID. `parse_dwconv2d_options` acrescenta `depth_mult`, com fallback 1. Ler depth_mult não implica que ele seja serializado ou respeitado pelo kernel.

`same_padding` recebe dimensão, kernel, stride e dilatação. Calcula `out=ceil(in/stride)`, `effective_kernel=(kernel-1)*dilation+1`, `total=max(0,(out-1)*stride+effective_kernel-in)`. Divide o total: anterior=floor(total/2), posterior=restante. Retorna top,bottom,left,right,out_h,out_w. Exemplo unidimensional: in=4,kernel=3,stride=2,dilation=1 → out=2,total=1,antes=0,depois=1.

```text
BuiltinOptions (Bytes, Pos)
              │
              ▼
 classe Conv2D/Depthwise/Add/FC
              │
      ┌───────┴─────────┐
      ▼                 ▼
  leitura OK       exceção/ausência
      │                 │
      ▼                 ▼
 valores reais       defaults
      └────────┬────────┘
               ▼
     builder → geometria / flags / act
```

Entram opções específicas do operador; o módulo traduz enums e calcula padding. Saem valores inteiros para LayerParams. Geometria é do modelo; codificação de flags/ativação é do runtime. O ramo de fallback não avisa no relatório que o valor foi substituído, o que limita a auditabilidade.

## Limitações

Stride zero pode causar divisão por zero em `same_padding`; não há validação geral de valores positivos. Operadores com opções não implementadas podem receber defaults silenciosos. A ativação extraída para ADD/FC é registrada, mas os kernels observados não aplicam o campo; a documentação distingue parsing de execução. Não há leitura de axis de MEAN ou beta de SOFTMAX neste módulo.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from tflite import ActivationFunctionType, AddOptions, Padding, Conv2DOptions, DepthwiseConv2DOptions, FullyConnectedOptions
```

### `parse_fused_activation` — assinatura

```python
def parse_fused_activation(activation_value)
```

### `parse_add_options` — assinatura

```python
def parse_add_options(op)
```

### `padding_is_same` — assinatura

```python
def padding_is_same(padding_value)
```

### `parse_conv2d_options` — assinatura

```python
def parse_conv2d_options(op)
```

### `parse_dwconv2d_options` — assinatura

```python
def parse_dwconv2d_options(op)
```

### `parse_fc_options` — assinatura

```python
def parse_fc_options(op)
```

### `same_padding` — assinatura

```python
def same_padding(in_h, in_w, kernel_h, kernel_w, stride_h, stride_w, dil_h=1, dil_w=1)
```

## Material técnico preservado

A explicação anterior está em [10-operacoes-opcoes.md](historico/10-operacoes-opcoes.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.md).
