#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
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
} report_row_t;

/* O servidor inicia depois do benchmark: o CSV servido e imutavel. */
static char *g_report_text = NULL;
static size_t g_report_len = 0;
static size_t g_report_cap = 0;
static bool g_report_failed = false;
static size_t g_success, g_errors, g_labeled, g_correct, g_invalid;

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
#if CONFIG_ESP_TASK_WDT_PANIC
        .trigger_panic = true,
#else
        .trigger_panic = false,
#endif
    };

    esp_err_t err = esp_task_wdt_reconfigure(&twdt_config);
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
typedef struct {
    uint8_t *buf;
    size_t   capacity;
    size_t   len;
    bool overflow;
} http_download_ctx_t;

static esp_err_t http_event_handler(esp_http_client_event_t *evt) {
    http_download_ctx_t *ctx = (http_download_ctx_t *)evt->user_data;
    if (evt->event_id == HTTP_EVENT_ON_DATA) {
        if (evt->data_len >= 0 && (size_t)evt->data_len <= ctx->capacity - ctx->len) {
            memcpy(ctx->buf + ctx->len, evt->data, evt->data_len);
            ctx->len += evt->data_len;
        } else {
            ctx->overflow = true;
            ESP_LOGE(TAG_HTTP, "Buffer estourado ao baixar imagem (%u + %u > %u)",
                     (unsigned)ctx->len, (unsigned)evt->data_len, (unsigned)ctx->capacity);
        }
    }
    return ESP_OK;
}

/* Baixa a imagem crua (raw) da URL para out_buf. Retorna true em sucesso. */
static bool download_image(const char *url, uint8_t *out_buf, size_t expected_len, int64_t *download_us) {
    http_download_ctx_t ctx = { .buf = out_buf, .capacity = expected_len, .len = 0 };

    esp_http_client_config_t config = {
        .url = url,
        .event_handler = http_event_handler,
        .user_data = &ctx,
        .timeout_ms = HTTP_DOWNLOAD_TIMEOUT_MS,
        .is_async = true, /* Cloudinary URLs are HTTPS. */
        .crt_bundle_attach = esp_crt_bundle_attach, // necessário para https://
        .keep_alive_enable = HTTP_KEEP_ALIVE_ENABLE,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG_HTTP, "Falha ao iniciar cliente HTTP");
        return false;
    }

    int64_t t0 = esp_timer_get_time();
    esp_err_t err;
    int64_t next_progress = t0 + (int64_t)HTTP_PROGRESS_INTERVAL_MS * 1000;
    do {
        err = esp_http_client_perform(client);
        int64_t now = esp_timer_get_time();
        if (ctx.overflow) { err = ESP_ERR_INVALID_SIZE; break; }
        if (now - t0 >= (int64_t)HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS * 1000) {
            ESP_LOGE(TAG_HTTP, "Download excedeu limite total: %u/%u bytes", (unsigned)ctx.len, (unsigned)expected_len);
            err = ESP_ERR_TIMEOUT;
            break;
        }
        if (err == ESP_ERR_HTTP_EAGAIN) {
            if (now >= next_progress) {
                ESP_LOGW(TAG_HTTP, "Download em andamento: %u/%u bytes, %.1f s, status=%d",
                         (unsigned)ctx.len, (unsigned)expected_len, (now - t0) / 1000000.0,
                         esp_http_client_get_status_code(client));
                next_progress = now + (int64_t)HTTP_PROGRESS_INTERVAL_MS * 1000;
            }
            vTaskDelay(pdMS_TO_TICKS(10) + 1);
        }
    } while (err == ESP_ERR_HTTP_EAGAIN);
    int64_t t1 = esp_timer_get_time();
    if (download_us) *download_us = t1 - t0;

    int status = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);

    if (err != ESP_OK) {
        ESP_LOGE(TAG_HTTP, "Erro HTTP ao baixar %s: %s", url, esp_err_to_name(err));
        return false;
    }
    if (status != 200) {
        ESP_LOGE(TAG_HTTP, "Status HTTP %d ao baixar %s", status, url);
        return false;
    }
    if (ctx.overflow || ctx.len != expected_len) {
        ESP_LOGE(TAG_HTTP, "Tamanho inesperado: esperado=%u recebido=%u (%s)",
                 (unsigned)expected_len, (unsigned)ctx.len, url);
        return false;
    }
    return true;
}

/* Extrai um "nome de arquivo" simples a partir da URL, só para o relatório */
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
static void process_image(const image_entry_t *entry, report_row_t *row, uint8_t *img_buf) {
    memset(row, 0, sizeof(*row));
    filename_from_url(entry->url, row->name_image, sizeof(row->name_image));
    row->label = entry->label;
    row->result = -1;
    row->right = -1;
    if (!download_image(entry->url, img_buf, INPUT_BYTES, &row->download_us)) return;
    ESP_LOGI(TAG, "Download concluido: %s (%u bytes); calculando SHA256", row->name_image, (unsigned)INPUT_BYTES);

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

static void run_benchmark(void) {
    uint8_t *img_buf = heap_caps_malloc(INPUT_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    report_row_t *row = heap_caps_malloc(sizeof(*row), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!img_buf || !row) {
        g_report_failed = true;
        ESP_LOGE(TAG, "Sem memoria para buffers do benchmark");
        heap_caps_free(img_buf);
        heap_caps_free(row);
        return;
    }
    report_append("name_image,ok");
    for (int c = 0; c < NUM_CLASSES; ++c) report_append(",class_%d_raw", c);
    report_append(",result,label,right,download_ms,inference_ms,heap_before,heap_after,"
                  "heap_used,psram_before,psram_after,psram_used,stack_min_free_bytes,preprocess_ms,invoke_ms,arena_reserved_bytes,arena_used_bytes,input_sha256\n");

    size_t success = 0, errors = 0, labeled = 0, correct = 0, invalid = 0;
    int64_t sum_us = 0, min_us = INT64_MAX, max_us = 0, sum_download_us = 0;
    for (size_t i = 0; i < NUM_IMAGES; ++i) {
        ESP_LOGI(TAG, "Processando [%u/%u]: %s", (unsigned)(i + 1), (unsigned)NUM_IMAGES, IMAGES[i].url);
        process_image(&IMAGES[i], row, img_buf);
        report_csv_string(row->name_image);
        report_append(",%d", row->ok);
        for (int c = 0; c < NUM_CLASSES; ++c) {
            if (row->ok) report_append(",%.9g", row->output[c]);
            else report_append(",");
        }
        size_t heap_used = row->heap_before > row->heap_after ? row->heap_before - row->heap_after : 0;
        size_t psram_used = row->psram_before > row->psram_after ? row->psram_before - row->psram_after : 0;
        report_append(",%d,%d,%d,%.3f,%.3f,%u,%u,%u,%u,%u,%u,%u,%.3f,%.3f,%u,%u,%s\n",
                      row->result, row->label, row->right,
                      row->download_us / 1000.0, row->inference_us / 1000.0,
                      (unsigned)row->heap_before, (unsigned)row->heap_after, (unsigned)heap_used,
                      (unsigned)row->psram_before, (unsigned)row->psram_after, (unsigned)psram_used,
                      (unsigned)row->stack_min_free_bytes, row->preprocess_us / 1000.0, row->invoke_us / 1000.0,
                      (unsigned)TENSOR_ARENA_BYTES, (unsigned)model_arena_used_bytes(), row->input_sha256);
        if (g_report_failed) break;
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
    ESP_LOGI(TAG, "Benchmark concluido: sucesso=%u erros=%u; CSV em http://<ip>:%d%s",
             (unsigned)success, (unsigned)errors, REPORT_HTTP_PORT, REPORT_HTTP_URI);
    g_success = success; g_errors = errors; g_labeled = labeled; g_correct = correct; g_invalid = invalid;
    heap_caps_free(row);
    heap_caps_free(img_buf);
}
/* ============================================================
 * Endpoint HTTP para baixar o relatorio (mais confiavel que
 * copiar do monitor serial quando ha muitas imagens).
 * Acesse: http://<ip_do_esp32>/report
 * ============================================================ */
static esp_err_t report_handler(httpd_req_t *req) {
    if (g_report_failed || !g_report_text) {
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "Relatorio indisponivel ou incompleto");
    }
    httpd_resp_set_type(req, "text/csv; charset=utf-8");
    httpd_resp_set_hdr(req, "Content-Disposition", "attachment; filename=report-tflite.csv");
    return httpd_resp_send(req, g_report_text, g_report_len);
}

static esp_err_t metadata_handler(httpd_req_t *req) {
    if (g_report_failed || !g_report_text) {
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Benchmark incomplete");
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
        "\"warmup_runs\":0,\"inference_ms_scope\":\"prepare_input + Invoke; download and output reading excluded\","
        "\"heap_scope\":\"free heap across capabilities; PSRAM also reported separately\"}",
        model_sha256(), IMAGE_LIST_SHA256, esp_get_idf_version(), INPUT_FORMAT, IMG_W, IMG_H, NUM_CLASSES,
        model_output_type(), model_output_scale(), model_output_zero_point(),
        (unsigned)TENSOR_ARENA_BYTES, (unsigned)model_arena_used_bytes(), CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ,
        (unsigned)NUM_IMAGES, (unsigned)g_success, (unsigned)g_errors, (unsigned)g_labeled,
        (unsigned)g_correct, (unsigned)g_invalid);
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
    run_benchmark();
    start_file_server();
    vTaskDelete(NULL);
}

void app_main(void) {
    wifi_init_sta();
    EventBits_t bits = xEventGroupWaitBits(wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE,
                                          pdMS_TO_TICKS(WIFI_CONNECT_TIMEOUT_MS));
    if (!(bits & WIFI_CONNECTED_BIT)) {
        ESP_LOGE(WIFI_TAG, "Wi-Fi timeout: check host_config.h");
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
