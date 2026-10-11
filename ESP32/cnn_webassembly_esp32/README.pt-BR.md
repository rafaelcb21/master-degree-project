# Projeto ESP32-CAM com WebAssembly (WAMR)

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

> **WASM → AOT no WSL:** [README_AOT_WSL.pt-BR.md](README_AOT_WSL.pt-BR.md).
> Passo a passo com versões do projeto, LLVM Xtensa, wamrc, firmware e diagnóstico.
> Configure o host e a lista de imagens com [HOST.pt-BR.md](HOST.pt-BR.md).
> O host atual baixa arquivos RAW do Cloudinary; as seções sobre câmera abaixo descrevem a configuração histórica.
> O [guia histórico completo](README_ptBR.pt-BR.md) mantém seu nome original e também possui versão em inglês.

Este projeto tem como objetivo configurar e executar um firmware personalizado na placa **ESP32-CAM**, integrando a captura de imagens com a execução de módulos WebAssembly pelo **WASM-Micro-Runtime (WAMR)**.

## 1. Instalação e configuração do ambiente ESP32-CAM

### Instalar o ESP-IDF

- Baixe o ESP-IDF no site da [Espressif](https://dl.espressif.com/dl/esp-idf/).
- Adicione `idf.py.exe` à variável de ambiente **PATH**:

```text
C:\Espressif\tools\idf-exe\1.0.3
```

### Criar o projeto

- Use o [projeto de exemplo oficial do ESP-IDF](https://github.com/espressif/esp-idf/tree/master/tools/templates/sample_project).
- Execute a compilação inicial para gerar o `sdkconfig`:

```bash
idf.py build
```

### Habilitar PSRAM

Ative manualmente no `sdkconfig`:

```text
CONFIG_SPIRAM=y
```

Ou use o `menuconfig`:

```bash
idf.py menuconfig
```

```text
Component config → ESP PSRAM → [*] Support for external SPI-connected RAM
```

### Tabela de partições personalizada

No `menuconfig`, selecione:

```text
Partition Table → Partition Table → Custom partition table CSV
```

Insira o seguinte no arquivo `partitions.csv` da raiz:

```csv
# Name, Type, SubType, Offset, Size, Flags
nvs,data,nvs,0x9000,24K,
phy_init,data,phy,0xf000,4K,
factory,app,factory,0x10000,2M,
spiffs,data,spiffs,0x210000,0x100000,
```

## 2. Adicionar o WAMR

Adicione ao `idf_component.yml`:

```yaml
dependencies:
  wasm-micro-runtime:
    version: "^1"
  idf:
    version: ">=4.4"
  espressif/esp32-camera:
    version: "*"
```

O ESP-IDF obtém as dependências automaticamente durante a compilação.
Não é necessário clonar o WAMR manualmente.

## 3. Compilar, gravar e monitorar o firmware

Execute em um terminal do ESP-IDF:

```bash
idf.py set-target esp32
idf.py fullclean
idf.py build
idf.py flash monitor
```

O comando `monitor` exibe a saída da placa em tempo real.

Neste projeto, `idf.py flash monitor` atualiza o firmware e reinicia a placa,
mas preserva as imagens salvas com `benchmark <rodadas> sim` na partição
SPIFFS, desde que a tabela de partições mantenha essa região.
Imagens mantidas apenas na RAM com `nao` e o relatório CSV são perdidos
ao reiniciar.

Para apagar toda a flash, incluindo o cache das imagens, execute:

```bash
idf.py erase-flash
```

Esse comando também apaga o firmware e as configurações persistentes.
Depois, grave novamente com `idf.py flash monitor`. No próximo comando
`benchmark <rodadas> sim`, as imagens precisarão ser baixadas novamente.
Veja os comandos de execução no [guia do host](HOST.pt-BR.md).

Se o download de uma imagem falhar ou receber menos bytes que o esperado,
a placa tenta novamente a mesma imagem até conseguir, sem limite de
tentativas, com uma pausa de 5 segundos entre elas. Isso vale para os modos
`sim`, `nao` e streaming. As imagens já salvas são preservadas; apenas um
download completo é gravado ou usado na inferência. No modo streaming,
`download_ms` inclui as tentativas e suas pausas. Erros de armazenamento
ou falta de espaço continuam interrompendo a preparação.

## Requisitos

- **Placa:** ESP32-CAM com PSRAM.
- **Sistema:** Windows (recomendado).
- **Ferramentas:** Git, Python 3.8+ e `idf.py` no PATH.

## Comandos wat2wasm e xxd

- Baixe o [WABT](https://github.com/WebAssembly/wabt/releases) para usar `wat2wasm`.
- Baixe o [xxd para Windows](https://sourceforge.net/projects/xxd-for-windows/).
- Adicione ambos ao PATH do sistema.

Converta `.wat` para `.wasm`:

```sh
wat2wasm .\hello_word.wat -o .\hello_word.wasm
```

Converta `.wasm` em um array C (método histórico):

```sh
xxd -i hello_word.wasm > test_wasm.h
```

## Variáveis de ambiente

```sh
IDF_PATH: C:\Espressif\frameworks\esp-idf-v5.3.1\
PATH:
    C:\Espressif\tools\idf-exe\1.0.3\
    C:\xxd
    C:\Program Files (x86)\WABT\bin
```

## Observação

Este projeto pressupõe que o firmware tenha suporte à execução de WebAssembly pelo WAMR.
No fluxo histórico com câmera, o código WebAssembly deve processar os buffers das imagens capturadas. Para o host atual com Cloudinary, consulte [HOST.pt-BR.md](HOST.pt-BR.md).
