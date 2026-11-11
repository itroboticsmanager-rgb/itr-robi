import { element } from './icons.js';

/**
 * Анкета на планшеті (D-065): CRM відкриває свою сторінку `/enroll/<token>?kiosk=1`,
 * кіоск тримає її у фреймі. Поля, перевірки й відправка — ті самі, що в
 * анкеті за QR, бо це та сама сторінка CRM; тут лише рамка навколо неї.
 *
 * Сторінка CRM розповідає лише ЩО відбувається (без даних анкети), контракт —
 * `src/lib/enroll-kiosk.ts` у CRM: `ready`, `activity`, `submitted`, `done`,
 * `error`. Повідомлення приймаються лише від цього фрейму і його origin.
 *
 * Персональні дані не осідають на пристрої (D-049): фрейм знищується разом
 * з екраном, Edge кіоску працює InPrivate, а сама сторінка в режимі терміналу
 * не пише чернетку в браузер.
 */

export const ENROLL_SOURCE = 'itr-enroll';
/** Скільки чекаємо, що анкета відкрилась, перш ніж сказати «недоступна». */
export const READY_TIMEOUT_MS = 20000;
/** Після «Надіслано» екран подяки висить, поки людина не натисне «Готово», але не довше. */
export const THANKS_MS = 90000;
/** За скільки до автозакриття питаємо «Ви ще заповнюєте?». */
export const WARN_BEFORE_MS = 40000;

/** Чи це наше повідомлення: тип і джерело, без жодних інших полів. */
export function readFormMessage(event, frameWindow, origin) {
  if (!frameWindow || event.source !== frameWindow || event.origin !== origin) return null;
  const data = event.data;
  if (!data || typeof data !== 'object' || data.source !== ENROLL_SOURCE) return null;
  return ['ready', 'activity', 'submitted', 'done', 'error'].includes(data.type) ? data.type : null;
}

/**
 * Адреса з CRM годиться для фрейму лише як https. Виняток — CRM на петлі
 * (локальна перевірка на робочому ПК): на пристрої таку адресу однаково не
 * пропустить allowlist служби, у якому лише https (D-038).
 */
export function formOrigin(url) {
  try {
    const u = new URL(url);
    if (u.protocol === 'https:') return u.origin;
    if (u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1')) return u.origin;
    return '';
  } catch { return ''; }
}

export function createFormScreen(host, { onClose, onActivity }) {
  const root = element('section', 'form-screen'); root.hidden = true; root.setAttribute('aria-label', 'Анкета');
  const bar = element('header', 'content-bar form-bar');
  const brand = element('span', 'content-brand', 'ITRobotics');
  const title = element('h1', 'form-title', 'Анкета нового учня'); title.tabIndex = -1;
  const cancel = element('button', 'secondary-button form-cancel', 'Скасувати');
  bar.append(brand, title, cancel);
  const stage = element('div', 'form-stage'), frameHost = element('div', 'form-frame-host');
  const veil = element('div', 'form-veil');
  const veilText = element('p', 'form-veil-text', 'Відкриваю анкету…');
  const veilActions = element('div', 'form-veil-actions');
  veil.append(veilText, veilActions);
  // Завіса — під смугою: «Скасувати» лишається доступним, навіть поки анкета вантажиться.
  stage.append(frameHost, veil); root.append(bar, stage); host.append(root);

  let frame = null, origin = '', state = 'idle', readyTimer = 0, thanksTimer = 0;

  function setVeil(text, actions = []) {
    veilText.textContent = text;
    veilActions.replaceChildren(...actions);
    veil.hidden = !text;
  }
  function button(label, cls, handler) {
    const b = element('button', cls, label); b.type = 'button'; b.addEventListener('click', handler); return b;
  }

  function onMessage(event) {
    const type = readFormMessage(event, frame?.contentWindow, origin);
    if (!type) return;
    if (type === 'ready') {
      clearTimeout(readyTimer); state = 'filling'; setVeil('');
    } else if (type === 'activity') {
      if (state === 'warn') setVeil('');
      if (state !== 'submitted') state = 'filling';
      onActivity();
    } else if (type === 'submitted') {
      clearTimeout(readyTimer); state = 'submitted'; setVeil('');
      cancel.textContent = 'Готово';
      onActivity();
      clearTimeout(thanksTimer); thanksTimer = setTimeout(() => onClose(), THANKS_MS);
    } else if (type === 'done') {
      onClose();
    } else if (type === 'error') {
      clearTimeout(readyTimer); state = 'error';
      setVeil('Анкета зараз недоступна. Зверніться, будь ласка, до адміністратора.', [button('На головну', 'primary-button', () => onClose())]);
    }
  }
  window.addEventListener('message', onMessage);

  function confirmCancel() {
    if (state === 'submitted' || state === 'error' || state === 'loading') { onClose(); return; }
    setVeil('Скасувати анкету? Усе введене буде стерто.', [
      button('Продовжити заповнення', 'secondary-button', () => { setVeil(''); onActivity(); }),
      button('Так, скасувати', 'primary-button', () => onClose()),
    ]);
  }
  cancel.addEventListener('click', confirmCancel);
  root.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); confirmCancel(); } });

  function show(url, heading) {
    hide();
    origin = formOrigin(url);
    if (!origin) return false;
    title.textContent = heading || 'Анкета нового учня';
    cancel.textContent = 'Скасувати';
    frame = element('iframe', 'form-frame');
    frame.title = title.textContent;
    frame.referrerPolicy = 'no-referrer';
    // Без allow-popups: посилання на Telegram тощо з анкети не відкриються
    // на планшеті, анкета в режимі терміналу показує QR для телефона.
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms');
    frame.src = url;
    frameHost.replaceChildren(frame);
    state = 'loading';
    setVeil('Відкриваю анкету…');
    readyTimer = setTimeout(() => {
      if (state !== 'loading') return;
      state = 'error';
      setVeil('Анкета зараз недоступна. Зверніться, будь ласка, до адміністратора.', [button('На головну', 'primary-button', () => onClose())]);
    }, READY_TIMEOUT_MS);
    root.hidden = false;
    title.focus({ preventScroll: true });
    return true;
  }

  function hide() {
    clearTimeout(readyTimer); clearTimeout(thanksTimer);
    // Фрейм знищується цілком — разом із введеним (D-049).
    if (frame) { frame.src = 'about:blank'; frame.remove(); frame = null; }
    frameHost.replaceChildren();
    origin = ''; state = 'idle'; setVeil('');
    root.hidden = true;
  }

  /** Залишилось мало часу: питаємо, чи людина ще тут. */
  function warn(secondsLeft) {
    if (state !== 'filling' && state !== 'warn') return;
    const text = `Ви ще заповнюєте? Анкета закриється через ${secondsLeft} с, і введене буде стерто.`;
    // Щотакту міняємо лише текст: нові кнопки посеред дотику з'їли б натискання.
    if (state === 'warn') { veilText.textContent = text; return; }
    state = 'warn';
    setVeil(text, [
      button('Так, продовжити', 'primary-button', () => { setVeil(''); state = 'filling'; onActivity(); }),
      button('Ні, закрити', 'secondary-button', () => onClose()),
    ]);
  }
  function calm() { if (state === 'warn') { state = 'filling'; setVeil(''); } }

  return { show, hide, warn, calm, get state() { return state; } };
}
