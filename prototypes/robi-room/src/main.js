import './style.css';
import { createLogoStage } from './logostage.js';
import { createKiosk } from './kiosk.js';

const $ = s => document.querySelector(s);
const canvas = $('#scene'), sensor = $('#window-sensor');
const query = matchMedia('(prefers-reduced-motion: reduce)');
// Кіоск у холі: перемикача «Менше руху» немає, рух вирішує лише налаштування
// системи. Старе збережене рішення з localStorage більше не читається.
let reduced = query.matches;
let stage, raf = 0, last = 0, paused = false, visible = true;
const debug = new URLSearchParams(location.search).has('debug');
const diagnostics = debug ? document.createElement('output') : null;
if (diagnostics) { diagnostics.hidden = true; diagnostics.id = 'robi-diagnostics'; document.body.append(diagnostics); }
// Як у logo-preview: автоматизація бачить сцену лише під ?debug.
if (debug) globalThis.__robiStage = () => stage;
let frames = 0, since = 0;
const pageTargets = { banner: $('#banner-slides'), menu: $('#launcher') };
function attention(target = '') {
  for (const [name, element] of Object.entries(pageTargets)) element.classList.toggle('robi-attention', name === target);
}
function measureTargets() {
  const origin = canvas.getBoundingClientRect();
  stage?.setPageTargets(Object.fromEntries(Object.entries(pageTargets).flatMap(([name, element]) => {
    const r = element.getBoundingClientRect();
    // Прихована карусель (з CRM немає банерів) — не ціль: Робі показує на меню.
    if (!r.width || !r.height) return [];
    return [[name, { x: r.left + r.width / 2 - origin.left, y: r.top + r.height / 2 - origin.top }]];
  })));
}
const targetObserver = new ResizeObserver(measureTargets);
for (const element of Object.values(pageTargets)) targetObserver.observe(element);
function motion(value) {
  reduced = value;
  if (stage) stage.reduced = value;
  document.documentElement.classList.toggle('reduced-motion', value);
  sensor.hidden = true;
  attention();
  document.documentElement.classList.remove('mascot-present');
  wake();
}
query.addEventListener('change', e => motion(e.matches));
// Свайп «назад» на сенсорі вивів Edge зі сторінки кіоску на заблоковану
// адресу (D-064). Жест гасить CSS (overscroll-behavior), а на випадок, якщо
// Edge його все одно виконає, тримаємо власний запис історії: «назад» лише
// знімає його, документ лишається тим самим. Запис ставиться в момент
// дотику, бо Chromium пропускає під час «назад» записи, додані без дії людини.
// Останній рубіж — наглядач, який перезапускає Edge, коли сторінка замовкла.
function armHistoryTrap() {
  if (history.state?.robiTrap) return;
  try { history.pushState({ robiTrap: true }, ''); } catch { /* Not critical. */ }
}
addEventListener('pointerdown', armHistoryTrap, { capture: true, passive: true });
addEventListener('keydown', armHistoryTrap, { capture: true, passive: true });
function frame(now) {
  raf = 0;
  if (!stage || paused || !visible || document.hidden) return;
  const dt = last ? Math.min((now - last) / 1000, .05) : 0; last = now;
  stage.update(dt); stage.render();
  attention(stage.attentionTarget);
  const bounds = stage.characterBounds();
  // Робі сидить на вивісці постійно, тож карусель чекає лише його «виступу».
  document.documentElement.classList.toggle('mascot-present', !!bounds && !reduced && stage.performing);
  // A real target over the character only. The logo cannot expand or navigate.
  sensor.hidden = !bounds || reduced;
  if (bounds && !reduced) {
    sensor.style.transform = `translate(${bounds.x}px, ${bounds.y}px)`;
    sensor.style.width = `${bounds.width}px`; sensor.style.height = `${bounds.height}px`;
  }
  if (diagnostics && now - since > 1000) {
    diagnostics.textContent = JSON.stringify({ fps: Math.round(frames * 1000 / (now - since)), cameo: stage.director.kind, reduced, expanded: false, drawCalls: stage.renderer.info.render.calls, triangles: stage.renderer.info.render.triangles });
    frames = 0; since = now;
  }
  frames++;
  if (!reduced) raf = requestAnimationFrame(frame);
}
function wake() { if (stage && !raf && !paused && visible && !document.hidden) raf = requestAnimationFrame(frame); }
function suspend() { if (raf) cancelAnimationFrame(raf); raf = 0; last = 0; }
sensor.addEventListener('click', () => { stage?.director.greet(); wake(); });
new ResizeObserver(entries => {
  const { width, height } = entries[0].contentRect;
  stage?.resize(Math.round(width), Math.round(height)); measureTargets(); wake();
}).observe($('#stage'));
new IntersectionObserver(entries => { visible = entries[0].isIntersecting; suspend(); wake(); }).observe(canvas);
document.addEventListener('visibilitychange', () => { suspend(); wake(); });
canvas.addEventListener('webglcontextlost', e => {
  e.preventDefault(); suspend(); stage = null; sensor.hidden = true;
  $('#logo-fallback').hidden = false;
});
canvas.addEventListener('webglcontextrestored', () => location.reload());
try {
  stage = createLogoStage(canvas, { reduced, onReady: () => { last = 0; if (reduced && stage) stage.render(); wake(); } });
  stage.resize($('#stage').clientWidth, $('#stage').clientHeight);
  $('#logo-fallback').hidden = true;
} catch (error) { console.error('Logo stage unavailable', error); }
motion(reduced);
createKiosk({
  pauseScene(value) { if (paused && !value) stage?.director.reset(); paused = value; attention(); suspend(); wake(); },
  mascot(state, gaze) { stage?.setMascot(state, gaze); },
});
