import test from 'node:test';
import assert from 'node:assert/strict';
import * as THREE from 'three';
import {createStageCamera,fitStageCamera} from '../src/stage-camera.js';
import {createRobot,poseRobot} from '../src/robot.js';
import {idlePose} from '../src/motion.js';

test('mascot face keeps its proportions at the center and both edges at every viewport', () => {
  const robot=createRobot();robot.root.scale.setScalar(.4);poseRobot(robot,idlePose(0));
  const camera=createStageCamera();
  for(const [width,height] of [[1920,350],[1280,220],[390,190]]) {
    const f=fitStageCamera(camera,width,height,6,1.16);
    let expected;
    for(const x of [-f.halfWidth*.85,0,f.halfWidth*.85]) {
      robot.root.position.set(x,-f.halfHeight,.8);robot.root.updateMatrixWorld(true);
      const box=new THREE.Box3().setFromObject(robot.head);
      const a=box.min.clone().project(camera), b=box.max.clone().project(camera);
      const ratio=(b.x-a.x)*width/((b.y-a.y)*height);
      expected ??= ratio;
      assert.ok(Math.abs(ratio-expected)<1e-10);
      assert.ok(Math.abs(ratio-(box.max.x-box.min.x)/(box.max.y-box.min.y))<1e-10);
    }
  }
});
