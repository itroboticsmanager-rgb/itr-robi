import { smooth } from './motion.js';

// Short performances separated by real pauses. Hidden tabs never catch up.
export class WindowPresence {
  constructor(random = Math.random) {
    this.random = random; this.wait = 1.5 + random() * 3;
    this.elapsed = 0; this.kind = ''; this.previous = ''; this.duration = 0; this.side = 0;
  }
  update(dt, { paused = false, reduced = false } = {}) {
    if (paused || reduced) return this.sample(reduced);
    if (!this.kind) {
      this.wait -= dt;
      if (this.wait <= 0) {
        const choices = ['wave', 'hop', 'curious', 'shy', 'hello'].filter(k => k !== this.previous);
        this.kind = choices[Math.floor(this.random() * choices.length)]; this.previous = this.kind;
        this.duration = 4.8 + this.random() * 3; this.side = (this.random() - .5) * 2.2; this.elapsed = 0;
      }
    } else {
      this.elapsed += dt;
      if (this.elapsed >= this.duration) { this.kind = ''; this.wait = 13 + this.random() * 27; }
    }
    return this.sample(reduced);
  }
  sample(reduced = false) {
    if (reduced) return { reveal: .78, x: 0, jump: 0, kind: 'calm', progress: 0 };
    if (!this.kind) return { reveal: 0, x: this.side, jump: 0, kind: '', progress: 0 };
    const t = this.elapsed;
    const reveal = Math.max(0, Math.min(1, smooth(0, this.kind === 'hop' ? .5 : 1, t) * (1 - smooth(this.duration - 1.1, this.duration, t))));
    return { reveal, x: this.side, kind: this.kind, progress: t,
      jump: this.kind === 'hop' ? Math.sin(Math.PI * Math.min(1, t / 1.2)) * .46 : 0 };
  }
}

export function windowPose(pose, appearance) {
  const p = structuredClone(pose), t = appearance.progress;
  p.curiosity = 0; p.smile = 0;
  if (appearance.kind === 'wave' || appearance.kind === 'hello') {
    const wave = smooth(.7, 1.5, t) * (1 - smooth(3.1, 4.2, t));
    p.arms[1].z += 2 * wave; p.arms[1].ez += .48 * wave;
    p.arms[1].wz += Math.sin(t * 9) * .3 * wave;
    p.arms[1].curl *= 1 - wave; p.arms[1].present = wave;
    p.headZ = -.12 * wave; p.smile = .8 * wave;
    if (appearance.kind === 'hello') p.headX += Math.sin(t * 5) * .09 * wave;
  } else if (appearance.kind === 'curious') {
    p.headY = Math.sin(t * 1.3) * .3; p.lookX = Math.sin(t * 1.3) * .65;
    p.headZ = .16 * Math.sin(t); p.curiosity = .8;
  } else if (appearance.kind === 'shy') {
    p.headZ = -.19; p.lookX = .35; p.smile = .35;
    p.blink = Math.max(p.blink, smooth(2, 2.1, t) * (1 - smooth(2.2, 2.35, t)));
  } else if (appearance.kind === 'hop') {
    p.surprise = .65 * (1 - smooth(1.4, 2.4, t)); p.smile = .65 * smooth(1.4, 2.4, t);
    p.antenna += Math.sin(t * 8) * .07 * Math.exp(-t);
  }
  return p;
}
