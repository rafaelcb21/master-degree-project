[English](08-layerparam-v1-contract.md) | [Português (Brasil)](08-contrato-layerparam-v1.pt-BR.md)

# 08 — The layerparam-v1 binary contract

[Index](README.md) · [LayerParams](30-extractor-layer-params.md) · [Serialization](31-extractor-params-blob.md) · [WAT runtime](13-runtime-wat.md)

## Meaning of the name

layerparam-v1 **is not a file**. It is the manifest name for the agreement between the parameter builder, serializer and WAT kernels. The loader checks the string; it does not read a version exported by WASM or establish that a custom template follows the agreement.

```text
layerparam-v1
 ├─ layer_params.py: creates per-operator dictionaries
 ├─ params_blob.py: resolves pointers and serializes
 └─ WAT template: reads fixed offsets and executes kernels
                         ↓
                WebAssembly runtime
```

TFLite operators/attributes enter the three components, which must agree on values, ordering and interpretation. Model geometry, weights and quantization vary; operation codes, fields and record size are shared.

## Representation and flow

LP_FMT = "<" + "i" * 29; LP_SIZE = struct.calcsize(LP_FMT) = 116. Every field is a signed, little-endian 32-bit integer with no internal padding. pack_layerparam converts values with int and calls struct.pack; out-of-range int32 values fail. Pointers occupy the same fields; memory64 is not used.

```text
TFLite Operator → layer_params.py
 → dictionary: op_type / act / flags / slots / geometry / offsets / quantization
 → params_blob.py: slot→pointer; base+offset→pointer
 → struct.pack("<29i") (equivalent to LP_FMT)
 → 29 × int32 = 116 bytes
 → PARAMS_BASE + layer_index × 116
 → field k at layer_base + 4 × k
 → WAT i32.load / kernel
```

Dictionaries, bases and offsets become absolute addresses and bytes. Consecutive records occupy PARAMS followed by final padding. Model layout determines bases; 4×k and 116 bytes are ABI invariants.

## All 29 fields

Offsets are bytes relative to a LayerParam's start. Names are pack_layerparam arguments.

| Index | Offset | Field | Basic meaning |
|---:|---:|---|---|
| 0 | 0 | op_type | Kernel code |
| 1 | 4 | act | Fused activation |
| 2 | 8 | flags | Bits or address, depending on operation |
| 3 | 12 | in_ptr | Absolute main input pointer |
| 4 | 16 | out_ptr | Absolute output pointer |
| 5 | 20 | in_h | Input height |
| 6 | 24 | in_w | Input width |
| 7 | 28 | cin | Input channels / vector length in some kernels |
| 8 | 32 | cout | Output channels/units |
| 9 | 36 | kh | Kernel height or special parameter |
| 10 | 40 | kw | Kernel width or special parameter |
| 11 | 44 | stride_h | Vertical stride or special parameter |
| 12 | 48 | stride_w | Horizontal stride or special parameter |
| 13 | 52 | dil_h | Vertical dilation or special multiplier |
| 14 | 56 | dil_w | Horizontal dilation or special shift |
| 15 | 60 | pad_t | Top padding or input A pointer |
| 16 | 64 | pad_b | Bottom padding or input B pointer |
| 17 | 68 | pad_l | Left padding or A zero point |
| 18 | 72 | pad_r | Right padding or B zero point |
| 19 | 76 | wptr | WEIGHTS base + weight offset |
| 20 | 80 | bias_ptr | BIAS base + offset; zero if absent |
| 21 | 84 | mul_ptr | MUL base + offset; zero if absent |
| 22 | 88 | shift_ptr | SHIFT base + offset; zero if absent |
| 23 | 92 | q6_ptr | Q6 base + offset only with data and RELU6 |
| 24 | 96 | zx | Input zero point |
| 25 | 100 | zw | Weight zero point; also records zB in ADD |
| 26 | 104 | zy | Output zero point |
| 27 | 108 | out_h | Output height |
| 28 | 112 | out_w | Output width |

depth_mult, quant_params, op_index, label, slot lists and presence booleans exist in dictionaries/reports but are **not** additional blob fields. op_index is the TFLite index; layer_index is the serialized position, including a synthetic layer when present.

## Operation and activation codes

| op_type | Operation | Origin |
|---:|---|---|
| 1 | CONV_2D | TFLite |
| 2 | DEPTHWISE_CONV_2D | TFLite |
| 3 | FULLY_CONNECTED | TFLite |
| 4 | ADD | TFLite |
| 5 | MEAN | TFLite |
| 6 | SOFTMAX | TFLite |
| 7 | QUANTIZE | TFLite |
| 8 | RGB565_TO_RGB888 | Synthetic, inserted by Python |

ACT_NONE=0, ACT_RELU=1, ACT_RELU6=3. Unknown activations map to NONE. Not every kernel uses act: ADD and FULLY_CONNECTED do not apply fused activation in the inspected templates. run_layer dispatches codes 1–8 without explicitly rejecting unknown codes.

## Reused fields

| Operation | Python-generated reinterpretation |
|---|---|
| ADD | kh/kw=mulA/shiftA; stride_h/w=mulB/shiftB; dil_h/w=out_mul/out_shift; pad_t/b=ptrA/ptrB; pad_l/r=zA/zB |
| MEAN | kh/kw=mul/shift for sX/sY; stride_h=H×W; stride_w=1; pad_t=input_ptr |
| SOFTMAX | kh/kw=input_beta_mul/input_beta_left_shift; stride_h=diff_min=-128; stride_w=input_left_shift; pad_t=input_ptr |
| QUANTIZE | kh/kw=mul/shift for scale_in/scale_out; pad_t=input_ptr; zx/zy=zp_in/zp_out |
| RGB565_TO_RGB888 | flags=FORMAT_FLAG_ADDR=0; kh=FORMAT_RGB565=65; slots 0→1 |

Producing a field does not imply WAT uses it. MEAN recomputes H×W; SOFTMAX uses 7877 and shift 16 instead of generated multipliers; RGB565 treats flags as an address, not a mask. Read this producer-side table together with the runtime chapter.

## QUANTIZE flags

Bit 0: input UINT8=0, INT8=1. Bit 1: output INT8=0, UINT8=1.

| flags | Input | Output |
|---:|---|---|
| 0 | UINT8 | INT8 |
| 1 | INT8 | INT8 |
| 2 | UINT8 | UINT8 |
| 3 | INT8 | UINT8 |

For convolutions, those bits mean PADDING_SAME (1) and HAS_Q6 (2). Meaning depends on op_type. The unused legacy template still chooses UINT8 output using fixed layer index 67, diverging from this contract.

## Pointers and offsets

```text
w_off     + WEIGHTS_BASE → wptr
b_off     + BIAS_BASE    → bias_ptr  (if has_bias)
mul_off   + MUL_BASE     → mul_ptr   (if has_mulq6)
shift_off + SHIFT_BASE   → shift_ptr (if has_mulq6)
q6_off    + Q6_BASE      → q6_ptr    (if has_mulq6 and act=RELU6)

in_slot  → slot_bases[in_slot]  → in_ptr
out_slot → slot_bases[out_slot] → out_ptr
ADD: in_ptr comes from pad_t, validated against slot A's base.
```

params_blob.py resolves relative offsets and layout bases to absolute addresses WAT can use directly. Sizes/bases vary; addressing rules are shared. wptr is calculated even for weightless operations, whose kernels must ignore it. Not all kernels interpret a zero pointer as absence.

## Slots, shifts and host requirements

Three equally sized slots are aligned to 16 bytes. A logical slot is neither a tensor nor an exclusive per-layer region; storage is reused. slot_shift adjusts logical mapping for the synthetic layer. Quantization shift is separate: real_multiplier ≈ multiplier / 2³¹ × 2^shift, positive for left shift and negative for right shift.

Required exports are memory, run_mobilenetv2 called without arguments, and get_result_ptr returning an address. The current template returns i32 zero from run_mobilenetv2; the Python host ignores it. Output elements occupy one byte. RGB565 host format uses byte 65 at address 0; the WAT execution flag is at address 4.

A replacement template must preserve fields, semantics, endianness, data segments, exports and compatible numerical rules. Keeping 116 bytes but changing field order breaks the contract. The code neither negotiates ABI versions nor confirms template numerical equivalence.

