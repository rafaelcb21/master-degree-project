"""Run the actual cache and command parser on Windows with mocked ESP-IDF I/O.

Uses MSVC/Windows SDK installed with Visual Studio Build Tools. Artifacts stay
in build-tflite/host-tests. SHA-256 is replaced by a deterministic test digest; real
mbedTLS integration is checked by the ESP-IDF build.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess

project = Path(__file__).resolve().parents[1]
out = project / "build-tflite" / "host-tests"
out.mkdir(parents=True, exist_ok=True)
headers = {
    "host_config.h": "#define INPUT_BYTES 16\n",
    "image_list.h": '''#include <stddef.h>
typedef struct { const char *url; int label; } image_entry_t;
static const image_entry_t IMAGES[] = {{"https://test/one", 0}, {"https://test/two", 1}};
#define NUM_IMAGES (sizeof(IMAGES) / sizeof(IMAGES[0]))
''',
    "esp_heap_caps.h": '''#include <stddef.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
void *heap_caps_malloc(size_t, int);
void heap_caps_free(void *);
''',
    "esp_log.h": "#define ESP_LOGE(...) ((void)0)\n#define ESP_LOGI(...) ((void)0)\n#define ESP_LOGW(...) ((void)0)\n",
    "esp_timer.h": "#include <stdint.h>\nint64_t esp_timer_get_time(void);\n",
    "freertos/FreeRTOS.h": "typedef unsigned TickType_t;\n#define pdMS_TO_TICKS(ms) (ms)\n",
    "freertos/task.h": "void vTaskDelay(unsigned);\n",
    "esp_spiffs.h": '''#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
typedef int esp_err_t;
#define ESP_OK 0
typedef struct { const char *base_path; const char *partition_label; int max_files; bool format_if_mount_failed; } esp_vfs_spiffs_conf_t;
int esp_vfs_spiffs_register(const esp_vfs_spiffs_conf_t *);
int esp_spiffs_info(const char *, size_t *, size_t *);
FILE *test_fopen(const char *, const char *);
int test_remove(const char *);
#define fopen test_fopen
#define remove test_remove
''',
    "mbedtls/md.h": '''#include <stddef.h>
#define MBEDTLS_MD_SHA256 1
const void *mbedtls_md_info_from_type(int);
int mbedtls_md(const void *, const unsigned char *, size_t, unsigned char *);
''',
}
for name, content in headers.items():
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
shutil.copyfile(project / "main" / "image_cache.c", out / "image_cache.c")
shutil.copyfile(project / "main" / "image_cache.h", out / "image_cache.h")
shutil.copyfile(project / "main" / "benchmark_session.inc", out / "benchmark_session.inc")
source = (project / "main" / "main.c").read_text(encoding="utf-8")
parser = re.search(r"static bool parse_command\(.*?\n}\n", source, re.S).group()
harness = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include "image_cache.c"
#undef fopen
#undef remove
static int downloads, writes, mounts, failures_remaining, retry_delays;
static bool fail_alloc;
static int64_t now_us;
void image_cache_keep_alive(void) {}
int64_t esp_timer_get_time(void) { return now_us; }
void vTaskDelay(unsigned ticks) { assert(ticks == 5000); ++retry_delays; now_us += ticks * 1000; }
static size_t flash_total = 1024 * 1024;
void *heap_caps_malloc(size_t size, int flags) { return fail_alloc ? NULL : malloc(size); }
void heap_caps_free(void *ptr) { free(ptr); }
int esp_vfs_spiffs_register(const esp_vfs_spiffs_conf_t *conf) { ++mounts; return 0; }
int esp_spiffs_info(const char *label, size_t *total, size_t *used) { *total = flash_total; *used = 0; return 0; }
FILE *test_fopen(const char *path, const char *mode) {
    if (mode[0] == 'w') ++writes;
    return fopen(path + 8, mode);
}
int test_remove(const char *path) { return remove(path + 8); }
const void *mbedtls_md_info_from_type(int kind) { return (void *)1; }
int mbedtls_md(const void *info, const unsigned char *data, size_t len, unsigned char *result) {
    uint64_t hash = UINT64_C(14695981039346656037);
    for (size_t i = 0; i < len; ++i) hash = (hash ^ data[i]) * UINT64_C(1099511628211);
    for (size_t i = 0; i < 32; ++i) result[i] = (uint8_t)(hash >> (8 * (i % 8)));
    return 0;
}
bool download_image(const char *url, uint8_t *buffer, size_t len, int64_t *elapsed) {
    ++downloads;
    now_us += 100;
    memset(buffer, strstr(url, "one") ? 11 : 22, len);
    *elapsed = 100;
    if (failures_remaining) {
        --failures_remaining;
        memset(buffer, 99, len); /* incomplete/invalid attempt must be overwritten */
        return false;
    }
    return true;
}
PARSER
#define NVS_READWRITE 1
#define ESP_ERR_NVS_NOT_FOUND 2
#define BENCHMARK_RUN_ID 2
#define TFLITE_MODEL_SHA256 "model"
#define IMAGE_LIST_SHA256 "images"
#define BENCHMARK_CONFIG_SHA256 "config"
typedef unsigned nvs_handle_t;
static uint32_t saved_id, staged_id;
static uint8_t saved_session[512], staged_session[512];
static size_t saved_size, staged_size;
static bool fail_commit;
static int nvs_open(const char *name, int mode, nvs_handle_t *handle) {
    *handle = 1; staged_id = saved_id; staged_size = saved_size;
    memcpy(staged_session, saved_session, saved_size); return 0;
}
static void nvs_close(nvs_handle_t handle) {}
static int nvs_get_u32(nvs_handle_t handle, const char *key, uint32_t *id) { *id = saved_id; return 0; }
static int nvs_set_u32(nvs_handle_t handle, const char *key, uint32_t id) { staged_id = id; return 0; }
static int nvs_get_blob(nvs_handle_t handle, const char *key, void *data, size_t *size) {
    if (!saved_size) return ESP_ERR_NVS_NOT_FOUND;
    assert(*size >= saved_size); *size = saved_size; memcpy(data, saved_session, saved_size); return 0;
}
static int nvs_set_blob(nvs_handle_t handle, const char *key, const void *data, size_t size) {
    assert(size <= sizeof(staged_session)); staged_size = size; memcpy(staged_session, data, size); return 0;
}
static int nvs_erase_key(nvs_handle_t handle, const char *key) { staged_size = 0; return 0; }
static int nvs_commit(nvs_handle_t handle) {
    if (fail_commit) return -1;
    saved_id = staged_id; saved_size = staged_size;
    memcpy(saved_session, staged_session, saved_size); return 0;
}
#include "benchmark_session.inc"
int main(void) {
    unsigned repetitions;
    bool persist;
    assert(parse_command("benchmark 10 sim", &repetitions, &persist) && repetitions == 10 && persist);
    assert(parse_command("benchmark 1 nao", &repetitions, &persist) && repetitions == 1 && !persist);
    const char *bad[] = {"", "benchmark", "benchmark 0 sim", "benchmark -1 nao", "benchmark +1 sim",
        "benchmark 1.5 sim", "benchmark 4294967296 sim", "benchmark 999999999999999999999999 sim",
        "benchmark 10 maybe", "benchmark 10 sim extra", "other 1 sim"};
    for (size_t i = 0; i < sizeof(bad)/sizeof(bad[0]); ++i) assert(!parse_command(bad[i], &repetitions, &persist));

    assert(!session_load());
    assert(session_start(10, true) && session.id == 1 && session.round == 1 && session.active);
    session.round = 2; assert(session_save());
    memset(&session, 0, sizeof(session));
    assert(session_load() && session.round == 2 && session.repetitions == 10 && session.persist);
    session.active = 0; assert(session_save());
    assert(session_load() && !session.active);
    assert(session_start(3, false) && session.id == 2 && session.round == 1);
    assert(session_cancel()); memset(&session, 0, sizeof(session)); assert(!session_load());
    assert(session_start(2, true) && session.id == 3); /* canceled commands never reuse IDs */
    fail_commit = true; assert(!session_start(9, false)); fail_commit = false;
    assert(session_load() && session.id == 3 && session.repetitions == 2);
    assert(session_start(9, false) && session.id == 4);
    session.round = 0; assert(session_save() && !session_load());

    uint8_t buffer[INPUT_BYTES]; int64_t elapsed;
    assert(image_cache_prepare(false, 10));
    assert(downloads == 2 && writes == 0 && mounts == 0);
    for (int round = 0; round < 10; ++round) {
        assert(image_cache_load(0, buffer, &elapsed) && buffer[0] == 11 && elapsed == 0);
        assert(image_cache_load(1, buffer, &elapsed) && buffer[0] == 22 && elapsed == 0);
    }
    assert(downloads == 2);
    image_cache_release();
    fail_alloc = true;
    assert(!image_cache_prepare(false, 2));
    assert(image_cache_prepare(false, 1));
    assert(image_cache_load(0, buffer, &elapsed) && elapsed == 100);
    fail_alloc = false;
    image_cache_release();

    char path[96];
    for (size_t i = 0; i < NUM_IMAGES; ++i) { assert(cache_path(i, path)); remove(path + 8); }
    int before = downloads;
    assert(image_cache_prepare(true, 10));
    assert(downloads == before + 2 && writes == 2 && mounts == 1);
    for (int i = 0; i < 10; ++i) assert(image_cache_load(0, buffer, &elapsed) && buffer[0] == 11 && elapsed == 0);
    image_cache_release();
    before = downloads;
    assert(image_cache_prepare(true, 10));
    assert(downloads == before && writes == 2); /* persistent cache reused */
    assert(cache_path(0, path));
    FILE *file = fopen(path + 8, "r+b"); assert(file);
    fseek(file, 64, SEEK_SET); fputc(99, file); fclose(file);
    assert(!image_cache_load(0, buffer, &elapsed)); /* no silent download mid-round */
    assert(image_cache_prepare(true, 2));
    assert(downloads == before + 1 && writes == 3); /* only corrupt file redownloaded */
    assert(image_cache_prepare(false, 2));
    assert(writes == 3 && mounts == 1); /* nao preserves an existing flash cache */
    image_cache_release();
    before = downloads;
    assert(image_cache_prepare(true, 2) && downloads == before);
    assert(cache_path(1, path)); remove(path + 8);
    failures_remaining = 3;
    before = downloads;
    assert(image_cache_prepare(true, 2));
    assert(downloads == before + 4 && writes == 4 && retry_delays == 3);
    assert(image_cache_load(1, buffer, &elapsed) && buffer[0] == 22 && elapsed == 0);
    flash_total = 100;
    before = downloads;
    assert(!image_cache_prepare(true, 2) && downloads == before);
    flash_total = 1024 * 1024;
    failures_remaining = 2;
    before = downloads;
    assert(image_cache_prepare(false, 2));
    assert(downloads == before + 4 && retry_delays == 5);
    assert(image_cache_load(0, buffer, &elapsed) && buffer[0] == 11 && elapsed == 0);
    image_cache_release();
    fail_alloc = true;
    assert(image_cache_prepare(false, 1));
    failures_remaining = 2;
    before = downloads;
    assert(image_cache_load(0, buffer, &elapsed) && buffer[0] == 11);
    assert(downloads == before + 3 && retry_delays == 7 && elapsed == 10000300);
    image_cache_release();
    puts("PASS: parser, session recovery/IDs, RAM/flash reuse, corruption, capacity, unlimited retries");
    return 0;
}
'''.replace("PARSER", parser)
(out / "check.c").write_text(harness, encoding="utf-8")
vc = Path("C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC")
vc = sorted(vc.iterdir())[-1]
sdk = Path("C:/Program Files (x86)/Windows Kits/10")
version = sorted((sdk / "Lib").iterdir())[-1].name
env = dict(os.environ)
env["INCLUDE"] = ";".join(map(str, [vc / "include"] + [sdk / "Include" / version / p for p in ["ucrt", "shared", "um"]]))
env["LIB"] = ";".join(map(str, [vc / "lib/x64", sdk / "Lib" / version / "ucrt/x64", sdk / "Lib" / version / "um/x64"]))
compiler = vc / "bin/Hostx64/x64/cl.exe"
subprocess.run([str(compiler), "/nologo", "/std:c11", "/I.", "check.c", "/Fe:check.exe"], cwd=out, env=env, check=True)
subprocess.run([str(out / "check.exe")], cwd=out, check=True)
