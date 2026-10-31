import { api, track } from '../api.js';
import { cart } from '../cart.js';
import { openCart } from '../drawer.js';
import { h, icon, installment, money, pixPrice, plural, rating, showError, skeleton, stockBadge } from '../ui.js';

const SORTS = {
  relevance: { label: 'Relevância', compare: (a, b) => a.id - b.id },
  price_asc: { label: 'Menor preço', compare: (a, b) => a.price_cents - b.price_cents },
  price_desc: { label: 'Maior preço', compare: (a, b) => b.price_cents - a.price_cents },
  rating: { label: 'Melhor avaliados', compare: (a, b) => b.rating - a.rating || b.reviews_count - a.reviews_count },
};
const SKELETON_CARDS = 8;

const normalize = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

export function addToCart(product, quantity, source) {
  cart.add(product, quantity);
  track('cart_add', { product_id: product.id, quantity, source });
  openCart();
}

export function productCard(product) {
  const soldOut = product.stock === 0;
  return h(
    'article',
    { class: soldOut ? 'product-card is-sold-out' : 'product-card' },
    h(
      'div',
      { class: 'card-media' },
      h('img', { src: product.image, alt: '', width: 200, height: 200 }),
      h('div', { class: 'card-badges' }, stockBadge(product.stock)),
    ),
    h(
      'div',
      { class: 'card-body' },
      h('p', { class: 'eyebrow' }, product.category),
      h('h3', { class: 'card-title' }, h('a', { href: `#/produto/${product.id}`, class: 'stretched-link' }, product.name)),
      rating(product),
      h(
        'div',
        { class: 'card-price' },
        h('p', { class: 'price' }, money(product.price_cents)),
        h('p', { class: 'installment' }, installment(product.price_cents)),
        h('p', { class: 'pix-price' }, `${money(pixPrice(product.price_cents))} no Pix`),
      ),
      h(
        'button',
        {
          type: 'button',
          class: 'btn btn-primary btn-block card-cta',
          disabled: soldOut,
          onclick: () => addToCart(product, 1, 'catalog'),
        },
        soldOut ? 'Indisponível' : 'Adicionar ao carrinho',
      ),
    ),
  );
}

function skeletonCard() {
  return h(
    'div',
    { class: 'product-card is-skeleton', 'aria-hidden': 'true' },
    skeleton('skeleton-media'),
    h(
      'div',
      { class: 'card-body' },
      skeleton('skeleton-line skeleton-30'),
      skeleton('skeleton-line skeleton-85'),
      skeleton('skeleton-line skeleton-60'),
      skeleton('skeleton-line skeleton-40'),
      skeleton('skeleton-price'),
      skeleton('skeleton-button'),
    ),
  );
}

export function renderCatalog(main, route) {
  let products = null;
  let search = route.query.get('q') || '';
  let category = route.query.get('categoria') || '';
  let sort = SORTS[route.query.get('ordem')] ? route.query.get('ordem') : 'relevance';

  const count = h('p', { class: 'result-count', 'aria-live': 'polite' });
  const chips = h('div', { class: 'chips', role: 'group', 'aria-label': 'Categorias' });
  const sortSelect = h(
    'select',
    { id: 'sort', class: 'input select' },
    Object.entries(SORTS).map(([value, { label }]) => h('option', { value, selected: value === sort }, label)),
  );
  sortSelect.addEventListener('change', () => {
    sort = sortSelect.value;
    update();
  });
  const grid = h('div', { class: 'product-grid' });

  main.replaceChildren(
    h(
      'section',
      { class: 'hero' },
      h('h1', {}, 'Setup de trabalho, sem excesso.'),
      h('p', { class: 'text-secondary' }, 'Periféricos e acessórios selecionados para uma mesa limpa e produtiva.'),
    ),
    h(
      'div',
      { class: 'toolbar' },
      chips,
      h('div', { class: 'sort' }, h('label', { for: 'sort', class: 'text-secondary text-sm' }, 'Ordenar por'), sortSelect),
    ),
    count,
    grid,
  );

  function syncUrl() {
    const query = new URLSearchParams();
    if (search) query.set('q', search);
    if (category) query.set('categoria', category);
    if (sort !== 'relevance') query.set('ordem', sort);
    const hash = query.toString() ? `#/?${query}` : '#/';
    if (location.hash !== hash) history.replaceState(null, '', hash);
  }

  function renderChips() {
    const categories = [...new Set(products.map((product) => product.category))];
    chips.replaceChildren(
      ...['', ...categories].map((value) =>
        h(
          'button',
          {
            type: 'button',
            class: 'chip',
            'aria-pressed': String(value === category),
            onclick: () => {
              category = value;
              update();
            },
          },
          value || 'Todos',
        ),
      ),
    );
  }

  function update() {
    syncUrl();
    if (!products) return;
    renderChips();
    const term = normalize(search.trim());
    const visible = products
      .filter((product) => !category || product.category === category)
      .filter((product) => !term || normalize(`${product.name} ${product.category}`).includes(term))
      .sort(SORTS[sort].compare);

    count.textContent = search ? `${plural(visible.length, 'produto', 'produtos')} para “${search}”` : plural(visible.length, 'produto', 'produtos');
    if (visible.length === 0) {
      grid.replaceChildren(
        h(
          'div',
          { class: 'empty-state' },
          icon('search', 'lg'),
          h('p', { class: 'empty-title' }, 'Nenhum produto encontrado'),
          h('p', { class: 'text-secondary' }, 'Tente outro termo ou veja todas as categorias.'),
          h(
            'button',
            {
              type: 'button',
              class: 'btn btn-secondary',
              onclick: () => {
                search = '';
                category = '';
                document.getElementById('search-input').value = '';
                update();
              },
            },
            'Limpar filtros',
          ),
        ),
      );
      return;
    }
    grid.replaceChildren(...visible.map(productCard));
  }

  async function load() {
    count.textContent = '';
    grid.setAttribute('aria-busy', 'true');
    grid.replaceChildren(...Array.from({ length: SKELETON_CARDS }, skeletonCard));
    try {
      products = await api('/products');
      update();
    } catch (error) {
      const slot = h('div', { class: 'page-alert' });
      grid.replaceChildren(slot);
      showError(slot, error, 'load_products', load);
    } finally {
      grid.removeAttribute('aria-busy');
    }
  }

  load();

  return {
    setSearch(value) {
      search = value;
      update();
    },
  };
}
