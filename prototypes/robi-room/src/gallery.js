import { element, icon } from './icons.js';

// Галерея напряму чи курсу (D-063): фото й переважно вертикальні відео з
// занять. Адреси — лише локальні `/media/content/…`, які віддає пристрій зі
// свого кешу; усе інше відкидається тут, а не довіряється знімку.
//
// Планшет на рецепції слабкий, тож одночасно грає не більше одного відео:
// у стрічці напряму — лише кадри, рух — на сцені курсу й у повному екрані.

const LOCAL = '/media/content/';
const PHOTO_MS = 5000;

const local = value => typeof value === 'string' && value.startsWith(LOCAL);

export const reducedMotion = () =>
  matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('reduced-motion');

/** Обкладинка першою, далі галерея в порядку CRM. */
export function mediaOf(node) {
  const list = [];
  if (local(node?.image)) list.push({ kind: 'image', url: node.image, poster: '' });
  for (const item of Array.isArray(node?.media) ? node.media : []) {
    if ((item?.kind === 'image' || item?.kind === 'video') && local(item.url)) {
      list.push({ kind: item.kind, url: item.url, poster: local(item.poster) ? item.poster : '' });
    }
  }
  return list;
}

/** «3 відео · 8 фото» — щоб було видно, що всередині є на що подивитися. */
export function mediaSummary(items) {
  const videos = items.filter(m => m.kind === 'video').length, photos = items.length - videos;
  return [videos ? `${videos} відео` : '', photos ? `${photos} фото` : ''].filter(Boolean).join(' · ');
}

// Кадр для мініатюри: постер, а без нього — перший кадр самого відео.
function still(item, className) {
  if (item.kind === 'image' || item.poster) {
    const img = element('img', className);
    img.alt = ''; img.decoding = 'async'; img.loading = 'lazy';
    img.src = item.kind === 'image' ? item.url : item.poster;
    return img;
  }
  const video = element('video', className);
  video.muted = true; video.playsInline = true; video.preload = 'metadata';
  video.src = `${item.url}#t=0.1`;
  video.setAttribute('aria-hidden', 'true');
  return video;
}

function playBadge() {
  const badge = element('span', 'play-badge');
  badge.append(icon('play'));
  return badge;
}

function thumb(item, className) {
  const frame = element('span', `${className} is-${item.kind}`);
  const media = still(item, 'thumb-media');
  media.addEventListener('error', () => frame.classList.add('is-broken'), { once: true });
  frame.append(media);
  if (item.kind === 'video') frame.append(playBadge());
  return frame;
}

/**
 * Мозаїка «як проходять заняття»: перший кадр великий, решта поруч.
 * Дотик відкриває повний екран; відео тут лише кадром — грає одне, на сцені.
 */
export function createMosaic(items, { onOpen }) {
  const grid = element('div', 'media-mosaic');
  // Сітка має бути рівною: великий кадр і чотири менші, решта — «+N» на
  // останньому. Чотири й менше кадрів мають власні розкладки.
  const shown = items.slice(0, items.length >= 5 ? 5 : items.length);
  grid.dataset.count = String(shown.length);
  shown.forEach((item, index) => {
    const button = element('button', 'mosaic-item');
    button.setAttribute('aria-label', item.kind === 'video' ? `Відео ${index + 1}` : `Фото ${index + 1}`);
    button.style.setProperty('--i', index);
    button.append(thumb(item, 'mosaic-frame'));
    const rest = items.length - shown.length;
    if (index === shown.length - 1 && rest > 0) button.append(element('span', 'mosaic-more', `+${rest}`));
    button.addEventListener('click', () => onOpen(index));
    grid.append(button);
  });
  return grid;
}

/**
 * Сцена курсу: великий кадр, що сам гортається, і мініатюри під ним.
 * Фото стоїть кілька секунд, відео грає без звуку до кінця. Звук — лише в
 * повному екрані, куди людина зайшла сама: хол школи не кінозал.
 */
export function createStage(items, { onOpen, thumbs: withThumbs = true }) {
  const root = element('div', 'gallery');
  const stage = element('button', 'gallery-stage');
  stage.setAttribute('aria-label', 'Відкрити галерею на весь екран');
  const backdrop = element('span', 'stage-backdrop'), layer = element('span', 'stage-layer');
  const counter = element('span', 'stage-counter'), expand = element('span', 'stage-expand');
  expand.append(icon('expand'));
  stage.append(backdrop, layer, counter, expand);
  root.append(stage);

  const thumbs = element('div', 'gallery-thumbs');
  const buttons = items.map((item, index) => {
    const button = element('button', 'gallery-thumb');
    button.setAttribute('aria-label', item.kind === 'video' ? `Відео ${index + 1}` : `Фото ${index + 1}`);
    button.append(thumb(item, 'thumb-frame'));
    button.addEventListener('click', () => show(index));
    thumbs.append(button);
    return button;
  });
  if (items.length > 1 && withThumbs) root.append(thumbs);
  else root.classList.add('no-thumbs');

  let current = -1, timer = 0, paused = false, video = null;

  function stop() {
    clearTimeout(timer); timer = 0;
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); video = null; }
  }
  function schedule(ms) {
    clearTimeout(timer);
    if (!paused && items.length > 1) timer = setTimeout(() => show((current + 1) % items.length), ms);
  }

  function show(index) {
    stop();
    current = index;
    const item = items[index];
    counter.textContent = items.length > 1 ? `${index + 1} / ${items.length}` : '';
    counter.hidden = items.length < 2;
    buttons.forEach((b, i) => b.setAttribute('aria-current', String(i === index)));
    buttons[index]?.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reducedMotion() ? 'auto' : 'smooth' });

    const back = still(item, 'backdrop-media');
    backdrop.replaceChildren(back);
    let media;
    if (item.kind === 'video' && !reducedMotion()) {
      media = element('video', 'stage-media');
      media.muted = true; media.playsInline = true; media.preload = 'auto';
      if (item.poster) media.poster = item.poster;
      media.src = item.url;
      media.loop = items.length === 1;
      media.addEventListener('ended', () => schedule(0));
      media.addEventListener('error', () => schedule(PHOTO_MS), { once: true });
      video = media;
      if (!paused) media.play().catch(() => schedule(PHOTO_MS));
    } else {
      media = still(item, 'stage-media');
      if (item.kind === 'image' && !reducedMotion()) media.classList.add('drift');
      media.addEventListener('error', () => schedule(0), { once: true });
      schedule(PHOTO_MS);
    }
    stage.classList.toggle('is-video', item.kind === 'video');
    layer.replaceChildren(media);
    if (item.kind === 'video' && reducedMotion()) layer.append(playBadge());
    if (!reducedMotion()) media.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 420, easing: 'ease-out' });
  }

  stage.addEventListener('click', () => onOpen(current));
  if (items.length) show(0);

  return {
    element: root,
    /** Поки відкрито повний екран, сцена стоїть і не грає другим відео. */
    pause() { paused = true; clearTimeout(timer); video?.pause(); },
    resume(index = current) { paused = false; show(index); },
    destroy: stop,
  };
}

/** Повний екран: гортання пальцем, відео зі звуком, лічильник. */
export function createLightbox(host, { onActivity, onClose } = {}) {
  const root = element('div', 'lightbox'); root.hidden = true;
  root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true'); root.setAttribute('aria-label', 'Галерея');
  const frame = element('div', 'lightbox-frame');
  const close = element('button', 'lightbox-close'); close.append(icon('close'), element('span', '', 'Закрити'));
  const prev = element('button', 'lightbox-nav prev'); prev.append(icon('back')); prev.setAttribute('aria-label', 'Попереднє');
  const next = element('button', 'lightbox-nav next'); next.append(icon('next')); next.setAttribute('aria-label', 'Наступне');
  const bar = element('div', 'lightbox-bar');
  const counter = element('span', 'lightbox-counter');
  const sound = element('button', 'lightbox-sound');
  const progress = element('span', 'lightbox-progress'), fill = element('span');
  progress.append(fill);
  bar.append(counter, progress, sound);
  root.append(frame, prev, next, close, bar);
  host.append(root);

  let items = [], index = 0, video = null, withSound = true, lastPing = 0, startX = null, swiped = false;

  function renderSound() {
    sound.replaceChildren(icon(withSound ? 'volume' : 'mute'), element('span', '', withSound ? 'Зі звуком' : 'Без звуку'));
    sound.setAttribute('aria-pressed', String(withSound));
  }

  function stopVideo() {
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); video = null; }
  }

  function show(i, direction = 0) {
    stopVideo();
    index = (i + items.length) % items.length;
    const item = items[index];
    counter.textContent = `${index + 1} / ${items.length}`;
    prev.hidden = next.hidden = items.length < 2;
    let media;
    if (item.kind === 'video') {
      media = element('video', 'lightbox-media');
      media.playsInline = true; media.preload = 'auto'; media.muted = !withSound;
      if (item.poster) media.poster = item.poster;
      media.src = item.url;
      media.addEventListener('timeupdate', () => {
        if (media.duration) fill.style.transform = `scaleX(${media.currentTime / media.duration})`;
        // Хтось дивиться відео — це не бездіяльність, меню не має закритися посеред.
        const now = performance.now();
        if (!media.paused && now - lastPing > 5000) { lastPing = now; onActivity?.(); }
      });
      media.addEventListener('ended', () => { if (items.length > 1) show(index + 1, 1); else root.classList.add('is-ended'); });
      media.addEventListener('play', () => root.classList.remove('is-paused', 'is-ended'));
      media.addEventListener('pause', () => root.classList.add('is-paused'));
      video = media;
      media.play().catch(() => {
        // Без звуку Chromium дозволяє завжди; зі звуком — лише після дотику.
        media.muted = true; withSound = false; renderSound();
        media.play().catch(() => root.classList.add('is-paused'));
      });
      const hint = element('span', 'lightbox-play'); hint.append(icon('play'));
      frame.replaceChildren(media, hint);
    } else {
      media = still(item, 'lightbox-media');
      frame.replaceChildren(media);
    }
    fill.style.transform = 'scaleX(0)';
    root.classList.toggle('is-video', item.kind === 'video');
    root.classList.remove('is-paused', 'is-ended');
    if (!reducedMotion()) {
      media.animate([{ opacity: 0, transform: `translateX(${direction * 40}px) scale(.98)` }, { opacity: 1, transform: 'none' }],
        { duration: 320, easing: 'cubic-bezier(.22,1,.36,1)' });
    }
  }

  function hide() {
    if (root.hidden) return;
    stopVideo(); frame.replaceChildren(); root.hidden = true;
    onClose?.(index);
  }

  close.addEventListener('click', hide);
  prev.addEventListener('click', () => show(index - 1, -1));
  next.addEventListener('click', () => show(index + 1, 1));
  sound.addEventListener('click', () => { withSound = !withSound; if (video) video.muted = !withSound; renderSound(); });
  frame.addEventListener('click', () => {
    if (swiped) { swiped = false; return; }
    if (!video) return;
    if (video.paused || video.ended) video.play().catch(() => {}); else video.pause();
  });
  frame.addEventListener('pointerdown', e => { startX = e.clientX; }, { passive: true });
  frame.addEventListener('pointerup', e => {
    if (startX == null || items.length < 2) return;
    const dx = e.clientX - startX; startX = null;
    if (Math.abs(dx) > 60) { swiped = true; show(index + (dx < 0 ? 1 : -1), dx < 0 ? 1 : -1); }
  });
  root.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); hide(); }
    else if (e.key === 'ArrowRight' && items.length > 1) show(index + 1, 1);
    else if (e.key === 'ArrowLeft' && items.length > 1) show(index - 1, -1);
  });
  renderSound();

  return {
    get open() { return !root.hidden; },
    show(list, start = 0) {
      if (!list.length) return;
      items = list; withSound = true; renderSound();
      root.hidden = false; show(start);
      close.focus({ preventScroll: true });
    },
    hide,
  };
}
