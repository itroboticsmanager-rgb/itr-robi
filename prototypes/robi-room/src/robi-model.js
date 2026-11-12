import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { createScreen, updateScreen } from './screen.js';
import url from './assets/robi.glb?url';

// Робі з Tripo (D-066): одна скінована сітка, 19 кісток, ріст 1 (від підлоги
// до кінчика антени). Поза — з `sit.js`, тут лише перенесення на кістки.
// Модель дивиться в +Z, .L — це +X (ліва рука самого Робі, праворуч від нас).

// Екран обличчя: темна панель голови. Поверх неї — той самий живий екран, що
// й у старого Робі; трохи перед панеллю (z .108) і за ободом (z .116).
const SCREEN = { width: .258, height: .175, x: 0, y: .70, z: .112, radius: .035 };
/** Висота сидячого Робі від сидіння (кульшового шарніра) до кінчика антени. */
export const SEAT_Y = .30;
const ARM_TUCK = .32;

const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 1, 0), Z = new THREE.Vector3(0, 0, 1);
const BONES = ['root', 'spine', 'neck', 'head', 'antenna', 'shoulderL', 'upper_armL', 'forearmL', 'handL',
  'shoulderR', 'upper_armR', 'forearmR', 'handR', 'thighL', 'shinL', 'footL', 'thighR', 'shinR', 'footR'];

function roundedRect(w, h, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const geo = new THREE.ShapeGeometry(s, 8), pos = geo.attributes.position, uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / w + .5, pos.getY(i) / h + .5);
  return geo;
}

export function loadRobiModel() {
  return new GLTFLoader().loadAsync(url).then(gltf => buildRobi(gltf.scene));
}

function buildRobi(scene) {
  const root = new THREE.Group();
  root.add(scene);
  root.updateMatrixWorld(true);
  const bones = {};
  scene.traverse(node => {
    if (node.isMesh) { node.castShadow = true; node.frustumCulled = false; }
    if (node.isBone && BONES.includes(node.name)) bones[node.name] = node;
  });
  const missing = BONES.filter(n => !bones[n]);
  if (missing.length) throw new Error(`robi.glb: немає кісток ${missing.join(', ')}`);

  // Спокій кожної кістки: локальний і світовий (у системі моделі) кватерніон.
  const inverseRoot = root.getWorldQuaternion(new THREE.Quaternion()).invert();
  const rest = {};
  for (const [name, bone] of Object.entries(bones)) {
    rest[name] = { local: bone.quaternion.clone(), worldInv: inverseRoot.clone().multiply(bone.getWorldQuaternion(new THREE.Quaternion())).invert(), pos: bone.position.clone() };
  }

  const material = createScreen();
  // Екран — фірмовий світло-блакитний, як у маскота й старого Робі.
  const face = new THREE.Mesh(roundedRect(SCREEN.width, SCREEN.height, SCREEN.radius), material);
  face.position.set(SCREEN.x, SCREEN.y, SCREEN.z);
  root.add(face); root.updateMatrixWorld(true);
  bones.head.attach(face);

  // Обертання навколо осі моделі в системі спокою кістки: так поворот
  // батька несе дитину, а кути однакові для лівої й правої сторони.
  const tmp = new THREE.Quaternion(), axis = new THREE.Vector3();
  const pending = {};
  function turn(name, worldAxis, angle) {
    if (!angle) return;
    axis.copy(worldAxis).applyQuaternion(rest[name].worldInv).normalize();
    tmp.setFromAxisAngle(axis, angle);
    (pending[name] ??= new THREE.Quaternion()).multiply(tmp);
  }

  function applyPose(p) {
    for (const name of BONES) pending[name] = new THREE.Quaternion();
    // Сидить (sit 1): стегна вперед, гомілки звисають з краю; стоїть (sit 0): ноги прямі.
    const sit = p.sit ?? 1;
    turn('spine', X, -.07 * sit + .025 * p.breathe + (p.lean ?? 0));
    turn('neck', X, -.012 * p.breathe);
    for (const [i, side] of [[0, 'L'], [1, 'R']]) {
      const sign = side === 'L' ? 1 : -1, leg = p.legs[i], arm = p.arms[i];
      turn('thigh' + side, X, -1.48 * sit + (leg.thigh ?? 0));
      turn('thigh' + side, Z, sign * .05 * sit);
      turn('shin' + side, X, 1.48 * sit + leg.swing);
      turn('foot' + side, X, -.15 * sit);
      // Плече бере третину підйому, рука — решту.
      // A-поза моделі тримає руки розведеними; сидячи вони ближче до тіла.
      turn('shoulder' + side, Z, sign * arm.raise * .3);
      turn('upper_arm' + side, Z, sign * (arm.raise * .7 - ARM_TUCK));
      turn('upper_arm' + side, X, -arm.forward);
      const up = THREE.MathUtils.clamp(arm.raise / 1.45, 0, 1);
      turn('forearm' + side, X, -arm.bend * (1 - up));
      turn('forearm' + side, Z, sign * arm.bend * up);
    }
    turn('head', Y, p.headYaw);
    turn('head', X, p.headPitch);
    turn('head', Z, p.headRoll);
    turn('antenna', Z, p.antenna);
    for (const name of BONES) bones[name].quaternion.copy(rest[name].local).multiply(pending[name]);
    updateScreen(material, p);
  }

  return { root, bones, face, applyPose, height: 1, seatY: SEAT_Y, faceY: SCREEN.y };
}
