// «Живе на вивісці» (D-066): Робі постійно сидить на кінці рядка під назвою
// школи. Цей модуль — лише поведінка, без three.js: що робить Робі зараз і
// яку позу з цього виходить. Його читає `robi-model.js` і тести.
//
// Принцип — ефектно, але не нав'язливо: у спокої рухи малі й повільні
// (дихання, кліпання, погляд на людину, ледь гойдає ногами); помітна дія —
// лише тихий помах, коли людина підійшла чи торкнулась, і рідкісна дрібниця
// раз на кілька хвилин.

export const WAVE_S = 3.2;
export const FLOURISH = { antenna: 3.4, look: 4.2 };
/** Після скількох секунд без людини наступна поява знову вітається. */
export const AWAY_S = 15;
/** Помах на появу людини — не частіше. Дотик вітається завжди. */
export const GREET_COOLDOWN_S = 45;
export const FLOURISH_MIN_S = 150, FLOURISH_MAX_S = 300;

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const pulse = (a, b, c, d, t) => smooth(a, b, t) * (1 - smooth(c, d, t));

export function restPose() {
  return {
    breathe: 0, headYaw: 0, headPitch: 0, headRoll: 0, antenna: 0,
    // Руки лежать на краю, де він сидить: трохи вперед і вниз.
    arms: [{ raise: 0, forward: .26, bend: .12 }, { raise: 0, forward: .26, bend: .12 }],
    // Ноги звисають з краю; swing — гойдання гомілок.
    legs: [{ swing: 0 }, { swing: 0 }],
    lookX: 0, lookY: 0, blink: 0, smile: .18, surprise: 0, curiosity: 0,
  };
}

export class SitDirector {
  constructor(random = Math.random) {
    this.random = random;
    this.time = 0;
    this.action = '';            // '', 'wave', 'antenna', 'look'
    this.actionT = 0;
    this.awayFor = AWAY_S;       // перша людина після запуску теж вітається
    this.sinceGreet = Infinity;
    this.nextFlourish = this.#flourishDelay();
    this.nextBlink = 2 + random() * 3;
    this.blinkT = -1;
    this.look = [0, 0];
  }
  #flourishDelay() { return FLOURISH_MIN_S + this.random() * (FLOURISH_MAX_S - FLOURISH_MIN_S); }

  /** Помітна дія зараз — сторінка тим часом не гортає банери. */
  get performing() { return this.action !== ''; }
  get kind() { return this.action; }

  /** Торкнулись Робі. */
  greet() {
    if (this.action === 'wave') return false;
    this.#start('wave');
    return true;
  }
  /** Сторінка повернулась на головну — без незавершених дій. */
  reset() { this.action = ''; this.actionT = 0; }
  force(kind) {
    if (!['wave', ...Object.keys(FLOURISH)].includes(kind)) return false;
    this.#start(kind); return true;
  }
  #start(kind) {
    this.action = kind; this.actionT = 0;
    if (kind === 'wave') this.sinceGreet = 0;
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

    if (present) {
      if (this.awayFor >= AWAY_S && this.sinceGreet >= GREET_COOLDOWN_S && !this.action) this.#start('wave');
      this.awayFor = 0;
    } else {
      this.awayFor += dt;
    }

    if (this.action) {
      this.actionT += dt;
      const length = this.action === 'wave' ? WAVE_S : FLOURISH[this.action];
      if (this.actionT >= length) { this.action = ''; this.actionT = 0; }
    } else if (!present) {
      // Дрібниці лише коли поруч нікого: людині він дивиться в очі.
      this.nextFlourish -= dt;
      if (this.nextFlourish <= 0) {
        this.#start(this.random() < .5 ? 'antenna' : 'look');
        this.nextFlourish = this.#flourishDelay();
      }
    }

    this.nextBlink -= dt;
    if (this.nextBlink <= 0) { this.blinkT = 0; this.nextBlink = 2.5 + this.random() * 4; }
    if (this.blinkT >= 0) { this.blinkT += dt; if (this.blinkT > .18) this.blinkT = -1; }

    // Погляд повільно наздоганяє людину, а без неї — спокійно блукає.
    const target = present && gaze ? gaze : [Math.sin(this.time * .23) * .35, Math.sin(this.time * .17 + 1) * .15 - .1];
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
    }
    return p;
  }
}
