// Interações do TracePilot: diagrama clicável, ajuda "?" dos indicadores,
// tooltip das tendências e atualização ao vivo do painel.
// Tudo por delegação de eventos no `document`, porque o painel troca o
// HTML do miolo a cada atualização e os elementos são recriados.
(function () {
  'use strict';

  // ---- Diagrama: selecionar nó --------------------------------------
  const ui = { selected: null, openHelp: new Set() };

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
    const hint = arch.querySelector('[data-node-hint]');
    if (hint) hint.classList.toggle('hidden', !!key);
    if (scroll && shown) shown.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function initArch(root) {
    (root || document).querySelectorAll('[data-arch]').forEach((arch) => {
      const key = ui.selected || arch.dataset.defaultSelected;
      if (key) selectNode(arch, key, false);
    });
  }

  document.addEventListener('click', (ev) => {
    const node = ev.target.closest('.dg-node[data-node]');
    if (node && node.closest('[data-arch]').querySelector('[data-panel]')) {
      selectNode(node.closest('[data-arch]'), node.dataset.node, true);
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
    tip.textContent = `${fmt(values[i], spark.dataset.unit)} · ${ago === 0 ? 'agora' : `${ago} leitura${ago > 1 ? 's' : ''} atrás`}`;
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
    if (!live || inFlight || document.hidden) return;
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
      if (updatedEl) updatedEl.textContent = 'sem conexão com o painel — tentando de novo…';
    } finally {
      inFlight = false;
    }
  }

  function tickLabel() {
    if (!updatedEl || (live && live.classList.contains('is-stale'))) return;
    const s = Math.round((Date.now() - lastUpdate) / 1000);
    updatedEl.textContent = s < 3 ? 'atualizado agora' : `atualizado há ${s}s`;
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
