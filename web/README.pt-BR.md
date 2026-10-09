# Research Explorer

## ESP32 pela USB (Windows / ESP-IDF 5.3.1)

1. Conecte o ESP32 por um cabo USB de dados. Feche o ESP-IDF Monitor e outros programas que usem a porta COM.
2. Abra **ESP32 · USB** e clique em **Verificar conexão**. Selecione a porta e o projeto TFLite Micro ou WASM/AOT. Os botões ficam bloqueados sem uma porta detectada; o servidor verifica novamente ao iniciar e usa o esptool para confirmar um chip ESP32 clássico antes de compilar/gravar. Um adaptador serial não é considerado automaticamente uma placa ESP32.
3. **Compilar e gravar** ativa o ESP-IDF, compila o projeto (`build-tflite` para TFLite, `build` para WASM), verifica novamente o chip e grava. **Reiniciar benchmark** executa o firmware já gravado, sem recompilar; selecione o projeto correspondente. O TFLite com checkpoints retoma o experimento atual; incremente `BENCHMARK_RUN_ID` e compile para começar da imagem 1. Firmwares sem persistência perdem os relatórios mantidos apenas na RAM ao reiniciar.
4. Acompanhe a compilação e o monitor serial pela página. Mantenha o servidor aberto e o USB conectado durante a gravação. **Fechar monitor** libera a porta sem reiniciar deliberadamente a placa; não interrompe a inferência. Esse botão fica bloqueado durante compilação/gravação. Encerrar o servidor termina seus processos filhos, portanto não o feche durante a gravação.
5. Com a importação automática habilitada, o site lê o IP nos logs e baixa os relatórios quando o firmware anuncia o servidor HTTP. Computador e placa ainda precisam se comunicar pela rede. Se a importação falhar, use **Importar do ESP32** para tentar novamente. Mantenha o monitor aberto para a importação automática funcionar.

Os caminhos `esp32.idf_root`, `esp32.python` e `esp32.tools` em `web/config.json` indicam a instalação ESP-IDF. Os valores fornecidos usam `C:/Espressif` e ESP-IDF 5.3.1. Não é preciso abrir o terminal ESP-IDF: o servidor executa `export.ps1` e `idf.py` no mesmo ambiente filho do PowerShell. A página controla os projetos existentes; modelo, Wi-Fi e pré-processamento continuam definidos nos arquivos de cada firmware. A inicialização/reset pela USB depende do circuito de reset automático da placa; se o esptool não conseguir identificá-la, a operação falha com logs. O mesmo servidor bloqueia execuções desktop e USB simultâneas.

## Executar modelos no desktop

Abra **Executar modelos** no menu lateral. Escolha Drowsiness ou MobileNetV2 Alpha 0.35, selecione WASM ou TFLite e clique em **Executar**. A página mostra os logs ao vivo (últimas 1.500 linhas), o status e links para os relatórios. Cada servidor permite uma execução por vez. Navegar ou recarregar a página não interrompe o processo; mantenha o servidor aberto. Encerrar o servidor termina seu processo ativo. O status fica na memória; os relatórios permanecem no disco.

WASM executa `main.py --model <modelo>` com `.venv-models`, incluindo extração, geração WAT/WASM e inferência. TFLite executa `run_tflite.py --model <modelo>` com `.venv-tflite`. Todo o conjunto de imagens configurado é utilizado. Os ambientes precisam ter as dependências instaladas. Para usar outros ambientes Python, adicione `"runner_python": {"wasm": "caminho/python.exe", "tflite": "caminho/python.exe"}` em `web/config.json` (caminhos relativos à raiz do repositório ou absolutos). Reinicie o servidor após alterar a configuração. Os relatórios usam pastas UTC separadas; os arquivos WASM em `generated/` são substituídos. Evite iniciar outro benchmark manualmente durante as medições.

## Importar resultados do ESP32

Clique em **Importar do ESP32**, selecione o firmware (TFLite Micro ou WebAssembly / AOT) e informe o IP da placa, por exemplo `192.168.0.18`. Aguarde o benchmark terminar; o computador precisa acessar a placa pela porta 80.

O servidor local baixa `/report` para `ESP32/cnn_tflite_esp32/reports/<horário UTC>/report.csv` ou `ESP32/cnn_webassembly_esp32/reports/<horário UTC>/report.csv`. No TFLite, também baixa `/metadata` como `metadata.json`. Cada importação cria uma nova pasta, como `20261006T234046384562Z`. Se o metadata falhar, o CSV é preservado e um aviso aparece. O site atualiza o índice e oferece um link para abrir o relatório importado. Abrir `/report` diretamente na placa continua usando a pasta de downloads do navegador. Reinicie o servidor local após atualizar o site.

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

Site local para navegar pela documentação e pelos relatórios de todo o repositório, incluindo os modelos e o ESP32. A interface usa HTML, CSS e TypeScript; um servidor pequeno em Python descobre e lê os arquivos.

## Iniciar

Requer **Python 3.10 ou superior**. Na raiz do repositório:

```powershell
python web/server/app.py
```

Abra **http://127.0.0.1:8000**. Mantenha o terminal aberto; use `Ctrl+C` para encerrar. Se `python` não estiver disponível no Windows, tente `py -3 web/server/app.py` ou ative seu ambiente Python. O ambiente do ESP-IDF também pode iniciar o servidor.

Não é necessário instalar as dependências de inferência nem o Node.js para consultar o site. O JavaScript compilado está incluído em `public/app.js`. Os dados são os arquivos existentes no disco; iniciar o site não executa o pipeline nem o firmware.

Se a porta estiver ocupada:

```powershell
python web/server/app.py --port 8001
```

Nesse caso, abra http://127.0.0.1:8001. O servidor atende somente no computador local.

## Navegação

- **EN / PT:** alterna o idioma de toda a interface, incluindo menus, filtros, métricas, datas e números. A preferência fica salva no navegador. Também seleciona o idioma da biblioteca e abre a tradução do documento atual, quando disponível. Conteúdos originais de relatórios e arquivos baixados permanecem intactos.
- **Visão geral:** projetos, contagens e relatórios modificados recentemente.
- **Relatórios:** arquivos agrupados por pasta, com busca por título ou caminho e filtro por projeto.
- **Documentação:** Markdown formatado, índice de seções, cópia de código e seleção de português, inglês ou ambos. O botão de idioma abre a versão correspondente, mesmo quando os nomes dos arquivos são diferentes.
- **Atualizar índice:** encontra novos arquivos e remove os que deixaram de existir. Para reler um arquivo alterado, use esse botão ou abra o arquivo novamente.
- **Baixar original:** salva o arquivo sem modificar seu conteúdo.

Links entre documentos indexados funcionam dentro do site. Referências a código e a outros arquivos fora da biblioteca ficam identificadas no texto, sem abrir esses arquivos. Imagens externas HTTPS são permitidas; imagens locais e diagramas Mermaid não têm um visualizador próprio nesta versão. Blocos Mermaid aparecem como código.

### Visualizações de relatórios

| Formato reconhecido | Apresentação |
|---|---|
| CSV do ESP32 | Acurácia, falhas, tempos médios, gráficos por amostra e tabela |
| Inferência binária do Python | Resultados, acurácia, inválidos e erros de processamento |
| ImageNet Top-K | Seleção de imagem, gráfico das cinco primeiras classes e tabela completa |
| Layout final de memória | Distribuição das regiões, endereços e tamanhos |
| Registros `op=...` de pesos e quantização | Campos extraídos em tabela |
| Outros TXT, JSON e LOG | Conteúdo original em painel de texto |

As tabelas permitem ordenar colunas, pesquisar valores e navegar em páginas de 50 linhas. Relatórios com `right` também permitem filtrar registros não corretos. O conteúdo original continua disponível abaixo da visualização.

No CSV, a acurácia usa registros com `ok=1` e `right` igual a `0` ou `1`. Tempos médios usam valores finitos e não negativos dos registros bem-sucedidos. Na inferência binária, inválidos e empates com `right=0` entram no denominador. Scores Top-K são saídas do modelo, não acurácia.

## Descoberta e configuração

Edite [`config.json`](config.json) para ajustar a porta, exclusões, formatos e limite de leitura. Reinicie o servidor após alterar a configuração.

- Todos os `.md` são indexados nas pastas permitidas, inclusive dentro de projetos com seu próprio `.git`.
- Relatórios são arquivos `.txt`, `.csv`, `.json` ou `.log` dentro de pastas chamadas `reports`, `report`, `relatorios` ou `relatórios`, ou com `report`/`relatório` no nome.
- `build`, `managed_components`, `.git`, `node_modules`, ambientes virtuais e outras pastas configuradas são ignorados. Links simbólicos não são percorridos.
- Arquivos `.pt-BR.md` são classificados como português; os demais Markdown, como inglês. A correspondência entre idiomas vem dos links `English` e `Português (Brasil)` no documento.
- Arquivos de até 16 MiB podem ser abertos por padrão. Arquivos maiores aparecem na lista, mas exigem aumentar `max_file_bytes` para leitura.

Os arquivos ficam em suas pastas originais. A busca da biblioteca consulta títulos e caminhos; a busca de uma tabela consulta os registros carregados. O site não busca relatórios diretamente no ESP32: salve o CSV recebido de `/report` no repositório e atualize o índice.

## Organização e desenvolvimento

```text
web/
  index.html          Página inicial
  config.json         Configuração do servidor e da descoberta
  src/app.ts          Navegação, leitor e visualizações
  styles/styles.css   Estilos e layout responsivo
  public/             JavaScript compilado e ícone
  server/app.py       Servidor HTTP e catálogo
  server/reports.py   Leitura dos formatos de relatório
  tests/              Testes de leitura e navegação
```

Para editar TypeScript, instale Node.js 22+ e execute:

```powershell
cd web
npm ci
npm run build
```

Inclua `public/app.js` atualizado junto com alterações em `src/app.ts`. `npm run watch` recompila durante a edição; mantenha o servidor Python em outro terminal e atualize a página para ver as mudanças. HTML e CSS são servidos diretamente.

### Verificações

Na raiz:

```powershell
python -m unittest discover -s web/tests -v
```

Com o servidor ativo na porta 8000, em `web/`:

```powershell
npm run test:ui
```

O teste usa Microsoft Edge instalado no Windows. Em outras máquinas, execute `npx playwright install chromium` antes do teste. Para outra porta, defina `EXPLORER_URL`. As capturas ficam em `web/test-results/`, ignorada pelo Git. Os testes conferem os relatórios de exemplo incluídos no repositório.

O servidor disponibiliza apenas os documentos e relatórios indexados e os recursos do site. Markdown passa por sanitização antes da exibição. Ele foi feito para consulta local, sem autenticação ou implantação pública.
