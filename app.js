(function () {
  var $ = function (id) { return document.getElementById(id); };
  var KEY = 'catraca-ru-coleta-v1';
  var pad = function (n) { return String(n).padStart(2, '0'); };
  /* Horário sempre no fuso de Brasília (America/Sao_Paulo, UTC-03:00), mesmo que o celular esteja em outro fuso. */
  var dtf = null;
  try { dtf = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/Sao_Paulo', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch (e) {}
  function parts(t) {
    var d = new Date(t), o = {}, ms = String(d.getMilliseconds()).padStart(3, '0');
    if (dtf) {
      dtf.formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
      return { y: o.year, mo: o.month, d: o.day, h: o.hour === '24' ? '00' : o.hour, mi: o.minute, s: o.second, ms: ms, off: '-03:00' };
    }
    return { y: d.getFullYear(), mo: pad(d.getMonth() + 1), d: pad(d.getDate()), h: pad(d.getHours()), mi: pad(d.getMinutes()), s: pad(d.getSeconds()), ms: ms, off: '' };
  }
  function today() { var p = parts(Date.now()); return p.y + '-' + p.mo + '-' + p.d; }
  var S = { meta: { sessao: today() + '-almoco', refeicao: 'almoco', catracas: 1, obs: 'A' }, events: [], inicio: null, fim: null, n: 0 };
  try { var raw = localStorage.getItem(KEY); if (raw) { var p = JSON.parse(raw); S = Object.assign(S, p); S.meta = Object.assign({ sessao: today() + '-almoco', refeicao: 'almoco', catracas: 1, obs: 'A' }, p.meta || {}); } } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }

  var audioCtx = null;
  function beep() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      var o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = 880; g.gain.value = 0.15; o.connect(g); g.connect(audioCtx.destination);
      o.start(); o.stop(audioCtx.currentTime + 0.18);
    } catch (e) {}
    try { if (navigator.vibrate) navigator.vibrate(150); } catch (e) {}
  }
  var toastTimer;
  function toast(msg) { var t = $('toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.hidden = true; }, 1600); }

  function running() { return S.inicio && !S.fim; }
  function elapsedSec() { return S.inicio ? ((S.fim || Date.now()) - S.inicio) / 1000 : 0; }
  function fmt(sec) { sec = Math.floor(sec); return Math.floor(sec / 60) + ':' + pad(sec % 60); }
  function bin(t) { return Math.floor((t - S.inicio) / 60000); }
  function add(tipo, valor) {
    S.events.push({ tipo: tipo, t: Date.now(), valor: (valor === undefined ? '' : valor) });
    save(); render();
  }
  function count(tipo) { return S.events.filter(function (e) { return e.tipo === tipo; }).length; }

  /* Sessão */
  $('f-sessao').value = S.meta.sessao; $('f-refeicao').value = S.meta.refeicao; $('f-catracas').value = S.meta.catracas; $('f-obs').value = S.meta.obs;
  $('f-sessao').addEventListener('input', function (e) { S.meta.sessao = e.target.value.trim(); save(); renderCsv(); });
  $('f-refeicao').addEventListener('change', function (e) { S.meta.refeicao = e.target.value; S.meta.sessao = today() + '-' + e.target.value; $('f-sessao').value = S.meta.sessao; save(); renderCsv(); });
  $('f-catracas').addEventListener('input', function (e) { S.meta.catracas = Math.max(1, parseInt(e.target.value, 10) || 1); save(); renderCsv(); });
  $('f-obs').addEventListener('change', function (e) { S.meta.obs = e.target.value; save(); renderCsv(); showTab(S.meta.obs === 'A' ? 'chegadas' : 'fila'); });

  /* Início e fim */
  $('btn-start').addEventListener('click', function () {
    if (S.events.length && !confirmStart) { confirmStart = true; $('btn-start').textContent = 'Há dados: toque de novo para recomeçar'; setTimeout(function () { confirmStart = false; render(); }, 3000); return; }
    confirmStart = false; S.events = []; S.inicio = Date.now(); S.fim = null; S.n = 0; lastBin = 0;
    S.events.push({ tipo: 'inicio', t: S.inicio, valor: '' });
    $('setup').open = false; beep(); save(); render();
  });
  var confirmStart = false;
  $('btn-stop').addEventListener('click', function () { if (!running()) return; S.fim = Date.now(); S.events.push({ tipo: 'fim', t: S.fim, valor: '' }); save(); render(); toast('Coleta encerrada'); showTab('dados'); });

  /* Chegadas */
  $('btn-chegou').addEventListener('click', function () { if (!running()) return; add('chegada'); try { if (navigator.vibrate) navigator.vibrate(30); } catch (e) {} });

  $('btn-saiu').addEventListener('click', function () { if (!running()) return; add('desistencia'); toast('Saída da fila anotada'); });

  /* Fila */
  $('n-minus').addEventListener('click', function () { S.n = Math.max(0, S.n - 1); save(); renderN(); });
  $('n-plus').addEventListener('click', function () { S.n += 1; save(); renderN(); });
  $('btn-fila').addEventListener('click', function () { if (!running()) return; add('fila', S.n); toast('Fila anotada: ' + S.n); });
  function renderN() { $('n-val').textContent = S.n; $('btn-fila').textContent = 'Anotar fila (' + S.n + ')'; }

  /* Cronômetro de atendimento */
  var sw = { on: false, t0: 0 };
  $('btn-sw').addEventListener('click', function () {
    if (!running()) return;
    if (!sw.on) { sw.on = true; sw.t0 = performance.now(); }
    else { var d = (performance.now() - sw.t0) / 1000; sw.on = false; add('atendimento', d.toFixed(2)); toast('Atendimento: ' + d.toFixed(1).replace('.', ',') + ' s'); }
    renderSw();
  });
  $('btn-sw-cancel').addEventListener('click', function () { sw.on = false; renderSw(); });
  function renderSw() {
    var b = $('btn-sw');
    b.firstChild.nodeValue = sw.on ? 'Passou' : 'Começou a passar';
    b.querySelector('span').textContent = sw.on ? 'toque quando o aluno passar pela catraca' : 'toque quando o aluno chegar na catraca';
    $('btn-sw-cancel').hidden = !sw.on;
    if (!sw.on) $('sw').textContent = '0,00 s';
  }

  /* Dados */
  function csvText() {
    var m = S.meta, lines = ['sessao,data,refeicao,catracas,observador,tipo,instante_iso,t_seg,valor'];
    S.events.forEach(function (e) {
      var q = parts(e.t);
      var iso = q.y + '-' + q.mo + '-' + q.d + 'T' + q.h + ':' + q.mi + ':' + q.s + '.' + q.ms + q.off;
      var ts = S.inicio ? ((e.t - S.inicio) / 1000).toFixed(1) : '';
      lines.push([m.sessao.replace(/,/g, ' '), today(), m.refeicao, m.catracas, m.obs, e.tipo, iso, ts, e.valor].join(','));
    });
    return lines.join('\n');
  }
  function renderCsv() { $('csv').value = csvText(); }
  $('btn-copy').addEventListener('click', function () {
    var ta = $('csv'); ta.focus(); ta.select();
    var done = function () { toast('CSV copiado'); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(ta.value).then(done, function () { try { document.execCommand('copy'); done(); } catch (e) { toast('Selecionado: copie manualmente'); } });
    else { try { document.execCommand('copy'); done(); } catch (e) { toast('Selecionado: copie manualmente'); } }
  });
  $('btn-undo').addEventListener('click', function () {
    var e = S.events.pop(); if (!e) return;
    if (e.tipo === 'inicio') { S.inicio = null; S.fim = null; }
    if (e.tipo === 'fim') { S.fim = null; }
    save(); render(); toast('Removido: ' + e.tipo);
  });
  var clearArmed = false;
  $('btn-clear').addEventListener('click', function () {
    if (!clearArmed) { clearArmed = true; $('btn-clear').textContent = 'Toque de novo para apagar'; setTimeout(function () { clearArmed = false; $('btn-clear').textContent = 'Apagar tudo'; }, 3000); return; }
    clearArmed = false; S.events = []; S.inicio = null; S.fim = null; S.n = 0; sw.on = false; save(); render(); renderSw(); $('btn-clear').textContent = 'Apagar tudo'; toast('Dados apagados');
  });

  /* Abas */
  function showTab(name) {
    ['chegadas', 'fila', 'dados'].forEach(function (k) {
      var sel = k === name; $('t-' + k).setAttribute('aria-selected', sel);
      var p = $('p-' + k); p.hidden = !sel;
    });
  }
  document.querySelectorAll('.tab').forEach(function (b) { b.addEventListener('click', function () { showTab(b.dataset.tab); }); });

  /* Renderização */
  function render() {
    var on = running();
    $('btn-start').textContent = on ? 'Coleta em andamento' : (S.inicio ? 'Nova coleta' : 'Iniciar coleta');
    $('btn-start').disabled = on;
    $('btn-stop').disabled = !on;
    ['btn-chegou', 'btn-saiu', 'btn-fila', 'btn-sw'].forEach(function (id) { $(id).disabled = !on; });
    var total = count('chegada');
    $('s-saiu').textContent = count('desistencia');
    $('s-total').textContent = total; $('d-ch').textContent = total; $('d-fi').textContent = count('fila');
    var at = count('atendimento'); $('s-atend').textContent = at; $('d-at').textContent = at;
    var nbins = 12, counts = new Array(nbins).fill(0), cur = S.inicio ? bin(S.fim || Date.now()) : 0;
    if (S.inicio) S.events.forEach(function (e) { if (e.tipo === 'chegada') { var i = nbins - 1 - (cur - bin(e.t)); if (i >= 0 && i < nbins) counts[i]++; } });
    var mx = Math.max.apply(null, counts.concat([4])), html = '';
    counts.forEach(function (c, i) { html += '<div class="bar' + (i === nbins - 1 ? ' now' : '') + '" style="height:' + Math.max(4, (c / mx) * 100) + '%" title="' + c + '"></div>'; });
    $('bars').innerHTML = html;
    $('s-min').textContent = counts[nbins - 1];
    var mins = elapsedSec() / 60; $('s-media').textContent = (mins >= 1 ? (total / mins) : total).toFixed(1).replace('.', ',');
    renderN(); renderCsv();
    var ul = $('log'); ul.innerHTML = '';
    S.events.slice(-8).reverse().forEach(function (e) {
      var li = document.createElement('li'), q = parts(e.t);
      var a = document.createElement('span'); a.className = 'tag-' + e.tipo; a.textContent = e.tipo + (e.valor !== '' ? ' · ' + e.valor : '');
      var b = document.createElement('span'); b.textContent = q.h + ':' + q.mi + ':' + q.s;
      li.appendChild(a); li.appendChild(b); ul.appendChild(li);
    });
    tick();
  }

  var lastBin = 0;
  function tick() {
    $('clock').textContent = fmt(elapsedSec());
    var now = parts(Date.now()); $('tod').textContent = now.h + ':' + now.mi + ':' + now.s;
    if (sw.on) $('sw').textContent = ((performance.now() - sw.t0) / 1000).toFixed(2).replace('.', ',') + ' s';
    var card = $('fila-card'), txt = $('due-txt');
    if (!running()) { card.classList.remove('due'); txt.textContent = S.inicio ? 'Coleta encerrada.' : 'Inicie a coleta para começar a contar o tempo.'; return; }
    var b = bin(Date.now());
    var done = S.events.some(function (e) { return e.tipo === 'fila' && bin(e.t) === b; });
    if (b !== lastBin) { lastBin = b; if (S.meta.obs === 'B' && !done) beep(); }
    card.classList.toggle('due', !done);
    var left = 60 - (elapsedSec() % 60);
    txt.textContent = done ? 'Anotado no minuto ' + b + '. Próximo em ' + fmt(left) + '.' : 'Minuto ' + b + ': anote a fila agora.';
  }
  setInterval(tick, 250);
  showTab(S.meta.obs === 'A' ? 'chegadas' : 'fila');
  render(); renderSw();
  if (S.inicio) $('setup').open = false;
})();
