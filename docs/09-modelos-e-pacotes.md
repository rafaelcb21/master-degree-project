[English](09-modelos-e-pacotes.md) | [Português (Brasil)](09-modelos-e-pacotes.pt-BR.md)

# 09 — Included models and packages

[Index](README.md) · [Drowsiness](../models/drowsiness/README.md) · [ImageNet](../models/mobilenetv2_alpha035/README.md)

## Comparison extracted from the files

| Property | drowsiness | mobilenetv2_alpha035 |
|---|---|---|
| Manifest name | Drowsiness MobileNetV2 | MobileNetV2 Alpha 0.35 ImageNet |
| Original file | model_int8_esp32.tflite | mobilenetv2_alpha035_quant.tflite |
| TFLite bytes | 618376 | 1925904 |
| Subgraphs/tensors | 1 / 175 | 1 / 175 |
| Input | [1,128,128,3] UINT8 | [1,224,224,3] UINT8 |
| Input scale / zero point | 0.003921508323401213 / 0 | 0.007843137718737125 / 127 |
| Output | [1,2] UINT8 | [1,1000] UINT8 |
| Output scale / zero point | 0.00390625 / 0 | 0.00390625 / 0 |
| Host RAW | Little-endian RGB565, 32768 bytes | BGR888, 150528 bytes |
| Synthetic layer / shift | RGB565_TO_RGB888 / 1 | none / 0 |
| Adapter | binary-folders | imagenet-topk |
| Discovered cases | 1000 + 1000 | 1 |
| TFLite / runtime layers | 67 / 68 | 67 / 67 |
| WASM pages in reports | 17 | 56 |

Both models have 35 CONV_2D, 17 DEPTHWISE_CONV_2D, 10 ADD, 2 QUANTIZE, 1 MEAN, 1 FULLY_CONNECTED and 1 SOFTMAX. int8 in a filename/template does not define I/O dtype: both FlatBuffers expose UINT8, with internal quantized operations and QUANTIZE at the boundaries.

## Input variants

```text
WITH SYNTHETIC LAYER — drowsiness    WITHOUT SYNTHETIC LAYER — ImageNet
RGB565 RAW                          BGR888 RAW
 ↓                                   ↓
BinaryFoldersAdapter reads bytes    ImageNetTopKAdapter swaps BGR → RGB
 ↓                                   ↓
SLOT0                               SLOT0
 ↓                                   │
synthetic RGB565_TO_RGB888            │
 ↓                                   │
SLOT1                                │
 ↓                                   ↓
first REAL TFLite op: QUANTIZE       first REAL TFLite op: QUANTIZE
```

In the first case, WAT expands RGB565; in the second, Python swaps B/R and writes RGB directly. Both feed the first real operation through the shared runner/slot protocol. The synthetic layer is absent from the original TFLite graph.

## What results establish

The drowsiness report has 2000 records, 1965 correct predictions, five invalid/tied cases, 98.25% accuracy and no processing errors. The ImageNet report ranks airliner first for its sole RAW, index 404, q=226 and score=0.8828125. These describe the existing runtime's execution. The test suite has neither a full TensorFlow Lite comparison nor evidence of accuracy outside these data.

Names/manifests indicate model purposes, but this flow does not provide complete training provenance, train/validation split, dataset licenses, hyperparameters or source checkpoint. Filenames cannot reconstruct that information. These results do not establish suitability for real driver monitoring.

## Shared sources and package independence

Drowsiness depends on a template outside its directory. ImageNet uses a local copy whose hash matched the active shared template in the original inspection. They can diverge; there is no automatic synchronization. The external img_mobilenetv2/aviao_uint8.raw copy does not participate in configured execution.

The earlier README referenced test/incompatible/a0397.raw, which was absent from the inspected tree. That reference was removed from operational instructions and recorded in chapter 99. The current state does not establish what happened to the file.

