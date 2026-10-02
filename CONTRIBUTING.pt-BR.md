# Contribuindo com a documentação

[English](CONTRIBUTING.md) | [Português (Brasil)](CONTRIBUTING.pt-BR.md)

## Atualize os dois idiomas juntos

A documentação autoral tem uma versão inglesa `nome.md` e uma versão em português brasileiro `nome.pt-BR.md` no mesmo diretório. O README principal é em inglês.

Ao alterar instruções ou comportamento documentado:

1. Atualize as duas versões na mesma mudança.
2. Inclua o seletor de idioma no início de cada página.
3. Mantenha os links internos no idioma do leitor, exceto o seletor de idioma.
4. Confira as âncoras após traduzir títulos; elas podem ser diferentes em cada idioma.
5. Preserve sintaxe dos comandos, caminhos, identificadores, constantes, equações, assinaturas de APIs e exemplos executáveis. Logs e mensagens reais podem continuar no idioma original; explique-os no texto.
6. Preserve avisos históricos e datas. Traduzir uma verificação anterior não significa executar novamente seus comandos.
7. Confira se os documentos locais vinculados existem e se os blocos de código estão fechados.

Exemplo para um documento chamado `HOST`:

```markdown
[English](HOST.md) | [Português (Brasil)](HOST.pt-BR.md)
```

Traduza todo o conteúdo explicativo, incluindo tabelas e legendas de diagramas, sem remover limitações ou substituir capítulos completos por resumos.

## Escopo

A convenção vale para a documentação autoral do repositório, incluindo pacotes de modelos, o host ESP32 independente e os capítulos arquivados em `docs/historico/`.

Não traduza nem altere documentação de dependências instaladas, ambientes virtuais, metadados Git ou arquivos gerados pelo build. Preserve código executável e artefatos gerados, salvo quando outra tarefa de implementação exigir mudanças.

Alguns nomes legados contêm palavras em português ou `ptBR`. Os nomes permanecem estáveis para preservar links existentes; o seletor de idioma identifica a página inglesa e sua correspondente em português.

