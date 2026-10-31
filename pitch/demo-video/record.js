#!/usr/bin/env node
// Gravação da apresentação do TracePilot com Playwright.
// Cada cena vira um vídeo próprio em out/raw — os cortes (✂) do roteiro
// acontecem naturalmente entre uma cena e outra. Depois, compose.sh junta tudo.
//
//   node record.js                 # tudo
//   node record.js 1 2 3           # só as cenas escolhidas
//   PACE=0.5 node record.js        # ensaio rápido
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { chromium } = require('playwright');
const { OVERLAY, say, chip, click, moveTo, scrollBy, scrollTo, type, wait } = require('./lib');

const TP = process.env.TP_URL || 'http://localhost:35739';
const SHOP = process.env.SHOP_URL || 'http://localhost:8088';
const CHAOS = process.env.CHAOS_URL || 'http://localhost:8090';
const OO = process.env.OO_URL || 'http://localhost:5080';
const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(__dirname, 'out');
const RAW = path.join(OUT, 'raw');

const env = (() => {
  const file = path.join(ROOT, '.env');
  const out = {};
  if (fs.existsSync(file)) {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m) out[m[1]] = m[2];
    }
  }
  return out;
})();

const sh = (cmd, args, opts = {}) => new Promise((res) => {
  execFile(cmd, args, { cwd: ROOT, timeout: 240000, ...opts }, (e, so, se) => res({ e, so, se }));
});
const chaos = (name, action) => fetch(`${CHAOS}/api/scenarios/${name}/${action}`, { method: 'POST' })
  .then((r) => r.json()).catch((e) => ({ error: String(e) }));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------------------------------------------------------------- gravação
let browser, wide, narrow;
const made = [];
let seq = 0;

async function ctxWide() {
  if (!wide) {
    wide = await browser.newContext({
      viewport: { width: 1600, height: 900 },
      recordVideo: { dir: RAW, size: { width: 1600, height: 900 } },
      locale: 'pt-BR', timezoneId: 'America/Sao_Paulo',
      permissions: ['clipboard-read', 'clipboard-write'],
    });
    await wide.addInitScript(OVERLAY);
  }
  return wide;
}
async function ctxNarrow() {
  if (!narrow) {
    const state = wide ? await wide.storageState() : undefined;
    narrow = await browser.newContext({
      viewport: { width: 800, height: 900 },
      recordVideo: { dir: RAW, size: { width: 800, height: 900 } },
      locale: 'pt-BR', timezoneId: 'America/Sao_Paulo', storageState: state,
    });
    await narrow.addInitScript(OVERLAY);
  }
  return narrow;
}

// Abre uma página só para esta cena: ao fechar, o vídeo dela fica pronto.
async function scene(name, fn, { narrowCtx = false } = {}) {
  const ctx = narrowCtx ? await ctxNarrow() : await ctxWide();
  const page = await ctx.newPage();
  const label = String(++seq).padStart(2, '0') + '-' + name;
  process.stdout.write(`\n▶ ${label}\n`);
  try {
    await fn(page);
  } catch (err) {
    console.error(`  ✕ ${label}: ${err.message}`);
  }
  const video = page.video();
  await page.close();
  if (video) {
    const src = await video.path();
    const dst = path.join(RAW, `${label}.webm`);
    fs.renameSync(src, dst);
    made.push(dst);
    process.stdout.write(`  ✓ ${path.basename(dst)}\n`);
  }
  return page;
}

// Fecha uma página extra (aberta no meio de uma cena) guardando o vídeo dela.
async function capture(page, label) {
  const video = page.video();
  await page.close();
  if (!video) return;
  const dst = path.join(RAW, `${label}.webm`);
  fs.renameSync(await video.path(), dst);
  process.stdout.write(`  ✓ ${path.basename(dst)}\n`);
}

// ------------------------------------------------------------------ cenas
async function abrir(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await wait(page, 1200);
}

const carrinho = (page) => page.evaluate(() => {
  try { return JSON.parse(localStorage.getItem('apex.cart') || '{}').items || []; } catch (e) { return []; }
});

// Põe um item no carrinho e só segue quando ele realmente está lá — o clique
// sozinho às vezes chega antes de a página hidratar.
async function porNoCarrinho(page, visivel = true) {
  for (let i = 0; i < 4; i++) {
    const botao = page.getByRole('button', { name: /Adicionar ao carrinho/i }).first();
    if (await botao.count()) {
      if (visivel && i === 0) await click(page, botao, { pause: 1500 });
      else { await botao.click({ timeout: 10000 }).catch(() => {}); await wait(page, 1200); }
    }
    if ((await carrinho(page)).length) return true;
    await wait(page, 900);
  }
  return false;
}

// Vai para o checkout pelo carrinho; se a gaveta não estiver aberta, vai direto.
async function irParaCheckout(page) {
  const link = page.getByRole('link', { name: /Finalizar compra/i }).first();
  if (await link.isVisible().catch(() => false)) {
    await click(page, link, { pause: 2000 });
  } else {
    await abrir(page, SHOP + '/#/checkout');
  }
  await page.locator('button:has-text("Finalizar pedido")').first()
    .waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
}

// Garante a sessão do Lucas: cada cena abre uma aba nova e pode cair no login.
async function garantirLogin(page) {
  if (!page.url().startsWith(TP)) await abrir(page, TP + '/dashboard');
  if (!page.url().includes('/login')) return;
  const entrar = page.getByRole('button', { name: /^Entrar$/ });
  if (await entrar.count()) {
    await entrar.click();
    await page.waitForLoadState('load').catch(() => {});
    await wait(page, 1500);
  }
}

// 1 · A proposta: a landing do TracePilot.
async function cenaLanding(page) {
  await abrir(page, TP + '/');
  await chip(page, 'TracePilot');
  await say(page, 'Seu sistema caiu. A gente diz por quê. Esse é o TracePilot.');
  await say(page, 'Ele vigia o site e o servidor, avisa antes de quebrar, aponta falhas de segurança e ataques.');
  await scrollBy(page, 700);
  await say(page, 'Este é o mapa do sistema. Cada caixa é uma parte: usuários, site, banco, servidor.');
  const box = page.locator('.showcase g[data-node="database"]').first();
  if (await box.count()) await click(page, box, { force: true, pause: 1200 });
  await say(page, 'Clicando numa caixa, ele mostra o que está acontecendo ali.');
  await scrollBy(page, 820);
  await say(page, 'Antes: um traceback que só um especialista entende. Depois: a causa em português.');
  await scrollBy(page, 760);
  await say(page, 'Segurança: vulnerabilidades por urgência e tráfego suspeito ao vivo.');
  await scrollBy(page, 760);
  await say(page, 'E duas formas de conectar: o Collector no servidor, ou a API, sem instalar nada.');
}

// 2 · A aplicação de teste, funcionando.
async function cenaLoja(page) {
  await abrir(page, SHOP + '/#/');
  await page.evaluate(() => { try { localStorage.removeItem('apex.cart'); } catch (e) {} });
  await abrir(page, SHOP + '/#/');
  await chip(page, 'Apex Space · loja de teste');
  await say(page, 'Esta é a Apex Space: uma loja online criada com ajuda de IA, do jeito que muita gente cria sistemas hoje.');
  await scrollBy(page, 600);
  await say(page, 'Vitrine, categorias, carrinho, cupom e pagamento. Por trás: API da loja, serviço de pagamento e banco.');
  const chipTeclados = page.getByRole('button', { name: 'Teclados', exact: true });
  if (await chipTeclados.count()) await click(page, chipTeclados);
  await say(page, 'Um gerador de tráfego simula clientes comprando o tempo todo.');
  await click(page, page.getByRole('link', { name: /Teclado mecânico 75%/i }), { nav: true, pause: 1500 });
  await say(page, 'Navegação normal: abro um produto…');
  await porNoCarrinho(page);
  await say(page, '…coloco no carrinho…');
  await irParaCheckout(page);
  await say(page, '…e finalizo o pedido com Pix.');
  await click(page, page.getByRole('button', { name: /Finalizar pedido/i }), { pause: 4000 });
  await say(page, 'Tudo funcionando. Agora imagine que algo quebra às onze da noite de uma sexta-feira.');
}

// 3 · Entrar e configurar: a jornada inteira.
async function cenaConfiguracao(page) {
  await sh('bash', ['-c', 'cp -f workspace/profile.json workspace/profile.gravacao.bak 2>/dev/null || true']);
  await abrir(page, TP + '/login');
  await chip(page, 'Configuração');
  if (page.url().includes('/dashboard')) {
    await say(page, 'Vou refazer a configuração do zero, como se fosse o primeiro acesso.');
    await click(page, page.getByRole('button', { name: /Refazer configuração/i }), { nav: true, pause: 1500 });
  } else {
    await say(page, 'Entro como o Lucas, dono da loja. O login já vem preenchido.');
    await click(page, page.getByRole('button', { name: /^Entrar$/ }), { nav: true, pause: 1800 });
  }
  if (page.url().includes('/dashboard')) {
    await click(page, page.getByRole('button', { name: /Refazer configuração/i }), { nav: true, pause: 1500 });
  }
  // Começa sempre pelo primeiro passo, mesmo que uma gravação anterior tenha
  // parado no meio da jornada.
  await abrir(page, TP + '/onboarding/welcome');
  await say(page, 'O TracePilot guia a configuração em poucos passos.');
  await click(page, page.getByRole('link', { name: /^Começar$/ }), { nav: true, pause: 1200 });

  await say(page, 'Quatro perguntas: nome do sistema, endereço, como foi feito e onde roda.');
  await scrollBy(page, 420);
  await wait(page, 1200);
  await click(page, page.getByRole('button', { name: /Continuar/i }), { nav: true, pause: 2000 });

  await say(page, 'Duas formas de conectar, lado a lado: o Collector no servidor, ou a API na aplicação.');
  await scrollBy(page, 420);
  await say(page, 'A loja já envia pela API com OpenTelemetry, e o Collector já está rodando nesta máquina.');
  await click(page, page.getByRole('link', { name: /Continuar/i }), { nav: true, pause: 1500 });

  await say(page, 'Um ou vários repositórios: a loja e o serviço de pagamentos.');
  await say(page, 'Com o código, ele identifica as tecnologias e já checa a segurança.');
  await click(page, page.getByRole('button', { name: /^Continuar$/ }), { nav: true, pause: 3000 });

  await say(page, 'Conexão: sistema no ar, Collector enviando, API recebendo, armazenamento online.');
  await click(page, page.getByRole('link', { name: /^Continuar$/ }), { nav: true, pause: 1200 });

  await say(page, 'Agora ele analisa a máquina, o sistema e a segurança…');
  // A etapa avança sozinha quando a varredura termina; só entro no lugar dela
  // se demorar demais.
  await page.waitForURL('**/onboarding/summary', { timeout: 180000 }).catch(() => {});
  if (!page.url().includes('/summary')) await abrir(page, TP + '/onboarding/summary');
  await wait(page, 1500);

  await say(page, '…e mostra o que a análise encontrou: máquina, recursos, tecnologias e segurança.');
  await scrollBy(page, 620);
  await say(page, 'E o que corrigir primeiro. Por exemplo: uma senha padrão no banco.');
  const alto = page.locator('details summary').filter({ hasText: /alto|crítico/i }).first();
  if (await alto.count()) {
    await click(page, alto, { pause: 1800 });
    await say(page, 'Cada item diz por que importa, como corrigir, e traz um prompt pronto para a IA.');
  }
  await scrollTo(page, 'form[action="/onboarding/complete"]');
  await click(page, page.getByRole('button', { name: /Iniciar monitoramento/i }), { nav: true, pause: 3000 });
}

// 4 · O painel, com o guia em balões.
// Aqui quem narra é o próprio guia: a legenda só abre e fecha a cena, para
// não competir com o texto dos balões.
async function cenaPainel(page) {
  await abrir(page, TP + '/dashboard?tour=1');
  await garantirLogin(page);
  if (!page.url().includes('tour=1')) await abrir(page, TP + '/dashboard?tour=1');
  await chip(page, 'Painel · monitoramento');
  await say(page, 'Configurado. A partir daqui, o painel mostra o sistema inteiro — e ele mesmo explica cada parte.');
  await say(page, '', 1);
  const next = page.locator('[data-tour-next]');
  await next.waitFor({ state: 'visible', timeout: 15000 }).catch(() => {});
  for (let i = 0; i < 12; i++) {
    if (!(await next.count())) break;
    const texto = await page.locator('.tour-pop .tour-text').textContent().catch(() => '');
    await wait(page, Math.max(2600, Math.min(8000, (texto || '').length * 62)));
    const label = await next.textContent().catch(() => '');
    await click(page, next, { pause: 900 });
    if (/Concluir/i.test(label || '')) break;
  }
  await wait(page, 800);
  await say(page, 'Tudo num lugar só, atualizando sozinho. Agora vamos quebrar alguma coisa.');
}

// 5 · A falha de pagamento: o cliente só vê "não consegui concluir".
async function cenaFalha(page) {
  await abrir(page, CHAOS + '/');
  await chip(page, 'Simulando uma falha real');
  await say(page, 'Este é o painel do apresentador: aqui eu ligo falhas reais no ambiente.');
  const card = page.locator('article.card').filter({ hasText: /Adquirente devolvendo 5XX/i }).first();
  await card.scrollIntoViewIfNeeded().catch(() => {});
  await say(page, 'Vou ligar esta: o processador de pagamentos começa a recusar parte das cobranças.');
  await click(page, card.getByRole('button', { name: /Ligar/i }), { pause: 2500 });
  await say(page, 'Ligado. Nada disto aparece na telemetria: para o TracePilot, é uma falha como outra qualquer.');

  const shop = await page.context().newPage();
  await shop.bringToFront();
  await abrir(shop, SHOP + '/#/');
  await shop.evaluate(() => { try { localStorage.removeItem('apex.cart'); } catch (e) {} });
  await abrir(shop, SHOP + '/#/produto/1');
  await chip(shop, 'Apex Space · cliente');
  await porNoCarrinho(shop);
  await irParaCheckout(shop);
  await say(shop, 'Do outro lado, um cliente tenta fechar o pedido.');
  let falhou = false;
  for (let i = 0; i < 6 && !falhou; i++) {
    await click(shop, shop.getByRole('button', { name: /Finalizar pedido/i }), { pause: 3500 });
    const txt = await shop.locator('#main-content').innerText().catch(() => '');
    falhou = /não consegui|nao consegui|erro/i.test(txt);
    if (!falhou) {
      await abrir(shop, SHOP + '/#/checkout');
      await wait(shop, 800);
    }
  }
  await say(shop, falhou
    ? 'E é isso que ele vê: "não consegui concluir a operação". Sem explicação, sem código, sem log.'
    : 'A falha é intermitente — parte das tentativas passa. É exatamente o tipo de problema difícil de achar.');
  await wait(shop, 1500);
  await capture(shop, '05b-loja-erro');
}

// 6 · Investigar: eu descrevo o problema como um cliente reclamaria.
let investigationId = null;
async function cenaInvestigar(page) {
  await abrir(page, TP + '/dashboard');
  await garantirLogin(page);
  await chip(page, 'TracePilot · investigação');
  await say(page, 'Em segundos o painel acusa: erros nos últimos quinze minutos, e o nó do site muda de cor.');
  await scrollTo(page, '.overview');
  await wait(page, 1500);
  await scrollTo(page, '.investigate-form');
  const texto = 'cliente reclamou que não consegue finalizar a compra, aparece erro ao pagar';
  await type(page, page.locator('textarea[name="error_report"]'), texto, { delay: 28 });
  await say(page, 'Descrevo o problema como um cliente reclamaria. Sem termo técnico, sem código de erro.');
  await click(page, page.locator('.investigate-form button[type="submit"]'), { nav: true, pause: 2500 });
  const m = page.url().match(/investigations\/([a-f0-9]+)/);
  investigationId = m ? m[1] : null;
  await say(page, 'A IA cruza logs, métricas e rastros de todos os serviços. Isso leva de alguns segundos a dois minutos.');
  await wait(page, 1500);
}

// Espera fora do vídeo — é o corte ✂ do roteiro.
async function esperarInvestigacao(id, limiteMs = 300000) {
  if (!id) return null;
  const alvo = Date.now() + limiteMs;
  process.stdout.write('  … aguardando a investigação (corte)\n');
  while (Date.now() < alvo) {
    const r = await fetch(`${TP}/api/investigations/${id}`).then((x) => x.json()).catch(() => null);
    if (r && r.status && r.status !== 'running') return r;
    await sleep(5000);
  }
  return null;
}

// 7 · O resultado: causa, origem, linha do tempo e prompt de correção.
async function cenaResultado(page) {
  const id = investigationId || process.env.INV_ID;
  if (!id) return;
  await abrir(page, `${TP}/investigations/${id}`);
  await garantirLogin(page);
  if (!page.url().includes('/investigations/')) await abrir(page, `${TP}/investigations/${id}`);
  await chip(page, 'A resposta do TracePilot');
  await say(page, 'E aqui está a resposta, em português: a causa, e o que fazer agora.');
  await scrollTo(page, '.decision-card');
  await wait(page, 2500);
  await say(page, 'O erro aparece na loja, mas nasce três saltos abaixo, no serviço de pagamento.');
  await scrollTo(page, '.chain');
  await wait(page, 2500);
  await say(page, 'Ele seguiu o rastro por todos os serviços até a origem, com a exceção exata.');
  await scrollTo(page, '.timeline');
  await wait(page, 2200);
  await say(page, 'A linha do tempo mostra quando começou e o que mudou junto.');
  await scrollTo(page, '.fix-prompt-box');
  await wait(page, 1200);
  await say(page, 'E entrega o prompt pronto para a sua IA corrigir. É só copiar e colar.');
  const copiar = page.locator('.fix-prompt-box .copy-btn');
  if (await copiar.count()) await click(page, copiar, { pause: 2000 });
}

// 8 · Lado a lado: o dado cru e a resposta pronta.
async function cenaComparacao() {
  const id = investigationId || process.env.INV_ID;
  const ctx = await ctxNarrow();
  const left = await ctx.newPage();   // OpenObserve
  const right = await ctx.newPage();  // TracePilot

  // O lado direito carrega primeiro: o login do OpenObserve demora, e a metade
  // direita não pode ficar em branco na tela dividida.
  await right.goto(id ? `${TP}/investigations/${id}` : `${TP}/dashboard`, { waitUntil: 'domcontentloaded' });
  await right.waitForTimeout(2000);
  await chip(right, 'Resposta · TracePilot');
  await say(right, 'A mesma falha, vista dos dois lados.', 1);

  await left.goto(OO + '/web/login', { waitUntil: 'domcontentloaded' });
  await left.waitForTimeout(2500);
  if (left.url().includes('/login')) {
    await left.locator('input[type=email]').fill(env.OPENOBSERVE_USER || '');
    await left.locator('input[type=password]').fill(env.OPENOBSERVE_PASSWORD || '');
    await left.locator('button[type=submit]').click();
    await left.waitForTimeout(6000);
  }
  const sql = 'SELECT _timestamp, service_name, severity, exception_type, body FROM "default" '
    + "WHERE severity = 'ERROR' ORDER BY _timestamp DESC";
  const q = Buffer.from(sql).toString('base64');
  await left.goto(`${OO}/web/logs?stream_type=logs&stream=default&period=1h&refresh=0&sql_mode=true`
    + `&query=${encodeURIComponent(q)}&org_identifier=default&quick_mode=false&show_histogram=true`,
    { waitUntil: 'domcontentloaded' });
  await left.waitForTimeout(9000);
  await chip(left, 'Dado cru · OpenObserve');
  await say(left, 'À esquerda, o dado cru: milhares de linhas. Dá para achar a resposta aqui — se você souber o que procurar.', 1);

  await right.bringToFront();
  await say(right, 'À direita, a mesma informação já lida: a causa, a origem e a correção.', 6000);
  await scrollTo(right, '.decision-card');
  await say(right, 'Um lado é um banco de dados. O outro é uma resposta.', 6000);
  await scrollTo(right, '.chain');
  await right.waitForTimeout(4000);

  for (const [name, p] of [['08a-openobserve', left], ['08b-tracepilot', right]]) {
    const v = p.video();
    await p.close();
    if (v) {
      const dst = path.join(RAW, `${name}.webm`);
      fs.renameSync(await v.path(), dst);
      process.stdout.write(`  ✓ ${path.basename(dst)}\n`);
    }
  }
  seq++;
}

// 9 · Mais dois casos: um deploy que quebra, e um ataque.
async function cenaCenarios(page) {
  await abrir(page, CHAOS + '/');
  await chip(page, 'Outros casos');
  await say(page, 'O ambiente tem outros casos prontos — cada um com o gabarito da causa raiz.');
  await scrollBy(page, 400);
  const card = page.locator('article.card').filter({ hasText: /Deploy 1.1.0/i }).first();
  await card.scrollIntoViewIfNeeded().catch(() => {});
  await moveTo(page, card);
  await say(page, 'Este aqui é um deploy: a versão 1.1.0 da loja, que quebra o cupom de cem por cento.');
  await say(page, 'O painel mostra o comando — e o deploy sobe de verdade, como subiria em produção.');
  const deploy = sh('make', ['deploy-bad'], { cwd: path.join(ROOT, 'demo_app') });
  await wait(page, 10000);
  await deploy;
  await say(page, 'Versão nova no ar. Para o usuário, é só mais uma atualização.');

  const shop = await page.context().newPage();
  await shop.bringToFront();
  await abrir(shop, SHOP + '/#/produto/1');
  await chip(shop, 'Apex Space · cupom');
  await porNoCarrinho(shop);
  const cupomBtn = shop.getByRole('button', { name: /cupom de desconto/i }).first();
  if (await cupomBtn.count()) await click(shop, cupomBtn, { pause: 900 });
  const campo = shop.locator('.coupon-form input, input[placeholder*="DESC10"]').first();
  if (await campo.count()) {
    await type(shop, campo, 'GRATIS100', { delay: 70 });
    for (let i = 0; i < 4; i++) {
      const aplicar = shop.getByRole('button', { name: /Aplicar/i }).first();
      if (!(await aplicar.count())) break;
      await click(shop, aplicar, { pause: 2200 });
      const txt = await shop.locator('body').innerText().catch(() => '');
      if (/não consegui|nao consegui/i.test(txt)) break;
    }
  }
  await say(shop, 'O cliente aplica o cupom e recebe de novo "não consegui concluir a operação".');
  await capture(shop, '09b-loja-cupom');

  await page.bringToFront();
  await say(page, 'E agora um ataque: um robô varrendo a loja atrás de arquivos esquecidos e brechas.');
  await sh('bash', ['scripts/simulate-attack.sh']);
  await wait(page, 8000);
}

// 10 · A reação do TracePilot aos dois casos.
async function cenaReacao(page) {
  await abrir(page, TP + '/dashboard');
  await garantirLogin(page);
  await chip(page, 'A reação do TracePilot');
  await say(page, 'Em segundos, o painel reage aos dois.');
  await scrollTo(page, '[data-tour="threats"]');
  await wait(page, 2500);
  await say(page, 'O ataque: ele separa robô de buscador legítimo, mostra o IP, o que foi tentado e o que fazer.');
  await wait(page, 3000);
  await scrollTo(page, '[data-tour="alerts"]');
  await wait(page, 2000);
  await say(page, 'E o deploy quebrado vira alerta de erro — com o botão de investigar já preenchido.');
  await scrollTo(page, '.investigate-form');
  await type(page, page.locator('textarea[name="error_report"]'),
    'o cupom GRATIS100 dá erro quando o cliente clica em Aplicar', { delay: 26 });
  await click(page, page.locator('.investigate-form button[type="submit"]'), { nav: true, pause: 2500 });
  const m = page.url().match(/investigations\/([a-f0-9]+)/);
  if (m) investigationId = m[1];
  await say(page, 'De novo: descrevo com as minhas palavras e deixo a IA seguir o rastro.');
}

// 11 · O deploy na linha do tempo + fechamento.
async function cenaFechamento(page) {
  const id = investigationId || process.env.INV_ID;
  if (id) {
    await abrir(page, `${TP}/investigations/${id}`);
    await garantirLogin(page);
    if (!page.url().includes('/investigations/')) await abrir(page, `${TP}/investigations/${id}`);
    await chip(page, 'O deploy que quebrou o cupom');
    await say(page, 'E aqui entra o tempo: o erro começou junto com o deploy da versão nova.');
    await scrollTo(page, '.decision-card');
    await wait(page, 2500);
    await scrollTo(page, '.timeline');
    await wait(page, 3000);
    await say(page, 'A linha do tempo liga o deploy da versão 1.1.0 ao erro, e aponta a divisão por zero no cálculo do preço.');
    await scrollTo(page, '.chain');
    await wait(page, 2500);
    await say(page, 'Mesmo sem certeza absoluta, ele não para no "inconclusivo": entrega o melhor palpite, com a confiança.');
  }
  await abrir(page, TP + '/dashboard');
  // O guia já foi mostrado na cena 4; aqui ele só atrapalharia o fechamento.
  await page.evaluate(() => { try { localStorage.setItem('tp-tour-seen', '1'); } catch (e) {} });
  await abrir(page, TP + '/dashboard');
  await chip(page, 'TracePilot');
  await say(page, 'Monitoramento vinte e quatro horas. Aviso antes de quebrar. Segurança. E investigação com IA.');
  await scrollTo(page, '.overview');
  await say(page, 'Que explica em português e entrega a correção pronta.');
  await say(page, 'Para quem cria sistemas com IA e não quer virar especialista em servidor. Isso é o TracePilot.');
  await wait(page, 2000);
}

// ------------------------------------------------------------------ main
const CENAS = {
  1: ['landing', cenaLanding],
  2: ['loja', cenaLoja],
  3: ['configuracao', cenaConfiguracao],
  4: ['painel', cenaPainel],
  5: ['falha', cenaFalha],
  6: ['investigar', cenaInvestigar],
  7: ['resultado', cenaResultado],
  8: ['comparacao', cenaComparacao],
  9: ['cenarios', cenaCenarios],
  10: ['reacao', cenaReacao],
  11: ['fechamento', cenaFechamento],
};

(async () => {
  const pedidas = process.argv.slice(2).filter((a) => /^\d+$/.test(a)).map(Number);
  const lista = pedidas.length ? pedidas : Object.keys(CENAS).map(Number);
  fs.mkdirSync(RAW, { recursive: true });
  browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--force-color-profile=srgb'] });

  for (const n of lista) {
    const [nome, fn] = CENAS[n] || [];
    if (!fn) continue;
    seq = n - 1;
    if (n === 8) { await cenaComparacao(); continue; }
    await scene(nome, fn);
    if (n === 6) await esperarInvestigacao(investigationId);
    if (n === 10) await esperarInvestigacao(investigationId);
  }

  if (wide) await wide.close();
  if (narrow) await narrow.close();
  await browser.close();

  // Volta o ambiente ao normal.
  process.stdout.write('\n⟲ desligando cenários e voltando a versão boa\n');
  for (const s of ['payment_errors', 'coupon_bug']) await chaos(s, 'disable');
  await sh('make', ['deploy-good'], { cwd: path.join(ROOT, 'demo_app') });
  console.log(`\nVídeos em ${RAW}`);
})();
