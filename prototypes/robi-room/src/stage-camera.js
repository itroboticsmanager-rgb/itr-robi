import * as THREE from 'three';

// Orthographic projection keeps the mascot's proportions identical at either
// edge. A wide perspective frustum distorted faces near the sides of the strip.
export function createStageCamera() {
  const camera = new THREE.OrthographicCamera(-5,5,2,-2,.1,80);
  camera.position.z = 12;
  camera.updateMatrixWorld();
  return camera;
}
export function fitStageCamera(camera,width,height,signWidth,signHeight) {
  const aspect=width/height;
  const halfHeight=Math.max(signWidth/.70/2/aspect,signHeight/.68/2);
  const halfWidth=halfHeight*aspect;
  camera.left=-halfWidth;camera.right=halfWidth;
  camera.top=halfHeight;camera.bottom=-halfHeight;
  camera.updateProjectionMatrix();camera.updateMatrixWorld();
  return {halfWidth,halfHeight};
}
