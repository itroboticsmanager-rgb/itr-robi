// «Живе на вивісці» (D-066): Робі постійно сидить на літері «s» у назві
// школи. Цей модуль — лише поведінка, без three.js: що робить Робі зараз і
// яку позу з цього виходить. Його читає `robi-model.js`, `logostage.js` і тести.
//
// Принцип — ефектно, але не нав'язливо: у спокої рухи малі й повільні
// (дихання, кліпання, погляд на людину, ледь гойдає ногами, інколи
// всміхається); літера під ним підстрибує — він підскакує разом із нею.
// Помітні дії — тихий помах, коли людина підійшла чи торкнулась, рідкісна
// дрібниця раз на кілька хвилин і найбільша: «візит» — зістрибує, підходить
// близько до камери, махає з усмішкою й повертається на місце.

export const WAVE_S = 3.2;
export const FLOURISH = { antenna: 3.4, look: 4.2 };
/** Після скількох секунд без людини наступна поява знову вітається. */
export const AWAY_S = 15;
/** Помах на появу людини — не частіше. Дотик вітається завжди. */
export const GREET_COOLDOWN_S = 45;
export const FLOURISH_MIN_S = 150, FLOURISH_MAX_S = 300;
/** Візит: скільки триває, скільки людина має постояти, і як часто він буває. */
export const VISIT_S = 10.8, VISIT_AFTER_S = 6, VISIT_COOLDOWN_S = 240, VISIT_TOUCH_COOLDOWN_S = 90;
/** Реакція на підстрибування літери. */
export const BUMP_S = 1.6;
export const SMILE_S = 2.6, SMILE_MIN_S = 20, SMILE_MAX_S = 50;
/** Помітні дії: на їх час сторінка не гортає банери. */
const PERFORMING = new Set(['wave', 'antenna', 'look', 'visit']);

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const pulse = (a, b, c, d, t) => smooth(a, b, t) * (1 - smooth(c, d, t));
const arc = (a, b, t) => { const k = clamp((t - a) / (b - a), 0, 1); return Math.sin(Math.PI * k); };

export function restPose() {
  return {
    breathe: 0, headYaw: 0, headPitch: 0, headRoll: 0, antenna: 0,
    // Руки лежать на краю, де він сидить: трохи вперед і вниз.
    arms: [{ raise: 0, forward: .26, bend: .12 }, { raise: 0, forward: .26, bend: .12 }],
    // swing — гомілка (звисає / згин коліна), thigh — стегно вперед (-) чи назад (+).
    legs: [{ swing: 0, thigh: 0 }, { swing: 0, thigh: 0 }],
    lookX: 0, lookY: 0, blink: 0, smile: .18, surprise: 0, curiosity: 0,
    // Де він: sit 1 — сидить, 0 — стоїть; travel 0 — на літері, 1 — біля камери;
    // hop — підскок (у рості моделі); yaw — розворот; lean — нахил корпусу вперед.
    sit: 1, travel: 0, hop: 0, yaw: 0, lean: 0,
  };
}

export class SitDirector {
  constructor(random = Math.random) {
    this.random = random;
    this.time = 0;
    this.action = '';            // '', 'wave', 'antenna', 'look', 'visit'
    this.actionT = 0;
    this.awayFor = AWAY_S;       // перша людина після запуску теж вітається
    this.presentFor = 0;
    this.sinceGreet = Infinity;
    this.sinceVisit = VISIT_COOLDOWN_S;
    this.nextFlourish = this.#between(FLOURISH_MIN_S, FLOURISH_MAX_S);
    this.nextBlink = 2 + random() * 3;
    this.blinkT = -1;
    this.nextSmile = this.#between(SMILE_MIN_S, SMILE_MAX_S);
    this.smileT = -1;
    this.bumpT = -1;
    this.bumps = 0;
    this.look = [0, 0];
  }
  #between(a, b) { return a + this.random() * (b - a); }

  get performing() { return PERFORMING.has(this.action); }
  get kind() { return this.action; }

  /** Торкнулись Робі: давно не підходив — підійде, інакше помахає. */
  greet() {
    if (this.action === 'wave' || this.action === 'visit') return false;
    this.#start(this.sinceVisit >= VISIT_TOUCH_COOLDOWN_S ? 'visit' : 'wave');
    return true;
  }
  /** Літера, на якій він сидить, почала підстрибувати. */
  bump() {
    if (this.action === 'visit' || this.bumpT >= 0) return false;
    this.bumpT = 0; this.bumps++;
    return true;
  }
  /** Сторінка повернулась на головну — без незавершених дій. */
  reset() { this.action = ''; this.actionT = 0; this.bumpT = -1; }
  force(kind) {
    if (!['wave', 'visit', ...Object.keys(FLOURISH)].includes(kind)) return false;
    this.#start(kind); return true;
  }
  #start(kind) {
    this.action = kind; this.actionT = 0;
    if (kind === 'wave' || kind === 'visit') this.sinceGreet = 0;
    if (kind === 'visit') { this.sinceVisit = 0; this.bumpT = -1; }
  }

  /**
   * @param dt секунди
   * @param present чи бачить камера обличчя (є `gaze` у знімку служби)
   * @param gaze [-1..1, -1..1] куди дивитись, або null
   */
  update(dt, { present = false, gaze = null } = {}) {
    dt = Math.max(0, Math.min(dt, .1));
    this.time += dt;
    this.sinceGreet += dt;
    this.sinceVisit += dt;

    if (present) {
      if (this.awayFor >= AWAY_S && this.sinceGreet >= GREET_COOLDOWN_S && !this.action) this.#start('wave');
      this.awayFor = 0; this.presentFor += dt;
      if (!this.action && this.presentFor >= VISIT_AFTER_S && this.sinceVisit >= VISIT_COOLDOWN_S) this.#start('visit');
    } else {
      this.awayFor += dt; this.presentFor = 0;
    }

    if (this.action) {
      this.actionT += dt;
      const length = this.action === 'wave' ? WAVE_S : this.action === 'visit' ? VISIT_S : FLOURISH[this.action];
      if (this.actionT >= length) { this.action = ''; this.actionT = 0; }
    } else if (!present) {
      // Дрібниці лише коли поруч нікого: людині він дивиться в очі.
      this.nextFlourish -= dt;
      if (this.nextFlourish <= 0) {
        this.#start(this.random() < .5 ? 'antenna' : 'look');
        this.nextFlourish = this.#between(FLOURISH_MIN_S, FLOURISH_MAX_S);
      }
    }

    if (this.bumpT >= 0) { this.bumpT += dt; if (this.bumpT > BUMP_S) this.bumpT = -1; }
    this.nextSmile -= dt;
    if (this.nextSmile <= 0) { if (!this.action) this.smileT = 0; this.nextSmile = this.#between(SMILE_MIN_S, SMILE_MAX_S); }
    if (this.smileT >= 0) { this.smileT += dt; if (this.smileT > SMILE_S) this.smileT = -1; }

    this.nextBlink -= dt;
    if (this.nextBlink <= 0) { this.blinkT = 0; this.nextBlink = 2.5 + this.random() * 4; }
    if (this.blinkT >= 0) { this.blinkT += dt; if (this.blinkT > .18) this.blinkT = -1; }

    // Погляд повільно наздоганяє людину, а без неї — спокійно блукає. Під час
    // візиту він дивиться просто в камеру.
    const target = this.action === 'visit' ? (present && gaze ? [gaze[0] * .4, gaze[1] * .4] : [0, 0])
      : present && gaze ? gaze : [Math.sin(this.time * .23) * .35, Math.sin(this.time * .17 + 1) * .15 - .1];
    const follow = 1 - Math.exp(-dt * (present ? 3 : 1.2));
    this.look[0] += (target[0] - this.look[0]) * follow;
    this.look[1] += (target[1] - this.look[1]) * follow;

    return this.pose();
  }

  pose() {
    const p = restPose(), t = this.time;
    p.breathe = Math.sin(t * 1.6) * .5 + .5;
    p.headYaw = this.look[0] * .38;
    p.headPitch = -this.look[1] * .16;
    p.headRoll = Math.sin(t * .31) * .025;
    p.antenna = Math.sin(t * 1.1) * .05 - p.headYaw * .25;
    p.legs[0].swing = Math.sin(t * 1.05) * .10;
    p.legs[1].swing = Math.sin(t * 1.05 + 2.1) * .10;
    p.lookX = this.look[0]; p.lookY = this.look[1];
    p.blink = this.blinkT >= 0 ? Math.sin(this.blinkT / .18 * Math.PI) : 0;
    if (this.smileT >= 0) p.smile = .18 + .55 * pulse(0, .5, SMILE_S - .7, SMILE_S, this.smileT);

    const a = this.actionT;
    if (this.action === 'wave') {
      // Права рука вгору, кисть гойдається; голова трохи нахилена, усмішка.
      const lift = pulse(0, .55, WAVE_S - .7, WAVE_S, a);
      const wag = Math.sin((a - .4) * 9) * pulse(.5, .8, WAVE_S - 1, WAVE_S - .6, a);
      p.arms[1].raise = 1.45 * lift; p.arms[1].forward = .26 * (1 - lift) + .15 * lift;
      p.arms[1].bend = .12 + (.45 + .25 * wag) * lift;
      p.headRoll += -.12 * lift; p.headYaw *= 1 - .4 * lift;
      p.smile = .18 + .62 * lift; p.antenna += .12 * wag * lift;
      p.legs.forEach(l => { l.swing *= 1 + 1.5 * lift; });
    } else if (this.action === 'antenna') {
      // Підняв ліву руку до антени, «поправив» її, повернув руку.
      const lift = pulse(0, .8, FLOURISH.antenna - .9, FLOURISH.antenna, a);
      const tweak = Math.sin((a - .9) * 7) * pulse(.9, 1.1, 2.2, 2.5, a);
      p.arms[0].raise = 1.85 * lift; p.arms[0].bend = .12 + 1.0 * lift; p.arms[0].forward = .26 * (1 - lift);
      p.headRoll += .10 * lift; p.headPitch += .06 * lift;
      p.antenna += .35 * tweak;
      p.curiosity = .6 * lift;
    } else if (this.action === 'look') {
      // Озирнувся ліворуч і праворуч, ніби щось почув.
      const turn = Math.sin(a / FLOURISH.look * Math.PI * 2) * pulse(0, .6, FLOURISH.look - .7, FLOURISH.look, a);
      p.headYaw += .55 * turn; p.lookX = clamp(p.lookX + turn, -1, 1);
      p.surprise = .35 * pulse(0, .4, 1.2, 1.8, a);
      p.antenna += -.15 * turn;
    } else if (this.action === 'visit') {
      visitPose(p, a);
    }

    if (this.bumpT >= 0 && !this.action.startsWith('visit')) {
      // Літера підкинула його: підскок, руки для рівноваги, «ух!» — і усмішка.
      // Через раз — радісніше, з ногами вгору.
      const b = this.bumpT, big = this.bumps % 2 === 1;
      const up = arc(.05, .75, b);
      p.hop += (big ? .07 : .035) * up;
      const arms = pulse(0, .3, .9, 1.4, b) * (big ? 1 : .55);
      p.arms[0].raise = Math.max(p.arms[0].raise, .7 * arms); p.arms[1].raise = Math.max(p.arms[1].raise, .7 * arms);
      p.legs.forEach(l => { l.swing -= (big ? .5 : .2) * up; });
      p.surprise = Math.max(p.surprise, .55 * pulse(0, .15, .35, .6, b));
      p.smile = Math.max(p.smile, .18 + .6 * pulse(.45, .7, BUMP_S - .5, BUMP_S, b));
      p.antenna += .25 * Math.sin(b * 14) * (1 - smooth(0, BUMP_S, b));
    }
    return p;
  }
}

// Візит: зістрибнув з літери, підійшов до камери, помахав з усмішкою,
// розвернувся, пішов назад і застрибнув на місце.
const V = { ready: .7, off: 1.5, near: 4.0, waved: 7.1, turned: 7.6, back: 9.5, faced: 9.9, end: VISIT_S };
const HOP_TRAVEL = .22;
function walk(p, phase, amount) {
  const s = Math.sin(phase);
  p.legs[0].thigh = -.45 * s * amount; p.legs[1].thigh = .45 * s * amount;
  p.legs[0].swing = .55 * Math.max(0, -Math.cos(phase)) * amount;
  p.legs[1].swing = .55 * Math.max(0, Math.cos(phase)) * amount;
  p.arms[0].forward = .1 + .35 * s * amount; p.arms[1].forward = .1 - .35 * s * amount;
  p.hop += .018 * Math.abs(Math.cos(phase)) * amount;
  p.lean += .05 * amount;
}
function visitPose(p, a) {
  const ease = (x, y) => smooth(x, y, a);
  // Готується: нахилився вперед, руки назад.
  const ready = pulse(0, V.ready, V.ready, V.off, a);
  p.lean += .28 * ready; p.arms.forEach(arm => { arm.forward -= .6 * ready; });
  // Стрибок униз (і назад нагору наприкінці).
  const down = ease(V.ready, V.off), up = ease(V.faced, V.end);
  p.sit = 1 - down + up;
  p.hop += .35 * arc(V.ready, V.off, a) + .35 * arc(V.faced, V.end, a);
  const jump = arc(V.ready, V.off, a) + arc(V.faced, V.end, a);
  p.arms.forEach(arm => { arm.raise = Math.max(arm.raise, .9 * jump); });
  // Шлях: на літері → унизу перед нею → біля камери → назад.
  const going = ease(V.off, V.near), coming = ease(V.turned, V.back);
  p.travel = HOP_TRAVEL * down * (1 - up) + (1 - HOP_TRAVEL) * (going - coming);
  if (a > V.off && a < V.near) walk(p, (a - V.off) * 7.5, pulse(V.off, V.off + .3, V.near - .4, V.near, a));
  if (a > V.turned && a < V.back) walk(p, (a - V.turned) * 7.5, pulse(V.turned, V.turned + .3, V.back - .3, V.back, a));
  // Розворот спиною й назад обличчям.
  p.yaw = Math.PI * (ease(V.waved, V.turned) - ease(V.back, V.faced));
  // Біля камери: махає правою, ліва трохи піднята, широка усмішка.
  const wave = pulse(V.near - .3, V.near + .4, V.waved - .6, V.waved, a);
  const wag = Math.sin((a - V.near) * 9) * pulse(V.near + .3, V.near + .6, V.waved - .9, V.waved - .5, a);
  p.arms[1].raise = Math.max(p.arms[1].raise, 1.6 * wave); p.arms[1].bend = .12 + (.5 + .3 * wag) * wave;
  p.arms[1].forward = p.arms[1].forward * (1 - wave) + .2 * wave;
  p.arms[0].raise = Math.max(p.arms[0].raise, .35 * wave);
  p.headRoll += -.14 * wave; p.antenna += .15 * wag * wave;
  p.hop += .02 * Math.abs(Math.sin((a - V.near) * 4.5)) * wave;
  p.smile = Math.max(p.smile, .18 + .45 * ease(V.off, V.near - .5) + .4 * wave - .45 * ease(V.waved, V.back));
  p.surprise = .4 * pulse(V.ready - .2, V.ready, V.ready + .2, V.off, a);
}
