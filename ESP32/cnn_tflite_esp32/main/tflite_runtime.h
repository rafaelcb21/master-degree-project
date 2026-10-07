#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
bool model_initialize(void);
bool model_prepare_input(const uint8_t *raw, size_t bytes);
bool model_invoke(void);
bool model_read_output(double *values, size_t count);
size_t model_arena_used_bytes(void);
float model_output_scale(void);
int model_output_zero_point(void);
const char *model_output_type(void);
const char *model_sha256(void);
#ifdef __cplusplus
}
#endif
