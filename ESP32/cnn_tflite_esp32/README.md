# ESP32-CAM project with WebAssembly (WAMR)

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

> **WASM → AOT in WSL:** [README_AOT_WSL.md](README_AOT_WSL.md).
> Step-by-step instructions covering project versions, Xtensa LLVM, wamrc, firmware, and troubleshooting.
> Configure the host and image list with [HOST.md](HOST.md).
> The current host downloads RAW files from Cloudinary; the camera sections below describe the historical setup.
> The longer [legacy guide](README_LEGACY.md) is also available in English.

This project aims to configure and run custom firmware on the **ESP32-CAM** board, integrating image capture with WebAssembly module execution through **WASM-Micro-Runtime (WAMR)**.

## 1. Installing and setting up the ESP32-CAM environment

### Install ESP-IDF

- Download ESP-IDF from [Espressif](https://dl.espressif.com/dl/esp-idf/).
- Add `idf.py.exe` to the **PATH** environment variable:

```text
C:\Espressif\tools\idf-exe\1.0.3
```

### Create the project

- Use the official [ESP-IDF sample project](https://github.com/espressif/esp-idf/tree/master/tools/templates/sample_project).
- Run the initial build to generate `sdkconfig`:

```bash
idf.py build
```

### Enable PSRAM

Enable it manually in `sdkconfig`:

```text
CONFIG_SPIRAM=y
```

Or use `menuconfig`:

```bash
idf.py menuconfig
```

```text
Component config → ESP PSRAM → [*] Support for external SPI-connected RAM
```

### Custom partition table

In `menuconfig`, select:

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

## 2. Add WAMR

Add to `idf_component.yml`:

```yaml
dependencies:
  wasm-micro-runtime:
    version: "^1"
  idf:
    version: ">=4.4"
  espressif/esp32-camera:
    version: "*"
```

ESP-IDF fetches dependencies automatically during the build.
Manual cloning of WAMR is not required.

## 3. Build, flash, and monitor the firmware

Run in an ESP-IDF terminal:

```bash
idf.py set-target esp32
idf.py fullclean
idf.py build
idf.py flash monitor
```

The `monitor` command displays the board's output in real time.

## Requirements

- **Board:** ESP32-CAM with PSRAM.
- **System:** Windows (recommended).
- **Tools:** Git, Python 3.8+, and `idf.py` in PATH.

## wat2wasm and xxd commands

- Download [WABT](https://github.com/WebAssembly/wabt/releases) for `wat2wasm`.
- Download [xxd for Windows](https://sourceforge.net/projects/xxd-for-windows/).
- Add both to the system PATH.

Convert `.wat` to `.wasm`:

```sh
wat2wasm .\hello_word.wat -o .\hello_word.wasm
```

Convert `.wasm` to a C array (historical method):

```sh
xxd -i hello_word.wasm > test_wasm.h
```

## Environment variables

```sh
IDF_PATH: C:\Espressif\frameworks\esp-idf-v5.3.1\
PATH:
    C:\Espressif\tools\idf-exe\1.0.3\
    C:\xxd
    C:\Program Files (x86)\WABT\bin
```

## Note

This project assumes that the firmware supports WebAssembly execution through WAMR.
For the historical camera workflow, the WebAssembly code must be able to handle captured image buffers. For the current Cloudinary host, follow [HOST.md](HOST.md).

