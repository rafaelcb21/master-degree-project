#include "tflite_runtime.h"
#include "host_config.h"
#include <cmath>
#include <cstring>
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

extern "C" const uint8_t tflite_model_start[];
extern "C" const uint8_t tflite_model_end[];
static const char *TAG = "tflite_runtime";
static tflite::MicroInterpreter *interpreter;
static TfLiteTensor *input;
static TfLiteTensor *output;

static bool supported_tensor(const TfLiteTensor *tensor) {
    if (!tensor || !tensor->data.raw) return false;
    if (tensor->type == kTfLiteFloat32) return true;
    if (tensor->type != kTfLiteUInt8 && tensor->type != kTfLiteInt8) return false;
    if (!std::isfinite(tensor->params.scale) || tensor->params.scale <= 0) return false;
    if (tensor->quantization.type != kTfLiteAffineQuantization) return false;
    const auto *q = static_cast<const TfLiteAffineQuantization *>(tensor->quantization.params);
    return q && q->scale && q->zero_point && q->scale->size == 1 && q->zero_point->size == 1;
}

bool model_initialize(void) {
    const size_t size = tflite_model_end - tflite_model_start;
    flatbuffers::Verifier verifier(tflite_model_start, size);
    if (!tflite::VerifyModelBuffer(verifier)) {
        ESP_LOGE(TAG, "Invalid TFLite FlatBuffer");
        return false;
    }
    const auto *model = tflite::GetModel(tflite_model_start);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        ESP_LOGE(TAG, "Unsupported schema: %lu", (unsigned long)model->version());
        return false;
    }
    static tflite::MicroMutableOpResolver<12> resolver;
    const TfLiteStatus registrations[] = {
        resolver.AddQuantize(), resolver.AddDequantize(), resolver.AddConv2D(),
        resolver.AddDepthwiseConv2D(), resolver.AddAdd(), resolver.AddMean(),
        resolver.AddAveragePool2D(), resolver.AddMaxPool2D(), resolver.AddReshape(),
        resolver.AddFullyConnected(), resolver.AddSoftmax(), resolver.AddPad()
    };
    for (auto status : registrations) if (status != kTfLiteOk) return false;
    auto *arena = static_cast<uint8_t *>(heap_caps_aligned_alloc(16, TENSOR_ARENA_BYTES, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
    if (!arena) {
        ESP_LOGE(TAG, "Cannot allocate %u bytes in PSRAM; largest block=%u", (unsigned)TENSOR_ARENA_BYTES,
                 (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
        return false;
    }
    static tflite::MicroInterpreter instance(model, resolver, arena, TENSOR_ARENA_BYTES);
    interpreter = &instance;
    if (interpreter->AllocateTensors() != kTfLiteOk) {
        ESP_LOGE(TAG, "AllocateTensors failed: check operators/types and TENSOR_ARENA_BYTES");
        return false;
    }
    if (interpreter->inputs_size() != 1 || interpreter->outputs_size() != 1) return false;
    input = interpreter->input(0);
    output = interpreter->output(0);
    if (!supported_tensor(input) || !supported_tensor(output)) {
        ESP_LOGE(TAG, "Only uint8/int8 per-tensor quantization or float32 IO is supported");
        return false;
    }
    if (input->dims->size != 4 || input->dims->data[0] != 1 || input->dims->data[1] != IMG_H ||
        input->dims->data[2] != IMG_W || input->dims->data[3] != 3) {
        ESP_LOGE(TAG, "Model input must be [1,%d,%d,3]; adjust host_config.h", IMG_H, IMG_W);
        return false;
    }
    size_t count = 1;
    for (int i = 0; i < output->dims->size; ++i) {
        if (output->dims->data[i] <= 0 || count > NUM_CLASSES / (size_t)output->dims->data[i]) {
            ESP_LOGE(TAG, "Output exceeds NUM_CLASSES=%d", NUM_CLASSES);
            return false;
        }
        count *= output->dims->data[i];
    }
    if (count != NUM_CLASSES) {
        ESP_LOGE(TAG, "Output class count does not match NUM_CLASSES=%d", NUM_CLASSES);
        return false;
    }
    ESP_LOGI(TAG, "TFLite SHA256=%s; model=%u bytes; arena=%u/%u bytes", TFLITE_MODEL_SHA256,
             (unsigned)size, (unsigned)interpreter->arena_used_bytes(), (unsigned)TENSOR_ARENA_BYTES);
    ESP_LOGI(TAG, "Input type=%d scale=%.9g zero_point=%d; output=%s scale=%.9g zero_point=%d",
             input->type, input->params.scale, (int)input->params.zero_point,
             model_output_type(), output->params.scale, (int)output->params.zero_point);
    return true;
}

bool model_prepare_input(const uint8_t *raw, size_t bytes) {
    if (!input || !raw || bytes != INPUT_BYTES) return false;
    for (size_t p = 0; p < IMG_W * IMG_H; ++p) {
        uint8_t rgb[3];
#if INPUT_FORMAT == INPUT_RGB565_LE
        const uint16_t value = raw[2 * p] | (uint16_t(raw[2 * p + 1]) << 8);
        const unsigned r = (value >> 11) & 31, g = (value >> 5) & 63, b = value & 31;
        rgb[0] = (r << 3) | (r >> 2);
        rgb[1] = (g << 2) | (g >> 4);
        rgb[2] = (b << 3) | (b >> 2);
#elif INPUT_FORMAT == INPUT_BGR888
        rgb[0] = raw[3 * p + 2]; rgb[1] = raw[3 * p + 1]; rgb[2] = raw[3 * p];
#else
        memcpy(rgb, raw + 3 * p, 3);
#endif
        for (size_t c = 0; c < 3; ++c) {
            const size_t i = 3 * p + c;
            if (input->type == kTfLiteUInt8) input->data.uint8[i] = rgb[c];
            else {
                const float real = rgb[c] * INPUT_REAL_MULTIPLIER + INPUT_REAL_OFFSET;
                if (input->type == kTfLiteFloat32) input->data.f[i] = real;
                else {
                    float q = std::nearbyint(real / input->params.scale + input->params.zero_point);
                    q = q < -128 ? -128 : (q > 127 ? 127 : q);
                    input->data.int8[i] = static_cast<int8_t>(q);
                }
            }
        }
    }
    return true;
}

bool model_invoke(void) { return interpreter && interpreter->Invoke() == kTfLiteOk; }
bool model_read_output(double *values, size_t count) {
    if (!output || !values || count != NUM_CLASSES) return false;
    for (size_t i = 0; i < count; ++i) {
        values[i] = output->type == kTfLiteFloat32 ? output->data.f[i] :
                    output->type == kTfLiteInt8 ? output->data.int8[i] : output->data.uint8[i];
        if (!std::isfinite(values[i])) return false;
    }
    return true;
}
size_t model_arena_used_bytes(void) { return interpreter ? interpreter->arena_used_bytes() : 0; }
float model_output_scale(void) { return output->type == kTfLiteFloat32 ? 1.0f : output->params.scale; }
int model_output_zero_point(void) { return output->type == kTfLiteFloat32 ? 0 : output->params.zero_point; }
const char *model_output_type(void) { return output->type == kTfLiteFloat32 ? "float32" : output->type == kTfLiteInt8 ? "int8" : "uint8"; }
const char *model_sha256(void) { return TFLITE_MODEL_SHA256; }
