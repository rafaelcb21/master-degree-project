#ifndef BENCHMARK_MEMORY_H
#define BENCHMARK_MEMORY_H

/* ESP32 / ESP-IDF 5.3: shared by the WASM and TFLite hosts. */
#include <stdint.h>
#include "esp_heap_caps.h"
#include "esp_flash.h"
#include "esp_image_format.h"
#include "esp_ota_ops.h"
#include "esp_spiffs.h"
#include "esp_private/esp_clk.h"

#define BENCHMARK_INTERNAL_CAPS (MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT)

extern char _data_start[], _data_end[], _bss_start[], _bss_end[];
extern char _noinit_start[], _noinit_end[], _iram_start[], _iram_end[];

/* Linker ranges include padding. DRAM heap is a separate dynamic metric. */
static inline size_t benchmark_linker_bytes(const char *start, const char *end) {
    return (uintptr_t)end - (uintptr_t)start;
}

static inline size_t benchmark_internal_free(void) {
    return heap_caps_get_free_size(BENCHMARK_INTERNAL_CAPS);
}

static void benchmark_memory_report(void (*append)(const char *, ...)) {
    /* Sample before writing the footer: report growth itself can allocate RAM.
     * Historical minima are since boot, not a reset at each benchmark round. */
    const size_t internal_total = heap_caps_get_total_size(BENCHMARK_INTERNAL_CAPS);
    const size_t internal_free = benchmark_internal_free();
    const size_t internal_min = heap_caps_get_minimum_free_size(BENCHMARK_INTERNAL_CAPS);
    const size_t internal_largest = heap_caps_get_largest_free_block(BENCHMARK_INTERNAL_CAPS);
    const size_t psram_total = heap_caps_get_total_size(MALLOC_CAP_SPIRAM);
    const size_t psram_free = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    const size_t psram_min = heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM);
    const size_t psram_largest = heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM);
    const size_t data = benchmark_linker_bytes(_data_start, _data_end);
    const size_t bss = benchmark_linker_bytes(_bss_start, _bss_end);
    const size_t noinit = benchmark_linker_bytes(_noinit_start, _noinit_end);
    const size_t iram = benchmark_linker_bytes(_iram_start, _iram_end);

    append("\n# memory_report_schema=1 cpu_frequency_mhz=%u\n", (unsigned)(esp_clk_cpu_freq() / 1000000));
    append("# memory_snapshot_scope=end_of_round_before_memory_footer_and_buffer_release\n");
    append("# memory_minimum_scope=since_boot_per_region_low_watermarks\n");
    append("# internal_heap_caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT psram_caps=MALLOC_CAP_SPIRAM\n");
    append("# memory_free_function=heap_caps_get_free_size memory_minimum_function=heap_caps_get_minimum_free_size\n");
    append("# memory_total_function=heap_caps_get_total_size memory_largest_function=heap_caps_get_largest_free_block\n");
    append("# legacy_heap_caps=MALLOC_CAP_DEFAULT legacy_heap_is_internal_only=0\n");
    append("# internal_heap_total_bytes=%u internal_heap_free_bytes=%u internal_heap_used_bytes=%u internal_heap_min_free_bytes=%u internal_heap_largest_free_block_bytes=%u\n",
           (unsigned)internal_total, (unsigned)internal_free, (unsigned)(internal_total - internal_free),
           (unsigned)internal_min, (unsigned)internal_largest);
    append("# psram_total_bytes=%u psram_free_bytes=%u psram_occupied_bytes=%u psram_min_free_bytes=%u psram_largest_free_block_bytes=%u\n",
           (unsigned)psram_total, (unsigned)psram_free, (unsigned)(psram_total - psram_free),
           (unsigned)psram_min, (unsigned)psram_largest);
    append("# sram_static_dram_data_bytes=%u sram_static_dram_bss_bytes=%u sram_static_dram_noinit_bytes=%u sram_static_dram_bytes=%u sram_static_iram_bytes=%u\n",
           (unsigned)data, (unsigned)bss, (unsigned)noinit, (unsigned)(data + bss + noinit), (unsigned)iram);
    append("# sram_static_source=linker_ranges_including_padding\n");

    uint32_t flash_size = 0;
    if (esp_flash_get_size(NULL, &flash_size) == ESP_OK)
        append("# flash_size_bytes=%u\n", (unsigned)flash_size);
    append("# flash_image_function=esp_image_get_metadata flash_partition_function=esp_ota_get_running_partition\n");
    const esp_partition_t *partition = esp_ota_get_running_partition();
    if (partition) {
        append("# flash_app_partition_bytes=%u\n", (unsigned)partition->size);
        esp_partition_pos_t position = { .offset = partition->address, .size = partition->size };
        esp_image_metadata_t image = {0};
        esp_err_t error = esp_image_get_metadata(&position, &image);
        append("# flash_app_image_metadata_ok=%u\n", (unsigned)(error == ESP_OK));
        if (error == ESP_OK) {
            append("# flash_app_image_bytes=%u flash_app_partition_free_bytes=%u flash_app_partition_used_pct=%.3f\n",
                   (unsigned)image.image_len,
                   (unsigned)(partition->size > image.image_len ? partition->size - image.image_len : 0),
                   partition->size ? 100.0 * image.image_len / partition->size : 0.0);
        }
    }
    size_t spiffs_total = 0, spiffs_used = 0;
    esp_err_t spiffs_error = esp_spiffs_info("spiffs", &spiffs_total, &spiffs_used);
    append("# flash_spiffs_usage_available=%u\n", (unsigned)(spiffs_error == ESP_OK));
    if (spiffs_error == ESP_OK)
        append("# flash_spiffs_total_bytes=%u flash_spiffs_used_bytes=%u\n", (unsigned)spiffs_total, (unsigned)spiffs_used);
    append("# flash_scope=running_application_partition_spiffs_separate_not_total_chip_occupation\n");
}
#endif
