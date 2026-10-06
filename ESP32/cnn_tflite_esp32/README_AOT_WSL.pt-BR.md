[English](README_AOT_WSL.md) | [Português (Brasil)](README_AOT_WSL.pt-BR.md)

# Compilar WASM para AOT no WSL e executar no ESP32

Este guia mostra como preparar o compilador **wamrc** no Ubuntu/WSL, converter
`main.wasm` em `main.aot` para o ESP32 e incorporar o resultado ao firmware
deste diretório. O ESP-IDF pode continuar instalado no Windows.

**Escopo:** ESP32 clássico, alvo `esp32`, arquitetura Xtensa. Os comandos de
CPU deste guia não devem ser reutilizados sem ajustes para ESP32-S3 ou
ESP32-C3/C6. Este procedimento é independente do pipeline Python.

> Guia elaborado a partir dos arquivos locais do projeto e das referências
> indicadas. Os comandos de instalação, compilação e gravação não foram
> executados durante a elaboração deste documento.

## Índice

1. [Entenda o fluxo](#1-entenda-o-fluxo)
2. [Confirme as versões do projeto](#2-confirme-as-versões-do-projeto)
3. [Prepare o WSL](#3-prepare-o-wsl)
4. [Obtenha o WAMR compatível](#4-obtenha-o-wamr-compatível)
5. [Compile o LLVM com Xtensa](#5-compile-o-llvm-com-xtensa)
6. [Compile o wamrc](#6-compile-o-wamrc)
7. [Gere o main.aot](#7-gere-o-mainaot)
8. [Compile e grave o firmware](#8-compile-e-grave-o-firmware)
9. [Rotina para os próximos modelos](#9-rotina-para-os-próximos-modelos)
10. [Resolva problemas](#10-resolva-problemas)
11. [Referências](#11-referências)

## 1. Entenda o fluxo

```text
Preparação da ferramenta, uma vez por ambiente/versão:
WAMR compatível + LLVM com Xtensa → wamrc Linux

Para cada modelo:
main.wasm → wamrc no WSL → main.aot
                              ↓
                 ESP-IDF no Windows → firmware → ESP32
```

| Item | Onde fica/roda | Função |
|---|---|---|
| LLVM com Xtensa | Sistema de arquivos Linux do WSL | Backend usado pelo compilador |
| `wamrc` | Ubuntu/WSL | Compila WASM para código do alvo |
| `main.wasm` | Pasta `main/` do projeto Windows | Entrada do compilador; também pode ser interpretada |
| `main.aot` | Pasta `main/` do projeto Windows | Artefato AOT incorporado ao firmware |
| ESP-IDF | Terminal ESP-IDF do Windows | Compila e grava o firmware |
| WAMR embarcado | ESP32 | Carrega e executa o módulo |

O `wamrc` gerado no Linux é um executável Linux, não um `wamrc.exe`.
O AOT contém código para o **alvo escolhido**, não para o computador que
executou o compilador. Ele ainda depende da compatibilidade com o runtime.

Os blocos **PowerShell**, **WSL/Bash** e **Terminal ESP-IDF** indicam onde
executar cada comando. A barra `\` ao final de uma linha continua um comando
no Bash; ela não é o continuador de linha do PowerShell.

## 2. Confirme as versões do projeto

Abra o **PowerShell**:

```powershell
Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
Get-Content dependencies.lock
Get-Content managed_components\espressif__wasm-micro-runtime\idf_component.yml
```

Na cópia usada para escrever este guia:

| Configuração | Valor encontrado |
|---|---|
| Alvo ESP-IDF | `esp32` |
| ESP-IDF registrado no lock | `5.3.1` |
| Componente WAMR | `espressif/wasm-micro-runtime 1.3.2~2` |
| Repositório informado pelo componente | `https://github.com/espressif/wasm-micro-runtime.git` |
| `repository_info.commit_sha` | `12a42fde353e72ae1aa7c117e3d395340ab37413` |
| `AOT_CURRENT_VERSION` no runtime | `3` |

Fontes locais: [dependencies.lock](dependencies.lock),
[manifesto do componente](managed_components/espressif__wasm-micro-runtime/idf_component.yml)
e [core/config.h](managed_components/espressif__wasm-micro-runtime/core/config.h).

**Use o commit informado pelo componente como referência para compilar o
wamrc.** Apenas escolher a branch mais recente ou uma tag com número parecido
não garante correspondência com o pacote instalado. O sufixo `~2`, sozinho,
não permite concluir quais arquivos ou patches mudaram.

O manifesto [main/idf_component.yml](main/idf_component.yml) permite uma faixa
de versões. O lock registra a versão resolvida nesta cópia. Se atualizar o
componente, confira novamente o manifesto instalado antes de reutilizar o
compilador. Não edite arquivos dentro de `managed_components` para corrigir
a compatibilidade.

## 3. Prepare o WSL

### 3.1. Instale ou confira o Ubuntu

**PowerShell:**

```powershell
wsl --list --verbose
```

Se o Ubuntu já aparecer com `VERSION 2`, use essa instalação. Se ainda não
tiver WSL, execute no **PowerShell como administrador**:

```powershell
wsl --install -d Ubuntu
```

Reinicie se solicitado e abra o Ubuntu para criar o usuário e a senha Linux.
Depois, entre nele:

```powershell
wsl -d Ubuntu
```

Se sua distribuição tiver outro nome, use o nome mostrado por
`wsl --list --verbose`. Esses passos seguem a
[documentação de instalação do WSL](https://learn.microsoft.com/en-us/windows/wsl/install).

### 3.2. Confira memória e disco

**WSL/Bash:**

```bash
free -h
df -h ~ /mnt/c
```

**PowerShell, em outra janela:**

```powershell
Get-PSDrive C
```

Planeje dezenas de GB livres para fontes e artefatos do LLVM. O uso exato
depende do build. O espaço disponível no Linux e na unidade Windows que
armazena a distribuição precisam ser suficientes.

Comece com **um job de compilação**. Isso reduz o consumo simultâneo de RAM,
mas não garante que uma etapa individual de link caiba na memória disponível.

Opcionalmente, ajuste `%UserProfile%\.wslconfig`. Exemplo para uma máquina
que tenha RAM suficiente para reservar 8 GB ao WSL:

```ini
[wsl2]
memory=8GB
processors=2
swap=4GB
```

Preserve as outras opções que já existirem no arquivo e deixe memória para o
Windows. Salve o trabalho aberto no WSL antes de aplicar:

**PowerShell:**

```powershell
wsl --shutdown
wsl -d Ubuntu
```

Isso encerra todas as distribuições em execução. Veja a
[referência de configuração do WSL](https://learn.microsoft.com/en-us/windows/wsl/wsl-config).

### 3.3. Instale as dependências

**WSL/Bash:**

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git ccache \
    python3 python3-pip python3-venv zlib1g-dev ca-certificates file
```

Confira:

```bash
gcc --version
cmake --version
ninja --version
git --version
python3 --version
```

Use `sudo` para instalar os pacotes. Os builds nas próximas etapas devem rodar
com seu usuário Linux.

## 4. Obtenha o WAMR compatível

Mantenha as fontes e o build no diretório pessoal Linux. O projeto Windows
será acessado apenas para ler o WASM e entregar o AOT.

**WSL/Bash, instalação nova:**

```bash
mkdir -p "$HOME/toolchains"
git clone https://github.com/espressif/wasm-micro-runtime.git \
    "$HOME/toolchains/wamr-esp32-1.3.2-r2"
cd "$HOME/toolchains/wamr-esp32-1.3.2-r2"
git checkout --detach 12a42fde353e72ae1aa7c117e3d395340ab37413
git rev-parse HEAD
```

**Resultado esperado:** o último comando imprime o commit acima. O estado
`detached HEAD` é esperado: estamos fixando a versão da ferramenta.

Se a pasta já existir, não clone por cima: entre nela, consulte
`git status --short` e `git rev-parse HEAD`. Preserve alterações locais.
Só prossiga quando ela representar a revisão desejada.

Defina uma variável para os próximos comandos:

```bash
export WAMR_ROOT="$HOME/toolchains/wamr-esp32-1.3.2-r2"
test -f "$WAMR_ROOT/wamr-compiler/CMakeLists.txt"
test -f "$WAMR_ROOT/build-scripts/build_llvm.py"
```

Os comandos `test` não imprimem nada em caso de sucesso. Se o checkout falhar
ou os arquivos não existirem, resolva isso antes do build. Não substitua
silenciosamente o commit pela branch mais recente.

## 5. Compile o LLVM com Xtensa

Esta é a etapa mais demorada. O LLVM padrão da distribuição não necessariamente
inclui o backend Xtensa necessário para o ESP32.

Na revisão do projeto, `build_llvm_xtensa.sh` instala requisitos Python com
`pip --user` e chama `build-scripts/build_llvm.py --platform xtensa`.
Aqui chamamos esse mesmo script Python diretamente, usando um ambiente
virtual para evitar conflito com o Python gerenciado pelo Ubuntu.

**WSL/Bash:**

```bash
cd "$WAMR_ROOT"
python3 -m venv .venv-build
source .venv-build/bin/activate
python -m pip install -r build-scripts/requirements.txt

export CMAKE_BUILD_PARALLEL_LEVEL=1
set -o pipefail
python build-scripts/build_llvm.py --platform xtensa \
    --extra-cmake-flags="-DLLVM_PARALLEL_LINK_JOBS=1" \
    2>&1 | tee llvm-build.log
```

Confira o código de saída **imediatamente após o comando**:

```bash
echo $?
```

**Resultado esperado: `0`.** Com `pipefail`, uma falha do build não fica
escondida pelo sucesso de `tee`.

`CMAKE_BUILD_PARALLEL_LEVEL=1` limita o paralelismo de `cmake --build`, usado
pelo script. A opção de LLVM limita os jobs de link do gerador Ninja.
Veja a [referência do CMake](https://cmake.org/cmake/help/latest/envvar/CMAKE_BUILD_PARALLEL_LEVEL.html).

Nesta revisão, o script:

- Busca o LLVM da Espressif, branch `xtensa_release_15.x`.
- Habilita `LLVM_EXPERIMENTAL_TARGETS_TO_BUILD=Xtensa`.
- Compila e empacota as bibliotecas.
- Substitui a pasta de build pelo conteúdo do pacote ao concluir o fluxo.

Por isso, depois do sucesso, `core/deps/llvm/build` pode conter um SDK
empacotado, sem `build.ninja`. Isso é diferente de um build interrompido.

Confira o resultado:

```bash
find "$WAMR_ROOT/core/deps/llvm/build" -name LLVMConfig.cmake
git -C "$WAMR_ROOT/core/deps/llvm" rev-parse HEAD
```

Registre o commit do LLVM: a branch usada pelo script pode mudar ao longo do
tempo. Para reproduzir exatamente o ambiente, preserve esse commit e o log.
A origem desses detalhes é o
[script instalado no projeto](managed_components/espressif__wasm-micro-runtime/build-scripts/build_llvm.py).

**Se houver erro, não avance para o wamrc.** Consulte a seção de problemas.

## 6. Compile o wamrc

A pasta de build do wamrc é diferente da pasta de build do LLVM.

**WSL/Bash:**

```bash
cmake -S "$WAMR_ROOT/wamr-compiler" \
    -B "$WAMR_ROOT/wamr-compiler/build-esp32" \
    -G Ninja -DCMAKE_BUILD_TYPE=Release

cmake --build "$WAMR_ROOT/wamr-compiler/build-esp32" --parallel 1
```

Durante a configuração, confira a mensagem `Using LLVMConfig.cmake in:`.
Ela deve apontar para o LLVM em `$WAMR_ROOT/core/deps/llvm/build`.

Não configure `WAMR_BUILD_TARGET=XTENSA` para construir a ferramenta Linux:
o executável wamrc precisa rodar no computador. O alvo do AOT é escolhido
depois, com `--target=xtensa`.

Confira:

```bash
export WAMRC="$WAMR_ROOT/wamr-compiler/build-esp32/wamrc"
test -x "$WAMRC"
file "$WAMRC"
"$WAMRC" --target=help
```

**Resultados esperados:**

- `file` identifica um executável Linux ELF.
- A lista de alvos inclui `xtensa`.

Se não incluir Xtensa, confira qual LLVM foi encontrado pelo CMake. Não
prossiga usando um compilador que apenas aceita x86/ARM.

## 7. Gere o main.aot

### 7.1. Aponte para o projeto Windows

**WSL/Bash:**

```bash
export ESP_PROJECT="/mnt/c/Users/rafae/Downloads/master-degree-project/ESP32/cnn_webassembly_esp32"
test -s "$ESP_PROJECT/main/main.wasm"
ls -lh "$ESP_PROJECT/main/main.wasm"
```

O caminho `C:\Users\rafae\...` do Windows corresponde a
`/mnt/c/Users/rafae/...` nessa configuração do WSL. Ajuste a variável se
mover o projeto. Use aspas para caminhos com espaços.

O arquivo de entrada deve ser um **WASM binário**, não texto WAT renomeado.
Este guia começa com `main.wasm` já gerado.

### 7.2. Compile para ESP32

**WSL/Bash:**

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

| Opção | Motivo |
|---|---|
| `--target=xtensa` | Gera código para a arquitetura do ESP32 clássico |
| `--cpu=esp32` | Seleciona a CPU alvo |
| `--cpu-features=-fp` | Mantém a configuração de ponto flutuante do script AOT existente neste projeto |
| `--opt-level=3` | Define explicitamente a otimização |
| `--size-level=3` | Define explicitamente a otimização de tamanho |
| `-o ...main.aot.new` | Gera um candidato antes de substituir o artefato em uso |

`-fp` desabilita a geração com a opção de coprocessador de ponto flutuante
do backend Xtensa. Não significa que todos os ESP32 sejam desprovidos de FPU.
Se mudar essa escolha para um experimento, registre-a junto aos resultados.

O comando acompanha as opções do
[script AOT já presente](main/build_aot_windows.ps1). Esse script PowerShell
espera um `wamrc.exe` e usa nomes antigos de artefatos; **não é o script
executado neste procedimento WSL**.

Não incluímos `--target-abi=ilp32`: o guia usa o padrão desse compilador
para Xtensa, em vez de transportar uma opção do histórico sem necessidade.
Também não incluímos `--enable-multi-thread`: a pthread do host C não exige
habilitar threads dentro do módulo WebAssembly. Se o próprio WASM usar
memória compartilhada/atômicos, compilador e runtime precisarão ser
configurados para esse contrato.

### 7.3. Confira o candidato antes de substituir

Execute apenas se a compilação anterior terminou com sucesso:

```bash
python3 - "$ESP_PROJECT/main/main.aot.new" <<'PY'
import pathlib
import struct
import sys

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
if len(data) < 8 or data[:4] != b"\x00aot":
    raise SystemExit("Arquivo sem cabecalho AOT valido")
version = struct.unpack_from("<I", data, 4)[0]
print(f"Arquivo: {path}\nBytes: {len(data)}\nVersao AOT: {version}")
if version != 3:
    raise SystemExit("Versao diferente de AOT_CURRENT_VERSION=3 deste runtime")
PY
```

Essa checagem verifica o cabeçalho e a versão do formato. Ela **não substitui
o carregamento e a execução na placa**, nem demonstra equivalência numérica
entre AOT e interpretador.

Depois de conferir, preserve o AOT anterior e publique o candidato:

```bash
if [ -f "$ESP_PROJECT/main/main.aot" ]; then
    cp -p "$ESP_PROJECT/main/main.aot" \
        "$ESP_PROJECT/main/main.aot.backup-$(date +%Y%m%d-%H%M%S)"
fi
mv "$ESP_PROJECT/main/main.aot.new" "$ESP_PROJECT/main/main.aot"
ls -lh "$ESP_PROJECT/main/main.aot"
sha256sum "$ESP_PROJECT/main/main.wasm" "$ESP_PROJECT/main/main.aot"
```

O AOT já está na pasta Windows. Não é necessário copiá-lo de outra janela.
Anote os hashes, os commits do WAMR/LLVM e as opções de compilação para
identificar o que foi medido em cada experimento.

## 8. Compile e grave o firmware

Use um **terminal ESP-IDF do Windows**, com o ambiente da versão do projeto
ativado. O Python e as ferramentas desse terminal pertencem ao ESP-IDF.

```powershell
Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
idf.py --version
Get-Item main\main.wasm, main\main.aot
```

### 8.1. Configure o host e o runtime

Edite:

- [main/host_config.h](main/host_config.h): Wi-Fi, entrada, saída, exports e limites.
- [main/image_list.h](main/image_list.h): URLs Cloudinary e rótulos.
- [HOST.md](HOST.pt-BR.md): contrato completo e descrição das medições.

Confira o SDK:

```powershell
Select-String -Path sdkconfig -Pattern '^CONFIG_IDF_TARGET=','^CONFIG_WAMR_ENABLE_AOT=','^CONFIG_WAMR_ENABLE_INTERP=','^CONFIG_SPIRAM=','^CONFIG_MBEDTLS_CERTIFICATE_BUNDLE='
```

Nesta cópia, o alvo é `esp32` e as quatro opções estão habilitadas.
Se precisar alterá-las:

```powershell
idf.py menuconfig
```

Na busca por `/`, procure `WAMR_ENABLE_AOT`; a opção é **AOT** no menu
**WASM Micro Runtime**. Preserve o interpretador se quiser comparar os modos.
PSRAM e o certificate bundle são usados pelo host atual.

### 8.2. Incorpore o AOT e compile

O [main/CMakeLists.txt](main/CMakeLists.txt) já faz a seleção:

- Existe `main/main.aot`: incorpora AOT e define `MODEL_MODULE_IS_AOT=1`.
- Não existe: incorpora `main/main.wasm` e define `MODEL_MODULE_IS_AOT=0`.

Não precisa adicionar outro `target_add_binary_data` nem editar as macros
manualmente. Reconfigure após criar, remover ou trocar o tipo do artefato:

```powershell
idf.py reconfigure
idf.py build
```

Só grave se o build terminar com sucesso. Ajuste a porta:

```powershell
idf.py -p COM5 flash monitor
```

No monitor, procure:

```text
Artefato embutido selecionado no build: AOT
WASM instanciado.
```

A segunda mensagem usa o nome genérico do runtime mesmo quando o módulo é
AOT. Depois do benchmark, consulte o CSV em `http://<ip-do-esp32>:80/report`,
ou na porta/caminho configurados. Para sair do monitor, use `Ctrl+]`.

### 8.3. Encontre o IP do ESP32 e abra o relatório

1. No **terminal ESP-IDF**, entre na pasta do projeto e abra o monitor serial:

   ```powershell
   Set-Location 'C:\Users\rafae\Downloads\master-degree-project\ESP32\cnn_webassembly_esp32'
   idf.py -p COM3 monitor
   ```

   `COM3` foi a porta identificada nesta placa. Se aparecer `could not open
   port`, confira a lista `Available ports` do próprio monitor ou a seção
   **Portas (COM e LPT)** do Gerenciador de Dispositivos do Windows e ajuste
   o comando. Feche outros programas que estejam usando a mesma porta.

2. Procure a mensagem de conexão Wi-Fi. Exemplo observado nesta placa:

   ```text
   wi-fi: Conectado ao Wi-Fi. IP: 192.168.0.24
   ```

   O endereço também pode aparecer na linha `esp_netif_handlers: sta ip:`.
   Se perdeu essas mensagens, reinicie a placa com o monitor aberto para
   acompanhar a conexão novamente. Isso também reinicia o benchmark.

3. Substitua `<ip-do-esp32>` pelo endereço mostrado. Para o exemplo acima,
   cole no navegador:

   ```text
   http://192.168.0.24/report
   ```

   Com a porta padrão 80, essa URL equivale a
   `http://192.168.0.24:80/report`. Se alterou `REPORT_HTTP_PORT` ou
   `REPORT_HTTP_URI` em `host_config.h`, use os valores configurados.

4. No host atual, aguarde o término de todas as imagens e a mensagem
   `Servidor HTTP iniciado` antes de acessar. O CSV completo só fica
   disponível depois do benchmark. Mantenha a placa ligada e conectada:
   o relatório fica na memória e é perdido quando ela reinicia.

O computador deve ter acesso ao ESP32 pela rede; normalmente, conecte ambos
à mesma rede local, sem isolamento entre dispositivos. O comando `ipconfig`
mostra os endereços **do computador**, não o IP atribuído à placa. O endereço
`192.168.0.24` é um exemplo real desta sessão e pode mudar após reconexões;
confira sempre o monitor.

**Se aparecer `Checksum mismatch between flashed and built applications`:**
o firmware na placa difere do build local. `monitor` apenas acompanha a
execução; ele não grava o código novo. Para atualizar, saia com `Ctrl+]`,
confira `host_config.h` e execute:

```powershell
idf.py build
idf.py -p COM3 flash monitor
```

Só execute a gravação se o build terminar com sucesso. Depois, confira
novamente o IP e aguarde o benchmark do firmware atualizado.

### 8.4. Volte ao interpretado para comparação

No **terminal ESP-IDF**, preserve o AOT fora do nome reconhecido pelo CMake:

```powershell
Rename-Item -LiteralPath main\main.aot -NewName main.aot.disabled
idf.py reconfigure
idf.py build
idf.py -p COM5 flash monitor
```

Se `main.aot.disabled` já existir, escolha outro nome antes de renomear.
O log deve mostrar `WASM`. Para voltar ao AOT, restaure o nome `main.aot`,
reconfigure e compile novamente.

Use o mesmo WASM de origem, as mesmas imagens e as mesmas configurações do
host nas comparações. Um novo `main.wasm` **não atualiza** o AOT sozinho.

## 9. Rotina para os próximos modelos

Com LLVM e wamrc prontos, você não precisa recompilá-los para cada imagem ou
cada novo WASM compatível com o mesmo runtime.

1. Coloque o novo `main.wasm` em `main/`.
2. Ajuste os headers do host para o contrato desse módulo.
3. Abra o WSL e restaure as variáveis abaixo.
4. Repita a [geração e conferência do AOT](#7-gere-o-mainaot).
5. No terminal ESP-IDF, reconfigure, compile e grave.

**WSL/Bash, em uma nova sessão:**

```bash
export WAMR_ROOT="$HOME/toolchains/wamr-esp32-1.3.2-r2"
export WAMRC="$WAMR_ROOT/wamr-compiler/build-esp32/wamrc"
export ESP_PROJECT="/mnt/c/Users/rafae/Downloads/master-degree-project/ESP32/cnn_webassembly_esp32"
test -x "$WAMRC"
```

O ambiente virtual foi necessário para o script que prepara o LLVM. Ele
não precisa estar ativado para executar o binário wamrc.

## 10. Resolva problemas

### O .sh abre e fecha uma janela no Windows

Abra o Ubuntu com `wsl -d Ubuntu` e execute os comandos Bash lá. A associação
de arquivos `.sh` do Windows não confirma que um build tenha sido realizado.

### Python mostra externally-managed-environment

Use o ambiente virtual da etapa 5. Não é necessário instalar pacotes no
Python global nem usar `--break-system-packages`. A chamada direta ao script
Python evita o `pip --user` do wrapper antigo.

### Build interrompido, Killed ou WSL sem memória

Confira `free -h`, o log e, quando disponível, `dmesg -T` para sinais de OOM.
Reduza o paralelismo e ajuste os recursos do WSL conforme a RAM física.

Se o build do LLVM foi interrompido **e ainda tem build.ninja**, retome:

**WSL/Bash:**

```bash
test -f "$WAMR_ROOT/core/deps/llvm/build/build.ninja"
cmake --build "$WAMR_ROOT/core/deps/llvm/build" --target package --parallel 1
```

Só execute o segundo comando se o primeiro passar. Ele reutiliza os objetos
existentes. Se concluir, a árvore de build pode ser usada pelo CMake do wamrc;
confira o caminho de `LLVMConfig.cmake`.

**Detalhe desta revisão:** o script considera a presença de
`lib/libLLVMCore.a` como indicação de build pronto. Esse arquivo pode existir
antes de todo o build terminar. Rodar o wrapper novamente após uma falha pode
pular o trabalho restante; retome com `cmake --build` como acima.

Se não houver `build.ninja` e já existir o SDK empacotado após um build
bem-sucedido, siga para a etapa 6. Não tente executar Ninja dentro do pacote.

### Permission denied; o build só funciona com sudo

`sudo ninja` não aumenta a memória disponível. Verifique se um comando
anterior criou arquivos pertencentes a root:

```bash
ls -ld "$WAMR_ROOT" "$WAMR_ROOT/core/deps/llvm/build"
find "$WAMR_ROOT" -user root -print -quit
```

Se essa árvore de ferramentas foi criada por você e contém arquivos de root,
corrija apenas essa pasta, depois de conferir o caminho:

```bash
realpath "$WAMR_ROOT"
sudo chown -R "$(id -u):$(id -g)" "$WAMR_ROOT"
```

Volte a compilar sem `sudo`. Não aplique essa correção a diretórios de sistema.

### No space left on device

Confira `df -h ~ /mnt/c` no WSL e `Get-PSDrive C` no PowerShell.
O disco virtual da distribuição ocupa espaço na unidade física do Windows.

Não apague automaticamente `core/deps/llvm/build`: depois do empacotamento,
ela contém o SDK usado para construir o wamrc. Antes de remover artefatos,
identifique o que precisa preservar para futuras recompilações.

Apagar arquivos no Linux não garante redução imediata do arquivo VHDX no
Windows. Consulte os procedimentos oficiais de
[gerenciamento de disco do WSL](https://learn.microsoft.com/en-us/windows/wsl/disk-space)
antes de manipular o disco virtual. Liberado o espaço, tente retomar o build
incremental; `idf.py fullclean` não é o primeiro passo obrigatório.

### Xtensa não aparece ou CMake encontra outro LLVM

Confira a saída `Using LLVMConfig.cmake in:` e o cache:

```bash
grep '^LLVM_DIR:' "$WAMR_ROOT/wamr-compiler/build-esp32/CMakeCache.txt"
find "$WAMR_ROOT/core/deps/llvm/build" -name LLVMConfig.cmake
```

Se necessário, configure uma nova pasta de build com `-DLLVM_DIR=...`,
usando o **diretório que contém** o arquivo encontrado. Não misture uma
pasta de build antiga com LLVM de outra origem.

### unknown binary version

Compare `AOT_CURRENT_VERSION` em `core/config.h` do compilador e do runtime,
o commit do wamrc e o cabeçalho do AOT. Neste projeto, a versão esperada é 3.

Um número de formato igual é necessário, mas não prova compatibilidade
completa. Recompile o wamrc da revisão do componente e gere outro AOT.
Confira também se o firmware incorporou o arquivo novo.

Não altere o número da versão no cabeçalho para forçar o carregamento.
O documento local do WAMR explica a
[compatibilidade de AOT](managed_components/espressif__wasm-micro-runtime/doc/build_wasm_app.md).

### AOT module load failed: mmap memory failed

Essa mensagem pode vir de uma alocação de memória no loader. **Não demonstra
que AOT esteja desabilitado.** Confira primeiro o log completo e o SDK.

No port ESP-IDF desta revisão, mapeamentos executáveis usam
`MALLOC_CAP_EXEC` no caminho padrão. Existe também um caminho condicionado
por `WASM_MEM_DUAL_BUS_MIRROR`, que aloca na PSRAM e converte o endereço.
Confira qual caminho seu build habilita; ter PSRAM livre, isoladamente,
não garante que a alocação e o mapeamento exigidos sejam possíveis.
Veja [espidf_memmap.c](managed_components/espressif__wasm-micro-runtime/core/shared/platform/esp-idf/espidf_memmap.c).

Investigue o tamanho do código AOT, a disponibilidade/fragmentação de memória
com a capacidade exigida e as configurações do runtime. O código e a memória
linear do módulo têm necessidades diferentes. Gerar o arquivo no computador
não assegura que ele caiba e possa executar na placa.

### O firmware continua usando o modelo anterior

Confira o horário/hash de `main.aot`, reconfigure, compile e grave o firmware
novo. A presença de AOT sempre tem prioridade sobre o WASM neste CMake.
Confira no monitor qual modo foi incorporado.

### O módulo carrega, mas a inferência falha ou o resultado está errado

Confira os exports, as dimensões, o formato do RAW, o tipo da saída e
`NUM_CLASSES` em [host_config.h](main/host_config.h). O host é configurável,
mas o modelo ainda precisa respeitar o [contrato descrito em HOST.md](HOST.pt-BR.md).
Verifique a interpretação das classes e compare os resultados com a execução
interpretada do mesmo WASM.

## 11. Referências

A base específica deste guia são os arquivos efetivamente instalados:

- [Manifesto e commit do componente WAMR](managed_components/espressif__wasm-micro-runtime/idf_component.yml).
- [Wrapper de build Xtensa](managed_components/espressif__wasm-micro-runtime/wamr-compiler/build_llvm_xtensa.sh).
- [Script Python de build/empacotamento LLVM](managed_components/espressif__wasm-micro-runtime/build-scripts/build_llvm.py).
- [CMake do wamrc](managed_components/espressif__wasm-micro-runtime/wamr-compiler/CMakeLists.txt).
- [Opções do compilador](managed_components/espressif__wasm-micro-runtime/wamr-compiler/main.c).
- [Opções WAMR do ESP-IDF](managed_components/espressif__wasm-micro-runtime/build-scripts/esp-idf/wamr/Kconfig).

Os links de `managed_components` pressupõem que as dependências tenham sido
resolvidas pelo ESP-IDF. Para instalação do WSL, limites de recursos e
paralelismo do CMake, use as referências oficiais vinculadas nas respectivas
etapas.

