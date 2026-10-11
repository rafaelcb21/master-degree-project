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
#include "bh_platform.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "wasm_export.h"
#include "esp_event.h"
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
#include "image_cache.h"

#define TAG "wasm_benchmark"
#define TAG_HTTP "HTTP_SERVER"
#define WIFI_TAG "wi-fi"
static EventGroupHandle_t wifi_event_group;
static const int WIFI_CONNECTED_BIT = BIT0;
static const int CLASS_LABEL_MAP[] = CLASS_LABELS;
_Static_assert(sizeof(CLASS_LABEL_MAP) / sizeof(CLASS_LABEL_MAP[0]) == NUM_CLASSES,
               "CLASS_LABELS deve ter NUM_CLASSES rotulos");
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
    size_t heap_before;
    size_t heap_after;
    size_t psram_before;
    size_t psram_after;
    size_t stack_min_free_bytes;
} report_row_t;

/* Builder owned by the benchmark; completed CSV published under a mutex. */
static char *g_report_text = NULL;
static size_t g_report_len = 0;
static size_t g_report_cap = 0;
static bool g_report_failed = false;
static pthread_mutex_t report_mutex = PTHREAD_MUTEX_INITIALIZER;
static char *published_report;
static size_t published_report_len;

static bool publish_report(void) {
    if (g_report_failed || !g_report_text) {
        ESP_LOGE(TAG, "Rodada sem relatorio completo; relatorio anterior preservado");
        return false;
    }
    pthread_mutex_lock(&report_mutex);
    heap_caps_free(published_report);
    published_report = g_report_text;
    published_report_len = g_report_len;
    g_report_text = NULL;
    g_report_len = g_report_cap = 0;
    pthread_mutex_unlock(&report_mutex);
    return true;
}

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
/* ============================================================
 * WASM runtime
 * ============================================================ */
static wasm_module_inst_t module_inst = NULL;
static wasm_exec_env_t    exec_env    = NULL;
static wasm_module_t      module_handle = NULL;
static uint8_t           *g_wasm_file_buf = NULL;

#if MODEL_MODULE_IS_AOT
extern const uint8_t model_aot_start[] asm("_binary_main_aot_start");
extern const uint8_t model_aot_end[] asm("_binary_main_aot_end");
#else
extern const uint8_t model_wasm_start[] asm("_binary_main_wasm_start");
extern const uint8_t model_wasm_end[] asm("_binary_main_wasm_end");
#endif

/* ============================================================
 * Alocador customizado do WAMR: força a memória linear do WASM
 * (pesos, biases, slots, params — ~1,1MB) a vir da PSRAM,
 * em vez de depender do malloc() padrão (que prioriza a SRAM
 * interna, pequena e disputada com Wi-Fi/HTTP/etc).
 *
 * OBS: se compilar com uma versão do WAMR onde os nomes dos
 * campos de MemAllocOption.allocator forem diferentes (ex.:
 * "alloc"/"realloc"/"free" em vez de "malloc_func"/...),
 * confira o wasm_export.h da sua versão e ajuste os nomes.
 * ============================================================ */
static void *psram_malloc(unsigned int size) {
    void *ptr = heap_caps_malloc(size, MALLOC_CAP_SPIRAM);
    if (!ptr) {
        ESP_LOGW(TAG, "PSRAM sem espaco para %u bytes, caindo para heap interna", size);
        ptr = malloc(size);
    }
    return ptr;
}

static void *psram_realloc(void *ptr, unsigned int size) {
    void *new_ptr = heap_caps_realloc(ptr, size, MALLOC_CAP_SPIRAM);
    if (!new_ptr) {
        ESP_LOGW(TAG, "PSRAM sem espaco para realloc de %u bytes, caindo para heap interna", size);
        new_ptr = realloc(ptr, size);
    }
    return new_ptr;
}

static void psram_free(void *ptr) {
    /* heap_caps_free funciona tanto para ponteiros vindos de heap_caps_malloc
     * quanto de malloc() comum, pois o alocador do ESP-IDF é unificado por baixo. */
    heap_caps_free(ptr);
}

/* Chama uma função WASM exportada sem parâmetros, que retorna i32.
 * Reaproveita o mesmo exec_env (chamadas sequenciais, sem concorrência). */
static int32_t call_wasm_i32(const char *fname) {
    wasm_function_inst_t func = wasm_runtime_lookup_function(module_inst, fname, NULL);
    if (!func) {
        ESP_LOGE(TAG, "Funcao WASM nao encontrada: %s (recompilou o .wasm?)", fname);
        return -1;
    }
    uint32_t argv[1] = {0};
    if (!wasm_runtime_call_wasm(exec_env, func, 0, argv)) {
        const char *exception = wasm_runtime_get_exception(module_inst);
        ESP_LOGE(TAG, "Erro ao chamar %s: %s", fname, exception ? exception : "sem detalhes");
        return -1;
    }
    return (int32_t)argv[0];
}

static bool require_wasm_export(const char *fname) {
    wasm_function_inst_t func = wasm_runtime_lookup_function(module_inst, fname, NULL);
    if (!func) {
        ESP_LOGE(TAG, "Export WASM obrigatorio ausente: %s", fname);
        return false;
    }
    return true;
}

static void destroy_wasm_runtime(void) {
    if (exec_env) {
        wasm_runtime_destroy_exec_env(exec_env);
        exec_env = NULL;
    }
    if (module_inst) {
        wasm_runtime_deinstantiate(module_inst);
        module_inst = NULL;
    }
    if (module_handle) {
        wasm_runtime_unload(module_handle);
        module_handle = NULL;
    }
    if (g_wasm_file_buf) {
        heap_caps_free(g_wasm_file_buf);
        g_wasm_file_buf = NULL;
    }
    wasm_runtime_destroy();
}

static void extend_task_wdt_for_benchmark(void) {
    const esp_task_wdt_config_t twdt_config = {
        .timeout_ms = BENCHMARK_WDT_TIMEOUT_MS,
        /* O benchmark monopoliza o core onde a pthread do WAMR roda por
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

static bool initialize_wasm_runtime(void) {
#if MODEL_MODULE_IS_AOT
    const uint8_t *wasm_file_flash = model_aot_start;
    uint32_t wasm_file_size = (uint32_t)(model_aot_end - model_aot_start);
#else
    const uint8_t *wasm_file_flash = model_wasm_start;
    uint32_t wasm_file_size = (uint32_t)(model_wasm_end - model_wasm_start);
#endif
    char error_buf[WASM_ERROR_BUFFER_BYTES];

    RuntimeInitArgs init_args;
    memset(&init_args, 0, sizeof(RuntimeInitArgs));

    ESP_LOGI(TAG, "PSRAM total: %u bytes | PSRAM livre antes de instanciar o WASM: %u bytes",
             (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    ESP_LOGI(TAG, "Artefato embutido selecionado no build: %s", MODEL_MODULE_KIND);

    init_args.mem_alloc_type = Alloc_With_Allocator;
    init_args.mem_alloc_option.allocator.malloc_func  = (void *)psram_malloc;
    init_args.mem_alloc_option.allocator.realloc_func = (void *)psram_realloc;
    init_args.mem_alloc_option.allocator.free_func    = (void *)psram_free;

    if (!wasm_runtime_full_init(&init_args)) {
        ESP_LOGE(TAG, "Falha ao inicializar o runtime WASM");
        return false;
    }

    g_wasm_file_buf = (uint8_t *)heap_caps_malloc(wasm_file_size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!g_wasm_file_buf) {
        ESP_LOGW(TAG, "Falha ao alocar buffer do WASM na PSRAM; tentando heap interna");
        g_wasm_file_buf = (uint8_t *)malloc(wasm_file_size);
    }
    if (!g_wasm_file_buf) {
        ESP_LOGE(TAG, "Falha ao alocar %u bytes para copiar o modulo WASM", (unsigned)wasm_file_size);
        wasm_runtime_destroy();
        return false;
    }

    memcpy(g_wasm_file_buf, wasm_file_flash, wasm_file_size);

    module_handle = wasm_runtime_load(g_wasm_file_buf, wasm_file_size, error_buf, sizeof(error_buf));
    if (!module_handle) {
        ESP_LOGE(TAG, "Falha ao carregar o modulo WASM: %s", error_buf);
        destroy_wasm_runtime();
        return false;
    }

    /* Nao libere g_wasm_file_buf aqui.
     * O WAMR mantem referencias a partes do binario carregado
     * (nomes de import/export e outros metadados). Se o buffer
     * for liberado neste ponto, o lookup de funcoes pode falhar
     * mesmo com o export existindo no .wasm. */
    /* O modulo usa memoria linear/exportada para pesos, slots e saida.
     * Nao precisamos reservar app heap do WAMR aqui.
     * Isso evita o erro "init app heap failed" causado pelo alinhamento
     * do pool do app heap dentro da memoria linear do modulo. */
    module_inst = wasm_runtime_instantiate(module_handle, WASM_MODULE_STACK_BYTES, WASM_APP_HEAP_BYTES, error_buf, sizeof(error_buf));
    if (!module_inst) {
        ESP_LOGE(TAG, "Falha ao instanciar o modulo WASM: %s", error_buf);
        destroy_wasm_runtime();
        return false;
    }

    ESP_LOGI(TAG, "WASM instanciado. PSRAM livre apos instanciar: %u bytes (consumo aprox: memoria linear + heap/stack do modulo)",
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));

    exec_env = wasm_runtime_create_exec_env(module_inst, WASM_EXEC_STACK_BYTES);
    if (!exec_env) {
        ESP_LOGE(TAG, "Falha ao criar exec_env WASM");
        destroy_wasm_runtime();
        return false;
    }

    if ((USE_READY_HANDSHAKE && !require_wasm_export(WASM_READY_EXPORT))
        || !require_wasm_export(WASM_INPUT_PTR_EXPORT)
        || !require_wasm_export(WASM_RUN_EXPORT)
        || !require_wasm_export(WASM_OUTPUT_PTR_EXPORT)) {
        ESP_LOGE(TAG, "O modulo WASM embutido nao corresponde a interface esperada pelo firmware");
        destroy_wasm_runtime();
        return false;
    }

    return true;
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
bool download_image(const char *url, uint8_t *out_buf, size_t expected_len, int64_t *download_us) {
    http_download_ctx_t ctx = { .buf = out_buf, .capacity = expected_len, .len = 0 };

    esp_http_client_config_t config = {
        .url = url,
        .event_handler = http_event_handler,
        .user_data = &ctx,
        .timeout_ms = HTTP_DOWNLOAD_TIMEOUT_MS,
        .crt_bundle_attach = esp_crt_bundle_attach, // necessário para https://
        .keep_alive_enable = HTTP_KEEP_ALIVE_ENABLE,
    };

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) {
        ESP_LOGE(TAG_HTTP, "Falha ao iniciar cliente HTTP");
        return false;
    }

    int64_t t0 = esp_timer_get_time();
    esp_err_t err = esp_http_client_perform(client);
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
 * Processa uma imagem: baixa, aguarda o WASM ficar pronto,
 * escreve na memoria, roda a inferencia e coleta metricas.
 * ============================================================ */
static void process_image(size_t index, report_row_t *row, uint8_t *img_buf) {
    const image_entry_t *entry = &IMAGES[index];
    memset(row, 0, sizeof(*row));
    filename_from_url(entry->url, row->name_image, sizeof(row->name_image));
    row->label = entry->label;
    row->result = -1;
    row->right = -1;
    if (!image_cache_load(index, img_buf, &row->download_us)) return;

    if (USE_READY_HANDSHAKE) {
        int64_t deadline = esp_timer_get_time() + (int64_t)READY_TIMEOUT_MS * 1000;
        for (;;) {
            int32_t ready = call_wasm_i32(WASM_READY_EXPORT);
            if (ready == 1) break;
            if (ready < 0 || esp_timer_get_time() >= deadline) {
                ESP_LOGE(TAG, "Falha/timeout aguardando modulo pronto; imagem descartada");
                return;
            }
            TickType_t ticks = pdMS_TO_TICKS(READY_POLL_MS);
            vTaskDelay(ticks ? ticks : 1);
        }
    }

    int32_t input_ptr = call_wasm_i32(WASM_INPUT_PTR_EXPORT);
    if (input_ptr < 0 || !wasm_runtime_validate_app_addr(module_inst, (uint32_t)input_ptr, INPUT_BYTES)) {
        ESP_LOGE(TAG, "Regiao de entrada invalida");
        return;
    }
    uint8_t *input = wasm_runtime_addr_app_to_native(module_inst, (uint32_t)input_ptr);
    if (!input) return;
    memcpy(input, img_buf, INPUT_BYTES);
#if WRITE_FORMAT_FLAG
    if (!wasm_runtime_validate_app_addr(module_inst, FORMAT_FLAG_ADDR, 1)) return;
    uint8_t *format = wasm_runtime_addr_app_to_native(module_inst, FORMAT_FLAG_ADDR);
    if (!format) return;
    *format = INPUT_FORMAT_VALUE;
#endif

    row->heap_before = esp_get_free_heap_size();
    row->psram_before = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    int64_t t0 = esp_timer_get_time();
    int32_t status = call_wasm_i32(WASM_RUN_EXPORT);
    row->inference_us = esp_timer_get_time() - t0;
    row->heap_after = esp_get_free_heap_size();
    row->psram_after = heap_caps_get_free_size(MALLOC_CAP_SPIRAM);
    /* ESP-IDF informa o high-water mark em bytes. */
    row->stack_min_free_bytes = uxTaskGetStackHighWaterMark(NULL);
    if (status != INFERENCE_SUCCESS_CODE) {
        ESP_LOGE(TAG, "Inferencia falhou: status=%" PRId32, status);
        return;
    }

    int32_t output_ptr = call_wasm_i32(WASM_OUTPUT_PTR_EXPORT);
    if (output_ptr < 0 || !wasm_runtime_validate_app_addr(module_inst, (uint32_t)output_ptr, OUTPUT_BYTES)) {
        ESP_LOGE(TAG, "Regiao de saida invalida");
        return;
    }
    const uint8_t *output = wasm_runtime_addr_app_to_native(module_inst, (uint32_t)output_ptr);
    if (!output) return;
    int best = 0;
    bool tied = false;
    for (int c = 0; c < NUM_CLASSES; ++c) {
#if OUTPUT_TYPE == OUTPUT_FLOAT32
        float value;
        memcpy(&value, output + c * OUTPUT_ELEMENT_BYTES, sizeof(value));
        row->output[c] = value;
#elif OUTPUT_TYPE == OUTPUT_INT8
        row->output[c] = (int8_t)output[c];
#else
        row->output[c] = output[c];
#endif
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
    row->result = tied ? -1 : CLASS_LABEL_MAP[best];
    row->right = entry->label < 0 ? -1 : (!tied && row->result == entry->label);
    row->ok = 1;
}

static bool run_benchmark(unsigned round, unsigned repetitions, bool persist) {
    heap_caps_free(g_report_text);
    g_report_text = NULL;
    g_report_len = g_report_cap = 0;
    g_report_failed = false;
    uint8_t *img_buf = heap_caps_malloc(INPUT_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    report_row_t *row = heap_caps_malloc(sizeof(*row), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!img_buf || !row) {
        ESP_LOGE(TAG, "Sem memoria para buffers do benchmark");
        heap_caps_free(img_buf);
        heap_caps_free(row);
        return false;
    }
    report_append("name_image,ok");
    for (int c = 0; c < NUM_CLASSES; ++c) report_append(",class_%d_raw", c);
    report_append(",result,label,right,download_ms,inference_ms,heap_before,heap_after,"
                  "heap_used,psram_before,psram_after,psram_used,stack_min_free_bytes\n");

    size_t success = 0, errors = 0, labeled = 0, correct = 0, invalid = 0;
    int64_t sum_us = 0, min_us = INT64_MAX, max_us = 0, sum_download_us = 0;
    for (size_t i = 0; i < NUM_IMAGES; ++i) {
        ESP_LOGI(TAG, "Processando [%u/%u]: %s", (unsigned)(i + 1), (unsigned)NUM_IMAGES, IMAGES[i].url);
        process_image(i, row, img_buf);
        report_csv_string(row->name_image);
        report_append(",%d", row->ok);
        for (int c = 0; c < NUM_CLASSES; ++c) {
            if (row->ok) report_append(",%.9g", row->output[c]);
            else report_append(",");
        }
        size_t heap_used = row->heap_before > row->heap_after ? row->heap_before - row->heap_after : 0;
        size_t psram_used = row->psram_before > row->psram_after ? row->psram_before - row->psram_after : 0;
        report_append(",%d,%d,%d,%.3f,%.3f,%u,%u,%u,%u,%u,%u,%u\n",
                      row->result, row->label, row->right,
                      row->download_us / 1000.0, row->inference_us / 1000.0,
                      (unsigned)row->heap_before, (unsigned)row->heap_after, (unsigned)heap_used,
                      (unsigned)row->psram_before, (unsigned)row->psram_after, (unsigned)psram_used,
                      (unsigned)row->stack_min_free_bytes);
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
    report_append("\n# round=%u repetitions=%u persist=%s\n", round, repetitions, persist ? "sim" : "nao");
    report_append("# total=%u sucesso=%u erros=%u empates=%u\n",
                  (unsigned)NUM_IMAGES, (unsigned)success, (unsigned)errors, (unsigned)invalid);
    report_append("# rotuladas_com_sucesso=%u acertos=%u\n", (unsigned)labeled, (unsigned)correct);
    if (labeled) report_append("# accuracy_pct=%.3f\n", 100.0 * correct / labeled);
    report_append("# inference_avg_ms=%.3f inference_min_ms=%.3f inference_max_ms=%.3f\n",
                  success ? sum_us / (double)success / 1000.0 : 0.0,
                  success ? min_us / 1000.0 : 0.0, max_us / 1000.0);
    report_append("# download_avg_ms=%.3f\n", success ? sum_download_us / (double)success / 1000.0 : 0.0);
    report_append("# heap_min_free_bytes=%u psram_min_free_bytes=%u psram_total_bytes=%u\n",
                  (unsigned)esp_get_minimum_free_heap_size(),
                  (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM),
                  (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM));
    heap_caps_free(row);
    heap_caps_free(img_buf);
    if (!publish_report()) return false;
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
    esp_err_t result = httpd_resp_send(req, published_report, published_report_len);
    pthread_mutex_unlock(&report_mutex);
    return result;
}

static void start_file_server(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = REPORT_HTTP_PORT;
    httpd_handle_t server = NULL;
    if (httpd_start(&server, &config) == ESP_OK) {
        httpd_uri_t report_uri = {
            .uri      = REPORT_HTTP_URI,
            .method   = HTTP_GET,
            .handler  = report_handler,
            .user_ctx = NULL
        };
        httpd_register_uri_handler(server, &report_uri);
        ESP_LOGI(TAG_HTTP, "Servidor HTTP iniciado. Relatorio em: http://<ip_do_esp32>:%d%s",
                 REPORT_HTTP_PORT, REPORT_HTTP_URI);
    } else {
        ESP_LOGE(TAG_HTTP, "Falha ao iniciar o servidor HTTP");
    }
}

/* The default ESP-IDF console uses nonblocking UART reads. Poll with a delay
 * to keep Wi-Fi/IDLE tasks running, and accept either CR or LF from monitors. */
static void read_command(char *line, size_t capacity) {
    size_t len = 0;
    bool overflow = false;
    while (1) {
        int ch = getchar();
        if (ch == EOF) {
            clearerr(stdin);
            vTaskDelay(pdMS_TO_TICKS(20));
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

static void *benchmark_thread_main(void *arg) {
    (void)arg;

    if (!wasm_runtime_init_thread_env()) {
        ESP_LOGE(TAG, "Falha ao inicializar thread env do WAMR");
        return NULL;
    }

    if (!initialize_wasm_runtime()) {
        ESP_LOGE(TAG, "Falha na inicializacao do WASM, saindo...");
        wasm_runtime_destroy_thread_env();
        return NULL;
    }


    extend_task_wdt_for_benchmark();

    ESP_LOGI(TAG, "Heap (interna) livre antes do benchmark: %u bytes", (unsigned)esp_get_free_heap_size());
    ESP_LOGI(TAG, "PSRAM total: %u bytes | PSRAM livre antes do benchmark: %u bytes",
             (unsigned)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    start_file_server();
    setvbuf(stdin, NULL, _IONBF, 0);
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
        if (!image_cache_prepare(persist, repetitions)) {
            image_cache_release();
            ESP_LOGE(TAG, "Preparacao falhou; nenhuma rodada iniciada.");
            continue;
        }
        for (unsigned round = 1; ; ++round) {
            ESP_LOGI(TAG, "Iniciando rodada %u/%u (%u imagens)", round, repetitions, (unsigned)NUM_IMAGES);
            if (!run_benchmark(round, repetitions, persist)) {
                ESP_LOGE(TAG, "Execucao interrompida por falta de memoria para relatorio/buffers.");
                break;
            }
            if (round == repetitions) break;
            ESP_LOGI(TAG, "CSV da rodada %u disponivel em %s; proxima rodada em 10 segundos.", round, REPORT_HTTP_URI);
            vTaskDelay(pdMS_TO_TICKS(10000));
        }
        image_cache_release();
    }

    return NULL;
}

/* ============================================================
 * main
 * ============================================================ */
void app_main(void) {
    pthread_t benchmark_thread;
    pthread_attr_t thread_attr;
    int pthread_res;

    wifi_init_sta();
    EventBits_t wifi_bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdTRUE,
        pdMS_TO_TICKS(WIFI_CONNECT_TIMEOUT_MS));
    if ((wifi_bits & WIFI_CONNECTED_BIT) == 0) {
        ESP_LOGE(WIFI_TAG, "Timeout aguardando conexao Wi-Fi. Verifique SSID/senha e o motivo de desconexao nos logs.");
        return;
    }
    ESP_LOGI(WIFI_TAG, "Wi-Fi conectado.");

    pthread_attr_init(&thread_attr);
    pthread_attr_setdetachstate(&thread_attr, PTHREAD_CREATE_JOINABLE);
    pthread_attr_setstacksize(&thread_attr, BENCHMARK_THREAD_STACK_BYTES);

    pthread_res = pthread_create(&benchmark_thread, &thread_attr, benchmark_thread_main, NULL);
    pthread_attr_destroy(&thread_attr);
    if (pthread_res != 0) {
        ESP_LOGE(TAG, "Falha ao criar pthread do benchmark/WASM: %d", pthread_res);
        return;
    }

    pthread_join(benchmark_thread, NULL);
}
