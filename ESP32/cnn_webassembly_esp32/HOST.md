# ESP32 host for WASM/AOT benchmarks

[English](HOST.md) | [Português (Brasil)](HOST.pt-BR.md)

This project is independent of Python. The host downloads RAW files from Cloudinary, copies the input into module memory, runs inference, and records results and measurements.

## Files to edit

- `main/host_config.h`: Wi-Fi, input dimensions and size, format flag, WASM exports, handshake, output type and count, labels, timeouts, stack sizes, and the HTTP report address.
- `main/image_list.h`: Cloudinary URLs and labels in execution order. The previous 2,000 entries have been preserved. Use `-1` as the label to run and measure without evaluating accuracy.

Wi-Fi credentials are placeholders: fill them in in `host_config.h`.
Changes to these files require rebuilding and flashing the firmware.

Example list entry:

```c
{ "https://res.cloudinary.com/SEU_CLOUD/raw/upload/imagem.raw", 0 },
```

`CLASS_LABELS` maps output tensor order to the labels in the list.
The initial value `{ 1, 0 }` preserves the previous model's mapping.
For a model with three classes labeled 0 through 2, use `NUM_CLASSES 3`
and `CLASS_LABELS { 0, 1, 2 }`.

## Module contract

The host supports modules that follow this interface. Export names are configurable, but their signatures must be `() -> i32`:

| Setting | Expected return value |
|---|---|
| `WASM_READY_EXPORT` | 1 when ready to receive an image; 0 when busy |
| `WASM_INPUT_PTR_EXPORT` | Input buffer offset |
| `WASM_RUN_EXPORT` | `INFERENCE_SUCCESS_CODE` on successful completion |
| `WASM_OUTPUT_PTR_EXPORT` | Contiguous output tensor offset |

The initial names preserve the existing modules' exports, including `run_mobilenetv2`. This name does not determine which model the host runs.
`USE_READY_HANDSHAKE 0` allows modules without a readiness export.
Execution is sequential and synchronous. A timeout or error aborts that image.
An internal failure may leave the module unavailable for subsequent images; the host does not clear the flag or force recovery of the model state.

The RAW file must contain exactly `INPUT_BYTES` bytes in the order and encoding expected by the module. The host does not resize, normalize, or swap channels.
The initial setting uses 128 × 128 RGB565 pixels (32,768 bytes).
For RGB888/BGR888, set `INPUT_BYTES_PER_PIXEL` to 3 and configure `WRITE_FORMAT_FLAG` according to the module contract. Disable this write when the module does not use the format flag.

The output may be `OUTPUT_UINT8`, `OUTPUT_INT8`, or `OUTPUT_FLOAT32`.
`NUM_CLASSES` must match the number of output elements. The host validates linear memory bounds, but cannot infer tensor capacity: sizes and format must match the module.
The result is the label of the largest element; a tie produces `-1`.
For quantized outputs, this comparison assumes a common positive scale and zero point across classes. Raw values are not converted to percentages.
Models with multiple outputs, detection, or other postprocessing need an adapted contract.

## Embedded module

Place `main.aot` or `main.wasm` in `main/`. The existing CMake rule gives `main.aot` priority when present. To use interpreted WASM, remove that AOT from the folder before reconfiguring/building the project.
The host does not generate these files. The AOT must match the target and WAMR used in the firmware.

## Commands, storage and repetitions

Build and flash in the ESP-IDF terminal with `idf.py build flash monitor`.
After Wi-Fi and WAMR initialization, enter a command in the serial monitor:

```text
benchmark 10 sim
benchmark 10 nao
```

The number specifies complete passes through the image list: 20 images and
10 passes produce 200 inferences. `sim` saves RAW files to SPIFFS; only
missing or invalid files are downloaded before execution. Files survive
power cycles and normal firmware flashes that preserve the SPIFFS partition.
The first use may format SPIFFS. Erasing flash removes the cache. Files are
identified by URL and input size and checked for integrity. Use versioned
URLs when changing remote content.

`nao` downloads the list once into PSRAM, reuses it across passes and frees
it when the command ends. It does not write or format SPIFFS. A new command
in this mode downloads again; existing flash files are preserved.

There is a **10-second pause between complete passes**, outside inference
timing. Save `/report` under a different name during each pause. The previous
CSV remains available during the next pass and is replaced only once a new
complete report is ready. The final report stays available until another
execution or reboot. Another command can be entered after execution ends.

The current SPIFFS partition is 1 MiB; 20 RGB565 files use 640 KiB plus
metadata. The cache reserves spare filesystem space and rejects oversized
lists. Old files are retained and also consume space. 2,000 files use
62.5 MiB and do not fit in this board's flash or PSRAM. `benchmark 1 nao`
supports such lists by streaming one file at a time. Multiple passes with
`nao` are rejected if the list cannot fit in PSRAM; repeating that many images
without downloads requires additional storage, such as an SD card.

## Measurements and CSV

After each pass, the server serves the CSV at `http://<esp32-ip>:80/report` (the port and path are configurable).
The server starts before commands and returns HTTP 503 until the first complete
report. The summary includes `round`, `repetitions` and `persist`.

Each image produces `ok`, `class_0_raw` through `class_N_raw`, the result, label, correctness, download time, inference time, heap and PSRAM before/after inference, memory differences, and the lowest observed free task stack space.
`right=-1` means no evaluation (failure or unknown label).
On failure, outputs are blank; measurements that were not taken remain zero.
Time averages and accuracy only include successfully processed images; accuracy excludes unlabeled images. Ties count as classification errors for labeled images.

Cached passes have `download_ms=0`: downloads happened during preparation.
Streaming passes record actual download times.
Inference time measures the export call, including lookup and entry into WAMR; download and input copying are outside this interval.
Heap/PSRAM differences do not represent peak memory use during inference.
Historical minima in the summary include other tasks and initialization.

The accumulated CSV resides in PSRAM; many images/classes may exhaust this space.
In that case, passes stop and the last complete CSV is preserved instead of
publishing a partial report. One image buffer and one result structure are reused,
alongside the optional PSRAM image cache and current/previous CSV buffers.

