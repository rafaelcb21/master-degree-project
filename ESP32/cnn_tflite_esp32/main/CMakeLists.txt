idf_component_register(
    SRCS "main.c" "tflite_runtime.cpp" "${CMAKE_CURRENT_BINARY_DIR}/model_data.S"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_psram esp_http_server esp_http_client
             mbedtls esp-tls esp_timer esp_system esp-tflite-micro
)

set(TFLITE_MODEL_FILE "${CMAKE_CURRENT_LIST_DIR}/../model_int8_esp32.tflite" CACHE FILEPATH "TFLite model embedded in firmware")
get_filename_component(TFLITE_MODEL_FILE "${TFLITE_MODEL_FILE}" ABSOLUTE)
if(NOT EXISTS "${TFLITE_MODEL_FILE}")
    message(FATAL_ERROR "TFLite model not found: ${TFLITE_MODEL_FILE}")
endif()
file(TO_CMAKE_PATH "${TFLITE_MODEL_FILE}" TFLITE_MODEL_ASM_PATH)
file(SHA256 "${TFLITE_MODEL_FILE}" TFLITE_MODEL_SHA256)
file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/image_list.h" IMAGE_LIST_SHA256)
configure_file("${CMAKE_CURRENT_LIST_DIR}/model_data.S.in" "${CMAKE_CURRENT_BINARY_DIR}/model_data.S" @ONLY)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${TFLITE_MODEL_FILE}")
set_source_files_properties("${CMAKE_CURRENT_BINARY_DIR}/model_data.S" PROPERTIES OBJECT_DEPENDS "${TFLITE_MODEL_FILE}")

target_compile_definitions(${COMPONENT_LIB} PRIVATE TFLITE_MODEL_SHA256="${TFLITE_MODEL_SHA256}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE IMAGE_LIST_SHA256="${IMAGE_LIST_SHA256}")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/image_list.h")

# Resume only results produced with the same host sources and configuration.
set(CHECKPOINT_SOURCE_HASHES "")
foreach(source main.c host_config.h checkpoint.inc download_http.inc tflite_runtime.cpp)
    file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/${source}" SOURCE_HASH)
    string(APPEND CHECKPOINT_SOURCE_HASHES "${SOURCE_HASH}")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/${source}")
endforeach()
foreach(source "${CMAKE_SOURCE_DIR}/sdkconfig" "${CMAKE_SOURCE_DIR}/dependencies.lock")
    if(EXISTS "${source}")
        file(SHA256 "${source}" SOURCE_HASH)
        string(APPEND CHECKPOINT_SOURCE_HASHES "${SOURCE_HASH}")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${source}")
    endif()
endforeach()
string(SHA256 BENCHMARK_CONFIG_SHA256 "${CHECKPOINT_SOURCE_HASHES}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE BENCHMARK_CONFIG_SHA256="${BENCHMARK_CONFIG_SHA256}")
