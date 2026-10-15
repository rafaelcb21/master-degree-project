# Métricas de memória dos benchmarks ESP32

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

Os próximos firmwares de `cnn_webassembly_esp32` e `cnn_tflite_esp32` incluem o mesmo [coletor de memória](benchmark_memory.h). É necessário compilar e gravar o firmware atualizado e executar uma nova rodada. A interface web apresenta as novas métricas quando importa um CSV com `memory_report_schema=1`.

## Campos por imagem

`internal_heap_before` e `internal_heap_after` medem o heap interno com `MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT`, antes/depois da inferência, fora do intervalo cronometrado. Não incluem PSRAM nem representam toda a SRAM física (por exemplo, código estático em IRAM).

Os campos anteriores `heap_before`, `heap_after` e `heap_used` continuam disponíveis para compatibilidade: consultam o heap padrão (`MALLOC_CAP_DEFAULT`) e podem incluir PSRAM. Não devem ser chamados de SRAM interna. `heap_used` e `psram_used` são diferenças não negativas antes/depois da chamada, não a ocupação total do modelo.

## Rodapé do CSV

| Grupo | Campos e definição |
|---|---|
| Heap interno | `internal_heap_total_bytes`, `internal_heap_free_bytes`, `internal_heap_used_bytes`, `internal_heap_min_free_bytes`, `internal_heap_largest_free_block_bytes` |
| PSRAM | `psram_total_bytes`, `psram_free_bytes`, `psram_occupied_bytes`, `psram_min_free_bytes`, `psram_largest_free_block_bytes` |
| SRAM estática | `sram_static_dram_data_bytes`, `sram_static_dram_bss_bytes`, `sram_static_dram_noinit_bytes`, soma `sram_static_dram_bytes`, intervalo `sram_static_iram_bytes` |
| Flash da aplicação | `flash_app_image_bytes`, `flash_app_partition_bytes`, `flash_app_partition_free_bytes`, `flash_app_partition_used_pct` |
| Flash / SPIFFS | `flash_size_bytes`; `flash_spiffs_total_bytes` e `flash_spiffs_used_bytes` se montado |
| Contexto | `cpu_frequency_mhz` medido ao final; escopos, capacidades e nomes das funções utilizadas |

As funções `heap_caps_get_total_size`, `heap_caps_get_free_size`, `heap_caps_get_minimum_free_size` e `heap_caps_get_largest_free_block` são registradas no próprio CSV. Os mínimos históricos somam os menores valores por região **desde o boot**, incluindo inicialização e rodadas anteriores; não são reiniciados por este coletor. A ocupação dinâmica é `total - livre` em uma amostra ao final da rodada, antes de escrever o rodapé de memória e liberar buffers. Inclui runtime, cache e o relatório em construção.

A SRAM estática é obtida dos símbolos do linker: `.data`, `.bss`, `.noinit` em DRAM e o intervalo `_iram_start` → `_iram_end`, incluindo alinhamento. Não é a soma do heap dinâmico com os 520 KiB nominais do chip. O mapa de memória do build continua disponível para detalhamento por componente com `idf.py size`.

A ocupação da aplicação na flash é o tamanho da imagem realmente em execução, obtido por `esp_image_get_metadata` sobre `esp_ota_get_running_partition`. Não inclui bootloader, tabela de partições ou SPIFFS. O tamanho da flash informado por `esp_flash_get_size` não é um contador de ocupação. A utilização do SPIFFS é obtida por `esp_spiffs_info` somente quando montado; quando indisponível, o CSV registra `flash_spiffs_usage_available=0` e não apresenta zero como uso medido.

No TFLite, checkpoints restaurados preservam os valores por imagem medidos originalmente; o rodapé descreve o boot/rodada que publicou o relatório. A inclusão do coletor e a mudança no formato das linhas alteram a identidade dos checkpoints. Resultados da versão anterior não são reinterpretados como novas medições.

O coletor fornece números reais após executar na placa. Compilar o firmware e os testes da web não produzem dados de uma nova coleta. Relatórios antigos continuam disponíveis, sem preenchimento artificial das métricas ausentes.
