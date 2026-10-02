[English](07-compilacao-wat-wasm.md) | [Português (Brasil)](07-compilacao-wat-wasm.pt-BR.md)

# 07 — Compilação WAT → WASM

[Índice](README.pt-BR.md) · Fonte: [pipeline/wasm_compiler.py](../pipeline/wasm_compiler.py)

## Interface e algoritmo

`compile_wat_to_wasm(wat_path, wasm_path)` recebe dois caminhos, converte-os em `Path` e exige que a origem seja arquivo. Lê UTF-8, chama a função importada `wasmtime.wat2wasm(wat_source)`, normaliza o retorno para `bytes` e confere prefixo `b"\x00asm"`. Cria o diretório pai do destino e grava o binário. Retorna `{output_path: Path, wasm_bytes: int}`.

```text
WAT fonte do template       dados extraídos
          └──────────┬────────────┘
                     ▼
                generate_wat
                     ▼
          generated/model.wat (UTF-8)
                     │ read_text
                     ▼
             wasmtime.wat2wasm
                     │ bytes
                     ▼
            prefixo 00 61 73 6d?
                     │
                     ▼
          generated/model.wasm
                     │ etapa seguinte
                     ▼
           Module + Instance (runner)
```

Entram o texto já materializado e o destino escolhido pelo pacote. O compilador converte sintaxe e grava bytes; sai um binário. A estrutura e os parâmetros são específicos do modelo; o formato WASM e a conversão são compartilhados. A chamada `wat2wasm` é uma API Python, não um executável externo nem um comando WABT.

## Erros e garantias

Origem ausente causa `FileNotFoundError`; UTF-8 inválido, falha do parser ou escrita sem permissão propagam exceções. Prefixo inesperado causa `RuntimeError`. A verificação do magic number não comprova compatibilidade com `layerparam-v1`, correção matemática ou presença de exports. A validação/compilação para execução acontece quando `Module` é criado no runner.

Não existem flags de otimização, escolha de target, chamada a clang, linking com bibliotecas TFLite ou geração AOT. O arquivo é substituído diretamente, sem escrita atômica. O tamanho retornado é o tamanho do arquivo binário, não o tamanho da memória linear nem o tamanho do TFLite original. O WAT costuma ser maior por codificar cada byte dos blobs com escapes hexadecimais.

O pipeline sempre gera o WAT antes de compilar, e sempre compila antes de inferir. Não há CLI para recompilar somente se o arquivo fonte mudou. Compilar não executa as imagens e não produz métricas por si só.
