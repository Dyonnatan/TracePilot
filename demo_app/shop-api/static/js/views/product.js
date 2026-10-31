import { api, track } from '../api.js';
import { maxQuantity } from '../cart.js';
import { h, icon, installment, money, pixPrice, rating, showError, skeleton, stepper, stockText } from '../ui.js';
import { addToCart } from './catalog.js';

const TRUST = [
  ['shield', 'Garantia oficial de 12 meses'],
  ['rotate', '7 dias para devolução'],
  ['truck', 'Envio em até 24h úteis'],
];

function productSkeleton() {
  return h(
    'div',
    { class: 'pdp', 'aria-hidden': 'true' },
    skeleton('skeleton-line skeleton-35 pdp-breadcrumb'),
    h('div', { class: 'pdp-media' }, skeleton('skeleton-media')),
    h(
      'div',
      { class: 'buybox' },
      skeleton('skeleton-title'),
      skeleton('skeleton-title skeleton-60'),
      skeleton('skeleton-price-lg'),
      skeleton('skeleton-line skeleton-50'),
      skeleton('skeleton-button-lg'),
      skeleton('skeleton-row'),
      skeleton('skeleton-row'),
      skeleton('skeleton-row'),
    ),
  );
}

function breadcrumb(product) {
  return h(
    'nav',
    { class: 'breadcrumb pdp-breadcrumb', 'aria-label': 'Trilha de navegação' },
    h(
      'ol',
      {},
      h('li', {}, h('a', { href: '#/' }, 'Início')),
      h('li', {}, h('a', { href: `#/?categoria=${encodeURIComponent(product.category)}` }, product.category)),
      h('li', { 'aria-current': 'page' }, product.name),
    ),
  );
}

function buyControls(product, { compact = false } = {}) {
  if (product.stock === 0) {
    return h('button', { type: 'button', class: 'btn btn-primary btn-lg btn-block', disabled: true }, 'Indisponível');
  }
  const quantity = compact ? null : stepper({ value: 1, max: maxQuantity(product.stock), label: 'Quantidade' });
  const button = h(
    'button',
    {
      type: 'button',
      class: compact ? 'btn btn-primary' : 'btn btn-primary btn-lg buy-button',
      onclick: () => addToCart(product, quantity ? quantity.value() : 1, compact ? 'product_bar' : 'product'),
    },
    icon('cart', 'sm'),
    'Adicionar ao carrinho',
  );
  return compact ? button : h('div', { class: 'buy-row' }, quantity, button);
}

function productPage(product) {
  return h(
    'div',
    { class: 'pdp' },
    breadcrumb(product),
    h(
      'div',
      { class: 'pdp-media' },
      h('img', { src: product.image, alt: product.name, width: 600, height: 600 }),
    ),
    h(
      'div',
      { class: 'buybox' },
      h('p', { class: 'eyebrow' }, product.category),
      h('h1', { class: 'pdp-title' }, product.name),
      rating(product),
      h(
        'div',
        { class: 'pdp-price' },
        h('p', { class: 'price price-lg' }, money(product.price_cents)),
        h('p', { class: 'installment' }, installment(product.price_cents)),
        h('p', { class: 'pix-price' }, `${money(pixPrice(product.price_cents))} no Pix (5% de desconto)`),
      ),
      stockText(product.stock),
      buyControls(product),
      h('ul', { class: 'trust-list' }, TRUST.map(([name, text]) => h('li', {}, icon(name, 'sm'), text))),
    ),
    h(
      'section',
      { class: 'pdp-details' },
      h('h2', {}, 'Sobre o produto'),
      h('p', { class: 'text-secondary' }, product.description),
      h(
        'details',
        { class: 'accordion', open: true },
        h('summary', {}, 'Especificações técnicas', icon('chevron-down', 'sm', 'accordion-icon')),
        h('dl', { class: 'specs' }, product.specs.map(([label, value]) => [h('dt', {}, label), h('dd', {}, value)])),
      ),
    ),
    h(
      'div',
      { class: 'mobile-buy-bar' },
      h('div', {}, h('p', { class: 'price' }, money(product.price_cents)), h('p', { class: 'installment' }, installment(product.price_cents))),
      buyControls(product, { compact: true }),
    ),
  );
}

export function renderProduct(main, route) {
  async function load() {
    main.replaceChildren(productSkeleton());
    try {
      const product = await api(`/products/${route.id}`);
      track('product_view', { product_id: product.id });
      document.title = `${product.name} · Apex Space`;
      main.replaceChildren(productPage(product));
    } catch (error) {
      if (error.status === 404) {
        main.replaceChildren(
          h(
            'div',
            { class: 'empty-state' },
            h('p', { class: 'empty-title' }, 'Produto não encontrado'),
            h('a', { href: '#/', class: 'btn btn-primary' }, 'Voltar à loja'),
          ),
        );
        return;
      }
      const slot = h('div', { class: 'page-alert' });
      main.replaceChildren(slot);
      showError(slot, error, 'load_product', load);
    }
  }
  load();
}
