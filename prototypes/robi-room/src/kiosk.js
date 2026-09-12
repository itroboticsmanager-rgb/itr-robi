import { ContentTree, Navigation, readSnapshot } from './content.js';
import { createContentScreen } from './menu.js';
import { element, icon } from './icons.js';
import { createBannerArt } from './banners.js';

const $ = s => document.querySelector(s);

export function createKiosk({ pauseScene, mascot }) {
  let tree = new ContentTree(), nav = new Navigation(tree);
  let mode = 'home', token = '', dismissed = '', deadline = Infinity, timeout = 45;
  let pending = false, localOnly = false, connected = false, lastActivity = 0, generation = 0;
  let contentKey = '', bannersKey = '', items = [], index = 0, previous = -1;
  let lastBannerContent = '';
  let carouselTime = 0, carouselPaused = false, launcherPage = 0;
  let carouselResumeWithFocus = false;
  const screen = createContentScreen($('#screens'), nav, { onClose: () => close(), onActivity: activity, onQr: id => openQr(id) });
  const qr = element('section', 'qr-screen'); qr.hidden = true; qr.setAttribute('aria-label', 'QR-код');
  const qrBar = element('header', 'content-bar'), qrClose = element('button', 'secondary-button', 'На головну');
  qrBar.append(element('span', 'content-brand', 'ITRobotics'), qrClose);
  const qrBody = element('div', 'qr-body'), qrCopy = element('div', 'qr-copy');
  const qrTitle = element('h1'), qrTimer = element('p', 'qr-timer'), qrCode = element('div', 'qr-code');
  qrTitle.tabIndex = -1;
  qrCopy.append(element('p', 'section-kicker', 'ОДИН ПРОСТИЙ КРОК'), qrTitle, element('p', '', 'Наведіть камеру телефона на код. Посилання відкриється на вашому телефоні.'), qrTimer);
  qrBody.append(qrCopy, qrCode); qr.append(qrBar, qrBody); $('#screens').append(qr);
  qrClose.addEventListener('click', close);
  qr.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
  let returnFocus = null;
  let returnNode = '', returnPage = 0, returnTimer;

  function setMode(next, node = '', display = {}) {
    const returning = mode !== 'home' && next === 'home';
    if (mode === 'home' && next !== 'home') {
      returnFocus = document.activeElement;
      returnNode = returnFocus?.dataset?.node ?? '';
      returnPage = launcherPage;
    }
    if (next !== 'info') screen.hide();
    if (next !== 'qr') { qr.hidden = true; qrCode.replaceChildren(); }
    mode = next;
    syncBannerMotion();
    if (next === 'info') screen.show(node);
    if (next === 'qr') {
      if (!drawQR(display.qr)) { next = 'home'; mode = 'home'; }
      else {
        qrTitle.textContent = display.title || 'Продовжимо на телефоні'; qr.hidden = false;
        qrTitle.focus({ preventScroll: true });
      }
    }
    $('#home').inert = next !== 'home';
    pauseScene(next === 'info' || next === 'qr');
    document.body.dataset.screen = mode;
    if (returning) {
      launcherPage = returnPage; renderLauncher();
      const button = [...$('#launcher').children].find(b => b.dataset.node === returnNode);
      (button ?? (returnFocus?.isConnected && !returnFocus.closest('[hidden]') ? returnFocus : $('#motion'))).focus({ preventScroll: true });
      clearTimeout(returnTimer);
      if (button) {
        button.classList.add('just-returned');
        returnTimer = setTimeout(() => button.classList.remove('just-returned'), 2000);
      }
      returnFocus = null;
    }
  }

  function drawQR(matrix) {
    if (!Array.isArray(matrix) || matrix.length < 21 || matrix.length > 177 || matrix.some(r => !Array.isArray(r) || r.length !== matrix.length || r.some(v => v !== 0 && v !== 1))) return false;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    const size = matrix.length + 8; svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'QR-код для відкриття на телефоні'); svg.setAttribute('shape-rendering', 'crispEdges');
    const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('fill', '#102f52');
    let d = ''; matrix.forEach((row, y) => row.forEach((v, x) => { if (v) d += `M${x + 4} ${y + 4}h1v1h-1z`; }));
    path.setAttribute('d', d); svg.append(path); qrCode.replaceChildren(svg); return true;
  }

  function renderLauncher() {
    const root = tree.node(tree.root), all = (root?.items ?? []).filter(id => tree.visible(id));
    // Один ряд кнопок, завжди (D-061): другий ряд забирав би висоту банера.
    // Що не влазить у ряд, іде на наступну сторінку через «Ще розділи».
    const perRow = 5, paged = all.length > perRow, pageSize = paged ? perRow - 1 : perRow;
    launcherPage = Math.min(launcherPage, Math.max(0, Math.ceil(all.length / pageSize) - 1));
    const shown = all.slice(launcherPage * pageSize, (launcherPage + 1) * pageSize);
    const count = shown.length + (paged ? 1 : 0), launcher = $('#launcher'); launcher.replaceChildren();
    launcher.style.setProperty('--cols', Math.max(1, count));
    launcher.style.setProperty('--rows', 1);
    // Чотири-п'ять кнопок у ряд — тісно: стрілку прибираємо, щоб підпис не рвався посеред слова.
    launcher.classList.toggle('dense', count > 3);
    function launcherButton(iconName, label) {
      const button = element('button', 'launcher-button');
      const badge = element('span', 'launcher-icon'); badge.append(icon(iconName));
      const arrow = icon('next'); arrow.classList.add('launcher-arrow');
      button.append(badge, element('span', 'launcher-label', label), arrow);
      return button;
    }
    for (const id of shown) {
      const button = launcherButton(tree.iconFor(id), tree.labelFor(id));
      // Колір напряму з CRM: той самий, що на сайті й у Схемі курсів.
      const accent = tree.node(id)?.accent;
      if (typeof accent === 'string' && /^#[0-9a-f]{6}$/.test(accent)) {
        button.style.setProperty('--accent', accent); button.classList.add('has-accent');
      }
      button.dataset.node = id;
      button.addEventListener('click', () => (tree.isQr(id) ? openQr(id) : open('info', id))); launcher.append(button);
    }
    if (paged) {
      const more = launcherButton('grid', 'Ще розділи');
      more.addEventListener('click', () => { launcherPage = (launcherPage + 1) % Math.ceil(all.length / pageSize); renderLauncher(); }); launcher.append(more);
    }
    // Порожній ряд прибирається, а його місце займає підказка тієї ж висоти.
    launcher.hidden = all.length === 0;
    $('#content-empty').hidden = all.length > 0;
  }

  function renderBanners(banners) {
    // Лише банери з CRM. Власних «запасних» кіоск не має: що бачать батьки
    // в холі, вирішує школа, а не код. Немає банерів — немає й каруселі.
    items = Array.isArray(banners) ? banners.slice(0, 12) : [];
    index = Math.min(index, Math.max(0, items.length - 1)); previous = -1; carouselTime = 0;
    $('.showcase').hidden = items.length === 0;
    $('#home').classList.toggle('no-banners', items.length === 0);
    const host = $('#banner-slides'); host.replaceChildren(); $('#banner-dots').replaceChildren();
    items.forEach((b, i) => {
      const slide = element('article', 'banner-slide'); slide.setAttribute('aria-label', `${i + 1} з ${items.length}`);
      const copy = element('div', 'banner-copy');
      copy.append(element('p', 'section-kicker', b.topic || 'ITROBOTICS'), element('h2', '', b.title), element('p', '', b.description || ''));
      slide.append(copy);
      if (typeof b.image === 'string' && b.image.startsWith('/media/banner/')) {
        // Uploaded banners are complete artwork; the editorial split is only a fallback.
        slide.classList.add('has-image');
        const img = element('img', 'banner-image'); img.alt = [b.title, b.description].filter(Boolean).join('. '); img.src = b.image;
        img.addEventListener('error', () => { slide.classList.remove('has-image'); img.replaceWith(createBannerArt()); }); slide.append(img);
      } else slide.append(createBannerArt());
      if (typeof b.target_node === 'string' && tree.has(b.target_node)) {
        const action = element('button', 'banner-open');
        action.setAttribute('aria-label', `${b.title}. Відкрити: ${tree.labelFor(b.target_node)}`);
        action.append(element('span', 'banner-open-label', `Відкрити: ${tree.labelFor(b.target_node)}`));
        action.addEventListener('click', () => { if (tree.has(b.target_node)) open('info', b.target_node); });
        slide.append(action);
      }
      host.append(slide);
      const dot = element('button', 'banner-dot'); dot.setAttribute('aria-label', `Банер ${i + 1}: ${b.title}`);
      dot.addEventListener('click', () => changeBanner(i)); $('#banner-dots').append(dot);
    });
    $('#carousel-controls').hidden = items.length < 2;
    $('#carousel-controls').parentElement.hidden = items.length < 2; updateBanner();
  }
  function syncBannerMotion() {
    const reduced = document.documentElement.classList.contains('reduced-motion') || matchMedia('(prefers-reduced-motion: reduce)').matches;
    $('.showcase').classList.toggle('motion-running', mode === 'home' && !document.hidden && !carouselPaused && !reduced);
  }
  function updateBanner() {
    [...$('#banner-slides').children].forEach((slide, i) => {
      slide.classList.toggle('current', i === index); slide.classList.toggle('previous', i === previous);
      slide.setAttribute('aria-hidden', String(i !== index)); slide.inert = i !== index;
    });
    [...$('#banner-dots').children].forEach((dot, i) => dot.setAttribute('aria-current', String(i === index)));
    syncBannerMotion();
  }
  function changeBanner(next) { previous = index; index = (next + items.length) % items.length; carouselTime = 0; updateBanner(); }
  $('#banner-prev').addEventListener('click', () => changeBanner(index - 1));
  $('#banner-next').addEventListener('click', () => changeBanner(index + 1));
  $('#banner-pause').addEventListener('click', () => {
    carouselPaused = !carouselPaused; $('#banner-pause').setAttribute('aria-pressed', String(carouselPaused));
    carouselResumeWithFocus = !carouselPaused;
    $('#banner-pause').textContent = carouselPaused ? 'Продовжити' : 'Пауза'; carouselTime = 0; syncBannerMotion();
  });
  $('.showcase').addEventListener('focusin', e => { if (e.target !== $('#banner-pause')) carouselResumeWithFocus = false; });

  function accept(snapshot, elapsed = 0) {
    if (!snapshot?.display) return;
    connected = true;
    timeout = Number.isFinite(snapshot.idle_timeout_s) ? Math.max(15, snapshot.idle_timeout_s) : 45;
    const ck = JSON.stringify(snapshot.content), bk = JSON.stringify(snapshot.banners);
    if (ck !== contentKey) {
      contentKey = ck; tree = new ContentTree(snapshot); nav.tree = tree; renderLauncher();
      if (mode === 'info' && !tree.has(nav.current?.id)) setMode('home');
    }
    if (bk !== bannersKey || ck !== lastBannerContent) { bannersKey = bk; lastBannerContent = ck; renderBanners(snapshot.banners); }
    mascot(snapshot.mascot?.state ?? 'idle', snapshot.mascot?.gaze);
    const d = snapshot.display;
    if (d.token === dismissed) return;
    const remoteMode = ['home', 'info', 'qr'].includes(d.mode) ? d.mode : 'home';
    if (localOnly && mode !== 'home') return;
    deadline = d.remaining_s == null ? Infinity : performance.now() + Math.max(0, d.remaining_s * 1000 - elapsed);
    if (token !== d.token || mode !== remoteMode) {
      token = d.token;
      if (remoteMode === 'info' && (!tree.available || (d.node && !tree.has(d.node)))) return;
      setMode(remoteMode, d.node, d);
    }
    expire();
  }
  function expire() {
    if (mode !== 'home' && performance.now() >= deadline) {
      dismissed = token; localOnly = false; setMode('home');
    }
  }
  function disconnected() {
    connected = false;
    if (mode === 'qr') { dismissed = token; setMode('home'); }
  }
  let commandIdle = Promise.resolve();
  async function command(payload) {
    if (pending) {
      if (payload.action !== 'close') return null;
      await commandIdle;
      return command(payload);
    }
    pending = true;
    let finish;
    commandIdle = new Promise(resolve => { finish = resolve; });
    generation++;
    try {
      const response = await fetch('/api/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: AbortSignal.timeout(3500) });
      if (!response.ok) throw new Error('unavailable');
      const result = await response.json();
      if (result.ok) { localOnly = false; if (payload.action !== 'activity') dismissed = ''; accept(result.snapshot); }
      return result;
    } catch { disconnected(); return null; }
    finally { pending = false; finish(); }
  }
  async function open(next, node = '') {
    if (pending || next !== 'info') return;
    if (next === 'info' && !tree.available) return;
    const result = await command({ action: 'menu', node });
    if (result === null) {
      localOnly = true; deadline = performance.now() + timeout * 1000; setMode(next, node);
    } else if (!result.ok) notice('Зачекайте мить і спробуйте ще.');
  }
  // Код із меню («Оплатити», D-060). Посилання й перевірку тримає пристрій:
  // сюди приходить лише готова матриця коду у знімку.
  async function openQr(node) {
    if (pending || !tree.visible(node)) return;
    const result = await command({ action: 'qr', node });
    if (result === null) notice('Код зараз недоступний. Зверніться до адміністратора.');
    else if (!result.ok) notice('Зачекайте мить і спробуйте ще.');
  }
  async function close() {
    const old = token; dismissed = old; localOnly = false; setMode('home');
    await command({ action: 'close', token: old });
  }
  function activity() {
    const now = performance.now();
    if (mode === 'home' || mode === 'qr') return;
    if (localOnly) deadline = now + timeout * 1000;
    if (now - lastActivity > 800 && !pending) {
      lastActivity = now;
      if (localOnly && connected) { open(mode, nav.current?.id ?? ''); }
      else if (!localOnly) command({ action: 'activity', token });
    }
  }
  let noticeTimer;
  function notice(text) { $('#notice').textContent = text; $('#notice').hidden = false; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => { $('#notice').hidden = true; }, 3500); }
  async function poll() {
    if (!document.hidden && !pending) {
      const start = performance.now();
      const requestGeneration = generation;
      const state = await readSnapshot((url, opts) => fetch(url, { ...opts, signal: AbortSignal.timeout(2500) }));
      if (!pending && generation === requestGeneration) { if (state?.display) accept(state, performance.now() - start); else disconnected(); }
    }
    setTimeout(poll, 750);
  }
  let tickAt = performance.now();
  setInterval(() => {
    const now = performance.now(), dt = Math.min(300, now - tickAt); tickAt = now;
    expire();
    if (mode === 'qr') qrTimer.textContent = `Код зникне через ${Math.max(0, Math.ceil((deadline - now) / 1000))} с`;
    const reduced = document.documentElement.classList.contains('reduced-motion') || matchMedia('(prefers-reduced-motion: reduce)').matches;
    syncBannerMotion();
    if (mode === 'home' && !document.hidden && !carouselPaused && !reduced && !document.documentElement.classList.contains('mascot-present') && (carouselResumeWithFocus || !$('.showcase').matches(':focus-within')) && items.length > 1) {
      carouselTime += dt;
      if (carouselTime >= 14000) changeBanner(index + 1);
    }
  }, 200);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) expire(); carouselTime = 0; syncBannerMotion(); });
  $('#stage').addEventListener('pointerdown', activity, { passive: true });
  $('#stage').addEventListener('pointermove', e => { if (e.buttons) activity(); }, { passive: true });
  $('#stage').addEventListener('keydown', activity);
  renderBanners([]); renderLauncher(); poll();
  return { close, activity, get mode() { return mode; } };
}
