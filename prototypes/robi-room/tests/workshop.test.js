import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import { createRobot, poseRobot } from '../src/robot.js';
import { idlePose } from '../src/motion.js';
import { reachHand } from '../src/workshop.js';

test('authored construction paths remain reachable without stretching arm bones', () => {
  const robot = createRobot(), actual = new THREE.Vector3();
  robot.root.position.x = -.15; robot.root.rotation.y = -.1;
  let worst = 0;
  for (let i = 0; i < 3; i++) for (let step = 0; step <= 20; step++) {
    const progress = step / 20;
    poseRobot(robot, idlePose(0));
    const start = new THREE.Vector3(-1.65, 1.87, -.65 + i * .36);
    const end = new THREE.Vector3(-1.55, 1.87 + i * .33, .43);
    const target = start.lerp(end, progress); target.y += Math.sin(progress * Math.PI) * .15; target.x += .18;
    reachHand(robot, 0, target, 1);
    robot.arms[0].hand.group.getWorldPosition(actual);
    worst = Math.max(worst, actual.distanceTo(target));
    assert.ok(actual.toArray().every(Number.isFinite));
    assert.equal(robot.arms[0].elbow.position.y, -.53);
    assert.equal(robot.arms[0].hand.group.position.y, -.51);
  }
  assert.ok(worst < .025, `maximum contact error ${worst}`);
});
