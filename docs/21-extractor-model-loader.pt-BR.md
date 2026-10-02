[English](21-extractor-model-loader.md) | [Português (Brasil)](21-extractor-model-loader.pt-BR.md)

# 21 — Carregamento do FlatBuffer TFLite

[Índice](README.pt-BR.md) · Fonte: [extractor/model_loader.py](../extractor/model_loader.py)

## Objetivo, entrada e saída

O módulo lê o binário original e devolve objetos de acesso ao schema TFLite. É chamado após discovery dos testes e antes de extrair metadados de entrada/saída. Não usa TensorFlow, não aloca tensores de um interpretador e não executa inferência TFLite.

`load_model(model_path)` lê todos os bytes com `Path.read_bytes`. Tenta `TFLModel.GetRootAsModel(buf,0)`; se não existir, tenta `TFLModel.Model.GetRootAsModel(buf,0)`. Essa dupla forma acomoda diferenças de exposição do binding Python. Se nenhuma existe, levanta `RuntimeError`. Retorna o objeto raiz do FlatBuffer; os acessores subsequentes consultam o buffer carregado.

`get_subgraph(model,index=0)` simplesmente retorna `model.Subgraphs(index)`. O pipeline sempre passa zero. Não agrega subgrafos, resolve chamadas entre subgrafos ou oferece seleção na CLI. Um arquivo com vários subgrafos não recebe suporte completo só porque o primeiro pode ser lido.

```text
model.toml: model.tflite
             │ ModelPackage.resolve
             ▼
          Path do arquivo
             │ read_bytes
             ▼
       GetRootAsModel(buf,0)
             │ objeto schema
             ▼
       Subgraphs(0) ──► grafo / tensores / opções
```

Entra o caminho específico do pacote. O loader cria uma visão estruturada dos bytes; saem model e subgraph para o extrator. O formato FlatBuffer é comum; operadores e buffers pertencem ao modelo. Não há alteração ou cópia permanente do TFLite em disco.

## Validações e erros

O pacote já exige arquivo não vazio, mas `load_model` também pode ser chamado diretamente. Erros de abertura propagam `OSError`; buffer inválido pode falhar no binding ou apenas em acessos posteriores. Não há verificação explícita de magic TFLite, versão do schema, compatibilidade de opcodes ou limites do índice do subgrafo. O método não retorna um relatório; o primeiro arquivo de relatório do pipeline é o grafo 02.

## Uso correto

Mantenha o objeto model e os dados derivados na mesma execução. Não confunda o objeto schema com um interpreter: ele não oferece `invoke()` neste fluxo. A validação de uma entrada/saída e de tipos vem do pipeline/runner, não deste módulo. O nome de arquivo `int8` é irrelevante para a leitura; consulte `tensor.Type()`.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from pathlib import Path
import tflite.Model as TFLModel
```

### `load_model` — assinatura

```python
def load_model(model_path)
```

### `get_subgraph` — assinatura

```python
def get_subgraph(model, index=0)
```

## Material técnico preservado

A explicação anterior está em [02-model-loading.md](historico/02-carregamento-modelo.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
