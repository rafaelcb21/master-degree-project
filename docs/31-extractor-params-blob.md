[English](31-extractor-params-blob.md) | [Português (Brasil)](31-extractor-params-blob.pt-BR.md)

# 31 — Serialization and pointer resolution

[Index](README.md) · Source: [extractor/params_blob.py](../extractor/params_blob.py)

## Input and position

Receives LayerParams dicts, slot bases, the params_bytes reservation, and parameter_layout. Returns PARAMS region bytes and diagnostic records. Called after layer construction and before the final memory calculation. It does not choose templates or run kernels.

## Name and flag helpers

`op_type_name` maps the eight codes to short names (CONV, DW, FC, etc.), returning `str(op_type)` for unknown values. `act_name` does the same for NONE/RELU/RELU6. `flags_pretty` handles QUANTIZE separately: OUTPUT_UINT8 or OUTPUT_INT8 from bit 1 and INPUT_INT8 or INPUT_UINT8 from bit 0. For other operations it uses PADDING_SAME and HAS_Q6, or the string 0. The synthetic layer's flags are an address, currently zero; this formatter does not describe their meaning without optype context.

## pack_layerparam

Receives 29 positional arguments in ABI order, builds a list, checks length 29, and calls `struct.pack(LP_FMT,*[int(value) ...])`. The length check is defensive because the signature itself defines the count. Returns 116 bytes. It does not restrict geometric fields to positive values or distinguish pointers from numbers; int32 overflow can cause `struct.error`.

## validate_layer_params

Checks in_slot/out_slot bounds for every layer. For ADD, requires two inputs, in_slot matching the first, and pad_t and pad_b matching the two slot bases and belonging to the base list. Returns True or RuntimeError with context. ADD's auxiliary slots index the list before individual range validation; badly malformed data may produce IndexError. It does not check each tensor's capacity, blob overlap, weight offset validity, or individual pointer alignment.

## build_params_blob

First calls validation. For each layer, resolves input/output, weights, bias, and quantization arrays. ADD input comes from pad_t; others use slot_bases[in_slot]. wptr is always kernel_base+w_off. bias_ptr is nonzero only with has_bias. mul_ptr/shift_ptr are enabled only with has_mulq6. q6_ptr requires has_mulq6 **and** act=RELU6. Calls pack_layerparam, requires LP_SIZE length, appends bytes, and creates a record with layer, blob offset, pointers, and a reference to the original dict.

```text
relative offset                 physical base
       │                             │
       └──────────────┬──────────────┘
                      ▼ addition
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
PARAMS: [L0:116][L1:116] ... [Ln:116][zero padding]
```

Inputs are model-specific offsets and calculated bases. The serializer resolves references, applies presence conditions, and produces consecutive records. Outputs are bytes and records consumed by memory/generator/reporting. The 116-byte stride and endianness are generic; pointers vary by package. The diagram shows additions only when the presence condition applies, except wptr, which is always calculated.

Finally, `used_bytes=len(params_blob)`. If this exceeds params_bytes, it raises RuntimeError; otherwise it appends zeros up to the exact reservation. Returns `params_blob,records,layer_count,layer_param_size,used_bytes,padding_bytes,params_bytes`. Padding occurs only at the block's end; there is no 16-byte alignment between records. Since 116 is a multiple of 4, each record remains aligned for i32 when PARAMS_BASE is aligned.

## Numerical examples

ImageNet has 67 records: 67×116=7772; aligned reservation is 7776, hence four trailing zeros. Record i starts at `PARAMS_BASE+i×116`, with out_ptr 16 bytes further on. Drowsiness has 68×116=7888 and zero padding. `depth_mult` does not appear after out_w: there is no thirtieth integer.

## params_blob_to_text and diagnostics

Emits count/size/padding and, for each record, codes/name, flags, slots, pointers, quantization parameters, and reinterpretations of special fields. Receives serialization and returns a string for 10. This representation distinguishes relative offsets from absolute pointers and helps verify ADD. The presence of an address does not guarantee the kernel ignores it when absent: some kernels load bias_ptr without checking zero, a runtime limitation recorded separately.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
import struct
from extractor.layer_params import LP_FMT, LP_SIZE, OP_CONV, OP_DW, OP_FC, OP_ADD, OP_MEAN, OP_SOFTMAX, OP_QUANTIZE, OP_RGB565_TO_RGB888, FLAG_PADDING_SAME, FLAG_HAS_Q6, FLAG_QUANTIZE_INPUT_INT8, FLAG_QUANTIZE_OUTPUT_UINT8
from extractor.operator_options import ACT_NONE, ACT_RELU, ACT_RELU6
```

### `op_type_name` — signature

```python
def op_type_name(op_type)
```

### `act_name` — signature

```python
def act_name(act)
```

### `flags_pretty` — signature

```python
def flags_pretty(flags, optype='')
```

### `pack_layerparam` — signature

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

### `validate_layer_params` — signature

```python
def validate_layer_params(layer_params, *, slot_bases)
```

### `build_params_blob` — signature

```python
def build_params_blob(layer_params, *, slot_bases, params_bytes, parameter_layout)
```

### `params_blob_to_text` — signature

```python
def params_blob_to_text(serialization)
```

## Preserved technical material

The previous explanation is in [12-params-blob.md](historico/12-params-blob.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
