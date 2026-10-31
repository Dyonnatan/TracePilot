// Interações do TracePilot: diagrama clicável, ajuda "?" dos indicadores,
// tooltip das tendências e atualização ao vivo do painel.
// Tudo por delegação de eventos no `document`, porque o painel troca o
// HTML do miolo a cada atualização e os elementos são recriados.
(function () {
  'use strict';

  // ---- Diagrama: selecionar nó --------------------------------------
  const ui = { selected: null, openHelp: new Set() };
  function closePanels(arch) {
    ui.selected = '';
    arch.querySelectorAll('.dg-node').forEach((g) => g.classList.remove('is-selected'));
    arch.querySelectorAll('[data-panel]').forEach((p) => { p.hidden = true; });
  }

  function selectNode(arch, key, scroll) {
    if (!arch) return;
    ui.selected = key;
    arch.querySelectorAll('.dg-node').forEach((g) => {
      g.classList.toggle('is-selected', g.dataset.node === key && !g.dataset.resource);
    });
    let shown = null;
    arch.querySelectorAll('[data-panel]').forEach((p) => {
      const match = p.dataset.panel === key;
      p.hidden = !match;
      if (match) shown = p;
    });
    if (scroll && shown) shown.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function initArch(root) {
    (root || document).querySelectorAll('[data-arch]').forEach((arch) => {
      // null = a pessoa ainda não escolheu (usa o padrão do servidor);
      // '' = ela fechou o painel de propósito.
      const key = ui.selected === null ? arch.dataset.defaultSelected : ui.selected;
      if (key) selectNode(arch, key, false);
    });
  }

  document.addEventListener('click', (ev) => {
    const node = ev.target.closest('.dg-node[data-node]');
    if (node && node.closest('[data-arch]').querySelector('[data-panel]')) {
      const arch = node.closest('[data-arch]');
      const already = ui.selected === node.dataset.node
        || (ui.selected === null && arch.dataset.defaultSelected === node.dataset.node);
      if (already && !node.dataset.resource) closePanels(arch);
      else selectNode(arch, node.dataset.node, true);
      return;
    }
    const focusBtn = ev.target.closest('[data-focus-node]');
    if (focusBtn) {
      const arch = document.querySelector('[data-arch]');
      selectNode(arch, focusBtn.dataset.focusNode, false);
      arch.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    const help = ev.target.closest('[data-help]');
    if (help) {
      const key = help.dataset.help;
      const text = document.querySelector(`[data-help-text="${key}"]`);
      const open = text.hidden;
      text.hidden = !open;
      help.setAttribute('aria-expanded', String(open));
      open ? ui.openHelp.add(key) : ui.openHelp.delete(key);
      return;
    }
    const prefill = ev.target.closest('[data-prefill]');
    if (prefill) {
      const box = document.getElementById('error-report');
      if (box && !box.value) box.value = prefill.dataset.prefill;
      setTimeout(() => box && box.focus(), 300);
    }
  });

  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const node = ev.target.closest && ev.target.closest('.dg-node[data-node][tabindex]');
    if (!node) return;
    ev.preventDefault();
    node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });

  // ---- Tooltip das tendências (sparklines) -----------------------------
  const tip = document.createElement('div');
  tip.className = 'spark-tip';
  tip.hidden = true;
  document.body.appendChild(tip);

  function fmt(v, unit) {
    if (unit === '%') return `${v.toFixed(0)}%`;
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(i ? 1 : 0)} ${units[i]}/s`;
  }

  document.addEventListener('mousemove', (ev) => {
    const spark = ev.target.closest && ev.target.closest('.spark');
    if (!spark) { tip.hidden = true; return; }
    const values = spark.dataset.values.split(',').map(Number);
    const rect = spark.getBoundingClientRect();
    const idx = Math.round(((ev.clientX - rect.left) / rect.width) * (values.length - 1));
    const i = Math.max(0, Math.min(values.length - 1, idx));
    const ago = values.length - 1 - i;
    tip.textContent = `${fmt(values[i], spark.dataset.unit)} · ${ago === 0 ? 'agora' : `-${ago * 10}s`}`;
    tip.style.left = `${ev.clientX + 12}px`;
    tip.style.top = `${ev.clientY - 30}px`;
    tip.hidden = false;
  });

  // ---- Atualização ao vivo ---------------------------------------------
  const live = document.getElementById('live-root');
  const updatedEl = document.querySelector('[data-updated]');
  let lastUpdate = Date.now();
  let inFlight = false;

  function restoreHelp() {
    ui.openHelp.forEach((key) => {
      const text = document.querySelector(`[data-help-text="${key}"]`);
      const btn = document.querySelector(`[data-help="${key}"]`);
      if (text) text.hidden = false;
      if (btn) btn.setAttribute('aria-expanded', 'true');
    });
  }

  async function refresh() {
    if (!live || inFlight || document.hidden || document.body.classList.contains('touring')) return;
    inFlight = true;
    try {
      const resp = await fetch(live.dataset.liveUrl, { headers: { 'X-Requested-With': 'fetch' } });
      if (resp.status === 401) { window.location.href = '/login'; return; }
      if (!resp.ok) throw new Error(resp.status);
      live.innerHTML = await resp.text();
      initArch(live);
      restoreHelp();
      lastUpdate = Date.now();
      live.classList.remove('is-stale');
    } catch (e) {
      live.classList.add('is-stale');
      if (updatedEl) updatedEl.textContent = 'sem conexão · tentando de novo';
    } finally {
      inFlight = false;
    }
  }

  function tickLabel() {
    if (!updatedEl || (live && live.classList.contains('is-stale'))) return;
    const s = Math.round((Date.now() - lastUpdate) / 1000);
    updatedEl.textContent = s < 3 ? 'ao vivo · agora' : `ao vivo · ${s}s`;
  }

  initArch(document);
  if (live) {
    const interval = Number(live.dataset.interval) || 10000;
    setInterval(refresh, interval);
    setInterval(tickLabel, 1000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
    const btn = document.querySelector('[data-refresh-now]');
    if (btn) btn.addEventListener('click', refresh);
  }
})();

// ---- Guia do painel (balões) ------------------------------------------
// Abre sozinho com ?tour=1 (fim do onboarding) ou na primeira visita;
// o botão "Guia" reabre. Pausa a atualização ao vivo enquanto está aberto,
// para o elemento destacado não ser trocado no meio do passo.
(function () {
  'use strict';
  const STEPS = [
    { sel: '[data-tour="overview"]', title: 'Resumo', text: 'Como está o sistema agora: problemas, pontos de atenção e erros recentes.' },
    { sel: '[data-tour="map"] .diagram-wrap', title: 'Mapa', text: 'Cada caixa é uma parte do seu sistema. Clique em uma para ver os detalhes.' },
    { sel: '[data-node="tracepilot"]', title: 'Conexão', text: 'Mostra se os dados estão chegando e por onde: TracePilot Collector, TracePilot API ou os dois.' },
    { sel: '[data-tour="resources"]', title: 'Recursos', text: 'Uso da máquina em tempo real. O ? explica cada indicador.' },
    { sel: '[data-tour="alerts"]', title: 'Alertas', text: 'O que precisa de atenção e o que fazer. Amarelo avisa antes de virar problema.' },
    { sel: '[data-tour="investigate"]', title: 'Investigar com IA', text: 'Descreva o problema com suas palavras. A IA encontra a causa e sugere a correção.' },
    { sel: '[data-tour="history"]', title: 'Histórico', text: 'Investigações anteriores, com o resultado de cada uma.' },
    { sel: '[data-tour="live"]', title: 'Ao vivo', text: 'O painel se atualiza sozinho a cada 10 segundos.' },
  ];
  const SEEN_KEY = 'tp-tour-seen';
  if (!document.querySelector('[data-tour]')) return;

  let steps = [];
  let i = 0;
  let spot, pop;

  function build() {
    spot = document.createElement('div');
    spot.className = 'tour-spot';
    pop = document.createElement('div');
    pop.className = 'tour-pop';
    pop.setAttribute('role', 'dialog');
    pop.innerHTML = '<span class="label tour-count"></span><h3 class="tour-title"></h3><p class="tour-text"></p>'
      + '<div class="tour-actions"><button type="button" class="link-button" data-tour-skip>Pular</button>'
      + '<span><button type="button" class="btn-line btn-sm" data-tour-prev>Anterior</button> '
      + '<button type="button" class="btn-sm" data-tour-next>Próximo</button></span></div>';
    document.body.append(spot, pop);
    pop.querySelector('[data-tour-skip]').onclick = end;
    pop.querySelector('[data-tour-prev]').onclick = () => go(i - 1);
    pop.querySelector('[data-tour-next]').onclick = () => (i === steps.length - 1 ? end() : go(i + 1));
  }

  function place() {
    const el = document.querySelector(steps[i].sel);
    if (!el) return;
    // Coordenadas do documento (position: absolute), não da janela: o
    // balão acompanha a rolagem sem precisar recalcular.
    const r = el.getBoundingClientRect();
    const sx = window.scrollX;
    const sy = window.scrollY;
    const pad = 6;
    Object.assign(spot.style, {
      top: `${r.top + sy - pad}px`, left: `${r.left + sx - pad}px`,
      width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
    });
    const pw = pop.offsetWidth;
    const ph = pop.offsetHeight;
    const below = r.bottom + 14 + ph < window.innerHeight;
    const top = below ? r.bottom + 14 : Math.max(12, r.top - ph - 14);
    const left = Math.min(Math.max(12, r.left), document.documentElement.clientWidth - pw - 12);
    Object.assign(pop.style, { top: `${top + sy}px`, left: `${left + sx}px` });
  }

  function go(n) {
    i = Math.max(0, Math.min(steps.length - 1, n));
    const s = steps[i];
    pop.querySelector('.tour-count').textContent = `${i + 1} de ${steps.length}`;
    pop.querySelector('.tour-title').textContent = s.title;
    pop.querySelector('.tour-text').textContent = s.text;
    pop.querySelector('[data-tour-prev]').disabled = i === 0;
    pop.querySelector('[data-tour-next]').textContent = i === steps.length - 1 ? 'Concluir' : 'Próximo';
    const el = document.querySelector(s.sel);
    const r = el.getBoundingClientRect();
    if (r.top < 80 || r.bottom > window.innerHeight - 160) {
      window.scrollTo({ top: window.scrollY + r.top - Math.max(90, (window.innerHeight - r.height) / 3), behavior: 'instant' });
    }
    place();
    pop.querySelector('[data-tour-next]').focus();
  }

  function start() {
    steps = STEPS.filter((s) => document.querySelector(s.sel));
    if (!steps.length) return;
    if (!spot) build();
    document.body.classList.add('touring');
    spot.hidden = false;
    pop.hidden = false;
    go(0);
  }

  function end() {
    document.body.classList.remove('touring');
    spot.hidden = true;
    pop.hidden = true;
    try { localStorage.setItem(SEEN_KEY, '1'); } catch (e) { /* sem storage: só não lembra */ }
  }

  window.addEventListener('resize', () => { if (document.body.classList.contains('touring')) place(); });
  document.addEventListener('keydown', (ev) => {
    if (!document.body.classList.contains('touring')) return;
    if (ev.key === 'Escape') end();
    if (ev.key === 'ArrowRight') go(i + 1);
    if (ev.key === 'ArrowLeft') go(i - 1);
  });
  document.addEventListener('click', (ev) => { if (ev.target.closest('[data-tour-start]')) start(); });

  let seen = false;
  try { seen = localStorage.getItem(SEEN_KEY) === '1'; } catch (e) { seen = false; }
  const params = new URLSearchParams(window.location.search);
  if (params.get('tour') === '1' || !seen) {
    if (params.get('tour')) history.replaceState(null, '', window.location.pathname);
    setTimeout(start, 400);
  }
})();
