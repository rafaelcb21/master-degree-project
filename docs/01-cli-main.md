[English](01-cli-main.md) | [Português (Brasil)](01-cli-main.pt-BR.md)

# 01 — CLI: main.py

[Index](README.md) · Source: [main.py](../main.py)

## Purpose and dependencies

`main(argv=None)` is the sole entry point. It accepts an optional argument list for argparse; `None` uses process arguments. ModelPackage is imported when the module loads; ModelPipeline is imported only in the execution branch. Thus `--list-models` avoids importing NumPy, TFLite and Wasmtime through the pipeline, but still needs Python and tomllib/tomli to read manifests.

| Argument | Type/action | Default | Effect |
|---|---|---|---|
| `--model` | string | `drowsiness` | Directory name under models/ |
| `--list-models` | store_true | False | Lists directory names and model.name |
| `-h`, `--help` | automatic argparse option | — | Prints help and exits |

There is no --one, image filter, subgraph selector, compile-only mode, direct template selector or CLI top-K option. These choices belong to manifests or code. Listing takes precedence if both --list-models and --model are supplied.

```text
argv → ArgumentParser.parse_args
       ├─ --list-models → ModelPackage.available() → print packages → return 0
       └─ execution → ModelPackage.load(args.model)
                    → ModelPipeline(package).run() → return 0 unless an exception occurs
```

Text arguments select a branch, load a package and delegate execution. The result is an exit code or terminating exception. Model names vary by package; CLI control is generic. No image bytes pass through the CLI.

## Commands

```powershell
python main.py
python main.py --list-models
python main.py --model drowsiness
python main.py --model mobilenetv2_alpha035
python main.py --help
```

Run from the repository root so main.py can be found. When using the script's absolute path, package resolution remains independent of the working directory because MODELS_DIR is derived from __file__.

## Outputs and failures

The try block catches only OSError, ValueError and RuntimeError, writing `Erro: ...` to stderr through `parser.exit(1, ...)`. Normal listing/execution returns 0. `raise SystemExit(main())` propagates this to the operating system. argparse handles invalid arguments before the try block, normally exiting with code 2.

KeyError, TypeError and exceptions outside the caught hierarchy may produce tracebacks. Not every invalid manifest yields a friendly error. A missing manifest causes OSError; an unknown contract causes ValueError. The runner collects per-image failures and the pipeline raises RuntimeError after writing its report.

## Extension and invariants

A valid package directory and manifest require no main.py changes. Adding a model name does not add support for new operators. ModelPipeline.run() returns an inference dictionary, which the CLI ignores: printed messages and files are its user interface.

