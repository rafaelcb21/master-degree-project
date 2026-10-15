# Proveniência da compilação AOT

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

O [gerador](../../build_aot_with_provenance.py) registra o vínculo **WASM de origem → wamrc e comando → AOT produzido** durante a compilação. Não atribui retroativamente uma origem ao AOT antigo e não comprova gravação ou execução na placa.

## Situação em 14/10/2026

**Confirmação do autor:** a geração AOT da coleta foi realizada em WSL em outro computador, seguindo integralmente o README do projeto, inclusive a revisão WAMR `12a42fde353e72ae1aa7c117e3d395340ab37413`. O autor também forneceu o WASM original e confirmou seu uso na geração. As duas cópias preservadas são idênticas byte a byte, com 510.943 bytes e SHA-256 `b2f2b2369a341031caec99530c3277499949712336c52d7a1ab5f2f70ee8ac13`. **A origem está identificada por hash e confirmação do autor; não foi recuperado um manifesto contemporâneo da compilação.** Ver [registro dos originais](../experimental-method/original-wasm-report.json).

O registro histórico `main/comando.txt` contém um comando e sua saída, mas não contém hashes que o vinculem ao AOT da coleta. A tentativa adicional com o compilador Windows `wamrc 1.3.2` deste computador, durante a auditoria, falhou com:

```text
Error: llvm get target from triple (xtensa-pc-linux-ilp32) failed
```

O `LLVMConfig.cmake` desse build informa LLVM 15.0.7 e alvos `AArch64;ARM;Mips;RISCV;X86`, sem Xtensa. A tentativa ficou preservada em [provenance-report.json](reports/20261014T152736270631Z/provenance-report.json), com o [log do compilador](reports/20261014T152736270631Z/compile-report.txt), WASM de entrada e configurações do build. O status é **`failed`**, sem hash de AOT produzido. O AOT existente do firmware não foi substituído.

**Para uma nova compilação com manifesto, execute o fluxo no ambiente que dispõe do backend Xtensa.** O WSL da coleta pertence ao outro computador; a falha Windows desta máquina não descreve aquele ambiente. Os testes do fluxo passaram com chamadas de compilador simuladas; isso não representa uma nova compilação real para ESP32.

## Gerar o manifesto no Windows

Na raiz do projeto, ajuste o caminho para um compilador com suporte Xtensa:

```powershell
.venv-models/Scripts/python.exe build_aot_with_provenance.py build --wamrc C:/toolchains/wamrc.exe
```

Também pode usar o wrapper:

```powershell
./ESP32/cnn_webassembly_esp32/main/build_aot_windows.ps1 -Wamrc C:/toolchains/wamrc.exe
```

O WASM padrão é `models/drowsiness/generated/model.wasm`. Para outro arquivo, use `--wasm caminho/model.wasm` ou `-Wasm` no wrapper. Para incluir registros da configuração/versões do compilador e LLVM, repita `--evidence caminho/arquivo`. O wrapper aceita `-EvidenceFiles`.

## Gerar no WSL/Linux

O script Python usa apenas a biblioteca padrão. Execute no ambiente onde o wamrc funciona:

```bash
cd /mnt/c/Users/rafae/Downloads/master-degree-project
python3 build_aot_with_provenance.py build --wamrc /caminho/para/wamrc
```

Não passe um executável Linux ao Python Windows. O [guia AOT](../../ESP32/cnn_webassembly_esp32/README_AOT_WSL.pt-BR.md) explica a preparação do compilador compatível com o runtime.

## O que fica registrado

Cada tentativa cria uma pasta nova em `analysis/aot-provenance/reports/<UTC>/`:

| Arquivo | Conteúdo |
|---|---|
| `input.wasm` | Cópia preservada do WASM efetivamente passado ao compilador |
| `output.aot` | AOT produzido; só aceito após sucesso e verificação do cabeçalho versão 3 |
| `compile-report.txt` | Saída combinada do compilador, inclusive em caso de falha |
| `provenance-report.json` | Hashes SHA-256, tamanhos, versão do wamrc, argumentos exatos, diretório de execução, horários UTC e status |
| `evidence-*` | Cópias dos arquivos adicionais enviados por `--evidence`, com hashes |

O JSON registra o hash do executável wamrc e os hashes de entrada e saída. O comando fixa `--target=xtensa`, `--target-abi=ilp32`, `--cpu=esp32`, `--cpu-features=-fp`, `--opt-level=3`, `--size-level=3`, `--bounds-checks=1` e `--stack-bounds-checks=1`.

O status **`compilation_verified`** exige saída zero do compilador, AOT versão 3 e preservação dos hashes do WASM e do executável durante a compilação. Uma pasta existente não pode ser reutilizada. Falhas permanecem como `failed`, sem serem apresentadas como prova de compilação bem-sucedida.

## Verificar e usar na próxima coleta

```powershell
.venv-models/Scripts/python.exe build_aot_with_provenance.py verify analysis/aot-provenance/reports/ID_DA_EXECUCAO/provenance-report.json
```

A verificação compara hashes e tamanhos das cópias arquivadas com o manifesto e rejeita tentativas falhas. É uma verificação de integridade local, não uma assinatura digital nem autenticação independente do documento.

Após a compilação bem-sucedida, preserve a pasta completa, use seu `output.aot` no firmware e registre o hash da imagem gravada e o ID do manifesto junto ao CSV da nova coleta. Essa etapa de firmware/coleta não é executada pelo gerador. Para sustentar portabilidade, o desktop deve executar o `input.wasm` dessa mesma pasta.

O relatório está disponível na biblioteca web em português e inglês; a documentação de metodologia aponta para este fluxo. **Procedimento, versão e uso do WASM original estão confirmados pelo autor; o hash e a igualdade das cópias foram verificados. O manifesto histórico não foi recuperado. A instrumentação para novas compilações foi implementada e testada.**
