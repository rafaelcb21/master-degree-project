import { language } from './i18n';

const escape = (value: string) => value.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
type Run = {status: string; phase: string; runtime: string; port: string; logs: string[]; reports: string[]; importStatus: string; ip: string | null};

export function esp32View(current: () => boolean, refreshIndex: () => Promise<void>) {
  const en = language === 'en';
  const text = (pt: string, english: string) => en ? english : pt;
  const get = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
  get('page-label').textContent = 'ESP32 · USB';
  get('main').innerHTML = `<div class="page-heading"><div><div class="eyebrow">ESP32 · USB</div><h1>${text('Executar no ESP32', 'Run on ESP32')}</h1><p>${text('Compile, grave e acompanhe a placa conectada ao notebook.', 'Build, flash and monitor the board connected to your computer.')}</p></div></div>
  <section class="panel execution-panel"><div class="toolbar">
  <label>${text('Porta USB', 'USB port')}<select id="board-port"></select></label>
  <button id="board-refresh" class="button subtle">${text('Verificar conexão', 'Check connection')}</button>
  <label>${text('Projeto / firmware', 'Project / firmware')}<select id="board-runtime"><option value="tflite">TFLite Micro</option><option value="wasm">WebAssembly / AOT</option></select></label></div>
  <p id="board-connection" role="status"></p>
  <label class="check"><input type="checkbox" id="board-import" checked> ${text('Importar relatórios automaticamente ao concluir', 'Automatically import reports when finished')}</label>
  <p>${text('Compilar e gravar substitui o firmware da placa. Reiniciar executa o firmware já gravado: selecione o projeto correspondente. O TFLite com checkpoints retoma os resultados salvos na flash; alterações no experimento iniciam uma nova execução. Firmwares sem persistência perdem os resultados mantidos apenas na RAM.', 'Build and flash replaces the board firmware. Restart runs the firmware already installed: select the matching project. TFLite with checkpoints resumes results saved in flash; changes to the experiment start a new run. Firmware without persistence loses results held only in RAM.')}</p>
  <div class="hero-actions"><button class="button primary" id="board-flash" disabled>${text('Compilar e gravar', 'Build and flash')}</button><button class="button subtle" id="board-restart" disabled>${text('Reiniciar benchmark', 'Restart benchmark')}</button><button class="button subtle" id="board-stop" disabled>${text('Fechar monitor', 'Close monitor')}</button></div>
  <p class="muted">${text('Feche outros monitores seriais. Mantenha o servidor aberto e o USB conectado durante a gravação. O Wi-Fi continua necessário para baixar imagens e importar relatórios.', 'Close other serial monitors. Keep the server running and USB connected while flashing. Wi-Fi is still required to download images and import reports.')}</p>
  <div id="board-status" role="status" aria-live="polite"></div><div id="board-error" role="alert"></div></section>
  <section class="panel execution-panel"><h2>${text('Monitor serial e compilação', 'Serial monitor and build log')}</h2><pre id="board-log" class="raw-text execution-log"></pre><div id="board-reports"></div></section>`;
  let run: Run | null = null, pending = false, connected = false, loaded = false, indexed = '';
  const draw = () => {
    if (!current()) return;
    const busy = pending || run?.status === 'running';
    for (const id of ['board-flash','board-restart']) get<HTMLButtonElement>(id).disabled = busy || !connected || !loaded;
    get<HTMLButtonElement>('board-stop').disabled = pending || run?.status !== 'running' || run.phase !== 'monitoring';
    for (const id of ['board-port','board-runtime','board-import']) (get(id) as HTMLInputElement).disabled = busy;
    const phases: Record<string,string> = {checking:text('Verificando chip ESP32', 'Checking ESP32 chip'), building:text('Compilando', 'Building'), flashing:text('Gravando', 'Flashing'), monitoring:text('Monitor serial ativo', 'Serial monitor active')};
    get('board-status').textContent = run ? `${run.status === 'running' ? phases[run.phase] || run.phase : run.status === 'completed' ? text('Monitor encerrado', 'Monitor closed') : text('Falha: consulte os logs', 'Failed: check logs')} · ${run.runtime.toUpperCase()} · ${run.port}${run.ip ? ` · IP ${run.ip}` : ''}` : text('Aguardando execução.', 'Waiting to start.');
    const log = get('board-log'), atEnd = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    log.textContent = run?.logs.join('\n') || '';
    if (atEnd) log.scrollTop = log.scrollHeight;
    const imports: Record<string,string> = {waiting:text('Aguardando relatório da placa.', 'Waiting for the board report.'), importing:text('Importando relatórios…', 'Importing reports…'), saved:text('Relatórios salvos.', 'Reports saved.'), partial:text('CSV salvo; metadata indisponível.', 'CSV saved; metadata unavailable.'), failed:text('Importação falhou. Use Importar do ESP32 para tentar novamente.', 'Import failed. Use Import from ESP32 to retry.'), disabled:''};
    get('board-reports').innerHTML = run ? `<p>${imports[run.importStatus] || ''}</p><ul>${run.reports.map(path => `<li><a class="text-link" href="#file?path=${encodeURIComponent(path)}">${escape(path)}</a></li>`).join('')}</ul>` : '';
  };
  const detect = async () => {
    get<HTMLButtonElement>('board-refresh').disabled = true;
    try {
      const response = await fetch('/api/esp32/ports');
      const data = await response.json();
      if (!current()) return;
      const select = get<HTMLSelectElement>('board-port'), selected = run?.status === 'running' ? run.port : select.value;
      select.innerHTML = data.ports.map((p: {port:string;description:string}) => `<option value="${escape(p.port)}">${escape(p.port)} · ${escape(p.description)}</option>`).join('');
      if (data.ports.some((p: {port:string}) => p.port === selected)) select.value = selected;
      connected = data.ports.length > 0;
      get('board-connection').textContent = data.error ? text('Confira a instalação ESP-IDF em web/config.json (esp32).', 'Check ESP-IDF settings in web/config.json (esp32).') : connected ? text('Porta detectada. O chip será confirmado antes da operação.', 'Port detected. The chip will be verified before the operation.') : text('Nenhuma porta detectada. Conecte a placa por um cabo USB de dados e verifique novamente.', 'No serial ports detected. Connect the board using a USB data cable and check again.');
    } catch { if (current()) get('board-connection').textContent = text('Não foi possível verificar as portas.', 'Could not check serial ports.'); connected = false; }
    finally { if (current()) {get<HTMLButtonElement>('board-refresh').disabled = false; draw();} }
  };
  const request = async (path: string, payload: object) => {
    pending = true; draw(); get('board-error').textContent = '';
    try {
      const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      if (current()) run = data.run;
    } catch (error) {
      if (current()) {
        const code = (error as Error).message;
        get('board-error').textContent = code === 'esp32_not_connected' ? text('A porta foi desconectada. Conecte a placa e verifique novamente.', 'The port was disconnected. Reconnect and check again.') : code === 'execution_busy' ? text('Já existe uma execução ou monitor ativo. Aguarde ou feche o monitor.', 'Another execution or monitor is active. Wait or close the monitor.') : text('Não foi possível iniciar. Confira a conexão, o ambiente ESP-IDF e os logs.', 'Could not start. Check the connection, ESP-IDF environment and logs.');
      }
    } finally {pending = false; draw();}
  };
  for (const action of ['flash','restart']) get(`board-${action}`).onclick = () => void request('/api/esp32/start', {action, port:get<HTMLSelectElement>('board-port').value, runtime:get<HTMLSelectElement>('board-runtime').value, autoImport:get<HTMLInputElement>('board-import').checked});
  get('board-stop').onclick = () => void request('/api/esp32/stop', {});
  get('board-refresh').onclick = () => void detect();
  const poll = async () => {
    try {
      const response = await fetch('/api/esp32/status');
      const data = await response.json();
      if (!current()) return;
      run = data.run; loaded = true;
      if (run?.status === 'running') get<HTMLSelectElement>('board-runtime').value = run.runtime;
      if (run?.reports.length && indexed !== run.reports.join()) { await refreshIndex(); indexed = run.reports.join(); }
      draw();
    } catch { if(current()) get('board-error').textContent = text('Servidor indisponível. Tentando novamente…', 'Server unavailable. Retrying…'); }
    if (current()) window.setTimeout(() => void poll(), 1500);
  };
  void detect(); void poll();
}
