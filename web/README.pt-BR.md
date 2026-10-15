# Research Explorer

## Memória nos novos relatórios ESP32

Os CSVs com `memory_report_schema=1` exibem métricas de heap interno, PSRAM, SRAM estática e ocupação da aplicação na flash, além das funções e escopos de medição. Os mínimos são históricos desde o boot; os campos legados `heap_*` não são apresentados como SRAM interna. Veja a [documentação do coletor dos dois firmwares](../ESP32/common/README.pt-BR.md). É necessário gravar o firmware atualizado e executar uma nova rodada. Relatórios antigos continuam disponíveis sem valores inventados para campos ausentes.

## Metodologia experimental

Abra **Metodologia experimental** no menu lateral para consultar o [relatório de versões, compilação, medição, imagens, memória, portabilidade e aquecimento](../analysis/experimental-method/report.pt-BR.md). A página distingue as evidências atuais dos registros históricos e permite baixar o Markdown em **Baixar original**. Use **EN / PT** para alternar entre os relatórios completos em inglês e português. Os tamanhos e SHA-256 auditados ficam em [artifacts-report.json](../analysis/experimental-method/artifacts-report.json).

## Parâmetros de modelos TFLite

Relatórios gerados ficam salvos em `analysis/tflite-parameters/`. Ao trocar o select, a aplicação carrega o resultado salvo automaticamente e lembra a última seleção ao recarregar a página. Os relatórios de uploads aparecem no grupo **Enviados · relatórios salvos**, mesmo sem reenviar o arquivo. **Regerar relatório** atualiza a análise de um modelo do projeto. Se o conteúdo do modelo ou o analisador mudar, a aplicação solicita uma nova geração em vez de apresentar um relatório desatualizado. Os relatórios continuam disponíveis depois de reiniciar o servidor.

A tabela usa cabeçalho fixo, linhas alternadas, números alinhados, totais destacados e barras de participação na soma por camadas. Clique no número de uma camada para abrir suas contas.

Abra **Parâmetros TFLite** no menu lateral. Selecione um `.tflite` do projeto e clique em **Gerar relatório online**, ou escolha um arquivo no computador e clique em **Analisar arquivo enviado**. A análise roda no servidor local usando `.venv-models` (ou `runner_python.wasm`), com os pacotes `tflite` e `flatbuffers`, sem executar inferência. O limite é `max_file_bytes` de `web/config.json` (16 MiB por padrão); uploads são temporários.

A tela mostra pesos, bias e outros parâmetros por operação, nomes e formas dos tensores, tipos, bytes e as multiplicações linha a linha. O total global conta buffers compartilhados uma única vez; a soma por camadas inclui a reutilização. Constantes auxiliares, ativações e metadados de quantização ficam fora do total de parâmetros identificados. Pesos FP16 com DEQUANTIZE são rastreados até o tensor armazenado. Tensores esparsos contam pela forma lógica, com bytes reais separados. Operações desconhecidas e parâmetros dinâmicos recebem observações: o total identificado pode ser parcial. O TFLite convertido pode fundir camadas e não informa quais parâmetros eram treináveis no modelo original.

Baixe **HTML** para abrir o relatório completo fora do site (ou imprimir/salvar como PDF pelo navegador), **MD** para as contas em texto, **CSV** para a tabela detalhada ou **JSON** para todos os dados. A geração e o download não alteram os modelos.

Pelo terminal: `.venv-models/Scripts/python.exe analyze_tflite_parameters.py models/drowsiness/model_int8_esp32.tflite --output report.json`.

## Determinismo intra-ambiente

A tela abre no grupo com mais imagens divergentes. Cada barra representa uma imagem e permite selecionar máximo, média, mediana, P95 ou P99, em quantized ou scores. Clique na barra para ver os valores por execução, a classe predita, as estatísticas e uma explicação daquele caso. Barras laranja identificam troca de classe. As estatísticas agregadas ficam recolhidas ao final, como consulta complementar.

A análise também calcula máximo, média, mediana, P95 e P99 das diferenças absolutas por componente, usando todos os pares de execuções da mesma imagem. Inclui zeros e utiliza interpolação linear para os percentis. As faixas quantized são 0, 1, 2–5, 6–10 e >10. Exibe distribuições por componente/par e por imagem (seu máximo), tanto para todas as imagens quanto para as divergentes. Scores têm estatísticas separadas. Cada imagem informa se o label registrado mudou; transições para saída inválida aparecem como mudanças de decisão. O CSV contém essas métricas para todas as imagens. No Top-15, classes sem correspondência não são preenchidas com zero.

Abra **Análises → Determinismo intra-ambiente** para acessar a tela exclusiva. **Gerar / atualizar análise** atualiza as duas consolidações com os relatórios salvos no projeto e depois recalcula o determinismo, incluindo novas execuções parciais. Consulte o resumo por ambiente, filtre imagens e expanda os valores e IDs das execuções com diferenças. A navegação apenas consulta a análise salva.

Pelo terminal: `python analyze_determinism.py`. Arquivos: `analysis/determinism/report.md`, `images.csv` e `report.json`. O método compara os números registrados de forma exata dentro de modelo/formato/ambiente, inclui empates concluídos e exclui falhas ou observações ausentes/ambíguas. Exige pelo menos duas execuções distintas. No MobileNet, cobre somente o Top-15 registrado e sua ordem. A identidade das entradas/modelos/configurações não é verificada; igualdade observada não garante determinismo futuro.

## Análise consolidada

Abra **Análise consolidada** no menu lateral para consultar e filtrar a tabela salva. **Gerar / atualizar tabela** refaz `analysis/consolidated.csv` a partir das execuções desktop e ESP32; a navegação não refaz a consolidação. Baixe a tabela e o mapa das execuções na mesma página. Veja [as colunas e regras das fontes](../analysis/README.pt-BR.md). Pelo terminal: `python consolidate_reports.py` na raiz do projeto.

## ESP32 pelo terminal ESP-IDF

Compile, grave e acompanhe a placa pelo terminal ESP-IDF. Consulte os guias de [TFLite Micro](../ESP32/cnn_tflite_esp32/README.pt-BR.md) e [WebAssembly / AOT](../ESP32/cnn_webassembly_esp32/README.pt-BR.md) para os comandos de cada projeto. Depois da execução, use **Importar do ESP32** na web para consultar os relatórios.

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

## Relatórios representativos do ESP32

No menu **Análises → Relatórios representativos · ESP32**, use **Gerar / atualizar relatórios** para criar um CSV por modelo e formato WASM/TFLite. Para cada imagem, saídas iguais são mantidas e, se houver diferenças, é escolhido o vetor completo mais frequente. A tela mostra votos, variantes, exclusões e execução de origem, com downloads CSV/JSON. Empates e conflitos ficam sem predição utilizável. A análise consolidada do ESP32 usa estes novos relatórios; gerar a tabela também atualiza a seleção. Os tempos vêm da primeira execução com o resultado escolhido. Os originais são preservados para a análise de determinismo. Veja [método e arquivos](../analysis/README.pt-BR.md).

## Comparação entre ambientes e formatos

Há também três tabelas com downloads CSV/Markdown: **Estatísticas das diferenças quantizadas**, **Distribuição das diferenças quantizadas** e **Acertos por classe de referência**. As duas primeiras resumem Δq por componente; a terceira mostra acertos Geral, non_drowsy e drowsy para WASM/TFLite no ESP32/desktop, usando os rótulos de referência e as execuções escolhidas. O percentual principal inclui todas as imagens rotuladas; saídas inválidas e falhas não contam como acerto. A cobertura mostra o percentual complementar entre predições válidas. Os dados já salvos bastam para visualizar e baixar esses relatórios.

A seção **Resumo de concordância** mostra a tabela das seis comparações, com percentuais de concordância vetorial e de classe, contagens e downloads CSV/Markdown. O resumo é obtido dos dados já salvos, sem novas inferências. Expanda **Denominadores e cobertura** para conferir as classes válidas e as saídas excluídas de cada cálculo.

Para comparar os resultados, abra **Análises → Comparação entre ambientes e formatos**. Selecione as execuções do desktop (padrão: mais recentes) e use **Gerar / atualizar comparações**. As seis combinações mostram, por imagem, scores e classe lado a lado, diferenças quantizadas e em score, máximo, média, mediana, P95/P99 e contagens nas cinco faixas quantizadas. Há filtros por imagem, igualdade, troca de classe e ordem da maior diferença. Baixe um CSV por comparação, todas as imagens, resumo agregado ou JSON detalhado. A tela avisa quando a consolidação mudou. Veja [método e arquivos](../analysis/README.pt-BR.md).
