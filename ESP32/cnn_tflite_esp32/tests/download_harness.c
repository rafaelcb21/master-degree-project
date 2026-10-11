/* Fake HTTP transport for the actual downloader. No ESP32/network needed. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "host_config.h"
#define ESP_OK 0
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(x) (x)
typedef int esp_err_t;
typedef int *esp_http_client_handle_t;
typedef struct {
    const char *url;
    int timeout_ms;
    bool is_async;
    void *crt_bundle_attach;
    bool keep_alive_enable, disable_auto_redirect;
} esp_http_client_config_t;
#define esp_crt_bundle_attach NULL
static int scenario, attempts, cleanups, position, reads, complete;
static int64_t clock_us;
static int64_t esp_timer_get_time(void) { return clock_us; }
static void vTaskDelay(int ms) { clock_us += (int64_t)ms * 1000; }
static esp_http_client_handle_t esp_http_client_init(const esp_http_client_config_t *cfg) {
    (void)cfg; ++attempts; position = 0; complete = 0;
    return scenario == 9 ? NULL : &attempts;
}
static int esp_http_client_set_timeout_ms(esp_http_client_handle_t c, int ms) { (void)c; return ms > 0 ? 0 : -1; }
static int esp_http_client_set_header(esp_http_client_handle_t c, const char *k, const char *v) { (void)c; (void)k; (void)v; return 0; }
static int esp_http_client_open(esp_http_client_handle_t c, int n) { (void)c; (void)n; return scenario == 8 ? -1 : 0; }
static int64_t esp_http_client_fetch_headers(esp_http_client_handle_t c) { (void)c; return scenario == 7 ? -1 : scenario == 10 ? 5 : 4; }
static int esp_http_client_get_status_code(esp_http_client_handle_t c) { (void)c; return scenario == 5 ? 503 : 200; }
static bool esp_http_client_is_chunked_response(esp_http_client_handle_t c) { (void)c; return scenario == 4 || scenario == 11; }
static bool esp_http_client_is_complete_data_received(esp_http_client_handle_t c) { (void)c; return complete; }
static int esp_http_client_get_errno(esp_http_client_handle_t c) { (void)c; return 11; }
static int esp_http_client_cleanup(esp_http_client_handle_t c) { (void)c; ++cleanups; return 0; }
static int esp_http_client_read(esp_http_client_handle_t c, char *out, int n) {
    (void)c; ++reads;
    if (scenario == 2 || (scenario == 1 && attempts == 1 && position > 0)) return -1;
    if (scenario == 3 && position >= 2) return 0;
    if (scenario == 11 && position == 4) { complete = 1; return 0; }
    int total = scenario == 4 ? 6 : 4;
    int count = total - position;
    if (count > n) count = n;
    if (count > 2) count = 2;
    if (scenario == 6) { count = 1; clock_us += 20000000; }
    else clock_us += 1000;
    for (int i = 0; i < count; ++i) out[i] = (char)(attempts * 10 + position + i);
    position += count;
    if (position == total && scenario != 11) complete = 1;
    return count;
}

#include "download_http.inc"

int check(int mode) {
    scenario = mode; attempts = cleanups = position = reads = complete = 0; clock_us = 0;
    uint8_t data[6]; for (int i = 0; i < 6; ++i) data[i] = 99;
    int64_t elapsed = -1;
    bool ok = download_image("https://test/image.raw", data + 1, 4, &elapsed);
    bool success = mode == 0 || mode == 11;
    if (ok != success) return 1;
    if (data[0] != 99 || data[5] != 99) return 2;
    if (attempts != 1) return 3;
    if (cleanups != (mode == 9 ? 0 : attempts)) return 4;
    if (success) for (int i = 0; i < 4; ++i) if (data[i+1] != attempts * 10 + i) return 5;
    if (elapsed < 0 || elapsed != clock_us) return 6;
    if ((mode == 5 || mode >= 7) && mode != 11 && reads) return 7;
    return 0;
}
