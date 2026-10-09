/* Included by main.c; isolated so the same code can be tested with fake HTTP. */
#if HTTP_DOWNLOAD_MAX_ATTEMPTS < 1 || HTTP_READ_CHUNK_BYTES < 1 || HTTP_READ_TIMEOUT_MS < 1 || HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS < 1
#error "HTTP download limits must be positive"
#endif

static bool download_set_timeout(esp_http_client_handle_t client, int64_t deadline, int limit_ms) {
    int64_t remaining_ms = (deadline - esp_timer_get_time()) / 1000;
    if (remaining_ms <= 0) return false;
    int timeout = remaining_ms < limit_ms ? (int)remaining_ms : limit_ms;
    return esp_http_client_set_timeout_ms(client, timeout) == ESP_OK;
}

static bool download_attempt(const char *url, uint8_t *out_buf, size_t expected_len) {
    const int64_t deadline = esp_timer_get_time() + (int64_t)HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS * 1000;
    esp_http_client_config_t config = {
        .url = url,
        .timeout_ms = HTTP_DOWNLOAD_TIMEOUT_MS,
        .is_async = false,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .keep_alive_enable = HTTP_KEEP_ALIVE_ENABLE,
        .disable_auto_redirect = true,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) return false;
    bool ok = false;
    size_t received = 0;
    esp_err_t err = esp_http_client_set_header(client, "Connection", "close");
    if (err != ESP_OK || !download_set_timeout(client, deadline, HTTP_DOWNLOAD_TIMEOUT_MS)) goto cleanup;
    ESP_LOGI(TAG_HTTP, "HTTP stream: conectando");
    err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGW(TAG_HTTP, "HTTP open falhou: %s", esp_err_to_name(err));
        goto cleanup;
    }
    if (!download_set_timeout(client, deadline, HTTP_DOWNLOAD_TIMEOUT_MS)) goto cleanup;
    ESP_LOGI(TAG_HTTP, "HTTP stream: aguardando cabecalho");
    int64_t content_length = esp_http_client_fetch_headers(client);
    int status = esp_http_client_get_status_code(client);
    if (content_length < 0 || status != 200) {
        ESP_LOGW(TAG_HTTP, "Cabecalho HTTP falhou: status=%d length=%lld", status, (long long)content_length);
        goto cleanup;
    }
    if (!esp_http_client_is_chunked_response(client) && content_length != (int64_t)expected_len) {
        ESP_LOGW(TAG_HTTP, "Content-Length inesperado: %lld; esperado=%u", (long long)content_length, (unsigned)expected_len);
        goto cleanup;
    }
    ESP_LOGI(TAG_HTTP, "HTTP stream: lendo corpo (%u bytes esperados)", (unsigned)expected_len);
    int64_t next_progress = esp_timer_get_time() + (int64_t)HTTP_PROGRESS_INTERVAL_MS * 1000;
    while (true) {
        if (!download_set_timeout(client, deadline, HTTP_READ_TIMEOUT_MS)) {
            ESP_LOGW(TAG_HTTP, "Limite total do download atingido");
            break;
        }
        if (esp_http_client_is_complete_data_received(client)) {
            ok = received == expected_len;
            break;
        }
        /* Read one extra byte only into a separate buffer to detect overflow
         * and consume the end of chunked responses without overrunning RAW. */
        uint8_t extra;
        size_t remaining = expected_len - received;
        int wanted = remaining > HTTP_READ_CHUNK_BYTES ? HTTP_READ_CHUNK_BYTES : (int)remaining;
        int count = esp_http_client_read(client, (char *)(remaining ? out_buf + received : &extra), remaining ? wanted : 1);
        if (count < 0) {
            ESP_LOGW(TAG_HTTP, "Leitura HTTP falhou: code=%d errno=%d bytes=%u/%u", count,
                     esp_http_client_get_errno(client), (unsigned)received, (unsigned)expected_len);
            break;
        }
        if (count == 0) {
            ok = received == expected_len && esp_http_client_is_complete_data_received(client);
            break;
        }
        if ((size_t)count > remaining) {
            ESP_LOGW(TAG_HTTP, "Corpo HTTP maior que a imagem esperada");
            break;
        }
        received += count;
        int64_t now = esp_timer_get_time();
        if (now >= next_progress) {
            ESP_LOGI(TAG_HTTP, "Download: %u/%u bytes", (unsigned)received, (unsigned)expected_len);
            next_progress = now + (int64_t)HTTP_PROGRESS_INTERVAL_MS * 1000;
        }
    }
cleanup:
    ESP_LOGI(TAG_HTTP, "HTTP stream: fechando conexao; bytes=%u/%u ok=%d", (unsigned)received, (unsigned)expected_len, ok);
    esp_http_client_cleanup(client);
    ESP_LOGI(TAG_HTTP, "HTTP stream: conexao liberada");
    return ok;
}

static bool download_image(const char *url, uint8_t *out_buf, size_t expected_len, int64_t *download_us) {
    int64_t started = esp_timer_get_time();
    bool ok = false;
    for (int attempt = 1; attempt <= HTTP_DOWNLOAD_MAX_ATTEMPTS; ++attempt) {
        ESP_LOGI(TAG_HTTP, "Download tentativa %d/%d", attempt, HTTP_DOWNLOAD_MAX_ATTEMPTS);
        if (download_attempt(url, out_buf, expected_len)) { ok = true; break; }
        ESP_LOGW(TAG_HTTP, "Download falhou na tentativa %d: %s", attempt, url);
        if (attempt < HTTP_DOWNLOAD_MAX_ATTEMPTS) vTaskDelay(pdMS_TO_TICKS(HTTP_RETRY_DELAY_MS) + 1);
    }
    if (download_us) *download_us = esp_timer_get_time() - started;
    if (!ok) ESP_LOGE(TAG_HTTP, "Imagem marcada como erro; seguindo para a proxima");
    return ok;
}
