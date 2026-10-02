[English](02-model-package.md) | [Português (Brasil)](02-model-package.pt-BR.md)

# 02 — ModelPackage e resolução de caminhos

[Índice](README.pt-BR.md) · Fonte: [pipeline/model_package.py](../pipeline/model_package.py)

## Objeto e posição no fluxo

`ModelPackage` é uma dataclass congelada com `root: Path` e `config: ModelConfig`. A imutabilidade impede reatribuir os atributos, mas não torna profundamente imutáveis os dicionários contidos em `config`. O objeto é criado pela CLI, recebido pelo pipeline e compartilhado com o adapter.

`MODELS_DIR = Path(__file__).resolve().parents[1] / "models"` ancora a seleção na raiz do repositório. O identificador CLI é o nome da pasta; `model.name` é uma descrição para exibição e pode ser diferente.

```text
--model drowsiness
          │
          ▼
MODELS_DIR / nome ──► root
          │
          ├── root/model.toml ──► ModelConfig.load
          │
          ▼
┌─────────────────────────────┐
│ ModelPackage                │
│ root + config               │
├─────────────────────────────┤
│ resolve(config.tflite)       │──► TFLite fonte
│ resolve(config.wat_template) │──► WAT fonte
│ wat_path / wasm_path        │──► generated/
│ reports_dir                 │──► reports/
└─────────────────────────────┘
```

Entram um nome e, opcionalmente, outro `models_dir`; o módulo monta caminhos e lê o manifest. Sai um pacote, sem criar diretórios ou compilar. Nomes de arquivos são específicos do pacote; os destinos `generated/model.*` e `reports/` são convenções comuns.

## Métodos, propriedades e erros

| API | Entrada | Retorno e comportamento |
|---|---|---|
| `load(name="drowsiness", models_dir=MODELS_DIR)` | Nome e diretório | Resolve `models_dir`, junta o nome, exige `root.parent == models_dir.resolve()`, lê `root/model.toml` e retorna a dataclass |
| `resolve(path)` | Caminho configurado | Retorna `(root / path).resolve()`; não exige existência |
| `reports_dir` | Estado do pacote | `root / "reports"` |
| `wat_path` | Estado do pacote | `root / "generated/model.wat"` |
| `wasm_path` | Estado do pacote | Mesmo caminho com extensão `.wasm` |
| `validate_sources()` | Estado do pacote | Verifica TFLite e template como arquivos não vazios; retorna `None` |
| `available(models_dir=MODELS_DIR)` | Diretório | Lista ordenada de pacotes para `*/model.toml`, carregando cada um |

`validate_sources` levanta `ValueError` para fonte ausente/vazia; erros de acesso ao filesystem podem propagar. Não valida labels, testes, tamanho de tensor, formato WAT nem identidade de ABI. `available` não chama `validate_sources`; portanto listar um pacote não prova que ele pode executar. Um manifest inválido interrompe a listagem inteira; não há coleta por pacote. Diretório sem manifests produz lista vazia.

## Semântica real dos caminhos

O código aplica a restrição de pai ao nome solicitado. A resolução de uma fonte permite `..`, necessário para o template compartilhado, e também aceita caminhos absolutos: a operação `Path / absoluto` usa o caminho absoluto. Portanto a descrição “todos os caminhos são relativos” é uma convenção dos manifests atuais, não uma barreira de acesso implementada por `resolve`. Links simbólicos também não são validados como uma fronteira de segurança.

No pacote sonolência, `../../wat/templates/mobilenet_int8_v1.wat` sai de `models/drowsiness/` para o diretório compartilhado. O pacote não é transportável isoladamente sem levar esse template ou ajustar seu manifest. No ImageNet, o template selecionado está dentro de `wat/` do pacote.

## Persistência e colisões

As propriedades não criam pastas. A criação ocorre nos escritores de WAT, WASM e relatórios. Duas execuções simultâneas do mesmo pacote usam os mesmos destinos e podem interferir; pacotes distintos têm destinos distintos. Não há bloqueio, diretório temporário por execução ou versionamento. A fonte e os destinos não são comparados para impedir uma configuração que aponte o template para o próprio artefato gerado: mantenha-os separados ao cadastrar modelos.
