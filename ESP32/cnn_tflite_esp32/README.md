# TFLite Micro benchmark on ESP32

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

This independent ESP-IDF project runs an original `.tflite` model on ESP32 with **TensorFlow Lite Micro**, downloads RAW inputs from Cloudinary, and serves CSV results for comparison with the [WASM/AOT host](../cnn_webassembly_esp32/README.md). The default model is Drowsiness, 128×128 RGB input and two output classes.

## What changed from the copied host

- `main/main.c`: Wi-Fi, downloads, sequential benchmark, measurements and HTTP endpoints.
- `main/tflite_runtime.cpp`: TensorFlow Lite Micro, model validation, input conversion and `Invoke()`.
- `main/host_config.h`: all editable runtime settings, dimensions, format, labels and arena size.
- `main/image_list.h`: the preserved Cloudinary image URLs and ground-truth labels.
- `model_int8_esp32.tflite`: original model embedded in aligned flash; no WAT, WASM or AOT conversion.
- `main/idf_component.yml`: Espressif TFLite Micro 1.3.5; resolved ESP-NN version is recorded in `dependencies.lock`.
- `legacy_wasm/`: copied WASM artifacts and historical guides. Its CSV is **not** a TFLite measurement.

The original `cnn_webassembly_esp32` project is unchanged. Old copied `build/` folders are unused; this guide uses a fresh `build-tflite/` directory.

## 1. Configure

Open an **ESP-IDF 5.3 terminal**. The checked configuration targets a classic ESP32 with PSRAM and 4 MiB flash. Confirm PSRAM mode, frequency and flash size for your actual board using `menuconfig`; they cannot be inferred from the model.

Edit `main/host_config.h`:

```c
#define WIFI_SSID "your-network"
#define WIFI_PASS "your-password"
#define INPUT_FORMAT INPUT_RGB565_LE
#define IMG_W 128
#define IMG_H 128
#define NUM_CLASSES 2
#define CLASS_LABELS_ARE_INDICES 0
#define CLASS_LABELS { 1, 0 }
#define TENSOR_ARENA_BYTES (1024 * 1024)
```

Edit the URLs in `main/image_list.h`. Each download must contain exactly 32,768 bytes of little-endian RGB565 for the default configuration. These are RAW bytes, not PNG/JPEG files. Label `-1` means unknown ground truth. Each pass processes the list in order; the number of passes is supplied in the serial monitor.

The host expands RGB565 to RGB888 with the same bit replication as WASM and places those bytes in the uint8 TFLite input. The original model's QUANTIZE layer is executed by TFLite Micro. The next image is loaded only after the synchronous `Invoke()` returns; there is no WASM handshake.

## 2. Build and flash

From this project directory:

```powershell
idf.py -B build-tflite reconfigure
idf.py -B build-tflite menuconfig
idf.py -B build-tflite build
idf.py -B build-tflite -p COM3 flash monitor
```

Replace `COM3` with your board's port. The first configuration downloads managed components. Keep the same `-B build-tflite` argument for subsequent commands. Exit the monitor with `Ctrl+]`.

### Commands and image cache

At the serial prompt, enter a command and press Enter:

```text
benchmark 10 sim
benchmark 10 nao
benchmark 1 nao
```

The number specifies complete passes through the list. With 20 images,
10 passes produce 200 inferences. `sim` saves RAW files to SPIFFS and downloads
only missing or invalid files. `nao` holds images in PSRAM during the command,
without writing them to flash. A new command with `nao` downloads again;
existing flash images are preserved. Commands/results still use NVS and the
checkpoint journal for recovery, including in `nao` mode.

There is a **10-second pause between complete passes** to save `/report`
and `/metadata` under different names. The previous complete report stays
available while the next pass runs. Endpoints return HTTP 503 before the
first complete report. Every new command executes new inferences.

Incomplete downloads, HTTP/TLS errors and timeouts retry the same image
**until success, without an attempt limit**, waiting **5 seconds** between
attempts. Each attempt uses a fresh connection and starts at byte zero.
Saved images are preserved and the watchdog is fed during retries.
Storage errors or insufficient space still stop preparation.

20 files of 32 KiB use 640 KiB and fit in the 1 MiB SPIFFS partition,
including the metadata reserve. Old files also consume space. 2,000 files
use 62.5 MiB and do not fit in this board's flash or PSRAM; `benchmark 1 nao`
streams one pass. Repeating without further downloads requires the list to
fit in PSRAM or additional storage, such as an SD card. Oversized cache
configurations are rejected.

`idf.py -B build-tflite flash monitor` preserves SPIFFS images provided the
partition table preserves that region. To erase all flash:

```powershell
idf.py -B build-tflite erase-flash
```

This erases images, firmware, settings and checkpoints. Flash again afterward;
the next `sim` command downloads images again. First use with `sim` may format
SPIFFS. Use versioned URLs when changing remote content: cache identity uses
the URL and RAW size.

**Upgrading older firmware:** SPIFFS at `0x210000` now stores images; results
use a separate 960 KiB checkpoint partition at `0x310000`. Old raw-journal
results in SPIFFS are not migrated; save those reports before upgrading.
Subsequent flashes preserve image files. Model/configuration changes invalidate
result recovery to avoid mixing experiments.

The firmware validates the model schema, operator availability, tensor types, dimensions and number of classes. An incompatible model or insufficient arena stops the benchmark with a log message. Increase the arena only if your PSRAM has room for it, the downloaded image and the accumulated CSV. Unsupported operators require adding their registrations in `tflite_runtime.cpp` and confirming that TFLite Micro supports their tensor types.

## 3. Download the results

Look for `Conectado ao Wi-Fi. IP:` in the serial log. This is the ESP32's address, not the computer's address. The server prints the download URLs and publishes results after each pass:

```text
http://<ESP32-IP>:80/report
http://<ESP32-IP>:80/metadata
```

The CSV and metadata become available after processing the image list or restoring a completed experiment from flash. Keep the board powered while downloading. From a computer on the same network, save both files into a new folder:

```powershell
$runDir = Join-Path 'reports' (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $runDir -Force
Invoke-WebRequest 'http://192.168.0.50:80/report' -OutFile (Join-Path $runDir 'report-tflite.csv')
Invoke-WebRequest 'http://192.168.0.50:80/metadata' -OutFile (Join-Path $runDir 'metadata.json')
```

Replace the example IP with the address printed by your board. In Research Explorer, refresh the index and open this project's `reports/` folder. No device measurements are supplied with this conversion: they must be generated by flashing and running the firmware on your board.

## If processing stops after certificate validation

If opening results causes `A stack overflow in task httpd has been detected`, flash the updated firmware: the `/metadata` JSON buffer is stored outside the stack, and `REPORT_HTTP_STACK_BYTES` in `main/host_config.h` reserves 8 KiB for the server. This failure occurs in the HTTP server after inference; the current firmware restores committed results from flash after restarting.

`Certificate validated` confirms only the TLS certificate check. Follow the next stage logs: `Imagem carregada`, `Iniciando preparacao + Invoke`, and `Invoke retornou`. These distinguish network delays from preprocessing or inference stalls.

HTTPS downloads use explicit open/header/body reads in `main/download_http.inc`. `HTTP_DOWNLOAD_TIMEOUT_MS` sets the connection/header timeout (15 seconds), `HTTP_READ_TIMEOUT_MS` the body-read timeout (3 seconds), and `HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS` the per-attempt deadline checked between calls (45 seconds). Reads are limited to `HTTP_READ_CHUNK_BYTES` (1,024 bytes). `main/image_cache.c` retries failed attempts indefinitely with a 5-second pause. Each attempt validates HTTP status, exact byte count and response completion. Streaming `download_ms` includes attempts, pauses and connection cleanup; cached passes report zero because downloads happened before measurement. These checks do not forcibly interrupt an internal driver call or a stuck inference.

The firmware build passed, and `tests/test_download.py` verifies the actual downloader with a fake HTTP transport across 12 success/error scenarios, including truncation, timeout, overflow and retry. This does not reproduce TLS faults on the physical ESP32. In the website, close the serial monitor and choose **Build and flash** to install this change; **Restart benchmark** alone runs the old firmware.

Rebuild and flash the firmware to apply changes. Restarting resumes the current experiment from flash; `/report` becomes available after the benchmark finishes or a completed report is restored.

## Comparing results

### Automatic recovery and persistent results

The host uses the 960 KiB `checkpoint` partition as a raw result journal, separate from SPIFFS images. Before each new image it atomically records its attempt in NVS; after processing it writes the result, its checksum, and a final commit marker to flash. Only committed records are restored. Interrupted writes consume an unused slot and do not overwrite earlier results. Storage errors stop processing rather than silently discarding the journal. The host checks that the partition can hold all configured samples before starting; larger outputs/datasets may require a larger partition.

The benchmark task is registered with the task watchdog. `BENCHMARK_WDT_TIMEOUT_MS=120000` triggers a panic/reboot if it stops making progress. After reboot, the CSV and totals are reconstructed from flash and processing resumes at the first uncommitted image. `RECOVERY_MAX_ATTEMPTS=2` limits interrupted executions per image; after two interruptions, the next boot records that image as an error and continues. Manual resets/power loss during an image also count as interruptions. CSV fields `recovery_attempts` and `recovery_skipped` expose this recovery; metadata includes `processed`, `resumed`, `recovery_skipped`, and `checkpoint_run_id`.

The first installation waits for a serial command. NVS stores the command and current pass; interrupted execution resumes automatically after reboot. `nao` loses its PSRAM images on reset and must download them again; `sim` reuses flash images. The last completed pass remains available through `/report` and `/metadata` after reboot, reconstructed from the journal without rerunning inference. Enter another `benchmark` command to start a new experiment; no rebuild is needed. Command/pass identities prevent reusing old results as new inferences. Changes to model, image list, sources or configuration invalidate recovery. Save the previous report before changing them. `fullclean` only cleans desktop build files, preserving board data. Flash writes occur outside measured inference time. Recovery does not establish or fix the underlying cause of an inference hang.

See [measurement definitions](HOST.md). The CSV preserves the WASM host's original column names and adds:

- `preprocess_ms`: RAW conversion and writing the model input.
- `invoke_ms`: TFLite Micro `Invoke()` only.
- `inference_ms`: preprocessing + Invoke. The WASM run includes its synthetic RGB conversion, so this is the closer scope for the embedded comparison; implementations still have different overheads.
- `arena_reserved_bytes`, `arena_used_bytes`: persistent tensor arena memory.
- `input_sha256`: SHA-256 of the downloaded RAW bytes.

`/metadata` records the runtime, model and image-list hashes, output quantization, CPU frequency and counts. Keep metadata with each CSV. Compare the same model, image bytes, dimensions, class mapping and board settings. Heap deltas are not the model's total memory use. Times exclude HTTP download and output interpretation; there is no warm-up invocation.

## Using another model

### Validation of this adaptation

The default firmware was built successfully with ESP-IDF 5.3.1 for `esp32`: 2,012,544 bytes, within the 2 MiB app partition (4% free). The embedded model's 16-byte alignment and the unchanged image list were checked. This verifies compilation, not execution on a physical board. Arena sizing, network downloads and inference results still require a device run. A larger model may require a larger app partition.

Choose the model during configuration:

```powershell
idf.py -B build-tflite -D TFLITE_MODEL_FILE=C:/path/to/model.tflite reconfigure
```

Adjust dimensions, input format, class count and labels in `host_config.h`, and replace the Cloudinary list with the matching RAW images. For the included MobileNetV2 ImageNet package: 224×224, `INPUT_BGR888`, 1,000 classes, `CLASS_LABELS_ARE_INDICES=1`, unknown image labels `-1`. Its CSV contains all 1,000 raw outputs, so start with a short image list to avoid exhausting report RAM. Its flash and arena requirements must be checked separately.

The host accepts uint8/int8 outputs with per-tensor quantization or float32. uint8 input receives RGB bytes directly, matching the two current packages. For int8/float models, review `INPUT_REAL_MULTIPLIER` and `INPUT_REAL_OFFSET` against the model's preprocessing. These are configurable assumptions, not a universal preprocessing rule.

Sources: [Espressif TFLite Micro](https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.3.5) and [TFLite Micro memory management](https://github.com/tensorflow/tflite-micro/blob/main/tensorflow/lite/micro/docs/memory_management.md).
