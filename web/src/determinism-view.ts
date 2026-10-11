import { language } from './i18n';

type Variant = {value: unknown; executions: number[]};
type Stats = {count:number; maximum:number|null; mean:number|null; median:number|null; p95:number|null; p99:number|null; buckets?:Record<string,number>; unmatched_components?:number};
type Magnitudes = {quantized:Stats; scores:Stats; image_maxima:Stats};
type Sample = {model: string; type: string; env: string; name_image: string; scope: string; status: string;
  observations: number; complete: boolean; quantized_equal: boolean | null; scores_equal: boolean | null;
  ranking_equal: boolean | null; compared_executions: number[]; missing_executions: number[];
  excluded_executions: number[]; duplicate_executions: number[]; invalid_observations: number;
  quantized_variants: Variant[]; scores_variants: Variant[]; ranking_variants: Variant[];
  quantized_differences:Stats; scores_differences:Stats; class_changed:boolean|null; decision_changed:boolean|null; prediction_variants:Variant[]};
type Group = {model: string; type: string; env: string; executions: number[]; comparable: number;
  equal: number; different: number; insufficient: number; incomplete: number;
  class_changes:number; decision_changes:number; magnitudes:{all:Magnitudes; divergent:Magnitudes}};
type Result = {exists: boolean; generated_at: string; groups: Group[]; images: Sample[];
  matched: number; page: number; pages: number; options: Record<string, string[]>; stale: string[];
  sources: {path: string; generated_at: string}[];
  execution_maps: Record<string, {execution: number; type: string; env: string; folder: string}[]>};
const e = (v: unknown) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]!));

export async function determinismView(active: () => boolean) {
  const t = (pt: string, en: string) => language === 'en' ? en : pt;
  const title = t('Determinismo intra-ambiente', 'Within-environment determinism');
  const main = document.querySelector<HTMLElement>('#main')!;
  document.querySelector('#page-label')!.textContent = title;
  main.innerHTML = `<section class="panel execution-panel"><h1>${title}</h1>
    <p>${t('A mesma imagem produz exatamente os mesmos valores quando executada várias vezes no mesmo ambiente?', 'Does the same image produce exactly the same values across repeated runs in the same environment?')}</p>
    <div class="hero-actions"><button class="button primary" id="det-generate">${t('Gerar / atualizar análise', 'Generate / update analysis')}</button>
    <a class="button subtle" href="/api/analyses/determinism/download">${t('Baixar relatório', 'Download report')}</a>
    <a class="button subtle" href="/api/analyses/determinism/download?file=images.csv">${t('Baixar resultados CSV', 'Download CSV results')}</a></div>
    <p id="det-status" role="status"></p>
    <details><summary>${t('Método e limites', 'Method and limitations')}</summary>
    <p>${t('Agrupamento por modelo, formato, ambiente e nome exato da imagem. Comparação numérica exata de quantized e scores, sem tolerância, com pelo menos duas execuções. Cada pasta é uma execução independente. Não compara tempos nem acurácia.', 'Groups by model, runtime, environment and exact image name. Exact numeric comparison of quantized outputs and scores, with no tolerance and at least two executions. Each folder is an independent execution. Timing and accuracy are not compared.')}</p>
    <p>${t('Empates e saídas inválidas concluídas são incluídos. Falhas, imagens ignoradas, vetores ausentes e registros duplicados da mesma execução são excluídos e indicados. Cobertura incompleta significa que alguma execução do grupo não contribuiu com uma saída comparável.', 'Completed ties and invalid outputs are included. Failures, skipped images, missing vectors and duplicate records within an execution are excluded and identified. Incomplete coverage means that some group executions did not contribute a comparable output.')}</p>
    <p>${t('MobileNetV2: compara as classes, q e scores do Top-15 e sua ordem. Não permite concluir igualdade do vetor completo. A igualdade é limitada à precisão dos relatórios. Os bytes das imagens, modelos e configurações não são verificados; alterações nesses fatores podem explicar diferenças. Igualdade observada não garante determinismo em execuções futuras.', 'MobileNetV2: compares Top-15 classes, q, scores and rank order. It cannot establish equality of the full output vector. Equality is limited to report precision. Image bytes, models and configurations are not verified; changes in these factors may explain differences. Observed equality does not guarantee determinism in future runs.')}</p>
    <p>${t('Gerar / atualizar análise primeiro atualiza as duas consolidações com os relatórios salvos no projeto e depois recalcula o determinismo. A navegação apenas consulta o resultado salvo.', 'Generate / update analysis first refreshes both consolidations from reports saved in the project, then recalculates determinism. Browsing only reads the saved result.')}</p></details></section>
    <section class="panel execution-panel"><h2>${t('Resumo por ambiente', 'Summary by environment')}</h2><div class="consolidation-table" id="det-summary"></div></section>
    <section class="panel execution-panel" id="det-aggregate-panel"><details><summary>${t('Estatísticas agregadas — consulta complementar', 'Aggregate statistics — additional reference')}</summary>
    <p>${t('Diferença absoluta por componente de saída, comparando todos os pares de execuções da mesma imagem. As estatísticas incluem zeros. Percentis usam interpolação linear. As faixas são em unidades de quantized; scores são calculados separadamente.', 'Absolute differences per output component across all pairs of executions of the same image. Statistics include zeros. Percentiles use linear interpolation. Buckets use quantized units; scores are calculated separately.')}</p>
    <p>${t('As contagens por componente/par e por imagem (seu máximo) têm denominadores diferentes. As agregações não são médias das médias. No Top-15, somente classes presentes nos dois resultados permitem calcular a diferença numérica; ausências não viram zero.', 'Component/pair counts and image counts (their maximum) have different denominators. Aggregates are not averages of averages. In Top-15, numeric differences use only classes present in both outputs; missing classes are not treated as zero.')}</p>
    <p>${t('Troca de classe usa os resultados registrados. Mudança de decisão inclui transições para saída inválida. Não comparável indica que não há resultados conhecidos suficientes.', 'Class changes use recorded predictions. Decision changes include transitions to invalid output. Not comparable means there are insufficient known predictions.')}</p><div id="det-magnitudes"></div></details></section>
    <section class="panel execution-panel"><h2>${t('Resultados por imagem', 'Results by image')}</h2><div class="toolbar consolidation-filters" id="det-filters"></div>
    <p id="det-count"></p><p id="det-interpretation" class="det-explanation"></p>
    <div class="det-inspector"><div><h3>${t('Quanto cada imagem variou?', 'How much did each image vary?')}</h3>
    <div class="toolbar consolidation-filters"><label>${t('Valor','Value')}<select id="det-unit"><option value="quantized">quantized</option><option value="scores">scores</option></select></label><label>${t('Medida','Measure')}<select id="det-measure"><option value="maximum">${t('Diferença máxima','Maximum difference')}</option><option value="mean">${t('Média','Mean')}</option><option value="median">${t('Mediana','Median')}</option><option value="p95">P95</option><option value="p99">P99</option></select></label></div>
    <p>${t('Cada barra é uma imagem. Clique para ver os valores e a interpretação. Laranja indica troca de classe; o texto ao lado também identifica essa mudança.', 'Each bar is one image. Click to inspect its values and interpretation. Orange marks a class change, also identified in the row text.')}</p><div id="det-chart"></div></div><div id="det-images" aria-live="polite"></div></div>
    <div class="hero-actions"><button class="button subtle" id="det-prev">${t('Anterior', 'Previous')}</button><span id="det-page"></span><button class="button subtle" id="det-next">${t('Próxima', 'Next')}</button></div></section>
    <section class="panel execution-panel"><details><summary>${t('Fontes e mapa das execuções', 'Sources and execution map')}</summary><div id="det-sources"></div></details></section>`;
  const get = <T extends HTMLElement = HTMLElement>(id: string) => main.querySelector<T>(`#${id}`)!;
  get('det-aggregate-panel').before(get('det-images').closest('section')!);
  const params = new URLSearchParams({status:'different'});
  let page = 1, serial = 0, busy = false, initial = true;
  const equality = (v: boolean | null) => v === null ? t('Não comparável', 'Not comparable') : v ? t('Iguais', 'Equal') : t('Diferentes', 'Different');
  const changed = (v:boolean|null) => v === null ? t('Não comparável', 'Not comparable') : v ? t('Sim', 'Yes') : t('Não', 'No');
  const number = (v:number|null) => v === null ? '—' : String(Number(v.toPrecision(8)));
  function metrics(q:Stats, s:Stats) {
    return `<div class="consolidation-table"><table class="data-table"><thead><tr>${['', 'N', t('Máximo','Maximum'), t('Média','Mean'), t('Mediana','Median'), 'P95', 'P99'].map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${[['quantized',q],['scores',s]].map(([name, value])=>{const m=value as Stats;return `<tr><td>${name}</td>${[m.count,m.maximum,m.mean,m.median,m.p95,m.p99].map(v=>`<td>${number(v)}</td>`).join('')}</tr>`;}).join('')}</tbody></table></div>`;
  }
  function distribution(label:string, stats:Stats) {
    const counts=Object.entries(stats.buckets ?? {}), max=Math.max(1,...counts.map(([,n])=>n));
    return `<h4>${label} (N=${stats.count})</h4><div class="det-distribution">${counts.map(([label,n])=>`<div><span>${e(label)}</span><div class="det-track"><i style="width:${n/max*100}%"></i></div><strong>${n}</strong></div>`).join('')}</div>`;
  }
  function explain(item:Sample) {
    const q=item.quantized_differences, s=item.scores_differences;
    if(!q || !q.count) return t('Não há pares com valores correspondentes suficientes para calcular a diferença.', 'There are not enough pairs with matching values to calculate a difference.');
    const conclusion=item.class_changed ? t('A classe predita mudou entre as execuções.', 'The predicted class changed between executions.') : item.decision_changed ? t('Houve uma transição entre predição e saída inválida.', 'There was a transition between a prediction and invalid output.') : item.class_changed===false ? t('A classe predita permaneceu a mesma, apesar da variação numérica.', 'The predicted class stayed the same despite the numeric variation.') : t('Não há classes registradas suficientes para concluir se houve troca.', 'There are not enough recorded classes to assess a change.');
    return `${t('Nas execuções','Across executions')} ${item.compared_executions.join(', ')}, ${t('a maior diferença desta imagem foi','this image’s largest difference was')} ${number(q.maximum)} ${t('unidades quantizadas e','quantized units and')} ${number(s.maximum)} ${t('em score','in score')}. ${conclusion} ${t('As estatísticas abaixo resumem','The statistics below summarize')} ${q.count} ${t('diferenças entre valores de saída desta imagem, não imagens diferentes.','differences between output values for this image, not different images.')} ${item.observations===2 && q.count===2 ? t('São duas execuções e duas saídas. Quando as duas diferenças são iguais, máximo, média, mediana, P95 e P99 coincidem.', 'There are two executions and two outputs. When both differences are equal, maximum, mean, median, P95 and P99 coincide.') : ''}`;
  }
  function outputs(item:Sample) {
    const at=(variants:Variant[], execution:number)=>variants.find(v=>v.executions.includes(execution))?.value;
    const label=(v:unknown)=>{const p=v as {state:string;label:number}|undefined; return p?.state==='class'? `${p.label}${item.model==='drowsiness'?p.label===1?' (drowsy)':' (non_drowsy)':''}` : p?.state==='invalid'?t('Saída inválida','Invalid output'):'—';};
    return `<h4>${t('Valores registrados — lado a lado','Recorded values — side by side')}</h4><div class="consolidation-table"><table class="data-table"><thead><tr>${[t('Execução','Execution'),'quantized','scores',t('Classe','Class')].map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${item.compared_executions.map(ex=>`<tr><td>${ex}</td><td>${e(JSON.stringify(at(item.quantized_variants,ex)))}</td><td>${e(JSON.stringify(at(item.scores_variants,ex)))}</td><td>${e(label(at(item.prediction_variants??[],ex)))}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function draw(data: Result) {
    if (!data.exists) {get('det-status').textContent = t('Nenhuma análise salva. Clique em Gerar / atualizar análise.', 'No saved analysis. Click Generate / update analysis.'); return;}
    page = data.page;
    get('det-status').textContent = `${t('Gerado em', 'Generated')}: ${new Date(data.generated_at).toLocaleString()}${data.stale.length ? ' · ' + t('As consolidações mudaram. Gere novamente esta análise.', 'Consolidations changed. Regenerate this analysis.') : ''}`;
    const headers = ['model', 'type', 'env', t('Execuções', 'Executions'), t('Comparáveis', 'Comparable'), t('Iguais', 'Equal'), t('Diferentes', 'Different'), t('Insuficientes', 'Insufficient'), t('Cobertura incompleta', 'Incomplete coverage')];
    get('det-summary').innerHTML = `<table class="data-table"><thead><tr>${headers.map(h => `<th>${e(h)}</th>`).join('')}</tr></thead><tbody>${data.groups.map(g => `<tr>${[g.model, g.type, g.env, g.executions.length, g.comparable, g.equal, g.different, g.insufficient, g.incomplete].map(v => `<td>${e(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    get('det-magnitudes').innerHTML = data.groups.map(g=>`<details class="det-image" ${g.different ? 'open' : ''}><summary>${e(g.model)} · ${e(g.type)} · ${e(g.env)}</summary><p>${t('Imagens com troca de classe','Images with class changes')}: <strong>${g.class_changes}</strong> · ${t('Mudança de decisão','Decision changes')}: <strong>${g.decision_changes}</strong></p>${g.magnitudes ? Object.entries(g.magnitudes).map(([population,m])=>`<h3>${population==='all'?t('Todas as imagens comparáveis','All comparable images'):t('Somente imagens divergentes','Divergent images only')}</h3>${metrics(m.quantized,m.scores)}${distribution(t('Diferenças quantized por componente/par','Quantized differences per component/pair'),m.quantized)}${distribution(t('Imagens por diferença quantized máxima','Images by maximum quantized difference'),m.image_maxima)}`).join('') : t('Gere novamente a análise para calcular as magnitudes.','Regenerate the analysis to compute magnitudes.')}</details>`).join('');
    if (!get('det-filters').children.length) {
      get('det-filters').innerHTML = Object.entries(data.options).map(([key, options]) => `<label>${e(key)}<select data-det="${key}"><option value="">${t('Todos', 'All')}</option>${options.map(v => `<option>${e(v)}</option>`).join('')}</select></label>`).join('') +
        `<label>${t('Resultado', 'Result')}<select data-det="status"><option value="different">${t('Com diferenças', 'Different')}</option><option value="equal">${t('Iguais', 'Equal')}</option><option value="insufficient">${t('Repetições insuficientes', 'Insufficient repeats')}</option><option value="">${t('Todos', 'All')}</option></select></label><label>${t('Imagem (distingue maiúsculas)', 'Image (case sensitive)')}<input data-det="search" placeholder="a0002.raw"></label>`;
      get('det-filters').querySelectorAll<HTMLInputElement | HTMLSelectElement>('[data-det]').forEach(input => {input.value=params.get(input.dataset.det!)??'';input.onchange = () => {params.set(input.dataset.det!, input.value); params.set('page','1'); void load();};});
    }
    get('det-count').textContent = `${data.matched} ${t('imagens neste filtro', 'images in this filter')}`;
    const group=data.groups.find(g=>g.model===params.get('model')&&g.type===params.get('type')&&g.env===params.get('env'));
    get('det-interpretation').textContent=group?`${group.model} · ${group.type} · ${group.env}: ${group.different} ${t('das','of')} ${group.comparable} ${t('imagens comparáveis apresentaram diferenças. Dessas,','comparable images differed. Of those,')} ${group.class_changes} ${t('tiveram troca de classe. Selecione uma barra para entender cada caso.','had a class change. Select a bar to understand each case.')}`:t('Selecione modelo, formato e ambiente para comparar as imagens do mesmo grupo. O gráfico mostra as imagens desta página, ordenadas pela maior diferença quantizada.','Select model, runtime and environment to compare images in one group. The chart shows this page’s images, sorted by largest quantized difference.');
    get('det-images').innerHTML = data.images.map((item,index) => {
      const show = (label: string, values: Variant[]) => !values.length ? '' : `<h4>${label}</h4>${values.map(v => `<p>${t('Execuções', 'Executions')} ${e(v.executions.join(', '))}</p><pre class="det-values">${e(JSON.stringify(v.value))}</pre>`).join('')}`;
      return `<article class="det-image" data-image="${index}" ${index?'hidden':''}><h3>${e(item.name_image)} <small>${e(item.model)} · ${e(item.type)} · ${e(item.env)}</small></h3><p class="det-explanation">${e(explain(item))}</p>${outputs(item)}
        <p>quantized: <strong>${e(equality(item.quantized_equal))}</strong> · scores: <strong>${e(equality(item.scores_equal))}</strong>${item.scope === 'top15' ? ` · ranking: <strong>${e(equality(item.ranking_equal))}</strong>` : ''}</p>
        <p>${t('Execuções comparadas', 'Compared executions')}: ${e(item.compared_executions.join(', ')) || '—'} · ${t('Saídas inválidas incluídas', 'Invalid outputs included')}: ${item.invalid_observations}</p>
        ${item.quantized_differences ? `<p>${t('Troca de classe','Class changed')}: <strong>${changed(item.class_changed)}</strong> · ${t('Mudança de decisão','Decision changed')}: <strong>${changed(item.decision_changed)}</strong></p>${metrics(item.quantized_differences,item.scores_differences)}<p>${t('Faixas quantized por componente/par','Quantized buckets per component/pair')}: ${Object.entries(item.quantized_differences.buckets??{}).map(([key,n])=>`${e(key)}: <strong>${n}</strong>`).join(' · ')}</p>${item.quantized_differences.unmatched_components ? `<p>${t('Componentes sem correspondência (excluídos da magnitude)','Unmatched components (excluded from magnitudes)')}: ${item.quantized_differences.unmatched_components}</p>` : ''}` : ''}
        ${item.complete ? '' : `<p>${t('Cobertura incompleta', 'Incomplete coverage')}: ${t('ausentes', 'missing')} [${item.missing_executions}], ${t('excluídas', 'excluded')} [${item.excluded_executions}], ${t('duplicadas', 'duplicates')} [${item.duplicate_executions}]</p>`}
        <details><summary>${t('Ver valores de cada execução', 'See values for each execution')}</summary>${show(t('Predições (label registrado)','Predictions (recorded label)'),item.prediction_variants??[])}${show('quantized', item.quantized_variants)}${show('scores', item.scores_variants)}${show('ranking', item.ranking_variants)}</details></article>`;
    }).join('') || `<p>${t('Nenhuma imagem corresponde aos filtros.', 'No images match these filters.')}</p>`;
    let selected=0;
    const chart=()=>{
      const unit=get<HTMLSelectElement>('det-unit').value==='scores'?'scores':'quantized';
      const measure=get<HTMLSelectElement>('det-measure').value as 'maximum'|'mean'|'median'|'p95'|'p99';
      const values=data.images.map(item=>item[unit==='scores'?'scores_differences':'quantized_differences']?.[measure]??null);
      const scale=Math.max(...values.map(v=>v??0),0);
      get('det-chart').innerHTML=`<p>${t('Escala linear','Linear scale')}: 0 – ${number(scale)} · ${unit}. ${t('Valores exatos ao lado das barras.','Exact values beside bars.')}</p>`+data.images.map((item,i)=>`<button class="det-image-bar ${item.class_changed?'class-change':''}" data-bar="${i}" aria-pressed="${selected===i}" type="button"><span><strong>${e(item.name_image)}</strong><small>${e(item.type)} · ${e(item.env)}${item.class_changed?' · '+t('classe mudou','class changed'):''}</small></span><span class="det-track"><i style="width:${scale?Math.max(0,(values[i]??0)/scale*100):0}%"></i></span><b>${number(values[i])}</b></button>`).join('');
      get('det-chart').querySelectorAll<HTMLButtonElement>('[data-bar]').forEach(button=>button.onclick=()=>{selected=Number(button.dataset.bar);get('det-images').querySelectorAll<HTMLElement>('[data-image]').forEach(article=>article.hidden=Number(article.dataset.image)!==selected);chart();if(innerWidth<1000)get('det-images').scrollIntoView({behavior:'smooth',block:'start'});});
    };
    get('det-unit').onchange=chart; get('det-measure').onchange=chart;chart();
    get('det-page').textContent = `${page} / ${data.pages}`;
    get<HTMLButtonElement>('det-prev').disabled = page <= 1;
    get<HTMLButtonElement>('det-next').disabled = page >= data.pages;
    get('det-sources').innerHTML = data.sources.map(s => `<p>${e(s.path)} · ${e(s.generated_at)}</p>`).join('') +
      Object.entries(data.execution_maps).map(([source, runs]) => `<h3>${e(source)}</h3>${runs.map(r => `<p>${r.execution} · ${e(r.type)} · ${e(r.env)} · <code>${e(r.folder)}</code></p>`).join('')}`).join('');
  }
  async function load(rebuild = false) {
    if (busy) return;
    const id = ++serial;
    if (rebuild) {busy = true; get<HTMLButtonElement>('det-generate').disabled = true; get('det-status').textContent = t('Atualizando consolidações e recalculando a análise…', 'Refreshing consolidations and recalculating the analysis…');}
    try {
      const response = await fetch('/api/analyses/determinism' + (rebuild ? '' : '?' + params), rebuild ? {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'} : undefined);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (initial && data.exists && !rebuild) {
        initial=false;
        const focus=[...data.groups].sort((a:Group,b:Group)=>b.different-a.different)[0];
        if(focus?.different){params.set('model',focus.model);params.set('type',focus.type);params.set('env',focus.env);await load();return;}
      }
      if (active() && serial === id) {
        if (rebuild) {params.set('page','1');busy=false;await load();return;}
        draw(data);
      }
    } catch (error) {if (active()) get('det-status').textContent = String(error);}
    finally {busy = false; if (active()) get<HTMLButtonElement>('det-generate').disabled = false;}
  }
  get('det-generate').onclick = () => void load(true);
  get('det-prev').onclick = () => {params.set('page', String(page - 1)); void load();};
  get('det-next').onclick = () => {params.set('page', String(page + 1)); void load();};
  await load();
}
