export type Language = 'pt-BR' | 'en';
export let language: Language = localStorage.getItem('explorer-ui-language') === 'en' ? 'en' : 'pt-BR';
export const locale = () => language === 'en' ? 'en-US' : 'pt-BR';
export function setLanguage(value: Language) {
  language = value;
  localStorage.setItem('explorer-ui-language', value);
}

// UI text only. Source documents, paths, report values and downloads stay intact.
const english: Record<string, string> = {
  'Pular para o conteúdo': 'Skip to content',
  'Navegação principal': 'Main navigation',
  'Abrir navegação': 'Open navigation',
  'Ambiente local': 'Local environment',
  'Atualizar índice': 'Refresh index',
  'Carregando a biblioteca do projeto…': 'Loading the project library…',
  'Documentação e resultados, em um só lugar.': 'Documentation and results, in one place.',
  'BIBLIOTECA DO PROJETO': 'PROJECT LIBRARY',
  'Visão geral': 'Overview', 'Relatórios': 'Reports', 'Documentação': 'Documentation',
  'PROJETOS': 'PROJECTS', 'Projeto & arquitetura': 'Project & architecture',
  'ESP32 · Host embarcado': 'ESP32 · Embedded host',
  'Um projeto.': 'One project.', 'Todas as descobertas.': 'Every discovery.',
  'Índice local atualizado': 'Local index updated',
  'Arquitetura, guias e histórico do projeto.': 'Architecture, guides and project history.',
  'Execução embarcada e medições do host.': 'Embedded execution and host measurements.',
  'Uso e manutenção desta biblioteca local.': 'Using and maintaining this local library.',
  'Documentação do modelo e relatórios do pipeline.': 'Model documentation and pipeline reports.',
  'EMBARCADO': 'EMBEDDED', 'MODELO': 'MODEL',
  'LABORATÓRIO / WEBASSEMBLY': 'LABORATORY / WEBASSEMBLY',
  'Do modelo ao dispositivo.': 'From model to device.',
  'Explore cada resultado.': 'Explore every result.',
  'Documentação, relatórios e medições do projeto.': 'Project documentation, reports and measurements.',
  'Conecte a arquitetura aos dados de cada execução.': 'Connect the architecture to the data from each run.',
  'Explorar relatórios': 'Explore reports', 'Ler documentação': 'Read documentation',
  'Projetos indexados': 'Indexed projects', 'Relatórios disponíveis': 'Available reports',
  'Documentos · PT / EN': 'Documents · PT / EN', 'Última leitura': 'Last scan',
  'EXPLORE O WORKSPACE': 'EXPLORE THE WORKSPACE',
  'Uma visão de cada projeto': 'A view of every project', 'RESULTADOS': 'RESULTS',
  'Relatórios recentes': 'Recent reports', 'Ver todos': 'View all',
  'Ainda não há relatórios. Atualize o índice depois de gerar os primeiros resultados.': 'No reports yet. Refresh the index after generating your first results.',
  'BASE DE CONHECIMENTO': 'KNOWLEDGE BASE', 'DADOS & MEDIÇÕES': 'DATA & MEASUREMENTS',
  'Da visão geral aos detalhes de implementação.': 'From the overview to implementation details.',
  'Abra um projeto e acompanhe seus resultados.': 'Open a project and explore its results.',
  'Buscar documento, assunto ou caminho…': 'Search documents, topics or paths…',
  'Buscar relatório ou caminho…': 'Search reports or paths…',
  'Buscar arquivos': 'Search files', 'Filtrar projeto': 'Filter project',
  'Todos os projetos': 'All projects', 'Idioma': 'Document language',
  'Português': 'Portuguese', 'Todos os idiomas': 'All languages',
  'Raiz do projeto': 'Project root', 'HISTÓRICO': 'HISTORY',
  'Nenhum arquivo encontrado': 'No files found',
  'Tente outro termo, idioma ou projeto. Novos arquivos aparecem ao atualizar o índice.': 'Try another search, language or project. Refresh the index to discover new files.',
  'Mínimo': 'Minimum', 'Máximo': 'Maximum',
  'Distribuição das regiões': 'Memory region distribution',
  'Proporção dos bytes por região, sem padding ou espaço livre.': 'Bytes per region, excluding padding and free space.',
  'Classes mais prováveis': 'Most likely classes',
  'Score do modelo; não representa uma medida de acurácia.': 'Model score; this is not a measure of accuracy.',
  'Filtrar os registros…': 'Filter records…', 'Filtrar registros': 'Filter records',
  'Somente erros': 'Errors only', 'Acerto': 'Correctness',
  '← Anterior': '← Previous', 'Próxima →': 'Next →',
  'Correto': 'Correct', 'Incorreto': 'Incorrect', 'Não avaliado': 'Not evaluated',
  'Nenhum registro corresponde ao filtro.': 'No records match the filter.',
  'Acurácia calculada sobre registros bem-sucedidos com': 'Accuracy is calculated from successful records with',
  'igual a 0 ou 1. Tempos médios consideram execuções bem-sucedidas.': 'equal to 0 or 1. Average times include successful runs.',
  'Acurácia calculada sobre as amostras com rótulo. Inválidos e empates permanecem nos registros, conforme o relatório original.': 'Accuracy is calculated from labeled samples. Invalid predictions and ties remain included, as in the original report.',
  'Registros do relatório': 'Report records', 'Clique em uma coluna para ordenar': 'Click a column to sort',
  'Este relatório está disponível em sua forma textual, com as seções originais preservadas.': 'This report is available as text, with its original sections preserved.',
  'Conteúdo original': 'Original content', 'Nesta página': 'On this page', 'NESTA PÁGINA': 'ON THIS PAGE',
  'Referência a arquivo fora da biblioteca de documentos e relatórios.': 'Reference to a file outside the document and report library.',
  'Copiar': 'Copy', 'Copiar bloco de código': 'Copy code block', 'Copiado!': 'Copied!',
  'Não foi possível copiar. Selecione o texto manualmente.': 'Could not copy. Select the text manually.',
  'DOCUMENTAÇÃO': 'DOCUMENTATION', 'RELATÓRIO': 'REPORT',
  '↓ Baixar original': '↓ Download original', 'DOCUMENTO HISTÓRICO': 'HISTORICAL DOCUMENT',
  'Abrindo arquivo…': 'Opening file…', 'Não foi possível abrir': 'Could not open file',
  'Voltar ao início': 'Back to overview', 'Biblioteca indisponível': 'Library unavailable',
  'Confira se o servidor está ativo e use “Atualizar índice” para tentar novamente.': 'Check that the server is running and use “Refresh index” to try again.',
  'Não foi possível carregar os dados.': 'Could not load data.',
  'Arquivo não encontrado no índice. Atualize a biblioteca.': 'File not found in the index. Refresh the library.',
  'Arquivo maior que o limite configurado em web/config.json.': 'File exceeds the limit configured in web/config.json.',
  'Arquivo maior que o limite de leitura.': 'File exceeds the read limit.',
  'Não foi possível ler o arquivo.': 'Could not read the file.',
  'Failed to fetch': 'Could not connect to the server.',
  'Registros': 'Records', 'Falhas': 'Failures', 'Acurácia': 'Accuracy',
  'Amostras avaliadas': 'Evaluated samples', 'Inferência média': 'Average inference',
  'Download médio': 'Average download', 'Inválidos / empates': 'Invalid / ties',
  'Erros de processamento': 'Processing errors', 'Imagens': 'Images',
  'Predições listadas': 'Listed predictions', 'Páginas WASM': 'WASM pages',
  'Fim da memória': 'Memory end', 'Tamanho de cada slot': 'Size of each slot',
  'Imagem': 'Image', 'Predição': 'Prediction', 'Rótulo': 'Label', 'Inválido': 'Invalid',
  'Quantizado': 'Quantized', 'Posição': 'Rank', 'Classe': 'Class', 'Índice': 'Index',
  'Região': 'Region', 'Fim': 'End', 'Seção': 'Section',
  'INFERÊNCIA WASM — binary-folders': 'WASM INFERENCE — binary-folders',
  'INFERÊNCIA WASM — ImageNet Top-K': 'WASM INFERENCE — ImageNet Top-K',
  'LAYOUT FINAL DE MEMORIA': 'FINAL MEMORY LAYOUT',
  'PESOS': 'WEIGHTS',
};

export function t(source: string): string {
  if (language !== 'en') return source;
  if (english[source]) return english[source];
  return source
    .replace(/^(\d+) relatórios$/, '$1 reports')
    .replace(/^(\d+) arquivos encontrados$/, '$1 files found')
    .replace(/^([\d.,]+) registros$/, '$1 records')
    .replace(/^Página (\d+) de (\d+)$/, 'Page $1 of $2')
    .replace(/^(Inferência|Download) por amostra$/, (_, name) => `${name === 'Inferência' ? 'Inference' : name} per sample`)
    .replace(/^(Inferência|Download): mínimo (.+) e máximo (.+)$/, (_, name, min, max) => `${name === 'Inferência' ? 'Inference' : name}: minimum ${min} and maximum ${max}`)
    .replace(/^← (.+)$/, (_, name) => `← ${english[name] ?? name}`);
}

const originals = new WeakMap<Node, Map<string, { source: string; rendered: string }>>();
function translated(node: Node, key: string, current: string) {
  let fields = originals.get(node);
  if (!fields) { fields = new Map(); originals.set(node, fields); }
  const saved = fields.get(key);
  const source = saved?.rendered === current ? saved.source : current;
  const rendered = source.replace(/\S[\s\S]*\S|\S/, text => t(text));
  fields.set(key, { source, rendered });
  return rendered;
}

/** Translate interface nodes after rendering without touching report data or Markdown. */
export function localize(root: HTMLElement = document.body) {
  document.documentElement.lang = language;
  const excluded = '#markdown, #toc-links, .raw-text, #rows, .file-info span, .page-heading p, .project-card code, #image-filter, .rank-row, .memory-legend';
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const parent = node.parentElement;
    if (!parent || parent.closest('script,style') || (parent.closest(excluded) && !parent.closest('.copy-code,.status'))) continue;
    node.textContent = translated(node, 'text', node.textContent ?? '');
  }
  root.querySelectorAll<HTMLElement>('[aria-label],[placeholder],[title]').forEach(node => {
    if (node.closest('#markdown') && !node.matches('.copy-code,.unavailable-link')) return;
    for (const attr of ['aria-label', 'placeholder', 'title']) {
      if (node.hasAttribute(attr)) node.setAttribute(attr, translated(node, attr, node.getAttribute(attr)!));
    }
  });
}
