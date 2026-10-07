# Compile WASM to AOT in WSL and run it on ESP32

[English](README_AOT_WSL.md) | [Português (Brasil)](README_AOT_WSL.pt-BR.md)

This guide explains how to prepare the **wamrc** compiler in Ubuntu/WSL, convert `main.wasm` into `main.aot` for ESP32, and embed the result in the firmware in this directory. ESP-IDF can remain installed on Windows.

**Scope:** classic ESP32, `esp32` target, Xtensa architecture. Do not reuse this guide's CPU commands for ESP32-S3 or ESP32-C3/C6 without adjustments. This procedure is independent of the Python pipeline.

> This guide was prepared from local project files and the cited references. Installation, compilation, and flashing commands were not run while preparing this document.

## Contents

1. [Understand the workflow](#1-understand-the-workflow)
2. [Check project versions](#2-check-project-versions)
3. [Prepare WSL](#3-prepare-wsl)
4. [Obtain compatible WAMR sources](#4-obtain-compatible-wamr-sources)
5. [Build LLVM with Xtensa](#5-build-llvm-with-xtensa)
6. [Build wamrc](#6-build-wamrc)
7. [Generate main.aot](#7-generate-mainaot)
8. [Build and flash the firmware](#8-build-and-flash-the-firmware)
9. [Workflow for subsequent models](#9-workflow-for-subsequent-models)
10. [Troubleshooting](#10-troubleshooting)
11. [References](#11-references)

## 1. Understand the workflow

```text
Tool preparation, once per environment/version:
Compatible WAMR + LLVM with Xtensa → Linux wamrc

For each model:
main.wasm → wamrc in WSL → main.aot
                              ↓
                 ESP-IDF on Windows → firmware → ESP32
```

| Item | Location / execution environment | Purpose |
|---|---|---|
| LLVM with Xtensa | WSL Linux filesystem | Backend used by the compiler |
| `wamrc` | Ubuntu/WSL | Compiles WASM into target code |
| `main.wasm` | Windows project's `main/` folder | Compiler input; can also be interpreted |
| `main.aot` | Windows project's `main/` folder | AOT artifact embedded in the firmware |
| ESP-IDF | Windows ESP-IDF terminal | Builds and flashes the firmware |
| Embedded WAMR | ESP32 | Loads and runs the module |

The `wamrc` built on Linux is a Linux executable, not `wamrc.exe`.
AOT contains code for the **selected target**, not for the computer running the compiler. It still depends on runtime compatibility.

The **PowerShell**, **WSL/Bash**, and **ESP-IDF terminal** labels indicate where each command runs. A trailing `\` continues a command in Bash; it is not PowerShell's line continuation character.

## 2. Check project versions

Open **PowerShell**:

```powershell
Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
Get-Content dependencies.lock
Get-Content managed_components\espressif__wasm-micro-runtime\idf_component.yml
```

In the copy used to write this guide:

| Setting | Observed value |
|---|---|
| ESP-IDF target | `esp32` |
| ESP-IDF recorded in lockfile | `5.3.1` |
| WAMR component | `espressif/wasm-micro-runtime 1.3.2~2` |
| Repository reported by component | `https://github.com/espressif/wasm-micro-runtime.git` |
| `repository_info.commit_sha` | `12a42fde353e72ae1aa7c117e3d395340ab37413` |
| Runtime `AOT_CURRENT_VERSION` | `3` |

Local sources: [dependencies.lock](dependencies.lock), [component manifest](managed_components/espressif__wasm-micro-runtime/idf_component.yml), and [core/config.h](managed_components/espressif__wasm-micro-runtime/core/config.h).

**Use the commit reported by the component as the reference for building wamrc.** Selecting the latest branch or a similarly numbered tag does not guarantee a match with the installed package. The `~2` suffix alone does not reveal which files or patches changed.

The [main/idf_component.yml](main/idf_component.yml) manifest allows a version range. The lockfile records the resolved version in this copy. If you update the component, check the installed manifest again before reusing the compiler. Do not edit files inside `managed_components` to fix compatibility.

## 3. Prepare WSL

### 3.1. Install or check Ubuntu

**PowerShell:**

```powershell
wsl --list --verbose
```

If Ubuntu already appears with `VERSION 2`, use that installation. If WSL is not installed, run **PowerShell as administrator**:

```powershell
wsl --install -d Ubuntu
```

Restart if requested and open Ubuntu to create a Linux username and password.
Then enter it:

```powershell
wsl -d Ubuntu
```

If your distribution has another name, use the name displayed by `wsl --list --verbose`. These steps follow the [WSL installation documentation](https://learn.microsoft.com/en-us/windows/wsl/install).

### 3.2. Check memory and disk space

**WSL/Bash:**

```bash
free -h
df -h ~ /mnt/c
```

**PowerShell, in another window:**

```powershell
Get-PSDrive C
```

Plan for tens of GB of free space for LLVM sources and artifacts. Exact usage depends on the build. Both Linux and the Windows drive hosting the distribution need sufficient free space.

Start with **one compilation job**. This reduces simultaneous RAM use but does not guarantee that an individual linking step fits in available memory.

Optionally adjust `%UserProfile%\.wslconfig`. Example for a machine with enough RAM to allocate 8 GB to WSL:

```ini
[wsl2]
memory=8GB
processors=2
swap=4GB
```

Preserve any other existing settings and leave memory for Windows. Save open work in WSL before applying:

**PowerShell:**

```powershell
wsl --shutdown
wsl -d Ubuntu
```

This stops all running distributions. See the [WSL configuration reference](https://learn.microsoft.com/en-us/windows/wsl/wsl-config).

### 3.3. Install dependencies

**WSL/Bash:**

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git ccache \
    python3 python3-pip python3-venv zlib1g-dev ca-certificates file
```

Check:

```bash
gcc --version
cmake --version
ninja --version
git --version
python3 --version
```

Use `sudo` to install packages. Run the builds in subsequent steps as your Linux user.

## 4. Obtain compatible WAMR sources

Keep sources and builds in your Linux home directory. Access the Windows project only to read the WASM and deliver the AOT.

**WSL/Bash, fresh installation:**

```bash
mkdir -p "$HOME/toolchains"
git clone https://github.com/espressif/wasm-micro-runtime.git \
    "$HOME/toolchains/wamr-esp32-1.3.2-r2"
cd "$HOME/toolchains/wamr-esp32-1.3.2-r2"
git checkout --detach 12a42fde353e72ae1aa7c117e3d395340ab37413
git rev-parse HEAD
```

**Expected result:** the last command prints the commit above. A `detached HEAD` state is expected because the tool version is pinned.

If the folder already exists, do not clone over it: enter it and inspect `git status --short` and `git rev-parse HEAD`. Preserve local changes. Proceed only when it represents the intended revision.

Define a variable for the next commands:

```bash
export WAMR_ROOT="$HOME/toolchains/wamr-esp32-1.3.2-r2"
test -f "$WAMR_ROOT/wamr-compiler/CMakeLists.txt"
test -f "$WAMR_ROOT/build-scripts/build_llvm.py"
```

The `test` commands print nothing on success. If checkout fails or files are absent, resolve that before building. Do not silently substitute the latest branch for the commit.

## 5. Build LLVM with Xtensa

This is the longest step. The distribution's standard LLVM does not necessarily include the Xtensa backend required for ESP32.

In the project's revision, `build_llvm_xtensa.sh` installs Python requirements with `pip --user` and calls `build-scripts/build_llvm.py --platform xtensa`.
Here, call that same Python script directly using a virtual environment to avoid conflicts with Ubuntu's managed Python.

**WSL/Bash:**

```bash
cd "$WAMR_ROOT"
python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install -r build-scripts/requirements.txt

export CMAKE_BUILD_PARALLEL_LEVEL=1
set -o pipefail
python build-scripts/build_llvm.py --platform xtensa \
    --extra-cmake-flags="-DLLVM_PARALLEL_LINK_JOBS=1" \
    2>&1 | tee llvm-build.log
```

Check the exit code **immediately after the command**:

```bash
echo $?
```

**Expected result: `0`.** With `pipefail`, a build failure is not hidden by a successful `tee`.

`CMAKE_BUILD_PARALLEL_LEVEL=1` limits the parallelism of `cmake --build`, used by the script. The LLVM option limits linking jobs for the Ninja generator.
See the [CMake reference](https://cmake.org/cmake/help/latest/envvar/CMAKE_BUILD_PARALLEL_LEVEL.html).

In this revision, the script:

- Fetches Espressif LLVM, branch `xtensa_release_15.x`.
- Enables `LLVM_EXPERIMENTAL_TARGETS_TO_BUILD=Xtensa`.
- Builds and packages the libraries.
- Replaces the build folder with package contents at completion.

After success, `core/deps/llvm/build` may therefore contain a packaged SDK without `build.ninja`. This differs from an interrupted build.

Check the result:

```bash
find "$WAMR_ROOT/core/deps/llvm/build" -name LLVMConfig.cmake
git -C "$WAMR_ROOT/core/deps/llvm" rev-parse HEAD
```

Record the LLVM commit: the branch used by the script may change over time. Preserve the commit and log to reproduce the exact environment.
These details come from the [script installed in the project](managed_components/espressif__wasm-micro-runtime/build-scripts/build_llvm.py).

**If an error occurs, do not proceed to wamrc.** Consult troubleshooting.

## 6. Build wamrc

The wamrc build folder is separate from the LLVM build folder.

**WSL/Bash:**

```bash
cmake -S "$WAMR_ROOT/wamr-compiler" \
    -B "$WAMR_ROOT/wamr-compiler/build-esp32" \
    -G Ninja -DCMAKE_BUILD_TYPE=Release

cmake --build "$WAMR_ROOT/wamr-compiler/build-esp32" --parallel 1
```

During configuration, check the `Using LLVMConfig.cmake in:` message.
It should point to LLVM under `$WAMR_ROOT/core/deps/llvm/build`.

Do not configure `WAMR_BUILD_TARGET=XTENSA` when building the Linux tool: the wamrc executable must run on the computer. Select the AOT target later with `--target=xtensa`.

Check:

```bash
export WAMRC="$WAMR_ROOT/wamr-compiler/build-esp32/wamrc"
test -x "$WAMRC"
file "$WAMRC"
"$WAMRC" --target=help
```

**Expected results:**

- `file` identifies a Linux ELF executable.
- The target list includes `xtensa`.

If Xtensa is missing, check which LLVM CMake found. Do not proceed with a compiler that only accepts x86/ARM.

## 7. Generate main.aot

### 7.1. Point to the Windows project

**WSL/Bash:**

```bash
export ESP_PROJECT="/mnt/c/Users/rafae/Downloads/master-degree-project/ESP32/cnn_webassembly_esp32"
test -s "$ESP_PROJECT/main/main.wasm"
ls -lh "$ESP_PROJECT/main/main.wasm"
```

The Windows path `C:\Users\rafae\...` corresponds to `/mnt/c/Users/rafae/...` in this WSL configuration. Adjust the variable if you move the project. Quote paths containing spaces.

The input must be a **binary WASM**, not renamed WAT text. This guide starts with an already generated `main.wasm`.

### 7.2. Compile for ESP32

**WSL/Bash:**

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

| Option | Purpose |
|---|---|
| `--target=xtensa` | Generates code for the classic ESP32 architecture |
| `--cpu=esp32` | Selects the target CPU |
| `--cpu-features=-fp` | Preserves the floating-point setting from this project's existing AOT script |
| `--opt-level=3` | Sets optimization explicitly |
| `--size-level=3` | Sets size optimization explicitly |
| `-o ...main.aot.new` | Generates a candidate before replacing the artifact in use |

`-fp` disables generation with the Xtensa backend's floating-point coprocessor option. It does not mean every ESP32 lacks an FPU. If you change this choice for an experiment, record it with the results.

The command follows the options in the [existing AOT script](main/build_aot_windows.ps1). That PowerShell script expects `wamrc.exe` and uses old artifact names; **it is not the script run in this WSL procedure**.

The command omits `--target-abi=ilp32`: this guide uses that compiler's default for Xtensa rather than carrying over an unnecessary historical option.
It also omits `--enable-multi-thread`: the C host's pthread does not require threads inside the WebAssembly module. If the WASM itself uses shared memory/atomics, both compiler and runtime must be configured for that contract.

### 7.3. Check the candidate before replacing the artifact

Run only if the previous compilation succeeded:

```bash
python3 - "$ESP_PROJECT/main/main.aot.new" <<'PY'
import pathlib
import struct
import sys

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
if len(data) < 8 or data[:4] != b"\x00aot":
    raise SystemExit("Arquivo sem cabecalho AOT valido")
version = struct.unpack_from("<I", data, 4)[0]
print(f"Arquivo: {path}\nBytes: {len(data)}\nVersao AOT: {version}")
if version != 3:
    raise SystemExit("Versao diferente de AOT_CURRENT_VERSION=3 deste runtime")
PY
```

This check verifies the header and format version. It **does not replace loading and running on the board**, or demonstrate numerical equivalence between AOT and the interpreter. Diagnostic strings in this example remain in Portuguese to preserve the original command.

After checking, preserve the previous AOT and put the candidate in place:

```bash
if [ -f "$ESP_PROJECT/main/main.aot" ]; then
    cp -p "$ESP_PROJECT/main/main.aot" \
        "$ESP_PROJECT/main/main.aot.backup-$(date +%Y%m%d-%H%M%S)"
fi
mv "$ESP_PROJECT/main/main.aot.new" "$ESP_PROJECT/main/main.aot"
ls -lh "$ESP_PROJECT/main/main.aot"
sha256sum "$ESP_PROJECT/main/main.wasm" "$ESP_PROJECT/main/main.aot"
```

The AOT is already in the Windows folder. You do not need to copy it from another window. Record hashes, WAMR/LLVM commits, and compiler options to identify what was measured in each experiment.

## 8. Build and flash the firmware

Use a **Windows ESP-IDF terminal** with the project's version environment activated. Its Python and tools belong to ESP-IDF.

```powershell
Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
idf.py --version
Get-Item main\main.wasm, main\main.aot
```

### 8.1. Configure the host and runtime

Edit:

- [main/host_config.h](main/host_config.h): Wi-Fi, input, output, exports, and limits.
- [main/image_list.h](main/image_list.h): Cloudinary URLs and labels.
- See [HOST.md](HOST.md) for the complete contract and measurement descriptions.

Check the SDK:

```powershell
Select-String -Path sdkconfig -Pattern '^CONFIG_IDF_TARGET=','^CONFIG_WAMR_ENABLE_AOT=','^CONFIG_WAMR_ENABLE_INTERP=','^CONFIG_SPIRAM=','^CONFIG_MBEDTLS_CERTIFICATE_BUNDLE='
```

In this copy, the target is `esp32` and all four options are enabled.
To change them:

```powershell
idf.py menuconfig
```

Use the `/` search for `WAMR_ENABLE_AOT`; the option is **AOT** in the **WASM Micro Runtime** menu. Keep the interpreter enabled to compare modes.
The current host uses PSRAM and the certificate bundle.

### 8.2. Embed AOT and build

[main/CMakeLists.txt](main/CMakeLists.txt) already selects the artifact:

- If `main/main.aot` exists: embeds AOT and defines `MODEL_MODULE_IS_AOT=1`.
- Otherwise: embeds `main/main.wasm` and defines `MODEL_MODULE_IS_AOT=0`.

You do not need another `target_add_binary_data` or manual macro changes.
Reconfigure after creating, removing, or changing the artifact type:

```powershell
idf.py reconfigure
idf.py build
```

Flash only if the build succeeds. Adjust the port:

```powershell
idf.py -p COM5 flash monitor
```

Look for these messages in the monitor (the firmware logs remain in Portuguese):

```text
Artefato embutido selecionado no build: AOT
WASM instanciado.
```

The second message uses the runtime's generic name even for AOT.
After the benchmark, access the CSV at `http://<esp32-ip>:80/report`, or the configured port/path. Exit the monitor with `Ctrl+]`.

### 8.3. Find the ESP32 IP address and open the report

1. In the **ESP-IDF terminal**, enter the project folder and open the serial monitor:

   ```powershell
   Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
   idf.py -p COM3 monitor
   ```

   `COM3` was the port identified for this board. If `could not open port` appears, check the monitor's `Available ports` list or **Ports (COM & LPT)** in Windows Device Manager and adjust the command. Close other programs using the same port.

2. Find the Wi-Fi connection message. Example observed on this board:

   ```text
   wi-fi: Conectado ao Wi-Fi. IP: 192.168.0.24
   ```

   The address may also appear on the `esp_netif_handlers: sta ip:` line.
   If you missed these messages, restart the board with the monitor open to see the connection again. This also restarts the benchmark.

3. Replace `<esp32-ip>` with the displayed address. For the example above, paste this into your browser:

   ```text
   http://192.168.0.24/report
   ```

   With default port 80, this is equivalent to `http://192.168.0.24:80/report`.
   If you changed `REPORT_HTTP_PORT` or `REPORT_HTTP_URI` in `host_config.h`, use the configured values.

4. With the current host, wait for all images to finish and for the `Servidor HTTP iniciado` message before accessing the report. The complete CSV is available only after the benchmark. Keep the board powered and connected: the report resides in memory and is lost on restart.

The computer must be able to reach ESP32 over the network; normally, connect both to the same local network without device isolation. `ipconfig` shows **the computer's** addresses, not the board's assigned IP. `192.168.0.24` is a real example from this session and may change after reconnection; always check the monitor.

**If `Checksum mismatch between flashed and built applications` appears:**
the board's firmware differs from the local build. `monitor` only observes execution; it does not flash new code. To update, exit with `Ctrl+]`, check `host_config.h`, and run:

```powershell
idf.py build
idf.py -p COM3 flash monitor
```

Flash only if the build succeeds. Then check the IP again and wait for the updated firmware's benchmark.

### 8.4. Return to interpreted mode for comparison

In the **ESP-IDF terminal**, preserve AOT under a name CMake does not recognize:

```powershell
Rename-Item -LiteralPath main\main.aot -NewName main.aot.disabled
idf.py reconfigure
idf.py build
idf.py -p COM5 flash monitor
```

If `main.aot.disabled` already exists, choose another name before renaming.
The log should show `WASM`. To return to AOT, restore the name `main.aot`, reconfigure, and build again.

Use the same source WASM, images, and host settings for comparisons.
A new `main.wasm` **does not update** AOT automatically.

## 9. Workflow for subsequent models

Once LLVM and wamrc are ready, you do not need to rebuild them for each image or new WASM compatible with the same runtime.

1. Place the new `main.wasm` in `main/`.
2. Adjust the host headers to that module's contract.
3. Open WSL and restore the variables below.
4. Repeat [AOT generation and verification](#7-generate-mainaot).
5. In the ESP-IDF terminal, reconfigure, build, and flash.

**WSL/Bash, in a new session:**

```bash
export WAMR_ROOT="$HOME/toolchains/wamr-esp32-1.3.2-r2"
export WAMRC="$WAMR_ROOT/wamr-compiler/build-esp32/wamrc"
export ESP_PROJECT="/mnt/c/Users/rafae/Downloads/master-degree-project/ESP32/cnn_webassembly_esp32"
test -x "$WAMRC"
```

The virtual environment was needed for the script that prepares LLVM.
It does not need to be activated to run the wamrc binary.

## 10. Troubleshooting

### The .sh file opens and closes a window on Windows

Open Ubuntu with `wsl -d Ubuntu` and run Bash commands there. Windows `.sh` file associations do not confirm that a build ran.

### Python reports externally-managed-environment

Use the virtual environment from step 5. You do not need to install packages in global Python or use `--break-system-packages`. Calling the Python script directly avoids the old wrapper's `pip --user`.

### Interrupted build, Killed, or WSL out of memory

Check `free -h`, the log, and, when available, `dmesg -T` for OOM signs.
Reduce parallelism and adjust WSL resources according to physical RAM.

If the LLVM build was interrupted **and still has build.ninja**, resume:

**WSL/Bash:**

```bash
test -f "$WAMR_ROOT/core/deps/llvm/build/build.ninja"
cmake --build "$WAMR_ROOT/core/deps/llvm/build" --target package --parallel 1
```

Run the second command only if the first succeeds. It reuses existing objects.
If it completes, the build tree can be used by wamrc's CMake; check the `LLVMConfig.cmake` path.

**Detail of this revision:** the script treats the presence of `lib/libLLVMCore.a` as a completed build. That file may exist before the entire build finishes. Rerunning the wrapper after failure may skip remaining work; resume with `cmake --build` as above.

If `build.ninja` is absent and the packaged SDK already exists after a successful build, proceed to step 6. Do not run Ninja inside the package.

### Permission denied; build only works with sudo

`sudo ninja` does not increase available memory. Check whether a previous command created root-owned files:

```bash
ls -ld "$WAMR_ROOT" "$WAMR_ROOT/core/deps/llvm/build"
find "$WAMR_ROOT" -user root -print -quit
```

If you created this toolchain tree and it contains root-owned files, fix only that folder after checking the path:

```bash
realpath "$WAMR_ROOT"
sudo chown -R "$(id -u):$(id -g)" "$WAMR_ROOT"
```

Resume building without `sudo`. Do not apply this correction to system directories.

### No space left on device

Check `df -h ~ /mnt/c` in WSL and `Get-PSDrive C` in PowerShell.
The distribution's virtual disk occupies space on the Windows physical drive.

Do not automatically delete `core/deps/llvm/build`: after packaging, it contains the SDK used to build wamrc. Before removing artifacts, identify what must be preserved for future builds.

Deleting Linux files does not guarantee an immediate reduction in the Windows VHDX file. Consult official [WSL disk management procedures](https://learn.microsoft.com/en-us/windows/wsl/disk-space) before manipulating the virtual disk.
Once space is available, try resuming the incremental build; `idf.py fullclean` is not a mandatory first step.

### Xtensa is missing or CMake finds another LLVM

Check `Using LLVMConfig.cmake in:` and the cache:

```bash
grep '^LLVM_DIR:' "$WAMR_ROOT/wamr-compiler/build-esp32/CMakeCache.txt"
find "$WAMR_ROOT/core/deps/llvm/build" -name LLVMConfig.cmake
```

If needed, configure a new build folder with `-DLLVM_DIR=...`, using **the directory containing** the discovered file. Do not mix an old build folder with LLVM from another source.

### unknown binary version

Compare `AOT_CURRENT_VERSION` in the compiler and runtime `core/config.h`, the wamrc commit, and the AOT header. This project expects version 3.

A matching format number is necessary but does not prove full compatibility.
Rebuild wamrc from the component's revision and generate another AOT.
Also check that the firmware embedded the new file.

Do not change the header version number to force loading.
The local WAMR document explains [AOT compatibility](managed_components/espressif__wasm-micro-runtime/doc/build_wasm_app.md).

### AOT module load failed: mmap memory failed

This message may come from a loader memory allocation. **It does not demonstrate that AOT is disabled.** Check the full log and SDK first.

In this revision's ESP-IDF port, executable mappings use `MALLOC_CAP_EXEC` in the default path. There is also a path conditional on `WASM_MEM_DUAL_BUS_MIRROR` that allocates in PSRAM and converts the address.
Check which path your build enables; free PSRAM alone does not guarantee the required allocation and mapping are possible.
See [espidf_memmap.c](managed_components/espressif__wasm-micro-runtime/core/shared/platform/esp-idf/espidf_memmap.c).

Investigate AOT code size, memory availability/fragmentation with the required capability, and runtime settings. Module code and linear memory have different requirements. Generating the file on the computer does not ensure it fits and runs on the board.

### Firmware still uses the previous model

Check the `main.aot` timestamp/hash, reconfigure, build, and flash the new firmware.
AOT always takes priority over WASM in this CMake configuration.
Check the monitor for the embedded mode.

### Module loads, but inference fails or results are wrong

Check exports, dimensions, RAW format, output type, and `NUM_CLASSES` in [host_config.h](main/host_config.h). The host is configurable, but the model must still follow the [contract in HOST.md](HOST.md).
Check class interpretation and compare results with interpreted execution of the same WASM.

## 11. References

This guide's project-specific basis is the files actually installed:

- [WAMR component manifest and commit](managed_components/espressif__wasm-micro-runtime/idf_component.yml).
- [Xtensa build wrapper](managed_components/espressif__wasm-micro-runtime/wamr-compiler/build_llvm_xtensa.sh).
- [LLVM Python build/packaging script](managed_components/espressif__wasm-micro-runtime/build-scripts/build_llvm.py).
- [wamrc CMake](managed_components/espressif__wasm-micro-runtime/wamr-compiler/CMakeLists.txt).
- [Compiler options](managed_components/espressif__wasm-micro-runtime/wamr-compiler/main.c).
- [ESP-IDF WAMR options](managed_components/espressif__wasm-micro-runtime/build-scripts/esp-idf/wamr/Kconfig).

Links under `managed_components` assume dependencies have been resolved by ESP-IDF.
For WSL installation, resource limits, and CMake parallelism, use the official references linked in the relevant steps.

