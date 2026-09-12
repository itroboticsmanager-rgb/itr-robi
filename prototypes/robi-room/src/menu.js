import { element, icon } from './icons.js';

// Колір напряму чи курсу приходить з CRM і вже перевірений на пристрої, але
// в CSS-змінну він іде лише як `#rrggbb` — удруге перевірити дешевше, ніж
// пояснювати, звідки на екрані взявся чужий рядок.
const ACCENT = /^#[0-9a-f]{6}$/;

function plural(n, one, few, many) {
  const tens = n % 100, units = n % 10;
  if (tens >= 11 && tens <= 14) return many;
  if (units === 1) return one;
  if (units >= 2 && units <= 4) return few;
  return many;
}

const genitiveYears = n => (n % 10 === 1 && n % 100 !== 11 ? 'року' : 'років');

// Одиночний перенос у тексті — це ширина поля, в якому його набирали, а не
// думка автора. На екрані він лише рве рядок; абзацом лишається порожній рядок.
const prose = text => String(text ?? '').replace(/\r\n?/g, '\n').replace(/([^\n])\n(?!\n)/g, '$1 ').trim();

/** «6–8 років», «від 12 років». Вік — перше, що питають батьки. */
export function ageLabel(min, max) {
  const lo = Number.isInteger(min) ? min : null, hi = Number.isInteger(max) ? max : null;
  if (lo != null && hi != null) return `${lo}–${hi} ${plural(hi, 'рік', 'роки', 'років')}`;
  if (lo != null) return `від ${lo} ${genitiveYears(lo)}`;
  if (hi != null) return `до ${hi} ${genitiveYears(hi)}`;
  return '';
}

export function durationLabel(months) {
  return Number.isInteger(months) && months > 0 ? `${months} ${plural(months, 'місяць', 'місяці', 'місяців')}` : '';
}

function withAccent(node, target) {
  if (typeof node?.accent === 'string' && ACCENT.test(node.accent)) {
    target.style.setProperty('--accent', node.accent);
    target.classList.add('has-accent');
  }
  return target;
}

function contentImage(node, className) {
  if (typeof node?.image !== 'string' || !node.image.startsWith('/media/content/')) return null;
  const img = element('img', className);
  img.alt = ''; img.src = node.image; img.decoding = 'async';
  return img;
}

export function createContentScreen(host, navigation, { onClose, onActivity, onQr } = {}) {
  const root = element('section', 'content-screen'); root.hidden = true;
  root.setAttribute('aria-label', 'Інформація ITRobotics');
  const bar = element('header', 'content-bar');
  const back = element('button', 'secondary-button'); back.append(icon('back'), element('span', '', 'Назад'));
  const home = element('button', 'secondary-button'); home.append(icon('home'), element('span', '', 'На головну'));
  bar.append(back, element('span', 'content-brand', 'ITRobotics'), home);
  const heading = element('h1', 'content-title'); heading.tabIndex = -1;
  const eyebrow = element('p', 'section-kicker');
  const body = element('div', 'content-body');
  root.append(bar, eyebrow, heading, body, element('p', 'content-help', 'Потрібна порада? Наш адміністратор поруч.')); host.append(root);
  let page = 0;
  function close() { root.hidden = true; navigation.exit(); onClose?.(); }
  home.addEventListener('click', close);
  back.addEventListener('click', () => { page = 0; if (navigation.back()) close(); else render(); });
  root.addEventListener('pointerdown', () => onActivity?.(), { passive: true });
  root.addEventListener('keydown', e => { onActivity?.(); if (e.key === 'Escape') { e.stopPropagation(); close(); } });

  function go(id) { page = 0; if (navigation.open(id)) render(); }

  // Плитка розділу або напряму: іконка в кольорі напряму, назва й вік.
  function menuItem(id) {
    const child = navigation.tree.node(id);
    const button = withAccent(child, element('button', 'content-item'));
    button.append(icon(navigation.tree.iconFor(id)), element('span', 'item-label', navigation.tree.labelFor(id)));
    const age = ageLabel(child?.age_min, child?.age_max);
    if (age) button.append(element('small', 'item-note', `Для дітей ${age}`));
    button.append(icon('next'));
    // Кнопка-код («Оплатити») не сторінка меню, а екран коду — його показує кіоск.
    button.addEventListener('click', () => (navigation.tree.isQr(id) ? onQr?.(id) : go(id)));
    return button;
  }

  // Рядок курсу в напрямі: обкладинка, назва, для кого, скільки коштує.
  // Курс без власної іконки чи кольору виглядає як свій напрям.
  function courseItem(id, parent) {
    const child = navigation.tree.node(id);
    const look = { icon: child?.icon || parent?.icon, accent: child?.accent || parent?.accent };
    const button = withAccent(look, element('button', 'course-item'));
    const thumb = element('span', 'course-thumb');
    const img = contentImage(child, 'course-thumb-image');
    if (img) { img.addEventListener('error', () => img.replaceWith(icon(look.icon))); thumb.append(img); }
    else thumb.append(icon(look.icon));
    const copy = element('span', 'course-copy');
    copy.append(element('strong', '', navigation.tree.labelFor(id)));
    const meta = [ageLabel(child?.age_min, child?.age_max), durationLabel(child?.duration_months)].filter(Boolean).join(' · ');
    if (meta) copy.append(element('span', 'course-meta', meta));
    button.append(thumb, copy);
    if (child?.price) button.append(element('span', 'course-price', child.price));
    button.append(icon('next'));
    button.addEventListener('click', () => go(id));
    return button;
  }

  function renderMenu(node) {
    const items = (node.items ?? []).filter(id => navigation.tree.visible(id));
    // Меню, де всі пункти — картки, це напрям із курсами, а не розділ.
    const courses = items.length > 0 && items.every(id => navigation.tree.isCard(id));
    const age = ageLabel(node.age_min, node.age_max);
    eyebrow.textContent = courses ? (age ? `НАПРЯМ · ДЛЯ ДІТЕЙ ${age.toUpperCase()}` : 'НАПРЯМ') : 'ОБИРАЙТЕ, ЩО ВАМ ЦІКАВО';
    if (node.body) body.append(element('p', 'pathway-intro', prose(node.body)));
    const shown = items.slice(page * 10, page * 10 + 10);
    if (courses) {
      const list = withAccent(node, element('div', 'course-list'));
      for (const id of shown) list.append(courseItem(id, node));
      body.append(list);
    } else {
      const grid = element('div', 'content-grid');
      const count = Math.min(items.length, 10);
      grid.style.setProperty('--cols', count <= 3 ? Math.max(1, count) : Math.ceil(count / 2));
      for (const id of shown) grid.append(menuItem(id));
      body.append(grid);
    }
    if (items.length > 10) {
      const pager = element('div', 'menu-pager');
      for (const [label, delta] of [['Попередні', -1], ['Наступні', 1]]) {
        const b = element('button', 'secondary-button', label);
        b.disabled = page + delta < 0 || (page + delta) * 10 >= items.length;
        b.addEventListener('click', () => { page += delta; render(); }); pager.append(b);
      }
      body.append(pager);
    }
    if (!items.length) body.append(element('p', 'content-text', 'Деталі підкаже адміністратор.'));
  }

  function renderCard(node) {
    eyebrow.textContent = 'КУРС';
    const parent = navigation.tree.node(navigation.stack[navigation.stack.length - 2]);
    const look = { icon: node.icon || parent?.icon, accent: node.accent || parent?.accent };
    const card = withAccent(look, element('article', 'course-page'));
    const visual = element('div', 'course-visual');
    const art = () => { const a = element('div', 'course-art'); a.append(icon(look.icon)); return a; };
    const img = contentImage(node, 'course-image');
    if (img) { img.addEventListener('error', () => img.replaceWith(art())); visual.append(img); }
    else visual.append(art());

    const info = element('div', 'course-info');
    const facts = [ageLabel(node.age_min, node.age_max), durationLabel(node.duration_months)].filter(Boolean);
    if (facts.length) {
      const list = element('ul', 'course-facts');
      for (const fact of facts) list.append(element('li', '', fact));
      info.append(list);
    }
    if (node.body) info.append(element('p', 'content-text', prose(node.body)));
    const highlights = Array.isArray(node.highlights) ? node.highlights.filter(h => typeof h === 'string' && h) : [];
    if (highlights.length) {
      const block = element('section', 'course-highlights');
      const list = element('ul');
      for (const text of highlights) { const li = element('li'); li.append(icon('check'), element('span', '', text)); list.append(li); }
      block.append(element('h2', '', 'Чого навчиться дитина'), list);
      info.append(block);
    }
    if (node.price) info.append(element('p', 'content-price', node.price));
    if (!node.body && !node.price && !highlights.length) info.append(element('p', 'content-text', 'Розкажемо більше на рецепції.'));
    card.append(visual, info);
    body.append(card);
  }

  function render() {
    const node = navigation.current;
    if (!node) { close(); return; }
    heading.textContent = node.title; body.replaceChildren(); body.scrollTop = 0;
    if (node.kind === 'menu') renderMenu(node); else renderCard(node);
    heading.focus({ preventScroll: true });
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches && !document.documentElement.classList.contains('reduced-motion')) {
      body.animate([{ opacity: 0, transform: `translateX(${navigation.direction * 18}px)` }, { opacity: 1, transform: 'translateX(0)' }], { duration: 230, easing: 'cubic-bezier(.22,1,.36,1)' });
    }
  }
  return { get open() { return !root.hidden; }, show(node = '') {
    if (!navigation.enter(node)) return false; page = 0; root.hidden = false; render(); return true;
  }, close, hide() { root.hidden = true; navigation.exit(); } };
}
