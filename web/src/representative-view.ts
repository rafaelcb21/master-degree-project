import { language } from './i18n';

type Image = {name_image:string; status:string; votes:number; observations:number; available:number; variant_count:number; selected_execution:number|null; selected_source:string|null; excluded_executions:number[]; conflicts:string[]; input_identity_verified:boolean; model_identity_verified:boolean; variants:{quantized:number[]; scores:number[]; result:number; votes:number; executions:number[]}[]};
type Group = {model:string; type:string; source_executions:number[]; selected:number; unresolved:number; statuses:Record<string,number>};
type Report = {exists:boolean; generated_at:string; groups:Group[]; group:string; images:Image[]; page:number; pages:number; matched:number};
const escape = (value:unknown) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]!));

export async function representativeView(active:()=>boolean) {
  const t = (pt:string,en:string) => language === 'en' ? en : pt;
  const title = t('Relatórios representativos · ESP32','Representative reports · ESP32');
  const statuses:Record<string,string> = {equal:t('Iguais','Equal'), mode:t('Mais frequente','Most frequent'), single:t('Uma observação','One observation'), tie:t('Empate','Tie'), conflict:t('Identidade conflitante','Conflicting identity'), no_valid:t('Sem saída completa','No complete output')};
  document.querySelector('#page-label')!.textContent = title;
  const main = document.querySelector<HTMLElement>('#main')!;
  main.innerHTML = `<section class="panel execution-panel"><h1>${title}</h1>
    <p>${t('Um novo relatório para cada modelo e formato do ESP32. Saídas iguais são mantidas; quando variam, escolhemos o vetor completo que mais se repete por imagem.', 'One new report per ESP32 model and runtime. Equal outputs are retained; when they vary, the most frequent complete output vector is selected per image.')}</p>
    <div class="hero-actions"><button id="rep-generate" class="button primary">${t('Gerar / atualizar relatórios','Generate / update reports')}</button><a class="button subtle" href="#analysis">${t('Abrir análise consolidada','Open consolidated analysis')}</a><a class="button subtle" href="/api/analyses/esp32-consensus/download?file=images.csv">${t('Baixar seleção CSV','Download selection CSV')}</a><a class="button subtle" href="/api/analyses/esp32-consensus/download?file=report.json">${t('Baixar evidências JSON','Download JSON evidence')}</a></div>
    <p id="rep-message" role="status"></p><details><summary>${t('Como a seleção funciona','How selection works')}</summary>
    <p>${t('Comparação numérica exata do vetor quantizado, scores, índices e resultado registrado. Cada execução fornece no máximo um voto por imagem. Falhas, imagens ignoradas, vetores incompletos e registros duplicados na mesma execução são excluídos. O maior número de votos deve ser único; empates e conflitos de identidade ficam sem resultado utilizável.', 'Exact numeric comparison of the quantized vector, scores, indices and recorded result. Each execution contributes at most one vote per image. Failures, skipped images, incomplete vectors and duplicate records within an execution are excluded. The highest vote count must be unique; ties and identity conflicts have no usable result.')}</p>
    <p>${t('A linha e seus tempos vêm da primeira execução que apresenta o resultado escolhido; os tempos não são calculados por votação. Hashes e configurações registrados são conferidos quando disponíveis. Nomes iguais sem hashes não comprovam que os bytes da imagem e do modelo são iguais. Uma única observação é mantida e identificada.', 'The row and its timings come from the first execution with the selected result; timing is not selected by voting. Recorded hashes and configurations are checked when available. Matching names without hashes do not prove matching image and model bytes. A single observation is retained and identified.')}</p>
    <p>${t('Gerar atualiza também a análise consolidada, que passa a usar estes relatórios no ESP32. Os relatórios originais são preservados e continuam sendo usados no determinismo intra-ambiente. Navegar nesta tela apenas consulta o resultado salvo.', 'Generating also updates consolidated analysis, which uses these reports for ESP32. Original reports are preserved and remain the source for within-environment determinism. Browsing this page only reads the saved result.')}</p></details></section>
    <section class="panel execution-panel"><h2>${t('Relatórios por modelo e formato','Reports by model and runtime')}</h2><div class="consolidation-table" id="rep-groups"></div></section>
    <section class="panel execution-panel"><h2>${t('Seleção por imagem','Selection by image')}</h2><div class="toolbar consolidation-filters"><label>${t('Relatório','Report')}<select id="rep-group"></select></label><label>${t('Situação','Status')}<select id="rep-status"><option value="">${t('Todas','All')}</option>${Object.entries(statuses).map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select></label><label>${t('Imagem','Image')}<input id="rep-search" type="search"></label></div><p id="rep-count"></p><div id="rep-images"></div><div class="hero-actions"><button id="rep-prev" class="button subtle">${t('Anterior','Previous')}</button><span id="rep-page"></span><button id="rep-next" class="button subtle">${t('Próxima','Next')}</button></div></section>`;
  const get = <T extends HTMLElement = HTMLElement>(id:string) => main.querySelector<T>(`#rep-${id}`)!;
  let page=1, serial=0, busy=false;
  const params = new URLSearchParams();
  async function load() {
    const request=++serial;
    params.set('page',String(page));
    try {
      const response=await fetch(`/api/analyses/esp32-consensus?${params}`);
      const data:Report=await response.json();
      if(!response.ok) throw new Error((data as any).error || response.statusText);
      if(!active() || request!==serial) return;
      if(!data.exists) {get('message').textContent=t('Nenhum relatório gerado. Clique em Gerar / atualizar relatórios.','No reports generated. Click Generate / update reports.');return;}
      get('message').textContent=`${t('Atualizado em','Updated at')} ${data.generated_at}`;
      get('groups').innerHTML=`<table class="data-table"><thead><tr>${[t('Modelo','Model'),t('Formato','Runtime'),t('Execuções de origem','Source executions'),t('Selecionadas','Selected'),t('Sem seleção','Unresolved'), 'CSV'].map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${data.groups.map(g=>`<tr><td>${escape(g.model)}</td><td>${escape(g.type)}</td><td>${g.source_executions.length}</td><td>${g.selected}</td><td>${g.unresolved}</td><td><a href="/api/analyses/esp32-consensus/download?group=${encodeURIComponent(`${g.model}/${g.type}`)}">${t('Baixar relatório','Download report')}</a></td></tr>`).join('')}</tbody></table>`;
      get<HTMLSelectElement>('group').innerHTML=data.groups.map(g=>`<option value="${escape(`${g.model}/${g.type}`)}">${escape(g.model)} · ${escape(g.type)}</option>`).join('');
      get<HTMLSelectElement>('group').value=data.group || '';
      if(data.group) params.set('group',data.group);
      get('count').textContent=`${data.matched} ${t('imagens neste filtro','images in this filter')}`;
      get('images').innerHTML=data.images.map(item=>`<details class="rep-image"><summary><strong>${escape(item.name_image)}</strong> · ${statuses[item.status]} · ${item.votes}/${item.observations} ${t('votos','votes')}</summary>
        <p>${t('Execução escolhida','Selected execution')}: ${item.selected_execution ?? '—'} · ${t('Execuções com registros','Executions with records')}: ${item.available} · ${t('Variantes','Variants')}: ${item.variant_count}</p>
        ${item.selected_source ? `<p class="rep-source">${escape(item.selected_source)}</p>` : ''}
        ${item.excluded_executions.length ? `<p>${t('Execuções excluídas','Excluded executions')}: ${item.excluded_executions.join(', ')}</p>` : ''}
        ${item.conflicts.length ? `<p>${t('Conflitos','Conflicts')}: ${escape(item.conflicts.join(', '))}</p>` : ''}
        <p>${t('Hash da imagem verificado em todas as observações','Image hash verified for all observations')}: ${item.input_identity_verified ? t('sim','yes') : t('não','no')} · ${t('Hash do modelo','Model hash')}: ${item.model_identity_verified ? t('sim','yes') : t('não','no')}</p>
        <div class="consolidation-table"><table class="data-table"><thead><tr>${[t('Votos','Votes'),'quantized','scores',t('Resultado','Result'),t('Execuções','Executions')].map(v=>`<th>${v}</th>`).join('')}</tr></thead><tbody>${item.variants.map(v=>`<tr><td>${v.votes}</td><td>${escape(JSON.stringify(v.quantized))}</td><td>${escape(JSON.stringify(v.scores))}</td><td>${escape(v.result)}</td><td>${escape(v.executions.join(', '))}</td></tr>`).join('')}</tbody></table></div></details>`).join('') || `<p>${t('Nenhuma imagem neste filtro.','No images in this filter.')}</p>`;
      page=data.page;get('page').textContent=`${data.page} / ${data.pages}`;
      get<HTMLButtonElement>('prev').disabled=page<=1;get<HTMLButtonElement>('next').disabled=page>=data.pages;
    } catch(error) {if(active() && request===serial) get('message').textContent=String(error);}
  }
  for(const key of ['group','status','search']) get(key).addEventListener('change',()=>{params.set(key,(get(key) as HTMLInputElement).value);page=1;void load();});
  get('prev').onclick=()=>{page--;void load();};get('next').onclick=()=>{page++;void load();};
  get('generate').onclick=async()=>{
    if(busy) return;busy=true;get<HTMLButtonElement>('generate').disabled=true;++serial;
    get('message').textContent=t('Gerando relatórios e atualizando a consolidação…','Generating reports and updating consolidation…');
    try {const response=await fetch('/api/analyses/esp32-consensus',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!response.ok) throw new Error((await response.json()).error || response.statusText);if(active()) await load();}
    catch(error) {if(active()) get('message').textContent=String(error);}
    finally {busy=false;if(active()) get<HTMLButtonElement>('generate').disabled=false;}
  };
  await load();
}
