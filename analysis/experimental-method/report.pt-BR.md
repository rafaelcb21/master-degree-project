# Relatório de metodologia experimental e rastreabilidade — WASM / ESP32-CAM

[English](report.md) | [Português (Brasil)](report.pt-BR.md)

Data da auditoria: **14/10/2026**. Revisão consultada: `4804169`, com os arquivos presentes no workspace nessa data.

Este relatório responde aos itens (a)–(g) para o estudo de caso **drowsiness**. Inclui a memória do MobileNetV2 α0,35 como comparação. A auditoria foi feita por leitura de código, configuração, registros de build, dissertação e cálculo dos hashes locais. Não foram executados novos benchmarks nem gravado firmware na placa.

**Distinção necessária:** a dissertação descreve um experimento desktop com Node.js; o pipeline atual do repositório executa WASM com Python/Wasmtime. Uma configuração encontrada hoje não comprova, sozinha, a configuração utilizada em uma coleta antiga.

## Resumo das respostas

| Item | Resultado | Alcance da evidência |
|---|---|---|
| a — versões e interpretador | WAMR `1.3.2~2`; ESP-IDF `5.3.1`; interpretador **rápido** habilitado. Node.js `v22.19.0` consta na dissertação e está instalado hoje. | Lock, configuração e build locais; Node histórico registrado no texto, sem log do benchmark. |
| b — compilação | **Procedimento, versão e WASM de origem confirmados pelo autor:** geração AOT em WSL em outro computador seguindo o README; WASM original de 510.943 bytes, com SHA-256 identificado. Destino Xtensa/ESP32, `--cpu-features=-fp`, otimização 3 e tamanho 3; bounds checks automáticos para 32 bits nessa revisão. WAT → WASM atual: `wasmtime.wat2wasm`, pacote `49.0.0`. | Procedimento e uso do WASM informados pelo autor; identidade das duas cópias verificada por SHA-256 e comparação byte a byte. Não há manifesto contemporâneo da compilação. |
| c — tempo | ESP32: `esp_timer_get_time()` antes/depois da chamada exportada. Inclui RGB565 → RGB888; exclui rede e cópia da entrada. | Confirmado no host e no WAT atuais. Temporizador do experimento Node não recuperado. |
| d — imagens e câmera | Arquivos RAW entregues por Wi-Fi/HTTPS; cache opcional em SPIFFS ou PSRAM. O host atual não captura imagens da câmera. | Caminho implementado confirmado; justificativa metodológica sugerida abaixo, a validar pelo autor. |
| e — tamanhos e memória | Drowsiness WASM: **514.564 bytes**; AOT: **528.564 bytes**; memória linear: **1.114.112 bytes**. Alocador do ESP32 prioriza PSRAM. | Artefatos atuais; há fallback de alocação. Não é uma medição do consumo total de RAM. |
| f — mesmo WASM | **Cópias originais dos projetos desktop e ESP32 idênticas byte a byte:** 510.943 bytes, SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`. O autor confirmou esse arquivo como entrada da geração AOT. | Identidade das cópias verificada; uso na compilação confirmado pelo autor. Os arquivos atuais regenerados são distintos desses originais. |
| g — aquecimento | **Não foi possível determinar se a chamada de 0,170 s foi descartada**, nem se era a primeira chamada. | O pipeline WASM atual não mede latência e não contém descarte de warm-up. |

## a) Versões dos ambientes e modo de execução

| Componente | Valor encontrado | Fonte |
|---|---|---|
| WAMR embarcado | Pacote Espressif `espressif/wasm-micro-runtime 1.3.2~2` | [dependencies.lock](../../ESP32/cnn_webassembly_esp32/dependencies.lock) |
| Revisão informada pelo componente | `12a42fde353e72ae1aa7c117e3d395340ab37413` | `managed_components/espressif__wasm-micro-runtime/idf_component.yml` |
| ESP-IDF | `5.3.1` no lock; `v5.3.1-dirty` na descrição do build | Lock e `build/project_description.json` |
| Interpretador WAMR | **Rápido**, loader normal; clássico desabilitado | [sdkconfig](../../ESP32/cnn_webassembly_esp32/sdkconfig), também confirmado em `build/config/sdkconfig.h` |
| AOT WAMR | Habilitado; arquivo AOT versão 3 | Configuração e cabeçalho binário de `main.aot` |
| Node.js histórico | `v22.19.0`, segundo a dissertação | `Dissertacao_Rafael_Braga_UNICO.tex`, linhas 2262 e 2400 |
| Node.js instalado na auditoria | `v22.19.0` | Saída de `node --version`; não comprova a versão usada numa coleta antiga |
| Runtime WASM do desktop atual | Wasmtime/Python; pacote instalado `49.0.0` | [wasm_inference.py](../../inference/wasm_inference.py), metadados de `.venv-models` |

As opções relevantes são `CONFIG_WAMR_ENABLE_INTERP=y`, `CONFIG_WAMR_INTERP_FAST=y`, `CONFIG_WAMR_INTERP_LOADER_NORMAL=y` e `CONFIG_WAMR_ENABLE_AOT=y`. A presença do interpretador no firmware **não significa que a execução AOT use esse interpretador**.

O [CMake do host](../../ESP32/cnn_webassembly_esp32/main/CMakeLists.txt) incorpora `main.aot` quando esse arquivo existe; caso contrário, seleciona `main.wasm`. No build local preservado, `compile_commands.json` e `main.aot.S` indicam incorporação de AOT. Isso comprova a seleção no build local, não a identidade do firmware gravado em cada experimento.

## b) Opções de compilação

**Confirmação do autor em 14/10/2026:** a geração AOT da coleta foi realizada em **WSL em outro computador**, seguindo integralmente o [README de geração AOT](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.pt-BR.md), inclusive a versão/revisão indicada. O procedimento e a versão são, portanto, registrados como **confirmados pelo relato do autor**. A revisão WAMR indicada é `12a42fde353e72ae1aa7c117e3d395340ab37413`, compatível com o componente embarcado `1.3.2~2`.

O comando seguido na etapa de geração, conforme o guia, foi:

```bash
"$WAMRC" \
    --target=xtensa \
    --cpu=esp32 \
    --cpu-features=-fp \
    --opt-level=3 \
    --size-level=3 \
    -o "$ESP_PROJECT/main/main.aot.new" \
    "$ESP_PROJECT/main/main.wasm"
```

O guia não passa `--target-abi` nem `--bounds-checks` explicitamente. O comando histórico abaixo é um registro adicional, distinto da confirmação de execução do procedimento do README.

**Atualização do item b:** o autor disponibilizou duas cópias preservadas do WASM original e confirmou que esse arquivo foi utilizado para gerar o AOT. Ambas possuem 510.943 bytes e SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`, com igualdade byte a byte verificada. Assim, o WASM de origem está identificado; a associação à compilação é sustentada pela confirmação do autor. Não foi recuperado um manifesto contemporâneo da geração.

Foi implementado o [fluxo com manifesto de proveniência](../aot-provenance/README.pt-BR.md) para novas compilações. A tentativa Windows feita nesta auditoria falhou por ausência de suporte Xtensa **neste computador**; ela não caracteriza o ambiente WSL utilizado na coleta. A indisponibilidade desse ambiente nesta máquina não invalida a confirmação do autor.

### Registro de wamrc encontrado

O [comando.txt](../../ESP32/cnn_webassembly_esp32/main/comando.txt) preserva este comando e sua saída de sucesso:

```bash
./wamrc --target=xtensa --target-abi=ilp32 --cpu=esp32 \
  -o /mnt/c/Users/User/Downloads/main.aot \
  /mnt/c/Users/User/Downloads/main.wasm
```

| Opção | Valor registrado |
|---|---|
| Arquitetura de destino | `xtensa` |
| CPU de destino | `esp32` |
| ABI | `ilp32` |
| Triple informado na saída | `xtensa-pc-linux-ilp32` |
| CPU features | Campo vazio nessa saída |
| Nível de otimização | `3`, informado pelo compilador |
| Nível de tamanho | `3`, informado pelo compilador |
| Formato de saída | AoT file |
| Bounds checks | Não explicitado no comando |

No código da revisão indicada, `wamr-compiler/main.c` inicializa a opção de bounds checks em modo automático; `core/iwasm/compilation/aot_llvm.c` habilita as verificações de memória por padrão em alvos de 32 bits. **O comando do guia mantém bounds checks habilitados por padrão para Xtensa/ESP32 nessa revisão.** Essa conclusão decorre do código e das opções do procedimento confirmado pelo autor; não é um parâmetro recuperado do AOT nem uma inspeção do executável utilizado no outro computador.

Na versão inicialmente auditada, o script Windows continha `--target=xtensa --cpu=esp32 --cpu-features=-fp --opt-level=3 --size-level=3` e nomes `rust_drowsiness_trucker.wasm/.aot`; sua presença não comprova que foi utilizado para gerar `main.aot`. O [script atualizado](../../ESP32/cnn_webassembly_esp32/main/build_aot_windows.ps1) agora chama o gerador de proveniência e preserva o AOT existente. O [guia AOT](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.pt-BR.md) contém instruções de reprodução, que também não devem ser confundidas com logs da coleta.

O procedimento, a revisão do compilador e o uso do WASM original como entrada estão confirmados pelo relato do autor. O hash desse WASM foi calculado sobre as cópias preservadas. Não há manifesto histórico que tenha registrado simultaneamente os hashes de entrada, compilador e AOT; um manifesto futuro documentará a nova execução, sem constituir um registro contemporâneo da coleta antiga.

### Conversão WAT → WASM

O [conversor atual](../../pipeline/wasm_compiler.py) usa a função **`wasmtime.wat2wasm(wat_source)`**, com leitura UTF-8 e gravação dos bytes retornados. O pacote instalado consultado é `wasmtime 49.0.0`, compatível com `wasmtime>=49,<50` em [requirements.txt](../../requirements.txt).

Não há, nessa chamada, flags de arquitetura, CPU, otimização ou bounds checks: ela converte o formato textual em binário WebAssembly. A escolha Xtensa/ESP32 acontece posteriormente, na compilação AOT. A reprodução do WAT atual do drowsiness com essa biblioteca resultou em **exatamente o mesmo WASM atual do desktop**, verificado por igualdade de bytes.

Não foi recuperada a ferramenta/versão usada na conversão do artefato do experimento Node histórico. Portanto, a conversão atual não deve ser retroativamente atribuída àquela coleta sem registros adicionais.

## c) Como o tempo foi medido

### ESP32 — implementação atual

O intervalo em [main.c](../../ESP32/cnn_webassembly_esp32/main/main.c) é:

```c
int64_t t0 = esp_timer_get_time();
int32_t status = call_wasm_i32(WASM_RUN_EXPORT);
row->inference_us = esp_timer_get_time() - t0;
```

`WASM_RUN_EXPORT` é `run_mobilenetv2`, inclusive no drowsiness. A função de temporização retorna microssegundos; o CSV grava `inference_us / 1000.0` em milissegundos, com três casas decimais. A unidade da API está documentada pela [Espressif — ESP Timer, v5.3.1](https://docs.espressif.com/projects/esp-idf/en/v5.3.1/esp32/api-reference/system/esp_timer.html).

| Etapa | Incluída em `inference_ms`? |
|---|---|
| Obter imagem pela rede ou pelo cache | Não |
| Esperar handshake de prontidão | Não |
| Validar entrada e copiar RAW para a memória linear | Não |
| Escrever flag do formato | Não |
| Lookup da função e chamada via `wasm_runtime_call_wasm` | Sim |
| Conversão RGB565 → RGB888 dentro do módulo | **Sim** |
| QUANTIZE e demais operações da rede | Sim |
| Localizar/ler saída, decidir classe e escrever CSV | Não |
| Inicializar, carregar e instanciar o runtime/módulo | Não |

A conversão está incluída porque o [modelo](../../models/drowsiness/model.toml) possui `synthetic_layer = "rgb565_to_rgb888"`, o host escreve a flag RGB565 e o dispatcher do WAT chama essa operação dentro de `run_mobilenetv2`.

O fluxo pode ser resumido como: **rede/cache → cópia da entrada → início do cronômetro → chamada WAMR + conversão + rede neural → fim do cronômetro → leitura/classificação da saída**.

O download tem uma medida separada. Em streaming, o código atual soma as tentativas e esperas de retry em `download_us`. Quando a entrada vem de SPIFFS ou de cache PSRAM, `download_ms` é zero; esse zero não significa que o download inicial ou a leitura do cache foram gratuitos, apenas que não são contabilizados nessa coluna durante a inferência.

### Desktop

O WASM atual é instanciado uma vez com Wasmtime e chamado para cada imagem, mas **não há cronômetro no loop WASM atual**. A consolidação usa zero como tempo não utilizado no desktop; isso não representa inferência instantânea. Ver [convenções de análise](../README.pt-BR.md).

Para a medição Node.js descrita na dissertação, não foi localizado o script que permite identificar a API de tempo, os pontos inicial/final ou a inclusão da conversão e da cópia da imagem. Esses campos permanecem **não confirmados**. O temporizador do baseline TFLite/Python é outro caminho e não deve ser utilizado para descrever o benchmark WASM/Node.

## d) Entrega das imagens e ausência de captura pela câmera

O host implementa conexão Wi-Fi e download **HTTPS** de arquivos `.raw` listados em [image_list.h](../../ESP32/cnn_webassembly_esp32/main/image_list.h), com URLs Cloudinary. A configuração do drowsiness usa **128 × 128 pixels, RGB565, dois bytes por pixel**, totalizando **32.768 bytes por imagem**. A dissertação descreve a ordenação little-endian.

O [cache](../../ESP32/cnn_webassembly_esp32/main/image_cache.c) permite persistência em **SPIFFS na flash** ou armazenamento em **PSRAM**. Se não houver cache RAM suficiente e houver uma única rodada, existe fallback para streaming de rede. O modo efetivamente escolhido em cada coleta depende da interação/configuração dessa sessão; não pode ser determinado só pela presença desses caminhos no código.

O caminho implementado não usa cartão SD nem recebe o payload das imagens pela serial. A serial serve ao monitor e às escolhas do benchmark. **SPIFFS é flash da placa, não cartão de memória.**

O firmware atual não contém chamadas de inicialização/captura `esp_camera_init` ou `esp_camera_fb_get`. A dependência `esp32-camera` existe, mas não comprova captura de imagens. A referência à câmera no capítulo 2 pode descrever o hardware sem significar que ela integrou a avaliação experimental.

**Justificativa metodológica sugerida, a confirmar pelo autor:** foram utilizadas imagens previamente selecionadas e rotuladas para permitir comparar plataformas com entradas controladas, sem variação de iluminação, enquadramento, captura e exposição. Assim, o experimento avalia a inferência sobre arquivos, e não o desempenho completo de captura ao vivo. O código confirma o uso de arquivos; não registra a motivação original dessa escolha.

## e) Tamanhos dos artefatos e alocação de memória

Os tamanhos abaixo são dos arquivos presentes na auditoria, não necessariamente dos arquivos utilizados nas tabelas históricas da dissertação.

| Artefato / região | Bytes | KiB |
|---|---:|---:|
| Drowsiness — `models/drowsiness/generated/model.wasm` | 514.564 | 502,50 |
| Drowsiness — `ESP32/cnn_webassembly_esp32/main/main.aot` | 528.564 | 516,18 |
| Drowsiness — memória linear inicial | **1.114.112** | **1.088,00** |
| MobileNetV2 α0,35 — `models/mobilenetv2_alpha035/generated/model.wasm` | 1.807.875 | 1.765,50 |
| MobileNetV2 α0,35 — memória linear inicial | 3.670.016 | 3.584,00 |

Não foi encontrado um AOT do MobileNetV2 no pacote atual desse modelo. O `main.aot` auditado corresponde ao host configurado para drowsiness; não deve ser usado como tamanho AOT do MobileNetV2.

### Mapa do drowsiness

Endereços finais **inclusivos**; o campo `END` no relatório original é exclusivo.

| Região | Início → fim inclusivo | Bytes |
|---|---:|---:|
| Região inicial de controle/reserva | 0 → 2.047 | 2.048 |
| WEIGHTS | 2.048 → 386.655 | 384.608 |
| BIAS | 386.656 → 414.823 | 28.168 |
| MUL | 414.832 → 443.003 | 28.172 |
| SHIFT | 443.008 → 471.179 | 28.172 |
| Q6 | 471.184 → 499.351 | 28.168 |
| PARAMS | 499.360 → 507.247 | 7.888 |
| SLOT0 | 507.248 → 703.855 | 196.608 |
| SLOT1 | 703.856 → 900.463 | 196.608 |
| SLOT2 | 900.464 → 1.097.071 | 196.608 |
| Sobra da última página | 1.097.072 → 1.114.111 | 17.040 |

Existem **24 bytes de alinhamento** entre as regiões de parâmetros. A região inicial contém flags de formato e controle; não é totalmente livre. SLOT2 tem 192 KiB: juntar a sobra da última página ao retângulo da figura não aumenta o tamanho do buffer.

Fonte: [layout final do drowsiness](../../models/drowsiness/reports/20261008T150239050848Z/11-layout-final-memoria.txt). O [WAT gerado](../../models/drowsiness/generated/model.wat) declara 17 páginas de 65.536 bytes. O metadata de memória do AOT também totaliza **1.114.112 bytes**, representados internamente por uma unidade de 1.114.112 bytes; essa representação do AOT não deve ser confundida com páginas WebAssembly de 64 KiB.

### Onde os dados ficam

| Objeto | Política de localização no ESP32 |
|---|---|
| WASM/AOT incorporado ao firmware | Seção `.rodata.embedded`, armazenada na imagem em flash |
| Cópia mutável usada pelo loader | PSRAM (`MALLOC_CAP_SPIRAM \| MALLOC_CAP_8BIT`), com fallback `malloc` |
| Memória linear e alocações do WAMR | Alocador customizado que solicita PSRAM; fallback `malloc/realloc` |
| Buffer RAW e texto do relatório | Alocações explícitas em PSRAM |
| Cache persistente de imagens | SPIFFS na flash |
| Cache RAM de imagens | PSRAM |

O host prioriza PSRAM, mas possui fallback; não é rigoroso afirmar que toda alocação ocorreu em PSRAM em todas as sessões sem logs/inspeção do endereço. O AOT ainda pode requerer alocações específicas de código pelo runtime; sua residência completa não foi medida aqui.

`WASM_APP_HEAP_BYTES` é zero; `WASM_MODULE_STACK_BYTES` é 1 MiB e `WASM_EXEC_STACK_BYTES` é 32 KiB. Esses são argumentos/configurações do runtime, não regiões adicionais do mapa de memória linear; o uso efetivo pode depender do modo AOT/interpretado. No desktop, a memória linear é administrada pelo runtime na memória do processo, sem PSRAM.

**Tamanho do arquivo, memória linear e consumo total de RAM são medidas distintas.** O consumo inclui cópia do artefato, metadados, pilhas, buffers, cache, Wi-Fi e runtime. `heap_used`/`psram_used` no CSV são diferenças de memória livre antes/depois da chamada; valores zero nessas colunas não significam que o modelo não ocupa memória.

## f) Identidade do WASM e prova de portabilidade

### Identificação do WASM original da coleta

O autor forneceu os seguintes arquivos preservados:

| Cópia | Caminho | Bytes |
|---|---|---:|
| Projeto desktop | `C:/Users/rafae/Downloads/modelos/wasm-project/project_predict/main.wasm` | 510.943 |
| Projeto ESP32 | `C:/Users/rafae/Downloads/dev/MESTRADO/github_repository/cnn_webassembly_esp32/main/main.wasm.txt` | 510.943 |

Os dois arquivos são **idênticos byte a byte** e possuem o mesmo SHA-256:

```text
b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13
```

Apesar da extensão `.txt`, a segunda cópia contém um binário WebAssembly, com cabeçalho `00 61 73 6D 01 00 00 00`. O autor confirmou que esse arquivo foi usado como entrada para a geração AOT no outro computador. A igualdade das cópias foi verificada diretamente; a identificação do arquivo utilizado na compilação decorre da confirmação do autor. Ver [registro dos arquivos originais](original-wasm-report.json).

**Texto para a dissertação:**

> A geração do artefato AOT utilizou como entrada o arquivo original `main.wasm`, de 510.943 bytes, conforme confirmado pelo autor. A identidade das cópias preservadas nos projetos desktop e ESP32 foi verificada por comparação byte a byte e pelo resumo criptográfico SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`, obtendo-se igualdade integral. A compilação foi realizada em WSL em outro computador, seguindo o procedimento e a revisão WAMR especificados no README do projeto. Dessa forma, identifica-se o módulo WebAssembly de origem do artefato AOT e documenta-se a correspondência entre as duas cópias do módulo. O hash foi calculado posteriormente sobre os arquivos preservados; não foi recuperado um manifesto contemporâneo da compilação.

### SHA-256 dos artefatos locais

| Artefato | SHA-256 |
|---|---|
| WASM drowsiness atual do desktop | `7634ca88b88c73bb3451e85fe59046c72dcf592322e2c3faf5ede25313c7ac2f` |
| AOT atual da pasta ESP32 | `c1a1d9ec9f0428336f6f508e7640304b67a22c8bfca2dfc019e12fcd35646f78` |
| WASM MobileNetV2 atual | `84db5ad4e4c65a77327c8f40cdbac99352dcdd10691a48bbc3594603ff562cb2` |
| Reconversão em memória do WAT atual da pasta ESP32 | `d86e8dade226ce995e5450809d391ce1957fac005e3c99bb8f35c235239d7ff5` |

A reconversão do WAT da pasta ESP32 produziu **514.568 bytes**, enquanto o WASM drowsiness do desktop possui **514.564 bytes**. Já a reconversão do WAT gerado do desktop reproduziu seu WASM byte a byte. A diferença encontrada não demonstra erro numérico ou falta de portabilidade; demonstra que os artefatos atuais não permitem certificar identidade binária pela simples comparação disponível.

O arquivo `ESP32/cnn_webassembly_esp32/main/main.wasm` **não existe no workspace atual**. O payload `.byte` de `build/main.aot.S` foi reconstruído e possui exatamente o hash do `main.aot` atual. Isso confirma a correspondência entre AOT e fonte assembly do build local, sem comprovar qual WASM originou o AOT nem qual firmware rodou na placa nas coletas.

**Conclusão atualizada:** as cópias originais dos projetos desktop e ESP32 são binariamente idênticas, e o autor confirmou o arquivo como entrada da geração AOT. Os hashes dos artefatos regenerados atualmente não devem ser usados para identificar esse WASM original. A igualdade das cópias documenta o compartilhamento do módulo entre os projetos; os relatórios antigos não registram hashes em tempo de execução que permitam auditar independentemente qual arquivo foi carregado em cada chamada.

Para sustentar essa afirmação em uma nova coleta, devem ser preservados:

1. Um WASM canônico, com tamanho e SHA-256 calculados antes da execução.
2. O mesmo hash registrado pelo desktop e no firmware interpretado; conferir o artefato incorporado e a imagem gravada.
3. Para AOT, um manifesto ligando **SHA-256 do WASM de origem → comando/versão de wamrc → SHA-256 do AOT → firmware**.
4. Identificadores da execução, configuração e hashes das imagens de entrada.

O AOT é um binário diferente do WASM e, portanto, terá outro hash. No modo AOT, a afirmação correta é que o ESP32 executa um artefato nativo **derivado do mesmo WASM**, quando essa derivação é rastreável. Não se deve exigir igualdade entre o hash do `.aot` e o do `.wasm`.

Os resultados completos estão em [artifacts-report.json](artifacts-report.json). Para repetir a auditoria local dos artefatos atuais:

```powershell
.venv-models/Scripts/python.exe analysis/audit_experimental_artifacts.py
```

Esse comando não mede desempenho nem recupera hashes históricos; atualiza apenas o JSON com os arquivos presentes naquele momento.

## g) Aquecimento do desktop e máximo de 0,170 s

A dissertação registra Node.js `v22.19.0`, média de **0,041 s**, mínimo de **0,036 s** e máximo de **0,170 s**, com 2.000 imagens. A razão máximo/média arredondada é aproximadamente **4,15**.

Esse máximo isolado **não comprova** compilação JIT na primeira chamada: seria necessário identificar a ordem das amostras, o intervalo cronometrado e o estado do runtime. Compilação/tiering, caches, escalonamento e outros fatores podem afetar a latência. A documentação do [pipeline de compilação WebAssembly do V8](https://v8.dev/docs/wasm-compilation-pipeline) descreve Liftoff/TurboFan e diferentes momentos de compilação; por isso a atribuição a JIT deve ser tratada como hipótese, não resultado observado.

**Resposta sobre descarte: não confirmado.** Não foram localizados o script Node de medição, a sequência de tempos individuais ou um registro de warm-up. Não há fundamento para escrever que a primeira execução foi descartada, nem para afirmar que o máximo corresponde à primeira execução. O WASM/Python atual não contém aquecimento separado, não descarta casos e não registra latência; isso não resolve o comportamento do Node histórico.

Redação fiel à evidência disponível:

> O experimento desktop registrou tempo médio de 0,041 s e máximo de 0,170 s. Os registros disponíveis não permitem identificar se houve aquecimento prévio ou descarte da primeira chamada. Consequentemente, não é possível separar retrospectivamente efeitos de inicialização e compilação dos demais fatores de variação da latência.

Para uma nova medição, registrar separadamente carregamento/compilação/instanciação, primeira chamada e chamadas após um aquecimento definido antes da coleta. Preservar os tempos individuais na ordem de execução e informar número de chamadas de aquecimento, descarte e tamanho da amostra final. Não descartar o máximo retrospectivamente apenas porque ele é maior que a média.

## Evidências e pendências para a dissertação

| Pendência | Evidência necessária |
|---|---|
| Temporizador e fronteiras do Node histórico | Script executado e comandos/opções do Node |
| Warm-up e descarte | Código de aquecimento e sequência original de tempos |
| Identidade binária entre plataformas | WASM usado em cada coleta, hashes e manifesto de execução |
| Registro contemporâneo da geração AOT | WASM de origem identificado por SHA-256 e uso confirmado pelo autor; manifesto automático de compilação não foi recuperado |
| Memória física efetivamente usada | Log de alocação/endereço ou instrumentação da coleta |
| Motivo original de não usar câmera | Confirmação metodológica do autor |

A dissertação foi consultada em `C:/Users/rafae/Downloads/latex-mestrado-2/Dissertacao_Rafael_Braga_UNICO.tex` (linhas 2234–2493); esse arquivo externo não foi alterado. As referências a código/build neste relatório identificam as fontes da auditoria, mesmo quando o Research Explorer não disponibiliza esses formatos para leitura.
