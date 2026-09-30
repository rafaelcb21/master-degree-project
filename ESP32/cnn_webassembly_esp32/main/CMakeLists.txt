set(MODEL_MODULE_FILE "main.wasm")
set(MODEL_MODULE_IS_AOT 0)
set(MODEL_MODULE_KIND "WASM")

if(EXISTS "${CMAKE_CURRENT_LIST_DIR}/main.aot")
    set(MODEL_MODULE_FILE "main.aot")
    set(MODEL_MODULE_IS_AOT 1)
    set(MODEL_MODULE_KIND "AOT")
endif()

idf_component_register(
    SRCS "main.c"
    EMBED_FILES "${MODEL_MODULE_FILE}"
    INCLUDE_DIRS "."
    PRIV_INCLUDE_DIRS .
    REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_psram esp_http_server esp_http_client spiffs mbedtls esp-tls
)

target_compile_definitions(${COMPONENT_LIB} PRIVATE
    MODEL_MODULE_IS_AOT=${MODEL_MODULE_IS_AOT}
    MODEL_MODULE_KIND="${MODEL_MODULE_KIND}"
)
