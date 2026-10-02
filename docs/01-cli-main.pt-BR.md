[English](01-cli-main.md) | [Português (Brasil)](01-cli-main.pt-BR.md)

# 01 — CLI: main.py

[Índice](README.pt-BR.md) · Fonte: [main.py](../main.py)

## Função e dependências

`main(argv=None)` é o único ponto de entrada. Recebe uma lista opcional de argumentos para `argparse`; com `None`, usa os argumentos do processo. Importa `ModelPackage` no carregamento do módulo e importa `ModelPipeline` apenas no ramo de execução. Assim, `--list-models` não importa NumPy, TFLite e Wasmtime através do pipeline, embora ainda precise de Python e de `tomllib`/`tomli` para ler manifests.

| Argumento | Tipo/ação | Default | Efeito |
|---|---|---|---|
| `--model` | string | `drowsiness` | Nome de pasta em `models/` |
| `--list-models` | `store_true` | `False` | Lista nome da pasta e `model.name` |
| `-h`, `--help` | automático do argparse | — | Mostra ajuda e encerra |

Não há `--one`, filtro de imagens, seleção de subgrafo, modo apenas compilação, escolha direta de template ou opção de top-K na CLI. Essas decisões estão no manifest ou no código. Se `--list-models` e `--model` forem usados juntos, a listagem prevalece.

```text
argv
 │
 ▼
ArgumentParser.parse_args
 │
 ├── --list-models ──► ModelPackage.available()
 │                         │
 │                         └──► imprime pacotes; return 0
 │
 └── execução ───────► ModelPackage.load(args.model)
                           │
                           ▼
                     ModelPipeline(package).run()
                           │
                           └──► return 0 se não houve exceção
```

Entram argumentos textuais; `main.py` seleciona um ramo, carrega o pacote e delega. Sai um código de retorno ou uma exceção de encerramento. O nome é específico do modelo; o controle da CLI é genérico. Nenhum byte de imagem passa pela CLI.

## Comandos reais

```powershell
python main.py
python main.py --list-models
python main.py --model drowsiness
python main.py --model mobilenetv2_alpha035
python main.py --help
```

Execute na raiz para que `main.py` seja encontrado. Ao fornecer o caminho absoluto do script, os caminhos dos pacotes continuam independentes do diretório de trabalho, pois `MODELS_DIR` deriva de `__file__`.

## Saídas e falhas

O bloco `try` captura apenas `OSError`, `ValueError` e `RuntimeError`, emitindo `Erro: ...` no stderr por `parser.exit(1, ...)`. Retorna 0 quando a listagem ou execução termina normalmente. `raise SystemExit(main())` propaga esse resultado ao sistema operacional. Argumentos inválidos são tratados por argparse antes do `try` e normalmente encerram com código 2.

`KeyError`, `TypeError` e exceções específicas que não herdam das classes capturadas podem produzir traceback. Não se deve documentar que todo manifest incorreto gera uma mensagem amigável. Um manifest ausente causa `OSError`; um contrato desconhecido causa `ValueError`. Erros por imagem são coletados pelo runner e levam a `RuntimeError` no final do pipeline, após gravar o relatório.

## Extensão e invariantes

Adicionar uma pasta válida e um manifest não exige alterar `main.py`. Adicionar um novo nome ao comando tampouco implica suporte automático a novos operadores. O contrato de retorno de `ModelPipeline.run()` é um dicionário de inferência; a CLI o ignora, usando as mensagens impressas e os arquivos como interface do usuário.
