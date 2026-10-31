import { navigate } from '../router.js';
import { totalsRows } from '../summary.js';
import { h, icon, money, orderCode } from '../ui.js';
import { ADDRESS, DELIVERY_ESTIMATE, LAST_ORDER_KEY, PAYMENT_METHODS } from './checkout.js';

function lastOrder(orderId) {
  try {
    const order = JSON.parse(sessionStorage.getItem(LAST_ORDER_KEY));
    return order && order.order_id === orderId ? order : null;
  } catch {
    return null;
  }
}

export function renderOrder(main, route) {
  const order = lastOrder(route.id);
  if (!order) {
    navigate('#/');
    return;
  }

  main.replaceChildren(
    h(
      'section',
      { class: 'confirmation' },
      h('p', { class: 'badge badge-success badge-lg' }, icon('circle-check', 'sm'), 'Pedido confirmado'),
      h('h1', {}, 'Tudo pronto! Seu setup está a caminho.'),
      h('p', { class: 'order-number' }, 'Pedido ', h('strong', { class: 'mono' }, orderCode(order.order_id))),
      order.economia_cents > 0 ? h('p', { class: 'savings' }, `Você economizou ${money(order.economia_cents)} nesta compra.`) : null,
      h(
        'div',
        { class: 'confirmation-grid' },
        h(
          'section',
          { class: 'panel' },
          h('h2', { class: 'panel-title' }, 'Itens'),
          h(
            'ul',
            { class: 'summary-items' },
            order.items.map((item) =>
              h(
                'li',
                {},
                h('img', { src: item.image, alt: '', width: 48, height: 48 }),
                h('span', { class: 'summary-item-name' }, item.name, h('span', { class: 'text-secondary text-sm' }, `${item.quantity} × ${money(item.unit_price_cents)}`)),
                h('span', { class: 'summary-item-total' }, money(item.line_total_cents)),
              ),
            ),
          ),
          h('dl', { class: 'totals' }, totalsRows(order)),
        ),
        h(
          'div',
          { class: 'confirmation-side' },
          h(
            'section',
            { class: 'panel' },
            h('h2', { class: 'panel-title' }, icon('truck', 'md'), 'Entrega'),
            h('p', {}, `${ADDRESS.name} — ${ADDRESS.line}`),
            h('p', { class: 'text-secondary text-sm' }, DELIVERY_ESTIMATE),
          ),
          h(
            'section',
            { class: 'panel' },
            h('h2', { class: 'panel-title' }, icon('card', 'md'), 'Pagamento'),
            h('p', {}, PAYMENT_METHODS[order.payment_method]?.label || order.payment_method),
          ),
        ),
      ),
      h('a', { href: '#/', class: 'btn btn-secondary btn-lg' }, 'Voltar à loja'),
    ),
  );
}
