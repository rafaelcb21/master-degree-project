import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { language as uiLanguage, locale, setLanguage, t, localize } from './i18n';

type Entry = { path: string; name: string; title: string; kind: 'document' | 'report'; project: string; folder: string; language: string; historical: boolean; size: number; modified: string; counterpart: string | null };
type Row = Record<string, string | number | null>;
type Metric = { label: string; value: number; unit?: string };
type Report = { kind: string; metrics: Metric[]; columns: string[]; rows: Row[]; regions: Row[]; series: { label: string; unit: string; points: { x: number; y: number }[] }[] };
type Catalog = { entries: Entry[]; scannedAt: string; repository: string };
type FileData = { entry: Entry; content: string; report: Report | null };

const $ = <T extends HTMLElement = HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const e = (value: unknown) => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!));
const fmt = (value: number, max = 2) => value.toLocaleString(locale(), { maximumFractionDigits: max });
const bytes = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${fmt(n / 1024)} KiB` : `${fmt(n / 1048576)} MiB`;
const date = (s: string) => new Date(s).toLocaleString(locale(), { dateStyle: 'short', timeStyle: 'short' });
const paths: Record<string, string> = {
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  chart: '<path d="M4 3v17h17M9 15V9m5 6V5m5 10v-4"/>',
  book: '<path d="M12 5v16M3 4c4-1 6 0 9 2 3-2 5-3 9-2v15c-4-1-6 0-9 2-3-2-5-3-9-2Z"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/><rect x="10" y="10" width="4" height="4"/>',
  folder: '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  file: '<path d="M14 2H5v20h14V7Zm0 0v5h5M8 12h8m-8 4h8"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icon = (name: string) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? paths.file}</svg>`;
const route = (view: string, params: Record<string, string> = {}) => `#${view}${Object.keys(params).length ? '?' + new URLSearchParams(params) : ''}`;
const fileRoute = (path: string, anchor = '') => route('file', { path, ...(anchor ? { anchor } : {}) });
const human = (s: string) => s.replace(/^\d+[-_]/, '').replace(/[-_]/g, ' ');
const projectName = (id: string) => id === 'repository' ? 'Projeto & arquitetura' : id === 'web' ? 'Research Explorer' : id.startsWith('ESP32/') ? 'ESP32 · Host embarcado' : id.split('/').at(-1) === 'mobilenetv2_alpha035' ? 'MobileNetV2 · α 0.35' : id.split('/').at(-1) === 'drowsiness' ? 'Drowsiness' : human(id.split('/').at(-1)!);
const projectDescription = (id: string) => id === 'repository' ? 'Arquitetura, guias e histórico do projeto.' : id.startsWith('ESP32/') ? 'Execução embarcada e medições do host.' : id === 'web' ? 'Uso e manutenção desta biblioteca local.' : 'Documentação do modelo e relatórios do pipeline.';
let catalog: Catalog = { entries: [], scannedAt: '', repository: '' };
let generation = 0;
let toastTimer: number;

function toast(message: string) {
  $('#toast').textContent = t(message);
  $('#toast').classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => $('#toast').classList.remove('visible'), 4500);
}
async function api<T>(path: string): Promise<T> {
  const response = await fetch(path);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error ?? 'Não foi possível carregar os dados.');
  return body;
}
function projects() { return [...new Set(catalog.entries.map(x => x.project))].sort((a, b) => a === 'repository' ? -1 : b === 'repository' ? 1 : a.localeCompare(b)); }
function sidebar(view: string, selected = '') {
  const reports = catalog.entries.filter(x => x.kind === 'report');
  $('#sidebar').innerHTML = `<a class="brand" href="#overview"><img src="/favicon.svg" alt="" width="38" height="38"><div>Research<span>EXPLORER</span></div></a>
    <div class="sidebar-caption">BIBLIOTECA DO PROJETO</div>
    <nav>${[['overview', 'grid', 'Visão geral'], ['reports', 'chart', 'Relatórios'], ['documents', 'book', 'Documentação']].map(([id, glyph, title]) => `<a class="nav-item ${view === id ? 'active' : ''}" href="#${id}" ${view === id ? 'aria-current="page"' : ''}>${icon(glyph)}${title}${id === 'reports' ? `<span class="count">${reports.length}</span>` : ''}</a>`).join('')}</nav>
    <div class="sidebar-caption">PROJETOS <span>${projects().length}</span></div>
    <nav class="project-nav">${projects().map(id => `<a class="nav-item ${selected === id ? 'selected' : ''}" href="${route(id === 'repository' || id === 'web' ? 'documents' : 'reports', { project: id })}"><span class="project-dot ${id.startsWith('ESP32') ? 'amber' : ''}"></span>${e(projectName(id))}</a>`).join('')}</nav>
    <div class="sidebar-bottom"><div class="side-note">${icon('folder')}<span>Um projeto.<br><strong>Todas as descobertas.</strong></span></div><p>Python · WebAssembly · ESP32</p><div class="index-status"><i></i> Índice local atualizado</div></div>`;
}
function title(eyebrow: string, heading: string, sub: string, right = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${e(eyebrow)}</div><h1>${e(heading)}</h1><p>${e(t(sub))}</p></div>${right}</div>`;
}
function metricCards(metrics: Metric[]) {
  return `<div class="metrics">${metrics.map(m => `<div class="metric"><span>${e(m.label)}</span><strong>${fmt(m.value, 3)}<small>${e(m.unit ?? '')}</small></strong></div>`).join('')}</div>`;
}
function card(id: string) {
  const entries = catalog.entries.filter(x => x.project === id);
  const reports = entries.filter(x => x.kind === 'report').length;
  const docs = entries.length - reports;
  return `<article class="project-card"><div class="card-top"><span class="project-symbol ${id.startsWith('ESP32') ? 'warm' : ''}">${icon(id.startsWith('ESP32') ? 'chip' : id === 'repository' ? 'book' : 'folder')}</span><span class="tag">${id.startsWith('ESP32') ? 'EMBARCADO' : id.startsWith('models/') ? 'MODELO' : 'WORKSPACE'}</span></div><h3>${e(projectName(id))}</h3><p>${e(projectDescription(id))}</p><code>${e(id === 'repository' ? '/docs + /' : '/' + id)}</code><div class="card-actions"><a href="${route('reports', { project: id })}">${reports} relatórios ${icon('arrow')}</a><a href="${route('documents', { project: id })}">${docs} docs</a></div></article>`;
}
function fileRows(entries: Entry[]) {
  return entries.map(x => `<a class="file-row" href="${fileRoute(x.path)}"><span class="file-symbol ${x.kind === 'report' ? 'mint' : ''}">${icon(x.kind === 'report' ? 'chart' : 'file')}</span><div class="file-info"><strong>${e(x.title)}</strong><span>${e(x.path)}</span></div><span class="file-meta">${bytes(x.size)}<small>${date(x.modified)}</small></span>${icon('arrow')}</a>`).join('');
}
function overview() {
  const docs = catalog.entries.filter(x => x.kind === 'document');
  const reports = catalog.entries.filter(x => x.kind === 'report');
  $('#main').innerHTML = `<section class="hero"><div class="hero-copy"><div class="eyebrow"><span class="tiny-square"></span> LABORATÓRIO / WEBASSEMBLY</div><h1>Do modelo ao dispositivo.<br><em>Explore cada resultado.</em></h1><p>Documentação, relatórios e medições do projeto.<br>Conecte a arquitetura aos dados de cada execução.</p><div class="hero-actions"><a class="button primary" href="#reports">Explorar relatórios ${icon('arrow')}</a><a class="button ghost" href="#documents">Ler documentação ${icon('book')}</a></div></div><div class="hero-art" aria-hidden="true"><div class="orb"></div><div class="art-label">EXECUTION PATH <span>01 — 03</span></div><div class="stack stack-one"><span>01</span><strong>TFLite</strong><small>MODEL</small></div><div class="stack stack-two"><span>02</span><strong>WebAssembly</strong><small>RUNTIME</small></div><div class="stack stack-three"><span>03</span><strong>ESP32</strong><small>DEVICE</small><i></i></div><div class="art-foot">MODEL → WASM → MEASURE</div></div></section>
    <div class="overview-stats">${[[projects().length, 'Projetos indexados', 'folder'], [reports.length, 'Relatórios disponíveis', 'chart'], [docs.length, 'Documentos · PT / EN', 'book']].map(([n, label, glyph]) => `<div>${icon(String(glyph))}<strong>${n}</strong><span>${label}</span></div>`).join('')}<div class="scan-stat">${icon('clock')}<span>Última leitura<strong>${date(catalog.scannedAt)}</strong></span></div></div>
    <div class="section-heading"><div class="eyebrow">EXPLORE O WORKSPACE</div><h2>Uma visão de cada projeto</h2></div><div class="project-grid">${projects().map(card).join('')}</div>
    <div class="section-heading horizontal"><div><div class="eyebrow">RESULTADOS</div><h2>Relatórios recentes</h2></div><a class="text-link" href="#reports">Ver todos ${icon('arrow')}</a></div><div class="panel file-list">${fileRows([...reports].sort((a, b) => b.modified.localeCompare(a.modified)).slice(0, 5)) || '<div class="empty">Ainda não há relatórios. Atualize o índice depois de gerar os primeiros resultados.</div>'}</div>`;
}
function library(view: string, selected: string) {
  const isDocs = view === 'documents';
  let language = localStorage.getItem('explorer-language') ?? uiLanguage;
  $('#main').innerHTML = title(isDocs ? 'BASE DE CONHECIMENTO' : 'DADOS & MEDIÇÕES', isDocs ? 'Documentação' : 'Relatórios', selected ? projectName(selected) : isDocs ? 'Da visão geral aos detalhes de implementação.' : 'Abra um projeto e acompanhe seus resultados.') +
    (!isDocs && !selected ? `<div class="project-grid compact">${projects().filter(id => catalog.entries.some(x => x.project === id && x.kind === 'report')).map(card).join('')}</div>` : '') +
    `<div class="toolbar"><label class="search-field">${icon('search')}<input id="search" type="search" placeholder="${isDocs ? 'Buscar documento, assunto ou caminho…' : 'Buscar relatório ou caminho…'}" aria-label="Buscar arquivos"></label><select id="project-filter" aria-label="Filtrar projeto"><option value="">Todos os projetos</option>${projects().map(id => `<option value="${e(id)}" ${id === selected ? 'selected' : ''}>${e(projectName(id))}</option>`).join('')}</select>${isDocs ? `<select id="language-filter" aria-label="Idioma"><option value="pt-BR">Português</option><option value="en">English</option><option value="all">Todos os idiomas</option></select>` : ''}</div><div id="library-count" class="result-count"></div><div id="library-list"></div>`;
  if (isDocs) $<HTMLSelectElement>('#language-filter').value = language;
  function update() {
    const q = $<HTMLInputElement>('#search').value.toLocaleLowerCase();
    const filtered = catalog.entries.filter(x => x.kind === (isDocs ? 'document' : 'report') && (!selected || x.project === selected) && (!isDocs || language === 'all' || x.language === language) && `${x.title} ${x.path}`.toLocaleLowerCase().includes(q));
    $('#library-count').textContent = `${filtered.length} arquivos encontrados`;
    const groups = new Map<string, Entry[]>();
    filtered.forEach(x => { const group = x.folder; groups.set(group, [...(groups.get(group) ?? []), x]); });
    $('#library-list').innerHTML = [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([folder, items]) => `<details class="panel folder-group" ${folder.includes('historico') && !q ? '' : 'open'}><summary>${icon('folder')}<strong>${e(folder === '.' ? 'Raiz do projeto' : folder)}</strong><span class="pill">${items.length}</span>${folder.includes('historico') ? '<span class="tag">HISTÓRICO</span>' : ''}</summary><div class="file-list">${fileRows(items.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })))}</div></details>`).join('') || '<div class="empty panel"><h3>Nenhum arquivo encontrado</h3><p>Tente outro termo, idioma ou projeto. Novos arquivos aparecem ao atualizar o índice.</p></div>';
  }
  $('#search').addEventListener('input', update);
  $('#search').addEventListener('input', () => localize());
  $('#project-filter').addEventListener('change', event => location.hash = route(view, { project: (event.target as HTMLSelectElement).value }));
  if (isDocs) $('#language-filter').addEventListener('change', event => { language = (event.target as HTMLSelectElement).value; localStorage.setItem('explorer-language', language); update(); localize(); });
  update();
}
function lineChart(series: Report['series'][number]) {
  const values = series.points.map(p => p.y);
  const min = values.reduce((a, b) => Math.min(a, b), Infinity), max = values.reduce((a, b) => Math.max(a, b), 0);
  const ceiling = max || 1, end = series.points.at(-1)?.x ?? 1;
  const points = series.points.map(p => `${48 + (p.x - 1) / Math.max(1, end - 1) * 660},${170 - p.y / ceiling * 132}`).join(' ');
  return `<div class="panel chart-panel"><div class="chart-title"><h3>${e(series.label)} por amostra</h3><span class="pill">${e(series.unit)}</span></div><svg class="line-chart" viewBox="0 0 740 208" role="img" aria-label="${e(series.label)}: mínimo ${fmt(min)} e máximo ${fmt(max)} ${e(series.unit)}"><path d="M48 38H708M48 104H708M48 170H708" stroke="#e2e8e5" stroke-dasharray="4 4" fill="none"/><polyline points="${points}" fill="none" stroke="#128273" stroke-width="1.6" vector-effect="non-scaling-stroke"/><g fill="#768780" font-size="11"><text x="0" y="42">${fmt(max, 0)}</text><text x="8" y="174">0</text><text x="48" y="197">1</text><text x="666" y="197">${end}</text></g></svg><div class="chart-caption"><span>Mínimo <strong>${fmt(min, 3)} ms</strong></span><span>Máximo <strong>${fmt(max, 3)} ms</strong></span></div></div>`;
}
function memoryChart(regions: Row[]) {
  const total = regions.reduce((sum, r) => sum + Number(r.Bytes), 0);
  return `<div class="panel chart-panel"><div class="chart-title"><h3>Distribuição das regiões</h3><span class="pill">${bytes(total)}</span></div><p class="muted">Proporção dos bytes por região, sem padding ou espaço livre.</p><div class="memory-bar">${regions.map((r, i) => `<div class="region-color color-${i % 8}" style="flex:${Number(r.Bytes)}" title="${e(r.Região)}: ${bytes(Number(r.Bytes))}"></div>`).join('')}</div><div class="memory-legend">${regions.map((r, i) => `<div><i class="region-color color-${i % 8}"></i><span>${e(r.Região)}</span><strong>${bytes(Number(r.Bytes))}</strong></div>`).join('')}</div></div>`;
}
function topChart(rows: Row[]) {
  return `<div class="panel chart-panel"><div class="chart-title"><h3>Classes mais prováveis</h3><span class="pill">Top 5</span></div><p class="muted">Score do modelo; não representa uma medida de acurácia.</p>${rows.slice(0, 5).map(r => `<div class="rank-row"><span>${e(r.Classe)}</span><div><i style="width:${Math.max(0, Math.min(100, Number(r.Score) * 100))}%"></i></div><strong>${fmt(Number(r.Score) * 100)}%</strong></div>`).join('')}</div>`;
}
function table(report: Report) {
  let page = 0, sortKey = '', ascending = true;
  const perPage = 50;
  $('#table-host').innerHTML = `<div class="panel data-panel"><div class="table-toolbar"><label class="search-field">${icon('search')}<input id="row-search" type="search" placeholder="Filtrar os registros…" aria-label="Filtrar registros"></label>${report.columns.includes('right') ? '<label class="check"><input type="checkbox" id="only-errors"> Somente erros</label>' : ''}<span id="row-count" class="muted"></span></div><div class="table-scroll"><table class="data-table"><thead><tr>${report.columns.map(c => `<th scope="col"><button data-sort="${e(c)}">${e(c === 'right' ? 'Acerto' : c)} <span>↕</span></button></th>`).join('')}</tr></thead><tbody id="rows"></tbody></table></div><div class="pagination"><span id="page-count"></span><div><button class="button subtle" id="prev">← Anterior</button><button class="button subtle" id="next">Próxima →</button></div></div></div>`;
  function render() {
    const query = $<HTMLInputElement>('#row-search').value.toLowerCase();
    const image = document.querySelector<HTMLSelectElement>('#image-filter')?.value;
    const onlyErrors = document.querySelector<HTMLInputElement>('#only-errors')?.checked;
    let rows = report.rows.filter(r => (!query || Object.values(r).some(v => String(v ?? '').toLowerCase().includes(query))) && (!onlyErrors || String(r.right) !== '1') && (!image || r.Imagem === image));
    if (sortKey) rows = [...rows].sort((a, b) => { const av = a[sortKey] ?? '', bv = b[sortKey] ?? ''; const result = av !== '' && bv !== '' && Number.isFinite(Number(av)) && Number.isFinite(Number(bv)) ? Number(av) - Number(bv) : String(av).localeCompare(String(bv), undefined, { numeric: true }); return result * (ascending ? 1 : -1); });
    const pages = Math.max(1, Math.ceil(rows.length / perPage));
    page = Math.min(page, pages - 1);
    $('#rows').innerHTML = rows.slice(page * perPage, (page + 1) * perPage).map(row => `<tr>${report.columns.map(c => `<td>${c === 'right' ? `<span class="status ${String(row[c]) === '1' ? 'good' : 'bad'}">${String(row[c]) === '1' ? 'Correto' : String(row[c]) === '0' ? 'Incorreto' : 'Não avaliado'}</span>` : e(row[c] ?? '—')}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${report.columns.length}" class="empty">Nenhum registro corresponde ao filtro.</td></tr>`;
    $('#row-count').textContent = `${fmt(rows.length)} registros`;
    $('#page-count').textContent = `Página ${page + 1} de ${pages}`;
    $<HTMLButtonElement>('#prev').disabled = page === 0;
    $<HTMLButtonElement>('#next').disabled = page + 1 >= pages;
    if (report.kind === 'topk') $('#top-chart').innerHTML = topChart(report.rows.filter(r => r.Imagem === image));
    localize();
  }
  $('#row-search').addEventListener('input', () => { page = 0; render(); });
  document.querySelector('#only-errors')?.addEventListener('change', () => { page = 0; render(); });
  document.querySelector('#image-filter')?.addEventListener('change', () => { page = 0; render(); });
  $('#prev').onclick = () => { page--; render(); };
  $('#next').onclick = () => { page++; render(); };
  document.querySelectorAll<HTMLButtonElement>('[data-sort]').forEach(button => button.onclick = () => {
    const key = button.dataset.sort!;
    ascending = key === sortKey ? !ascending : true; sortKey = key;
    document.querySelectorAll('th').forEach(th => th.removeAttribute('aria-sort'));
    button.parentElement!.setAttribute('aria-sort', ascending ? 'ascending' : 'descending');
    render();
  });
  render();
}
function reportView(data: FileData) {
  const report = data.report!;
  const images = [...new Set(report.rows.map(r => String(r.Imagem ?? '')))];
  $('#detail-body').innerHTML = metricCards(report.metrics) +
    (report.kind === 'csv' && report.columns.includes('right') ? '<p class="metric-note">Acurácia calculada sobre registros bem-sucedidos com <code>right</code> igual a 0 ou 1. Tempos médios consideram execuções bem-sucedidas.</p>' : '') +
    (report.kind === 'inference' ? '<p class="metric-note">Acurácia calculada sobre as amostras com rótulo. Inválidos e empates permanecem nos registros, conforme o relatório original.</p>' : '') +
    (report.regions.length ? memoryChart(report.regions) : '') +
    `<div class="charts">${report.series.map(lineChart).join('')}</div>` +
    (report.kind === 'topk' ? `<div class="toolbar"><label for="image-filter">Imagem</label><select id="image-filter">${images.map(name => `<option>${e(name)}</option>`).join('')}</select></div><div id="top-chart"></div>` : '') +
    (report.rows.length ? '<div class="section-heading horizontal"><h2>Registros do relatório</h2><span class="muted">Clique em uma coluna para ordenar</span></div><div id="table-host"></div>' : '<div class="notice">Este relatório está disponível em sua forma textual, com as seções originais preservadas.</div>') +
    `<details class="panel raw-panel" ${report.rows.length ? '' : 'open'}><summary>${icon('file')} Conteúdo original <span class="muted">${bytes(data.entry.size)}</span></summary><pre class="raw-text">${e(data.content)}</pre></details>`;
  if (report.rows.length) table(report);
}
async function markdownView(data: FileData, anchor: string) {
  const token = generation;
  $('#detail-body').innerHTML = '<div class="reader-layout"><article class="markdown panel" id="markdown"></article><aside class="toc" aria-label="Nesta página"><span class="eyebrow">NESTA PÁGINA</span><nav id="toc-links"></nav></aside></div>';
  const html = await marked.parse(data.content);
  if (token !== generation) return;
  const article = $('#markdown');
  article.innerHTML = DOMPurify.sanitize(html, { FORBID_TAGS: ['style', 'form', 'input', 'button'], FORBID_ATTR: ['style'] });
  const counts = new Map<string, number>();
  const headings = [...article.querySelectorAll<HTMLHeadingElement>('h1,h2,h3,h4,h5,h6')];
  headings.forEach(h => {
    const base = (h.textContent ?? '').toLowerCase().replace(/[^\p{L}\p{N}_\-\s]/gu, '').replace(/ /g, '-');
    const n = counts.get(base) ?? 0; counts.set(base, n + 1); h.id = base + (n ? `-${n}` : '');
  });
  $('#toc-links').innerHTML = headings.filter(h => ['H1', 'H2', 'H3'].includes(h.tagName)).map(h => `<a class="level-${h.tagName}" href="${fileRoute(data.entry.path, h.id)}">${e(h.textContent)}</a>`).join('');
  article.querySelectorAll<HTMLAnchorElement>('a[href]').forEach(a => {
    const href = a.getAttribute('href')!;
    if (/^(https?:|mailto:)/i.test(href)) { a.target = '_blank'; a.rel = 'noopener noreferrer'; return; }
    try {
      const url = new URL(href, 'http://workspace/' + data.entry.path);
      const path = decodeURIComponent(url.pathname).slice(1);
      const target = catalog.entries.find(x => x.path === path);
      if (target) a.href = fileRoute(target.path, decodeURIComponent(url.hash.slice(1)));
      else {
        a.removeAttribute('href'); a.classList.add('unavailable-link'); a.title = 'Referência a arquivo fora da biblioteca de documentos e relatórios.';
      }
    } catch { a.removeAttribute('href'); }
  });
  article.querySelectorAll('pre').forEach(pre => {
    const text = pre.textContent ?? '';
    const button = document.createElement('button'); button.className = 'copy-code'; button.textContent = t('Copiar'); button.setAttribute('aria-label', t('Copiar bloco de código'));
    button.onclick = () => navigator.clipboard.writeText(text).then(() => { button.textContent = t('Copiado!'); setTimeout(() => button.textContent = t('Copiar'), 1800); }).catch(() => toast('Não foi possível copiar. Selecione o texto manualmente.'));
    pre.append(button);
  });
  if (anchor) document.getElementById(anchor)?.scrollIntoView({ block: 'start' });
}
async function openFile(path: string, anchor: string, token: number) {
  const data = await api<FileData>('/api/file?' + new URLSearchParams({ path }));
  if (token !== generation) return;
  const item = data.entry;
  const docs = item.kind === 'document';
  sidebar(docs ? 'documents' : 'reports', item.project);
  $('#page-label').textContent = docs ? 'Documentação' : 'Relatórios';
  $('#main').innerHTML = `<a class="back-link" href="${route(docs ? 'documents' : 'reports', { project: item.project })}">← ${e(projectName(item.project))}</a>` +
    title(docs ? 'DOCUMENTAÇÃO' : 'RELATÓRIO', item.title, item.path, `<div class="detail-actions">${item.counterpart && catalog.entries.some(x => x.path === item.counterpart) ? `<a class="button subtle" href="${fileRoute(item.counterpart)}">${item.language === 'pt-BR' ? 'Read in English' : 'Ler em português'}</a>` : ''}<a class="button subtle" href="/api/file?${new URLSearchParams({ path, download: '1' })}">↓ Baixar original</a></div>`) +
    `<div class="file-details"><span>${icon('clock')} ${date(item.modified)}</span><span>${bytes(item.size)}</span>${item.historical ? '<span class="tag">DOCUMENTO HISTÓRICO</span>' : ''}</div><div id="detail-body"></div>`;
  if (docs) await markdownView(data, anchor); else reportView(data);
}
async function render() {
  const token = ++generation;
  const [rawView, query = ''] = location.hash.slice(1).split('?');
  const view = rawView || 'overview';
  const params = new URLSearchParams(query), project = params.get('project') ?? '';
  document.body.classList.remove('menu-open'); $('#menu').setAttribute('aria-expanded', 'false');
  sidebar(view, project);
  $('#page-label').textContent = view === 'reports' ? 'Relatórios' : view === 'documents' ? 'Documentação' : 'Visão geral';
  window.scrollTo(0, 0);
  try {
    if (view === 'file') { $('#main').innerHTML = `<div class="loading">${t('Abrindo arquivo…')}</div>`; localize(); await openFile(params.get('path') ?? '', params.get('anchor') ?? '', token); }
    else if (view === 'reports' || view === 'documents') library(view, project);
    else overview();
  } catch (error) {
    if (token === generation) $('#main').innerHTML = `<div class="empty panel"><h2>Não foi possível abrir</h2><p>${e((error as Error).message)}</p><a class="button primary" href="#overview">Voltar ao início</a></div>`;
  }
  localize();
}
async function refresh() {
  const button = $<HTMLButtonElement>('#refresh'); button.disabled = true;
  try { catalog = await api<Catalog>('/api/index'); await render(); }
  catch (error) { $('#main').innerHTML = `<div class="empty panel"><h2>Biblioteca indisponível</h2><p>${e((error as Error).message)}</p><p>Confira se o servidor está ativo e use “Atualizar índice” para tentar novamente.</p></div>`; }
  finally { button.disabled = false; localize(); }
}
function languageButton() {
  $('#ui-language').textContent = uiLanguage === 'pt-BR' ? 'EN' : 'PT';
  $('#ui-language').setAttribute('aria-label', uiLanguage === 'pt-BR' ? 'Switch site to English' : 'Mudar site para português');
  $('#ui-language').setAttribute('title', uiLanguage === 'pt-BR' ? 'English' : 'Português');
}
$('#ui-language').onclick = () => {
  setLanguage(uiLanguage === 'pt-BR' ? 'en' : 'pt-BR');
  localStorage.setItem('explorer-language', uiLanguage);
  languageButton();
  const params = new URLSearchParams(location.hash.split('?')[1] ?? '');
  const current = catalog.entries.find(entry => entry.path === params.get('path'));
  if (current?.kind === 'document' && current.language !== uiLanguage && current.counterpart && catalog.entries.some(entry => entry.path === current.counterpart)) {
    location.hash = fileRoute(current.counterpart);
  } else void render();
  localize();
};
languageButton();
localize();
$('#refresh').onclick = () => void refresh();
$('.skip-link').onclick = event => { event.preventDefault(); $('#main').focus(); $('#main').scrollIntoView(); };
$('#menu').onclick = () => { const open = document.body.classList.toggle('menu-open'); $('#menu').setAttribute('aria-expanded', String(open)); };
window.addEventListener('hashchange', () => void render());
window.addEventListener('keydown', event => { if (event.key === 'Escape') { document.body.classList.remove('menu-open'); $('#menu').setAttribute('aria-expanded', 'false'); } });
void refresh();
