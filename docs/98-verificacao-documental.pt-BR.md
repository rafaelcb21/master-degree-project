[English](98-verificacao-documental.md) | [Português (Brasil)](98-verificacao-documental.pt-BR.md)

# 98 — Verificação da documentação

[Índice](README.pt-BR.md) · [Limitações e divergências](99-inconsistencias-e-limitacoes.pt-BR.md)

## Escopo da revisão

A análise começou em 28/09/2026 e a revisão final foi concluída em 29/09/2026. Foram lidos os módulos da aplicação e testes, os dois manifests, os três templates fonte e os relatórios existentes. Os dois TFLite foram abertos pelos bindings do projeto para obter shapes, tipos, escalas, zero points, contagens de operadores e tensores. Os RAWs foram inventariados por pasta e tamanho; o conteúdo de cor de um RAW não fornece metadados autodescritivos, portanto sua interpretação foi documentada conforme manifest e código.

## Critérios verificados

- Links Markdown locais, caminhos de fontes e arquivos citados como links.
- Fechamento de blocos de código e alinhamento das caixas dos novos diagramas textuais.
- Cobertura de cada arquivo Python relevante no inventário e nos capítulos de referência.
- Ordem dos 29 campos, offsets de quatro bytes e LP_SIZE de 116 bytes.
- Correspondência entre os manifests e os caminhos/templates documentados.
- Shapes, dtypes, quantização, contagem/tamanho dos RAWs e layout de memória dos dois pacotes.
- Distinção entre fontes, artefatos, comportamento executado e propostas de evolução.
- Preservação dos corpos dos 14 documentos anteriores no diretório `historico/`.
- Integridade dos arquivos não documentais, comparados por SHA-256 ao início da tarefa.

## Testes executados

```powershell
.venv-models/Scripts/python.exe -X utf8 -m unittest discover -s tests -v
```

Resultado: **7 testes, todos aprovados**. A suíte inclui o kernel QUANTIZE em WASM e os testes de contrato, caminhos, camada sintética, conversão BGR, interpretação INT8, ranking estável e classificação binária. O [capítulo 11](11-testes.pt-BR.md) explica o alcance exato de cada assertion.

Não foi necessário regenerar WAT/WASM nem executar novamente as 2000 imagens para esta tarefa de documentação. As métricas nos READMEs foram lidas dos relatórios presentes, e os metadados dos modelos foram inspecionados diretamente. Os testes criam seus próprios arquivos temporários quando necessário.

## Resultado e limites

Foram verificados **49 arquivos Markdown**, incluindo os READMEs e o histórico,
com **290 links locais válidos** e **52 diagramas textuais nos documentos atuais**.
Os 14 corpos históricos coincidem com os textos anteriores, desconsiderando
apenas a normalização de finais de linha e o aviso acrescentado antes de cada corpo.
A comparação por SHA-256 confirmou **2067 arquivos não documentais inalterados**.

Os capítulos atuais corrigem referências à arquitetura de modelo único e identificam os arquivos históricos/legados. O capítulo 99 registra divergências sem corrigi-las silenciosamente na implementação. Código funcional, manifests, TFLite, templates, RAWs e artefatos existentes foram preservados.

A verificação documental não demonstra equivalência matemática entre todos os kernels e TensorFlow Lite, nem valida os dados de treinamento. Também não transforma as propostas do capítulo 99 em funcionalidades existentes. A finalidade desta revisão é permitir que o leitor identifique precisamente o comportamento atual e seus limites.
