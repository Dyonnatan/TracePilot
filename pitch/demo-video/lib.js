// Apoio da gravação: legenda, cursor visível e ritmo. Tudo é injetado na
// página, então aparece no vídeo sem precisar de edição depois.
const OVERLAY = () => {
  if (window.__tpOverlay) return;
  window.__tpOverlay = true;
  const install = () => {
    if (!document.body || document.getElementById('tp-cap')) return;
    const css = document.createElement('style');
    css.textContent = `
      #tp-cap,#tp-chip,#tp-cursor{position:fixed;z-index:2147483647;pointer-events:none;
        font-family:"IBM Plex Sans",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
      #tp-cap{left:50%;transform:translateX(-50%);bottom:34px;max-width:1120px;
        background:rgba(9,12,20,.92);color:#f4f6fb;padding:14px 22px;border-radius:12px;
        font-size:20px;line-height:1.45;box-shadow:0 10px 40px rgba(0,0,0,.45);
        border:1px solid rgba(255,255,255,.12);opacity:0;transition:opacity .35s ease}
      #tp-cap.on{opacity:1}
      #tp-chip{left:28px;bottom:40px;background:rgba(9,12,20,.88);color:#8be9b7;
        border:1px solid rgba(139,233,183,.35);padding:7px 14px;border-radius:999px;
        font-size:13px;letter-spacing:.09em;text-transform:uppercase;font-weight:600;
        opacity:0;transition:opacity .35s ease}
      #tp-chip.on{opacity:1}
      #tp-cursor{left:0;top:0;width:26px;height:26px;margin:-4px 0 0 -4px;
        transition:transform .45s cubic-bezier(.22,.61,.36,1);opacity:0}
      #tp-cursor.on{opacity:1}
      #tp-cursor svg{filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))}
      #tp-cursor.tap::after{content:'';position:absolute;left:-9px;top:-9px;width:40px;height:40px;
        border-radius:50%;border:2px solid #8be9b7;animation:tp-tap .5s ease-out}
      @keyframes tp-tap{from{transform:scale(.2);opacity:.9}to{transform:scale(1.15);opacity:0}}
    `;
    document.head.appendChild(css);
    const cap = document.createElement('div'); cap.id = 'tp-cap';
    const chip = document.createElement('div'); chip.id = 'tp-chip';
    const cur = document.createElement('div'); cur.id = 'tp-cursor';
    cur.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M5 2.5 19 12l-6.2 1.3L9.9 20z" fill="#fff" stroke="#111" stroke-width="1.4" stroke-linejoin="round"/></svg>';
    document.body.append(cap, chip, cur);
    if (window.__tpState) {
      if (window.__tpState.cap) window.__tpSay(window.__tpState.cap);
      if (window.__tpState.chip) window.__tpChip(window.__tpState.chip);
      if (window.__tpState.pos) window.__tpMove(window.__tpState.pos[0], window.__tpState.pos[1]);
    }
  };
  window.__tpState = window.__tpState || { cap: '', chip: '', pos: null };
  window.__tpSay = (t) => {
    window.__tpState.cap = t;
    const el = document.getElementById('tp-cap'); if (!el) return;
    el.textContent = t || ''; el.classList.toggle('on', !!t);
  };
  window.__tpChip = (t) => {
    window.__tpState.chip = t;
    const el = document.getElementById('tp-chip'); if (!el) return;
    el.textContent = t || ''; el.classList.toggle('on', !!t);
  };
  window.__tpMove = (x, y) => {
    window.__tpState.pos = [x, y];
    const el = document.getElementById('tp-cursor'); if (!el) return;
    el.classList.add('on'); el.style.transform = `translate(${x}px, ${y}px)`;
  };
  window.__tpTap = () => {
    const el = document.getElementById('tp-cursor'); if (!el) return;
    el.classList.remove('tap'); void el.offsetWidth; el.classList.add('tap');
  };
  if (document.body) install();
  document.addEventListener('DOMContentLoaded', install);
  new MutationObserver(install).observe(document.documentElement, { childList: true });
};

const PACE = Number(process.env.PACE || 1);
const wait = (page, ms) => page.waitForTimeout(Math.round(ms * PACE));

async function say(page, text, ms = 0) {
  await page.evaluate((t) => window.__tpSay && window.__tpSay(t), text).catch(() => {});
  // ~17 caracteres por segundo de leitura, com um mínimo confortável.
  const hold = ms || Math.max(2200, Math.min(9000, text.length * 58));
  if (hold) await wait(page, hold);
}
const chip = (page, text) => page.evaluate((t) => window.__tpChip && window.__tpChip(t), text).catch(() => {});

async function moveTo(page, locator) {
  const box = await locator.boundingBox();
  if (!box) return null;
  const x = box.x + box.width / 2, y = box.y + Math.min(box.height / 2, 26);
  await page.evaluate(([a, b]) => window.__tpMove && window.__tpMove(a, b), [x, y]).catch(() => {});
  await page.mouse.move(x, y);
  await wait(page, 550);
  return { x, y };
}

// Clique "humano": o cursor anda até o alvo, pisca e só então clica.
async function click(page, locator, { nav = false, pause = 700, force = false } = {}) {
  const target = locator.first();
  await target.scrollIntoViewIfNeeded().catch(() => {});
  await wait(page, 300);
  await moveTo(page, target);
  await page.evaluate(() => window.__tpTap && window.__tpTap()).catch(() => {});
  await wait(page, 220);
  if (nav) {
    await Promise.all([page.waitForLoadState('load').catch(() => {}), target.click({ force, timeout: 15000 })]);
  } else {
    await target.click({ force, timeout: 15000 });
  }
  await wait(page, pause);
}

// Rolagem suave: o vídeo fica legível, diferente do salto do scrollIntoView.
async function scrollBy(page, px, steps = 26) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, px / steps);
    await wait(page, 36);
  }
  await wait(page, 350);
}

async function scrollTo(page, selector) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, selector).catch(() => {});
  await wait(page, 1300);
}

async function type(page, locator, text, { delay = 45 } = {}) {
  await moveTo(page, locator.first());
  await locator.first().click();
  await locator.first().fill('');
  await locator.first().type(text, { delay: Math.round(delay * PACE) });
  await wait(page, 500);
}

module.exports = { OVERLAY, say, chip, click, moveTo, scrollBy, scrollTo, type, wait, PACE };
