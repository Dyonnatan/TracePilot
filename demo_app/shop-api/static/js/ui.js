import { api, sessionId, track } from './api.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const ERROR_TITLE = 'Não consegui concluir a operação.';
const ERROR_TEXT = 'Tente novamente em alguns instantes. Se o problema continuar, reporte para o nosso time.';
export const INSTALLMENTS = 10;
export const PIX_DISCOUNT_PCT = 5;

/** Cria elementos sem innerHTML: strings viram nós de texto. */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'class') el.className = value;
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, value);
  }
  el.append(...children.flat().filter((child) => child !== null && child !== undefined && child !== false));
  return el;
}

export function icon(name, size = 'md', extraClass = '') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', `icon icon-${size} ${extraClass}`.trim());
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#i-${name}`);
  svg.append(use);
  return svg;
}

const moneyFormat = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
export const money = (cents) => moneyFormat.format(cents / 100);
export const installment = (cents) => `ou ${INSTALLMENTS}x de ${money(Math.round(cents / INSTALLMENTS))} sem juros`;
export const pixPrice = (cents) => Math.round(cents * (1 - PIX_DISCOUNT_PCT / 100));
export const orderCode = (orderId) => `#AS-${String(orderId).padStart(6, '0')}`;
export const plural = (count, singular, pluralForm) => `${count} ${count === 1 ? singular : pluralForm}`;
const ratingFormat = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export function rating(product) {
  return h(
    'p',
    { class: 'rating', 'aria-label': `Nota ${ratingFormat.format(product.rating)} de 5, ${product.reviews_count} avaliações` },
    icon('star', 'sm', 'icon-filled'),
    h('span', { 'aria-hidden': 'true' }, `${ratingFormat.format(product.rating)} (${product.reviews_count})`),
  );
}

export function stockBadge(stock) {
  if (stock === 0) return h('span', { class: 'badge badge-neutral' }, 'Esgotado');
  if (stock <= 3) return h('span', { class: 'badge badge-warning' }, `Últimas ${stock} unidades`);
  return null;
}

export function stockText(stock) {
  if (stock === 0) return h('p', { class: 'stock stock-out' }, 'Produto esgotado');
  if (stock <= 3) return h('p', { class: 'stock stock-low' }, `Últimas ${stock} unidades em estoque`);
  return h('p', { class: 'stock' }, icon('check', 'sm'), 'Em estoque — envio em até 24h');
}

export function skeleton(className) {
  return h('div', { class: `skeleton ${className}`, 'aria-hidden': 'true' });
}

export function setLoading(button, loading) {
  button.classList.toggle('is-loading', loading);
  button.disabled = loading;
  button.setAttribute('aria-busy', String(loading));
}

export function stepper({ value, max, label, onChange }) {
  const input = h('input', {
    type: 'number', class: 'stepper-input', min: 1, max, value, 'aria-label': label, inputmode: 'numeric',
  });
  const minus = h('button', { type: 'button', class: 'stepper-btn', 'aria-label': 'Diminuir quantidade' }, icon('minus', 'sm'));
  const plus = h('button', { type: 'button', class: 'stepper-btn', 'aria-label': 'Aumentar quantidade' }, icon('plus', 'sm'));

  const set = (next) => {
    const clamped = Math.min(Math.max(Number.isFinite(next) ? next : 1, 1), max);
    input.value = clamped;
    minus.disabled = clamped <= 1;
    plus.disabled = clamped >= max;
    return clamped;
  };
  set(value);
  minus.addEventListener('click', () => onChange?.(set(Number(input.value) - 1)));
  plus.addEventListener('click', () => onChange?.(set(Number(input.value) + 1)));
  input.addEventListener('change', () => onChange?.(set(Math.trunc(Number(input.value)))));

  const el = h('div', { class: 'stepper' }, minus, input, plus);
  el.value = () => Number(input.value);
  return el;
}

function copyButton(text) {
  const label = h('span', {}, 'Copiar código');
  const button = h('button', { type: 'button', class: 'btn btn-secondary btn-sm' }, icon('copy', 'sm'), label);
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return;
    }
    button.classList.add('is-copied');
    button.replaceChildren(icon('check', 'sm'), h('span', {}, 'Copiado'));
    setTimeout(() => {
      button.classList.remove('is-copied');
      button.replaceChildren(icon('copy', 'sm'), label);
    }, 2000);
  });
  return button;
}

/** Alerta inline persistente usado em todos os pontos de falha da loja. */
export function errorAlert({ traceId, step, onRetry }) {
  const code = traceId
    ? h(
        'div',
        { class: 'support-code' },
        h('span', { class: 'support-label' }, 'Código de suporte'),
        h(
          'div',
          { class: 'support-row' },
          h(
            'code',
            { class: 'mono support-value', title: traceId },
            h('span', { class: 'code-full' }, traceId),
            h('span', { class: 'code-short', 'aria-hidden': 'true' }, `${traceId.slice(0, 8)}…${traceId.slice(-4)}`),
          ),
          copyButton(traceId),
        ),
      )
    : null;

  return h(
    'div',
    { class: 'alert alert-danger', role: 'alert' },
    icon('alert', 'md', 'alert-icon'),
    h(
      'div',
      { class: 'alert-content' },
      h('p', { class: 'alert-title' }, ERROR_TITLE),
      h('p', {}, ERROR_TEXT),
      code,
      h(
        'div',
        { class: 'alert-actions' },
        h('button', { type: 'button', class: 'btn btn-primary btn-sm', onclick: () => openReport({ traceId, step }) }, 'Reportar problema'),
        onRetry ? h('button', { type: 'button', class: 'btn-link', onclick: onRetry }, icon('refresh', 'sm'), 'Tentar novamente') : null,
      ),
    ),
  );
}

/** Substitui o conteúdo de slot pelo alerta de erro e registra o evento de jornada. */
export function showError(slot, error, step, onRetry) {
  track('error_shown', { step, status: error.status || 0, trace_id: error.traceId || '' });
  slot.replaceChildren(errorAlert({ traceId: error.traceId, step, onRetry }));
}

// Diálogo "Reportar problema" (markup em index.html).
const reportDialog = document.getElementById('report-dialog');
const reportForm = document.getElementById('report-form');
const reportDone = document.getElementById('report-done');
const reportCodeField = document.getElementById('report-code-field');
const reportCode = document.getElementById('report-code');
const reportMessage = document.getElementById('report-message');
const reportError = document.getElementById('report-error');
const reportSubmit = document.getElementById('report-submit');
let reportContext = { traceId: null, step: 'help' };

export function openReport({ traceId = null, step = 'help' } = {}) {
  reportContext = { traceId, step };
  track('report_opened', { step, trace_id: traceId || '' });
  reportForm.hidden = false;
  reportDone.hidden = true;
  reportError.hidden = true;
  reportMessage.value = '';
  reportCodeField.hidden = !traceId;
  reportCode.value = traceId || '';
  reportDialog.showModal();
  reportMessage.focus();
}

reportForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setLoading(reportSubmit, true);
  reportError.hidden = true;
  try {
    const { ticket } = await api('/support/report', {
      method: 'POST',
      body: {
        session_id: sessionId,
        message: reportMessage.value,
        trace_id: reportContext.traceId,
        page: location.hash || '#/',
      },
    });
    track('report_sent', { step: reportContext.step, ticket });
    document.getElementById('report-ticket').textContent = ticket;
    reportForm.hidden = true;
    reportDone.hidden = false;
    reportDone.querySelector('[data-close]').focus();
  } catch {
    reportError.textContent = 'Não foi possível enviar o relato agora. Tente novamente.';
    reportError.hidden = false;
  } finally {
    setLoading(reportSubmit, false);
  }
});

/** Fecha diálogos pelo botão [data-close] ou pelo clique no backdrop. */
export function wireDialog(dialog) {
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
  });
}

wireDialog(reportDialog);
