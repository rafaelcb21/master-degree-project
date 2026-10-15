# Experimental methodology and traceability report — WASM / ESP32-CAM

[English](report.md) | [Português (Brasil)](report.pt-BR.md)

Audit date: **October 14, 2026**. Revision examined: `4804169`, together with the files present in the workspace on that date.

This report answers items (a)–(g) for the **drowsiness** case study. It includes the memory requirements of MobileNetV2 α0.35 for comparison. The audit consisted of inspecting code, configuration, build records, the dissertation and locally calculated hashes. No new benchmarks were run and no firmware was flashed to the board.

**Necessary distinction:** the dissertation describes a desktop experiment using Node.js; the current repository pipeline executes WASM using Python/Wasmtime. A configuration found today does not, by itself, establish the configuration used in an earlier data collection.

## Summary of answers

| Item | Finding | Scope of evidence |
|---|---|---|
| a — versions and interpreter | WAMR `1.3.2~2`; ESP-IDF `5.3.1`; **fast** interpreter enabled. Node.js `v22.19.0` is stated in the dissertation and is installed today. | Local lock file, configuration and build; historical Node version recorded in the text, without a benchmark log. |
| b — compilation | **Procedure, version and source WASM confirmed by the author:** AOT generation under WSL on another computer following the README; original WASM of 510,943 bytes, with its SHA-256 identified. Xtensa/ESP32 target, `--cpu-features=-fp`, optimization level 3 and size level 3; automatic bounds checks for 32-bit targets in that revision. Current WAT → WASM conversion: `wasmtime.wat2wasm`, package `49.0.0`. | Procedure and use of the WASM reported by the author; identity of both copies verified using SHA-256 and byte-by-byte comparison. No contemporaneous compilation manifest is available. |
| c — timing | ESP32: `esp_timer_get_time()` before/after the exported call. Includes RGB565 → RGB888; excludes network transfer and input copying. | Confirmed in the current host and WAT. The timer used in the Node experiment was not recovered. |
| d — images and camera | RAW files delivered over Wi-Fi/HTTPS; optional SPIFFS or PSRAM cache. The current host does not capture camera images. | Implemented path confirmed; a suggested methodological rationale appears below, subject to the author's confirmation. |
| e — sizes and memory | Drowsiness WASM: **514,564 bytes**; AOT: **528,564 bytes**; linear memory: **1,114,112 bytes**. The ESP32 allocator prioritizes PSRAM. | Current artifacts; allocation fallback exists. This is not a measurement of total RAM consumption. |
| f — same WASM | **Original desktop and ESP32 project copies are identical byte for byte:** 510,943 bytes, SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`. The author confirmed this file as the AOT generation input. | Copy identity verified; use in compilation confirmed by the author. Current regenerated artifacts differ from these originals. |
| g — warm-up | **It was not possible to determine whether the 0.170 s call was discarded**, or whether it was the first call. | The current WASM pipeline does not measure latency and does not discard warm-up calls. |

## a) Environment versions and execution mode

| Component | Value found | Source |
|---|---|---|
| Embedded WAMR | Espressif package `espressif/wasm-micro-runtime 1.3.2~2` | [dependencies.lock](../../ESP32/cnn_webassembly_esp32/dependencies.lock) |
| Revision reported by the component | `12a42fde353e72ae1aa7c117e3d395340ab37413` | `managed_components/espressif__wasm-micro-runtime/idf_component.yml` |
| ESP-IDF | `5.3.1` in the lock file; `v5.3.1-dirty` in the build description | Lock file and `build/project_description.json` |
| WAMR interpreter | **Fast**, normal loader; classic disabled | [sdkconfig](../../ESP32/cnn_webassembly_esp32/sdkconfig), also confirmed in `build/config/sdkconfig.h` |
| WAMR AOT | Enabled; AOT file version 3 | Configuration and binary header of `main.aot` |
| Historical Node.js | `v22.19.0`, according to the dissertation | `Dissertacao_Rafael_Braga_UNICO.tex`, lines 2262 and 2400 |
| Node.js installed during the audit | `v22.19.0` | Output of `node --version`; does not establish the version used in an earlier collection |
| Current desktop WASM runtime | Wasmtime/Python; installed package `49.0.0` | [wasm_inference.py](../../inference/wasm_inference.py), `.venv-models` metadata |

The relevant options are `CONFIG_WAMR_ENABLE_INTERP=y`, `CONFIG_WAMR_INTERP_FAST=y`, `CONFIG_WAMR_INTERP_LOADER_NORMAL=y` and `CONFIG_WAMR_ENABLE_AOT=y`. Including an interpreter in the firmware **does not mean that AOT execution uses that interpreter**.

The [host CMake file](../../ESP32/cnn_webassembly_esp32/main/CMakeLists.txt) embeds `main.aot` when that file exists; otherwise it selects `main.wasm`. In the preserved local build, `compile_commands.json` and `main.aot.S` indicate AOT embedding. This establishes the selection in the local build, not the identity of the firmware flashed in each experiment.

## b) Compilation options

**Author confirmation on October 14, 2026:** the collection's AOT was generated under **WSL on another computer**, following the [AOT generation README](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.md) in full, including its specified version/revision. The procedure and version are therefore recorded as **confirmed by the author's account**. The specified WAMR revision is `12a42fde353e72ae1aa7c117e3d395340ab37413`, compatible with the embedded component `1.3.2~2`.

The generation command followed, according to the guide, was:

```bash
"$WAMRC" \
    --target=xtensa \
    --cpu=esp32 \
    --cpu-features=-fp \
    --opt-level=3 \
    --size-level=3 \
    -o "$ESP_PROJECT/main/main.aot.new" \
    "$ESP_PROJECT/main/main.wasm"
```

The guide does not explicitly pass `--target-abi` or `--bounds-checks`. The historical command below is an additional record, distinct from the confirmation that the README procedure was followed.

**Update to item b:** the author supplied two preserved copies of the original WASM and confirmed that this file was used to generate the AOT. Both contain 510,943 bytes and have SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`, with byte-for-byte equality verified. The source WASM is therefore identified; its association with the compilation is supported by the author's confirmation. No contemporaneous generation manifest was recovered.

The [workflow with a provenance manifest](../aot-provenance/README.md) was implemented for future compilations. The Windows attempt during this audit failed because Xtensa support was unavailable **on this computer**; it does not characterize the WSL environment used for collection. That environment's absence on this machine does not invalidate the author's confirmation.

### wamrc record found

The [comando.txt file](../../ESP32/cnn_webassembly_esp32/main/comando.txt) preserves this command and its successful output:

```bash
./wamrc --target=xtensa --target-abi=ilp32 --cpu=esp32 \
  -o /mnt/c/Users/User/Downloads/main.aot \
  /mnt/c/Users/User/Downloads/main.wasm
```

| Option | Recorded value |
|---|---|
| Target architecture | `xtensa` |
| Target CPU | `esp32` |
| ABI | `ilp32` |
| Triple reported in the output | `xtensa-pc-linux-ilp32` |
| CPU features | Empty field in that output |
| Optimization level | `3`, reported by the compiler |
| Size level | `3`, reported by the compiler |
| Output format | AoT file |
| Bounds checks | Not explicit in the command |

In the source of the specified revision, `wamr-compiler/main.c` initializes the bounds-checking option in automatic mode; `core/iwasm/compilation/aot_llvm.c` enables memory checks by default for 32-bit targets. **The guide's command keeps bounds checks enabled by default for Xtensa/ESP32 in that revision.** This conclusion follows from the source and options of the procedure confirmed by the author; it is not a parameter recovered from the AOT or an inspection of the executable used on the other computer.

In the initially audited version, the Windows script contained `--target=xtensa --cpu=esp32 --cpu-features=-fp --opt-level=3 --size-level=3` and names `rust_drowsiness_trucker.wasm/.aot`; its presence does not establish that it generated `main.aot`. The [updated script](../../ESP32/cnn_webassembly_esp32/main/build_aot_windows.ps1) now calls the provenance generator and preserves the existing AOT. The [AOT guide](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.md) contains reproduction instructions, which must also not be confused with collection logs.

The procedure, compiler revision and use of the original WASM as input are confirmed by the author's account. The WASM hash was calculated from the preserved copies. No historical manifest simultaneously recorded the input, compiler and AOT hashes; a future manifest will document a new run, without constituting a contemporaneous record of the earlier collection.

### WAT → WASM conversion

The [current converter](../../pipeline/wasm_compiler.py) uses **`wasmtime.wat2wasm(wat_source)`**, reading UTF-8 text and writing the returned bytes. The installed package examined is `wasmtime 49.0.0`, consistent with `wasmtime>=49,<50` in [requirements.txt](../../requirements.txt).

This call has no architecture, CPU, optimization or bounds-checking flags: it converts the textual representation into a WebAssembly binary. Xtensa/ESP32 selection occurs later, during AOT compilation. Reproducing the current drowsiness WAT using this library produced **exactly the current desktop WASM**, verified by byte equality.

The tool/version used to convert the artifact for the historical Node experiment was not recovered. Therefore, the current conversion must not be retroactively attributed to that collection without additional records.

## c) How execution time was measured

### ESP32 — current implementation

The interval in [main.c](../../ESP32/cnn_webassembly_esp32/main/main.c) is:

```c
int64_t t0 = esp_timer_get_time();
int32_t status = call_wasm_i32(WASM_RUN_EXPORT);
row->inference_us = esp_timer_get_time() - t0;
```

`WASM_RUN_EXPORT` is `run_mobilenetv2`, including for drowsiness. The timing function returns microseconds; the CSV records `inference_us / 1000.0` in milliseconds, with three decimal places. The API unit is documented by [Espressif — ESP Timer, v5.3.1](https://docs.espressif.com/projects/esp-idf/en/v5.3.1/esp32/api-reference/system/esp_timer.html).

| Stage | Included in `inference_ms`? |
|---|---|
| Retrieve the image over the network or from the cache | No |
| Wait for the readiness handshake | No |
| Validate the input and copy RAW data into linear memory | No |
| Write the format flag | No |
| Function lookup and call through `wasm_runtime_call_wasm` | Yes |
| RGB565 → RGB888 conversion inside the module | **Yes** |
| QUANTIZE and remaining network operations | Yes |
| Locate/read the output, decide the class and write the CSV | No |
| Initialize, load and instantiate the runtime/module | No |

Conversion is included because the [model](../../models/drowsiness/model.toml) has `synthetic_layer = "rgb565_to_rgb888"`, the host writes the RGB565 flag and the WAT dispatcher calls this operation inside `run_mobilenetv2`.

The flow is: **network/cache → input copy → start timer → WAMR call + conversion + neural network → stop timer → output reading/classification**.

Download time is measured separately. In streaming mode, the current code includes attempts and retry waits in `download_us`. When input comes from SPIFFS or the PSRAM cache, `download_ms` is zero; this does not mean the initial download or cache read had no cost, only that they are not accounted for in this column during inference.

### Desktop

The current WASM is instantiated once with Wasmtime and called for each image, but **the current WASM loop has no timer**. Consolidation uses zero to indicate unused desktop timing; this does not represent instantaneous inference. See the [analysis conventions](../README.md).

For the Node.js measurement described in the dissertation, the script needed to identify the timing API, start/end points and inclusion of conversion and image copying was not found. These fields remain **unconfirmed**. The TFLite/Python baseline timer belongs to a different execution path and must not be used to describe the WASM/Node benchmark.

## d) Image delivery and absence of camera capture

The host implements Wi-Fi connectivity and **HTTPS** downloads of `.raw` files listed in [image_list.h](../../ESP32/cnn_webassembly_esp32/main/image_list.h), using Cloudinary URLs. The drowsiness configuration uses **128 × 128 pixels, RGB565, two bytes per pixel**, totaling **32,768 bytes per image**. The dissertation describes little-endian byte order.

The [cache](../../ESP32/cnn_webassembly_esp32/main/image_cache.c) supports persistence in **SPIFFS on flash** or storage in **PSRAM**. If there is insufficient RAM cache and only one round, network streaming is available as a fallback. The mode actually selected for each collection depends on that session's interaction/configuration; it cannot be determined solely from the existence of these code paths.

The implemented path does not use an SD card or receive image payloads over serial. Serial is used for monitoring and benchmark choices. **SPIFFS is board flash, not a memory card.**

The current firmware contains no `esp_camera_init` or `esp_camera_fb_get` initialization/capture calls. The `esp32-camera` dependency exists, but does not establish image capture. The reference to the camera in Chapter 2 may describe the hardware without implying its use in the experimental evaluation.

**Suggested methodological rationale, to be confirmed by the author:** previously selected, labeled images were used to compare platforms with controlled inputs, avoiding variations in lighting, framing, capture and exposure. The experiment therefore evaluates inference on files rather than complete live capture performance. The code confirms the use of files; it does not record the original motivation for this choice.

## e) Artifact sizes and memory allocation

The sizes below belong to the files present during the audit, not necessarily the files used in the dissertation's historical tables.

| Artifact / region | Bytes | KiB |
|---|---:|---:|
| Drowsiness — `models/drowsiness/generated/model.wasm` | 514,564 | 502.50 |
| Drowsiness — `ESP32/cnn_webassembly_esp32/main/main.aot` | 528,564 | 516.18 |
| Drowsiness — initial linear memory | **1,114,112** | **1,088.00** |
| MobileNetV2 α0.35 — `models/mobilenetv2_alpha035/generated/model.wasm` | 1,807,875 | 1,765.50 |
| MobileNetV2 α0.35 — initial linear memory | 3,670,016 | 3,584.00 |

No MobileNetV2 AOT was found in that model's current package. The audited `main.aot` belongs to the host configured for drowsiness; it must not be used as the MobileNetV2 AOT size.

### Drowsiness memory map

Final addresses are **inclusive**; the `END` field in the original report is exclusive.

| Region | Start → inclusive end | Bytes |
|---|---:|---:|
| Initial control/reserved region | 0 → 2,047 | 2,048 |
| WEIGHTS | 2,048 → 386,655 | 384,608 |
| BIAS | 386,656 → 414,823 | 28,168 |
| MUL | 414,832 → 443,003 | 28,172 |
| SHIFT | 443,008 → 471,179 | 28,172 |
| Q6 | 471,184 → 499,351 | 28,168 |
| PARAMS | 499,360 → 507,247 | 7,888 |
| SLOT0 | 507,248 → 703,855 | 196,608 |
| SLOT1 | 703,856 → 900,463 | 196,608 |
| SLOT2 | 900,464 → 1,097,071 | 196,608 |
| Unused space in the last page | 1,097,072 → 1,114,111 | 17,040 |

There are **24 alignment bytes** between the parameter regions. The initial region contains format and control flags; it is not entirely free. SLOT2 is 192 KiB: including unused page space in the diagram's rectangle does not increase the buffer size.

Source: [drowsiness final layout](../../models/drowsiness/reports/20261008T150239050848Z/11-layout-final-memoria.txt). The [generated WAT](../../models/drowsiness/generated/model.wat) declares 17 pages of 65,536 bytes. AOT memory metadata also totals **1,114,112 bytes**, represented internally as one unit of 1,114,112 bytes; this AOT representation must not be confused with 64 KiB WebAssembly pages.

### Where the data resides

| Object | ESP32 allocation/storage policy |
|---|---|
| WASM/AOT embedded in firmware | `.rodata.embedded` section, stored in the firmware image on flash |
| Mutable copy used by the loader | PSRAM (`MALLOC_CAP_SPIRAM \| MALLOC_CAP_8BIT`), with `malloc` fallback |
| Linear memory and WAMR allocations | Custom allocator requesting PSRAM; `malloc/realloc` fallback |
| RAW buffer and report text | Explicit PSRAM allocations |
| Persistent image cache | SPIFFS on flash |
| RAM image cache | PSRAM |

The host prioritizes PSRAM, but supports fallback; it would not be rigorous to state that every allocation occurred in PSRAM in every session without logs/address inspection. AOT may also require runtime-specific code allocations; its complete residency was not measured here.

`WASM_APP_HEAP_BYTES` is zero; `WASM_MODULE_STACK_BYTES` is 1 MiB and `WASM_EXEC_STACK_BYTES` is 32 KiB. These are runtime arguments/settings, not additional regions of the linear memory map; actual usage may depend on AOT/interpreted mode. On desktop, the runtime manages linear memory within process memory, without PSRAM.

**File size, linear memory and total RAM consumption are different measurements.** Consumption includes the artifact copy, metadata, stacks, buffers, cache, Wi-Fi and runtime. CSV fields `heap_used`/`psram_used` are differences in free memory before/after the call; zero values do not mean that the model occupies no memory.

## f) WASM identity and evidence of portability

### Identification of the collection's original WASM

The author provided these preserved files:

| Copy | Path | Bytes |
|---|---|---:|
| Desktop project | `C:/Users/rafae/Downloads/modelos/wasm-project/project_predict/main.wasm` | 510,943 |
| ESP32 project | `C:/Users/rafae/Downloads/dev/MESTRADO/github_repository/cnn_webassembly_esp32/main/main.wasm.txt` | 510,943 |

Both files are **identical byte for byte** and have the same SHA-256:

```text
b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13
```

Despite its `.txt` extension, the second copy contains a WebAssembly binary with header `00 61 73 6D 01 00 00 00`. The author confirmed that this file was used as the input for AOT generation on the other computer. Copy equality was verified directly; identification of the compilation input relies on the author's confirmation. See the [original file record](original-wasm-report.json).

**Text for the dissertation:**

> AOT generation used the original `main.wasm` file, containing 510,943 bytes, as input, as confirmed by the author. The identity of the copies preserved in the desktop and ESP32 projects was verified through byte-by-byte comparison and SHA-256 digest `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`, establishing complete equality. Compilation took place under WSL on another computer, following the procedure and WAMR revision specified in the project README. This identifies the source WebAssembly module of the AOT artifact and documents the correspondence between both module copies. The hash was calculated retrospectively from the preserved files; no contemporaneous compilation manifest was recovered.

### SHA-256 of local artifacts

| Artifact | SHA-256 |
|---|---|
| Current desktop drowsiness WASM | `7634ca88b88c73bb3451e85fe59046c72dcf592322e2c3faf5ede25313c7ac2f` |
| Current AOT in the ESP32 directory | `c1a1d9ec9f0428336f6f508e7640304b67a22c8bfca2dfc019e12fcd35646f78` |
| Current MobileNetV2 WASM | `84db5ad4e4c65a77327c8f40cdbac99352dcdd10691a48bbc3594603ff562cb2` |
| In-memory reconversion of the current WAT in the ESP32 directory | `d86e8dade226ce995e5450809d391ce1957fac005e3c99bb8f35c235239d7ff5` |

Reconversion of the WAT in the ESP32 directory produced **514,568 bytes**, whereas the desktop drowsiness WASM has **514,564 bytes**. Reconversion of the desktop's generated WAT reproduced its WASM byte for byte. The difference does not demonstrate a numerical error or a lack of portability; it demonstrates that the current artifacts do not allow binary identity to be certified through the available comparison.

The file `ESP32/cnn_webassembly_esp32/main/main.wasm` **does not exist in the current workspace**. The `.byte` payload of `build/main.aot.S` was reconstructed and has exactly the same hash as the current `main.aot`. This confirms the correspondence between the AOT and the local build's assembly source, without establishing which WASM produced the AOT or which firmware ran on the board during collection.

**Updated conclusion:** the original desktop and ESP32 project copies are binarily identical, and the author confirmed the file as the AOT generation input. Hashes of currently regenerated artifacts must not be used to identify this original WASM. Copy equality documents the sharing of the module between projects; earlier reports do not record runtime hashes enabling independent auditing of the file loaded for each call.

To support this claim in a new collection, preserve:

1. A canonical WASM, with size and SHA-256 calculated before execution.
2. The same hash recorded by the desktop and interpreted firmware; verify the embedded artifact and flashed image.
3. For AOT, a manifest linking **source WASM SHA-256 → wamrc command/version → AOT SHA-256 → firmware**.
4. Execution identifiers, configuration and input image hashes.

AOT is a different binary from WASM and will therefore have a different hash. In AOT mode, the correct claim is that the ESP32 executes a native artifact **derived from the same WASM**, when that derivation is traceable. Equality between the `.aot` and `.wasm` hashes must not be required.

Complete results are available in [artifacts-report.json](artifacts-report.json). To repeat the local audit of current artifacts:

```powershell
.venv-models/Scripts/python.exe analysis/audit_experimental_artifacts.py
```

This command does not measure performance or recover historical hashes; it only updates the JSON using the files present at that time.

## g) Desktop warm-up and the 0.170 s maximum

The dissertation reports Node.js `v22.19.0`, a mean of **0.041 s**, minimum of **0.036 s** and maximum of **0.170 s**, with 2,000 images. The rounded maximum/mean ratio is approximately **4.15**.

This maximum alone **does not establish** JIT compilation during the first call: sample order, the timed interval and runtime state would need to be identified. Compilation/tiering, caches, scheduling and other factors can affect latency. The [V8 WebAssembly compilation pipeline documentation](https://v8.dev/docs/wasm-compilation-pipeline) describes Liftoff/TurboFan and different compilation times; attributing the maximum to JIT must therefore be treated as a hypothesis, not an observed result.

**Answer about discarding: unconfirmed.** The Node timing script, sequence of individual times and warm-up record were not found. There is no basis for stating that the first run was discarded or that the maximum belongs to the first run. The current WASM/Python path has no separate warm-up, does not discard cases and does not record latency; this does not resolve the historical Node behavior.

Wording consistent with the available evidence:

> The desktop experiment recorded a mean time of 0.041 s and a maximum of 0.170 s. Available records do not establish whether prior warm-up occurred or whether the first call was discarded. Consequently, initialization and compilation effects cannot be retrospectively separated from other sources of latency variation.

For a new measurement, record loading/compilation/instantiation, the first call and calls after a warm-up protocol defined before collection separately. Preserve individual times in execution order and state the number of warm-up calls, discarded calls and final sample size. Do not retrospectively discard the maximum simply because it exceeds the mean.

## Evidence and outstanding items for the dissertation

| Outstanding item | Evidence needed |
|---|---|
| Historical Node timer and measurement boundaries | Executed script and Node commands/options |
| Warm-up and discarding | Warm-up code and original timing sequence |
| Binary identity across platforms | WASM used in each collection, hashes and execution manifest |
| Contemporaneous AOT generation record | Source WASM identified by SHA-256 and its use confirmed by the author; automatic compilation manifest not recovered |
| Physical memory actually used | Allocation/address log or collection instrumentation |
| Original reason for not using the camera | Author's methodological confirmation |

The dissertation was examined at `C:/Users/rafae/Downloads/latex-mestrado-2/Dissertacao_Rafael_Braga_UNICO.tex` (lines 2234–2493); that external file was not modified. Code/build references in this report identify the audit sources, including formats that Research Explorer does not make available for reading.
