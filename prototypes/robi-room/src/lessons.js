// «Що зараз на заняттях» — екран для батьків, які чекають дитину в холі.
//
// Дані — сьогоднішні групові заняття з CRM (курс, група, час, колір курсу),
// без імен дітей і викладачів. Що «зараз», «далі» й «завершилось», рахує
// сам екран за годинником планшета, тож між оновленнями раз на 5 хв він
// лишається правдивим. Екран локальний: служба про нього не знає, як і про
// сон (D-068), тож закривається кнопкою або сам після бездіяльності.

import { element, icon } from './icons.js';

const TIME = new Intl.DateTimeFormat('uk-UA', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Kyiv' });

/** Сьогоднішні заняття, поділені на «зараз», «далі» й «завершились». */
export function splitLessons(lessons, now = Date.now()) {
  const groups = { now: [], next: [], done: [] };
  for (const lesson of Array.isArray(lessons) ? lessons : []) {
    const start = Date.parse(lesson?.start), end = Date.parse(lesson?.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
    const item = { ...lesson, startMs: start, endMs: end };
    if (now >= end) groups.done.push(item);
    else if (now >= start) groups.now.push(item);
    else groups.next.push(item);
  }
  for (const list of Object.values(groups)) list.sort((a, b) => a.startMs - b.startMs || String(a.course).localeCompare(String(b.course)));
  return groups;
}

/** Чи є сьогодні ще щось, що не скінчилось: тоді на головній є кнопка. */
export function hasLessonsAhead(lessons, now = Date.now()) {
  const { now: current, next } = splitLessons(lessons, now);
  return current.length + next.length > 0;
}

function minutesLeft(ms) {
  const minutes = Math.max(1, Math.round(ms / 60000));
  if (minutes < 60) return `${minutes} хв`;
  const hours = Math.floor(minutes / 60), rest = minutes % 60;
  return rest ? `${hours} год ${rest} хв` : `${hours} год`;
}

export function createLessonsScreen(host, { onClose }) {
  const screen = element('section', 'lessons-screen'); screen.hidden = true;
  screen.setAttribute('aria-label', 'Що зараз на заняттях');
  const bar = element('header', 'content-bar'), closeButton = element('button', 'secondary-button', 'На головну');
  bar.append(element('span', 'content-brand', 'ITRobotics'), closeButton);
  const title = element('h1', 'content-title', 'Що зараз на заняттях'); title.tabIndex = -1;
  const body = element('div', 'lessons-body');
  screen.append(bar, element('p', 'section-kicker', 'СЬОГОДНІ В ШКОЛІ'), title, body);
  host.append(screen);
  closeButton.addEventListener('click', () => onClose());
  screen.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); onClose(); } });

  let lessons = [];

  function card(lesson, state, now) {
    const item = element('article', `lesson-card ${state}`);
    if (/^#[0-9a-fA-F]{6}$/.test(lesson.color || '')) item.style.setProperty('--accent', lesson.color);
    const badge = element('span', 'lesson-icon'); badge.append(icon(lesson.icon || 'robot'));
    const copy = element('div', 'lesson-copy');
    copy.append(element('h2', 'lesson-course', lesson.course));
    const time = element('p', 'lesson-time', `${TIME.format(lesson.startMs)} – ${TIME.format(lesson.endMs)}`);
    copy.append(time);
    item.append(badge, copy);
    if (state === 'now') {
      const share = Math.min(1, Math.max(0, (now - lesson.startMs) / (lesson.endMs - lesson.startMs)));
      const progress = element('div', 'lesson-progress'); progress.style.setProperty('--share', share.toFixed(3));
      progress.setAttribute('role', 'progressbar');
      progress.setAttribute('aria-valuenow', String(Math.round(share * 100)));
      progress.setAttribute('aria-valuemin', '0'); progress.setAttribute('aria-valuemax', '100');
      copy.append(progress, element('p', 'lesson-left', `Закінчиться через ${minutesLeft(lesson.endMs - now)}`));
    } else if (state === 'next') {
      copy.append(element('p', 'lesson-left', `Почнеться через ${minutesLeft(lesson.startMs - now)}`));
    }
    return item;
  }

  function section(label, list, state, now) {
    if (!list.length) return null;
    const block = element('section', `lessons-section ${state}`);
    block.append(element('h3', 'lessons-heading', label));
    const grid = element('div', 'lessons-grid');
    for (const lesson of list) grid.append(card(lesson, state, now));
    block.append(grid);
    return block;
  }

  function render() {
    const now = Date.now(), parts = splitLessons(lessons, now);
    const blocks = [
      section('Зараз', parts.now, 'now', now),
      section('Далі сьогодні', parts.next, 'next', now),
      section('Уже завершились', parts.done, 'done', now),
    ].filter(Boolean);
    body.replaceChildren(...blocks);
    if (!parts.now.length && !parts.next.length) {
      body.prepend(element('p', 'lessons-empty', 'На сьогодні заняття вже завершились. Чекаємо вас наступного разу!'));
    }
  }

  return {
    get open() { return !screen.hidden; },
    setLessons(next) { lessons = Array.isArray(next) ? next : []; if (!screen.hidden) render(); },
    show() { render(); screen.hidden = false; title.focus({ preventScroll: true }); },
    hide() { screen.hidden = true; },
    tick() { if (!screen.hidden) render(); },
  };
}
