[English](13-runtime-wat.md) | [Português (Brasil)](13-runtime-wat.pt-BR.md)

# 13 — WebAssembly templates and runtime

[Index](README.md) · [ABI](08-layerparam-v1-contract.md) · [Generator](32-extractor-wat-generator.md)

## Files and actual selection

There are three source templates: [mobilenet_int8_v1.wat](../wat/templates/mobilenet_int8_v1.wat), selected by drowsiness; the [local ImageNet template](../models/mobilenetv2_alpha035/wat/model_template.wat), selected by the other package; and [legacy model_template.wat](../wat/templates/model_template.wat), unreferenced by current manifests. The two active templates have identical contents at inspection. Selection comes from `runtime.wat_template`; there is no per-model kernel factory.

The template is a WebAssembly module with exported linear memory, base/size globals, integer math functions, kernels, and a dispatcher. It imports neither WASI nor TensorFlow. The generator inserts data segments. `run_mobilenetv2` is a fixed export name required by the host, although its body iterates over a list of operations described by parameters.

## Memory and control

```text
exported memory
  │
  ├── address 0: host RGB565 marker (65)
  ├── address 4: FLAG_BASE; 1 during run, 0 on completion
  ├── WEIGHTS / BIAS / MUL / SHIFT / Q6
  ├── PARAMS: base + layer_index × LP_SIZE
  └── SLOT0 / SLOT1 / SLOT2
                        │
                        ▼
                RESULT_BASE / RESULT_COUNT
```

Inputs are initialized data and an image written by the host. The runtime reads records and writes activations to slots; the output is a vector at the generator-defined base. Addresses and sizes are model-specific; flags and record offsets are shared. The comment beside FLAG_BASE mentions address 0, but the executed value is 4; this documentation follows the code.

`layerparam_base(layer_idx)` calculates `PARAMS_BASE + layer_idx*LP_SIZE`. `run_layer` reads op_type and dispatches 1–8. Unknown codes simply return from the function. `run_mobilenetv2` marks busy, iterates indices 0 through NUM_LAYERS−1, calls `run_layer`, clears busy, and returns i32 0. It does not check the original op_index or output tensor identity.

## Executed kernels

### CONV_2D

Reads the 29 fields and iterates output H/W, output channel, kernel positions, and input channels. Activation indexing is NHWC; weights are OHWI, with a block per output channel. Adds bias and `(x-zx)*(w-zw)` products in i32. Padding skips coordinates outside the valid area; stride and dilation enter row/column calculations. Applies `multiply_by_quantized_multiplier_3`, adds zy, applies RELU or RELU6 when act=1/3, and clamps to INT8. Bias, multiplier, and shift are read per channel without semantic validation of absence.

### DEPTHWISE_CONV_2D

Iterates output pixels and output channel; accesses activation at `((row*in_w+col)*cin + oc)` and weights at `((ki*kw+kj)*cout + oc)`. This direct association of `oc` with input assumes depth multiplier 1. Python records `depth_mult` but does not serialize it; there is no `input_channel=oc/depth_mult` calculation. Requantization/activation resemble convolution, and output is INT8.

### FULLY_CONNECTED

For each oc, initializes the accumulator with bias[oc], iterates ic from 0 to cin−1, reads `input[ic]` and `weight[oc*cin+ic]` as signed bytes, removes zero points, multiplies, and adds. Requantizes, adds zy, and clamps to INT8. The body does not read act; fused activation recorded by Python is not applied. It also does not implement arbitrary H×W×C flattening: it depends on cin being prepared correctly for the input tensor, as with vectors following MEAN in current models.

### ADD

Reads A/B pointers from pad_t/pad_b, zA/zB from pad_l/pad_r, multiplier/shift pairs from repurposed fields, and zy. For each of H×W×cin elements, it implicitly converts integers to a common scale, adds, applies output requantization, and clamps to INT8. It does not read act, check shapes, or broadcast. Padding field names here do not represent image padding.

### MEAN

For each channel, sums `x-zX` over H×W positions, divides by H×W with `i32.div_s` (truncation toward zero), requantizes with kh/kw, adds zY, and clamps to INT8. Recalculates spatial_size from H×W, although Python also records it in stride_h. It does not read axis/keep_dims and does not implement all TFLite MEAN cases. The template includes the `div_round_nearest` helper, but this kernel directly uses `i32.div_s`.

### QUANTIZE

Iterates out_h×out_w×cout. Flag bit 0 selects load8_s or load8_u; subtracts zx, applies kh/kw, and adds zy. Bit 1 selects UINT8 `[0,255]` or INT8 `[-128,127]` clamp, followed by store8. Python allocates this operator in place. In the legacy template, clamp depends on `layer_idx==67`; in both active templates it depends on flags.

### SOFTMAX: actual implementation

```text
cin INT8 logits
      │
      ▼
maximum logit
      │
      ▼
diff = ((val - max) × 7877) >> 16
      │
      ▼
exp_q15: discrete table for integer diff in [-11,0]
      │
      ▼
sum of exponential approximations
      │
      ▼
q = (exp_val × 256) / sum + zY
      │ unsigned integer division
      ▼
INT8 clamp and store8
```

Inputs are logits from the previous layer; the kernel uses a fixed factor, table approximations, and integer normalization. Outputs are INT8 bytes, subsequently converted by QUANTIZE in both models. Cin and zY are model data; 7877, shift 16, factor 256, and the table are runtime constants. `kh`, `kw`, `stride_h/w`, MUL, and SHIFT produced for softmax do not determine this calculation. Therefore, output scores should not be presented as calibrated probabilities or exact reproductions of the TFLite operator.

`exp_q15(x)` returns zero below −11, clamps positive inputs to zero, and uses this table for −11…0: `1,1,4,11,30,81,221,600,1631,4435,12055,32768`. These are approximate integer values of a scaled exponential. The effective logit scale is approximately 7877/65536, not necessarily the TFLite `input_scale`.

### RGB565_TO_RGB888

Reads flags as the marker address and kh as the sentinel. If memory[flags]==kh, reads little-endian `load16_u` and extracts R5=(pixel>>11)&31, G6=(pixel>>5)&63, B5=pixel&31. Expands R/B using `(v<<3)|(v>>2)` and G using `(v<<2)|(v>>4)`. Writes bytes in R,G,B order. Otherwise, copies H×W×3 RGB888 bytes from input to output. The current host uses this kernel only with the RGB565 sentinel and does not expose the copy branch in the manifest.

## Integer arithmetic helpers

`multiply_by_quantized_multiplier_3` is called by CONV, DW, FC, ADD, MEAN, and QUANTIZE kernels. It first applies a left shift if shift>0, then a rounded high multiply, and for shift<0 divides by a power of two. `saturating_rounding_doubling_high_mul_3` uses an i64 product, adds 2³⁰, performs arithmetic shift 31, and returns i32; it explicitly handles INT32_MIN×INT32_MIN as INT32_MAX. `rounding_divide_by_pot_3` returns x for exponent≤0; otherwise it uses nudge=2^(exponent−1), adding nudge−1 for x≥0 and nudge for x<0 before arithmetic shifting. Do not assume ties match every TFLite backend.

There are also `_2` variants, exported functions without suffixes, and `multiply_by_quantized_multiplier_softmax`. They are not all equivalent: exported `multiply_by_quantized_multiplier` performs high multiply and division by `-shift`, without the prior left shift used by `_3`. The `_2` variants use different threshold/remainder logic for division. These exports' presence does not mean the pipeline uses them. No test covers equivalence between variants.

## Exports and host use

| Family | Functions | Use |
|---|---|---|
| Essential | `memory`, `run_mobilenetv2`, `get_result_ptr` | Required by the runner |
| Bases and sizes | `get_weights_base`, `get_bias_base`, `get_mul_base`, `get_shift_base`, `get_q6_base`, `get_params_base`, `get_slot0_base`, `get_slot1_base`, `get_slot2_base`, `get_result_count` | Diagnostics; main host uses its own metadata |
| Control | `get_flag_base`, `is_ready_for_image` | Busy flag at 4; not queried by the synchronous runner |
| Kernels | `conv2d`, `depthwise_conv2d`, `fully_connected`, `add`, `mean`, `softmax`, `quantize`, `rgb565_to_rgb888`, `run_layer` | Called by dispatcher; quantize is also tested independently |
| Ranking | `get_top_class`, `get_top5` | Unused by adapters; read signed bytes |
| Math | three exported helpers without suffixes | Inspection/external use, not the main `_3` variant |
| Debug | `debug_memory(ptr,size)` | Sums squared signed bytes; does not print memory |

`get_top5` writes five `(index i32,value i32)` pairs in 40 bytes starting at the supplied pointer, initializing indices to −1 and values to −128. Both ranking exports read INT8, unsuitable for directly interpreting current UINT8 outputs. The project's Top-15 is calculated by the Python adapter using the correct dtype.

## Contract versus implementation limitations

The 29 fields can describe more cases than the kernels actually implement. Bias_ptr=0 does not safely represent optional bias in every kernel because loads occur without presence checks. Kernels do not validate each pointer against slot size. WASM may trap on access outside all memory, but does not detect reads from a wrong region still inside it. These restrictions are recorded in [99](99-inconsistencies-and-limitations.md); none was fixed in this documentation task.

