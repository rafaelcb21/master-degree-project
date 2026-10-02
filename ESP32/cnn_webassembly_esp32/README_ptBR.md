# ESP32-CAM project with WebAssembly (WAMR) — legacy guide

[English](README_ptBR.md) | [Português (Brasil)](README_ptBR.pt-BR.md)

> **WASM → AOT in WSL:** [README_AOT_WSL.md](README_AOT_WSL.md).
> Step-by-step instructions covering project versions, Xtensa LLVM, wamrc, firmware, and troubleshooting.
> Configure the host and image list with [HOST.md](HOST.md).
> The current host downloads RAW files from Cloudinary; older camera sections are historical.
>
> This is the complete English translation of the longer legacy Portuguese guide. Its original filename, `README_ptBR.md`, is retained to preserve references. The historical module names, measurements, and memory explanations below describe that earlier implementation; use HOST.md and README_AOT_WSL.md for the current host.

This project aims to configure and run custom firmware on the **ESP32-CAM**, integrating image capture with WebAssembly module execution through **WASM-Micro-Runtime (WAMR)**.

## 1. Installing and setting up the ESP32-CAM environment

### Install ESP-IDF

- Download ESP-IDF from the [official address](https://dl.espressif.com/dl/esp-idf/).
- Add the `idf.py.exe` executable to the system **PATH**:

```text
C:\Espressif\tools\idf-exe\1.0.3
```

### Create the project

Use the official [ESP-IDF sample project](https://github.com/espressif/esp-idf/tree/master/tools/templates/sample_project) as a base.
Run the initial build to generate `sdkconfig` automatically:

```bash
idf.py build
```

### Enable PSRAM (external memory)

Enable 4 MB of PSRAM manually in `sdkconfig`:

```
CONFIG_SPIRAM=y
```

### Enable PSRAM on the ESP32-CAM board

Run `idf.py menuconfig` and enable `Component config → ESP PSRAM → [*] Support for external SPI-connected RAM`.

### Configure a custom partition table

In `menuconfig`, navigate to:

```text
Partition Table → Partition Table → Custom partition table CSV
```

Put the following in the root-level `partitions.csv`:

```csv
# Name, Type, SubType, Offset, Size, Flags
nvs,data,nvs,0x9000,24K,
phy_init,data,phy,0xf000,4K,
factory,app,factory,0x10000,2M,
spiffs,data,spiffs,0x210000,0x100000,
```

This reserves 2 MB for firmware in the `factory` partition and 1 MB for files in the `spiffs` partition.

## 2. Add WebAssembly Micro Runtime (WAMR)

Add to `idf_component.yml`:

```yaml
## IDF Component Manager Manifest File
dependencies:
  wasm-micro-runtime:
    version: "^1"
  idf:
    version: ">=4.4"
  espressif/esp32-camera:
    version: "*"
```

The ESP-IDF component manager automatically fetches dependencies during the build. You do not need to clone repositories such as WAMR manually.

## 2.1. How the WASM module is embedded in firmware

In the version documented here, the WebAssembly file is no longer converted into a C header containing a large `unsigned char[]` array.

Previously, the workflow was:

```text
.wasm file
  -> conversion with xxd -i
  -> .h file containing a binary array as C text
  -> #include in main.c
  -> compiler processes the entire array
```

This method works, but has a significant drawback: the compiler must read and process a very large `.h` file on each relevant rebuild, substantially increasing build time, especially after `idf.py fullclean`.

The arrangement described here uses:

```text
main/rust_drowsiness_trucker.wasm
  -> declared in main/CMakeLists.txt with EMBED_FILES
  -> embedded in the final binary during linking
  -> accessed in main.c through automatically generated symbols
```

In [main/CMakeLists.txt](./main/CMakeLists.txt), this line instructs ESP-IDF to embed the binary directly in the firmware:

```cmake
idf_component_register(
    SRCS "main.c"
    EMBED_FILES "rust_drowsiness_trucker.wasm"
    ...
)
```

In [main/main.c](./main/main.c), the embedded contents are accessed through build-generated symbols:

```c
extern const uint8_t rust_drowsiness_trucker_wasm_start[] asm("_binary_rust_drowsiness_trucker_wasm_start");
extern const uint8_t rust_drowsiness_trucker_wasm_end[] asm("_binary_rust_drowsiness_trucker_wasm_end");
```

The code then obtains:

- The starting address of the embedded WASM file.
- Its size, calculated by subtracting the start pointer from the end pointer.

```c
uint8_t *wasm_file_buf = (uint8_t *)rust_drowsiness_trucker_wasm_start;
uint32_t wasm_file_size = (uint32_t)(rust_drowsiness_trucker_wasm_end - rust_drowsiness_trucker_wasm_start);
```

Finally, this buffer is passed to WAMR:

```c
wasm_module_t module = wasm_runtime_load(wasm_file_buf, wasm_file_size, error_buf, sizeof(error_buf));
```

## 2.2. What the linker does here

The **compiler** transforms each source file (`.c`) into intermediate object files.

The **linker** is the next stage: it combines compiled objects, libraries, tables, and embedded files into a final firmware image. Firmware build images include:

- `bootloader.bin`
- `partition-table.bin`
- `cnn_webassembly_esp32.bin`

With `EMBED_FILES`, the `.wasm` file does not become C code. Instead, the build passes it to the linker, which places it in the final firmware image as an embedded binary block.
The linker also creates symbols such as:

- `_binary_rust_drowsiness_trucker_wasm_start`
- `_binary_rust_drowsiness_trucker_wasm_end`

These symbols serve as memory markers, letting C code locate the beginning and end of the embedded file.

## 2.3. Where WASM resides in firmware and during execution

Distinguish two phases:

### 1. Firmware stored on the board

`rust_drowsiness_trucker.wasm` is embedded in the application partition (`factory`) in ESP32 **flash memory**.

Therefore, it is:

- Not on the stack.
- Not on the heap.
- Not in SPIFFS.
- Not initially in PSRAM.

It becomes part of the firmware image written to flash.

### 2. Program execution

When `main.c` calls `wasm_runtime_load()`, the runtime reads the embedded contents and creates the internal structures needed to interpret/instantiate the WebAssembly module.

In the arrangement documented here:

- The **raw WASM file** is embedded in firmware in **flash**.
- **Module linear memory**, runtime structures, buffers, and execution areas use **RAM**.
- The implemented allocation strategy prioritizes **PSRAM** for WAMR through:

```c
init_args.mem_alloc_type = Alloc_With_Allocator;
init_args.mem_alloc_option.allocator.malloc_func  = (void *)psram_malloc;
init_args.mem_alloc_option.allocator.realloc_func = (void *)psram_realloc;
init_args.mem_alloc_option.allocator.free_func    = (void *)psram_free;
```

Thus:

- **Raw WASM:** stored in flash, inside firmware.
- **WASM execution memory:** allocated mostly in PSRAM.
- **Internal heap:** used as fallback when PSRAM cannot satisfy a request.

## 2.4. Flash, stack, heap, PSRAM, and SPIFFS

### Flash

Nonvolatile memory where firmware is stored. Contents remain when the board is powered off.
The `.wasm` embedded through `EMBED_FILES` resides here as part of the application image.

### Stack

Memory used for function calls, local variables, and task context. It is small and volatile. The `.wasm` file is not stored on the stack.

### Internal heap

The ESP32's main dynamic RAM, used by `malloc()`. It is more limited and shared by Wi-Fi, TCP/IP, HTTP, and other system structures.

### PSRAM

The ESP32-CAM's external RAM. This project uses it to relieve pressure on the internal heap, particularly for WebAssembly linear memory and larger runtime structures.

### SPIFFS

A filesystem in flash. It could be used if the project stored `.wasm` as an external file and loaded it dynamically at runtime.
That does not happen in this arrangement: `.wasm` is embedded directly in firmware rather than loaded from SPIFFS.

## 2.5. Technical description for the dissertation

The solution can be described as follows:

> The inference model's WebAssembly module is embedded in firmware through ESP-IDF's `EMBED_FILES` mechanism, replacing the previous strategy of converting the `.wasm` binary into a C array. Consequently, the binary is no longer processed as source text by the compiler; it is embedded in the final firmware image during linking. At runtime, its contents are accessed through automatically generated linker symbols, while the WebAssembly runtime's dynamic structures are allocated preferentially in PSRAM. This approach reduces compilation overhead, improves project maintenance, and preserves the ability to load the WASM module locally on the device.

## 2.6. Memory and partition structure documented for the project

### Configured total flash size

The project is configured for **4 MB of flash**, according to `sdkconfig`:

```text
CONFIG_ESPTOOLPY_FLASHSIZE="4MB"
```

This configuration is needed because the partition table reserves:

- 2 MB for the main application.
- 1 MB for SPIFFS.
- Smaller areas for NVS and `phy_init`.

### Partition table in use

The project uses a **custom table** defined in [partitions.csv](./partitions.csv), with these entries:

```csv
# Name, Type, SubType, Offset, Size, Flags
nvs,data,nvs,0x9000,24K,
phy_init,data,phy,0xf000,4K,
factory,app,factory,0x10000,2M,
spiffs,data,spiffs,0x210000,0x100000,
```

In `sdkconfig`:

```text
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
CONFIG_PARTITION_TABLE_FILENAME="partitions.csv"
```

### Meaning of each partition

#### nvs

- Type: `data`
- Subtype: `nvs`
- Offset: `0x9000`
- Size: `24 KB`

ESP-IDF uses this area for nonvolatile storage of parameters such as persistent data, Wi-Fi settings, credentials, calibration, and other small pieces of information.

#### phy_init

- Type: `data`
- Subtype: `phy`
- Offset: `0xF000`
- Size: `4 KB`

Stores initialization data for the ESP32 radio's physical layer.

#### factory

- Type: `app`
- Subtype: `factory`
- Offset: `0x10000`
- Size: `2 MB` (`0x200000` bytes)

The main firmware partition, containing the final application binary, including:

- Compiled C/C++ code.
- ESP-IDF libraries.
- WAMR libraries.
- Internal tables and firmware metadata.
- `rust_drowsiness_trucker.wasm`, embedded through `EMBED_FILES`.

#### spiffs

- Type: `data`
- Subtype: `spiffs`
- Offset: `0x210000`
- Size: `1 MB` (`0x100000` bytes)

Reserved for a SPIFFS filesystem.
In this project structure, WASM is **not** loaded from SPIFFS. It is embedded directly in firmware within `factory`.

## 2.7. Flash addressing and recorded usage

Given the documented configuration, the practical layout is:

```text
Total configured flash: 4 MB

0x0000  -> initial region / boot metadata
0x1000  -> bootloader
0x8000  -> partition table
0x9000  -> NVS (24 KB)
0xF000  -> phy_init (4 KB)
0x10000 -> app factory (2 MB)
0x210000 -> SPIFFS (1 MB)
```

### Build artifacts

The recorded build produced these main artifact sizes:

- `bootloader.bin`: `26,752 bytes` (about `26.1 KB`).
- `partition-table.bin`: `3,072 bytes` (about `3.0 KB`).
- `cnn_webassembly_esp32.bin`: `1,702,080 bytes` (about `1.62 MiB`).

### factory partition usage

The `factory` partition has:

- Total capacity: `2,097,152 bytes` (`2 MB`).
- Recorded firmware: `1,702,080 bytes`.
- Approximate free space: `395,072 bytes`.

Percentages:

- `factory` usage: approximately `81.2%`.
- Remaining space: approximately `18.8%`.

This agrees with the build output:

```text
cnn_webassembly_esp32.bin binary size 0x19f8c0 bytes.
Smallest app partition is 0x200000 bytes.
0x60740 bytes (19%) free.
```

### spiffs partition usage

The `spiffs` partition is only **reserved** in the partition table.
The firmware build does not use this space to store WASM.

Thus:

- `factory`: actively used by the application.
- `spiffs`: reserved for future use or external file storage.

## 2.8. Where each element is stored

### Main firmware

The file:

- `build/cnn_webassembly_esp32.bin`

is written to the flash `factory` partition.

### WASM file

The file:

- `main/rust_drowsiness_trucker.wasm` (historical artifact name)

is embedded in firmware during linking and therefore also stored in `factory`.

It is **not**:

- On the stack.
- On the heap.
- In the SPIFFS partition.
- A separate external file in flash.

It becomes an integral part of the main application binary image.

### Runtime memory

During execution, WAMR needs memory for:

- Module linear memory.
- Runtime internal structures.
- Execution buffers.
- Module execution stack.

In this project, these allocations preferentially use **PSRAM** through custom allocation functions:

```c
init_args.mem_alloc_type = Alloc_With_Allocator;
init_args.mem_alloc_option.allocator.malloc_func  = (void *)psram_malloc;
init_args.mem_alloc_option.allocator.realloc_func = (void *)psram_realloc;
init_args.mem_alloc_option.allocator.free_func    = (void *)psram_free;
```

This means:

- The **WASM binary** resides in flash.
- **Module execution** consumes RAM.
- The project tries to use **PSRAM** for that dynamic RAM.
- If PSRAM is unavailable, code falls back to ordinary `malloc()`.

## 2.9. PSRAM state in the documented project configuration

PSRAM was reenabled in `sdkconfig` and persisted in `sdkconfig.defaults`.

Main settings:

```text
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_SPIRAM_TYPE_AUTO=y
CONFIG_SPIRAM_SPEED_40M=y
CONFIG_SPIRAM_BOOT_INIT=y
```

The project also retains:

```text
CONFIG_SPIRAM_USE_MALLOC=y
CONFIG_SPIRAM_MEMTEST=y
```

In practice:

- PSRAM support is enabled in the build.
- PSRAM initializes at boot.
- The project can use `MALLOC_CAP_SPIRAM`.
- The WASM runtime can allocate dynamic memory preferentially in PSRAM.
- Internal heap remains available as fallback.

This makes configuration consistent with the WAMR initialization code in `main.c`.

## 2.10. Memory made available at runtime

Besides where resources reside, it is useful to record how much memory the code explicitly requests from the runtime.

### Memory configured for the WASM module

In this call:

```c
module_inst = wasm_runtime_instantiate(module, 1024 * 1024, 512 * 1024, error_buf, sizeof(error_buf));
```

the project requests:

- `1024 * 1024` bytes = **1 MB**.
- `512 * 1024` bytes = **512 KB**.

The original guide describes these as approximately:

- **1 MB** for the main area associated with module instantiation.
- **512 KB** for the module's configured heap/auxiliary area.

The WASM call execution environment is also created with:

```c
exec_env = wasm_runtime_create_exec_env(module_inst, 32 * 1024);
```

That is:

- **32 KB** for `exec_env`.

### C-side image buffer

The code also maintains a static input image buffer:

```c
#define RGB565_BYTES (IMG_W * IMG_H * 2)
static uint8_t img_buf[RGB565_BYTES];
```

With `IMG_W = 128` and `IMG_H = 128`, the buffer occupies:

- `128 * 128 * 2 = 32768 bytes`.
- **32 KB**.

### Additional C-side usage

Other memory structures also contribute:

- `g_rows[MAX_REPORT_ROWS]`, which grows with the number of configured benchmark images.
- Dynamic `g_report_text`, which grows as the report accumulates.
- Wi-Fi, TCP/IP stack, HTTP client, and HTTP server structures.
- Internal ESP-IDF and WAMR allocations.

Total RAM use is therefore not simply `1 MB + 512 KB + 32 KB + 32 KB`.

### Numerical overview of explicit configuration

Values directly defined in the documented code:

- WASM module instantiated with **1 MB**.
- Module auxiliary/configured heap of **512 KB**.
- `exec_env` of **32 KB**.
- RGB565 image buffer of **32 KB**.

Adding only these main explicitly visible blocks:

- **Approximately 1.56 MB**.

This should be understood as a **minimum structural estimate of the main configured blocks**, not an exact measurement of total firmware memory use at runtime.

### Where this memory tends to reside

In this arrangement:

- Raw `.wasm` remains in **flash**.
- Dynamic runtime memory is preferentially allocated in **PSRAM**.
- Internal heap may serve as fallback.
- Task stacks remain separate.

The architecture can therefore be read as:

```text
Flash:
  - firmware
  - embedded .wasm

PSRAM (preferred):
  - main WASM instance memory
  - module auxiliary heap/configuration
  - a substantial part of WAMR dynamic allocations

Internal RAM:
  - malloc fallback
  - stacks
  - system, Wi-Fi, and network structures
```

### Methodological note

Although the code configures these sizes, actual runtime use depends on:

- Actual PSRAM availability on the board.
- Successful PSRAM initialization at boot.
- WAMR internal behavior.
- Number of images processed.
- Active network buffers.
- Simultaneous Wi-Fi, HTTP, and report usage.

Experimental dissertation results should therefore combine:

- **Nominal code configuration**, described here.
- **Empirical measurements** from `heap_caps_get_free_size(MALLOC_CAP_SPIRAM)`, `esp_get_free_heap_size()`, and `heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM)` logs.

## 2.11. Final structural overview

Storage and execution architecture:

```text
FLASH (4 MB)
├── bootloader
├── partition table
├── nvs
├── phy_init
├── factory (2 MB)
│   ├── main firmware
│   ├── compiled C/C++ code
│   ├── ESP-IDF libraries
│   ├── WAMR
│   └── embedded rust_drowsiness_trucker.wasm
└── spiffs (1 MB reserved)

Runtime RAM
├── task stacks
├── internal heap
└── PSRAM (when enabled)
    └── preferred target for WASM runtime allocations
```

This arrangement avoids a giant binary-array header and makes the separation clearer between:

- Persistent module storage (`flash`, within firmware).
- Dynamic execution memory (`RAM`, preferentially `PSRAM`).

## 3. Build, flash, and monitor the firmware

Use an ESP-IDF terminal such as **ESP-IDF PowerShell** or **ESP-IDF CMD**:

```bash
idf.py menuconfig # adjust settings if needed
idf.py set-target esp32 # used once to set the target
idf.py fullclean
idf.py build
idf.py flash monitor
```

The `monitor` command shows ESP32-CAM logs and messages directly in the terminal.

## AOT

1. Generate `.aot` from `.wasm` (historical command):

```sh
wamrc --target=xtensa --target-abi=ilp32 --cpu=esp32 --enable-multi-thread -o main.aot main.wasm
```

Use [README_AOT_WSL.md](README_AOT_WSL.md) for the current version-specific procedure.

## Requirements

- Board: **ESP32-CAM with PSRAM support**.
- System: **Windows (recommended)** with ESP-IDF installed.
- Tools:
  - Git.
  - Python 3.8+.
  - `idf.py` configured in PATH.

## wat2wasm commands

`wat2wasm` is part of WABT, available from [WABT GitHub releases](https://github.com/WebAssembly/wabt/releases).
After downloading, add the program to the environment variables.

`wat2wasm` converts a WAT file into a WASM binary:

```sh
wat2wasm .\hello_word.wat -o .\hello_word.wasm
```

In this version, `xxd` is no longer needed to convert `.wasm` to a C header.
Keep `.wasm` binary and embed it with `EMBED_FILES`.

## Environment variables

```sh
IDF-PATH: C:\Espressif\frameworks\esp-idf-v5.3.1\
PATH: 
    C:\Espressif\tools\idf-exe\1.0.3\ 
    C:\xxd 
    C:\Program Files (x86)\WABT\bin
```

## Note

The project assumes the firmware runs with WebAssembly support through WAMR.
For the historical camera setup described here, ensure the WebAssembly code can handle buffers captured by the integrated camera.

