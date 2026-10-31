import { api } from './api.js';

const CART_KEY = 'apex.cart';
const MAX_QUANTITY = 20;
const events = new EventTarget();
let state = load();

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(CART_KEY));
    if (saved && Array.isArray(saved.items)) return { items: saved.items, coupon: saved.coupon || null };
  } catch {
    // Carrinho corrompido: começa vazio.
  }
  return { items: [], coupon: null };
}

function save() {
  localStorage.setItem(CART_KEY, JSON.stringify(state));
  events.dispatchEvent(new Event('change'));
}

export const maxQuantity = (stock) => Math.min(MAX_QUANTITY, stock);

/** Os itens guardam nome, imagem e preço do momento da adição para exibir o carrinho mesmo se a cotação falhar. */
export const cart = {
  get items() {
    return state.items;
  },
  get coupon() {
    return state.coupon;
  },
  count() {
    return state.items.reduce((total, item) => total + item.quantity, 0);
  },
  add(product, quantity) {
    const existing = state.items.find((item) => item.product_id === product.id);
    const max = maxQuantity(product.stock);
    if (existing) {
      existing.quantity = Math.min(existing.quantity + quantity, max);
      existing.stock = product.stock;
    } else {
      state.items.push({
        product_id: product.id,
        quantity: Math.min(quantity, max),
        name: product.name,
        image: product.image,
        price_cents: product.price_cents,
        stock: product.stock,
      });
    }
    save();
  },
  setQuantity(productId, quantity) {
    const item = state.items.find((entry) => entry.product_id === productId);
    if (item) item.quantity = quantity;
    save();
  },
  remove(productId) {
    state.items = state.items.filter((item) => item.product_id !== productId);
    if (state.items.length === 0) state.coupon = null;
    save();
  },
  setCoupon(code) {
    state.coupon = code || null;
    save();
  },
  clear() {
    state = { items: [], coupon: null };
    save();
  },
  onChange(listener) {
    events.addEventListener('change', listener);
  },
};

export function quoteCart({ coupon = state.coupon, paymentMethod = 'card' } = {}) {
  return api('/cart/quote', {
    method: 'POST',
    body: {
      items: state.items.map(({ product_id, quantity }) => ({ product_id, quantity })),
      coupon,
      payment_method: paymentMethod,
    },
  });
}

export function checkoutCart(paymentMethod) {
  return api('/checkout', {
    method: 'POST',
    body: {
      items: state.items.map(({ product_id, quantity }) => ({ product_id, quantity })),
      coupon: state.coupon,
      payment_method: paymentMethod,
    },
  });
}
