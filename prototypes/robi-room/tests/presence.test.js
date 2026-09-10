import test from 'node:test';
import assert from 'node:assert/strict';
import { WindowPresence, windowPose } from '../src/presence.js';
import { idlePose } from '../src/motion.js';

function random(seed = 32) { return () => { seed = (1664525 * seed + 1013904223) >>> 0; return seed / 4294967296; }; }
test('appearances vary, never repeat consecutively, and leave genuine quiet intervals', () => {
  const p = new WindowPresence(random());
  const seen = [], pauses = []; let quiet = 0, prior = '';
  for (let i = 0; i < 30 * 600; i++) {
    const pose = p.update(1 / 30);
    assert.ok(pose.reveal >= 0 && pose.reveal <= 1);
    if (!pose.kind) quiet += 1 / 30;
    if (pose.kind && !prior) { seen.push(pose.kind); pauses.push(quiet); quiet = 0; }
    prior = pose.kind;
    const result = windowPose(idlePose(i / 30), pose);
    assert.ok(Number.isFinite(result.headZ));
  }
  assert.ok(new Set(seen).size >= 4);
  assert.ok(seen.every((k, i) => !i || k !== seen[i - 1]));
  assert.ok(pauses.slice(1).every(s => s >= 12.9 && s <= 40.1));
});
test('opening workshop and hiding the scene freeze the appearance timeline', () => {
  const p = new WindowPresence(random()); p.update(5);
  const before = p.sample();
  for (let i = 0; i < 1000; i++) p.update(.1, { paused: true });
  assert.deepEqual(p.sample(), before);
});
test('reduced motion keeps a quiet visible character without hopping or waving', () => {
  const p = new WindowPresence(random());
  const a = p.update(1, { reduced: true });
  assert.deepEqual(p.update(60, { reduced: true }), a);
  assert.equal(a.kind, 'calm'); assert.equal(a.jump, 0); assert.ok(a.reveal > .5);
});
test('an appearance settles out without snapping and poses are distinct', () => {
  const p = new WindowPresence(random()); p.update(5);
  p.elapsed = p.duration - .00001; assert.ok(p.sample().reveal < .00001);
  const wave = windowPose(idlePose(0), { kind: 'wave', progress: 2 });
  const curious = windowPose(idlePose(0), { kind: 'curious', progress: 2 });
  assert.ok(wave.arms[1].z > curious.arms[1].z + 1);
  assert.ok(curious.curiosity > wave.curiosity);
});
