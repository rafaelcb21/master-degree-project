#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "tflite_runtime.h"
#include "mbedtls/sha256.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "esp_partition.h"
#include <stddef.h>
#include "freertos/event_groups.h"
#include "esp_http_server.h"
#include "esp_http_client.h"
#include "esp_crt_bundle.h"
#include "esp_task_wdt.h"
#include "esp_wifi.h"
#include "esp_system.h"

/* ============================================================
 * ATENÇÃO — Dependências de componentes (adicionar no CMakeLists.txt
 * do componente/projeto, em REQUIRES ou PRIV_REQUIRES):
 *   esp_http_client
 *   esp-tls
 *   mbedtls
 * E habilitar no menuconfig (idf.py menuconfig):
 *   Component config -> mbedTLS -> Certificate Bundle -> Enable (CONFIG_MBEDTLS_CERTIFICATE_BUNDLE=y)
 * (necessário para HTTPS no res.cloudinary.com via esp_crt_bundle_attach)
 * ============================================================ */

#include <math.h>
#include <inttypes.h>
#include "host_config.h"
#include "image_list.h"
#include "image_cache.h"

#define TAG "tflite_benchmark"
#define TAG_HTTP "HTTP_SERVER"
#define WIFI_TAG "wi-fi"
static EventGroupHandle_t wifi_event_group;
static const int WIFI_CONNECTED_BIT = BIT0;
#if !CLASS_LABELS_ARE_INDICES
static const int CLASS_LABEL_MAP[] = CLASS_LABELS;
_Static_assert(sizeof(CLASS_LABEL_MAP) / sizeof(CLASS_LABEL_MAP[0]) == NUM_CLASSES,
               "CLASS_LABELS deve ter NUM_CLASSES rotulos");
#endif
/* ============================================================
 * Linha do relatório (equivalente a uma linha do SQLite no JS)
 * ============================================================ */
typedef struct {
    char name_image[IMAGE_NAME_BYTES];
    int ok;
    int result;
    int label;
    int right;
    double output[NUM_CLASSES];
    int64_t download_us;
    int64_t inference_us;
    int64_t preprocess_us;
    int64_t invoke_us;
    char input_sha256[65];
    size_t heap_before;
    size_t heap_after;
    size_t psram_before;
    size_t psram_after;
    size_t stack_min_free_bytes;
    unsigned recovery_attempts;
    int recovery_skipped;
} report_row_t;

/* Benchmark builds a new CSV while HTTP serves the last completed pass. */
static char *g_report_text = NULL;
static size_t g_report_len = 0;
static size_t g_report_cap = 0;
static bool g_report_failed = false;
static size_t g_success, g_errors, g_labeled, g_correct, g_invalid;
static size_t g_processed, g_resumed, g_recovery_skipped;
static pthread_mutex_t report_mutex = PTHREAD_MUTEX_INITIALIZER;
static char *published_report;
static size_t published_report_len;
static size_t published_counts[8];
static unsigned published_round, published_repetitions;
static bool published_persist;

static void report_append(const char *fmt, ...) {
    if (g_report_failed) return;
    va_list args, copy;
    va_start(args, fmt);
    va_copy(copy, args);
    int n = vsnprintf(NULL, 0, fmt, copy);
    va_end(copy);
    if (n < 0) {
        va_end(args);
        g_report_failed = true;
        return;
    }
    size_t needed = g_report_len + (size_t)n + 1;
    if (needed < g_report_len) {
        va_end(args);
        g_report_failed = true;
        return;
    }
    if (needed > g_report_cap) {
        size_t new_cap = g_report_cap ? g_report_cap : REPORT_INITIAL_BYTES;
        while (new_cap < needed) {
            if (new_cap > SIZE_MAX / 2) {
                new_cap = needed;
                break;
            }
            new_cap *= 2;
        }
        char *buffer = heap_caps_realloc(g_report_text, new_cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!buffer) {
            va_end(args);
            g_report_failed = true;
            ESP_LOGE(TAG, "Sem memoria para o relatorio CSV");
            return;
        }
        g_report_text = buffer;
        g_report_cap = new_cap;
    }
    vsnprintf(g_report_text + g_report_len, (size_t)n + 1, fmt, args);
    va_end(args);
    g_report_len += (size_t)n;
}

static void report_csv_string(const char *value) {
    report_append("\"");
    for (; *value; ++value) {
        if (*value == '"') report_append("\"");
        report_append("%c", *value);
    }
    report_append("\"");
}
static void extend_task_wdt_for_benchmark(void) {
    const esp_task_wdt_config_t twdt_config = {
        .timeout_ms = BENCHMARK_WDT_TIMEOUT_MS,
        /* O benchmark monopoliza o core onde a tarefa TFLite roda por
         * periodos longos. Se mantivermos o IDLE1 monitorado, o TWDT
         * dispara mesmo com a inferencia funcionando corretamente.
         * Mantemos o monitoramento do core 0, onde ficam Wi-Fi e demais
         * tarefas do sistema, e liberamos o core da inferencia. */
        .idle_core_mask = BENCHMARK_WDT_IDLE_CORE_MASK,
        .trigger_panic = true,
    };

    esp_err_t err = esp_task_wdt_reconfigure(&twdt_config);
    if (err == ESP_ERR_INVALID_STATE) err = esp_task_wdt_init(&twdt_config);
    ESP_ERROR_CHECK(err);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Task WDT reconfigurado para %u ms durante o benchmark", (unsigned)BENCHMARK_WDT_TIMEOUT_MS);
    } else {
        ESP_LOGW(TAG, "Falha ao reconfigurar Task WDT: %s", esp_err_to_name(err));
    }
}

/* ============================================================
 * Wi-Fi
 * ============================================================ */
static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                                int32_t event_id, void *event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *event = (wifi_event_sta_disconnected_t *)event_data;
        ESP_LOGW(WIFI_TAG, "Wi-Fi desconectado. reason=%d. Tentando reconectar...", event ? event->reason : -1);
        xEventGroupClearBits(wifi_event_group, WIFI_CONNECTED_BIT);
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(WIFI_TAG, "Conectado ao Wi-Fi. IP: " IPSTR, IP2STR(&event->ip_info.ip));
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init_sta(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
            .threshold.authmode = WIFI_MIN_AUTHMODE,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(ESP_IF_WIFI_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(WIFI_TAG, "Wi-Fi inicializado");
}

/* ============================================================
 * Download de imagem via HTTP(S) direto para um buffer fixo
 * ============================================================ */
#include "download_http.inc"

static void filename_from_url(const char *url, char *out, size_t out_size) {
    const char *slash = strrchr(url, '/');
    const char *name  = slash ? slash + 1 : url;
    strncpy(out, name, out_size - 1);
    out[out_size - 1] = '\0';
}

/* ============================================================
 * Processa uma imagem: download, preparacao RGB, Invoke e metricas.
 * Execucao sincrona: a proxima imagem so entra apos Invoke retornar.
 * ============================================================ */
static void process_image(size_t index, report_row_t *row, uint8_t *img_buf) {
    const image_entry_t *entry = &IMAGES[index];
    memset(row, 0, sizeof(*row));
    filename_from_url(entry->url, row->name_image, sizeof(row->name_image));
    row->label = entry->label;
    row->result = -1;
    row->right = -1;
    if (!image_cache_load(index, img_buf, &row->download_us)) return;
    ESP_ERROR_CHECK(esp_task_wdt_reset());
    ESP_LOGI(TAG, "Imagem carregada: %s (%u bytes); calculando SHA256", row->name_image, (unsigned)INPUT_BYTES);

    uint8_t digest[32];
    if (mbedtls_sha256(img_buf, INPUT_BYTES, digest, 0) != 0) return;
    for (size_t i = 0; i < sizeof(digest); ++i) snprintf(row->input_sha256 + 2 * i, 3, "%02x", digest[i]);
    ESP_LOGI(TAG, "Iniciando preparacao + Invoke: %s | heap=%u PSRAM=%u maior_bloco_PSRAM=%u",
             row->name_image, (unsigned)esp_get_free_heap_size(),
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
    row->heap_before = esp_get_free_heap_size();
    row->psram_before = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    int64_t t0 = esp_timer_get_time();
    bool prepared = model_prepare_input(img_buf, INPUT_BYTES);
    int64_t t1 = esp_timer_get_time();
    bool invoked = prepared && model_invoke();
    int64_t t2 = esp_timer_get_time();
    row->preprocess_us = t1 - t0;
    row->invoke_us = t2 - t1;
    row->inference_us = t2 - t0; /* Includes RGB conversion, as the WASM run does. */
    row->heap_after = esp_get_free_heap_size();
    row->psram_after = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    ESP_LOGI(TAG, "Invoke retornou: %s | sucesso=%d | preprocess=%.3f ms invoke=%.3f ms",
             row->name_image, invoked, row->preprocess_us / 1000.0, row->invoke_us / 1000.0);
    row->stack_min_free_bytes = uxTaskGetStackHighWaterMark(NULL);
    if (!invoked || !model_read_output(row->output, NUM_CLASSES)) {
        ESP_LOGE(TAG, "TFLite preparation/Invoke/output failed");
        return;
    }
    int best = 0;
    bool tied = false;
    for (int c = 0; c < NUM_CLASSES; ++c) {
        if (!isfinite(row->output[c])) {
            ESP_LOGE(TAG, "Saida nao finita na classe %d", c);
            return;
        }
        if (c > 0 && row->output[c] > row->output[best]) {
            best = c;
            tied = false;
        } else if (c > 0 && row->output[c] == row->output[best]) {
            tied = true;
        }
    }
#if CLASS_LABELS_ARE_INDICES
    row->result = tied ? -1 : best;
#else
    row->result = tied ? -1 : CLASS_LABEL_MAP[best];
#endif
    row->right = entry->label < 0 ? -1 : (!tied && row->result == entry->label);
    row->ok = 1;
}

#include "checkpoint.inc"
#include "benchmark_session.inc"

static bool run_benchmark(unsigned round, unsigned repetitions, bool persist) {
    heap_caps_free(g_report_text);
    g_report_text = NULL;
    g_report_len = g_report_cap = 0;
    g_report_failed = false;
    g_success = g_errors = g_labeled = g_correct = g_invalid = 0;
    g_processed = g_resumed = g_recovery_skipped = 0;
    cp_command_id = session.id;
    cp_round = round;
    uint8_t *img_buf = heap_caps_malloc(INPUT_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    report_row_t *row = heap_caps_malloc(sizeof(*row), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!img_buf || !row) {
        g_report_failed = true;
        ESP_LOGE(TAG, "Sem memoria para buffers do benchmark");
        heap_caps_free(img_buf);
        heap_caps_free(row);
        return false;
    }
    report_append("name_image,ok");
    for (int c = 0; c < NUM_CLASSES; ++c) report_append(",class_%d_raw", c);
    report_append(",result,label,right,download_ms,inference_ms,heap_before,heap_after,"
                  "heap_used,psram_before,psram_after,psram_used,stack_min_free_bytes,preprocess_ms,invoke_ms,arena_reserved_bytes,arena_used_bytes,input_sha256,recovery_attempts,recovery_skipped\n");

    size_t success = 0, errors = 0, labeled = 0, correct = 0, invalid = 0;
    int64_t sum_us = 0, min_us = INT64_MAX, max_us = 0, sum_download_us = 0;
    if (!checkpoint_open()) {
        g_report_failed = true;
        ESP_LOGE(TAG, "Checkpoint indisponivel; benchmark interrompido para preservar resultados");
        heap_caps_free(img_buf); heap_caps_free(row);
        heap_caps_free(cp_record); cp_record = NULL;
        if (cp_nvs) { nvs_close(cp_nvs); cp_nvs = 0; }
        return false;
    }
    for (size_t i = 0; i < NUM_IMAGES; ++i) {
        ESP_ERROR_CHECK(esp_task_wdt_reset());
        int restored = checkpoint_read(row);
        if (restored < 0) { g_report_failed = true; break; }
        if (restored) {
            ++g_resumed;
        } else {
            if (i == g_resumed) ESP_LOGI(TAG, "Retomada: %u resultados restaurados; proxima imagem=%u", (unsigned)g_resumed, (unsigned)(i + 1));
            while (!(xEventGroupWaitBits(wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, pdMS_TO_TICKS(10000)) & WIFI_CONNECTED_BIT)) {
                ESP_ERROR_CHECK(esp_task_wdt_reset());
                ESP_LOGW(TAG, "Aguardando Wi-Fi; progresso preservado");
            }
            unsigned attempts = 0;
            bool skip = false;
            if (!checkpoint_attempt(i, &attempts, &skip)) { g_report_failed = true; break; }
            ESP_ERROR_CHECK(esp_task_wdt_reset());
            if (skip) {
                memset(row, 0, sizeof(*row));
                filename_from_url(IMAGES[i].url, row->name_image, sizeof(row->name_image));
                row->label = IMAGES[i].label; row->result = -1; row->right = -1;
                row->recovery_skipped = 1;
                ESP_LOGE(TAG, "Imagem %u interrompida %u vezes; registrando erro e avancando", (unsigned)(i + 1), attempts);
            } else {
                ESP_LOGI(TAG, "Processando [%u/%u], tentativa persistente %u: %s", (unsigned)(i + 1), (unsigned)NUM_IMAGES, attempts, IMAGES[i].url);
                process_image(i, row, img_buf);
            }
            row->recovery_attempts = attempts;
            ESP_ERROR_CHECK(esp_task_wdt_reset());
            if (!checkpoint_append(i, row)) { g_report_failed = true; break; }
        }
        report_csv_string(row->name_image);
        report_append(",%d", row->ok);
        for (int c = 0; c < NUM_CLASSES; ++c) {
            if (row->ok) report_append(",%.9g", row->output[c]);
            else report_append(",");
        }
        size_t heap_used = row->heap_before > row->heap_after ? row->heap_before - row->heap_after : 0;
        size_t psram_used = row->psram_before > row->psram_after ? row->psram_before - row->psram_after : 0;
        report_append(",%d,%d,%d,%.3f,%.3f,%u,%u,%u,%u,%u,%u,%u,%.3f,%.3f,%u,%u,%s,%u,%d\n",
                      row->result, row->label, row->right,
                      row->download_us / 1000.0, row->inference_us / 1000.0,
                      (unsigned)row->heap_before, (unsigned)row->heap_after, (unsigned)heap_used,
                      (unsigned)row->psram_before, (unsigned)row->psram_after, (unsigned)psram_used,
                      (unsigned)row->stack_min_free_bytes, row->preprocess_us / 1000.0, row->invoke_us / 1000.0,
                      (unsigned)TENSOR_ARENA_BYTES, (unsigned)model_arena_used_bytes(), row->input_sha256, row->recovery_attempts, row->recovery_skipped);
        if (g_report_failed) break;
        ++g_processed;
        g_recovery_skipped += row->recovery_skipped;
        vTaskDelay(pdMS_TO_TICKS(BENCHMARK_YIELD_MS) + 1);
        if (!row->ok) {
            ++errors;
            ESP_LOGE(TAG, "Falha: %s", row->name_image);
            continue;
        }
        ++success;
        if (row->result == -1) ++invalid;
        if (row->label >= 0) {
            ++labeled;
            if (row->right == 1) ++correct;
        }
        sum_us += row->inference_us;
        sum_download_us += row->download_us;
        if (row->inference_us < min_us) min_us = row->inference_us;
        if (row->inference_us > max_us) max_us = row->inference_us;
        ESP_LOGI(TAG, "%s | result=%d label=%d right=%d | download=%.3f ms inference=%.3f ms",
                 row->name_image, row->result, row->label, row->right,
                 row->download_us / 1000.0, row->inference_us / 1000.0);
    }
    ESP_LOGI(TAG, "total=%u sucesso=%u erros=%u empates=%u",
                  (unsigned)NUM_IMAGES, (unsigned)success, (unsigned)errors, (unsigned)invalid);
    ESP_LOGI(TAG, "rotuladas_com_sucesso=%u acertos=%u", (unsigned)labeled, (unsigned)correct);
    if (labeled) ESP_LOGI(TAG, "accuracy_pct=%.3f", 100.0 * correct / labeled);
    ESP_LOGI(TAG, "inference_avg_ms=%.3f inference_min_ms=%.3f inference_max_ms=%.3f",
                  success ? sum_us / (double)success / 1000.0 : 0.0,
                  success ? min_us / 1000.0 : 0.0, max_us / 1000.0);
    ESP_LOGI(TAG, "download_avg_ms=%.3f", success ? sum_download_us / (double)success / 1000.0 : 0.0);
    ESP_LOGI(TAG, "heap_min_free_bytes=%u psram_min_free_bytes=%u psram_total_bytes=%u",
                  (unsigned)esp_get_minimum_free_heap_size(),
                  (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM),
                  (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM));
    ESP_LOGI(TAG, "Checkpoint: confirmados=%u/%u restaurados=%u", (unsigned)cp_next, (unsigned)NUM_IMAGES, (unsigned)g_resumed);
    if (g_report_failed) ESP_LOGE(TAG, "Benchmark incompleto; resultados confirmados permanecem na flash");
    g_success = success; g_errors = errors; g_labeled = labeled; g_correct = correct; g_invalid = invalid;
    heap_caps_free(row);
    heap_caps_free(img_buf);
    heap_caps_free(cp_record);
    cp_record = NULL;
    nvs_close(cp_nvs);
    cp_nvs = 0;
    if (g_report_failed) return false;
    report_append("\n# round=%u repetitions=%u persist=%s\n", round, repetitions, persist ? "sim" : "nao");
    if (g_report_failed) return false;
    pthread_mutex_lock(&report_mutex);
    heap_caps_free(published_report);
    published_report = g_report_text;
    published_report_len = g_report_len;
    g_report_text = NULL;
    g_report_len = g_report_cap = 0;
    size_t counts[] = {g_success, g_errors, g_labeled, g_correct, g_invalid,
                       g_processed, g_resumed, g_recovery_skipped};
    memcpy(published_counts, counts, sizeof(counts));
    published_round = round; published_repetitions = repetitions; published_persist = persist;
    pthread_mutex_unlock(&report_mutex);
    ESP_LOGI(TAG, "Benchmark concluido: sucesso=%u erros=%u; CSV em http://<ip>:%d%s",
             (unsigned)success, (unsigned)errors, REPORT_HTTP_PORT, REPORT_HTTP_URI);
    return true;
}
/* ============================================================
 * Endpoint HTTP para baixar o relatorio (mais confiavel que
 * copiar do monitor serial quando ha muitas imagens).
 * Acesse: http://<ip_do_esp32>/report
 * ============================================================ */
static esp_err_t report_handler(httpd_req_t *req) {
    pthread_mutex_lock(&report_mutex);
    if (!published_report) {
        pthread_mutex_unlock(&report_mutex);
        httpd_resp_set_status(req, "503 Service Unavailable");
        return httpd_resp_sendstr(req, "Aguardando primeira rodada completa");
    }
    httpd_resp_set_type(req, "text/csv; charset=utf-8");
    httpd_resp_set_hdr(req, "Content-Disposition", "attachment; filename=report-tflite.csv");
    esp_err_t result = httpd_resp_send(req, published_report, published_report_len);
    pthread_mutex_unlock(&report_mutex);
    return result;
}

static esp_err_t metadata_handler(httpd_req_t *req) {
    pthread_mutex_lock(&report_mutex);
    if (!published_report) {
        pthread_mutex_unlock(&report_mutex);
        httpd_resp_set_status(req, "503 Service Unavailable");
        return httpd_resp_sendstr(req, "Aguardando primeira rodada completa");
    }
    /* This server runs synchronous handlers serially. Keep the response off
     * the httpd task stack; httpd_resp_send consumes it before returning. */
    static char json[2048];
    int n = snprintf(json, sizeof(json),
        "{\"runtime\":\"TensorFlow Lite Micro\",\"component_version\":\"1.3.5\",\"kernels\":\"ESP-NN enabled\","
        "\"model_sha256\":\"%s\",\"image_list_sha256\":\"%s\",\"idf_version\":\"%s\","
        "\"input_format\":%d,\"width\":%d,\"height\":%d,\"classes\":%d,"
        "\"output_type\":\"%s\",\"output_scale\":%.9g,\"output_zero_point\":%d,"
        "\"arena_reserved_bytes\":%u,\"arena_used_bytes\":%u,\"cpu_mhz\":%d,"
        "\"total\":%u,\"success\":%u,\"errors\":%u,\"labeled\":%u,\"correct\":%u,\"ties\":%u,"
        "\"processed\":%u,\"resumed\":%u,\"recovery_skipped\":%u,\"checkpoint_run_id\":%u,"
        "\"round\":%u,\"repetitions\":%u,\"persist\":%s,"
        "\"warmup_runs\":0,\"inference_ms_scope\":\"prepare_input + Invoke; download, checkpoint and output reading excluded\","
        "\"heap_scope\":\"free heap across capabilities; PSRAM also reported separately\"}",
        model_sha256(), IMAGE_LIST_SHA256, esp_get_idf_version(), INPUT_FORMAT, IMG_W, IMG_H, NUM_CLASSES,
        model_output_type(), model_output_scale(), model_output_zero_point(),
        (unsigned)TENSOR_ARENA_BYTES, (unsigned)model_arena_used_bytes(), CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ,
        (unsigned)NUM_IMAGES, (unsigned)published_counts[0], (unsigned)published_counts[1], (unsigned)published_counts[2],
        (unsigned)published_counts[3], (unsigned)published_counts[4], (unsigned)published_counts[5],
        (unsigned)published_counts[6], (unsigned)published_counts[7], (unsigned)BENCHMARK_RUN_ID,
        published_round, published_repetitions, published_persist ? "true" : "false");
    pthread_mutex_unlock(&report_mutex);
    if (n < 0 || (size_t)n >= sizeof(json)) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Metadata too large");
    httpd_resp_set_type(req, "application/json");
    return httpd_resp_send(req, json, n);
}

static void start_file_server(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = REPORT_HTTP_PORT;
    config.stack_size = REPORT_HTTP_STACK_BYTES;
    httpd_handle_t server = NULL;
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t report_uri = {
            .uri      = REPORT_HTTP_URI,
            .method   = HTTP_GET,
            .handler  = report_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &report_uri);
        const httpd_uri_t metadata_uri = { .uri = "/metadata", .method = HTTP_GET, .handler = metadata_handler };
        httpd_register_uri_handler(server, &metadata_uri);
        esp_netif_ip_info_t ip;
        esp_netif_t *netif = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
        if (netif && esp_netif_get_ip_info(netif, &ip) == ESP_OK) {
            ESP_LOGI(TAG_HTTP, "Download CSV: http://" IPSTR ":%d%s", IP2STR(&ip.ip), REPORT_HTTP_PORT, REPORT_HTTP_URI);
            ESP_LOGI(TAG_HTTP, "Metadata: http://" IPSTR ":%d/metadata", IP2STR(&ip.ip), REPORT_HTTP_PORT);
        }
        ESP_LOGI(TAG_HTTP, "Servidor HTTP iniciado. Relatorio em: http://<ip_do_esp32>:%d%s",
                 REPORT_HTTP_PORT, REPORT_HTTP_URI);
    } else {
        ESP_LOGE(TAG_HTTP, "Falha ao iniciar o servidor HTTP");
    }
}

void image_cache_keep_alive(void) {
    ESP_ERROR_CHECK(esp_task_wdt_reset());
}

static void read_command(char *line, size_t capacity) {
    size_t len = 0;
    bool overflow = false;
    while (1) {
        image_cache_keep_alive();
        int ch = getchar();
        if (ch == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20) + 1);
            continue;
        }
        if (ch == '\r' || ch == '\n') {
            if (!len && !overflow) continue;
            putchar('\n');
            line[overflow ? 0 : len] = '\0';
            if (overflow) ESP_LOGE(TAG, "Comando muito longo");
            return;
        }
        if (ch == 8 || ch == 127) {
            if (len) { --len; printf("\b \b"); }
        } else if (ch >= 32 && ch < 127) {
            if (len + 1 < capacity) { line[len++] = (char)ch; putchar(ch); }
            else overflow = true;
        }
        fflush(stdout);
    }
}

static bool parse_command(const char *line, unsigned *repetitions, bool *persist) {
    char command[16], count[24], save[8], extra[2];
    if (sscanf(line, "%15s %23s %7s %1s", command, count, save, extra) != 3
        || strcmp(command, "benchmark") != 0
        || (strcmp(save, "sim") != 0 && strcmp(save, "nao") != 0)) return false;
    for (const char *p = count; *p; ++p) if (*p < '0' || *p > '9') return false;
    errno = 0;
    char *end;
    unsigned long value = strtoul(count, &end, 10);
    if (errno || *end || value == 0 || value > UINT_MAX) return false;
    *repetitions = (unsigned)value;
    *persist = strcmp(save, "sim") == 0;
    return true;
}

static void run_session(void) {
    if (!image_cache_prepare(session.persist != 0, session.repetitions)) {
        image_cache_release();
        if (!session_cancel()) ESP_LOGE(TAG, "Falha cancelando comando persistente");
        ESP_LOGE(TAG, "Preparacao falhou; nenhuma rodada iniciada.");
        return;
    }
    while (1) {
        image_cache_keep_alive();
        ESP_LOGI(TAG, "Iniciando rodada %u/%u (%u imagens)", (unsigned)session.round,
                 (unsigned)session.repetitions, (unsigned)NUM_IMAGES);
        if (!run_benchmark(session.round, session.repetitions, session.persist != 0)) {
            ESP_LOGE(TAG, "Rodada interrompida; checkpoint preservado para recuperacao apos reiniciar.");
            break;
        }
        bool last = session.round == session.repetitions;
        if (last) session.active = 0;
        else ++session.round;
        if (!session_save()) {
            ESP_LOGE(TAG, "Falha salvando progresso do comando; execucao interrompida.");
            break;
        }
        if (last) break;
        ESP_LOGI(TAG, "CSV e metadata disponiveis; proxima rodada em 10 segundos.");
        vTaskDelay(pdMS_TO_TICKS(10000));
    }
    image_cache_release();
}

static void benchmark_task(void *arg) {
    (void)arg;
    extend_task_wdt_for_benchmark();
#if !CLASS_LABELS_ARE_INDICES
    for (int i = 0; i < NUM_CLASSES; ++i) {
        if (CLASS_LABEL_MAP[i] < 0) { ESP_LOGE(TAG, "Negative class label"); vTaskDelete(NULL); return; }
        for (int j = 0; j < i; ++j) {
            if (CLASS_LABEL_MAP[i] == CLASS_LABEL_MAP[j]) { ESP_LOGE(TAG, "Duplicate class label"); vTaskDelete(NULL); return; }
        }
    }
#endif
    if (!model_initialize()) {
        ESP_LOGE(TAG, "TFLite initialization failed; no benchmark was executed");
        vTaskDelete(NULL);
        return;
    }
    ESP_ERROR_CHECK(esp_task_wdt_add(NULL));
    ESP_ERROR_CHECK(esp_task_wdt_reset());
    start_file_server();
    setvbuf(stdin, NULL, _IONBF, 0);
    if (session_load()) {
        if (session.active) {
            ESP_LOGI(TAG, "Retomando comando %u, rodada %u/%u", (unsigned)session.id,
                     (unsigned)session.round, (unsigned)session.repetitions);
            run_session();
        } else {
            ESP_LOGI(TAG, "Restaurando relatorio da ultima rodada concluida");
            if (!run_benchmark(session.round, session.repetitions, session.persist != 0))
                ESP_LOGE(TAG, "Falha restaurando relatorio");
        }
    }
    while (1) {
        char command[96];
        unsigned repetitions;
        bool persist;
        printf("\nComando: benchmark <rodadas> <sim|nao> (gravar imagens na flash)\n> ");
        fflush(stdout);
        read_command(command, sizeof(command));
        if (!parse_command(command, &repetitions, &persist)) {
            ESP_LOGE(TAG, "Use benchmark 10 sim ou benchmark 10 nao; rodadas deve ser inteiro positivo.");
            continue;
        }
        if (!session_start(repetitions, persist)) {
            ESP_LOGE(TAG, "Falha persistindo comando; nenhuma rodada iniciada.");
            continue;
        }
        run_session();
    }
}

void app_main(void) {
    wifi_init_sta();
    EventBits_t bits = xEventGroupWaitBits(wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE,
                                          pdMS_TO_TICKS(WIFI_CONNECT_TIMEOUT_MS));
    if (!(bits & WIFI_CONNECTED_BIT)) {
        ESP_LOGE(WIFI_TAG, "Wi-Fi timeout; reiniciando com progresso preservado");
        esp_restart();
        return;
    }
#if CONFIG_FREERTOS_UNICORE
    const int core = 0;
#else
    const int core = BENCHMARK_TASK_CORE;
#endif
    if (xTaskCreatePinnedToCore(benchmark_task, "tflite_benchmark", BENCHMARK_THREAD_STACK_BYTES,
                               NULL, BENCHMARK_TASK_PRIORITY, NULL, core) != pdPASS) {
        ESP_LOGE(TAG, "Could not create benchmark task");
    }
}
