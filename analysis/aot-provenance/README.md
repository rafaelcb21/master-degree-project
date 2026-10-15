# AOT compilation provenance

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

The [generator](../../build_aot_with_provenance.py) records **source WASM → wamrc and command → produced AOT** during compilation. It does not retroactively attribute a source to the old AOT and does not establish flashing or board execution.

## Status on October 14, 2026

**Author confirmation:** the collection's AOT was generated under WSL on another computer, following the project README in full, including WAMR revision `12a42fde353e72ae1aa7c117e3d395340ab37413`. The author also supplied the original WASM and confirmed its use in generation. Both preserved copies are identical byte for byte, containing 510,943 bytes and SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`. **The source is identified through its hash and the author's confirmation; no contemporaneous compilation manifest was recovered.** See the [original file record](../experimental-method/original-wasm-report.json).

The historical `main/comando.txt` record contains a command and its output, but no hashes linking it to the collection's AOT. An additional attempt using this computer's Windows `wamrc 1.3.2`, during the audit, failed with:

```text
Error: llvm get target from triple (xtensa-pc-linux-ilp32) failed
```

That build's `LLVMConfig.cmake` reports LLVM 15.0.7 and targets `AArch64;ARM;Mips;RISCV;X86`, without Xtensa. The attempt is preserved in [provenance-report.json](reports/20261014T152736270631Z/provenance-report.json), with the [compiler log](reports/20261014T152736270631Z/compile-report.txt), input WASM and build configurations. Its status is **`failed`**, without a produced AOT hash. The firmware's existing AOT was not replaced.

**For a new compilation with a manifest, run the workflow in the environment that includes the Xtensa backend.** The collection's WSL environment belongs to the other computer; this machine's Windows failure does not describe that environment. Workflow tests passed with mocked compiler calls; this does not represent a new real ESP32 compilation.

## Generate a manifest on Windows

From the repository root, adjust the path to a compiler supporting Xtensa:

```powershell
.venv-models/Scripts/python.exe build_aot_with_provenance.py build --wamrc C:/toolchains/wamrc.exe
```

Alternatively, use the wrapper:

```powershell
./ESP32/cnn_webassembly_esp32/main/build_aot_windows.ps1 -Wamrc C:/toolchains/wamrc.exe
```

The default WASM is `models/drowsiness/generated/model.wasm`. For another file, use `--wasm path/model.wasm` or `-Wasm` in the wrapper. To include compiler/LLVM configuration or version records, repeat `--evidence path/file`. The wrapper accepts `-EvidenceFiles`.

## Generate on WSL/Linux

The Python script uses only the standard library. Run it in the environment where wamrc works:

```bash
cd /mnt/c/Users/rafae/Downloads/master-degree-project
python3 build_aot_with_provenance.py build --wamrc /path/to/wamrc
```

Do not pass a Linux executable to Windows Python. The [AOT guide](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.md) explains how to prepare a compiler compatible with the runtime.

## Recorded evidence

Each attempt creates a fresh directory in `analysis/aot-provenance/reports/<UTC>/`:

| File | Contents |
|---|---|
| `input.wasm` | Preserved copy of the WASM actually passed to the compiler |
| `output.aot` | Produced AOT; accepted only after successful compilation and version-3 header verification |
| `compile-report.txt` | Combined compiler output, including failures |
| `provenance-report.json` | SHA-256 hashes, sizes, wamrc version, exact arguments, working directory, UTC timestamps and status |
| `evidence-*` | Copies of additional files supplied through `--evidence`, with hashes |

The JSON records the wamrc executable hash and input/output hashes. The command explicitly sets `--target=xtensa`, `--target-abi=ilp32`, `--cpu=esp32`, `--cpu-features=-fp`, `--opt-level=3`, `--size-level=3`, `--bounds-checks=1` and `--stack-bounds-checks=1`.

Status **`compilation_verified`** requires compiler exit code zero, AOT version 3 and unchanged WASM/executable hashes during compilation. Existing directories cannot be reused. Failures retain status `failed` and are not presented as evidence of successful compilation.

## Verify and use in the next collection

```powershell
.venv-models/Scripts/python.exe build_aot_with_provenance.py verify analysis/aot-provenance/reports/RUN_ID/provenance-report.json
```

Verification compares archived copy hashes and sizes against the manifest and rejects failed attempts. This is a local integrity check, not a digital signature or independent document authentication.

After successful compilation, preserve the complete directory, use its `output.aot` in the firmware and record the flashed image hash and manifest ID with the new collection's CSV. The generator does not perform this firmware/collection step. To support portability, the desktop should execute `input.wasm` from the same directory.

The report is available in the web library in English and Portuguese; the methodology documentation links to this workflow. **The procedure, version and use of the original WASM are confirmed by the author; its hash and copy equality were verified. The historical manifest was not recovered. Instrumentation for new compilations has been implemented and tested.**
