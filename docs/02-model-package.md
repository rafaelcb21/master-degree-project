[English](02-model-package.md) | [Português (Brasil)](02-model-package.pt-BR.md)

# 02 — ModelPackage and path resolution

[Index](README.md) · Source: [pipeline/model_package.py](../pipeline/model_package.py)

## Object and place in the flow

ModelPackage is a frozen dataclass with `root: Path` and `config: ModelConfig`. Freezing prevents attribute reassignment but does not deeply freeze dictionaries within config. The CLI creates the object; the pipeline receives it and shares it with the adapter.

`MODELS_DIR = Path(__file__).resolve().parents[1] / "models"` anchors selection to the repository root. The CLI identifier is the directory name; model.name is a display description and can differ.

```text
--model drowsiness → MODELS_DIR / name → root
                                      ├─ model.toml → ModelConfig.load
                                      └─ ModelPackage(root, config)
                                           ├─ resolve(config.tflite) → source TFLite
                                           ├─ resolve(config.wat_template) → source WAT
                                           ├─ wat_path / wasm_path → generated/
                                           └─ reports_dir → reports/
```

The input is a name and optional models_dir. The module resolves paths and reads the manifest, returning a package without creating directories or compiling. Source names are package-specific; generated/model.* and reports/ are shared conventions.

## Methods, properties and errors

| API | Input | Result/behavior |
|---|---|---|
| `load(name="drowsiness", models_dir=MODELS_DIR)` | Name and directory | Resolves models_dir, appends name, requires root.parent == models_dir.resolve(), reads root/model.toml, returns dataclass |
| `resolve(path)` | Configured path | Returns (root / path).resolve(); existence is not required |
| `reports_dir` | Package state | root / "reports" |
| `wat_path` | Package state | root / "generated/model.wat" |
| `wasm_path` | Package state | Same path with .wasm extension |
| `validate_sources()` | Package state | Requires nonempty TFLite and template files; returns None |
| `available(models_dir=MODELS_DIR)` | Directory | Sorted list of loaded packages matching */model.toml |

validate_sources raises ValueError for missing/empty sources; filesystem access errors may propagate. It does not validate labels, tests, tensor size, WAT syntax or ABI identity. available does not call validate_sources: listing a package does not prove it can run. An invalid manifest stops the entire listing; errors are not collected per package. No manifests means an empty list.

## Actual path semantics

The parent restriction applies to the requested package name. Source resolution allows `..`, needed for the shared template, and absolute paths: Path / absolute uses the absolute path. “All paths are relative” describes current manifest conventions, not a restriction enforced by resolve. Symlinks are not validated as a security boundary either.

Drowsiness uses ../../wat/templates/mobilenet_int8_v1.wat, leaving models/drowsiness/ for the shared directory. That package cannot be moved independently without including the template or adjusting its manifest. ImageNet's selected template is under its own wat/ directory.

## Persistence and collisions

Properties do not create directories; WAT/WASM/report writers do. Concurrent executions of the same package share destinations and may interfere; different packages have different destinations. There is no locking, per-run temporary directory or versioning. Source/output paths are not compared to prevent a template from pointing at the generated artifact itself. Keep sources and destinations separate.

