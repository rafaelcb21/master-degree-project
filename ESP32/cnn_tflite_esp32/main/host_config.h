#ifndef HOST_CONFIG_H
#define HOST_CONFIG_H
/* Independent host configuration. */
#define WIFI_SSID "Contabil2025"
#define WIFI_PASS "Reservalagos36@"
#define WIFI_CONNECT_TIMEOUT_MS 30000
#define WIFI_MIN_AUTHMODE WIFI_AUTH_WPA2_PSK
#define HTTP_DOWNLOAD_TIMEOUT_MS 15000
/* Streaming download: total budget per attempt, short body reads, one retry. */
#define HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS 45000
#define HTTP_READ_TIMEOUT_MS 3000
#define HTTP_READ_CHUNK_BYTES 1024
#define HTTP_DOWNLOAD_MAX_ATTEMPTS 2
#define HTTP_RETRY_DELAY_MS 1000
#define HTTP_PROGRESS_INTERVAL_MS 5000
#define HTTP_KEEP_ALIVE_ENABLE 0
#define REPORT_HTTP_PORT 80
#define REPORT_HTTP_URI "/report"
/* HTTP handlers and floating-point JSON formatting need stack headroom. */
#define REPORT_HTTP_STACK_BYTES (8 * 1024)
/* Cloudinary RAW layout. Must match model width and height. */
#define INPUT_RGB565_LE 1
#define INPUT_RGB888 2
#define INPUT_BGR888 3
#define INPUT_FORMAT INPUT_RGB565_LE
#define IMG_W 128
#define IMG_H 128
#if INPUT_FORMAT == INPUT_RGB565_LE
#define INPUT_BYTES_PER_PIXEL 2
#elif INPUT_FORMAT == INPUT_RGB888 || INPUT_FORMAT == INPUT_BGR888
#define INPUT_BYTES_PER_PIXEL 3
#else
#error "Unsupported INPUT_FORMAT"
#endif
#define INPUT_BYTES (IMG_W * IMG_H * INPUT_BYTES_PER_PIXEL)
/* uint8: RGB bytes directly. int8/float: real = pixel * multiplier + offset.
 * int8 is then quantized using the model scale and zero point. */
#define INPUT_REAL_MULTIPLIER (1.0f / 127.5f)
#define INPUT_REAL_OFFSET (-1.0f)
/* Output type/quantization come from the model. For ImageNet, set
 * NUM_CLASSES=1000 and CLASS_LABELS_ARE_INDICES=1. Unknown label=-1.
 * Ties give result=-1, as in the ESP32 WASM host. */
#define NUM_CLASSES 2
#define CLASS_LABELS_ARE_INDICES 0
#define CLASS_LABELS { 1, 0 }
/* Arena is allocated once in PSRAM. Per-inference heap deltas exclude it.
 * Increase this if AllocateTensors fails, subject to available memory. */
#define TENSOR_ARENA_BYTES (1024 * 1024)
#define BENCHMARK_THREAD_STACK_BYTES (32 * 1024)
#define BENCHMARK_TASK_CORE 1
#define BENCHMARK_TASK_PRIORITY 5
#define BENCHMARK_WDT_TIMEOUT_MS 120000
/* Increment to deliberately start a new persistent experiment. */
#define BENCHMARK_RUN_ID 2
#define RECOVERY_MAX_ATTEMPTS 2
#define CHECKPOINT_PARTITION_LABEL "spiffs"
#if RECOVERY_MAX_ATTEMPTS < 1
#error "RECOVERY_MAX_ATTEMPTS must be positive"
#endif
#define BENCHMARK_WDT_IDLE_CORE_MASK BIT0
#define IMAGE_NAME_BYTES 128
#define REPORT_INITIAL_BYTES 4096
#define BENCHMARK_YIELD_MS 1
#if NUM_CLASSES < 1 || IMG_W < 1 || IMG_H < 1 || TENSOR_ARENA_BYTES < 16
#error "Invalid model dimensions, class count or arena size"
#endif
#if REPORT_INITIAL_BYTES < 1 || IMAGE_NAME_BYTES < 2
#error "Invalid buffer sizes"
#endif
#endif
