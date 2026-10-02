[English](README_ptBR.md) | [Português (Brasil)](README_ptBR.pt-BR.md)

> **Guia WASM → AOT no WSL:** [README_AOT_WSL.md](README_AOT_WSL.pt-BR.md).
> Passo a passo com versões do projeto, LLVM Xtensa, wamrc, firmware e diagnóstico.
> Para configurar o host e a lista de imagens: [HOST.md](HOST.pt-BR.md).
> O host atual baixa arquivos RAW do Cloudinary; as seções antigas sobre câmera são históricas.

> **Guia legado preservado.** Este documento mantém a explicação extensa da implementação anterior, incluindo nomes antigos de arquivos, requisitos e organização da memória. O nome `README_ptBR` foi mantido para preservar referências existentes. Para o host atual, use [HOST](HOST.pt-BR.md) e o [guia AOT](README_AOT_WSL.pt-BR.md).


---
# Idioma ptBR
# Projeto ESP32-CAM com WebAssembly (WAMR)

Este projeto tem como objetivo configurar e executar um firmware customizado na placa **ESP32-CAM**, integrando a captura de imagem com a execução de módulos WebAssembly através do **WASM-Micro-Runtime (WAMR)**.

## 1. Instalação e Configuração do Ambiente ESP32-CAM

### 📦 Instalar o ESP-IDF

- Faça o download do ESP-IDF no endereço oficial:  
  [https://dl.espressif.com/dl/esp-idf/](https://dl.espressif.com/dl/esp-idf/)

- Adicione o executável `idf.py.exe` ao **PATH** do sistema:  
C:\Espressif\tools\idf-exe\1.0.3


### 📁 Criar o Projeto

- Use o template oficial como base do projeto:  
[Sample Project - ESP-IDF GitHub](https://github.com/espressif/esp-idf/tree/master/tools/templates/sample_project)

- Execute o primeiro build para gerar automaticamente o arquivo `sdkconfig`:
```bash
idf.py build
```

### 🧠 Habilitar PSRAM (memória externa)
* Ative os 4MB de PSRAM manualmente no `sdkconfig`:
```
CONFIG_SPIRAM=y
```

### 🧠 Habilitar na placa ESP32-CAM o PSRAM:

* Execute `idf.py menuconfig` e habilite no segunte menu: `Component config → ESP PSRAM | [*] Support for external | SPI-connected RAM`


### 🗂️ Configurar Partição Customizada

* No `menuconfig`, vá para:

  ```
  Partition Table → Partition Table → Custom partition table CSV
  ```

* Insira o seguinte conteúdo no arquivo `partitions.csv` na raiz do projeto:

  ```csv
  # Name, Type, SubType, Offset, Size, Flags
  nvs,data,nvs,0x9000,24K,
  phy_init,data,phy,0xf000,4K,
  factory,app,factory,0x10000,2M,
  spiffs,data,spiffs,0x210000,0x100000,
  ```

  Isso reserva 2MB para o firmware na partição `factory` e 1MB para arquivos na partição `spiffs`.

---

## 2. Adicionar WebAssembly Micro Runtime (WAMR)

* No arquivo `idf_component.yml`, adicione:

  ```yaml
  ## IDF Component Manager Manifest File
  dependencies:
    wasm-micro-runtime:
      version: "^1"
    idf:
      version: ">=4.4"
    espressif/esp32-camera:
      version: "*"
  ```

> O gerenciador de componentes do ESP-IDF buscará automaticamente as dependências durante o build. Não é necessário clonar manualmente repositórios como o WAMR.

---

## 2.1. Como o módulo WASM é incorporado ao firmware

Na versão atual do projeto, o arquivo WebAssembly não é mais convertido para um `header` C com um array gigante do tipo `unsigned char[]`.

Antes, o fluxo era este:

```text
arquivo .wasm
  -> conversão com xxd -i
  -> arquivo .h com array binário em texto C
  -> #include no main.c
  -> compilador processa todo o conteúdo do array
```

Esse método funciona, mas tem uma desvantagem importante: o compilador precisa ler e processar um arquivo `.h` muito grande a cada recompilação relevante, o que aumenta bastante o tempo de build, especialmente após `idf.py fullclean`.

No arranjo atual, o fluxo ficou assim:

```text
main/rust_drowsiness_trucker.wasm
  -> declarado em main/CMakeLists.txt com EMBED_FILES
  -> incorporado ao binário final pelo processo de linkedição
  -> acessado em main.c por símbolos gerados automaticamente
```

Em [main/CMakeLists.txt](./main/CMakeLists.txt), a linha abaixo instrui o ESP-IDF a embutir o arquivo binário diretamente no firmware:

```cmake
idf_component_register(
    SRCS "main.c"
    EMBED_FILES "rust_drowsiness_trucker.wasm"
    ...
)
```

No [main/main.c](./main/main.c), o conteúdo embutido é acessado pelos símbolos gerados pelo build:

```c
extern const uint8_t rust_drowsiness_trucker_wasm_start[] asm("_binary_rust_drowsiness_trucker_wasm_start");
extern const uint8_t rust_drowsiness_trucker_wasm_end[] asm("_binary_rust_drowsiness_trucker_wasm_end");
```

Depois, o código obtém:

- o endereço inicial do arquivo WASM embutido
- o tamanho do arquivo, calculado pela diferença entre o ponteiro final e o inicial

```c
uint8_t *wasm_file_buf = (uint8_t *)rust_drowsiness_trucker_wasm_start;
uint32_t wasm_file_size = (uint32_t)(rust_drowsiness_trucker_wasm_end - rust_drowsiness_trucker_wasm_start);
```

Por fim, esse buffer é passado ao WAMR:

```c
wasm_module_t module = wasm_runtime_load(wasm_file_buf, wasm_file_size, error_buf, sizeof(error_buf));
```

---

## 2.2. O que é o linker neste contexto

O **compilador** transforma cada arquivo-fonte (`.c`) em arquivos objeto intermediários.

O **linker** é a etapa seguinte: ele junta todos esses objetos compilados, bibliotecas, tabelas e arquivos embutidos em uma única imagem final do firmware, como por exemplo:

- `bootloader.bin`
- `partition-table.bin`
- `cnn_webassembly_esp32.bin`

Quando se usa `EMBED_FILES`, o arquivo `.wasm` não vira código C. Em vez disso, o build o entrega ao linker, que o coloca dentro da imagem final do firmware como um bloco binário embutido. Além disso, o linker cria símbolos com nomes como:

- `_binary_rust_drowsiness_trucker_wasm_start`
- `_binary_rust_drowsiness_trucker_wasm_end`

Esses símbolos funcionam como marcadores de memória, permitindo ao código C localizar onde o arquivo embutido começa e termina.

---

## 2.3. Onde o arquivo WASM fica no firmware e na execução

É importante separar duas fases:

### 1. No firmware armazenado na placa

O arquivo `rust_drowsiness_trucker.wasm` fica embutido dentro da partição de aplicação (`factory`) na **memória flash** do ESP32.

Portanto:

- não fica na stack
- não fica na heap
- não fica no SPIFFS
- não fica inicialmente na PSRAM

Ele passa a compor a imagem do firmware gravada em flash.

### 2. Durante a execução do programa

Quando o `main.c` chama `wasm_runtime_load()`, o runtime lê esse conteúdo embutido e cria as estruturas internas necessárias para interpretar/instanciar o módulo WebAssembly.

No projeto atual:

- o **arquivo WASM bruto** está embutido no firmware em **flash**
- a **memória linear do módulo**, estruturas do runtime, buffers e áreas de execução passam a usar **RAM**
- a estratégia implementada prioriza a **PSRAM** para as alocações do WAMR, por meio de:

```c
init_args.mem_alloc_type = Alloc_With_Allocator;
init_args.mem_alloc_option.allocator.malloc_func  = (void *)psram_malloc;
init_args.mem_alloc_option.allocator.realloc_func = (void *)psram_realloc;
init_args.mem_alloc_option.allocator.free_func    = (void *)psram_free;
```

Ou seja, o módulo tem o seguinte comportamento:

- **WASM bruto**: armazenado em flash, dentro do firmware
- **memória de execução do WASM**: alocada majoritariamente em PSRAM
- **heap interna**: usada apenas como fallback quando a PSRAM não consegue atender

---

## 2.4. Diferença entre flash, stack, heap, PSRAM e SPIFFS

### Flash

É a memória não volátil onde o firmware fica gravado. Ao desligar a placa, o conteúdo permanece. O `.wasm` embutido por `EMBED_FILES` fica aqui como parte da imagem do aplicativo.

### Stack

É a memória usada por chamadas de função, variáveis locais e contexto das tasks. Ela é pequena e volátil. O arquivo `.wasm` não é armazenado na stack.

### Heap interna

É a RAM dinâmica principal do ESP32, usada por `malloc()`. Ela é mais limitada e disputada por Wi-Fi, TCP/IP, HTTP e outras estruturas do sistema.

### PSRAM

É a RAM externa da ESP32-CAM. No presente projeto, ela é usada para aliviar a pressão sobre a heap interna, especialmente para a memória linear do módulo WebAssembly e outras estruturas mais pesadas em tempo de execução.

### SPIFFS

É um sistema de arquivos em flash. Ele serviria se o projeto optasse por armazenar o `.wasm` como arquivo externo e carregá-lo dinamicamente em tempo de execução. No arranjo atual, isso não ocorre: o `.wasm` não é carregado do SPIFFS, mas sim embutido diretamente no firmware.

---

## 2.5. Resumo técnico para dissertação

Pode-se descrever a solução da seguinte forma:

> O módulo WebAssembly do modelo de inferência passou a ser incorporado ao firmware por meio do mecanismo `EMBED_FILES` do ESP-IDF, substituindo a estratégia anterior baseada na conversão do binário `.wasm` para um array em linguagem C. Com isso, o arquivo binário deixou de ser processado como texto-fonte pelo compilador e passou a ser embutido na imagem final do firmware durante a etapa de linkedição. Em tempo de execução, o conteúdo é acessado por símbolos gerados automaticamente pelo linker, enquanto as estruturas dinâmicas do runtime WebAssembly são alocadas preferencialmente em PSRAM. Essa abordagem reduz o custo de compilação, melhora a manutenção do projeto e preserva a capacidade de carregar o módulo WASM localmente no dispositivo.

---

## 2.6. Estrutura atual de memória e partições do projeto

### Tamanho total de flash configurado

O projeto está atualmente configurado para **4 MB de flash**, conforme o `sdkconfig`:

```text
CONFIG_ESPTOOLPY_FLASHSIZE="4MB"
```

Essa configuração é necessária porque a tabela de partições reservou:

- 2 MB para a aplicação principal
- 1 MB para SPIFFS
- além de áreas menores para NVS e `phy_init`

### Tabela de partições em uso

O projeto usa uma **tabela customizada** definida em [partitions.csv](./partitions.csv), com as seguintes entradas:

```csv
# Name, Type, SubType, Offset, Size, Flags
nvs,data,nvs,0x9000,24K,
phy_init,data,phy,0xf000,4K,
factory,app,factory,0x10000,2M,
spiffs,data,spiffs,0x210000,0x100000,
```

No `sdkconfig`, isso aparece como:

```text
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions.csv"
CONFIG_PARTITION_TABLE_FILENAME="partitions.csv"
```

### Interpretação de cada partição

#### `nvs`

- tipo: `data`
- subtipo: `nvs`
- offset: `0x9000`
- tamanho: `24 KB`

Essa área é usada pelo ESP-IDF para armazenamento não volátil de parâmetros, como dados persistentes, configurações de Wi-Fi, credenciais, calibrações e outras informações pequenas.

#### `phy_init`

- tipo: `data`
- subtipo: `phy`
- offset: `0xF000`
- tamanho: `4 KB`

Essa partição armazena dados de inicialização da camada física do rádio do ESP32.

#### `factory`

- tipo: `app`
- subtipo: `factory`
- offset: `0x10000`
- tamanho: `2 MB` (`0x200000` bytes)

Essa é a partição principal do firmware. É nela que fica o binário final da aplicação, incluindo:

- o código compilado em C/C++
- bibliotecas do ESP-IDF
- bibliotecas do WAMR
- tabelas internas e metadados do firmware
- o arquivo `rust_drowsiness_trucker.wasm` embutido por `EMBED_FILES`

#### `spiffs`

- tipo: `data`
- subtipo: `spiffs`
- offset: `0x210000`
- tamanho: `1 MB` (`0x100000` bytes)

Essa partição é reservada para sistema de arquivos SPIFFS. Na estrutura atual do projeto, o módulo WASM **não** está sendo carregado a partir do SPIFFS. Ele está embutido diretamente no firmware, dentro da partição `factory`.

---

## 2.7. Endereçamento e ocupação atual da flash

Considerando a configuração atual, a organização prática fica assim:

```text
Flash total configurada: 4 MB

0x0000  -> região inicial / boot metadata
0x1000  -> bootloader
0x8000  -> partition table
0x9000  -> NVS (24 KB)
0xF000  -> phy_init (4 KB)
0x10000 -> app factory (2 MB)
0x210000 -> SPIFFS (1 MB)
```

### Artefatos gerados no build

No build atual, os artefatos principais ficaram com os seguintes tamanhos:

- `bootloader.bin`: `26.752 bytes` (aprox. `26,1 KB`)
- `partition-table.bin`: `3.072 bytes` (aprox. `3,0 KB`)
- `cnn_webassembly_esp32.bin`: `1.702.080 bytes` (aprox. `1,62 MiB`)

### Ocupação da partição `factory`

A partição `factory` possui:

- capacidade total: `2.097.152 bytes` (`2 MB`)
- firmware atual: `1.702.080 bytes`
- espaço livre aproximado: `395.072 bytes`

Em termos percentuais:

- uso da partição `factory`: aproximadamente `81,2%`
- espaço livre restante: aproximadamente `18,8%`

Esse número é coerente com a saída do build:

```text
cnn_webassembly_esp32.bin binary size 0x19f8c0 bytes.
Smallest app partition is 0x200000 bytes.
0x60740 bytes (19%) free.
```

### Ocupação da partição `spiffs`

Atualmente, a partição `spiffs` está apenas **reservada** na tabela de partições. O processo de build do firmware não está usando esse espaço para armazenar o módulo WASM.

Portanto, no arranjo atual:

- `factory`: usada ativamente pela aplicação
- `spiffs`: reservada para uso futuro ou armazenamento de arquivos externos

---

## 2.8. Onde cada elemento fica armazenado

### O firmware principal

O arquivo:

- `build/cnn_webassembly_esp32.bin`

fica gravado na partição `factory` da flash.

### O arquivo WASM

O arquivo:

- `main/rust_drowsiness_trucker.wasm` (nome histórico; esse arquivo não está presente na árvore atual)

é incorporado ao firmware na etapa de linkedição e, portanto, também passa a ficar armazenado dentro da partição `factory`.

Ele **não** fica:

- na stack
- na heap
- na partição SPIFFS
- em um arquivo externo separado na flash

Ele passa a existir como parte integrante da imagem binária principal da aplicação.

### A memória dinâmica do WAMR

Durante a execução, o conteúdo bruto do arquivo `.wasm` está em flash, porém a execução do módulo exige estruturas dinâmicas em RAM, tais como:

- memória linear do módulo
- heap interna do módulo WebAssembly
- stack de execução do runtime
- buffers auxiliares

No código atual, essas alocações foram configuradas para priorizar PSRAM:

```c
init_args.mem_alloc_type = Alloc_With_Allocator;
init_args.mem_alloc_option.allocator.malloc_func  = (void *)psram_malloc;
init_args.mem_alloc_option.allocator.realloc_func = (void *)psram_realloc;
init_args.mem_alloc_option.allocator.free_func    = (void *)psram_free;
```

Isso significa que:

- o **binário WASM** fica na flash
- a **execução do módulo** consome RAM
- o projeto tenta usar **PSRAM** para essa RAM dinâmica
- se a PSRAM não estiver disponível, o código cai para `malloc()` comum

---

## 2.9. Estado atual de PSRAM na configuração do projeto

Na configuração atual do projeto, a PSRAM foi reativada no `sdkconfig` e persistida no `sdkconfig.defaults`.

Os pontos principais são:

```text
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_SPIRAM_TYPE_AUTO=y
CONFIG_SPIRAM_SPEED_40M=y
CONFIG_SPIRAM_BOOT_INIT=y
```

Além disso, o projeto mantém:

```text
CONFIG_SPIRAM_USE_MALLOC=y
CONFIG_SPIRAM_MEMTEST=y
```

Na prática, isso significa que:

- o suporte à PSRAM está habilitado no build
- a inicialização da PSRAM ocorre no boot
- o projeto pode usar `MALLOC_CAP_SPIRAM`
- o runtime WASM pode alocar sua memória dinâmica preferencialmente em PSRAM
- a heap interna permanece como fallback quando necessário

Isso deixa a configuração coerente com o código de inicialização do WAMR em `main.c`.

---

## 2.10. Memória disponibilizada em tempo de execução

O README já descreve onde cada recurso fica armazenado. Além disso, é útil registrar quanto de memória o código solicita explicitamente ao runtime.

### Memória configurada para o módulo WASM

Na chamada abaixo:

```c
module_inst = wasm_runtime_instantiate(module, 1024 * 1024, 512 * 1024, error_buf, sizeof(error_buf));
```

o projeto solicita ao WAMR:

- `1024 * 1024` bytes = **1 MB**
- `512 * 1024` bytes = **512 KB**

Em termos práticos, isso significa que o runtime tenta disponibilizar aproximadamente:

- **1 MB** para a área principal associada à instanciação do módulo
- **512 KB** para a heap/área auxiliar configurada do módulo

Além disso, o ambiente de execução de chamadas WASM é criado com:

```c
exec_env = wasm_runtime_create_exec_env(module_inst, 32 * 1024);
```

ou seja:

- **32 KB** para o `exec_env`

### Buffer de imagem no lado C

O código também mantém um buffer estático para a imagem de entrada:

```c
#define RGB565_BYTES (IMG_W * IMG_H * 2)
static uint8_t img_buf[RGB565_BYTES];
```

Como `IMG_W = 128` e `IMG_H = 128`, o buffer ocupa:

- `128 * 128 * 2 = 32768 bytes`
- ou seja, **32 KB**

### Consumo adicional no lado C

Há ainda outras estruturas de memória que também participam do consumo:

- vetor `g_rows[MAX_REPORT_ROWS]`, que cresce conforme a quantidade de imagens configuradas no benchmark
- buffer dinâmico `g_report_text`, que cresce conforme o relatório é acumulado
- estruturas do Wi-Fi, pilha TCP/IP, HTTP client e HTTP server
- alocações internas do próprio ESP-IDF e do WAMR

Por isso, o consumo real total em RAM não é apenas a soma direta de `1 MB + 512 KB + 32 KB + 32 KB`.

### Resumo numérico do que está explicitamente configurado

Os valores diretamente definidos no código são:

- módulo WASM instanciado com **1 MB**
- heap auxiliar/configurada do módulo com **512 KB**
- `exec_env` com **32 KB**
- buffer de imagem RGB565 com **32 KB**

Somando apenas esses blocos principais explicitamente visíveis no código:

- **aproximadamente 1,56 MB**

Esse valor deve ser entendido como uma **estimativa estrutural mínima dos blocos principais configurados**, e não como medida exata do consumo total do firmware em tempo de execução.

### Onde essa memória tende a ficar

No arranjo atual:

- o arquivo `.wasm` bruto continua armazenado em **flash**
- a memória dinâmica do runtime tende a ser alocada preferencialmente em **PSRAM**
- a heap interna pode ser usada como fallback
- a stack das tasks continua separada disso

Portanto, o leitor pode interpretar a arquitetura assim:

```text
Flash:
  - firmware
  - .wasm embutido

PSRAM (preferencialmente):
  - memória principal da instância WASM
  - heap/configuração auxiliar do módulo
  - parte relevante das alocações dinâmicas do WAMR

RAM interna:
  - fallback de malloc
  - stacks
  - estruturas do sistema, Wi-Fi e rede
```

### Observação metodológica importante

Embora o código configure esses tamanhos, a quantidade efetivamente consumida em tempo de execução depende de:

- disponibilidade real de PSRAM na placa
- sucesso da inicialização da PSRAM no boot
- comportamento interno do WAMR
- número de imagens processadas
- buffers de rede ativos
- uso simultâneo de Wi-Fi, HTTP e relatório

Por isso, a forma correta de relatar resultados experimentais no mestrado é combinar:

- **configuração nominal** do código, descrita nesta seção
- **medição empírica** pelos logs de `heap_caps_get_free_size(MALLOC_CAP_SPIRAM)`, `esp_get_free_heap_size()` e `heap_caps_get_minimum_free_size(MALLOC_CAP_SPIRAM)`

---

## 2.11. Resumo estrutural final

Em termos de arquitetura de armazenamento e execução, o projeto ficou assim:

```text
FLASH (4 MB)
├── bootloader
├── partition table
├── nvs
├── phy_init
├── factory (2 MB)
│   ├── firmware principal
│   ├── código C/C++ compilado
│   ├── bibliotecas ESP-IDF
│   ├── WAMR
│   └── rust_drowsiness_trucker.wasm embutido
└── spiffs (1 MB reservado)

RAM em tempo de execução
├── stack das tasks
├── heap interna
└── PSRAM (quando habilitada)
    └── alvo preferencial das alocações do runtime WASM
```

Esse arranjo evita o uso de um `header` gigante com array binário e torna mais clara a separação entre:

- armazenamento persistente do módulo (`flash`, dentro do firmware)
- memória dinâmica de execução (`RAM`, preferencialmente `PSRAM`)

---

## 3. Compilar, Gravar e Monitorar o Firmware

Utilize um terminal do ESP-IDF como **ESP-IDF PowerShell** ou **ESP-IDF CMD** e execute:

```bash
idf.py menuconfig # mexer nas configurações caso precis
idf.py set-target esp32 # utilizado somente 1 vez para setar o ambiente
idf.py fullclean
idf.py build
idf.py flash monitor
```

* O comando `monitor` permite visualizar a saída de logs e mensagens da ESP32-CAM diretamente no seu terminal.

---

## AOT

1) Gerar o .aot a partir do seu .wasm

wamrc --target=xtensa --target-abi=ilp32 --cpu=esp32 --enable-multi-thread -o main.aot main.wasm

---

## ✅ Requisitos

* Placa: **ESP32-CAM com suporte a PSRAM**
* Sistema: **Windows (recomendado)** com ESP-IDF instalado
* Ferramentas:

  * Git
  * Python 3.8+
  * `idf.py` configurado no PATH

---
* Comandos `wat2wasm`
O comando `wat2wasm` esta dentro do programa WABT que precisa ser feito o download no seguinte endereço [WABT GitHub](https://github.com/WebAssembly/wabt/releases)

Após o download, inserir o programa nas variaveis de ambiente.

O comando `wat2wasm` serve para converter o arquivo wat para o binario wasm
```sh
wat2wasm .\hello_word.wat -o .\hello_word.wasm
```

Na versão atual do projeto, não é mais necessário usar `xxd` para converter o `.wasm` em `header` C. O arquivo `.wasm` deve permanecer binário e ser embutido com `EMBED_FILES`.

---
* Variaveis de Ambiente: 
```sh
IDF-PATH: C:\Espressif\frameworks\esp-idf-v5.3.1\
PATH: 
    C:\Espressif\tools\idf-exe\1.0.3\ 
    C:\xxd 
    C:\Program Files (x86)\WABT\bin
```

## 📎 Observação

O projeto assume que o firmware será executado com suporte a WebAssembly via WAMR. Certifique-se de que o seu código WebAssembly esteja preparado para lidar com buffers de imagem capturados pela câmera integrada.
