/* Append-only flash journal: a result is visible only after its commit word.
 * Interrupted writes consume a slot; they never overwrite a previous result.
 * NVS atomically records attempts before executing an image. */
#define CP_MAGIC 0x43504b31u
#define CP_BASE 4096u
typedef struct {
    uint32_t committed, version, images, row_bytes, run_id;
    char model[65], images_hash[65], config[65];
} cp_header_t;
typedef struct {
    uint32_t index, crc, committed;
    report_row_t row;
} cp_record_t;
static const esp_partition_t *cp_partition;
static nvs_handle_t cp_nvs;
static size_t cp_offset, cp_next;
static const size_t cp_stride = (sizeof(cp_record_t) + 15u) & ~15u;
static cp_record_t *cp_record;

static uint32_t cp_crc(const report_row_t *row) {
    uint32_t crc = UINT32_MAX;
    const uint8_t *p = (const uint8_t *)row;
    for (size_t i = 0; i < sizeof(*row); ++i) {
        crc ^= p[i];
        for (int bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static bool checkpoint_open(void) {
    cp_next = 0; cp_offset = CP_BASE;
    cp_partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, CHECKPOINT_PARTITION_LABEL);
    if (!cp_partition || CP_BASE + (uint64_t)NUM_IMAGES * cp_stride > cp_partition->size) {
        ESP_LOGE(TAG, "Particao insuficiente para checkpoints; nenhum dado foi apagado");
        return false;
    }
    cp_record = heap_caps_malloc(sizeof(*cp_record), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!cp_record || nvs_open("bench_resume", NVS_READWRITE, &cp_nvs) != ESP_OK) return false;
    cp_header_t expected, saved;
    memset(&expected, 0, sizeof(expected));
    expected.committed = CP_MAGIC; expected.version = 1;
    expected.images = NUM_IMAGES; expected.row_bytes = sizeof(report_row_t); expected.run_id = BENCHMARK_RUN_ID;
    snprintf(expected.model, sizeof(expected.model), "%s", TFLITE_MODEL_SHA256);
    snprintf(expected.images_hash, sizeof(expected.images_hash), "%s", IMAGE_LIST_SHA256);
    snprintf(expected.config, sizeof(expected.config), "%s", BENCHMARK_CONFIG_SHA256);
    if (esp_partition_read(cp_partition, 0, &saved, sizeof(saved)) != ESP_OK) return false;
    if (memcmp(&expected, &saved, sizeof(saved)) != 0) {
        ESP_LOGW(TAG, "Novo experimento: inicializando checkpoints na particao %s", CHECKPOINT_PARTITION_LABEL);
        if (esp_partition_erase_range(cp_partition, 0, cp_partition->size) != ESP_OK) return false;
        if (nvs_set_u64(cp_nvs, "attempt", 0) != ESP_OK || nvs_commit(cp_nvs) != ESP_OK) return false;
        expected.committed = UINT32_MAX;
        if (esp_partition_write(cp_partition, 0, &expected, sizeof(expected)) != ESP_OK) return false;
        uint32_t commit = CP_MAGIC;
        if (esp_partition_write(cp_partition, 0, &commit, sizeof(commit)) != ESP_OK) return false;
    }
    return true;
}

/* Returns 1 for a committed row, 0 at the end, -1 on a storage error. */
static int checkpoint_read(report_row_t *row) {
    while (cp_offset + cp_stride <= cp_partition->size) {
        if (esp_partition_read(cp_partition, cp_offset, cp_record, sizeof(*cp_record)) != ESP_OK) return -1;
        bool erased = true;
        for (size_t i = 0; i < sizeof(*cp_record); ++i) {
            if (((const uint8_t *)cp_record)[i] != 0xff) { erased = false; break; }
        }
        if (erased) return 0;
        cp_offset += cp_stride;
        if (cp_record->committed != CP_MAGIC || cp_crc(&cp_record->row) != cp_record->crc) {
            ESP_LOGW(TAG, "Checkpoint interrompido ignorado; retomando do ultimo resultado confirmado");
            continue;
        }
        if (cp_record->index != cp_next || cp_next >= NUM_IMAGES) return -1;
        memcpy(row, &cp_record->row, sizeof(*row));
        ++cp_next;
        return 1;
    }
    return cp_next == NUM_IMAGES ? 0 : -1;
}

static bool checkpoint_attempt(size_t index, unsigned *attempts, bool *skip) {
    uint64_t value = 0;
    esp_err_t err = nvs_get_u64(cp_nvs, "attempt", &value);
    if (err != ESP_OK && err != ESP_ERR_NVS_NOT_FOUND) return false;
    *attempts = (value >> 32) == index ? (uint32_t)value : 0;
    *skip = *attempts >= RECOVERY_MAX_ATTEMPTS;
    if (*skip) return true;
    ++*attempts;
    value = ((uint64_t)index << 32) | *attempts;
    return nvs_set_u64(cp_nvs, "attempt", value) == ESP_OK && nvs_commit(cp_nvs) == ESP_OK;
}

static bool checkpoint_append(size_t index, const report_row_t *row) {
    if (index != cp_next || cp_offset + cp_stride > cp_partition->size) return false;
    memset(cp_record, 0, sizeof(*cp_record));
    cp_record->index = index; cp_record->crc = cp_crc(row); cp_record->committed = UINT32_MAX;
    memcpy(&cp_record->row, row, sizeof(*row));
    if (esp_partition_write(cp_partition, cp_offset, cp_record, sizeof(*cp_record)) != ESP_OK) return false;
    uint32_t commit = CP_MAGIC;
    if (esp_partition_write(cp_partition, cp_offset + offsetof(cp_record_t, committed), &commit, sizeof(commit)) != ESP_OK) return false;
    cp_offset += cp_stride; ++cp_next;
    return true;
}
