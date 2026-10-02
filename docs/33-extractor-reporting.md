[English](33-extractor-reporting.md) | [Português (Brasil)](33-extractor-reporting.pt-BR.md)

# 33 — Report persistence

[Index](README.md) · Source: [extractor/reporting.py](../extractor/reporting.py)

## Interface and responsibility

`save_report(path: Path,content: str)` performs two actions: creates the parent with `mkdir(parents=True,exist_ok=True)` and writes content using `path.write_text(...,encoding="utf-8")`. Returns None. The pipeline calls this helper after each formatter and after the adapter. The module does not format, calculate metrics, or decide which package is running.

```text
stage dict ──► specific formatter ──► string
                                         │
package.reports_dir / name ───────────────┤
                                         ▼
                                    save_report
                                         │ mkdir parent
                                         ▼
                                     UTF-8 file
```

Inputs are a path and text produced by other modules. The helper ensures the directory exists and writes; the output is a file. Content and directory belong to the package/stage; persistence policy is shared. The extension is not interpreted.

## Observable behavior

An existing file is replaced, not appended to. No newline, timestamp, header, checksum, or run metadata is added. Content ends exactly where the string ends. Type hints do not convert a string to Path; passing a string directly causes AttributeError at `.parent`. The pipeline correctly passes Path.

It does not catch OSError or implement a fallback. Report failure interrupts the stage and may prevent later generation/inference, even when the calculation producing the report finished. There is no atomic writing, history, lock, or cleanup of old reports. `exist_ok=True` allows an existing directory but does not resolve a file occupying the directory's location.

## Position in the current architecture

`ModelPipeline`, not the CLI, chooses names 02–12 and calls save_report. `reports_dir` comes from ModelPackage; current config has no global REPORTS_DIR. The function does not read previous reports: they are diagnostic outputs, not inputs for reconstructing the model. A complete run can recreate them; an interrupted run may leave a partially updated set.

## Other initialization files

`extractor/__init__.py` contains only a docstring about extraction tools. `pipeline/__init__.py` and `adapters/__init__.py` are empty. None registers classes, loads models, or creates extra global state. There is no `inference/__init__.py` or `tests/__init__.py` in the inspected tree. These observations avoid attributing nonexistent initialization effects to imports.

## Verified dependencies and signatures

The signatures below were extracted from the AST of the current file. Keyword-only arguments appear after `*`. Behavior is described in the preceding sections; type annotations do not replace validation.

```python
from pathlib import Path
```

### `save_report` — signature

```python
def save_report(path: Path, content: str)
```

## Preserved technical material

The previous explanation is in [14-reporting.md](historico/14-reporting.md). It preserves useful examples and derivations, but is not the reference for current paths, CLI, and variants. Where they differ, use this chapter and the [limitations register](99-inconsistencies-and-limitations.md).
