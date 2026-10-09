#ifndef HOST_CONFIG_H
#define HOST_CONFIG_H

/* Configuracao manual do host. Nao depende do pipeline Python. */
#define WIFI_SSID "Contabil2025"
#define WIFI_PASS "Reservalagos36@"
#define WIFI_CONNECT_TIMEOUT_MS 30000
#define WIFI_MIN_AUTHMODE WIFI_AUTH_WPA2_PSK
#define HTTP_DOWNLOAD_TIMEOUT_MS 15000
#define HTTP_KEEP_ALIVE_ENABLE 0
#define REPORT_HTTP_PORT 80
#define REPORT_HTTP_URI "/report"

/* O arquivo RAW deve ter exatamente INPUT_BYTES bytes, no formato que
 * o modulo espera. Para RGB888/BGR888 use 3 bytes por pixel. */
#define IMG_W 128
#define IMG_H 128
#define INPUT_BYTES_PER_PIXEL 2
#define INPUT_BYTES (IMG_W * IMG_H * INPUT_BYTES_PER_PIXEL)
#define WRITE_FORMAT_FLAG 1
#define FORMAT_FLAG_ADDR 0
#define FORMAT_RGB565 65
#define INPUT_FORMAT_VALUE FORMAT_RGB565

/* Contrato: exports sem argumentos, com retorno i32. A inferencia retorna
 * INFERENCE_SUCCESS_CODE. Os ponteiros sao offsets na memoria do modulo.
 * Os nomes abaixo mantem compatibilidade com os modulos existentes. */
#define WASM_READY_EXPORT "is_ready_for_image"
#define WASM_INPUT_PTR_EXPORT "get_slot0_base"
#define WASM_RUN_EXPORT "run_mobilenetv2"
#define WASM_OUTPUT_PTR_EXPORT "get_result_ptr"
#define USE_READY_HANDSHAKE 1
#define READY_TIMEOUT_MS 5000
#define READY_POLL_MS 5
#define INFERENCE_SUCCESS_CODE 0

/* Saida contigua de classificacao: UINT8, INT8 ou FLOAT32.
 * class_N_raw no CSV usa a ordem dos elementos do tensor de saida.
 * CLASS_LABELS associa cada indice ao rotulo usado em image_list.h.
 * Use rotulos distintos e nao negativos em CLASS_LABELS.
 * Use -1 na lista de imagens quando nao houver rotulo conhecido.
 * Argmax usa valores brutos; tensores quantizados devem ter escala positiva
 * e zero point comuns a todas as classes. Nao assume probabilidades.
 * Empates no maior valor produzem result=-1. */
#define OUTPUT_UINT8 1
#define OUTPUT_INT8 2
#define OUTPUT_FLOAT32 3
#define OUTPUT_TYPE OUTPUT_UINT8
#define NUM_CLASSES 2
#define CLASS_LABELS { 1, 0 }

#define BENCHMARK_WDT_TIMEOUT_MS 300000
#define BENCHMARK_WDT_IDLE_CORE_MASK BIT0
#define WASM_MODULE_STACK_BYTES (1024 * 1024)
#define WASM_APP_HEAP_BYTES 0
#define WASM_EXEC_STACK_BYTES (32 * 1024)
#define BENCHMARK_THREAD_STACK_BYTES (16 * 1024)
#define IDLE_DELAY_MS 1000
#define IMAGE_NAME_BYTES 128
#define WASM_ERROR_BUFFER_BYTES 128
#define REPORT_INITIAL_BYTES 4096

#if NUM_CLASSES < 1 || INPUT_BYTES < 1 || READY_POLL_MS < 1
#error "Configuracao de classes, entrada ou polling invalida"
#endif
#if REPORT_INITIAL_BYTES < 1 || IMAGE_NAME_BYTES < 2
#error "Tamanhos de buffers invalidos"
#endif
#if INFERENCE_SUCCESS_CODE == -1
#error "-1 e reservado para falhas de chamada do host"
#endif
#if OUTPUT_TYPE == OUTPUT_FLOAT32
#define OUTPUT_ELEMENT_BYTES 4
#elif OUTPUT_TYPE == OUTPUT_UINT8 || OUTPUT_TYPE == OUTPUT_INT8
#define OUTPUT_ELEMENT_BYTES 1
#else
#error "OUTPUT_TYPE deve ser OUTPUT_UINT8, OUTPUT_INT8 ou OUTPUT_FLOAT32"
#endif
#define OUTPUT_BYTES (NUM_CLASSES * OUTPUT_ELEMENT_BYTES)

#endif
