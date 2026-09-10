import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { createLogo } from './logo.js';
import { animateLogo } from './logo-motion.js';
import { createStageCamera, fitStageCamera } from './stage-camera.js';
import { createRobot, poseRobot } from './robot.js';
import { MotionController } from './motion.js';
import { CameoDirector, cameoPlacement, cameoPose } from './cameo.js';

const SIGN_WIDTH = 6, ROBOT_Z = .8;
export function createLogoStage(canvas, { theme = 'dark', reduced = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  const scene = new THREE.Scene();
  const camera = createStageCamera();
  const pmrem = new THREE.PMREMGenerator(renderer), room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, .04);
  scene.environment = environment.texture; scene.environmentIntensity = .45;
  room.dispose(); pmrem.dispose();

  // A spatial light wash, composed in frame coordinates at every aspect ratio.
  const wallMaterial = new THREE.ShaderMaterial({
    uniforms: { time: { value: 0 }, lightTheme: { value: 0 } },
    vertexShader: `varying vec2 uvStage; void main(){uvStage=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader: `varying vec2 uvStage; uniform float time; uniform float lightTheme;
      void main(){
        vec2 p=uvStage;
        float wash=exp(-length((p-vec2(.39+.025*sin(time*.13),.60))*vec2(1.3,1.8))*3.2);
        float edge=pow(abs(p.x-.5)*2.,2.)*.3+pow(abs(p.y-.5)*2.,3.)*.2;
        vec3 color=mix(vec3(.012,.075,.32),vec3(.025,.24,.68),wash);
        float rim=exp(-pow((p.y-.055)*95.,2.))*(.3+.7*sin(p.x*3.14159));
        color+=vec3(.025,.12,.24)*rim;
        color*=1.-edge;
        vec3 pale=mix(vec3(.55,.66,.77),vec3(.79,.85,.90),wash);
        gl_FragColor=vec4(mix(color,pale,lightTheme),1.);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  const wall = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), wallMaterial);
  wall.position.z = -.25; scene.add(wall);
  const shadowWall = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.ShadowMaterial({ color: '#020a17', opacity: .14 }));
  shadowWall.position.z = -.24; shadowWall.receiveShadow = true; scene.add(shadowWall);

  const logo = createLogo({ width: SIGN_WIDTH });
  logo.position.z = .2; logo.rotation.set(.018,-.055,0); scene.add(logo);
  const robot = createRobot(); robot.root.visible = false; scene.add(robot.root);
  robot.root.traverse(node => { if (node.isMesh) node.castShadow = true; });
  const span = new THREE.Box3().setFromObject(robot.root).getSize(new THREE.Vector3()).y;
  const controller = new MotionController(), director = new CameoDirector();
  const ambient = new THREE.HemisphereLight('#e1efff', '#183557', 1.2);
  const key = new THREE.DirectionalLight('#fff0d9', 2.5); key.position.set(-3, 4, 8);
  key.castShadow = true; key.shadow.mapSize.set(1024, 1024);
  key.shadow.radius = 4; key.shadow.bias = -.0005;
  Object.assign(key.shadow.camera, { left: -7, right: 7, top: 5, bottom: -5, near: 1, far: 25 });
  key.shadow.camera.updateProjectionMatrix();
  const rim = new THREE.DirectionalLight('#8ac9f3', 1.8); rim.position.set(5, 1, 3);
  const sweep = new THREE.PointLight('#fff0c7', 12, 24, 2); sweep.position.set(-4, 1, 4);
  scene.add(ambient, key, rim, sweep);
  let themeName;
  function setTheme(name) {
    themeName = name;
    wallMaterial.uniforms.lightTheme.value = name === 'light' ? 1 : 0;
    scene.environmentIntensity = name === 'light' ? .7 : .45;
    renderer.toneMappingExposure = name === 'light' ? .95 : 1.02;
  }
  setTheme(theme);
  const frame = { halfWidth: 0, halfHeight: 0, signHalfWidth: 3, signTop: 0, height: 0, scale: 1 };
  let width = 0, height = 0, clock = 0, onStage = null, gaze = null, emotion = 'idle';
  const settledGaze = [0, 0];
  let flourishAt = 0;
  let pageTargets = {};
  // Ціль, якої зараз немає на сторінці (карусель без банерів), замінює меню:
  // гід не має показувати рукою в порожнє місце.
  const aimFor = name => (pageTargets[name] ? name : 'menu');
  function resize(w, h) {
    if (!w || !h) return;
    width = w; height = h; renderer.setSize(w, h, false);
    Object.assign(frame, fitStageCamera(camera,w,h,SIGN_WIDTH,logo.userData.height));
    frame.height = Math.min(frame.halfHeight * 2 * .78, frame.halfWidth * .48); frame.scale = frame.height / span;
    frame.signTop = logo.userData.height / 2;
    robot.root.scale.setScalar(frame.scale);
    wall.scale.set(frame.halfWidth * 2, frame.halfHeight * 2, 1); shadowWall.scale.copy(wall.scale);
    logo.position.y = frame.halfHeight * .07;
  }
  function update(dt) {
    if (reduced) return false;
    clock += Math.max(0, Math.min(dt, .08));
    wallMaterial.uniforms.time.value = clock;
    // The sign is anchored. Only its individual details animate.
    sweep.position.x = Math.sin(clock * .24 - 1) * 5;
    sweep.intensity = 12 + 7 * Math.sin(clock * .24) ** 2;
    animateLogo(logo, clock, clock - flourishAt);
    const cameo = director.update(dt);
    onStage = cameo;
    robot.root.visible = !!cameo;
    if (cameo) {
      const place = cameoPlacement(cameo, frame);
      robot.root.visible = place.visible;
      robot.root.position.set(place.x, place.y, ROBOT_Z);
      robot.root.rotation.set(0, place.turn, place.roll ?? 0);
      const target = pageTargets[aimFor(cameo.target)];
      let attention;
      if (target) {
        const x = target.x - (place.x / frame.halfWidth + 1) * width / 2;
        const y = target.y - height * .8;
        const distance = Math.max(1, Math.hypot(x, y));
        attention = { x: x / distance, y: -y / distance };
      }
      const pose = cameoPose(controller.update(dt), cameo, attention);
      const follow = 1 - Math.exp(-dt * 3);
      for (const i of [0, 1]) settledGaze[i] += ((gaze?.[i] ?? 0) - settledGaze[i]) * follow;
      pose.lookX += settledGaze[0] * .18; pose.lookY += settledGaze[1] * .12;
      if (['happy', 'success', 'achievement'].includes(emotion)) pose.smile = Math.max(pose.smile, .5);
      poseRobot(robot, pose);
    }
    return true;
  }
  const box = new THREE.Box3(), point = new THREE.Vector3();
  function characterBounds() {
    if (!onStage || !robot.root.visible || reduced) return null;
    robot.root.updateMatrixWorld(true); box.setFromObject(robot.head);
    let left = width, right = 0, top = height, bottom = 0;
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
      point.set(x, y, z).project(camera);
      const px = (point.x + 1) * width / 2, py = (1 - point.y) * height / 2;
      left = Math.min(left, px); right = Math.max(right, px); top = Math.min(top, py); bottom = Math.max(bottom, py);
    }
    left = Math.max(0, left); right = Math.min(width, right); top = Math.max(0, top); bottom = Math.min(height, bottom);
    return right > left && bottom - top > 20 ? { x: left, y: top, width: right - left, height: bottom - top } : null;
  }
  function touch(x, y) {
    const b = characterBounds(), r = canvas.getBoundingClientRect();
    if (!b || x-r.left < b.x || x-r.left > b.x+b.width || y-r.top < b.y || y-r.top > b.y+b.height) return false;
    return director.greet();
  }
  function dispose() {
    const geometries = new Set(), materials = new Set();
    scene.traverse(o => { if (o.geometry) geometries.add(o.geometry); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => materials.add(m)); });
    geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); environment.dispose(); renderer.dispose();
  }
  return { renderer, scene, camera, logo, robot, director, frame, resize, update, characterBounds, touch, dispose, setTheme,
    setPageTargets(targets) { pageTargets = targets; },
    get attentionTarget() { return !reduced && onStage?.kind === 'guide' && onStage.greeted < 0 && onStage.t > 4.4 && onStage.t < 8.3 ? aimFor(onStage.target) : ''; },
    render: () => renderer.render(scene, camera), sweepNow: () => { if (clock - flourishAt > 8) flourishAt = clock; },
    setMascot(state, nextGaze) { emotion = state; gaze = Array.isArray(nextGaze) && nextGaze.length === 2 && nextGaze.every(Number.isFinite) ? nextGaze.map(v => THREE.MathUtils.clamp(v, -1, 1)) : null; },
    set reduced(value) { reduced = value; if (value) { robot.root.visible = false; onStage = null; director.reset(); } },
    get reduced() { return reduced; },
  };
}
