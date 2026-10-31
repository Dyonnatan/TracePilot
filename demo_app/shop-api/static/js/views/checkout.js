import { track } from '../api.js';
import { cart, checkoutCart } from '../cart.js';
import { navigate } from '../router.js';
import { createSummary } from '../summary.js';
import { h, icon, money, setLoading, showError } from '../ui.js';

export const ADDRESS = { name: 'Ana Souza', line: 'Rua Augusta, 1500, São Paulo/SP' };
export const DELIVERY_ESTIMATE = 'Previsão: 3 a 5 dias úteis';
export const PAYMENT_METHODS = {
  pix: { label: 'Pix', description: 'Aprovação imediata', badge: '-5%' },
  card: { label: 'Cartão de crédito', description: 'Em até 10x sem juros' },
  boleto: { label: 'Boleto', description: 'Compensação em até 2 dias úteis' },
};
export const LAST_ORDER_KEY = 'apex.lastOrder';

function emptyCheckout() {
  return h(
    'div',
    { class: 'empty-state' },
    icon('bag', 'lg'),
    h('h1', { class: 'empty-title' }, 'Seu carrinho está vazio'),
    h('p', { class: 'text-secondary' }, 'Adicione produtos para finalizar a compra.'),
    h('a', { href: '#/', class: 'btn btn-primary' }, 'Explorar produtos'),
  );
}

function paymentOption(value, method, checked) {
  return h(
    'label',
    { class: 'radio-card' },
    h('input', { type: 'radio', name: 'payment', value, checked }),
    h(
      'span',
      { class: 'radio-card-body' },
      h('span', { class: 'radio-card-title' }, method.label, method.badge ? h('span', { class: 'badge badge-bronze' }, method.badge) : null),
      h('span', { class: 'text-secondary text-sm' }, method.description),
    ),
  );
}

export function renderCheckout(main) {
  track('checkout_view', { items: cart.count() });
  if (cart.items.length === 0) {
    main.replaceChildren(emptyCheckout());
    return;
  }

  let paymentMethod = 'card';
  const alertSlot = h('div', { class: 'checkout-alert' });
  const submit = h('button', { type: 'button', class: 'btn btn-primary btn-lg btn-block', onclick: () => placeOrder() }, 'Finalizar pedido');
  const summary = createSummary({
    step: 'checkout',
    onQuote: (quote) => {
      submit.textContent = quote ? `Finalizar pedido — ${money(quote.total_cents)}` : 'Finalizar pedido';
    },
  });

  const payment = h(
    'fieldset',
    { class: 'panel' },
    h('legend', { class: 'panel-title' }, icon('card', 'md'), 'Pagamento'),
    h('div', { class: 'radio-group' }, Object.entries(PAYMENT_METHODS).map(([value, method]) => paymentOption(value, method, value === paymentMethod))),
  );
  payment.addEventListener('change', (event) => {
    paymentMethod = event.target.value;
    summary.setPaymentMethod(paymentMethod);
  });

  async function placeOrder() {
    track('checkout_attempt', { items: cart.count(), payment_method: paymentMethod, coupon: cart.coupon || '' });
    setLoading(submit, true);
    alertSlot.replaceChildren();
    try {
      const order = await checkoutCart(paymentMethod);
      sessionStorage.setItem(LAST_ORDER_KEY, JSON.stringify(order));
      track('checkout_success', { order_id: order.order_id, payment_method: paymentMethod });
      cart.clear();
      navigate(`#/pedido/${order.order_id}`);
    } catch (error) {
      if (error.field === 'coupon') {
        summary.refresh();
      } else {
        showError(alertSlot, error, 'checkout', () => placeOrder());
        alertSlot.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    } finally {
      setLoading(submit, false);
    }
  }

  main.replaceChildren(
    h('h1', { class: 'page-title' }, 'Finalizar compra'),
    h(
      'div',
      { class: 'checkout-grid' },
      h(
        'div',
        { class: 'checkout-main' },
        h(
          'section',
          { class: 'panel', 'aria-labelledby': 'delivery-title' },
          h('h2', { class: 'panel-title', id: 'delivery-title' }, icon('map-pin', 'md'), 'Entrega'),
          h('p', {}, `Entregar em: ${ADDRESS.name} — ${ADDRESS.line}`),
          h('p', { class: 'text-secondary text-sm' }, DELIVERY_ESTIMATE),
        ),
        payment,
      ),
      h(
        'aside',
        { class: 'panel checkout-summary', 'aria-labelledby': 'summary-title' },
        alertSlot,
        h('h2', { class: 'panel-title', id: 'summary-title' }, 'Resumo da compra'),
        h(
          'ul',
          { class: 'summary-items' },
          cart.items.map((item) =>
            h(
              'li',
              {},
              h('img', { src: item.image, alt: '', width: 48, height: 48 }),
              h('span', { class: 'summary-item-name' }, item.name, h('span', { class: 'text-secondary text-sm' }, `${item.quantity} × ${money(item.price_cents)}`)),
              h('span', { class: 'summary-item-total' }, money(item.price_cents * item.quantity)),
            ),
          ),
        ),
        summary.el,
        submit,
        h('p', { class: 'secure-note' }, icon('lock', 'sm'), 'Pagamento processado com criptografia de ponta a ponta'),
        h('p', { class: 'payment-marks', 'aria-label': 'Aceitamos Pix, Visa, Mastercard e boleto' }, 'Pix · Visa · Mastercard · Boleto'),
      ),
    ),
  );
  summary.refresh();
}
