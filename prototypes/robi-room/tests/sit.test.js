import test from 'node:test';
import assert from 'node:assert/strict';
import { SitDirector, AWAY_S, GREET_COOLDOWN_S, WAVE_S, FLOURISH_MAX_S } from '../src/sit.js';

const run = (d, seconds, opts) => { for (let t = 0; t < seconds; t += .05) d.update(.05, opts); };
const near = { present: true, gaze: [.3, 0] };

test('greets a person once when they approach', () => {
  const d = new SitDirector(() => .5);
  d.update(.05, near);
  assert.equal(d.kind, 'wave');
  run(d, WAVE_S + .2, near);
  assert.equal(d.performing, false);
  run(d, 60, near);
  assert.equal(d.performing, false, 'stays calm while the same person is there');
});

test('a returning person is greeted again only after the cooldown', () => {
  const d = new SitDirector(() => .5);
  run(d, WAVE_S + .2, near);
  run(d, AWAY_S + 1, {});
  d.update(.05, near);
  assert.equal(d.performing, false, 'cooldown not over yet');
  run(d, GREET_COOLDOWN_S, {});
  d.update(.05, near);
  assert.equal(d.kind, 'wave');
});

test('no flourishes while someone is present, rare ones otherwise', () => {
  const d = new SitDirector(() => 0);
  run(d, WAVE_S + .2, near);
  run(d, FLOURISH_MAX_S + 10, near);
  assert.equal(d.performing, false);
  const idle = new SitDirector(() => 0);
  let seen = '';
  for (let t = 0; t < FLOURISH_MAX_S + 10 && !seen; t += .05) { idle.update(.05); seen = idle.kind; }
  assert.ok(['antenna', 'look'].includes(seen));
});

test('touch greets, reset stops the action', () => {
  const d = new SitDirector(() => .5);
  assert.equal(d.greet(), true);
  assert.equal(d.greet(), false, 'no restart mid-wave');
  run(d, 1);
  assert.ok(d.pose().arms[1].raise > 1);
  d.reset();
  assert.equal(d.performing, false);
  assert.equal(d.pose().arms[1].raise, 0);
});

test('idle pose stays small and calm', () => {
  const d = new SitDirector(() => .5);
  for (let t = 0; t < 30; t += .05) {
    const p = d.update(.05);
    if (d.performing) continue;
    assert.ok(Math.abs(p.headYaw) < .2 && Math.abs(p.legs[0].swing) <= .1 && p.arms[0].raise === 0);
  }
});
