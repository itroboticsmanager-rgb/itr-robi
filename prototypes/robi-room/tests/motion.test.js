import test from 'node:test';
import assert from 'node:assert/strict';
import { MotionController, actionPose, idlePose, durations } from '../src/motion.js';
import { createRobot, poseRobot } from '../src/robot.js';
import * as THREE from 'three';
import { CarryMotion } from '../src/carry.js';
import { RoomWalker } from '../src/walk.js';

function values(pose) { return Object.values(pose).flatMap(v => typeof v === 'number' ? [v] : values(v)); }
function distance(a, b) { return Math.max(...values(a).map((v, i) => Math.abs(v - values(b)[i]))); }

test('every gesture begins and ends at its underlying idle pose', () => {
  const idle = idlePose(0);
  for (const [name, duration] of Object.entries(durations)) {
    assert.ok(distance(actionPose(name, 0, idle), idle) < 1e-10, `${name} start`);
    assert.ok(distance(actionPose(name, duration, idle), idle) < 1e-10, `${name} end`);
  }
});
test('interrupting a gesture preserves the outgoing pose on the first frame', () => {
  const c = new MotionController(); c.play('dance');
  for (let i = 0; i < 40; i++) c.update(1 / 30);
  const before = structuredClone(c.pose);
  c.play('highfive');
  assert.ok(distance(c.update(0), before) < 1e-10);
  assert.ok(distance(c.update(1 / 60), before) < .025);
});
test('greeting moves torso, head and both arms while keeping feet planted', () => {
  const idle = idlePose(0), p = actionPose('greet', 1.4, idle);
  assert.ok(Math.abs(p.shift) > .08);
  assert.ok(Math.abs(p.headZ) > .08);
  assert.ok(Math.abs(p.arms[0].ex - idle.arms[0].ex) > .15);
  assert.ok(Math.abs(p.arms[1].z - idle.arms[1].z) > 2);
  assert.deepEqual(p.feet, [0, 0]);
});
test('all sampled gestures produce finite transforms and planted shoe positions', () => {
  const robot = createRobot();
  for (const [name, duration] of Object.entries(durations)) {
    for (let t = 0; t <= duration; t += 1 / 30) {
      const p = actionPose(name, t, idlePose(t));
      assert.ok(values(p).every(Number.isFinite));
      poseRobot(robot, p);
      robot.root.updateMatrixWorld(true);
      robot.root.traverse(node => assert.ok(node.matrixWorld.elements.every(Number.isFinite), `${name}:${node.name}`));
      // The foot pivots on the ankle, so a planted shoe sits at the resting ankle.
      if (name !== 'dance') for (const leg of robot.legs) {
        assert.equal(leg.shoe.position.y, .34);
        assert.equal(leg.shoe.position.x, leg.side * .36);
      }
    }
  }
});
test('reduced motion suppresses gesture movement and blinking', () => {
  const c = new MotionController(); c.reduced = true; c.play('dance');
  const a = c.update(1 / 30);
  for (let i = 0; i < 80; i++) c.update(1 / 30);
  assert.equal(c.action, null);
  assert.equal(distance(a, c.pose), 0);
});
test('equal elapsed times produce equal poses across 30 and 60 Hz updates', () => {
  const a = new MotionController(), b = new MotionController(); a.play('greet'); b.play('greet');
  for (let i = 0; i < 60; i++) a.update(1 / 30, { x: .4, y: .1 });
  for (let i = 0; i < 120; i++) b.update(1 / 60, { x: .4, y: .1 });
  assert.ok(distance(a.pose, b.pose) < 1e-10);
});

test('face rests neutral and emotional reactions have distinct, temporary shapes', () => {
  const base = idlePose(0);
  assert.equal(base.smile, 0);
  assert.ok(actionPose('greet', 1.4, base).smile > .7);
  assert.ok(actionPose('highfive', 1.4, base).surprise > .8);
  assert.ok(idlePose(8).curiosity > .5);
  const c = new MotionController(); c.play('greet');
  for (let i = 0; i < 150; i++) c.update(1 / 30);
  assert.equal(c.pose.smile, 0); assert.equal(c.pose.surprise, 0);
});
test('display is planar, skin weights normalized, and leg faces point outward', () => {
  const r = createRobot(); poseRobot(r, idlePose(0));
  const screen = r.screen.geometry.attributes.position;
  for (let i = 0; i < screen.count; i++) assert.equal(screen.getZ(i), 0);
  r.root.traverse(o => {
    if (!o.isSkinnedMesh) return;
    const weights = o.geometry.attributes.skinWeight;
    for (let i = 0; i < weights.count; i++) assert.ok(Math.abs(weights.getX(i) + weights.getY(i) + weights.getZ(i) + weights.getW(i) - 1) < 1e-6);
  });
  const g = r.legs[0].surface.geometry, p = g.attributes.position, normal = g.attributes.normal;
  for (let i = 0; i < g.index.count; i += 3) {
    const a = g.index.getX(i), b = g.index.getX(i + 1), c = g.index.getX(i + 2);
    const av = new THREE.Vector3().fromBufferAttribute(p, a), bv = new THREE.Vector3().fromBufferAttribute(p, b), cv = new THREE.Vector3().fromBufferAttribute(p, c);
    const n = new THREE.Vector3().fromBufferAttribute(normal, a);
    assert.ok(bv.sub(av).cross(cv.sub(av)).dot(n) > 0);
  }
});

test('antenna rests straight and shorts follow changing thigh directions', () => {
  const r = createRobot();
  for (const time of [0, 2, 7, 19]) assert.equal(idlePose(time).antenna, 0);
  poseRobot(r, idlePose(0));
  const initial = r.thighs.map(b => b.quaternion.clone());
  poseRobot(r, actionPose('dance', 1.4, idlePose(0)));
  assert.ok(r.shorts.isSkinnedMesh);
  r.thighs.forEach(b => assert.ok(r.shorts.skeleton.bones.includes(b)));
  assert.ok(r.thighs.some((b, i) => b.quaternion.angleTo(initial[i]) > .05));
});

test('resting shorts retain their length and a level hem through an idle cycle', () => {
  const r = createRobot(), position = r.shorts.geometry.attributes.position;
  const v = new THREE.Vector3();
  const hems = [[], []];
  for (let i = 0; i < position.count; i++) {
    // The leg of the shorts ends above the knee, so the shin never leaves the cuff.
    if (position.getY(i) < -.515) hems[position.getX(i) < 0 ? 0 : 1].push(i);
  }
  for (const hem of hems) assert.ok(hem.length > 10);
  for (let time = 0; time < 18; time += .5) {
    poseRobot(r, idlePose(time)); r.root.updateMatrixWorld(true); r.shorts.skeleton.update();
    for (const hem of hems) {
      const heights = hem.map(i => {
        v.fromBufferAttribute(position, i); r.shorts.applyBoneTransform(i, v); return v.y;
      });
      assert.ok(Math.max(...heights) < -.45, `hem hiked up at ${time}`);
      assert.ok(Math.max(...heights) - Math.min(...heights) < .10, `hem tilted at ${time}`);
    }
  }
});

test('greeting and high-five show an upright open palm toward the viewer', () => {
  const r = createRobot(), orientation = new THREE.Quaternion();
  r.root.rotation.y = -.10;
  for (const gesture of ['greet', 'highfive']) {
    for (const x of [-1, 0, 1]) {
      poseRobot(r, actionPose(gesture, 1.4, idlePose(0, { x, y: .3 })));
      r.root.updateMatrixWorld(true);
      r.arms[1].hand.group.getWorldQuaternion(orientation);
      const palmNormal = new THREE.Vector3(0, 0, 1).applyQuaternion(orientation);
      const fingerDirection = new THREE.Vector3(0, -1, 0).applyQuaternion(orientation);
      assert.ok(palmNormal.z > .92, `${gesture}: palm turned edge-on`);
      assert.ok(fingerDirection.y > .85, `${gesture}: fingers not upright`);
    }
  }
});

test('carrying stays bounded under fast direction changes and fully returns home', () => {
  const c = new CarryMotion(), base = idlePose(0), r = createRobot(); c.grab(base);
  for (let i = 0; i < 240; i++) {
    c.update(1 / 30, i % 20 < 10 ? 90 : -90);
    const p = c.pose(base); poseRobot(r, p); r.root.updateMatrixWorld(true);
    assert.ok(values(p).every(Number.isFinite));
    assert.ok(Math.abs(c.angle) <= .42);
  }
  assert.equal(c.pose(base).suspend, 1);
  c.offset = { x: 2.4, y: 1.2 }; c.release();
  for (let i = 0; i < 30; i++) c.update(1 / 30);
  assert.equal(c.mode, 'idle'); assert.deepEqual(c.offset, { x: 0, y: 0 });
  assert.equal(distance(c.pose(base), base), 0);
});

test('releasing during pickup preserves the visible pose and reduced motion suppresses sway', () => {
  const c = new CarryMotion(), base = idlePose(0); c.grab(actionPose('greet', 1.4, base));
  c.update(.08, 10); const before = c.pose(base); c.release();
  assert.ok(distance(c.pose(base), before) < 1e-12);
  c.reset(); c.grab(base);
  for (let i = 0; i < 60; i++) c.update(1 / 30, 50, true);
  assert.equal(c.angle, 0); assert.equal(c.velocity, 0);
  const still = c.pose(base, true);
  for (let i = 0; i < 60; i++) c.update(1 / 30, -50, true);
  assert.equal(distance(still, c.pose(base, true)), 0);
});

test('suspended shoes follow the body instead of staying planted on the floor', () => {
  const r = createRobot(), c = new CarryMotion(), base = idlePose(0); c.grab(base);
  for (let i = 0; i < 20; i++) c.update(1 / 30);
  const p = c.pose(base); poseRobot(r, p);
  const positions = r.legs.map(leg => leg.shoe.position.clone());
  p.shift += .4; p.bob += .3; poseRobot(r, p);
  r.legs.forEach((leg, i) => {
    assert.ok(Math.abs(leg.shoe.position.x - positions[i].x - .4) < 1e-6);
    assert.ok(Math.abs(leg.shoe.position.y - positions[i].y - .3) < 1e-6);
  });
});

test('landing retains the placed position before starting a bounded autonomous walk', () => {
  const w = new RoomWalker(); w.setBounds(-3, 2); w.land(-2.4);
  for (let i = 0; i < 30; i++) { w.update(1 / 30); w.pose(idlePose(i / 30)); }
  assert.equal(w.x, -2.4); assert.equal(w.mode, 'landing');
  let walking = false, turned = false;
  for (let i = 0; i < 2400; i++) {
    w.update(1 / 30); const p = w.pose(idlePose(i / 30));
    assert.ok(values(p).every(Number.isFinite));
    assert.ok(w.x >= -3 && w.x <= 2);
    walking ||= w.mode === 'walking'; turned ||= w.trip >= 2;
  }
  assert.ok(walking); assert.ok(turned);
});

test('supporting shoe stays planted in world space as the walking body advances', () => {
  const w = new RoomWalker(), r = createRobot(); w.setBounds(-3, 3); w.land(-1);
  for (let i = 0; i < 200 && w.mode !== 'walking'; i++) { w.update(1 / 60); w.pose(idlePose(0)); }
  assert.equal(w.mode, 'walking');
  const planted = 1 - w.swing;
  function shoePosition() {
    r.root.position.x = w.x; r.root.rotation.y = w.yaw;
    poseRobot(r, w.pose(idlePose(0))); r.root.updateMatrixWorld(true);
    return r.legs[planted].shoe.getWorldPosition(new THREE.Vector3());
  }
  const start = shoePosition(), startX = w.x;
  for (let i = 0; i < 20; i++) {
    w.update(1 / 60); const current = shoePosition();
    assert.ok(current.distanceTo(start) < 1e-6, 'support foot slid across the floor');
  }
  assert.ok(Math.abs(w.x - startX) > .05);
  assert.ok(r.legs[w.swing].shoe.position.y > r.legs[1 - w.swing].shoe.position.y + .04, 'the swing foot should be clear of the floor');
  // The trip opens on an eased half stride. Once that is behind it the body holds
  // one speed, instead of stopping dead at every footfall.
  while (w.mode === 'walking' && w.firstStep) { w.update(1 / 60); w.pose(idlePose(0)); }
  const cruiseX = w.x;
  for (let i = 0; i < 24; i++) { w.update(1 / 60); w.pose(idlePose(0)); }
  assert.equal(w.mode, 'walking');
  assert.ok(Math.abs(w.x - cruiseX) > .2, 'body should keep its walking speed across a step');
});

test('grabbing, gestures and reduced motion stop walking without changing its floor position', () => {
  for (const reduced of [false, true]) {
    const w = new RoomWalker(); w.setBounds(-2, 2); w.land(-1);
    for (let i = 0; i < 140; i++) { w.update(1 / 60); w.pose(idlePose(0)); }
    assert.equal(w.mode, 'walking'); const x = w.x;
    for (let i = 0; i < 240; i++) { w.update(1 / 60, !reduced, reduced); w.pose(idlePose(0)); }
    assert.equal(w.x, x); assert.equal(w.mode, 'resting');
    assert.ok(Math.abs(w.yaw + .10) < 1e-12);
  }
});

test('the leg never comes out through the cuff of the shorts', () => {
  const r = createRobot(), position = r.shorts.geometry.attributes.position;
  const v = new THREE.Vector3(), a = new THREE.Vector3(), b = new THREE.Vector3(), ab = new THREE.Vector3(), near = new THREE.Vector3();
  const smooth = (lo, hi, x) => THREE.MathUtils.smoothstep(x, lo, hi);
  // The rim of each leg opening, found with the field the shorts were cut with.
  const rim = [];
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i), y = position.getY(i), z = position.getZ(i);
    if (y > -.42) continue;
    const s = Math.sign(x) || 1;
    const edge = (Math.hypot((x - s * .30) / .172, (z - .085 * (1 - smooth(-.53, -.22, y))) / .200) - 1) * .172;
    if (Math.abs(edge) < .005) rim.push({ i, side: s < 0 ? 0 : 1 });
  }
  assert.ok(rim.length > 200);
  function clearance() {
    r.root.updateMatrixWorld(true); r.shorts.skeleton.update();
    const rings = [0, 1].map(leg => {
      const p = r.legs[leg].surface.geometry.attributes.position;
      return Array.from({ length: 25 }, (_, j) => {
        const c = new THREE.Vector3();
        for (let k = 0; k < 16; k++) c.add(new THREE.Vector3(p.getX(j * 17 + k), p.getY(j * 17 + k), p.getZ(j * 17 + k)));
        return c.multiplyScalar(1 / 16);
      });
    });
    let worst = Infinity;
    for (const { i, side } of rim) {
      v.fromBufferAttribute(position, i); r.shorts.applyBoneTransform(i, v); v.applyMatrix4(r.torso.matrix);
      for (let j = 0; j < 24; j++) {
        a.copy(rings[side][j]); b.copy(rings[side][j + 1]); ab.subVectors(b, a);
        const t = THREE.MathUtils.clamp(v.clone().sub(a).dot(ab) / ab.lengthSq(), 0, 1);
        near.copy(a).addScaledVector(ab, t);
        worst = Math.min(worst, v.distanceTo(near) - (.147 - .045 * (j + t) / 24));
      }
    }
    return worst;
  }
  poseRobot(r, idlePose(0));
  assert.ok(clearance() > .005, 'the cuff already touches the leg at rest');
  const w = new RoomWalker(); w.setBounds(-1.5, 1.5); w.land(-1.2);
  for (let i = 0, time = 0; i < 300; i++, time += 1 / 30) {
    w.update(1 / 30); const p = w.pose(idlePose(time));
    if (w.mode !== 'walking') continue;
    poseRobot(r, p);
    assert.ok(clearance() > .005, `the leg came through the cuff while walking, frame ${i}`);
  }
  for (const name of ['greet', 'highfive', 'dance', 'peek']) {
    for (let i = 0; i < 170; i += 4) {
      poseRobot(r, actionPose(name, i / 30, idlePose(i / 30)));
      assert.ok(clearance() > .005, `the leg came through the cuff during ${name} at ${(i / 30).toFixed(2)}s`);
    }
  }
});
