[English](05-adapters.md) | [Português (Brasil)](05-adapters.pt-BR.md)

# 05 — Test adapters and registry

[Index](README.md) · Sources: [base.py](../adapters/base.py), [binary_folders.py](../adapters/binary_folders.py), [imagenet_topk.py](../adapters/imagenet_topk.py), [registry.py](../adapters/registry.py)

## Responsibility boundary

An adapter is the test Strategy: it adapts file organization and output semantics to the runner interface. It neither loads TFLite nor compiles or accesses Wasmtime memory. It receives the package and tensor metadata and returns bytes or Python records. The runner does not know class names or decide correctness.

```text
model.toml: test.adapter → registry.create_adapter(package)
                            ├─ binary-folders → BinaryFoldersAdapter
                            │                    folder labels, correctness/ties
                            └─ imagenet-topk → ImageNetTopKAdapter
                                               index labels, score ranking
Both implement TestAdapter.
```

The factory looks up ADAPTERS and instantiates the selected class with the package. Folder/class data are model-specific; the method protocol is shared. Unknown names raise ValueError listing alternatives. Registration is explicit, with no module scanning or entry points.

## base.py: types and methods

TestCase is a frozen dataclass with path: Path and label: int | None = None. It does not open files or validate labels. TestAdapter(ABC) stores package/config. Its four abstract methods prevent instantiating incomplete implementations.

| Method | Input | Output/responsibility |
|---|---|---|
| raw_files(path) | Package-supported relative/absolute path | Sorted immediate-directory files with case-insensitive .raw extension; error for missing directory or no RAWs |
| discover_cases() | Stored configuration | Iterable of TestCase, materialized with list by pipeline |
| prepare_input(case, input_info) | Case and metadata | Bytes to write into the slot |
| evaluate_output(case, output, output_info) | WASM output bytes | Domain result record |
| build_report(results) | Records/errors dictionary | Domain report string |
| decode_output(output, info) | Bytes, dtype, scale, zero point | NumPy (values, scores) pair |

decode_output uses np.frombuffer(..., dtype=info["dtype"]) and scores = (values.astype(float) - zero_point) * scale. It does not apply softmax, normalize by the sum or verify class count. Byte 0xff means −1 for INT8 and 255 for UINT8. Positive scalar scale preserves quantized-value order.

```text
discover_cases → TestCase list
  for each case:
    prepare_input → bytes → runner writes/runs/reads → output bytes
    → evaluate_output → results.records
  build_report(results) → text
```

The adapter prepares/interprets; the runner executes. Input formats and result semantics vary, while byte transfer is shared. The runner collects per-case exceptions; discovery failures occur before it.

## binary_folders.py: binary classification

discover_cases is a generator. Iteration requires exactly two classes, at least one dataset, and dataset labels included in the class labels. It visits datasets in TOML order and files in Path order. It does not require a dataset for each class, distinct labels or balanced sample counts. Each case receives its folder label.

prepare_input requires config.input_format == "rgb565" and reads the whole file without conversion or byte swapping. The runner checks dimensions/length. The synthetic WAT layer performs RGB565 conversion.

evaluate_output decodes output and requires len(values) == len(classes). It finds all indices equal to the maximum. Multiple winners or a score sum <= 0 make the result invalid: result=None, invalid=True, right=False. The current record does not use class −1. A unique winner yields classes[winner_index]["label"], regardless of the numeric index itself.

```text
output bytes + dtype/scale/zero point → values and scores
                                      → maximum and tied indices
                  ┌───────────────────────────┴────────────────────┐
           tie or sum <= 0                                  unique winner
           result=None                                      classes[index].label
           right=False                                      compare with case.label
                  └───────────────────────────┬────────────────────┘
                                     record and report accuracy
```

The output record contains file, label, result, invalid, right, quantized and scores. Class order/meaning belongs to the model; dequantization and validity criteria belong to the Strategy.

build_report lists classes, all records and a summary. Accuracy is 100 * correct / len(records), or zero for no records. Invalid cases count in the denominator; failures that prevented record creation do not. The pipeline appends the error list, not the adapter. Example: [200,55] with scale 1/256 and zp 0 gives 0.78125 and 0.21484375. In the current package, index 0 means label 1 (drowsy).

## imagenet_topk.py: discovery and labels

discover_cases loads UTF-8 JSON before listing RAWs. It requires a nonempty object whose entries each contain exactly two nonempty strings: [wnid, class_name]. Complete output-index coverage is checked only in evaluate_output. Synset syntax, semantic consistency with TFLite and name uniqueness are not checked. Cases have no ground truth.

top_k defaults to 15 and must pass isinstance(..., int) and positivity checks. There is no explicit upper limit: K above class count returns all indices through slicing. Python True passes the integer check; use a normal TOML integer.

## BGR/RGB preparation

RAW bytes are read as np.uint8 and must total input_info["elements"]. BGR uses reshape(-1,3)[:,::-1].copy().reshape(-1) to reverse channels per pixel; RGB keeps the order. There is no resize, rotation, cropping, header parsing or metadata. A renamed PNG is not a RAW file.

UINT8 tensors receive RGB pixels directly. INT8 uses fixed MobileNet preprocessing: real = pixel/127.5 - 1; q = clip(rint(real/scale + zero_point), -128,127), then np.int8 conversion. This does not automatically support other INT8 normalization schemes. np.rint rounds halfway cases to even.

## Ranking and report

```text
WASM output: N bytes / N classes
 → decode_output with the correct dtype
 → score[i] = (q[i] - zp) × scale
 → np.argsort(-scores, kind="stable")
 → first K indices
 → index / class_name / wnid / quantized / score
```

Ranking is descending, with ties preserving original index order. The current configuration uses Top-15. Class count and labels vary by model; ranking is generic. No ImageNet accuracy is calculated because cases lack ground truth.

Each record contains file and top; each item contains index, wnid, class_name, quantized and score. The report places the class name first, with other values on indented lines. Scores are runtime-dequantized values; current softmax implementation does not establish calibrated probabilities or exact TFLite equivalence.

## Adding an adapter

Implement the four abstract methods, register the class in ADAPTERS, set test.adapter and add required TOML data. The loader retains test as a dictionary, allowing new fields without pipeline changes. Pipeline restrictions on image geometry, dtype, slots and input/output counts still apply. adapters/__init__.py is empty; import side effects do not register adapters.

