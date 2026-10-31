import { track } from './api.js';
import { cart } from './cart.js';
import { openCart } from './drawer.js';
import { currentRoute, navigate } from './router.js';
import { openReport, plural } from './ui.js';
import { renderCatalog } from './views/catalog.js';
import { renderCheckout } from './views/checkout.js';
import { renderOrder } from './views/order.js';
import { renderProduct } from './views/product.js';

const main = document.getElementById('main-content');
const searchForm = document.getElementById('search-form');
const searchInput = document.getElementById('search-input');
const cartButton = document.getElementById('cart-button');
const cartCount = document.getElementById('cart-count');
const DEFAULT_TITLE = document.title;

let catalogView = null;
let firstRender = true;

function render() {
  const route = currentRoute();
  document.querySelectorAll('dialog[open]').forEach((dialog) => dialog.close());
  document.body.dataset.route = route.name;
  document.title = DEFAULT_TITLE;
  catalogView = null;
  track('page_view', { route: route.name });

  if (route.name === 'checkout' || route.name === 'order') searchInput.value = '';

  if (route.name === 'product') renderProduct(main, route);
  else if (route.name === 'checkout') renderCheckout(main);
  else if (route.name === 'order') renderOrder(main, route);
  else {
    searchInput.value = route.query.get('q') || '';
    catalogView = renderCatalog(main, route);
  }

  if (!firstRender) {
    window.scrollTo(0, 0);
    main.focus({ preventScroll: true });
  }
  firstRender = false;
}

function updateCartCount() {
  const count = cart.count();
  cartCount.hidden = count === 0;
  cartCount.textContent = String(count);
  cartButton.setAttribute('aria-label', `Carrinho, ${plural(count, 'item', 'itens')}`);
}

searchInput.addEventListener('input', () => catalogView?.setSearch(searchInput.value));
searchForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const term = searchInput.value.trim();
  if (catalogView) catalogView.setSearch(term);
  else navigate(term ? `#/?q=${encodeURIComponent(term)}` : '#/');
});

document.addEventListener('keydown', (event) => {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.closest('input, textarea, select, [contenteditable]') || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  searchInput.focus();
});

cartButton.addEventListener('click', openCart);
document.getElementById('help-button').addEventListener('click', () => openReport({ step: 'help' }));
cart.onChange(updateCartCount);
window.addEventListener('hashchange', render);

updateCartCount();
render();
