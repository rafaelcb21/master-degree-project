[English](20-extractor-config.md) | [Português (Brasil)](20-extractor-config.pt-BR.md)

# 20 — Constantes compartilhadas do extrator

[Índice](README.pt-BR.md) · Fonte: [extractor/config.py](../extractor/config.py)

## Responsabilidade e posição no pipeline

O módulo contém apenas `BATCH=1`, `ALIGN=16` e `KERNEL_BASE_HINT=2048`. Não recebe parâmetros, não tem funções e não escreve arquivos. `ModelPipeline` importa essas constantes e as passa explicitamente aos cálculos de memória. Não há mais caminhos de modelo, template ou relatório nesse arquivo.

| Constante | Consumidor | Efeito real |
|---|---|---|
| BATCH | `calculate_slot_bytes` → `tensor_numel` | Substitui dimensões negativas pelo valor 1 na contagem; não implementa batching de imagens |
| ALIGN | Layout de blobs, slots e parâmetros | Alinha bases/tamanhos em múltiplos de 16 |
| KERNEL_BASE_HINT | `calculate_parameter_layout` | Inicia a região WEIGHTS em `align_up(2048,16)` |

```text
config.py                         model.toml
   │ constantes compartilhadas       │ escolhas por pacote
   └───────────────┬──────────────────┘
                   ▼
              ModelPipeline
                   │
                   ├── memory: ALIGN / base de pesos / BATCH
                   └── slots: num_slots do manifest
```

Entram constantes e configuração do pacote; o pipeline encaminha cada valor ao módulo responsável. Saem decisões de layout. As constantes são genéricas do runtime atual; número de slots é lido do modelo, mas validado como 3. Alterar BATCH não supera a validação de entrada batch 1 em `ModelPipeline`.

## Invariantes e armadilhas

`align_up` em `memory.py` usa máscara de bits, exigindo alinhamento positivo e potência de dois para a fórmula funcionar como pretendido. Não existe validação dessa condição no módulo de configuração. O espaço abaixo de 2048 reserva as flags usadas pelo template, mas não tem um allocator independente. Reduzir essa base pode sobrepor áreas de controle. A constante é chamada HINT, porém o código não procura outro endereço: apenas a alinha.

## Migração documental

Textos antigos sobre `MODEL_PATH`, `WAT_TEMPLATE_PATH`, `OUT_WAT_PATH`, `REPORTS_DIR` e `NUM_SLOTS` como globais descrevem a arquitetura anterior. Agora os caminhos vêm de `ModelPackage`, `ModelConfig` e `model.toml`. Este módulo não depende de `Path`, de TOML nem do pacote.

## Dependências e assinaturas verificadas

As assinaturas abaixo foram extraídas da AST do arquivo atual. Os argumentos keyword-only aparecem após `*`. O comportamento está descrito nas seções anteriores; anotações de tipo não substituem validações.

```python

```

## Material técnico preservado

A explicação anterior está em [01-configuration.md](historico/01-configuracao.pt-BR.md). Ela conserva exemplos e derivações úteis, mas não é a referência para caminhos, CLI e variantes atuais. Em divergências, use este capítulo e o [registro de limitações](99-inconsistencias-e-limitacoes.pt-BR.md).
