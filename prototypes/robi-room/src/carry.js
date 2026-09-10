import { idlePose, mixPose, smooth } from './motion.js';

// A bounded pendulum, integrated in small steps so touch event rate cannot
// change its stability. Rendering and pointer capture live in main.js.
export class CarryMotion {
  constructor() { this.mode = 'idle'; this.weight = 0; this.angle = 0; this.velocity = 0; this.time = 0; this.offset = { x: 0, y: 0 }; }
  grab(pose) {
    this.mode = 'held'; this.time = 0; this.from = structuredClone(pose);
    this.lastPose = this.from;
    this.weight = 0; this.angle = this.velocity = 0;
  }
  release() {
    if (this.mode !== 'held') return;
    this.mode = 'returning'; this.time = 0; this.releaseWeight = this.weight;
    this.releaseOffset = { ...this.offset };
    this.releasePose = this.lastPose ?? this.from; this.returnMix = 1;
  }
  reset() { this.mode = 'idle'; this.weight = 0; this.angle = this.velocity = 0; this.offset = { x: 0, y: 0 }; }
  update(dt, horizontalSpeed = 0, reduced = false) {
    if (this.mode === 'idle') return;
    dt = Math.min(.08, Math.max(0, dt)); this.time += dt;
    if (this.mode === 'held') this.weight = smooth(0, reduced ? .12 : .32, this.time);
    else {
      const left = 1 - smooth(0, reduced ? .25 : .8, this.time);
      this.returnMix = left;
      this.weight = this.releaseWeight * left;
      this.offset.x = this.releaseOffset.x * left; this.offset.y = this.releaseOffset.y * left;
      if (!left) { this.reset(); return; }
    }
    const target = reduced ? 0 : Math.max(-.38, Math.min(.38, horizontalSpeed * .075));
    for (let remaining = dt; remaining > 1e-8;) {
      const h = Math.min(1 / 120, remaining); remaining -= h;
      this.velocity += ((target - this.angle) * 48 - this.velocity * 7) * h;
      this.angle = Math.max(-.42, Math.min(.42, this.angle + this.velocity * h));
    }
    if (reduced) this.angle = this.velocity = 0;
  }
  pose(base, reduced = false) {
    if (this.mode === 'idle') return base;
    if (this.mode === 'returning') return mixPose(base, this.releasePose, this.returnMix);
    const hang = idlePose(0, { x: base.lookX, y: base.lookY }, true);
    const wiggle = reduced ? 0 : Math.sin(this.time * 3.8) * .055;
    hang.suspend = 1; hang.dangle = this.angle;
    hang.tilt = this.angle; hang.headZ = -this.angle * .92;
    hang.headX = -.025; hang.lean = .025;
    hang.smile = this.time > 1.1 ? .25 : 0;
    hang.surprise = this.mode === 'held' ? 1 - smooth(.35, 1.2, this.time) : 0;
    hang.blink = base.blink;
    hang.arms.forEach((arm, i) => {
      const side = i ? 1 : -1;
      arm.z = side * .075 - this.angle * .55 + side * wiggle;
      arm.x = -.035; arm.ex = -.15 + wiggle; arm.ez = side * .055;
      arm.wx = .12; arm.wz = -this.angle * .25; arm.curl = .22; arm.spread = .015;
    });
    const source = this.mode === 'held' ? this.from : base;
    this.lastPose = mixPose(source, hang, this.weight); return this.lastPose;
  }
}
