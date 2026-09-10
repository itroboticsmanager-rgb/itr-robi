import { smooth, mixPose } from './motion.js';

const SCENES = { peek: 11.8, greet: 12.8, curious: 12.5, side: 12.8, peekaboo: 15, guide: 14.5 };
export const KINDS = Object.keys(SCENES);
const pulse = (a, b, c, d, t) => smooth(a, b, t) * (1 - smooth(c, d, t));

export class CameoDirector {
  constructor(random = Math.random) {
    this.random = random; this.wait = 12 + random() * 6;
    this.target = 'menu';
    this.kind = ''; this.previous = ''; this.elapsed = 0;
    this.duration = 0; this.side = 1; this.greeted = -1;
  }
  force(kind) {
    if (!KINDS.includes(kind)) return false;
    this.kind = this.previous = kind; this.duration = SCENES[kind];
    this.elapsed = 0; this.greeted = -1; this.side = this.random() < .5 ? -1 : 1;
    if (kind === 'guide') this.target = this.target === 'menu' ? 'banner' : 'menu';
    return true;
  }
  greet() {
    // Do not extend the timeline during departure: that rewinds the entrance.
    if (!this.kind || this.elapsed < (this.kind === 'peekaboo' ? 6.8 : this.kind === 'peek' ? 4 : 2.8) || this.elapsed > this.duration - 5 || (this.greeted >= 0 && this.elapsed - this.greeted < 4)) return false;
    this.greeted = this.elapsed;
    return true;
  }
  reset() { this.kind = ''; this.wait = 55 + this.random() * 35; }
  update(dt, { reduced = false, paused = false, allowed = KINDS } = {}) {
    if (paused || reduced) return null;
    dt = Math.max(0, dt);
    if (!this.kind) {
      this.wait -= dt;
      if (this.wait > 0) return null;
      const valid = allowed.filter(kind => KINDS.includes(kind));
      const choices = valid.length > 1 ? valid.filter(k => k !== this.previous) : valid;
      if (!choices.length) return null;
      this.force(choices[Math.min(choices.length - 1, Math.floor(this.random() * choices.length))]);
    }
    this.elapsed += dt;
    if (this.elapsed >= this.duration) {
      this.reset(); return null;
    }
    return { kind: this.kind, side: this.side, t: this.elapsed, duration: this.duration, target: this.target,
      greeted: this.greeted >= 0 ? this.elapsed - this.greeted : -1 };
  }
}

export function cameoPlacement({ t, duration, side, kind }, frame) {
  const { halfWidth, halfHeight, height } = frame;
  const exit = 1-smooth(duration-2.6,duration,t);
  const entry = smooth(.3,2.8,t);
  const lane = halfWidth-height*.54;
  let reveal=entry*exit, x=side*lane, roll=0;
  if(kind==='peek') {
    // First just the eyes, a deliberate pause, then the rest of the face.
    reveal=(.46*smooth(.3,1.7,t)+.54*smooth(2.6,4,t))*exit;
  } else if(kind==='peekaboo') {
    // One shy look, disappear completely, then return a little closer in.
    reveal=(.56*pulse(.3,1.7,2.8,4,t)+smooth(4.9,6.8,t))*exit;
    x-=side*height*.13*smooth(4,4.85,t);
  } else if(kind==='side') {
    const off=halfWidth+height*.65;
    x=side*(off+(lane-off)*reveal);
    roll=-side*.16*pulse(.3,2,6.8,9,t);
    return {x,y:-halfHeight-height*.28,turn:-side*.06,roll,visible:reveal>0};
  } else if(kind==='curious') {
    const inspect=pulse(3.2,4.8,6.3,8,t);
    x-=side*height*.10*inspect;
    roll=side*.045*inspect;
  }
  return {x,y:-halfHeight-height*1.05+height*.76*reveal,
    turn:-side*.09,roll,visible:reveal>0};
}

function wave(p, time, side = 1) {
  const engage = pulse(0, .85, 3.0, 4.3, time);
  const lift = pulse(.3, 1.25, 2.85, 4.05, time);
  const flutter = Math.sin((time - 1.3) * 5.8) * pulse(1.3, 1.65, 2.65, 3.05, time);
  const arm = p.arms[side === 1 ? 1 : 0], sign = side;
  p.shift -= sign * .065 * engage; p.tilt += sign * .045 * engage;
  p.headZ -= sign * .075 * pulse(.12, 1, 3.05, 4.25, time);
  arm.z += sign * 1.8 * lift; arm.x += .12 * lift;
  arm.ez += sign * .32 * lift; arm.wz += sign * (.16 * flutter);
  arm.curl *= 1 - lift; arm.present = .85 * lift; arm.spread = .06 * lift;
  p.smile = Math.max(p.smile, .65 * engage);
  p.antenna += sign * .025 * Math.sin((time - .4) * 4.2) * engage;
}

export function cameoPose(pose, cameo, attention = { x: -cameo.side * .5, y: -.7 }) {
  const p = structuredClone(pose), { t, duration, kind, side, greeted } = cameo;
  const settled = pulse(1.8, 3.1, duration - 3.3, duration - 1.4, t);
  const glance = pulse(2.7, 3.6, 4.3, 5.5, t);
  const notice = pulse(4.5, 5.4, duration - 3.5, duration - 2.5, t);
  // Eyes lead, then the head settles, then shoulders follow. Small, finite gestures.
  p.lookX = -side * .48 * glance;
  p.headY = -side * .19 * pulse(2.9, 4, 4.5, 5.9, t);
  p.turn = -side * .045 * pulse(3.2, 4.3, 4.6, 6.2, t);
  p.lookY = .08 * settled;
  p.curiosity = (kind === 'curious' ? .5 : .18) * glance;
  p.smile = .22 * settled + .28 * notice;
  p.headZ = side * .065 * pulse(4.6, 5.6, 7.3, 8.8, t);
  p.headX += .05 * pulse(5.8, 6.35, 6.5, 7.2, t);
  p.shift *= .45; p.bob *= .7;
  const depart = pulse(duration - 3.2, duration - 2.7, duration - 1, duration, t);
  p.headX += .08 * depart; p.lean += .025 * depart;
  const responseBase = structuredClone(p);
  if (kind === 'greet') wave(p, t - 4.6);
  if (kind === 'side') { wave(p,t-4.1); p.headZ+=side*.10*pulse(1.4,2.7,4,5,t); }
  if (kind === 'peekaboo') {
    wave(p,t-7.1);
    p.surprise=.55*pulse(5.6,6.5,7.2,8,t);
    p.lookX=-side*.35*pulse(1.4,2,2.6,3.6,t);
    p.headY=-side*.12*pulse(1.5,2.2,2.8,3.8,t);
  }
  if (kind === 'peek') {
    p.lookX=side*.42*pulse(1.4,1.95,2.35,3,t)-side*.3*pulse(4.1,4.8,5.3,6.1,t);
    p.headZ+=side*.10*pulse(3.4,4.5,6.1,7.5,t);
  }
  if (kind === 'curious') {
    p.headZ += side * .075 * pulse(5.2, 6.4, 7.2, 8.5, t);
    p.curiosity += .25 * notice;
  }
  if (kind === 'guide') {
    const eyes = pulse(3.2, 4.1, 7.4, 8.6, t);
    const head = pulse(3.5, 4.6, 7.6, 9, t);
    const hand = pulse(4, 5.3, 7.2, 8.8, t);
    p.lookX = attention.x * .65 * eyes; p.lookY = attention.y * .65 * eyes;
    p.headY = attention.x * .32 * head; p.headX += -attention.y * .24 * head;
    p.headZ = side * .035 * head;
    const sign = attention.x < 0 ? -1 : 1, arm = p.arms[sign === 1 ? 1 : 0];
    arm.z += sign * 1.55 * hand; arm.x += .18 * hand;
    arm.ez += sign * .55 * hand; arm.present = .7 * hand;
    arm.curl *= 1 - hand; arm.spread = .07 * hand;
    p.smile = Math.max(p.smile, .45 * head);
  }
  if (greeted >= 0) {
    wave(responseBase, greeted);
    return mixPose(p, responseBase, pulse(0, .4, 3.7, 4.3, greeted));
  }
  return p;
}
