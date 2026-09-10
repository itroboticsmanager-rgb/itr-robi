import * as THREE from 'three';
import { blend, rounded, ellipsoid, segment, sculpt, skin, tubeGeometry, bendTube } from './sculpt.js';
import { createScreen, updateScreen } from './screen.js';

const blue = new THREE.MeshStandardMaterial({ color: '#1267d9', roughness: .36, metalness: .03 });
const rim = new THREE.MeshStandardMaterial({ color: '#174d96', roughness: .36 });
const glove = new THREE.MeshStandardMaterial({ color: '#83c6f4', roughness: .49 });
const yellow = new THREE.MeshStandardMaterial({ color: '#ffc522', roughness: .85 });
const soleMat = new THREE.MeshStandardMaterial({ color: '#efb518', roughness: .64 });
const navy = new THREE.MeshStandardMaterial({ color: '#263e61', roughness: .9 });
const white = new THREE.MeshStandardMaterial({ color: '#dceffc', roughness: .7 });
const sphere = new THREE.SphereGeometry(1, 24, 16);
// Thigh and shin are the same length, so the leg reaches exactly SEGMENT * 2.
const SEGMENT = .335, REACH = SEGMENT * 2;
const smooth = (a, b, x) => THREE.MathUtils.smoothstep(x, a, b);
function group(parent, pos = [0, 0, 0], bone = false) { const g = bone ? new THREE.Bone() : new THREE.Group(); g.position.set(...pos); parent.add(g); return g; }
function mesh(parent, geometry, material, pos = [0, 0, 0]) { const m = new THREE.Mesh(geometry, material); m.position.set(...pos); parent.add(m); return m; }
function oval(parent, material, pos, scale) { const m = mesh(parent, sphere, material, pos); m.scale.set(...scale); return m; }
function tube(parent, material, points, radius) { return mesh(parent, new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p))), 28, radius, 8, false), material); }
function roundShape(w, h, r) {
  const x = -w / 2, y = -h / 2, s = new THREE.Shape();
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y); return s;
}
function plate(parent, mat, w, h, r, depth, pos) { return mesh(parent, new THREE.ExtrudeGeometry(roundShape(w, h, r), { depth, bevelEnabled: true, bevelThickness: .012, bevelSize: .012, bevelSegments: 3, curveSegments: 16, steps: 1 }), mat, pos); }
function headShell() {
  // Rounded profiles form one convex housing, returning into the inset screen.
  const profiles = [
    [1.80, 1.27, .36, -.39], [2.04, 1.51, .44, -.29],
    [2.16, 1.63, .48, -.08], [2.16, 1.63, .48, .16],
    [2.10, 1.57, .46, .31], [1.98, 1.45, .42, .41],
    [1.84, 1.31, .34, .445], [1.75, 1.22, .29, .415],
    [1.72, 1.19, .27, .365],
  ];
  const contour = new THREE.CatmullRomCurve3(profiles.map(([w, h, r, z]) => new THREE.Vector3(w, h, z)), false, 'catmullrom', .5);
  const corners = new THREE.CatmullRomCurve3(profiles.map(p => new THREE.Vector3(p[2], 0, 0)), false, 'catmullrom', .5);
  const positions = [], indices = [];
  let count;
  for (let j = 0; j <= 40; j++) {
    const point = contour.getPoint(j / 40), r = corners.getPoint(j / 40).x;
    const { x: w, y: h, z } = point;
    const points = roundShape(w, h, r).getPoints(16); count = points.length;
    points.forEach(p => positions.push(p.x, p.y, z));
    if (!j) continue;
    for (let i = 0; i < count - 1; i++) {
      const a = (j - 1) * count + i, b = j * count + i;
      indices.push(a, a + 1, b, a + 1, b + 1, b);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  g.setIndex(indices); g.computeVertexNormals(); return g;
}
function skinned(parent, geo, mat, bones, pending) {
  const m = new THREE.SkinnedMesh(geo, mat); parent.add(m); m.frustumCulled = false;
  // Raycasts need a bound that includes animated vertices, not the first pose.
  // Conservative local bound avoids scanning the skinned vertices each frame.
  m.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 3);
  pending.push([m, bones]); return m;
}

function handAt(elbow, side, pending) {
  const hand = group(elbow, [0, -.51, 0]); hand.userData.action = 'highfive';
  const base = group(hand, [0, 0, 0], true);
  const fingers = [-1, 0, 1].map(i => group(base, [i * .125, -.26, .025], true));
  const thumb = group(base, [-side * .13, -.07, .035], true);
  const starts = [-1, 0, 1].map(i => [i * .125, -.22, .025]);
  const ends = [-1, 0, 1].map(i => [i * .125, -.475 + Math.abs(i) * .035, .025]);
  const thumbStart = [-side * .13, -.09, .035], thumbEnd = [-side * .285, -.225, .065];
  const geo = sculpt((x, y, z) => {
    let d = ellipsoid(x, y + .14, z - .018, .181, .195, .11);
    d = blend(d, segment(x, y, z, [0, .025, 0], [0, -.10, .015], .115), .06);
    for (let i = 0; i < 3; i++) d = blend(d, segment(x, y, z, starts[i], ends[i], .052), .004 + .037 * smooth(-.34, -.25, y));
    return blend(d, segment(x, y, z, thumbStart, thumbEnd, .066), .06);
  }, [[-.40, -.59, -.18], [.40, .20, .24]], 44);
  skin(geo, (x, y) => {
    const thumbWeight = smooth(.12, .22, -side * x) * smooth(-.30, -.18, y);
    if (-side * x > .17 && y > -.30) return [[0, 1 - thumbWeight], [4, thumbWeight]];
    const index = Math.max(0, Math.min(2, Math.round(x / .125) + 1));
    const f = 1 - smooth(-.32, -.22, y); return [[0, 1 - f], [index + 1, f]];
  });
  const surface = skinned(hand, geo, glove, [base, ...fingers, thumb], pending); surface.name = 'Continuous glove';
  return { group: hand, fingers, thumb, surface };
}
function armAt(torso, base, side, pending) {
  const shoulder = group(base, [side * .65, .72, 0], true), elbow = group(shoulder, [0, -.53, 0], true);
  const geo = new THREE.CapsuleGeometry(.145, .76, 8, 24, 28);
  geo.translate(0, -.525, 0);
  const positions = geo.getAttribute('position');
  for (let i = 0; i < positions.count; i++) {
    const y = positions.getY(i);
    const taper = (.105 + .040 * smooth(-.95, -.18, y) + .006 * Math.exp(-(((y + .72) / .14) ** 2))) / .145;
    positions.setX(i, positions.getX(i) * taper); positions.setZ(i, positions.getZ(i) * taper);
  }
  geo.computeVertexNormals();
  geo.translate(side * .65, .72, 0);
  skin(geo, (x, y) => { const f = 1 - smooth(-.015, .395, y); return [[0, 1 - f], [1, f]]; });
  const surface = skinned(torso, geo, blue, [shoulder, elbow], pending); surface.name = 'Continuous arm';
  return { shoulder, elbow, hand: handAt(elbow, side, pending), surface };
}
function shoeField(x, y, z) {
  // A low toe box climbing into a cuff around the ankle. The cuff had to be a
  // ball before, because the foot pitched about a point far below the ankle and
  // the collar swung off the leg; it hung 2.7 cm past the back of the sole.
  const body = ellipsoid(x, y + .045, z - .13, .213, .285, .36);
  const cuff = ellipsoid(x, y - .175, z + .075, .150, .180, .150);
  return Math.max(blend(body, cuff, .09), -.058 - y);
}
function shoeTop(x, z) {
  let low = .02, high = .45;
  for (let i = 0; i < 18; i++) { const mid = (low + high) / 2; if (shoeField(x, mid, z) < 0) low = mid; else high = mid; }
  return (low + high) / 2;
}
function shoeAt(parent, side, shoeGeometry) {
  // The group pivots on the ankle, the joint the foot actually turns about, and
  // the shoe hangs below and ahead of it. Turning the foot about a point on the
  // sole instead swung the collar off the leg it is meant to close around.
  const shoe = group(parent, [side * .36, .34, .015]);
  const foot = group(shoe, [0, -.21, .07]);
  const sole = mesh(foot, new THREE.ExtrudeGeometry(roundShape(.435, .735, .19), { depth: .026, bevelEnabled: true, bevelThickness: .004, bevelSize: .004, bevelSegments: 2, curveSegments: 16, steps: 1 }), soleMat, [0, -.087, .13]);
  sole.rotation.x = -Math.PI / 2; sole.name = 'Thin fitted outsole';
  mesh(foot, shoeGeometry, blue).name = 'Sneaker upper';
  // A tongue follows the same last, and each lace samples the actual upper.
  const points = [], indices = [];
  for (let j = 0; j <= 10; j++) for (let i = 0; i <= 6; i++) {
    const x = (i / 6 - .5) * .18, z = -.035 + j / 10 * .30;
    points.push(x, shoeTop(x, z) + .003, z);
    if (j < 10 && i < 6) { const a = j * 7 + i; indices.push(a, a + 7, a + 1, a + 1, a + 7, a + 8); }
  }
  const tongue = new THREE.BufferGeometry(); tongue.setAttribute('position', new THREE.Float32BufferAttribute(points, 3)); tongue.setIndex(indices); tongue.computeVertexNormals();
  mesh(foot, tongue, rim).name = 'Fitted tongue';
  for (let i = 0; i < 3; i++) {
    const z = .015 + i * .09;
    tube(foot, white, [-.12, -.06, 0, .06, .12].map(x => [x, shoeTop(x, z) + .014, z]), .014);
  }
  return { shoe, foot };
}
export function createRobot() {
  const root = new THREE.Group(); root.name = 'ROBI';
  const torso = group(root, [0, 1.30, 0]), base = group(torso, [0, 0, 0], true), pending = [];
  const arms = [-1, 1].map(s => armAt(torso, base, s, pending));
  const shirtGeo = sculpt((x, y, z) => {
    const flare = .018 * (1 - smooth(.10, .70, y));
    let d = rounded(x, y - .51, z, .555 + flare, .49, .33, .16);
    for (const side of [-1, 1]) d = blend(d, segment(x, y, z, [side * .47, .79, 0], [side * .69, .52, 0], .238), .15);
    const neck = Math.max(Math.hypot(x, z * 1.25) - .225, .88 - y);
    d = Math.max(d, -neck);
    d += .007 * Math.exp(-(((y - .08) / .018) ** 2));
    return d;
  }, [[-1.05, -.09, -.49], [1.05, 1.12, .49]], 52);
  skin(shirtGeo, (x, y) => { const f = smooth(.43, .85, Math.abs(x)) * smooth(.20, .48, y); return [[0, 1 - f], [x < 0 ? 1 : 2, f]]; });
  const shirt = skinned(torso, shirtGeo, yellow, [base, arms[0].shoulder, arms[1].shoulder], pending); shirt.name = 'One-piece shirt and sleeves';
  mesh(torso, new THREE.CapsuleGeometry(.15, .19, 6, 20), blue, [0, 1.04, 0]);
  mesh(torso, new THREE.CircleGeometry(.13, 32), blue, [0, .55, .334]);
  const shortsGeo = sculpt((x, y, z) => {
    // An oval seat flows into tapered, round fabric tubes instead of box legs.
    const seatRadial = (Math.hypot(x / .505, z / .315) - 1) * .315;
    const seatVertical = Math.abs(y + .095) - .205;
    let d = Math.hypot(Math.max(seatRadial + .075, 0), Math.max(seatVertical + .075, 0)) + Math.min(Math.max(seatRadial + .075, seatVertical + .075), 0) - .075;
    const forwardFit = .085 * (1 - smooth(-.53, -.22, y));
    const fullness = smooth(-.53, -.22, y);
    // The fabric tube sits on the leg it covers rather than inboard of it, and
    // keeps its width down to the hem. Offset and tapered, the outboard side of
    // the cuff came out 0.9 mm thick -- a thirtieth of a sculpt voxel, far too
    // thin for marching cubes to hold together, so the hem tore open on the leg.
    const radiusX = .245 + .009 * fullness, radiusZ = .288 - .008 * fullness;
    for (const s of [-1, 1]) {
      const radial = (Math.hypot((x - s * .30) / radiusX, (z - forwardFit) / radiusZ) - 1) * radiusX;
      // The leg of the shorts stops above the knee. Hanging past it put the hem
      // on the shin while the cuff is rigidly bound to the thigh, so a bent knee
      // sawed the shin straight out through the hem.
      const vertical = Math.abs(y + .3075) - .2225;
      const leg = Math.hypot(Math.max(radial + .035, 0), Math.max(vertical + .035, 0)) + Math.min(Math.max(radial + .035, vertical + .035), 0) - .035;
      d = blend(d, leg, .09);
    }
    for (const s of [-1, 1]) {
      const legOpening = Math.max((Math.hypot((x - s * .30) / .172, (z - forwardFit) / .200) - 1) * .172, y + .43);
      d = Math.max(d, -legOpening);
    }
    // A shallow stitched hem is part of the cloth, not a separate floating cuff.
    d += .0035 * Math.exp(-(((y + .475) / .013) ** 2));
    return d;
  }, [[-.62, -.64, -.40], [.62, .24, .46]], 48);
  const thighs = [-1, 1].map(side => group(base, [side * .30, -.32, 0], true));
  skin(shortsGeo, (x, y) => {
    // The leg of the shorts rides the thigh outright and only the seat stays with
    // the torso. Handing the cuff barely two thirds of the thigh left it behind
    // whenever the leg swung, and the leg came out through the hem.
    const lower = (1 - smooth(-.46, -.10, y)) * smooth(.035, .18, Math.abs(x));
    return [[0, 1 - lower], [x < 0 ? 1 : 2, lower]];
  });
  const shorts = skinned(torso, shortsGeo, navy, [base, ...thighs], pending); shorts.name = 'Shorts following the thighs';
  const head = group(torso, [0, 1.31, 0]); head.userData.action = 'greet';
  mesh(head, headShell(), blue, [0, .56, 0]).name = 'Rounded mascot housing';
  plate(head, blue, 1.80, 1.27, .36, .025, [0, .56, -.41]);
  const screenMaterial = createScreen();
  const screenGeo = new THREE.ShapeGeometry(roundShape(1.74, 1.21, .275), 20);
  const uv = screenGeo.attributes.uv, pos = screenGeo.attributes.position;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, pos.getX(i) / 1.74 + .5, pos.getY(i) / 1.21 + .5);
  const screen = mesh(head, screenGeo, screenMaterial, [0, .56, .37]); screen.name = 'Pixel display';
  for (const s of [-1, 1]) oval(head, glove, [s * 1.03, .49, -.025], [.13, .225, .20]);
  const antenna = group(head, [-.10, 1.31, -.06]);
  tube(antenna, blue, [[0, 0, 0], [0, .16, 0], [0, .32, 0], [0, .48, 0]], .040);
  oval(antenna, glove, [0, .48, 0], [.145, .145, .145]);
  const shoeGeo = sculpt(shoeField, [[-.29, -.11, -.30], [.29, .47, .58]], 38);
  const legs = [-1, 1].map(side => { const surface = mesh(root, tubeGeometry(), blue); surface.name = 'Continuous leg'; surface.frustumCulled = false; return { side, surface, ...shoeAt(root, side, shoeGeo) }; });
  root.updateMatrixWorld(true);
  for (const [m, bones] of pending) m.bind(new THREE.Skeleton(bones));
  const thighRest = legs.map(leg => {
    const restAxis = new THREE.Vector3(leg.side * .06, -.64, .015);
    const d = restAxis.length(); restAxis.normalize();
    const restBend = new THREE.Vector3(0, 0, 1).addScaledVector(restAxis, -restAxis.z).normalize();
    const direction = restAxis.multiplyScalar(d / 2).addScaledVector(restBend, Math.sqrt(SEGMENT ** 2 - (d / 2) ** 2)).normalize();
    return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, -1, 0), direction).invert();
  });
  return { root, torso, head, antenna, arms, legs, thighs, thighRest, shirt, shorts, screen, screenMaterial };
}

const hip = new THREE.Vector3(), ankle = new THREE.Vector3(), knee = new THREE.Vector3();
const axis = new THREE.Vector3(), bend = new THREE.Vector3(), forward = new THREE.Vector3(0, 0, 1);
const thighDirection = new THREE.Vector3(), inverseTorso = new THREE.Quaternion(), down = new THREE.Vector3(0, -1, 0);
const armRotation = new THREE.Quaternion(), openPalm = new THREE.Quaternion(), palmEuler = new THREE.Euler();
const hangingAnkle = new THREE.Vector3(), restingThigh = new THREE.Quaternion();
export function poseRobot(robot, p) {
  robot.torso.position.set(p.shift, 1.30 + p.bob, 0); robot.torso.rotation.set(p.lean, p.turn, p.tilt);
  robot.head.rotation.set(p.headX, p.headY, p.headZ); robot.antenna.rotation.z = p.antenna;
  updateScreen(robot.screenMaterial, p);
  robot.arms.forEach((arm, i) => {
    const v = p.arms[i]; arm.shoulder.rotation.set(v.x, v.y, v.z); arm.elbow.rotation.set(v.ex, 0, v.ez); arm.hand.group.rotation.set(v.wx, v.wy, v.wz);
    if (v.present > 0) {
      // Keep the palm legible when the shoulder pitches forward for contact.
      armRotation.copy(robot.torso.quaternion).multiply(arm.shoulder.quaternion).multiply(arm.elbow.quaternion).invert();
      openPalm.setFromEuler(palmEuler.set(.06, -.10, Math.PI - .20 + v.wz));
      armRotation.multiply(openPalm);
      arm.hand.group.quaternion.slerp(armRotation, v.present);
    }
    arm.hand.fingers.forEach((finger, f) => { finger.rotation.x = v.curl; finger.rotation.z = (f - 1) * (.10 + v.spread); });
  });
  robot.root.updateMatrixWorld(true);
  robot.legs.forEach((leg, i) => {
    hip.set(leg.side * .30, -.32, 0).applyMatrix4(robot.torso.matrix);
    const lift = p.feet[i]; ankle.set(leg.side * .36 + (p.footX?.[i] ?? 0), .34 + lift, .015 + (p.footZ?.[i] ?? 0));
    const suspended = p.suspend ?? 0;
    if (suspended) {
      hangingAnkle.set(leg.side * .025 - p.dangle * .16, -.59, .035 + leg.side * p.dangle * .12).applyQuaternion(robot.torso.quaternion).add(hip);
      ankle.lerp(hangingAnkle, suspended);
    }
    // Stop just short of full extension. A straight two-bone leg is a singular
    // solution: the knee offset is a square root that falls to zero with an
    // infinite slope, so it whipped straight and back at every long stride.
    axis.subVectors(ankle, hip); const d = Math.min(REACH * .96, Math.max(.05, axis.length())); axis.normalize();
    bend.copy(forward).addScaledVector(axis, -forward.dot(axis)).normalize();
    const a = d / 2, h = Math.sqrt(Math.max(0, SEGMENT ** 2 - a ** 2));
    knee.copy(hip).addScaledVector(axis, a).addScaledVector(bend, h);
    // Bind the cloth to the resting thigh: absolute IK angles would hike up the hem.
    inverseTorso.copy(robot.torso.quaternion).invert();
    thighDirection.subVectors(knee, hip).applyQuaternion(inverseTorso).normalize();
    robot.thighs[i].quaternion.setFromUnitVectors(down, thighDirection).multiply(robot.thighRest[i]);
    robot.thighs[i].quaternion.slerp(restingThigh, suspended * .8);
    bendTube(leg.surface.geometry, hip, knee, ankle);
    leg.shoe.position.copy(ankle);
    leg.shoe.rotation.set(lift * .45 + suspended * .22 + (p.toe?.[i] ?? 0), 0, suspended * (p.tilt - p.dangle * .35));
  });
}
