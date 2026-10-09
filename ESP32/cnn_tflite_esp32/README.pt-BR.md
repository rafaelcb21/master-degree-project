# Benchmark TFLite Micro no ESP32

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

Este projeto ESP-IDF independente executa o próprio `.tflite` no ESP32 com **TensorFlow Lite Micro**, baixa entradas RAW do Cloudinary e disponibiliza resultados CSV para comparar com o [host WASM/AOT](../cnn_webassembly_esp32/README.pt-BR.md). O modelo padrão é o Drowsiness, com entrada RGB 128×128 e duas classes de saída.

## O que mudou em relação à cópia

- `main/main.c`: Wi-Fi, downloads, benchmark sequencial, medições e endpoints HTTP.
- `main/tflite_runtime.cpp`: TensorFlow Lite Micro, validação do modelo, conversão da entrada e `Invoke()`.
- `main/host_config.h`: configurações editáveis, dimensões, formato, rótulos e tamanho da arena.
- `main/image_list.h`: lista preservada de URLs Cloudinary e rótulos esperados.
- `model_int8_esp32.tflite`: modelo original incorporado na flash com alinhamento; não há conversão para WAT, WASM ou AOT.
- `main/idf_component.yml`: TFLite Micro 1.3.5 da Espressif; a versão resolvida de ESP-NN está em `dependencies.lock`.
- `legacy_wasm/`: artefatos WASM e guias antigos copiados. Seu CSV **não** é uma medição TFLite.

O projeto original `cnn_webassembly_esp32` permanece intacto. As pastas `build/` copiadas não são usadas; este guia usa a pasta nova `build-tflite/`.

## 1. Configurar

Abra um **terminal ESP-IDF 5.3**. A configuração conferida é para ESP32 clássico com PSRAM e flash de 4 MiB. Confirme o modo/frequência da PSRAM e o tamanho da flash da sua placa no `menuconfig`; essas características não vêm do modelo.

Edite `main/host_config.h`:

```c
#define WIFI_SSID "sua-rede"
#define WIFI_PASS "sua-senha"
#define INPUT_FORMAT INPUT_RGB565_LE
#define IMG_W 128
#define IMG_H 128
#define NUM_CLASSES 2
#define CLASS_LABELS_ARE_INDICES 0
#define CLASS_LABELS { 1, 0 }
#define TENSOR_ARENA_BYTES (1024 * 1024)
```

Edite as URLs em `main/image_list.h`. Cada download deve conter exatamente 32.768 bytes RGB565 little-endian na configuração padrão. São bytes RAW, não arquivos PNG/JPEG. O rótulo `-1` indica ausência de referência. A lista é executada na ordem, uma vez a cada inicialização.

O host expande RGB565 para RGB888 com a mesma replicação de bits do WASM e coloca os bytes na entrada uint8 do TFLite. A camada QUANTIZE original do modelo é executada pelo TFLite Micro. A imagem seguinte só entra após o retorno síncrono de `Invoke()`; não há handshake WASM.

## 2. Compilar e gravar

Na pasta deste projeto:

```powershell
idf.py -B build-tflite fullclean
idf.py -B build-tflite reconfigure
idf.py -B build-tflite menuconfig
idf.py -B build-tflite build
idf.py -B build-tflite -p COM3 flash monitor
```

Substitua `COM3` pela porta da placa. A primeira configuração baixa os componentes gerenciados. Mantenha `-B build-tflite` nos comandos seguintes. Saia do monitor com `Ctrl+]`.

O firmware valida schema, disponibilidade de operadores, tipos, dimensões e quantidade de classes. Modelo incompatível ou arena insuficiente interrompem o benchmark com uma mensagem no log. Aumente a arena somente se houver PSRAM para ela, a imagem baixada e o CSV acumulado. Novos operadores exigem registrar seus kernels em `tflite_runtime.cpp` e confirmar o suporte aos tipos usados pelo modelo.

## 3. Baixar os resultados

Procure `Conectado ao Wi-Fi. IP:` no monitor serial. Esse é o endereço do ESP32, não o do computador. Ao concluir o benchmark, o host imprime as URLs completas:

```text
http://<IP-DO-ESP32>:80/report
http://<IP-DO-ESP32>:80/metadata
```

CSV e metadados ficam disponíveis depois de processar a lista ou restaurar um experimento concluído da flash. Mantenha a placa ligada durante o download. Em um computador na mesma rede, salve os dois arquivos em uma pasta nova:

```powershell
$runDir = Join-Path 'reports' (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $runDir -Force
Invoke-WebRequest 'http://192.168.0.50:80/report' -OutFile (Join-Path $runDir 'report-tflite.csv')
Invoke-WebRequest 'http://192.168.0.50:80/metadata' -OutFile (Join-Path $runDir 'metadata.json')
```

Troque o IP de exemplo pelo endereço mostrado pela placa. No Research Explorer, atualize o índice e abra a pasta `reports/` deste projeto. Esta adaptação não inclui medições da placa: elas precisam ser geradas gravando e executando o firmware no seu dispositivo.

## Se parar depois da validação do certificado

Se aparecer `A stack overflow in task httpd has been detected` ao abrir os resultados, grave o firmware atualizado: o buffer JSON de `/metadata` fica fora da pilha e `REPORT_HTTP_STACK_BYTES`, em `main/host_config.h`, reserva 8 KiB para o servidor. Essa falha ocorre no servidor HTTP, após as inferências, e o firmware atual restaura os resultados confirmados na flash após reiniciar.

`Certificate validated` confirma apenas a verificação do certificado TLS. Observe os próximos logs: `Download concluido`, `Iniciando preparacao + Invoke` e `Invoke retornou`. Eles permitem distinguir atrasos de rede de travamentos na preparação ou inferência.

Os downloads HTTPS do Cloudinary usam abertura, cabeçalho e leitura do corpo explícitos em `main/download_http.inc`, incluído pelo `main.c`. O fluxo não usa mais `esp_http_client_perform()` assíncrono. Em `main/host_config.h`, `HTTP_DOWNLOAD_TIMEOUT_MS` define o timeout de conexão/cabeçalho (15 segundos), `HTTP_READ_TIMEOUT_MS` define o timeout de leitura do corpo (3 segundos) e `HTTP_DOWNLOAD_TOTAL_TIMEOUT_MS` define o limite por tentativa verificado entre chamadas (45 segundos). As leituras têm no máximo `HTTP_READ_CHUNK_BYTES` (1.024 bytes), com progresso a cada `HTTP_PROGRESS_INTERVAL_MS` (5 segundos). `HTTP_DOWNLOAD_MAX_ATTEMPTS=2` permite uma nova tentativa, com `HTTP_RETRY_DELAY_MS=1000` entre elas. Cada tentativa usa uma conexão nova e valida status HTTP, tamanho exato e conclusão da resposta. Se ambas falharem, a imagem gera `ok=0` e o processamento continua. `download_ms` inclui tentativas, espera entre elas e liberação da conexão. Os logs identificam conexão, cabeçalho, corpo e fechamento. Essas verificações não interrompem à força uma chamada interna do driver ou uma inferência travada.

O firmware compilou e `tests/test_download.py` verificou o código real do downloader com transporte HTTP simulado em 12 cenários, incluindo resposta truncada, timeout, excesso de bytes e nova tentativa. Isso não reproduz falhas TLS na placa física. No site, feche o monitor serial e escolha **Compilar e gravar** para instalar esta mudança; apenas **Reiniciar benchmark** executa o firmware antigo.

Recompile e grave o firmware para aplicar as mudanças. Reiniciar retoma o experimento atual da flash; `/report` fica disponível ao concluir o benchmark ou restaurar um relatório concluído.

## Comparar resultados

### Recuperação automática e resultados persistentes

O host usa a partição existente de 1 MiB chamada `spiffs` como um registro bruto de checkpoints, sem montar um sistema de arquivos. Antes de cada imagem nova, grava a tentativa atomicamente na NVS; depois do processamento, grava o resultado, seu checksum e um marcador final de confirmação na flash. Apenas registros confirmados são restaurados. Gravações interrompidas ocupam um espaço livre e não sobrescrevem resultados anteriores. Erros de armazenamento interrompem o processamento sem descartar silenciosamente o histórico. O host verifica se a partição comporta todas as amostras antes de começar; mais classes/imagens podem exigir uma partição maior.

A tarefa do benchmark está registrada no watchdog. `BENCHMARK_WDT_TIMEOUT_MS=120000` provoca panic/reinício se ela deixar de avançar. Após reiniciar, o CSV e os totais são reconstruídos da flash e o processamento retoma na primeira imagem sem resultado confirmado. `RECOVERY_MAX_ATTEMPTS=2` limita execuções interrompidas por imagem; após duas interrupções, o próximo boot registra essa imagem como erro e continua. Reset manual ou falta de energia durante uma imagem também contam como interrupção. As colunas `recovery_attempts` e `recovery_skipped` identificam a recuperação; o metadata inclui `processed`, `resumed`, `recovery_skipped` e `checkpoint_run_id`.

A primeira instalação começa na imagem 1. Um experimento concluído continua disponível em `/report` e `/metadata` após reiniciar, sem repetir inferências. Para iniciar outro experimento, incremente `BENCHMARK_RUN_ID` em `main/host_config.h` e compile/grave. Mudanças no modelo, lista de imagens, fontes do host ou configuração também iniciam um histórico novo para não misturar experimentos. Salve o relatório anterior antes dessas alterações. `fullclean` limpa apenas os arquivos de compilação do computador; não apaga checkpoints da placa. As gravações na flash ficam fora do tempo medido de inferência. Isso recupera o progresso após uma parada; não identifica nem corrige a causa original de um travamento na inferência.

Consulte as [definições das medições](HOST.pt-BR.md). O CSV preserva os nomes das colunas do host WASM e acrescenta:

- `preprocess_ms`: conversão RAW e preenchimento da entrada do modelo.
- `invoke_ms`: apenas `Invoke()` do TFLite Micro.
- `inference_ms`: preparação + Invoke. A chamada WASM inclui a conversão RGB sintética, portanto este escopo é mais próximo para comparar os hosts embarcados; cada implementação ainda tem custos próprios.
- `arena_reserved_bytes`, `arena_used_bytes`: memória persistente da arena dos tensores.
- `input_sha256`: SHA-256 dos bytes RAW baixados.

`/metadata` registra runtime, hashes do modelo e da lista, quantização da saída, frequência da CPU e contagens. Guarde os metadados com cada CSV. Compare o mesmo modelo, bytes de imagem, dimensões, mapeamento de classes e configurações da placa. A variação de heap não representa toda a memória usada pelo modelo. Os tempos excluem download HTTP e interpretação da saída; não há inferência de aquecimento.

## Usar outro modelo

### Validação desta adaptação

O firmware padrão compilou com ESP-IDF 5.3.1 para `esp32`: 2.012.544 bytes, dentro da partição de aplicação de 2 MiB (4% livres). Foram conferidos o alinhamento de 16 bytes do modelo incorporado e a preservação da lista de imagens. Isso valida a compilação, não a execução física. O tamanho da arena, os downloads e os resultados de inferência ainda precisam ser confirmados na placa. Um modelo maior pode exigir uma partição de aplicação maior.

Selecione o arquivo durante a configuração:

```powershell
idf.py -B build-tflite -D TFLITE_MODEL_FILE=C:/caminho/modelo.tflite reconfigure
```

Ajuste dimensões, formato, classes e rótulos em `host_config.h` e substitua a lista Cloudinary por imagens RAW compatíveis. Para o MobileNetV2 ImageNet incluído no repositório: 224×224, `INPUT_BGR888`, 1.000 classes, `CLASS_LABELS_ARE_INDICES=1`, rótulos desconhecidos `-1`. Seu CSV contém as 1.000 saídas brutas; comece com poucas imagens para não esgotar a RAM do relatório. As necessidades de flash e arena desse modelo devem ser verificadas separadamente.

O host aceita saídas uint8/int8 com quantização por tensor ou float32. A entrada uint8 recebe os bytes RGB diretamente, como nos dois pacotes atuais. Para modelos int8/float, confira `INPUT_REAL_MULTIPLIER` e `INPUT_REAL_OFFSET` conforme o pré-processamento do modelo. São parâmetros configuráveis, não uma regra universal.

Fontes: [TFLite Micro da Espressif](https://components.espressif.com/components/espressif/esp-tflite-micro/versions/1.3.5) e [gerenciamento de memória do TFLite Micro](https://github.com/tensorflow/tflite-micro/blob/main/tensorflow/lite/micro/docs/memory_management.md).
