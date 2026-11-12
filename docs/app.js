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

  var defMeta = { sessao: today() + '-almoco', refeicao: 'almoco', catracas: 1, obs: 'A', n0: 0 };
  var S = { meta: Object.assign({}, defMeta), events: [], inicio: null, fim: null };
  try { var raw = localStorage.getItem(KEY); if (raw) { var p = JSON.parse(raw); S = Object.assign(S, p); S.meta = Object.assign({}, defMeta, p.meta || {}); } } catch (e) {}
  function save() { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} }

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
  $('f-sessao').value = S.meta.sessao; $('f-refeicao').value = S.meta.refeicao; $('f-catracas').value = S.meta.catracas; $('f-obs').value = S.meta.obs; $('f-n0').value = S.meta.n0;
  $('f-sessao').addEventListener('input', function (e) { S.meta.sessao = e.target.value.trim(); save(); renderCsv(); });
  $('f-refeicao').addEventListener('change', function (e) { S.meta.refeicao = e.target.value; S.meta.sessao = today() + '-' + e.target.value; $('f-sessao').value = S.meta.sessao; save(); renderCsv(); });
  $('f-catracas').addEventListener('input', function (e) { S.meta.catracas = Math.max(1, parseInt(e.target.value, 10) || 1); save(); renderCsv(); });
  $('f-n0').addEventListener('input', function (e) { S.meta.n0 = Math.max(0, parseInt(e.target.value, 10) || 0); save(); });
  var ROLE_TAB = { A: 'chegadas', B: 'fila', C: 'saida' };
  $('f-obs').addEventListener('change', function (e) { S.meta.obs = e.target.value; save(); renderCsv(); showTab(ROLE_TAB[S.meta.obs]); });

  /* Início e fim */
  var confirmStart = false;
  $('btn-start').addEventListener('click', function () {
    if (S.events.length && !confirmStart) { confirmStart = true; $('btn-start').textContent = 'Há dados: toque de novo para recomeçar'; setTimeout(function () { confirmStart = false; render(); }, 3000); return; }
    confirmStart = false; S.events = []; S.inicio = Date.now(); S.fim = null;
    S.events.push({ tipo: 'inicio', t: S.inicio, valor: S.meta.n0 });
    $('setup').open = false; save(); render();
  });
  $('btn-stop').addEventListener('click', function () { if (!running()) return; S.fim = Date.now(); S.events.push({ tipo: 'fim', t: S.fim, valor: '' }); save(); render(); toast('Coleta encerrada'); showTab('dados'); });

  /* Botões de evento */
  [['btn-chegou', 'chegada', 'Chegada anotada'], ['btn-saiu', 'desistencia', 'Saída da fila anotada'], ['btn-ini', 'inicio_atend', 'Início de atendimento anotado'], ['btn-fim', 'saida_atend', 'Saída do atendimento anotada']].forEach(function (c) {
    $(c[0]).addEventListener('click', function () {
      if (!running()) return;
      add(c[1]);
      try { if (navigator.vibrate) navigator.vibrate(30); } catch (e) {}
      if (c[1] !== 'chegada' && c[1] !== 'inicio_atend' && c[1] !== 'saida_atend') toast(c[2]);
    });
  });

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
    clearArmed = false; S.events = []; S.inicio = null; S.fim = null; save(); render(); $('btn-clear').textContent = 'Apagar tudo'; toast('Dados apagados');
  });

  /* Abas */
  function showTab(name) {
    ['chegadas', 'fila', 'saida', 'dados'].forEach(function (k) {
      $('t-' + k).setAttribute('aria-selected', k === name);
      $('p-' + k).hidden = k !== name;
    });
  }
  document.querySelectorAll('.tab').forEach(function (b) { b.addEventListener('click', function () { showTab(b.dataset.tab); }); });

  /* Contadores por tipo de evento */
  var CONT = [
    { tipo: 'chegada', total: 's-total', min: 's-min', media: 's-media', bars: 'bars' },
    { tipo: 'inicio_atend', total: 'f-total', min: 'f-min', media: 'f-media', bars: 'f-bars' },
    { tipo: 'saida_atend', total: 'x-total', min: 'x-min', media: 'x-media', bars: 'x-bars' }
  ];
  function renderCont(c) {
    var total = count(c.tipo);
    $(c.total).textContent = total;
    var nb = 12, counts = new Array(nb).fill(0), cur = S.inicio ? bin(S.fim || Date.now()) : 0;
    if (S.inicio) S.events.forEach(function (e) { if (e.tipo === c.tipo) { var i = nb - 1 - (cur - bin(e.t)); if (i >= 0 && i < nb) counts[i]++; } });
    var mx = Math.max.apply(null, counts.concat([4])), html = '';
    counts.forEach(function (n, i) { html += '<div class="bar' + (i === nb - 1 ? ' now' : '') + '" style="height:' + Math.max(4, (n / mx) * 100) + '%" title="' + n + '"></div>'; });
    $(c.bars).innerHTML = html;
    $(c.min).textContent = counts[nb - 1];
    var mins = elapsedSec() / 60; $(c.media).textContent = (mins >= 1 ? (total / mins) : total).toFixed(1).replace('.', ',');
  }

  function render() {
    var on = running();
    $('btn-start').textContent = on ? 'Coleta em andamento' : (S.inicio ? 'Nova coleta' : 'Iniciar coleta');
    $('btn-start').disabled = on;
    $('btn-stop').disabled = !on;
    ['btn-chegou', 'btn-saiu', 'btn-ini', 'btn-fim'].forEach(function (id) { $(id).disabled = !on; });
    CONT.forEach(renderCont);
    $('s-saiu').textContent = count('desistencia');
    $('d-ch').textContent = count('chegada'); $('d-de').textContent = count('desistencia');
    $('d-in').textContent = count('inicio_atend'); $('d-sa').textContent = count('saida_atend');
    renderCsv();
    renderLog();
    tick();
  }

  /* Lista de registros com filtro por tipo */
  var NOMES = { chegada: 'Chegou aluno', desistencia: 'Saiu da fila sem passar', inicio_atend: 'Começou a ser atendido', saida_atend: 'Saiu do atendimento', inicio: 'Início da coleta', fim: 'Fim da coleta' };
  var filtro = 'todos';
  function renderLog() {
    ['chegada', 'desistencia', 'inicio_atend', 'saida_atend'].forEach(function (k) { $('c-' + k).textContent = count(k); });
    $('c-todos').textContent = S.events.length;
    document.querySelectorAll('.chip').forEach(function (c) { c.setAttribute('aria-pressed', c.dataset.f === filtro); });
    var ul = $('log'); ul.innerHTML = '';
    var lista = [];
    S.events.forEach(function (e, i) { if (filtro === 'todos' || e.tipo === filtro) lista.push({ e: e, n: i }); });
    if (!lista.length) { var v = document.createElement('li'); v.className = 'none'; v.textContent = 'Nenhum registro ainda.'; ul.appendChild(v); return; }
    var cont = {};
    lista.forEach(function (x) { cont[x.e.tipo] = (cont[x.e.tipo] || 0) + 1; x.k = cont[x.e.tipo]; });
    lista.reverse().forEach(function (x) {
      var e = x.e, q = parts(e.t), li = document.createElement('li');
      var a = document.createElement('span'); a.className = 'tag-' + e.tipo;
      a.textContent = (e.tipo === 'inicio' || e.tipo === 'fim' ? '' : '#' + x.k + ' ') + (NOMES[e.tipo] || e.tipo);
      var b = document.createElement('span'); b.className = 't'; b.textContent = q.h + ':' + q.mi + ':' + q.s;
      li.appendChild(a); li.appendChild(b); ul.appendChild(li);
    });
  }
  document.querySelectorAll('.chip').forEach(function (c) { c.addEventListener('click', function () { filtro = c.dataset.f; renderLog(); }); });

  function tick() {
    $('clock').textContent = fmt(elapsedSec());
    var now = parts(Date.now()); $('tod').textContent = now.h + ':' + now.mi + ':' + now.s;
  }
  setInterval(tick, 250);
  showTab(ROLE_TAB[S.meta.obs] || 'chegadas');
  render();
  if (S.inicio) $('setup').open = false;
})();
