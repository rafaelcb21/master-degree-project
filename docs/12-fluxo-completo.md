[English](12-fluxo-completo.md) | [Português (Brasil)](12-fluxo-completo.pt-BR.md)

# 12 — Complete flow and reading reports

[Index](README.md) · [Orchestration](04-model-pipeline.md) · [Package comparison](09-modelos-e-pacotes.md)

## Walkthrough: drowsiness

```text
python main.py --model drowsiness
 → model.toml → ModelPackage → BinaryFoldersAdapter
                               2000 TestCase objects with folder labels
 → model_int8_esp32.tflite: 67 operators / 175 tensors
 → graph → 3 logical slots → tensor_to_slot
   weights = 384608 bytes; bias = 28168 bytes; MUL/SHIFT/Q6
 → slot_bytes = 196608; PARAMS_BASE = 499360
   synthetic_count=1; slot_shift=1
 → 68 LayerParams → 7888 PARAMS bytes
 → SLOT0=507248; SLOT1=703856; SLOT2=900464
 → MEM_END=1097072 → 17 pages
 → shared template → generated/model.wat → model.wasm
 → 32768-byte RAW → SLOT0 → RGB565_TO_RGB888 → SLOT1
 → 67 real operations → two-element UINT8 output
 → adapter: index 0=label 1; index 1=label 0
 → reports/12-inferencia-wasm.txt
```

The pipeline computes these values from the package sources; existing reports confirm them. Artifacts contain 68 kernels including the synthetic operation. Weights, dimensions and case count vary by model; ABI, three slots and 65536-byte pages are shared.

## ImageNet variant

The other package has the same 67 TFLite operation types/counts but no synthetic layer. PARAMS_BASE=1792768, parameter region=7776 bytes, slot_bytes=602112; slot bases are 1800544, 2402656 and 3004768. MEM_END=3606880, requiring 56 pages. The adapter swaps BGR→RGB before writing 150528 bytes to SLOT0. Output has 1000 elements and yields Top-15; this adapter has no expected folder label.

## Catalog of 11 reports

All are under models/<name>/reports/. The current pipeline does not produce report 01.

| File | Content | Diagnostic question |
|---|---|---|
| 02-grafo.txt | Types, labels, upstream/downstream neighbors | Are residual dependencies present? |
| 03-alocacao-slots.txt | Logical input/output slots, in-place marker | Is storage reused while readers still need it? |
| 04-mapeamento-tensor-slot.txt | Tensor IDs, producers, pending entries, closure | Do all consumed tensors have storage? |
| 05-pesos-bias.txt | Offsets, shapes, dtypes, sizes | Was the expected constant extracted? |
| 06-quantizacao.txt | Scales, zero points, multipliers, shifts, Q6, offsets | Do per-channel scale ratios match the model? |
| 07-slot-bytes.txt | Nonconstant tensors and largest byte requirement | Which tensor determines slot memory? |
| 08-layout-parametros.txt | Blob bases and lengths | Do regions start where expected? |
| 09-layer-params.txt | Operation fields, slots, special parameters | Are ADD, QUANTIZE and the synthetic layer encoded correctly? |
| 10-params-blob.txt | Serialized records, pointers, padding | Which address will WAT actually read? |
| 11-layout-final-memoria.txt | Regions, ends, pages, unused space | Is there enough memory for slots and data? |
| 12-inferencia-wasm.txt | Per-RAW results, adapter summary, errors | Which cases were processed and how were they interpreted? |

## From symptom to candidate cause

```text
unexpected result
 ├─ RAW rejected? → 12: size/path/preparation
 ├─ trap? → 10/11: pointers and regions
 ├─ swapped classes? → manifest classes / JSON / channel order
 ├─ saturation? → 06/09: dtype, scale, zero point, flags
 └─ numerical difference? → WAT kernel + intermediate tensors
```

Reports let you trace symptoms from the host to binary representation. They identify candidates for investigation, not automatic proof of cause. Model sources determine expected data; the runtime determines mathematics/addressing. No errors in report 12 does not mean numerical TFLite equivalence.

## Regeneration and interpretation

A successful run can regenerate all 11 reports and both artifacts. There is no history or stale-file removal. Absolute paths in records make text differ across computers even if inferred bytes match. Documentation-only changes do not regenerate reports; an older heading in 09 may come from a previous artifact rather than current writer code.

