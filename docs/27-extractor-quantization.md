[English](27-extractor-quantization.md) | [Português (Brasil)](27-extractor-quantization.pt-BR.md)

# 27 — Integer quantization and per-channel blobs

[Index](README.md) · Source: [extractor/quantization.py](../extractor/quantization.py)

## Concepts and representation

A quantized value q represents `real = (q - zero_point) × scale`. For convolution accumulators, the desired per-channel ratio is `M[c] = input_scale × weight_scale[c] / output_scale`. The module produces integer multipliers, shifts, and RELU6 limits so WAT can operate without float scales in the interface.

## quantize_multiplier

Receives a real number converted to float. For zero, it returns `(0,0)`. It uses `math.frexp` to decompose `M = q × 2^exponent`, rounds `q × 2^31` with Python's `round`, and corrects the case equal to 2^31 by dividing by 2 and incrementing the exponent. It clamps the integer to `[INT32_MIN,INT32_MAX]`. Returns `(q31,exponent)`.

Example: M=0.25 gives q=0.5 and exponent=−1; q31=1073741824. Reconstruction is `(1073741824/2^31)×2^-1=0.25`. M=1 produces the same q31 with shift=1. A positive shift means amplification by a power of two; a negative shift means reduction. Multiplication rounding and saturation are implemented in WAT and are not completely determined by this pair.

There is no prior validation of M's finiteness or positivity. NaN/inf and invalid scales may cause exceptions or meaningless results; this is not a complete quantization schema.

## extract_quantization_parameters: operators with weights

Visits the original operators. In CONV and FC, `nfeat` comes from `weight_shape[0]`; in depthwise, from `[3]`. Operators with insufficient inputs/outputs, insufficient shape, or missing qparams are skipped. It uses the first input/output scale and the first output zero point; it preserves the weight scale array.

With one weight scale, it replicates the same M across all channels. With several, it uses up to `min(nfeat,count)` and repeats the last if scales are missing. It does not validate whether `QuantizedDimension` matches the assumed axis; qdim is retained in the report. It calculates `q6[c] = round(6/scale_out[c]) + zp_out`, using `np.round`; it may replicate or extend the array in the same way. Q6 is produced for these operators even when activation is not RELU6, although the pointer is enabled only for that activation.

Offsets are calculated before appending values: `len(mul_vals)*4`, `len(shift_vals)*4`, `len(q6_vals)*4`. The `mul_q6_off[op_idx]` map contains `(mul_offset,shift_offset,q6_offset,nfeat)`. It is not indexed by label or weight tensor: two operators sharing weights may have different requantization parameters.

## SOFTMAX path

Reads the input scale, fixes beta=1 and integer_bits=5. Calculates `input_left_shift = max(0,5-floor(log2(127*scale+1e-9))-1)`, quantizes `beta*scale`, appends one MUL and SHIFT without Q6, and records offsets with nfeat=1. The softmax builder also calculates these data.

**Actual limitation:** the observed WAT kernel does not use these parameters for its exponential calculation; it uses `(val-max)*7877 >> 16` and a fixed Q15 table. Thus, report 06 documents extracted values, but does not prove the kernel applies them. Do not interpret a correct multiplier table as a guarantee of softmax equivalence to TFLite.

```text
TFLite scales per operator/channel
                 │
                 ▼
 M = sX × sW / sY        q6 = round(6/sY) + zY
                 │                     │
                 ▼                     │
       quantize_multiplier             │
                 │                     │
          ┌──────┴──────┐              │
          ▼             ▼              ▼
       mul_vals      shift_vals      q6_vals
          │             │              │
          ▼             ▼              ▼
       dtype='<i4': 4 little-endian bytes per value
          │             │              │
          └─────────────┼──────────────┘
                        ▼
          blobs + mul_q6_off + records
```

Inputs are model-specific metadata; the module calculates integer parameters and serializes arrays. Outputs are blobs for MUL/SHIFT/Q6 regions and offsets for LayerParams. The int32 format and shift convention belong to the runtime. For SOFTMAX, the connection between calculated parameters and the kernel is incomplete, as described above.

## compute_add_quantization_params

Receives scales A, B, and Y. Defines `scale_common = 2*max(scale_a,scale_b)`. If both inputs are zero, output is zero, or common is zero, it returns six zeros and common. In the normal case, it quantizes A/common, B/common, and common/Y. Returns seven values `(mul_a,shift_a,mul_b,shift_b,out_mul,out_shift,scale_common)`. The builder puts them in repurposed geometric fields. It does not write to the global blobs.

## Return value and report

`extract_quantization_parameters` returns lists `mul_vals,shift_vals,q6_vals`, bytes `mul_blob,shift_blob,q6_blob`, map `mul_q6_off`, and `records`. All three arrays are serialized with `np.array(...,dtype='<i4').tobytes()`. `quantization_to_text` shows scales, ratios, arrays, offsets, and totals per operation; it returns a string for 06. It does not run network operations.

## Invariants and pitfalls

MUL and SHIFT must match channel by channel; byte offsets must point to 4-byte integers. Zero output scales may cause division by zero in this extractor even when another function has a fallback. Missing scales may omit records without an immediate error. Repeating the last scale is current behavior, not validation of arbitrary per-axis quantization. Kernels accumulate in i32 and have their own rounding rules; overflow and rounding differences require specific numerical tests.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
import math
import numpy as np
from extractor.tflite_utils import op_name, qparams_np, scale_scalar, tensor_shape_list, zp_scalar
```

### `quantize_multiplier` — signature

```python
def quantize_multiplier(real_multiplier: float)
```

### `extract_quantization_parameters` — signature

```python
def extract_quantization_parameters(model, subgraph)
```

### `compute_add_quantization_params` — signature

```python
def compute_add_quantization_params(scale_a, scale_b, scale_y)
```

### `quantization_to_text` — signature

```python
def quantization_to_text(extraction)
```

## Preserved technical material

The previous explanation is in [08-quantizacao.md](historico/08-quantizacao.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencias-e-limitacoes.md).
