import { ContentTree, Navigation, readSnapshot } from './content.js';
import { createContentScreen } from './menu.js';
import { element, icon } from './icons.js';
import { createBannerArt } from './banners.js';
import { createFormScreen, WARN_BEFORE_MS } from './form.js';

const $ = s => document.querySelector(s);

export function createKiosk({ pauseScene, mascot }) {
  let tree = new ContentTree(), nav = new Navigation(tree);
  let mode = 'home', token = '', dismissed = '', deadline = Infinity, timeout = 45;
  let pending = false, localOnly = false, connected = false, lastActivity = 0, generation = 0;
  let contentKey = '', bannersKey = '', items = [], index = 0, previous = -1;
  let lastBannerContent = '';
  let carouselTime = 0, launcherPage = 0;
  let scannerAvailable = false, scannerRetry = 0;
  const screen = createContentScreen($('#screens'), nav, { onClose: () => close(), onActivity: activity, onQr: id => openQr(id) });
  const qr = element('section', 'qr-screen'); qr.hidden = true; qr.setAttribute('aria-label', 'QR-код');
  const qrBar = element('header', 'content-bar'), qrClose = element('button', 'secondary-button', 'На головну');
  qrBar.append(element('span', 'content-brand', 'ITRobotics'), qrClose);
  const qrBody = element('div', 'qr-body'), qrCopy = element('div', 'qr-copy');
  const qrKicker = element('p', 'section-kicker', 'ОДИН ПРОСТИЙ КРОК');
  const qrTitle = element('h1'), qrInstruction = element('p'), qrTimer = element('p', 'qr-timer'), qrCode = element('div', 'qr-code');
  const wifiDetails = element('dl', 'wifi-details'); wifiDetails.hidden = true;
  const wifiNetwork = element('dd'), wifiPassword = element('dd');
  wifiDetails.append(element('dt', '', 'Назва мережі'), wifiNetwork, element('dt', '', 'Пароль'), wifiPassword);
  qrTitle.tabIndex = -1;
  qrInstruction.textContent = 'Наведіть камеру телефона на код. Посилання відкриється на вашому телефоні.';
  qrCopy.append(qrKicker, qrTitle, qrInstruction, wifiDetails, qrTimer);
  qrBody.append(qrCopy, qrCode); qr.append(qrBar, qrBody); $('#screens').append(qr);
  qrClose.addEventListener('click', close);
  qr.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });

  const scanner = element('section', 'scanner-screen'); scanner.hidden = true; scanner.setAttribute('aria-label', 'Сканер кодів');
  const scannerBar = element('header', 'content-bar'), scannerClose = element('button', 'secondary-button', 'На головну');
  scannerBar.append(element('span', 'content-brand', 'ITRobotics'), scannerClose);
  const scannerBody = element('div', 'scanner-body'), scannerViewport = element('div', 'scanner-viewport');
  const scannerFrame = element('img', 'scanner-frame'); scannerFrame.alt = 'Зображення з камери планшета'; scannerFrame.hidden = true;
  const scannerGuide = element('div', 'scanner-guide'); scannerGuide.setAttribute('aria-hidden', 'true');
  const scannerPlaceholder = element('p', 'scanner-placeholder', 'Вмикаю камеру…');
  scannerViewport.append(scannerFrame, scannerGuide, scannerPlaceholder);
  const scannerCopy = element('div', 'scanner-copy');
  const scannerKicker = element('p', 'section-kicker', 'СКАНЕР ПЛАНШЕТА');
  const scannerTitle = element('h1', '', 'Покажіть код камері'); scannerTitle.tabIndex = -1;
  const scannerInstruction = element('p', '', 'Тримайте QR-код або штрихкод нерухомо в рамці, на відстані 30–40 см: ближче камера не фокусується. Результат з’явиться тут — планшет нічого не відкриватиме автоматично.');
  const scannerStatus = element('p', 'scanner-status', 'Шукаю код…'); scannerStatus.setAttribute('role', 'status');
  const scannerResult = element('div', 'scanner-result'); scannerResult.hidden = true; scannerResult.setAttribute('aria-live', 'polite');
  const scannerFormat = element('span', 'scanner-format'), scannerValue = element('p', 'scanner-value');
  const scannerAgain = element('button', 'primary-button', 'Сканувати ще');
  scannerResult.append(scannerFormat, scannerValue, scannerAgain);
  scannerCopy.append(scannerKicker, scannerTitle, scannerInstruction, scannerStatus, scannerResult);
  scannerBody.append(scannerViewport, scannerCopy); scanner.append(scannerBar, scannerBody); $('#screens').append(scanner);
  scannerClose.addEventListener('click', close);
  scannerAgain.addEventListener('click', scanAgain);
  scanner.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
  scannerFrame.addEventListener('load', () => { scannerFrame.hidden = false; scannerPlaceholder.hidden = true; });
  scannerFrame.addEventListener('error', () => {
    scannerFrame.hidden = true; scannerPlaceholder.hidden = false;
    // Камера відкривається вже після входу в режим, і до того потоку ще
    // немає (404). Пробуємо знову, доки сканер лишається на екрані.
    clearTimeout(scannerRetry); scannerRetry = setTimeout(connectScannerStream, 600);
  });
  function connectScannerStream() {
    if (mode !== 'scanner') return;
    // Один MJPEG-потік замість запиту на кожен кадр: кадр з'являється тієї
    // миті, коли його дала камера, а не на такті таймера сторінки.
    scannerFrame.src = `/media/scanner/stream.mjpg?v=${Date.now()}`;
  }
  // Анкета з CRM (D-065): та сама сторінка CRM у фреймі, ми лише рамка навколо.
  let lastFormActivity = 0, lastSnapshotAt = performance.now();
  const FORM_OFFLINE_MS = 15000;
  const form = createFormScreen($('#screens'), { onClose: () => close(), onActivity: () => formActivity() });
  function formActivity() {
    const now = performance.now();
    if (mode !== 'form' || now - lastFormActivity < 5000) return;
    lastFormActivity = now;
    command({ action: 'activity', token });
  }
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
    if (next !== 'qr') {
      qr.hidden = true; qrCode.replaceChildren(); wifiDetails.hidden = true;
      wifiNetwork.textContent = ''; wifiPassword.textContent = '';
    }
    if (next !== 'form') form.hide();
    if (next !== 'scanner') {
      scanner.hidden = true; scannerFrame.hidden = true; scannerFrame.removeAttribute('src');
      scannerResult.hidden = true; scannerValue.textContent = ''; clearTimeout(scannerRetry);
    }
    mode = next;
    syncBannerMotion();
    if (next === 'info') screen.show(node);
    if (next === 'qr') {
      if (!drawQR(display.qr)) { next = 'home'; mode = 'home'; }
      else {
        const wifi = display.kind === 'wifi';
        qrTitle.textContent = display.title || 'Продовжимо на телефоні'; qr.hidden = false;
        qrKicker.textContent = wifi ? 'WI-FI ДЛЯ ГОСТЕЙ' : 'ОДИН ПРОСТИЙ КРОК';
        qrInstruction.textContent = wifi
          ? 'Наведіть камеру телефона на код, щоб підключитися автоматично.'
          : 'Наведіть камеру телефона на код. Посилання відкриється на вашому телефоні.';
        wifiDetails.hidden = !wifi;
        wifiNetwork.textContent = wifi ? display.network || 'Невідома мережа' : '';
        wifiPassword.textContent = wifi ? display.password || 'Без пароля' : '';
        qrTitle.focus({ preventScroll: true });
      }
    }
    if (next === 'scanner') {
      scanner.hidden = false;
      if (!scannerFrame.getAttribute('src')) connectScannerStream();
      updateScanner(display);
      scannerTitle.focus({ preventScroll: true });
    }
    if (next === 'form') {
      if (!form.show(display.url, display.title)) { next = 'home'; mode = 'home'; }
      else lastFormActivity = 0;
    }
    $('#home').inert = next !== 'home';
    pauseScene(next === 'info' || next === 'qr' || next === 'scanner' || next === 'form');
    document.body.dataset.screen = mode;
    if (returning) {
      launcherPage = returnPage; renderLauncher();
      const button = [...$('#launcher').children].find(b => b.dataset.node === returnNode);
      (button ?? (returnFocus?.isConnected && !returnFocus.closest('[hidden]') ? returnFocus : $('#launcher button'))).focus({ preventScroll: true });
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

  function formatName(value) {
    const names = {
      QR_CODE: 'QR-код', QRCode: 'QR-код', MicroQRCode: 'Micro QR',
      DATA_MATRIX: 'Data Matrix', DataMatrix: 'Data Matrix', Aztec: 'Aztec', PDF417: 'PDF417',
      EAN_13: 'EAN-13', EAN13: 'EAN-13', EAN_8: 'EAN-8', EAN8: 'EAN-8',
      UPC_A: 'UPC-A', UPCA: 'UPC-A', UPC_E: 'UPC-E', UPCE: 'UPC-E',
      CODE_128: 'Code 128', Code128: 'Code 128', CODE_39: 'Code 39', Code39: 'Code 39', ITF: 'ITF',
    };
    return names[value] || String(value || 'Код').replaceAll('_', ' ');
  }

  function updateScanner(display = {}) {
    const state = display.scanner || {}, result = state.result;
    scannerViewport.classList.toggle('has-result', Boolean(result));
    scannerResult.hidden = !result;
    if (result) {
      scannerStatus.textContent = 'Код розпізнано';
      scannerFormat.textContent = formatName(result.format);
      scannerValue.textContent = result.value || '';
      scannerPlaceholder.textContent = 'Код розпізнано';
    } else {
      scannerFormat.textContent = ''; scannerValue.textContent = '';
      if (state.error) {
        scannerStatus.textContent = state.error;
        scannerPlaceholder.textContent = 'Камера недоступна';
      } else if (state.ready) {
        scannerStatus.textContent = 'Шукаю QR-код або штрихкод…';
        scannerPlaceholder.textContent = 'Шукаю код…';
      } else {
        scannerStatus.textContent = 'Вмикаю камеру…';
        scannerPlaceholder.textContent = 'Вмикаю камеру…';
      }
    }
  }

  function renderLauncher() {
    const root = tree.node(tree.root), all = (root?.items ?? []).filter(id => tree.visible(id));
    // Wi-Fi і сканер — локальні постійні дії, а не контент CRM. Вони займають
    // останні місця на кожній сторінці, щоб гість не мусив їх шукати.
    const perRow = 5, fixedCount = scannerAvailable ? 2 : 1;
    const paged = all.length > perRow - fixedCount;
    const pageSize = paged ? perRow - fixedCount - 1 : perRow - fixedCount;
    launcherPage = Math.min(launcherPage, Math.max(0, Math.ceil(all.length / pageSize) - 1));
    const shown = all.slice(launcherPage * pageSize, (launcherPage + 1) * pageSize);
    // Кількість колонок завжди дорівнює фактичній кількості кнопок, включно
    // з постійними локальними кнопками. Інакше остання кнопка створює другий ряд і
    // змінює висоту банерів над лаунчером.
    const count = shown.length + (paged ? 1 : 0) + fixedCount, launcher = $('#launcher'); launcher.replaceChildren();
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
    const wifi = launcherButton('wifi', 'Wi-Fi');
    wifi.classList.add('wifi-launcher');
    wifi.addEventListener('click', () => openWifi(wifi)); launcher.append(wifi);
    if (scannerAvailable) {
      const scan = launcherButton('scan', 'Сканувати код');
      scan.classList.add('scanner-launcher');
      scan.addEventListener('click', () => openScanner(scan)); launcher.append(scan);
    }
    launcher.hidden = false;
    $('#content-empty').hidden = true;
  }

  function renderBanners(banners) {
    // Лише банери з CRM. Власних «запасних» кіоск не має: що бачать батьки
    // в холі, вирішує школа, а не код. Немає банерів — немає й каруселі.
    items = Array.isArray(banners) ? banners.slice(0, 12) : [];
    index = Math.min(index, Math.max(0, items.length - 1)); previous = -1; carouselTime = 0;
    $('.showcase').hidden = items.length === 0;
    $('#home').classList.toggle('no-banners', items.length === 0);
    const host = $('#banner-slides'); host.replaceChildren();
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
    });
    updateBanner();
  }
  function syncBannerMotion() {
    const reduced = document.documentElement.classList.contains('reduced-motion') || matchMedia('(prefers-reduced-motion: reduce)').matches;
    $('.showcase').classList.toggle('motion-running', mode === 'home' && !document.hidden && !reduced);
  }
  function updateBanner() {
    [...$('#banner-slides').children].forEach((slide, i) => {
      slide.classList.toggle('current', i === index); slide.classList.toggle('previous', i === previous);
      slide.setAttribute('aria-hidden', String(i !== index)); slide.inert = i !== index;
    });
    syncBannerMotion();
  }
  function changeBanner(next) { previous = index; index = (next + items.length) % items.length; carouselTime = 0; updateBanner(); }

  function accept(snapshot, elapsed = 0) {
    if (!snapshot?.display) return;
    connected = true; lastSnapshotAt = performance.now();
    timeout = Number.isFinite(snapshot.idle_timeout_s) ? Math.max(15, snapshot.idle_timeout_s) : 45;
    const hadScanner = scannerAvailable;
    scannerAvailable = snapshot.capabilities?.scanner === true;
    const ck = JSON.stringify(snapshot.content), bk = JSON.stringify(snapshot.banners);
    if (ck !== contentKey) {
      contentKey = ck; tree = new ContentTree(snapshot); nav.tree = tree; renderLauncher();
      if (mode === 'info' && !tree.has(nav.current?.id)) setMode('home');
    }
    else if (hadScanner !== scannerAvailable) renderLauncher();
    if (bk !== bannersKey || ck !== lastBannerContent) { bannersKey = bk; lastBannerContent = ck; renderBanners(snapshot.banners); }
    mascot(snapshot.mascot?.state ?? 'idle', snapshot.mascot?.gaze);
    const d = snapshot.display;
    if (d.token === dismissed) return;
    const remoteMode = ['home', 'info', 'qr', 'scanner', 'form'].includes(d.mode) ? d.mode : 'home';
    if (localOnly && mode !== 'home') return;
    deadline = d.remaining_s == null ? Infinity : performance.now() + Math.max(0, d.remaining_s * 1000 - elapsed);
    if (token !== d.token || mode !== remoteMode) {
      token = d.token;
      if (remoteMode === 'info' && (!tree.available || (d.node && !tree.has(d.node)))) return;
      setMode(remoteMode, d.node, d);
    }
    else if (remoteMode === 'scanner') updateScanner(d);
    expire();
  }
  function expire() {
    if (mode !== 'home' && performance.now() >= deadline) {
      dismissed = token; localOnly = false; setMode('home');
    }
  }
  function disconnected() {
    connected = false;
    // Анкету не рвемо через одне повільне опитування: поки Surface вантажить
    // сторінку CRM у фрейм, служба може не встигнути за 2,5 с (12.11.2026 так
    // анкета зникала за секунду). Закриваємо, лише коли служба мовчить довго —
    // тоді строк анкети справді нікому стежити (D-049).
    if (mode === 'form' && performance.now() - lastSnapshotAt < FORM_OFFLINE_MS) return;
    if (mode === 'qr' || mode === 'scanner' || mode === 'form') { dismissed = token; setMode('home'); }
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
  async function openWifi(button) {
    if (pending) return;
    const label = button.querySelector('.launcher-label'), previous = label.textContent;
    button.setAttribute('aria-busy', 'true'); button.setAttribute('aria-disabled', 'true'); label.textContent = 'Перевіряю…';
    try {
      const result = await command({ action: 'wifi' });
      if (result?.ok) return;
      const messages = {
        not_connected: 'Планшет зараз не підключений до Wi-Fi.',
        permission_denied: 'Windows не дозволяє показати пароль. Зверніться до адміністратора.',
        unsupported_security: 'Цю мережу не можна підключити через звичайний QR-код.',
        password_unavailable: 'Пароль цієї мережі недоступний.',
        unsupported_platform: 'Перегляд Wi-Fi доступний на планшеті ROBI.',
        preempted: 'Зачекайте мить і спробуйте ще.',
      };
      notice(messages[result?.reason] || 'Дані Wi-Fi зараз недоступні.');
    } finally {
      button.removeAttribute('aria-busy'); button.removeAttribute('aria-disabled'); label.textContent = previous;
    }
  }
  function scannerAspect() {
    // Показ і приховування в одному завданні не встигають намалюватися, тож
    // вікно прев'ю можна виміряти ще до входу в режим. Сервер вирізає рівно
    // ту частину кадру, яку покаже object-fit: cover, у повній роздільності.
    const wasHidden = scanner.hidden; scanner.hidden = false;
    const { width, height } = scannerViewport.getBoundingClientRect();
    scanner.hidden = wasHidden;
    return width > 0 && height > 0 ? Math.round(width / height * 1000) / 1000 : undefined;
  }
  async function openScanner(button) {
    if (pending) return;
    const label = button.querySelector('.launcher-label'), previous = label.textContent;
    button.setAttribute('aria-busy', 'true'); button.setAttribute('aria-disabled', 'true'); label.textContent = 'Вмикаю…';
    try {
      const result = await command({ action: 'scanner', aspect: scannerAspect() });
      if (result?.ok) return;
      notice(result?.reason === 'scanner_unavailable' ? 'Камера сканера зараз недоступна.' : 'Зачекайте мить і спробуйте ще.');
    } finally {
      button.removeAttribute('aria-busy'); button.removeAttribute('aria-disabled'); label.textContent = previous;
    }
  }
  async function scanAgain() {
    if (pending || mode !== 'scanner') return;
    scannerAgain.disabled = true;
    const result = await command({ action: 'scanner_again', token });
    if (!result?.ok) notice('Не вдалося продовжити сканування. Спробуйте ще раз.');
    scannerAgain.disabled = false;
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
    // У сканері результат має з'явитися одразу, а не через ¾ секунди.
    setTimeout(poll, mode === 'scanner' ? 250 : 750);
  }
  let tickAt = performance.now();
  setInterval(() => {
    const now = performance.now(), dt = Math.min(300, now - tickAt); tickAt = now;
    expire();
    if (mode === 'qr') qrTimer.textContent = `Дані зникнуть через ${Math.max(0, Math.ceil((deadline - now) / 1000))} с`;
    if (mode === 'form') {
      const left = deadline - now;
      if (left > 0 && left < WARN_BEFORE_MS) form.warn(Math.ceil(left / 1000)); else form.calm();
    }
    syncBannerMotion();
    // Кнопок каруселі немає, тож банери гортаються самі завжди, і при
    // зменшеній анімації теж (тоді лише без переходу), інакше кіоск
    // назавжди лишився б на першому банері.
    if (mode === 'home' && !document.hidden && !document.documentElement.classList.contains('mascot-present') && !$('.showcase').matches(':focus-within') && items.length > 1) {
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
