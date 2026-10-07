# Configurações e medições do host TFLite

[English](HOST.md) | [Português (Brasil)](HOST.pt-BR.md)

[Compilar e executar](README.pt-BR.md)

## Arquivos editáveis

| Arquivo | Finalidade |
|---|---|
| `main/host_config.h` | Wi-Fi, HTTP, formato RAW, rótulos, arena PSRAM e tarefa |
| `main/image_list.h` | URLs RAW Cloudinary e rótulos, na ordem de execução |
| `main/CMakeLists.txt` / `TFLITE_MODEL_FILE` | Modelo original incorporado |
| `sdkconfig` / `sdkconfig.defaults` | Placa, PSRAM, flash, CPU e TLS |

A ordem padrão é `{1, 0}`: saída 0 representa rótulo 1, saída 1 representa rótulo 0. Ela precisa corresponder ao modelo e à lista de imagens. `CLASS_LABELS_ARE_INDICES=1` usa diretamente os índices de saída. Empate no máximo gera `result=-1`; rótulo esperado desconhecido gera `right=-1`. Empates continuam sendo inferências bem-sucedidas (`ok=1`) e contam como incorretos quando há rótulo. Essa é a regra do host WASM ESP32; o adaptador binário Python também rejeita soma de scores não positiva.

## Campos CSV

| Campos | Significado |
|---|---|
| `name_image` | Nome final da URL, correspondente à lista copiada do WASM |
| `ok` | 1 somente após download, preparação, Invoke e leitura de saída bem-sucedidos |
| `class_N_raw` | Elemento bruto do tensor, na ordem do modelo; vazio em falhas |
| `result`, `label`, `right` | Rótulo previsto, rótulo esperado, acerto (1/0 ou -1 quando indisponível) |
| `download_ms` | Duração da requisição HTTP |
| `preprocess_ms` | Decodificação RAW, ordem dos canais, normalização e escrita do tensor |
| `invoke_ms` | Duração de Invoke do TFLite Micro |
| `inference_ms` | `preprocess_ms + invoke_ms`; exclui rede, hashing e leitura da saída |
| `heap_before`, `heap_after`, `heap_used` | Heap livre total antes/depois da preparação + Invoke; redução positiva, limitada a zero |
| `psram_before`, `psram_after`, `psram_used` | As mesmas medições restritas à PSRAM |
| `stack_min_free_bytes` | Menor espaço livre histórico da pilha da tarefa, não alocação por imagem |
| `arena_reserved_bytes`, `arena_used_bytes` | Reserva configurada e uso da arena informado pelo TFLite Micro |
| `input_sha256` | Hash dos bytes RAW baixados, antes do pré-processamento |

Interpretador e arena são criados antes das medições por imagem; `heap_used=0` **não** significa ausência de uso de memória pelo modelo. Não some heap e PSRAM: o heap total pode já incluir a PSRAM. O armazenamento do CSV cresce depois de cada amostra e influencia o heap livre das próximas medições.

O relatório servido é imutável. Se faltar memória para o CSV, `/report` retorna erro, sem apresentar um resultado parcial como completo. Imagens com falha têm `ok=0`; resumos aparecem no serial e em `/metadata`, sem linhas falsas de dados no CSV. Os endpoints começam após o benchmark e permanecem disponíveis enquanto a placa estiver ligada.

## Metadados e reprodutibilidade

`/metadata` contém SHA-256 do modelo/lista de imagens, runtime/versão do componente, versão IDF, tipo/escala/zero point da saída, frequência da CPU, arena e contagens. Para desquantizar, use `(raw - output_zero_point) * output_scale`; a saída float já representa valores reais. Guarde `dependencies.lock`, `host_config.h` e `sdkconfig` com o experimento. O componente da Espressif habilita kernels ESP-NN; suas implementações diferem do TFLite desktop e dos kernels WASM próprios.

Compare predições usando hashes de modelo e bytes de imagem idênticos. O CSV WASM antigo não possui hashes de entrada; confira as fontes Cloudinary separadamente. Separe download de inferência, mantenha as mesmas configurações de CPU/PSRAM e registre que não há aquecimento. A arena padrão de 1 MiB é uma reserva inicial; somente a execução na placa confirma se o modelo cabe e funciona corretamente.
