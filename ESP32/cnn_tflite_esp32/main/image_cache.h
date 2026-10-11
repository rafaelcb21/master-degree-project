#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

bool image_cache_prepare(bool persist, unsigned repetitions);
bool image_cache_load(size_t index, uint8_t *buffer, int64_t *download_us);
void image_cache_release(void);
