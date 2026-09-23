import { element, icon } from './icons.js';
import { createLightbox, createReel, createStage, mediaOf, mediaSummary, reducedMotion } from './gallery.js';

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

export const coursesLabel = n => `${n} ${plural(n, 'курс', 'курси', 'курсів')}`;

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

// Великий напівпрозорий знак напряму в куті — те, що робить плитку впізнаваною
// здалеку, ще до того, як прочитано назву.
function watermark(name, className) {
  const mark = element('span', className);
  mark.append(icon(name));
  return mark;
}

function badge(name, className) {
  const b = element('span', className);
  b.append(icon(name));
  return b;
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
  const head = element('div', 'content-head');
  const body = element('div', 'content-body');
  root.append(bar, head, body, element('p', 'content-help', 'Потрібна порада? Наш адміністратор поруч.')); host.append(root);
  let page = 0;
  // Таймери й відео поточної сторінки: сторінка, яку покинули, не має грати далі.
  const disposers = [];
  let stage = null;
  const lightbox = createLightbox(root, { onActivity, onClose: index => stage?.resume(index) });

  function dispose() {
    lightbox.hide();
    for (const fn of disposers.splice(0)) fn();
    stage = null;
  }
  function close() { dispose(); root.hidden = true; navigation.exit(); onClose?.(); }
  home.addEventListener('click', close);
  back.addEventListener('click', () => { page = 0; if (navigation.back()) close(); else render(); });
  root.addEventListener('pointerdown', () => onActivity?.(), { passive: true });
  root.addEventListener('keydown', e => { onActivity?.(); if (e.key === 'Escape') { e.stopPropagation(); close(); } });

  // Сцена курсу займає рівно видиму висоту: мініатюри під нею не мають ховатися за край.
  const measure = () => { if (!root.hidden) root.style.setProperty('--room', `${body.clientHeight}px`); };
  addEventListener('resize', measure, { passive: true });

  function go(id) { page = 0; if (navigation.open(id)) render(); }
  function openGallery(items, index) { stage?.pause(); lightbox.show(items, index); }

  // Плитка розділу або напряму: знак і колір напряму з CRM, вік, кількість
  // курсів і, якщо є, світлина з занять, що проступає з правого краю.
  function menuItem(id, index) {
    const child = navigation.tree.node(id);
    const button = withAccent(child, element('button', 'content-item'));
    button.style.setProperty('--i', index);
    const iconName = navigation.tree.iconFor(id);
    const courses = (child?.items ?? []).filter(i => navigation.tree.visible(i));
    const photo = [child, ...courses.map(i => navigation.tree.node(i))]
      .flatMap(node => mediaOf(node)).find(m => m.kind === 'image' || m.poster);
    if (photo) {
      const img = element('img', 'tile-photo');
      img.alt = ''; img.decoding = 'async'; img.src = photo.kind === 'image' ? photo.url : photo.poster;
      img.addEventListener('error', () => { img.remove(); button.classList.remove('has-photo'); }, { once: true });
      button.append(img); button.classList.add('has-photo');
    }
    button.append(watermark(iconName, 'tile-mark'), badge(iconName, 'tile-badge'));
    const copy = element('span', 'tile-copy');
    copy.append(element('span', 'item-label', navigation.tree.labelFor(id)));
    const meta = element('span', 'tile-meta');
    const age = ageLabel(child?.age_min, child?.age_max);
    if (age) meta.append(element('small', 'tile-chip', `Для дітей ${age}`));
    if (courses.length > 1 && courses.every(i => navigation.tree.isCard(i))) meta.append(element('small', 'tile-count', coursesLabel(courses.length)));
    if (meta.childElementCount) copy.append(meta);
    button.append(copy, badge('next', 'tile-go'));
    // Кнопка-код («Оплатити») не сторінка меню, а екран коду — його показує кіоск.
    button.addEventListener('click', () => (navigation.tree.isQr(id) ? onQr?.(id) : go(id)));
    return button;
  }

  // Картка курсу в напрямі: обкладинка з позначкою галереї, назва, для кого,
  // скільки коштує. Курс без власної іконки чи кольору виглядає як свій напрям.
  function courseItem(id, parent, index) {
    const child = navigation.tree.node(id);
    const look = { icon: child?.icon || parent?.icon, accent: child?.accent || parent?.accent };
    const button = withAccent(look, element('button', 'course-item'));
    button.style.setProperty('--i', index);
    const cover = element('span', 'course-cover');
    const art = () => { const a = element('span', 'cover-art'); a.append(icon(look.icon)); return a; };
    const img = contentImage(child, 'course-cover-image');
    if (img) { img.addEventListener('error', () => img.replaceWith(art())); cover.append(img); }
    else cover.append(art());
    const media = mediaOf(child).filter(m => m.url !== child?.image);
    if (media.length) {
      const tag = element('span', 'cover-tag');
      tag.append(icon(media.some(m => m.kind === 'video') ? 'play' : 'images'), element('span', '', mediaSummary(media)));
      cover.append(tag);
    }
    const copy = element('span', 'course-copy');
    copy.append(element('strong', '', navigation.tree.labelFor(id)));
    const meta = [ageLabel(child?.age_min, child?.age_max), durationLabel(child?.duration_months)].filter(Boolean).join(' · ');
    if (meta) copy.append(element('span', 'course-meta', meta));
    const foot = element('span', 'course-foot');
    if (child?.price) foot.append(element('span', 'course-price', child.price));
    foot.append(badge('next', 'course-go'));
    copy.append(foot);
    button.append(cover, copy);
    button.addEventListener('click', () => go(id));
    return button;
  }

  // Напрям: шапка в його кольорі, стрічка фото й відео з занять, далі курси.
  function renderPathway(node, items) {
    const hero = withAccent(node, element('header', 'pathway-hero'));
    const copy = element('div', 'hero-copy');
    const age = ageLabel(node.age_min, node.age_max);
    eyebrow.textContent = age ? `НАПРЯМ · ДЛЯ ДІТЕЙ ${age.toUpperCase()}` : 'НАПРЯМ';
    copy.append(eyebrow, heading);
    if (node.body) copy.append(element('p', 'pathway-intro', prose(node.body)));
    hero.append(watermark(node.icon, 'hero-mark'), badge(node.icon, 'hero-badge'), copy);
    body.append(hero);

    const media = mediaOf(node);
    if (media.length) {
      const section = withAccent(node, element('section', 'pathway-gallery'));
      const title = element('h2', 'section-title');
      title.append(icon(media.some(m => m.kind === 'video') ? 'play' : 'images'), element('span', '', 'Як проходять заняття'));
      section.append(title, createReel(media, { onOpen: i => openGallery(media, i) }));
      body.append(section);
    }

    const shown = items.slice(page * 10, page * 10 + 10);
    const section = element('section', 'pathway-courses');
    if (items.length > 1) section.append(element('h2', 'section-title', 'Курси напряму'));
    const list = withAccent(node, element('div', 'course-list'));
    list.dataset.count = String(Math.min(shown.length, 3));
    shown.forEach((id, i) => list.append(courseItem(id, node, i)));
    section.append(list);
    body.append(section);
  }

  function renderMenu(node) {
    const items = (node.items ?? []).filter(id => navigation.tree.visible(id));
    // Меню, де всі пункти — картки, це напрям із курсами, а не розділ.
    if (items.length > 0 && items.every(id => navigation.tree.isCard(id))) renderPathway(node, items);
    else {
      eyebrow.textContent = 'ОБИРАЙТЕ, ЩО ВАМ ЦІКАВО';
      const grid = element('div', 'content-grid');
      const count = Math.min(items.length, 10);
      grid.style.setProperty('--cols', count <= 3 ? Math.max(1, count) : Math.ceil(count / 2));
      items.slice(page * 10, page * 10 + 10).forEach((id, i) => grid.append(menuItem(id, i)));
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

  // Курс: зліва сцена з фото й відео, що гортаються самі, справа — все, що
  // питають батьки: для кого, чого навчиться, скільки коштує.
  function renderCard(node) {
    const parent = navigation.tree.node(navigation.stack[navigation.stack.length - 2]);
    eyebrow.textContent = parent && parent.id !== navigation.tree.root ? `КУРС · ${parent.title.toUpperCase()}` : 'КУРС';
    const look = { icon: node.icon || parent?.icon, accent: node.accent || parent?.accent };
    const card = withAccent(look, element('article', 'course-page'));
    const visual = element('div', 'course-visual');
    const media = mediaOf(node);
    if (media.length) {
      const current = createStage(media, { onOpen: i => openGallery(media, i) });
      stage = current;
      disposers.push(() => current.destroy());
      visual.append(current.element);
    } else {
      const art = element('div', 'course-art');
      art.append(watermark(look.icon, 'art-mark'), badge(look.icon, 'hero-badge'));
      visual.append(art);
    }

    const info = element('div', 'course-info');
    info.append(eyebrow, heading);
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
    if (node.price) {
      const price = element('div', 'price-row');
      price.append(element('p', 'content-price', node.price), element('p', 'price-note', 'Записатися й підібрати групу допоможе адміністратор.'));
      info.append(price);
    }
    if (!node.body && !node.price && !highlights.length) info.append(element('p', 'content-text', 'Розкажемо більше на рецепції.'));
    card.append(visual, info);
    body.append(card);
  }

  function render() {
    const node = navigation.current;
    if (!node) { close(); return; }
    dispose();
    heading.textContent = node.title; body.replaceChildren(); body.scrollTop = 0;
    // Заголовок живе вгорі, а сторінки напряму й курсу забирають його у свій
    // макет. Повертаємо на місце щоразу, щоб наступна сторінка почала з чистого.
    head.append(eyebrow, heading);
    if (node.kind === 'menu') renderMenu(node); else renderCard(node);
    head.hidden = !head.childElementCount;
    measure();
    root.dataset.page = node.kind === 'card' ? 'course' : body.querySelector('.pathway-hero') ? 'pathway' : 'menu';
    heading.focus({ preventScroll: true });
    if (!reducedMotion()) {
      body.animate([{ opacity: 0, transform: `translateX(${navigation.direction * 18}px)` }, { opacity: 1, transform: 'translateX(0)' }], { duration: 230, easing: 'cubic-bezier(.22,1,.36,1)' });
    }
  }
  return { get open() { return !root.hidden; }, show(node = '') {
    // Той самий вузол, що вже на екрані, — це пристрій підтвердив відкрите
    // меню, а не новий перехід: людина посеред галереї чи відео не має
    // опинитися на початку сторінки.
    if (!root.hidden && node && navigation.current?.id === node) return true;
    if (!navigation.enter(node)) return false; page = 0; root.hidden = false; render(); return true;
  }, close, hide() { dispose(); root.hidden = true; navigation.exit(); } };
}
