// Pose functions are time-based, deterministic and independent of the render rate.
// A single controller composes complete poses so concurrent tweens cannot fight.
export const durations = { greet: 3.8, highfive: 3.5, dance: 5.4, peek: 3.4 };
export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export function smooth(a, b, t) { const v = clamp((t - a) / (b - a)); return v * v * v * (v * (v * 6 - 15) + 10); }
function pulse(a, b, c, d, t) { return smooth(a, b, t) * (1 - smooth(c, d, t)); }
function arm(side) { return { x: -.06, y: 0, z: side * .19, ex: -.12, ez: side * .08, wx: 0, wy: 0, wz: 0, curl: .13, spread: 0, present: 0 }; }
export function idlePose(time, look = { x: 0, y: 0 }, reduced = false) {
  const breath = reduced ? 0 : Math.sin(time * 1.8) * .009;
  const weight = reduced ? 0 : Math.sin(time * .51) * .035;
  // An infrequent paired blink, separated by long still periods.
  const blinkTime = time % 5.9;
  const blink = reduced ? 0 : pulse(3.9, 3.99, 4.035, 4.14, blinkTime);
  return {
    shift: weight, bob: breath, tilt: -weight * .25, lean: .01, turn: look.x * .055,
    headX: -look.y * .095, headY: look.x * .17, headZ: weight * .5,
    antenna: 0,
    lookX: look.x, lookY: look.y, blink, smile: 0, surprise: 0,
    curiosity: reduced ? 0 : pulse(6.0, 7.0, 9.0, 10.2, time % 18) * .65,
    hide: 0, suspend: 0, dangle: 0, arms: [arm(-1), arm(1)], feet: [0, 0], footX: [0, 0], footZ: [0, 0], toe: [0, 0],
  };
}
export function actionPose(name, t, base) {
  const p = structuredClone(base);
  const a = p.arms[1], other = p.arms[0];
  if (name === 'greet') {
    const engage = pulse(0, .5, 2.85, 3.8, t);
    const prepare = pulse(0, .20, .26, .60, t);
    const lift = pulse(.18, .9, 2.58, 3.5, t);
    const wave = Math.sin((t - .94) * 11) * pulse(.9, 1.12, 2.3, 2.65, t);
    p.shift += -.115 * engage;
    p.bob += -.055 * prepare + .025 * engage;
    p.tilt += .075 * engage + .014 * wave;
    p.lean += .075 * engage;
    p.turn += -.085 * engage;
    p.headZ += -.13 * pulse(.08, .68, 2.6, 3.55, t);
    p.headX += .065 * engage;
    p.headY += -.06 * engage;
    a.z += 2.05 * lift; a.x += .20 * lift;
    a.ez += .37 * lift + .10 * wave;
    a.wz += .24 * Math.sin((t - 1.02) * 11) * pulse(.95, 1.15, 2.3, 2.65, t);
    a.wx -= .13 * lift; a.curl *= 1 - lift; a.spread = .08 * lift;
    a.present = .85 * lift;
    other.z -= .12 * engage; other.ex -= .23 * engage; other.wz += .07 * engage;
    p.antenna += .07 * wave + .065 * Math.sin(t * 5.8 - .8) * engage;
    p.smile += .82 * engage;
  } else if (name === 'highfive') {
    const reach = pulse(0, .8, 2.3, 3.5, t);
    const contact = pulse(1.2, 1.35, 1.5, 1.8, t);
    p.shift -= .10 * reach; p.lean += .10 * reach;
    p.tilt += .065 * reach; p.headZ -= .10 * reach;
    a.z += 1.85 * reach; a.x += .35 * reach; a.ez += .6 * reach;
    a.wx -= .23 * reach; a.wy += .08 * reach;
    a.curl = .13 * (1 - reach); a.spread = .13 * reach;
    a.present = reach;
    a.ex -= .20 * contact; p.bob -= .045 * contact;
    other.z -= .2 * reach; other.ex -= .16 * reach;
    p.antenna += .09 * contact; p.smile += .68 * reach * (1 - contact);
    p.surprise += .9 * contact;
  } else if (name === 'dance') {
    const active = pulse(0, .6, 4.55, 5.4, t);
    const beat = Math.sin(t * 6.4), sway = Math.sin(t * 3.2);
    p.shift += .16 * sway * active; p.bob -= .075 * (.5 + .5 * beat) * active;
    p.tilt += -.11 * sway * active; p.turn += .17 * sway * active;
    p.headZ += .14 * Math.sin(t * 3.2 - .4) * active;
    p.headX += .075 * Math.sin(t * 6.4 - .3) * active;
    p.arms.forEach((v, i) => {
      const s = i === 0 ? -1 : 1;
      v.z += s * (.6 + .3 * Math.sin(t * 3.2 + i * Math.PI)) * active;
      v.ex -= (.5 + .35 * Math.sin(t * 3.2 + i * Math.PI)) * active;
      v.ez += s * .3 * active;
      v.wz += .22 * Math.sin(t * 6.4 - .4 + i) * active;
    });
    p.feet = [Math.max(0, -sway) * .14 * active, Math.max(0, sway) * .14 * active];
    p.antenna += .12 * Math.sin(t * 6.4 - .8) * active; p.smile += .95 * active;
  } else if (name === 'peek') {
    const duck = pulse(0, .7, 1.25, 2.1, t);
    const peek = pulse(1.5, 2.1, 2.65, 3.4, t);
    p.hide = duck * 1.75;
    p.headZ -= .15 * peek; p.headY += .1 * peek;
    p.bob -= .12 * duck; p.lean += .14 * duck;
    p.arms[0].z -= .35 * duck; p.arms[1].z += .35 * duck;
    p.antenna -= .13 * duck;
    p.surprise += pulse(1.5, 1.9, 2.15, 2.5, t);
    p.smile += .65 * pulse(2.35, 2.7, 2.9, 3.4, t);
  }
  return p;
}
export function mixPose(a, b, t) {
  const result = {};
  for (const key of Object.keys(a)) {
    if (typeof a[key] === 'number') result[key] = a[key] + (b[key] - a[key]) * t;
    else if (Array.isArray(a[key])) result[key] = a[key].map((v, i) => typeof v === 'number' ? v + (b[key][i] - v) * t : mixPose(v, b[key][i], t));
  }
  return result;
}

export class MotionController {
  constructor() { this.time = 0; this.action = null; this.elapsed = 0; this.pose = idlePose(0); this.from = this.pose; this.look = { x: 0, y: 0 }; this.reduced = false; }
  play(name) {
    if (!(name in durations)) return false;
    this.from = structuredClone(this.pose);
    this.action = name; this.elapsed = 0;
    return true;
  }
  update(dt, targetLook = { x: 0, y: 0 }) {
    dt = clamp(dt, 0, .08);
    this.time += dt; this.elapsed += dt;
    const follow = 1 - Math.exp(-dt * 5);
    this.look.x += (clamp(targetLook.x, -1, 1) - this.look.x) * follow;
    this.look.y += (clamp(targetLook.y, -1, 1) - this.look.y) * follow;
    const base = idlePose(this.time, this.look, this.reduced);
    if (this.reduced) {
      this.pose = base;
      if (this.elapsed > .6) this.action = null;
      return this.pose;
    }
    if (this.action && this.elapsed >= durations[this.action]) this.action = null;
    const target = this.action ? actionPose(this.action, this.elapsed, base) : base;
    this.pose = this.action ? mixPose(this.from, target, smooth(0, .22, this.elapsed)) : target;
    return this.pose;
  }
}
