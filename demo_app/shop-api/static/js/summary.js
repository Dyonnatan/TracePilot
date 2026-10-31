import { track } from './api.js';
import { cart, quoteCart } from './cart.js';
import { h, icon, money, setLoading, showError, skeleton } from './ui.js';

const INVALID_COUPON = 'Cupom expirado ou inválido. Verifique o código e tente novamente.';

export function totalsRows(quote) {
  const row = (label, value, className = '') => [h('dt', { class: className }, label), h('dd', { class: className }, value)];
  return [
    ...row('Subtotal', money(quote.subtotal_cents)),
    ...(quote.coupon_discount_cents > 0
      ? row(`Desconto (${quote.coupon})`, `- ${money(quote.coupon_discount_cents)}`, 'is-discount')
      : []),
    ...(quote.pix_discount_cents > 0 ? row('Desconto Pix (5%)', `- ${money(quote.pix_discount_cents)}`, 'is-discount') : []),
    ...row('Frete', quote.shipping_cents ? money(quote.shipping_cents) : 'Grátis'),
    ...row('Total', money(quote.total_cents), 'is-total'),
  ];
}

/**
 * Resumo de valores com cupom, usado no drawer e no checkout. Toda cotação
 * passa por POST /cart/quote; falhas viram o alerta inline com código de suporte.
 */
export function createSummary({ step, showShippingBar = false, onQuote = () => {} }) {
  let paymentMethod = 'card';
  let couponOpen = false;
  let couponDraft = '';
  let couponInvalid = false;
  let requestId = 0;

  const shippingSlot = h('div', { class: 'shipping-progress' });
  const couponSlot = h('div', { class: 'coupon' });
  const alertSlot = h('div', { class: 'summary-alert' });
  const totals = h('dl', { class: 'totals', 'aria-live': 'polite' });
  const savings = h('p', { class: 'savings', hidden: true });
  const el = h('div', { class: 'summary' }, showShippingBar ? shippingSlot : null, couponSlot, alertSlot, totals, savings);

  function renderCoupon() {
    if (cart.coupon) {
      couponSlot.replaceChildren(
        h(
          'div',
          { class: 'coupon-applied' },
          h(
            'span',
            { class: 'chip chip-success' },
            icon('check', 'sm'),
            cart.coupon,
            h('button', { type: 'button', class: 'chip-remove', 'aria-label': `Remover cupom ${cart.coupon}`, onclick: removeCoupon }, icon('x', 'sm')),
          ),
          h('span', { class: 'text-secondary text-sm' }, `Cupom ${cart.coupon} aplicado`),
        ),
      );
      return;
    }
    if (!couponOpen) {
      couponSlot.replaceChildren(
        h(
          'button',
          {
            type: 'button',
            class: 'btn-link',
            onclick: () => {
              couponOpen = true;
              renderCoupon();
              couponSlot.querySelector('input').focus();
            },
          },
          icon('plus', 'sm'),
          'Possui um cupom de desconto?',
        ),
      );
      return;
    }

    const inputId = `coupon-${step}`;
    const errorId = `${inputId}-error`;
    const input = h('input', {
      id: inputId,
      class: couponInvalid ? 'input is-invalid' : 'input',
      type: 'text',
      maxlength: 32,
      autocomplete: 'off',
      autocapitalize: 'characters',
      placeholder: 'Ex.: DESC10',
      'aria-invalid': couponInvalid ? 'true' : null,
      'aria-describedby': couponInvalid ? errorId : null,
      oninput: (event) => {
        couponDraft = event.target.value;
      },
    });
    input.value = couponDraft;
    const apply = h('button', { type: 'submit', class: 'btn btn-secondary' }, 'Aplicar');
    couponSlot.replaceChildren(
      h(
        'form',
        {
          class: 'coupon-form',
          onsubmit: (event) => {
            event.preventDefault();
            applyCoupon(apply);
          },
        },
        h('label', { for: inputId }, 'Cupom de desconto'),
        h('div', { class: 'coupon-row' }, input, apply),
        couponInvalid ? h('p', { id: errorId, class: 'field-error' }, icon('alert', 'sm'), INVALID_COUPON) : null,
      ),
    );
  }

  function renderTotals(quote) {
    totals.replaceChildren(...totalsRows(quote));
    savings.hidden = !(quote.economia_cents > 0);
    savings.textContent = savings.hidden ? '' : `Você economizou ${money(quote.economia_cents)} nesta compra.`;

    if (showShippingBar) {
      const missing = quote.free_shipping_threshold_cents - quote.subtotal_cents;
      const progress = Math.min(100, Math.round((quote.subtotal_cents / quote.free_shipping_threshold_cents) * 100));
      shippingSlot.replaceChildren(
        h(
          'p',
          { class: missing > 0 ? 'shipping-text' : 'shipping-text is-free' },
          icon('truck', 'sm'),
          missing > 0 ? `Faltam ${money(missing)} para frete grátis` : 'Você ganhou frete grátis',
        ),
        h('div', { class: 'progress', 'aria-hidden': 'true' }, h('div', { class: 'progress-bar', style: `width: ${progress}%` })),
      );
    }
  }

  function renderTotalsSkeleton() {
    totals.replaceChildren(skeleton('skeleton-line'), skeleton('skeleton-line'), skeleton('skeleton-line skeleton-wide'));
  }

  async function applyCoupon(button) {
    const code = couponDraft.trim();
    if (!code) return;
    track('coupon_apply', { step, coupon: code.toUpperCase() });
    setLoading(button, true);
    await refresh({ coupon: code });
  }

  function removeCoupon() {
    cart.setCoupon(null);
    couponDraft = '';
    couponOpen = false;
    couponInvalid = false;
    renderCoupon();
    refresh();
  }

  async function refresh({ coupon } = {}) {
    const applying = coupon !== undefined;
    const id = ++requestId;
    el.setAttribute('aria-busy', 'true');
    try {
      const quote = await quoteCart({ coupon: applying ? coupon : cart.coupon, paymentMethod });
      if (id !== requestId) return null;
      alertSlot.replaceChildren();
      if (applying) {
        cart.setCoupon(quote.coupon);
        couponInvalid = false;
        couponOpen = false;
        couponDraft = '';
      }
      renderCoupon();
      renderTotals(quote);
      onQuote(quote);
      return quote;
    } catch (error) {
      if (id !== requestId) return null;
      if (error.field === 'coupon') {
        couponInvalid = true;
        couponOpen = true;
        if (!applying) {
          couponDraft = cart.coupon || '';
          cart.setCoupon(null);
          renderCoupon();
          return refresh();
        }
        renderCoupon();
        return null;
      }
      if (totals.querySelector('.skeleton')) totals.replaceChildren();
      showError(alertSlot, error, applying ? 'coupon_apply' : step, () => refresh(applying ? { coupon } : {}));
      if (applying) renderCoupon();
      onQuote(null);
      return null;
    } finally {
      if (id === requestId) el.removeAttribute('aria-busy');
    }
  }

  renderCoupon();
  renderTotalsSkeleton();

  return {
    el,
    refresh,
    setPaymentMethod(method) {
      paymentMethod = method;
      return refresh();
    },
  };
}
