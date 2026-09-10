import { idlePose, mixPose, smooth } from './motion.js';

const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const STEP_TIME = .46, STEP_LENGTH = .26, STEP_LIFT = .12, TURN_TIME = .55;

export class RoomWalker {
  constructor() {
    this.autonomous = true; this.requestedTarget = null;
    this.x = 0; this.yaw = -.10; this.enabled = false; this.mode = 'resting';
    this.time = 0; this.left = -1; this.right = 1; this.trip = 0; this.amount = 0; this.stepIndex = 0;
    this.feet = this.stance(); this.swing = 0; this.lastPose = idlePose(0);
  }
  stance(x = this.x, yaw = this.yaw) {
    return [-1, 1].map(side => ({ x: x + side * .36 * Math.cos(yaw) + .015 * Math.sin(yaw), z: -side * .36 * Math.sin(yaw) + .015 * Math.cos(yaw), y: 0 }));
  }
  setBounds(left, right) {
    this.left = left; this.right = Math.max(left, right);
    const bounded = clamp(this.x, this.left, this.right);
    if (bounded !== this.x || (this.target != null && (this.target < left || this.target > right))) {
      this.x = bounded; this.interrupt();
    }
  }
  land(x, explore = true) {
    this.x = clamp(x, this.left, this.right); this.enabled ||= explore;
    this.yaw = -.10; this.amount = 0; this.mode = 'landing'; this.time = 0;
    this.feet = this.stance();
  }
  interrupt() {
    this.requestedTarget = null;
    if (this.mode === 'settling') return;
    this.fromYaw = this.yaw; this.fromAmount = this.amount;
    this.fromPose = this.lastPose; this.mode = 'settling'; this.time = 0;
  }
  startTurn() {
    const middle = (this.left + this.right) / 2;
    const directed = this.requestedTarget != null;
    this.target = directed ? this.requestedTarget : this.x <= middle ? this.right - .12 : this.left + .12;
    this.target = clamp(this.target, this.left, this.right);
    if (Math.abs(this.target - this.x) < (directed ? .04 : STEP_LENGTH * 2)) { this.mode = 'resting'; this.time = 0; return; }
    this.direction = Math.sign(this.target - this.x);
    // Whole strides: half a step out of the turn, half a step into the stop, full
    // steps between. A trip that ended on whatever was left over finished on a
    // stub step and left one foot a whole stride behind the hips.
    if (!directed) this.target = this.x + this.direction * STEP_LENGTH * Math.floor(Math.abs(this.target - this.x) / STEP_LENGTH);
    this.fromYaw = this.yaw; this.targetYaw = this.direction * 1.22;
    this.mode = 'turning'; this.time = 0; this.stepIndex = 0;
  }
  startStep() {
    this.mode = 'walking'; this.time = 0; this.startX = this.x;
    const remaining = Math.abs(this.target - this.x);
    this.firstStep = this.stepIndex === 0; this.lastStep = remaining <= STEP_LENGTH * .75;
    const stride = this.firstStep || this.lastStep ? STEP_LENGTH * .5 : STEP_LENGTH;
    this.endX = this.x + this.direction * Math.min(stride, remaining);
    this.startFoot = { ...this.feet[this.swing] };
    // The swing foot lands half a stride ahead of where the body will be, so each
    // leg reaches forward and then pushes off behind. Landing it under the hip
    // instead let both feet only ever trail, which reads as a drag, and left the
    // trailing leg at exactly full extension at every footfall.
    const reach = this.lastStep ? 0 : this.direction * STEP_LENGTH * .5;
    this.endFoot = this.stance(this.endX + reach)[this.swing];
  }
  update(dt, blocked = false, reduced = false) {
    dt = clamp(dt, 0, .08);
    if ((blocked || reduced) && ['walking', 'turning'].includes(this.mode)) this.interrupt();
    if (this.mode === 'settling') {
      this.settleDuration = reduced ? .15 : .32;
      this.time += dt; const t = smooth(0, this.settleDuration, this.time);
      this.yaw = lerp(this.fromYaw, -.10, t); this.amount = this.fromAmount * (1 - t);
      if (t === 1) { this.mode = 'resting'; this.time = 0; this.feet = this.stance(); }
      return;
    }
    if (blocked || reduced || !this.enabled) return;
    this.time += dt;
    if (this.mode === 'landing' || this.mode === 'resting') {
      if ((this.autonomous || this.requestedTarget != null) && this.time > (this.mode === 'landing' ? 1.25 : this.requestedTarget != null ? .1 : 2.8 + this.trip % 3 * .65)) this.startTurn();
    } else if (this.mode === 'turning') {
      const t = smooth(0, TURN_TIME, this.time);
      this.yaw = lerp(this.fromYaw, this.targetYaw, t); this.amount = t;
      this.feet = this.stance();
      // A small shuffle accompanies the turn before the first full step.
      this.feet[this.direction > 0 ? 1 : 0].y = .035 * Math.sin(Math.PI * t);
      if (t === 1) this.startStep();
    } else if (this.mode === 'walking') {
      const u = Math.min(1, this.time / STEP_TIME), t = smooth(0, 1, u);
      // The body holds one speed for the whole trip. Easing every step made it
      // stop dead at each footfall; the opening and closing half strides carry
      // the acceleration, and each profile hands over at the same speed.
      const travel = this.firstStep ? u * u : this.lastStep ? u * (2 - u) : u;
      this.x = lerp(this.startX, this.endX, travel);
      const foot = this.feet[this.swing];
      foot.x = lerp(this.startFoot.x, this.endFoot.x, t);
      foot.z = lerp(this.startFoot.z, this.endFoot.z, t);
      foot.y = STEP_LIFT * Math.sin(Math.PI * u) ** 1.5;
      // The other foot stays at its saved world position throughout the step.
      if (u === 1) {
        foot.y = 0; this.swing = 1 - this.swing; this.stepIndex++;
        if (Math.abs(this.target - this.x) < .001) { this.trip++; this.interrupt(); }
        else this.startStep();
      }
    }
  }
  goTo(x) {
    const target = clamp(x, this.left, this.right);
    if (Math.abs(this.x - target) < .04 && !this.moving) return true;
    if (this.moving) return false;
    this.enabled = true; this.requestedTarget = target;
    return false;
  }
  pose(base) {
    if (this.mode === 'settling') {
      this.lastPose = mixPose(base, this.fromPose, 1 - smooth(0, this.settleDuration ?? .32, this.time));
      return this.lastPose;
    }
    if (!['walking', 'turning'].includes(this.mode)) {
      const p = structuredClone(base);
      if (this.enabled) p.headY += Math.sin(this.time * 1.3) * .16;
      this.lastPose = p; return p;
    }
    const p = structuredClone(base), turning = this.mode === 'turning';
    // The whole gait fades in across the turn, so no joint snaps into place on
    // the first step; from there every term is continuous across the footfall.
    const enter = turning ? smooth(0, TURN_TIME, this.time) : 1;
    const into = (from, to) => from + (to - from) * enter;
    const u = turning ? 0 : Math.min(1, this.time / STEP_TIME);
    const side = this.swing ? 1 : -1, swing = Math.sin(Math.PI * u), stride = Math.cos(Math.PI * u);
    // The hips sit lowest at the footfall, when the legs are spread, and rise
    // over the near-straight stance leg. Rising at the footfall instead fought
    // the stride for reach and pushed the knees into their limit.
    p.bob = into(base.bob, -.028 - .022 * Math.cos(u * Math.PI * 2));
    p.shift = into(base.shift, -side * .028 * swing); p.lean = into(base.lean, .035);
    p.tilt = into(base.tilt, -side * .025 * swing); p.turn = into(base.turn, 0);
    p.headY = into(base.headY, -this.direction * .20); p.headZ = into(base.headZ, -p.tilt * .5);
    p.headX = into(base.headX, -.015); p.smile = into(base.smile, .16);
    p.antenna = into(base.antenna, .016 * swing);
    this.feet.forEach((foot, i) => {
      const dx = foot.x - this.x, c = Math.cos(this.yaw), s = Math.sin(this.yaw);
      p.footX[i] = dx * c - foot.z * s - (i ? .36 : -.36);
      p.footZ[i] = dx * s + foot.z * c - .015;
      p.feet[i] = foot.y;
      // Toe down as the foot leaves the ground, up again before it lands. Both
      // ends of the swing reach zero, so nothing flicks at lift-off or contact.
      p.toe[i] = i === this.swing ? .17 * Math.sin(2 * Math.PI * u) * enter : 0;
      // Arms are furthest out at the footfall and neutral at mid-stance, matching
      // the legs they oppose and carrying across the step without a reversal.
      p.arms[i].x = into(base.arms[i].x, (i === this.swing ? -.30 : .30) * stride);
      p.arms[i].z = into(base.arms[i].z, (i ? 1 : -1) * .14);
      p.arms[i].ex = into(base.arms[i].ex, -.22); p.arms[i].ez = into(base.arms[i].ez, (i ? 1 : -1) * .065);
    });
    this.lastPose = p; return p;
  }
  get moving() { return ['walking', 'turning', 'settling'].includes(this.mode); }
}
