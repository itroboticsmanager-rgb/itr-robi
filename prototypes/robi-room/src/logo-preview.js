import { createLogoStage } from './logostage.js';
import { KINDS } from './cameo.js';

// Two frames at once: the kiosk window at the agreed 30% height and a taller
// panel, so one sign can be judged at both proportions before it ships.
const stages = ['stage-window', 'panel'].map(id => {
  const canvas = document.getElementById(id);
  const stage = createLogoStage(canvas);
  canvas.addEventListener('pointerdown', event => stage.touch(event.clientX, event.clientY));
  return { canvas, stage };
});

function fit() {
  for (const { canvas, stage } of stages) {
    const rect = canvas.getBoundingClientRect();
    stage.resize(Math.round(rect.width), Math.round(rect.height));
  }
}
addEventListener('resize', fit);
fit();

// Matching the room prototype: automation hooks appear only under ?debug.
if (new URLSearchParams(location.search).has('debug')) globalThis.__stages = stages;
const stats = document.getElementById('stats');
let paused = false;
let last = performance.now(), frames = 0, since = last, worst = 0;
function frame(now) {
  const step = now - last, dt = Math.min(.05, step / 1000); last = now;
  worst = Math.max(worst, step);
  for (const { stage } of stages) { if (!paused) stage.update(dt); stage.render(); }
  if (++frames >= 40) {
    const info = stages[0].stage.renderer.info, scene = stages[0].stage.director.kind || 'пауза';
    stats.textContent = `${Math.round(frames * 1000 / (now - since))} FPS · пік кадру ${worst.toFixed(1)} мс · ${info.render.calls} викликів · ${info.render.triangles.toLocaleString('uk')} трикутників · сцена: ${scene}`;
    frames = 0; since = now; worst = 0;
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

let dark = true;
document.getElementById('theme').addEventListener('click', event => {
  dark = !dark;
  for (const { stage } of stages) stage.setTheme(dark ? 'dark' : 'light');
  event.currentTarget.setAttribute('aria-pressed', String(dark));
  event.currentTarget.textContent = dark ? 'Темна стіна' : 'Світла стіна';
});
document.getElementById('sweep').addEventListener('click', () => {
  for (const { stage } of stages) stage.sweepNow();
});

const scenes = document.getElementById('scenes');
for (const kind of KINDS) {
  const button = document.createElement('button');
  button.textContent = {peek: 'Визирнути', greet: 'Привітатися', curious: 'Роздивитися', side: 'З-за краю', peekaboo: 'Ку-ку', guide: 'Запросити до меню'}[kind];
  button.addEventListener('click', () => { for (const { stage } of stages) { stage.director.force(kind); stage.update(0); } });
  scenes.append(button);
}

document.getElementById('pause').addEventListener('click', event => {
  paused = !paused;
  event.currentTarget.setAttribute('aria-pressed', String(paused));
  event.currentTarget.textContent = paused ? 'Продовжити' : 'Пауза';
});
document.getElementById('scrub').addEventListener('input', event => {
  paused = true;
  document.getElementById('pause').setAttribute('aria-pressed', 'true');
  document.getElementById('pause').textContent = 'Продовжити';
  for (const { stage } of stages) {
    if (!stage.director.kind) stage.director.force('greet');
    stage.director.elapsed = Math.min(.9999, Number(event.target.value) / 100) * stage.director.duration;
    stage.update(0);
  }
});
