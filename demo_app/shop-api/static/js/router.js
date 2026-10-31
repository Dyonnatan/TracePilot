const ROUTES = [
  { name: 'product', pattern: /^\/produto\/(\d+)$/ },
  { name: 'checkout', pattern: /^\/checkout$/ },
  { name: 'order', pattern: /^\/pedido\/(\d+)$/ },
  { name: 'catalog', pattern: /^\/?$/ },
];

export function currentRoute() {
  const [path, queryString = ''] = location.hash.replace(/^#/, '').split('?');
  const query = new URLSearchParams(queryString);
  for (const route of ROUTES) {
    const match = path.match(route.pattern);
    if (match) return { name: route.name, id: match[1] ? Number(match[1]) : null, query };
  }
  return { name: 'catalog', id: null, query };
}

export function navigate(hash) {
  if (location.hash === hash) window.dispatchEvent(new HashChangeEvent('hashchange'));
  else location.hash = hash;
}
