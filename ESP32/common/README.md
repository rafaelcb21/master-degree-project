# ESP32 benchmark memory metrics

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

The next `cnn_webassembly_esp32` and `cnn_tflite_esp32` firmwares include the same [memory collector](benchmark_memory.h). Build and flash the updated firmware, then run a new round. The web interface displays the new metrics when importing a CSV with `memory_report_schema=1`.

## Per-image fields

`internal_heap_before` and `internal_heap_after` measure internal heap with `MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT`, before/after inference and outside the timed interval. They exclude PSRAM and do not represent all physical SRAM (for example, static code in IRAM).

Existing fields `heap_before`, `heap_after` and `heap_used` remain available for compatibility: they query the default heap (`MALLOC_CAP_DEFAULT`), which can include PSRAM. They must not be labeled internal SRAM. `heap_used` and `psram_used` are nonnegative before/after differences, not the model's total occupancy.

## CSV footer

| Group | Fields and definition |
|---|---|
| Internal heap | `internal_heap_total_bytes`, `internal_heap_free_bytes`, `internal_heap_used_bytes`, `internal_heap_min_free_bytes`, `internal_heap_largest_free_block_bytes` |
| PSRAM | `psram_total_bytes`, `psram_free_bytes`, `psram_occupied_bytes`, `psram_min_free_bytes`, `psram_largest_free_block_bytes` |
| Static SRAM | `sram_static_dram_data_bytes`, `sram_static_dram_bss_bytes`, `sram_static_dram_noinit_bytes`, sum `sram_static_dram_bytes`, range `sram_static_iram_bytes` |
| Application flash | `flash_app_image_bytes`, `flash_app_partition_bytes`, `flash_app_partition_free_bytes`, `flash_app_partition_used_pct` |
| Flash / SPIFFS | `flash_size_bytes`; `flash_spiffs_total_bytes` and `flash_spiffs_used_bytes` when mounted |
| Context | `cpu_frequency_mhz` measured at round end; scopes, capabilities and function names |

The CSV records the functions `heap_caps_get_total_size`, `heap_caps_get_free_size`, `heap_caps_get_minimum_free_size` and `heap_caps_get_largest_free_block`. Historical minima sum per-region low watermarks **since boot**, including initialization and previous rounds; this collector does not reset them. Dynamic occupancy is `total - free` sampled at round end, before writing the memory footer and releasing buffers. It includes the runtime, cache and report under construction.

Static SRAM comes from linker symbols: `.data`, `.bss`, `.noinit` in DRAM and the `_iram_start` → `_iram_end` range, including padding. It is not the sum of dynamic heap and the chip's nominal 520 KiB. The build's memory map remains available for component-level analysis with `idf.py size`.

Application flash occupancy is the running image size, obtained through `esp_image_get_metadata` on `esp_ota_get_running_partition`. It excludes the bootloader, partition table and SPIFFS. Flash size returned by `esp_flash_get_size` is not a usage counter. SPIFFS usage comes from `esp_spiffs_info` only when mounted; otherwise the CSV records `flash_spiffs_usage_available=0` and does not present zero as measured usage.

In TFLite, restored checkpoints retain the original per-image measurements; the footer describes the boot/round publishing the report. Adding the collector and changing the row format changes checkpoint identity. Results from the previous version are not reinterpreted as new measurements.

The collector produces real values after running on the board. Firmware builds and web tests do not produce a new experimental collection. Older reports remain available without fabricated values for missing metrics.
