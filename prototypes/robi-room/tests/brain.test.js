import test from 'node:test';
import assert from 'node:assert/strict';
import { WorkshopBrain, readWorld, stations } from '../src/brain.js';
import { RoomWalker } from '../src/walk.js';
import { idlePose } from '../src/motion.js';

function tick(brain, seconds, options = {}) {
  for (let i = 0; i < Math.round(seconds * 60); i++) brain.update(1 / 60, options);
}
test('autonomous building completes three persistent steps', () => {
  const brain = new WorkshopBrain(); tick(brain, 20);
  assert.equal(brain.world.blocks, 3);
  assert.equal(brain.revision, 3);
});
test('ball interrupts after one block and returns to the unfinished build', () => {
  const brain = new WorkshopBrain(); brain.interact('blocks'); tick(brain, 4.7);
  assert.equal(brain.world.blocks, 1);
  brain.interact('ball'); assert.equal(brain.resume, 'build');
  tick(brain, 6.7);
  assert.equal(brain.task, 'build'); assert.equal(brain.world.blocks, 1);
  assert.match(brain.drain().join(' '), /Повернуся/);
  tick(brain, 9); assert.equal(brain.world.blocks, 3);
});
test('lamp toggles immediately and repeated events preserve build memory', () => {
  const brain = new WorkshopBrain(); brain.interact('blocks'); tick(brain, 4.7);
  for (let i = 0; i < 8; i++) brain.interact('lamp');
  assert.equal(brain.world.lamp, true); assert.equal(brain.resume, 'build');
  assert.equal(brain.world.blocks, 1);
  tick(brain, 14); assert.equal(brain.world.blocks, 3);
});
test('repeated ball taps do not restart its phase', () => {
  const brain = new WorkshopBrain(); brain.interact('ball'); tick(brain, 2);
  const before = brain.elapsed;
  for (let i = 0; i < 20; i++) brain.interact('ball');
  assert.equal(brain.elapsed, before); assert.equal(brain.events.length, 1);
});
test('a passed ball waits for the visitor rather than returning by itself', () => {
  const brain = new WorkshopBrain({ blocks: 3 }); brain.interact('ball'); tick(brain, 8);
  assert.equal(brain.ballAtVisitor, true); tick(brain, 45);
  assert.notEqual(brain.task, 'ball'); assert.equal(brain.ballAtVisitor, true);
  brain.interact('ball'); assert.equal(brain.ballReturning, true);
  tick(brain, 1); assert.equal(brain.ballReturning, false);
});
test('external pause and reduced motion freeze intentions without losing progress', () => {
  const brain = new WorkshopBrain(); brain.interact('blocks'); tick(brain, 4.7);
  const before = JSON.stringify(brain);
  tick(brain, 90, { paused: true }); tick(brain, 90, { reduced: true });
  assert.equal(JSON.stringify(brain), before);
  tick(brain, 10); assert.equal(brain.world.blocks, 3);
});
test('reduced motion actions remain useful and never require locomotion', () => {
  const brain = new WorkshopBrain(); brain.interact('blocks', true);
  brain.interact('lamp', true); brain.interact('ball', true);
  assert.equal(brain.world.blocks, 1); assert.equal(brain.world.lamp, false);
  assert.equal(brain.phase, 'rest'); assert.equal(brain.events.length, 3);
});
test('approach must actually arrive before the object can change', () => {
  const brain = new WorkshopBrain(); brain.interact('blocks'); tick(brain, 60, { arrived: false });
  assert.equal(brain.phase, 'approach'); assert.equal(brain.world.blocks, 0);
  tick(brain, 4); assert.equal(brain.world.blocks, 1);
});
test('storage accepts only a bounded world and works without localStorage', () => {
  assert.deepEqual(readWorld(undefined), { blocks: 0, lamp: true });
  assert.deepEqual(readWorld({ getItem: () => '{broken' }), { blocks: 0, lamp: true });
  assert.deepEqual(readWorld({ getItem: () => '{"blocks":999,"lamp":"no"}' }), { blocks: 3, lamp: true });
  assert.deepEqual(readWorld({ getItem: () => '{"blocks":2,"lamp":false}' }), { blocks: 2, lamp: false });
});
test('directed walker reaches short and long stations and then stays there', () => {
  const walker = new RoomWalker(); walker.autonomous = false; walker.setBounds(-.65, 3.4);
  for (const target of [stations.build, stations.ball, .57, .61, stations.build]) {
    let arrived = false;
    for (let i = 0; i < 1500 && !arrived; i++) {
      arrived = walker.goTo(target); walker.update(1 / 60); walker.pose(idlePose(i / 60));
      assert.ok(walker.x >= -.65 && walker.x <= 3.4);
    }
    assert.ok(arrived, `did not reach ${target}`); assert.ok(Math.abs(walker.x - target) < .041);
    const atRest = walker.x;
    for (let i = 0; i < 600; i++) walker.update(1 / 60);
    assert.equal(walker.x, atRest);
  }
});
test('brain plus directed walking returns from the ball and finishes building', () => {
  const brain = new WorkshopBrain(), walker = new RoomWalker();
  walker.autonomous = false; walker.setBounds(-.65, 3.4);
  let interrupted = false, returned = false;
  for (let i = 0; i < 60 * 65; i++) {
    if (!interrupted && brain.world.blocks === 1) { brain.interact('ball'); walker.interrupt(); interrupted = true; }
    if (interrupted && brain.task === 'build') returned = true;
    let arrived = Math.abs(walker.x - brain.target) < .06 && !walker.moving;
    if (brain.phase === 'approach') arrived = walker.goTo(brain.target);
    walker.update(1 / 60); walker.pose(idlePose(i / 60));
    brain.update(1 / 60, { arrived });
  }
  assert.ok(interrupted && returned); assert.equal(brain.world.blocks, 3);
});
