import { language } from './i18n';

type Result = {exists: boolean; generated_at: string; total: number; matched: number; execution_count: number;
  options: Record<string, string[]>; columns: string[]; rows: Record<string, unknown>[];
  execution_labels: Record<string, string>;
  warnings: string[]; page: number; pages: number};
const escape = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]!));

export async function consolidationView(active: () => boolean, mobilenet = false) {
  const text = (pt: string, en: string) => language === 'en' ? en : pt;
  const endpoint = mobilenet ? '/api/mobilenet-consolidation' : '/api/consolidation';
  const filename = mobilenet ? 'mobilenet_top15.csv' : 'consolidated.csv';
  const title = mobilenet ? 'MobileNetV2 · Top-15' : text('Análise consolidada', 'Consolidated analysis');
  const main = document.querySelector<HTMLElement>('#main')!;
  document.querySelector('#page-label')!.textContent = title;
  main.innerHTML = `<section class="panel execution-panel"><nav class="hero-actions" aria-label="${text('Tabelas', 'Tables')}"><a class="button ${mobilenet ? 'subtle' : 'primary'}" href="#analysis">Drowsiness</a><a class="button ${mobilenet ? 'primary' : 'subtle'}" href="#analysis-mobilenet">MobileNetV2 · Top-15</a></nav><h1>${title}</h1>
    <p>${mobilenet ? text('Uma linha por resultado do Top-15, na ordem do relatório. Selecione uma execução para ver suas 15 classes. O mapa identifica o formato e a pasta de origem.', 'One row per Top-15 result, in report order. Select an execution to see its 15 classes. The map identifies its runtime and source folder.') : text('Compare as saídas por modelo, execução e ambiente. Cada pasta representa uma execução independente.', 'Compare outputs by model, execution and environment. Each folder represents an independent execution.')}</p>
    <div class="hero-actions"><button class="button primary" id="consolidate">${text('Gerar / atualizar tabela', 'Generate / update table')}</button>
      <a class="button subtle" href="${endpoint}/download">${text('Baixar CSV', 'Download CSV')}</a>
      <a class="button subtle" href="${endpoint}/download?file=${mobilenet ? 'mobilenet_executions.csv' : 'executions.csv'}">${text('Mapa de execuções', 'Execution map')}</a></div>
    <p>${text('A navegação usa o arquivo salvo. O botão acima refaz somente esta tabela.', 'Navigation uses the saved file. The button above rebuilds only this table.')}</p>
    ${mobilenet ? '' : `<p>${text('inference_ms = 0 no desktop significa tempo não utilizado. prediction_usable exclui falhas, saídas inválidas conhecidas e imagens ignoradas; invalid vazio significa desconhecido.', 'Desktop inference_ms = 0 means timing is not used. prediction_usable excludes failures, known invalid outputs and skipped images; blank invalid means unknown.')}</p>`}
    <p id="consolidation-status" role="status"></p></section>
    <section class="panel execution-panel"><div class="toolbar consolidation-filters" id="consolidation-filters"></div>
    <p id="consolidation-count"></p><div class="consolidation-table" id="consolidation-table"></div>
    <div class="hero-actions"><button class="button subtle" id="consolidation-prev">${text('Anterior', 'Previous')}</button><span id="consolidation-page"></span><button class="button subtle" id="consolidation-next">${text('Próxima', 'Next')}</button></div>
    <details><summary>${text('Observações das fontes', 'Source notes')}</summary><ul id="consolidation-warnings"></ul></details></section>`;
  const get = <T extends HTMLElement = HTMLElement>(id: string) => main.querySelector<T>(`#${id}`)!;
  const params = new URLSearchParams();
  let serial = 0, page = 1, busy = false;
  function draw(data: Result) {
    if (!data.exists) {
      get('consolidation-status').textContent = text('Ainda não há tabela salva. Clique em Gerar / atualizar tabela.', 'No saved table yet. Click Generate / update table.');
      get<HTMLButtonElement>('consolidation-prev').disabled = true;
      get<HTMLButtonElement>('consolidation-next').disabled = true;
      return;
    }
    page = data.page;
    get('consolidation-status').textContent = `${text('Arquivo', 'File')}: analysis/${filename} · ${text('Atualizado em', 'Updated')} ${new Date(data.generated_at).toLocaleString()} · ${data.execution_count} ${text('execuções', 'executions')}`;
    if (!get('consolidation-filters').children.length) {
      get('consolidation-filters').innerHTML = Object.entries(data.options).map(([key, values]) => `<label>${escape(key)}<select data-filter="${key}"><option value="">${text('Todos', 'All')}</option>${values.map(v => `<option value="${escape(v)}">${escape(mobilenet && key === 'execution' ? data.execution_labels[v] : v)}</option>`).join('')}</select></label>`).join('') +
        `<label>${mobilenet ? text('Classe', 'Class') : text('Imagem', 'Image')}<input data-filter="search" placeholder="${mobilenet ? '[404] airliner' : 'A0001.raw'}"></label>` + (mobilenet ? '' : `<label>${text('Predições', 'Predictions')}<select data-filter="usable"><option value="">${text('Todas', 'All')}</option><option value="1">${text('Somente predições utilizáveis', 'Usable predictions only')}</option><option value="0">${text('Somente erros (não utilizáveis)', 'Errors only (unusable)')}</option></select></label>`);
      get('consolidation-filters').querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-filter]').forEach(input => {
        input.onchange = () => {params.set(input.dataset.filter!, input instanceof HTMLInputElement && input.type === 'checkbox' ? (input.checked ? '1' : '') : input.value); params.set('page', '1'); void load();};
      });
    }
    get('consolidation-count').textContent = `${data.matched} / ${data.total} ${text('linhas', 'rows')}`;
    const cell = (value: unknown) => {
      const content = escape(Array.isArray(value) ? JSON.stringify(value) : value);
      return content.length > 100 ? `<details><summary>${text('Ver valores', 'View values')}</summary><div class="consolidation-values">${content}</div></details>` : content;
    };
    const sorted = params.get('sort') === 'name_image';
    const descending = sorted && params.get('direction') === 'desc';
    const header = (column: string) => column === 'name_image'
      ? `<th aria-sort="${sorted ? (descending ? 'descending' : 'ascending') : 'none'}">name_image <button id="sort-image" class="sort-image" type="button" aria-label="${text('Ordenar imagens', 'Sort images')} ${descending || !sorted ? 'A–Z' : 'Z–A'}">${sorted ? (descending ? 'Z–A ↓' : 'A–Z ↑') : 'A–Z ↕'}</button></th>`
      : `<th>${escape(column)}</th>`;
    get('consolidation-table').innerHTML = `<table class="data-table"><thead><tr>${data.columns.map(header).join('')}</tr></thead><tbody>${data.rows.map(r => `<tr class="${r.prediction_usable === 0 ? 'consolidation-failed' : ''}">${data.columns.map(c => `<td>${cell(r[c])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    if (!mobilenet) get('sort-image').onclick = () => {
      if (busy) return;
      params.set('sort', 'name_image');
      params.set('direction', sorted && !descending ? 'desc' : 'asc');
      params.set('page', '1');
      void load();
    };
    get('consolidation-page').textContent = `${data.page} / ${data.pages}`;
    get<HTMLButtonElement>('consolidation-prev').disabled = page <= 1;
    get<HTMLButtonElement>('consolidation-next').disabled = page >= data.pages;
    get('consolidation-warnings').innerHTML = data.warnings.map(w => `<li>${escape(w)}</li>`).join('');
  }
  async function load(rebuild = false) {
    if (busy) return;
    const request = ++serial;
    if (rebuild) {busy = true; get<HTMLButtonElement>('consolidate').disabled = true; get('consolidation-status').textContent = text('Consolidando relatórios…', 'Consolidating reports…');}
    try {
      const response = await fetch(`${endpoint}${rebuild ? '' : '?' + params}`, rebuild ? {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'} : undefined);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (active() && serial === request) {
        if (rebuild) {Array.from(params.keys()).forEach(key => params.delete(key)); get('consolidation-filters').innerHTML = '';}
        draw(data);
      }
    } catch (error) {
      if (active()) get('consolidation-status').textContent = `${text('Não foi possível carregar a tabela', 'Could not load the table')}: ${String(error)}`;
    } finally {busy = false; if (active()) get<HTMLButtonElement>('consolidate').disabled = false;}
  }
  get('consolidate').onclick = () => void load(true);
  get('consolidation-prev').onclick = () => {params.set('page', String(page - 1)); void load();};
  get('consolidation-next').onclick = () => {params.set('page', String(page + 1)); void load();};
  await load();
}
