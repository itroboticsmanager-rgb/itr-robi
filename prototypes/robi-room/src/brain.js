// Local, deterministic intentions. No renderer, network or visitor identity.
const limit = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const stations = { build: -.15, ball: 2.10, lamp: -.15, rest: .6 };
export function readWorld(storage) {
  try {
    const value = JSON.parse(storage.getItem('robi-workshop-v1'));
    return { blocks: Number.isInteger(value?.blocks) ? limit(value.blocks, 0, 3) : 0, lamp: typeof value?.lamp === 'boolean' ? value.lamp : true };
  } catch { return { blocks: 0, lamp: true }; }
}
export class WorkshopBrain {
  constructor(world = {}) {
    this.world = { blocks: Number.isInteger(world.blocks) ? limit(world.blocks, 0, 3) : 0, lamp: world.lamp !== false };
    this.task = 'rest'; this.phase = 'rest'; this.elapsed = 0; this.wait = 5;
    this.resume = null; this.events = []; this.revision = 0; this.cycle = 0;
    this.ballAtVisitor = false; this.ballReturning = false;
  }
  emit(text) { this.events.push(text); }
  drain() { return this.events.splice(0); }
  start(task, returning = false) {
    this.task = task; this.phase = 'notice'; this.elapsed = 0;
    const lines = { build: returning ? 'Повернуся до конструктора. Пам’ятаю, де зупинився!' : 'Спробую скласти маленьку вежу.', ball: 'Бачу м’яч! Зараз поверну його тобі.', lamp: this.world.lamp ? 'О, світліше! Деталі краще видно.' : 'Світло згасло. Я помітив!', rest: 'Трохи помилуюся своєю роботою.' };
    this.emit(lines[task]);
  }
  interact(object, reduced = false) {
    if (!['ball', 'blocks', 'lamp'].includes(object)) return false;
    if (object === 'lamp') { this.world.lamp = !this.world.lamp; this.revision++; }
    if (reduced) {
      if (object === 'blocks') { this.world.blocks = (this.world.blocks + 1) % 4; this.revision++; }
      this.emit(object === 'lamp' ? (this.world.lamp ? 'Лампу увімкнено.' : 'Лампу вимкнено.') : object === 'ball' ? 'М’яч на місці. Можемо пограти без руху.' : `У вежі деталей: ${this.world.blocks}.`);
      return true;
    }
    const next = object === 'blocks' ? 'build' : object;
    // Repeated taps do not restart an action or pile up an unbounded queue.
    if (this.task === next && this.phase !== 'rest' && object !== 'lamp') return true;
    if (next === 'ball') { this.ballReturning = this.ballAtVisitor; this.ballAtVisitor = false; }
    if (this.task === 'build' && this.world.blocks < 3) this.resume = 'build';
    if (next === 'build') {
      this.resume = null;
      if (this.world.blocks === 3) { this.world.blocks = 0; this.revision++; }
    }
    this.start(next);
    return true;
  }
  update(dt, { paused = false, reduced = false, arrived = true } = {}) {
    if (paused || reduced) return;
    this.elapsed += limit(dt, 0, .1);
    if (this.phase === 'rest') {
      if (this.elapsed >= this.wait) {
        if (this.resume) { const next = this.resume; this.resume = null; this.start(next, true); }
        else this.start(this.world.blocks < 3 ? 'build' : (!this.ballAtVisitor && ++this.cycle % 2 ? 'ball' : 'rest'));
      }
    } else if (this.phase === 'notice' && this.elapsed >= .85) {
      if (this.task === 'ball') this.ballReturning = false;
      this.phase = 'approach'; this.elapsed = 0;
    } else if (this.phase === 'approach' && arrived) {
      this.phase = 'act'; this.elapsed = 0;
    } else if (this.phase === 'act') {
      const duration = this.task === 'build' ? 3.6 : this.task === 'ball' ? 3.2 : 1.8;
      if (this.elapsed >= duration) {
        if (this.task === 'ball') { this.ballAtVisitor = true; this.emit('Твій хід! Торкнися м’яча, щоб повернути його.'); }
        if (this.task === 'build') {
          this.world.blocks = Math.min(3, this.world.blocks + 1); this.revision++;
          if (this.world.blocks < 3) { this.elapsed = 0; return; }
          this.emit('Готово! Три деталі, і вежа тримається.');
        }
        this.phase = 'recover'; this.elapsed = 0;
      }
    } else if (this.phase === 'recover' && this.elapsed >= 1) {
      this.phase = 'rest'; this.elapsed = 0; this.wait = this.resume ? 1.5 : 10;
      this.task = 'rest';
    }
  }
  get target() { return stations[this.task]; }
  get active() { return this.phase !== 'rest'; }
  get status() {
    if (this.phase === 'rest') return this.resume ? 'Пам’ятає про незавершену вежу' : this.world.blocks === 3 ? 'Милується своєю роботою' : 'Обирає наступну справу';
    return { build: `Складає вежу · ${this.world.blocks} із 3 деталей`, ball: 'Грається з м’ячем', lamp: 'Роздивляється світло', rest: 'Відпочиває в майстерні' }[this.task];
  }
}
