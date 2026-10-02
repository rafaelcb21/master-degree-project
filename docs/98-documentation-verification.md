# 98 — Documentation verification

[English](98-documentation-verification.md) | [Português (Brasil)](98-verificacao-documental.pt-BR.md)

[Index](README.md) · [Limitations and discrepancies](99-inconsistencies-and-limitations.md)

## Review scope

Analysis began on September 28, 2026, and the final review was completed on September 29, 2026. The application and test modules, both manifests, all three source templates, and existing reports were read. Both TFLite files were opened with the project's bindings to obtain shapes, types, scales, zero points, and operator and tensor counts. RAW files were inventoried by folder and size; a RAW file's color contents do not provide self-describing metadata, so their interpretation was documented according to the manifest and code.

## Verification criteria

- Local Markdown links, source paths, and files referenced by links.
- Closed code fences and aligned boxes in the new text diagrams.
- Coverage of each relevant Python file in the inventory and reference chapters.
- Order of the 29 fields, four-byte offsets, and the 116-byte LP_SIZE.
- Agreement between manifests and documented paths/templates.
- Shapes, dtypes, quantization, RAW counts/sizes, and memory layouts of both packages.
- Distinction between sources, artifacts, executed behavior, and proposed improvements.
- Preservation of the bodies of the 14 previous documents in `historico/`.
- Integrity of non-documentation files, compared by SHA-256 against the start of the task.

## Tests run

```powershell
.venv-models/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
```

Result: **7 tests, all passed**. The suite includes the WASM QUANTIZE kernel and tests of the contract, paths, synthetic layer, BGR conversion, INT8 interpretation, stable ranking, and binary classification. [Chapter 11](11-tests.md) explains the exact scope of each assertion.

Regenerating WAT/WASM or rerunning the 2,000 images was unnecessary for this documentation task. README metrics were read from existing reports, and model metadata was inspected directly. Tests create their own temporary files when needed.

## Results and limits

**49 Markdown files** were checked, including READMEs and historical documents, with **290 valid local links** and **52 text diagrams in current documents**.
The 14 historical bodies match the previous texts, allowing only line-ending normalization and the notice added before each body.
SHA-256 comparison confirmed **2,067 unchanged non-documentation files**.

Current chapters correct references to the single-model architecture and identify historical/legacy files. Chapter 99 records discrepancies without silently fixing them in the implementation. Functional code, manifests, TFLite files, templates, RAW files, and existing artifacts were preserved.

Documentation verification does not demonstrate mathematical equivalence between every kernel and TensorFlow Lite, or validate training data. It also does not turn the proposals in chapter 99 into existing features. This review aims to let readers identify the current behavior and its limits precisely.

The dates, counts, and test results above describe the original documentation review. They are not a claim that tests were rerun during the English translation.

