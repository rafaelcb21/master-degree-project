/* Persist the command and current pass so watchdog recovery stays compatible
 * with repeated passes. Each new command gets a distinct checkpoint identity. */
typedef struct {
    uint32_t version, id, repetitions, round, persist, active, run_id;
    char model[65], images[65], config[65];
} benchmark_session_t;
static benchmark_session_t session;

static bool session_save(void) {
    nvs_handle_t handle;
    if (nvs_open("bench_command", NVS_READWRITE, &handle) != ESP_OK) return false;
    bool ok = nvs_set_blob(handle, "session", &session, sizeof(session)) == ESP_OK
        && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return ok;
}

static bool session_load(void) {
    nvs_handle_t handle;
    if (nvs_open("bench_command", NVS_READWRITE, &handle) != ESP_OK) return false;
    size_t size = sizeof(session);
    bool ok = nvs_get_blob(handle, "session", &session, &size) == ESP_OK;
    nvs_close(handle);
    return ok && size == sizeof(session) && session.version == 1
        && session.id && session.repetitions && session.round
        && session.round <= session.repetitions && session.persist <= 1 && session.active <= 1
        && session.run_id == BENCHMARK_RUN_ID
        && memcmp(session.model, TFLITE_MODEL_SHA256, sizeof(TFLITE_MODEL_SHA256)) == 0
        && memcmp(session.images, IMAGE_LIST_SHA256, sizeof(IMAGE_LIST_SHA256)) == 0
        && memcmp(session.config, BENCHMARK_CONFIG_SHA256, sizeof(BENCHMARK_CONFIG_SHA256)) == 0;
}

static bool session_start(unsigned repetitions, bool persist) {
    nvs_handle_t handle;
    if (nvs_open("bench_command", NVS_READWRITE, &handle) != ESP_OK) return false;
    uint32_t id = 0;
    esp_err_t err = nvs_get_u32(handle, "next_id", &id);
    if ((err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) || id == UINT32_MAX) {
        nvs_close(handle);
        return false;
    }
    memset(&session, 0, sizeof(session));
    session.version = 1; session.id = id + 1;
    session.repetitions = repetitions; session.round = 1;
    session.persist = persist; session.active = 1; session.run_id = BENCHMARK_RUN_ID;
    snprintf(session.model, sizeof(session.model), "%s", TFLITE_MODEL_SHA256);
    snprintf(session.images, sizeof(session.images), "%s", IMAGE_LIST_SHA256);
    snprintf(session.config, sizeof(session.config), "%s", BENCHMARK_CONFIG_SHA256);
    bool ok = nvs_set_u32(handle, "next_id", session.id) == ESP_OK
        && nvs_set_blob(handle, "session", &session, sizeof(session)) == ESP_OK
        && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return ok;
}

static bool session_cancel(void) {
    nvs_handle_t handle;
    if (nvs_open("bench_command", NVS_READWRITE, &handle) != ESP_OK) return false;
    esp_err_t err = nvs_erase_key(handle, "session");
    bool ok = (err == ESP_OK || err == ESP_ERR_NVS_NOT_FOUND) && nvs_commit(handle) == ESP_OK;
    nvs_close(handle);
    return ok;
}
