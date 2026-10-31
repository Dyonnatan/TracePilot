import { track } from './api.js';
import { cart, maxQuantity } from './cart.js';
import { navigate } from './router.js';
import { createSummary } from './summary.js';
import { h, icon, money, plural, stepper, wireDialog } from './ui.js';

const drawer = document.getElementById('cart-drawer');
const title = document.getElementById('cart-title');
const body = document.getElementById('cart-body');
const footer = document.getElementById('cart-footer');
let summary = null;

wireDialog(drawer);

export function openCart() {
  track('cart_view', { items: cart.count() });
  render();
  if (!drawer.open) drawer.showModal();
}

function updateTitle() {
  title.textContent = cart.count() ? `Seu carrinho (${plural(cart.count(), 'item', 'itens')})` : 'Seu carrinho';
}

function render() {
  updateTitle();
  if (cart.items.length === 0) {
    body.replaceChildren(emptyState());
    footer.replaceChildren();
    footer.hidden = true;
    return;
  }
  body.replaceChildren(h('ul', { class: 'cart-items', 'aria-label': 'Itens do carrinho' }, cart.items.map(cartItem)));
  summary = createSummary({ step: 'cart', showShippingBar: true });
  footer.hidden = false;
  footer.replaceChildren(
    summary.el,
    h('a', { href: '#/checkout', class: 'btn btn-primary btn-lg btn-block', onclick: () => drawer.close() }, 'Finalizar compra'),
  );
  summary.refresh();
}

function cartItem(item) {
  const lineTotal = h('p', { class: 'cart-item-price' }, money(item.price_cents * item.quantity));
  return h(
    'li',
    { class: 'cart-item' },
    h('img', { src: item.image, alt: '', width: 64, height: 64, class: 'cart-item-image' }),
    h(
      'div',
      { class: 'cart-item-info' },
      h('a', { href: `#/produto/${item.product_id}`, class: 'cart-item-name', onclick: () => drawer.close() }, item.name),
      h('p', { class: 'text-secondary text-sm' }, `${money(item.price_cents)} cada`),
      h(
        'div',
        { class: 'cart-item-actions' },
        stepper({
          value: item.quantity,
          max: maxQuantity(item.stock),
          label: `Quantidade de ${item.name}`,
          onChange: (quantity) => {
            cart.setQuantity(item.product_id, quantity);
            lineTotal.textContent = money(item.price_cents * quantity);
            updateTitle();
            summary.refresh();
          },
        }),
        h(
          'button',
          {
            type: 'button',
            class: 'btn btn-ghost btn-icon btn-sm',
            'aria-label': `Remover item ${item.name}`,
            onclick: () => {
              cart.remove(item.product_id);
              render();
              drawer.querySelector('[data-close]').focus();
            },
          },
          icon('trash', 'sm'),
        ),
      ),
    ),
    lineTotal,
  );
}

function emptyState() {
  return h(
    'div',
    { class: 'empty-state' },
    icon('bag', 'lg'),
    h('p', { class: 'empty-title' }, 'Seu carrinho está vazio'),
    h('p', { class: 'text-secondary' }, 'Que tal conhecer os periféricos para montar o seu setup?'),
    h(
      'button',
      {
        type: 'button',
        class: 'btn btn-primary',
        onclick: () => {
          drawer.close();
          navigate('#/');
        },
      },
      'Explorar produtos',
    ),
  );
}
