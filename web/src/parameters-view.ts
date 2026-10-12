import { language, locale } from './i18n';

type Tensor = { id: number; name: string; shape: number[]; dtype: string; count: number; storedBytes: number; role: string; calculation: string; shared?: boolean; sparse: boolean };
type Layer = { subgraph: number; subgraphName: string; index: number; operator: string; weights: number; bias: number; other: number; total: number; parameters: Tensor[]; constants: Tensor[]; notes: string[]; calculation: string };
type Report = { name: string; savedId: string; generatedAt: string; fileBytes: number; layers: Layer[]; totals: { weights: number; bias: number; other: number; total: number; layerSum: number; parameterBytes: number; auxiliaryElements: number }; method: string; warnings: string[] };
const e = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]!));
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.querySelector<T>(s)!;

export async function parametersView(current: () => boolean) {
  const en = language === 'en';
  const label = en ? 'TFLite parameters' : 'Parâmetros TFLite';
  const n = (v: number) => v.toLocaleString(locale());
  const roles: Record<string, string> = en ? { weights: 'Weights', bias: 'Bias', other: 'Other parameters', auxiliary: 'Auxiliary constants' } : { weights: 'Pesos', bias: 'Bias', other: 'Outros parâmetros', auxiliary: 'Constantes auxiliares' };
  $('#page-label').textContent = label;
  $('#main').innerHTML = `<div class="page-heading"><div><div class="eyebrow">TENSORFLOW LITE</div><h1>${label}</h1><p>${en ? 'Inspect each layer, follow the calculations and download the report.' : 'Veja cada camada, acompanhe as contas e baixe o relatório.'}</p></div></div>
    <section class="panel parameter-panel"><form id="parameters-form">
    <div class="toolbar"><label>${en ? 'Model / saved report' : 'Modelo / relatório salvo'}<select id="parameters-model"><option value="">${en ? 'Loading…' : 'Carregando…'}</option></select></label><button class="button primary" id="parameters-run" disabled>${en ? 'Generate report online' : 'Gerar relatório online'}</button></div>
    <div class="toolbar"><label>${en ? 'Or upload a .tflite file' : 'Ou envie um arquivo .tflite'}<input id="parameters-file" type="file" accept=".tflite"></label><button type="button" class="button ghost" id="parameters-upload" disabled>${en ? 'Analyze uploaded file' : 'Analisar arquivo enviado'}</button></div>
    <p id="parameters-limit" class="muted"></p><p class="muted">${en ? 'Saved reports appear automatically when you select a model. Uploaded model files are temporary; their reports remain available.' : 'Relatórios salvos aparecem automaticamente ao selecionar um modelo. Os arquivos enviados são temporários; seus relatórios continuam disponíveis.'}</p>
    </form><div id="parameters-status" role="status" aria-live="polite"></div><div id="parameters-error" role="alert"></div></section><div id="parameters-result"></div>`;
  let report: Report | null = null, busy = false, maxBytes = 0, selectionVersion = 0;
  const model = $<HTMLSelectElement>('#parameters-model');
  const file = $<HTMLInputElement>('#parameters-file');
  const update = () => {
    const button = $<HTMLButtonElement>('#parameters-run');
    button.disabled = busy || !model.value || model.value.startsWith('saved:');
    button.textContent = model.value.startsWith('saved:') ? (en ? 'Saved report' : 'Relatório salvo') : report ? (en ? 'Regenerate report' : 'Regerar relatório') : (en ? 'Generate report online' : 'Gerar relatório online');
    $<HTMLButtonElement>('#parameters-upload').disabled = busy || !file.files?.length || !maxBytes;
    model.disabled = file.disabled = busy;
  };
  const tensorLines = (tensor: Tensor) => `<div class="parameter-tensor"><strong>${e(roles[tensor.role])}</strong> · <code>${e(tensor.name || `tensor ${tensor.id}`)}</code><br><span>${e(tensor.dtype)} · [${e(tensor.shape.join(', '))}] · ${n(tensor.storedBytes)} bytes${tensor.shared ? ` · ${en ? 'shared' : 'compartilhado'}` : ''}${tensor.sparse ? ` · ${en ? 'sparse' : 'esparso'}` : ''}</span><pre>${e(tensor.calculation)}</pre></div>`;
  const reportHTML = (data: Report) => `<section class="panel parameter-panel"><h2>${e(data.name)}</h2><p>${e(new Date(data.generatedAt).toLocaleString(locale()))} · ${n(data.fileBytes)} bytes</p>
    <div class="metrics">${[[en ? 'Unique parameters' : 'Parâmetros únicos', data.totals.total], [roles.weights, data.totals.weights], [roles.bias, data.totals.bias], [roles.other, data.totals.other]].map(([title, value]) => `<div class="metric"><span>${e(title)}</span><strong>${n(Number(value))}</strong></div>`).join('')}</div>
    <p>${e(data.method)}</p><p>${en ? 'Sum across layers (including reuse)' : 'Soma por camadas (incluindo reutilização)'}: <strong>${n(data.totals.layerSum)}</strong> · ${en ? 'Stored parameter bytes' : 'Bytes dos parâmetros armazenados'}: ${n(data.totals.parameterBytes)} · ${en ? 'Auxiliary elements' : 'Elementos auxiliares'}: ${n(data.totals.auxiliaryElements)}</p>
    <pre>${data.totals.weights} + ${data.totals.bias} + ${data.totals.other} = ${data.totals.total}</pre>
    ${data.warnings.length ? `<details class="parameter-warning"><summary>${en ? 'Classification notes' : 'Observações de classificação'} (${data.warnings.length})</summary><ul>${data.warnings.map(w => `<li>${e(w)}</li>`).join('')}</ul></details>` : ''}</section>
    <section class="panel parameter-panel parameter-summary"><div class="parameter-table-heading"><div><div class="eyebrow">${en ? 'MODEL STRUCTURE' : 'ESTRUTURA DO MODELO'}</div><h2>${en ? 'Layer summary' : 'Resumo por camada'}</h2><p class="muted">${en ? 'Click a layer to see its calculations. Share includes parameter reuse.' : 'Clique na camada para ver as contas. A participação inclui a reutilização de parâmetros.'}</p></div><span class="parameter-count">${data.layers.length} ${en ? 'layers' : 'camadas'}</span></div>
    <div class="table-scroll parameter-table-scroll"><table class="parameter-table"><thead><tr>${[en ? 'Layer' : 'Camada', en ? 'Operation' : 'Operação', roles.weights, roles.bias, roles.other, 'Total', en ? 'Share' : 'Participação'].map((h, i) => `<th scope="col" class="${i >= 2 ? 'parameter-numeric' : ''}">${e(h)}</th>`).join('')}</tr></thead><tbody>${data.layers.map(l => {
      const share = data.totals.layerSum ? 100 * l.total / data.totals.layerSum : 0;
      const shareLabel = share > 0 && share < 0.1 ? `<${(0.1).toLocaleString(locale())}%` : `${share.toLocaleString(locale(), { maximumFractionDigits: 1 })}%`;
      return `<tr class="${l.total ? '' : 'parameter-empty-row'}"><td><a class="parameter-layer-link" href="#parameter-layer-${l.subgraph}-${l.index}" data-layer-link="parameter-layer-${l.subgraph}-${l.index}"><span class="parameter-index">${String(l.index).padStart(2, '0')}</span><small>${en ? 'Subgraph' : 'Subgrafo'} ${l.subgraph}</small></a></td><td><span class="parameter-op ${l.operator.includes('CONV') ? 'convolution' : l.operator === 'FULLY_CONNECTED' ? 'dense' : ''}">${e(l.operator)}</span></td>${[l.weights, l.bias, l.other].map(v => `<td class="parameter-numeric ${v ? '' : 'parameter-zero'}">${n(v)}</td>`).join('')}<td class="parameter-numeric parameter-total">${n(l.total)}</td><td class="parameter-numeric"><div class="parameter-share"><span>${e(shareLabel)}</span><div class="parameter-share-track"><i style="width:${share}%;${share ? 'min-width:2px' : ''}"></i></div></div></td></tr>`;
    }).join('')}</tbody><tfoot><tr><th colspan="2" scope="row">${en ? 'Sum across layers' : 'Soma por camadas'}</th>${[data.layers.reduce((sum, l) => sum + l.weights, 0), data.layers.reduce((sum, l) => sum + l.bias, 0), data.layers.reduce((sum, l) => sum + l.other, 0), data.totals.layerSum].map(v => `<td class="parameter-numeric">${n(v)}</td>`).join('')}<td class="parameter-numeric">${data.totals.layerSum ? '100%' : '0%'}</td></tr></tfoot></table></div></section>
    <section class="panel parameter-panel"><h2>${en ? 'Calculations, layer by layer' : 'Contas, camada por camada'}</h2>${data.layers.map(l => `<details class="parameter-layer" id="parameter-layer-${l.subgraph}-${l.index}" open><summary>${l.subgraph} / ${l.index} · ${e(l.operator)} · ${n(l.total)} ${en ? 'parameters' : 'parâmetros'}</summary><p>${en ? 'Subgraph' : 'Subgrafo'}: ${e(l.subgraphName || l.subgraph)}</p>${l.parameters.map(tensorLines).join('') || `<p>${en ? 'No stored parameters identified.' : 'Nenhum parâmetro armazenado identificado.'}</p>`}<pre>${e(l.calculation)}</pre>${l.constants.length ? `<details><summary>${roles.auxiliary} (${l.constants.length})</summary>${l.constants.map(tensorLines).join('')}</details>` : ''}${l.notes.map(note => `<p class="muted">${e(note)}</p>`).join('')}</details>`).join('')}</section>`;
  const show = (data: Report, saved = false) => {
    report = data;
    $('#parameters-result').innerHTML = `<div class="toolbar parameter-downloads">${['html', 'md', 'csv', 'json'].map(format => `<button class="button ghost" data-parameter-download="${format}">${en ? 'Download' : 'Baixar'} ${format.toUpperCase()}</button>`).join('')}</div>` + reportHTML(data);
    document.querySelectorAll<HTMLButtonElement>('[data-parameter-download]').forEach(button => button.onclick = () => download(button.dataset.parameterDownload!));
    document.querySelectorAll<HTMLAnchorElement>('[data-layer-link]').forEach(link => link.onclick = event => {
      event.preventDefault();
      const detail = document.getElementById(link.dataset.layerLink!) as HTMLDetailsElement;
      detail.open = true; detail.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    $('#parameters-status').textContent = saved ? (en ? 'Saved report loaded.' : 'Relatório salvo carregado.') : (en ? 'Report ready and saved.' : 'Relatório pronto e salvo.');
    update();
  };
  const loadSaved = async () => {
    const version = ++selectionVersion;
    localStorage.setItem('parameters-model', model.value);
    report = null; $('#parameters-result').innerHTML = ''; $('#parameters-error').textContent = ''; update();
    if (!model.value) { $('#parameters-status').textContent = ''; return; }
    $('#parameters-status').textContent = en ? 'Loading saved report…' : 'Carregando relatório salvo…';
    try {
      const response = await fetch('/api/tflite-parameters/report?' + new URLSearchParams({ path: model.value }));
      const data = await response.json();
      if (!current() || version !== selectionVersion) return;
      if (!response.ok) throw new Error(data.error);
      if (data.exists) show(data.report, true);
      else $('#parameters-status').textContent = en ? 'No current report saved. Generate a report for this model.' : 'Nenhum relatório atualizado salvo. Gere um relatório para este modelo.';
    } catch (error) { if (current() && version === selectionVersion) { $('#parameters-status').textContent = ''; $('#parameters-error').textContent = (error as Error).message; } }
  };
  const download = (format: string) => {
    if (!report) return;
    let content: string, type: string;
    if (format === 'json') { content = JSON.stringify(report, null, 2); type = 'application/json'; }
    else if (format === 'html') {
      const tableStyles = `.parameter-table{border-collapse:separate;border-spacing:0;font-size:13px}.parameter-table th,.parameter-table td{border:0;border-bottom:1px solid #e4ece7;padding:14px 16px;white-space:nowrap}.parameter-table thead th,.parameter-table tfoot{background:#edf5f0}.parameter-table tbody tr:nth-child(even){background:#f8fbf9}.parameter-numeric{text-align:right!important;font-variant-numeric:tabular-nums}.parameter-total{font-weight:700;color:#176b53}.parameter-zero{color:#97a89e}.parameter-op,.parameter-index,.parameter-count{background:#edf5f0;color:#31705b;padding:5px 8px;border-radius:6px;font-size:11px}.parameter-layer-link{display:flex;gap:8px;align-items:center;color:inherit;text-decoration:none}.parameter-layer-link small{font-size:10px}.parameter-share-track{height:4px;background:#e3ede6;border-radius:4px;margin-top:5px}.parameter-share-track i{display:block;height:100%;background:#51a984}.parameter-table-heading{display:flex;justify-content:space-between;align-items:start;gap:16px}.parameter-count{white-space:nowrap}.parameter-table-scroll{border:1px solid #e0e9e4;border-radius:12px}.parameter-share{min-width:80px;font-size:11px}`;
      content = `<!doctype html><html lang="${language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${e(report.name)} — ${label}</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:16px;color:#182b30}table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:left;border:1px solid #ccc}.metrics{display:flex;gap:24px;flex-wrap:wrap}.metric span,.metric strong{display:block}.metric strong{font-size:28px}pre,code{white-space:pre-wrap;overflow-wrap:anywhere}details{border-top:1px solid #ddd;padding:12px 0}.parameter-panel{margin-bottom:28px}.table-scroll{overflow:auto}.parameter-tensor{margin:12px 0}@media print{details{break-inside:avoid}}${tableStyles}</style><body>${reportHTML(report)}</body></html>`;
      type = 'text/html';
    } else if (format === 'csv') {
      const rows: unknown[][] = [['subgraph', 'layer', 'operator', 'role', 'tensor', 'shape', 'dtype', 'elements', 'stored_bytes', 'shared', 'calculation']];
      for (const l of report.layers) {
        rows.push([l.subgraph, l.index, l.operator, 'layer_total', '', '', '', l.total, '', '', l.calculation]);
        for (const tensor of [...l.parameters, ...l.constants]) rows.push([l.subgraph, l.index, l.operator, tensor.role, tensor.name, tensor.shape.join(' x '), tensor.dtype, tensor.count, tensor.storedBytes, !!tensor.shared, tensor.calculation]);
      }
      rows.push(['', '', '', 'unique_total', '', '', '', report.totals.total, report.totals.parameterBytes, '', `${report.totals.weights} + ${report.totals.bias} + ${report.totals.other} = ${report.totals.total}`]);
      content = '\uFEFF' + rows.map(row => row.map(value => {
        let s = String(value ?? '');
        if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
        return '"' + s.replace(/"/g, '""') + '"';
      }).join(',')).join('\r\n'); type = 'text/csv';
    } else {
      content = [`# ${label}: ${report.name}`, report.method, `Total: ${report.totals.weights} + ${report.totals.bias} + ${report.totals.other} = ${report.totals.total}`, `Soma por camadas: ${report.totals.layerSum}`, ...report.warnings,
        ...report.layers.flatMap(l => [`\n## ${l.subgraph} / ${l.index} — ${l.operator}`, ...[...l.parameters, ...l.constants].map(tensor => `${roles[tensor.role]}: ${tensor.name} [${tensor.dtype}] — ${tensor.calculation}${tensor.shared ? ' (shared / compartilhado)' : ''}`), l.calculation, ...l.notes])].join('\n\n'); type = 'text/markdown';
    }
    const url = URL.createObjectURL(new Blob([content], { type: type + ';charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = report.name.replace(/\.tflite$/i, '').replace(/[^\p{L}\p{N}._-]/gu, '_') + '-parameters.' + format; a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const run = async (upload: boolean) => {
    if (busy) return;
    $('#parameters-error').textContent = '';
    const selected = file.files?.[0];
    if (upload && (!selected || !/\.tflite$/i.test(selected.name) || selected.size > maxBytes || !selected.size)) {
      $('#parameters-error').textContent = en ? 'Choose a nonempty .tflite within the upload limit.' : 'Escolha um .tflite não vazio dentro do limite de upload.'; return;
    }
    ++selectionVersion;
    busy = true; update(); $('#parameters-status').textContent = en ? 'Analyzing model…' : 'Analisando modelo…';
    $('#parameters-result').innerHTML = ''; report = null;
    try {
      const response = await fetch('/api/tflite-parameters' + (upload ? '/upload' : ''), { method: 'POST',
        headers: upload ? { 'Content-Type': 'application/octet-stream', 'X-Model-Name': encodeURIComponent(selected!.name) } : { 'Content-Type': 'application/json' },
        body: upload ? selected : JSON.stringify({ path: model.value }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (!current()) return;
      if (upload) {
        const value = 'saved:' + data.savedId;
        if (![...model.options].some(option => option.value === value)) {
          const group = model.querySelector('#parameters-saved')!;
          group.append(new Option(data.name, value));
        }
        model.value = value;
      }
      localStorage.setItem('parameters-model', model.value);
      show(data);
    } catch (error) {
      if (current()) { $('#parameters-error').textContent = (error as Error).message; $('#parameters-status').textContent = ''; }
    } finally { busy = false; if (current()) update(); }
  };
  $('#parameters-form').onsubmit = event => { event.preventDefault(); void run(false); };
  $('#parameters-upload').onclick = () => void run(true);
  file.onchange = update;
  model.onchange = () => { update(); void loadSaved(); };
  const response = await fetch('/api/tflite-parameters/models');
  const data = await response.json();
  if (!current()) return;
  if (!response.ok) throw new Error(data.error);
  maxBytes = data.maxBytes;
  model.innerHTML = `<optgroup label="${en ? 'Project models' : 'Modelos do projeto'}">${data.models.map((item: { path: string }) => `<option value="${e(item.path)}">${e(item.path)}</option>`).join('')}</optgroup><optgroup id="parameters-saved" label="${en ? 'Uploaded · saved reports' : 'Enviados · relatórios salvos'}">${data.saved.map((item: { path: string; name: string }) => `<option value="${e(item.path)}">${e(item.name)}</option>`).join('')}</optgroup>`;
  if (!model.options.length) model.add(new Option(en ? 'No models found' : 'Nenhum modelo encontrado', ''));
  const previous = localStorage.getItem('parameters-model');
  if (previous && [...model.options].some(option => option.value === previous)) model.value = previous;
  $('#parameters-limit').textContent = `${en ? 'Upload limit' : 'Limite de upload'}: ${n(maxBytes / 1048576)} MiB.`;
  update();
  await loadSaved();
}
