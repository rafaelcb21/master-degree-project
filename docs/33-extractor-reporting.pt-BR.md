[English](33-extractor-reporting.md) | [Português (Brasil)](33-extractor-reporting.pt-BR.md)

# 33 — Persistência dos relatórios

[Índice](README.pt-BR.md) · Fonte: [extractor/reporting.py](../extractor/reporting.py)

## Interface e responsabilidade

`save_report(path: Path,content: str)` executa duas ações: cria o pai com `mkdir(parents=True,exist_ok=True)` e escreve o conteúdo com `path.write_text(...,encoding="utf-8")`. Retorna None. O pipeline chama esse helper após cada formatter e após o adapter. O módulo não formata, calcula métricas ou decide qual pacote está em execução.

```text
dict de etapa ──► formatter específico ──► string
                                              │
package.reports_dir / nome ────────────────────┤
                                              ▼
                                         save_report
                                              │ mkdir pai
                                              ▼
                                      arquivo UTF-8
```

Entram caminho e texto produzidos por outros módulos. O helper garante a existência do diretório e escreve; sai o arquivo. O conteúdo e o diretório pertencem ao pacote/etapa; a política de persistência é comum. A extensão não é interpretada.

## Comportamento observável

Arquivo existente é substituído, não anexado. Não acrescenta newline, timestamp, cabeçalho, checksum ou metadados de execução. O conteúdo termina exatamente onde a string termina. Type hints não convertem string em Path; passar uma string diretamente causa AttributeError em `.parent`. O pipeline passa Path corretamente.

Não captura OSError nem implementa fallback. Falha de relatório interrompe a etapa e pode impedir geração/inferência posteriores, mesmo quando o cálculo que o produziu terminou. Não há escrita atômica, histórico, lock ou limpeza de relatórios antigos. `exist_ok=True` permite diretório já existente, mas não resolve um arquivo ocupando o lugar do diretório.

## Posição na arquitetura atual

Quem escolhe os nomes 02–12 e chama save_report é `ModelPipeline`, não a CLI. `reports_dir` vem de ModelPackage; não existe REPORTS_DIR global no config atual. A função não lê relatórios anteriores: eles são saídas de diagnóstico, não entradas para reconstruir o modelo. Uma execução completa pode recriá-los; uma interrompida pode deixar um conjunto parcialmente atualizado.

## Demais arquivos de inicialização

`extractor/__init__.py` contém somente uma docstring sobre ferramentas de extração. `pipeline/__init__.py` e `adapters/__init__.py` estão vazios. Nenhum deles registra classes, carrega modelos ou cria estado global adicional. Não há `inference/__init__.py` ou `tests/__init__.py` na árvore inspecionada. Essas observações evitam atribuir efeitos de inicialização inexistentes às importações.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python
from pathlib import Path
```

### `save_report` — assinatura

```python
def save_report(path: Path, content: str)
```

## Material técnico preservado

A explicação anterior está em [14-relatorios.md](historico/14-relatorios.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
