#include <stdio.h>
#include <string.h>
#include <inttypes.h>
#include "esp_spiffs.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/md.h"
#include "host_config.h"
#include "image_list.h"
#include "image_cache.h"

/* Download lives in main.c; neither flash nor RAM reads count as download. */
extern bool download_image(const char *, uint8_t *, size_t, int64_t *);
extern void image_cache_keep_alive(void);
static uint8_t *ram_images;
static bool use_flash;
static bool mounted;
static const char *TAG = "image_cache";

/* Each call creates a fresh HTTP client and starts writing at byte zero.
 * Never save or infer from an incomplete download. */
static void download_until_complete(const char *url, uint8_t *buffer, int64_t *elapsed) {
    const int retry_delay_ms = 5000;
    int64_t started = esp_timer_get_time();
    uint32_t attempt = 1;
    while (1) {
        image_cache_keep_alive();
        if (download_image(url, buffer, INPUT_BYTES, elapsed)) break;
        ESP_LOGW(TAG, "Download falhou na tentativa %" PRIu32 "; nova tentativa em 5 segundos: %s", attempt, url);
        TickType_t ticks = pdMS_TO_TICKS(retry_delay_ms);
        vTaskDelay(ticks ? ticks : 1);
        if (attempt < UINT32_MAX) ++attempt;
    }
    *elapsed = esp_timer_get_time() - started;
}

static bool digest(const void *data, size_t len, uint8_t out[32]) {
    return mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256), data, len, out) == 0;
}

static bool cache_path(size_t index, char path[96]) {
    uint8_t hash[32];
    if (!digest(IMAGES[index].url, strlen(IMAGES[index].url), hash)) return false;
    strcpy(path, "/images/");
    for (size_t j = 0; j < 8; ++j) sprintf(path + 8 + j * 2, "%02x", hash[j]);
    snprintf(path + 24, 72, "_%u.raw", (unsigned)INPUT_BYTES);
    return true;
}

static bool read_flash(size_t index, uint8_t *buffer) {
    char path[96];
    uint8_t expected[32], actual[32], stored_url[32], url_hash[32];
    if (!cache_path(index, path)) return false;
    FILE *file = fopen(path, "rb");
    if (!file) return false;
    bool ok = digest(IMAGES[index].url, strlen(IMAGES[index].url), url_hash)
        && fread(stored_url, 1, sizeof(stored_url), file) == sizeof(stored_url)
        && memcmp(stored_url, url_hash, sizeof(url_hash)) == 0
        && fread(expected, 1, sizeof(expected), file) == sizeof(expected)
        && fread(buffer, 1, INPUT_BYTES, file) == INPUT_BYTES
        && fgetc(file) == EOF && !ferror(file)
        && digest(buffer, INPUT_BYTES, actual)
        && memcmp(expected, actual, sizeof(expected)) == 0;
    fclose(file);
    return ok;
}

static bool write_flash(size_t index, const uint8_t *buffer) {
    char path[96];
    uint8_t hash[32], url_hash[32];
    if (!cache_path(index, path) || !digest(buffer, INPUT_BYTES, hash)
        || !digest(IMAGES[index].url, strlen(IMAGES[index].url), url_hash)) return false;
    FILE *file = fopen(path, "wb");
    if (!file) return false;
    bool ok = fwrite(url_hash, 1, sizeof(url_hash), file) == sizeof(url_hash)
        && fwrite(hash, 1, sizeof(hash), file) == sizeof(hash)
        && fwrite(buffer, 1, INPUT_BYTES, file) == INPUT_BYTES;
    if (fclose(file) != 0) ok = false;
    if (!ok) remove(path);
    return ok;
}

void image_cache_release(void) {
    heap_caps_free(ram_images);
    ram_images = NULL;
    use_flash = false;
}

bool image_cache_prepare(bool persist, unsigned repetitions) {
    image_cache_release();
    if (persist) {
        if (!mounted) {
            esp_vfs_spiffs_conf_t conf = {
                .base_path = "/images", .partition_label = "spiffs",
                .max_files = 2, .format_if_mount_failed = true,
            };
            esp_err_t err = esp_vfs_spiffs_register(&conf);
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Falha montando SPIFFS: %s", esp_err_to_name(err));
                return false;
            }
            mounted = true;
        }
        size_t total = 0, used = 0;
        if (esp_spiffs_info("spiffs", &total, &used) != ESP_OK) return false;
        /* SPIFFS needs spare blocks for GC and per-file metadata. */
        if (NUM_IMAGES > (total * 3 / 4) / (INPUT_BYTES + 512)) {
            ESP_LOGE(TAG, "Lista nao cabe no SPIFFS (%u imagens, %u bytes cada, particao=%u). Use nao.",
                     (unsigned)NUM_IMAGES, (unsigned)INPUT_BYTES, (unsigned)total);
            return false;
        }
        use_flash = true;
        uint8_t *buffer = heap_caps_malloc(INPUT_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!buffer) return false;
        bool ok = true;
        for (size_t i = 0; i < NUM_IMAGES; ++i) {
            image_cache_keep_alive();
            if (read_flash(i, buffer)) continue;
            int64_t elapsed = 0;
            ESP_LOGI(TAG, "Baixando e gravando [%u/%u]", (unsigned)(i + 1), (unsigned)NUM_IMAGES);
            download_until_complete(IMAGES[i].url, buffer, &elapsed);
            if (!write_flash(i, buffer) || !read_flash(i, buffer)) {
                ESP_LOGE(TAG, "Falha preparando cache; confira rede/espaco. Arquivos antigos nao sao apagados.");
                ok = false;
                break;
            }
        }
        heap_caps_free(buffer);
        return ok;
    }

    if (NUM_IMAGES > SIZE_MAX / INPUT_BYTES) return false;
    size_t bytes = NUM_IMAGES * INPUT_BYTES;
    ram_images = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!ram_images) {
        if (repetitions == 1) {
            ESP_LOGI(TAG, "Sem cache RAM: uma rodada em streaming, sem gravar flash.");
            return true;
        }
        ESP_LOGE(TAG, "Repetir sem download exige %u bytes de PSRAM para imagens. Reduza a lista ou use uma rodada.",
                 (unsigned)bytes);
        return false;
    }
    for (size_t i = 0; i < NUM_IMAGES; ++i) {
        int64_t elapsed = 0;
        ESP_LOGI(TAG, "Baixando para PSRAM [%u/%u]", (unsigned)(i + 1), (unsigned)NUM_IMAGES);
        download_until_complete(IMAGES[i].url, ram_images + i * INPUT_BYTES, &elapsed);
    }
    return true;
}

bool image_cache_load(size_t index, uint8_t *buffer, int64_t *download_us) {
    *download_us = 0;
    if (use_flash) return read_flash(index, buffer);
    if (ram_images) {
        memcpy(buffer, ram_images + index * INPUT_BYTES, INPUT_BYTES);
        return true;
    }
    download_until_complete(IMAGES[index].url, buffer, download_us);
    return true;
}
