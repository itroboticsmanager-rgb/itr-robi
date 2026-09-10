import test from 'node:test';
import assert from 'node:assert/strict';
import { CameoDirector, cameoPlacement, cameoPose, KINDS } from '../src/cameo.js';
import { idlePose } from '../src/motion.js';

const frame = {halfWidth: 4.5, halfHeight: 1, height: 1.56, scale: .4};
function flatten(o) { return typeof o === 'number' ? [o] : Object.values(o).flatMap(flatten); }
test('cameos have continuous position and pose, with quiet entry and departure', () => {
  for (const kind of KINDS) for (const side of [-1, 1]) {
    const d = new CameoDirector(() => .4); d.force(kind);
    let previous;
    for (let t = 0; t < d.duration; t += 1 / 120) {
      const c = {kind, side, t, duration: d.duration, greeted: -1};
      const place = cameoPlacement(c, frame), pose = cameoPose(idlePose(t), c);
      const values = flatten(pose); assert.ok(values.every(Number.isFinite));
      if(kind !== 'side') assert.ok(Math.abs(place.x) < frame.halfWidth);
      else assert.ok(Math.abs(place.x) <= frame.halfWidth + frame.height*.65 + 1e-9);
      if (previous) {
        assert.ok(Math.abs(place.y - previous.y) < .025, `${kind}: position jump`);
        assert.ok(values.every((v, i) => Math.abs(v - previous.values[i]) < .24), `${kind}: pose jump`);
      }
      if(previous) assert.ok(Math.abs(place.x-previous.x)<.04, `${kind}: horizontal jump`);
      previous = {x:place.x,y:place.y, values};
    }
    const start = cameoPlacement({kind, side, t:0, duration:d.duration}, frame);
    const end = cameoPlacement({kind, side, t:d.duration, duration:d.duration}, frame);
    assert.equal(start.visible, false); assert.equal(end.visible, false);
    assert.equal(start.y, end.y);
  }
});
test('tapping never changes the departure path or restarts an active greeting', () => {
  const d = new CameoDirector(() => .4); d.force('greet'); d.update(4);
  const before = cameoPlacement(d.update(0), frame);
  assert.equal(d.greet(), true); assert.equal(d.greet(), false);
  assert.deepEqual(cameoPlacement(d.update(0), frame), before);
  d.update(d.duration - d.elapsed - 1);
  const duration = d.duration; assert.equal(d.greet(), false); assert.equal(d.duration, duration);
});
test('pause and reduced motion freeze the director, and scenes do not repeat', () => {
  const d = new CameoDirector(() => .4); d.force('peek'); d.update(3);
  const before = d.update(0);
  d.update(100, {paused:true}); d.update(100, {reduced:true});
  assert.deepEqual(d.update(0), before);
  d.update(20); assert.equal(d.kind, ''); assert.ok(d.wait >= 55 && d.wait <= 90);
  d.update(d.wait + .01); assert.notEqual(d.kind, 'peek');
  assert.equal(d.force('climb'), false);
});
test('equal elapsed time has equal placement at 30 and 60 fps', () => {
  const sample = hz => { const d = new CameoDirector(() => .4); d.force('curious'); for(let i=0;i<hz*6;i++) d.update(1/hz); return cameoPlacement(d.update(0), frame); };
  const a=sample(30),b=sample(60); for(const k of ['x','y','turn']) assert.ok(Math.abs(a[k]-b[k]) < 1e-10);
});
test('a tap blends over an automatic wave without doubling shoulder rotation', () => {
  const d = new CameoDirector(() => .4); d.force('greet');
  for (let t=4; t<10; t+=.01) {
    const p = cameoPose(idlePose(t), {kind:'greet',side:1,t,duration:d.duration,greeted:t-4});
    assert.ok(p.arms[1].z < 2.1);
  }
});

test('peekaboo is fully hidden between looks and side entry starts beyond the frame', () => {
  const d=new CameoDirector(()=>.4); d.force('peekaboo');
  const hidden=cameoPlacement({kind:'peekaboo',t:4.4,duration:d.duration,side:1},frame);
  assert.equal(hidden.visible,false);
  const returned=cameoPlacement({kind:'peekaboo',t:8,duration:d.duration,side:1},frame);
  assert.ok(returned.visible);assert.ok(returned.y>hidden.y);
  d.force('side');
  for(const side of [-1,1]){
    const start=cameoPlacement({kind:'side',t:0,duration:d.duration,side},frame);
    const settled=cameoPlacement({kind:'side',t:4,duration:d.duration,side},frame);
    assert.ok(Math.abs(start.x)>frame.halfWidth);assert.ok(Math.abs(settled.x)<frame.halfWidth);
  }
});

test('guide follows a page target, alternates targets and settles before departure', () => {
  const d = new CameoDirector(() => .4); d.force('guide');
  assert.equal(d.update(0).target, 'banner');
  for (const side of [-1, 1]) {
    const c = {kind:'guide', side, t:6, duration:d.duration, greeted:-1};
    const p = cameoPose(idlePose(6), c, {x:-side*.5, y:-.8});
    assert.ok(p.lookY < -.4); assert.ok(p.lookX * side < 0);
    assert.ok(p.arms[side === 1 ? 0 : 1].present > .5);
    const end = cameoPose(idlePose(12), {...c,t:12}, {x:-side*.5,y:-.8});
    assert.equal(end.arms[side === 1 ? 0 : 1].present, 0);
  }
  d.force('guide'); assert.equal(d.update(0).target, 'menu');
  for (const random of [() => 0, () => .999999]) {
    const clock = new CameoDirector(random); clock.force('guide'); clock.update(20);
    assert.ok(clock.wait >= 55 && clock.wait <= 90);
    const wait = clock.wait; assert.equal(clock.update(wait - .01), null);
    assert.ok(clock.update(.02));
  }
});
