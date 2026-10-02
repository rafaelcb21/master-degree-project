[English](29-extractor-operator-options.md) | [Português (Brasil)](29-extractor-operator-options.pt-BR.md)

# 29 — Operator options and geometry

[Index](README.md) · Source: [extractor/operator_options.py](../extractor/operator_options.py)

## Purpose and contract

Decodes the binding's `BuiltinOptions` for LayerParams builders. It does not discover operators or validate complete networks. It uses tflite classes and tolerates both a directly imported class and a module containing the class. Several methods catch any `Exception` and return defaults: consider this behavior when debugging an incompatible model.

## Functions

`parse_fused_activation` recognizes NONE, RELU, and RELU6 using the enum, then numeric values 0,1,3. Any other activation returns NONE. These codes are those used by the ABI, not a list of everything TFLite supports.

`parse_add_options` and `parse_fc_options` access BuiltinOptions Bytes/Pos, initialize the appropriate class, and return the normalized activation. Failure or an unexpected form results in ACT_NONE.

`padding_is_same` compares against Padding.SAME; on exception, it compares against zero. `parse_conv2d_options` returns `(stride_h,stride_w,dil_h,dil_w,padding_kind,activation)`; absent dilation defaults to 1; padding_kind is 0 for SAME and 1 otherwise. The complete fallback is `(1,1,1,1,1,ACT_NONE)`, a path treated as VALID. `parse_dwconv2d_options` adds `depth_mult`, with fallback 1. Reading depth_mult does not imply that it is serialized or honored by the kernel.

`same_padding` receives dimensions, kernel, stride, and dilation. Calculates `out=ceil(in/stride)`, `effective_kernel=(kernel-1)*dilation+1`, `total=max(0,(out-1)*stride+effective_kernel-in)`. Splits the total: before=floor(total/2), after=remainder. Returns top,bottom,left,right,out_h,out_w. One-dimensional example: in=4,kernel=3,stride=2,dilation=1 → out=2,total=1,before=0,after=1.

```text
BuiltinOptions (Bytes, Pos)
              │
              ▼
 Conv2D/Depthwise/Add/FC class
              │
      ┌───────┴─────────┐
      ▼                 ▼
 successful read   exception/absence
      │                 │
      ▼                 ▼
 actual values       defaults
      └────────┬────────┘
               ▼
     builder → geometry / flags / act
```

Inputs are operator-specific options; the module translates enums and calculates padding. Outputs are integer values for LayerParams. Geometry belongs to the model; flag/activation encoding belongs to the runtime. The fallback branch does not report that a value was replaced, limiting auditability.

## Limitations

Zero stride may cause division by zero in `same_padding`; there is no general validation of positive values. Operators with unimplemented options may silently receive defaults. Activation extracted for ADD/FC is recorded, but the observed kernels do not apply the field; this documentation distinguishes parsing from execution. This module does not read MEAN axis or SOFTMAX beta.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from tflite import ActivationFunctionType, AddOptions, Padding, Conv2DOptions, DepthwiseConv2DOptions, FullyConnectedOptions
```

### `parse_fused_activation` — signature

```python
def parse_fused_activation(activation_value)
```

### `parse_add_options` — signature

```python
def parse_add_options(op)
```

### `padding_is_same` — signature

```python
def padding_is_same(padding_value)
```

### `parse_conv2d_options` — signature

```python
def parse_conv2d_options(op)
```

### `parse_dwconv2d_options` — signature

```python
def parse_dwconv2d_options(op)
```

### `parse_fc_options` — signature

```python
def parse_fc_options(op)
```

### `same_padding` — signature

```python
def same_padding(in_h, in_w, kernel_h, kernel_w, stride_h, stride_w, dil_h=1, dil_w=1)
```

## Preserved technical material

The previous explanation is in [10-operator-options.md](historico/10-operator-options.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
