import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { smooth } from './motion.js';

// ITRobotics surfaces: blue-tinted neutrals carry the room, brand blue marks
// structure and equipment, and yellow or coral appear only as short accents.
// The roles follow app/src/robi/ui/theme.py, so the bay matches the kiosk.
const colors = {
  floor: '#cbdef2', floorInlay: '#b2cde8', wall: '#e6f0fa', panel: '#d6e7f7', seam: '#bed6ee',
  steel: '#b4cbe4', steelDeep: '#8fadcd', white: '#f8fbfe', glass: '#c6e0f8', sky: '#9fd0f7',
  blue: '#2563eb', blueSoft: '#4b9dfa', blueDeep: '#1b4bb0', ink: '#123a6b',
  yellow: '#fab720', coral: '#f16f5d', mint: '#47c38b',
};
const vector = new THREE.Vector3();

export function createWorkshop() {
  const root = new THREE.Group(), fixed = new THREE.Group(); root.add(fixed);
  const metallic = key => key === 'steel' || key === 'steelDeep';
  const materials = Object.fromEntries(Object.entries(colors).map(([key, color]) => [key,
    new THREE.MeshStandardMaterial({ color, roughness: key === 'glass' ? .24 : metallic(key) ? .46 : .78, metalness: metallic(key) ? .25 : .02 })]));
  const box = (parent, size, at, material = 'panel', radius = .05) => {
    const obj = new THREE.Mesh(new RoundedBoxGeometry(...size, 2, Math.min(radius, Math.min(...size) / 2)), materials[material]);
    obj.position.set(...at); parent.add(obj); return obj;
  };
  const ballMesh = (parent, radius, at, material) => {
    const obj = new THREE.Mesh(new THREE.SphereGeometry(radius, 20, 12), materials[material]); obj.position.set(...at); parent.add(obj); return obj;
  };
  const rod = (parent, a, b, radius, material) => {
    const dir = new THREE.Vector3(...b).sub(new THREE.Vector3(...a));
    const obj = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, dir.length(), 12), materials[material]);
    obj.position.set(...a).addScaledVector(dir, .5); obj.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize()); parent.add(obj); return obj;
  };
  const ring = (parent, radius, at, material, tube = radius * .3) => {
    const obj = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 8, 24), materials[material]); obj.position.set(...at); parent.add(obj); return obj;
  };
  const lit = color => new THREE.MeshBasicMaterial({ color });

  // Shell of a bright lab bay. One readable plane, fixed camera, no navigation.
  // The bay fills the display, so the floor runs past the bottom of the frame
  // and the walls past the top: a room that stopped short left empty bands.
  box(fixed, [12.8, .20, 20], [0, -.15, 6.9], 'floor', .1);
  // Inlaid panel grid and a painted work-zone edge, flush with the floor.
  for (let i = -5; i <= 5; i++) box(fixed, [.02, .008, 19.4], [i * 1.04, -.046, 6.9], 'floorInlay', .002);
  for (let i = -2; i <= 12; i++) box(fixed, [12.4, .008, .02], [0, -.046, -.2 + i * 1.15], 'floorInlay', .002);
  box(fixed, [12.4, .01, .06], [0, -.044, 1.62], 'yellow', .004);
  box(fixed, [12.8, 7.8, .20], [0, 3.7, -2.65], 'wall');
  for (const x of [-6.3, 6.3]) box(fixed, [.24, 7.8, 20], [x, 3.7, 6.9], 'wall');
  // Panelling seams and a skirting conduit give the wall a built, technical read.
  for (const y of [1.05, 2.95, 4.85, 6.75]) box(fixed, [12.4, .045, .05], [0, y, -2.52], 'seam', .01);
  box(fixed, [12.4, .10, .07], [0, .16, -2.50], 'steel', .02);
  // Ceiling service rail carrying the luminaires that light the bay.
  box(fixed, [11.6, .18, .34], [0, 7.05, -1.15], 'steel', .05);
  for (const x of [-3.6, 0, 3.6]) box(fixed, [2.15, .10, .52], [x, 6.91, -1.15], 'white', .05);

  // Window onto a bright exterior, with a clean mullion instead of scenery.
  box(fixed, [3.25, 2.55, .22], [-3.83, 3.77, -2.41], 'blue', .09);
  box(fixed, [2.91, 2.21, .06], [-3.83, 3.77, -2.27], 'sky', .06);
  ballMesh(fixed, .30, [-4.62, 4.30, -2.20], 'white').scale.z = .08;
  for (const [x, h] of [[-4.85, .55], [-4.35, .34], [-3.85, .72], [-3.30, .45], [-2.75, .60]]) {
    box(fixed, [.30, h, .03], [x, 2.86 + h / 2, -2.19], 'steel', .02);
  }
  box(fixed, [.10, 2.23, .12], [-3.83, 3.77, -2.15], 'white');
  box(fixed, [2.94, .10, .12], [-3.83, 3.73, -2.15], 'white');
  box(fixed, [3.55, .16, .50], [-3.83, 2.41, -2.12], 'steel', .03);

  // Access door: brand frame, frosted panel, and a reader that stays lit.
  box(fixed, [2.20, 4.58, .18], [4.6, 2.25, -2.40], 'blue', .11);
  box(fixed, [1.86, 4.20, .08], [4.6, 2.14, -2.27], 'panel', .10);
  box(fixed, [1.32, 1.42, .04], [4.6, 3.24, -2.20], 'glass', .08);
  for (let i = 0; i < 3; i++) box(fixed, [1.32, .035, .05], [4.6, 2.94 + i * .30, -2.18], 'panel', .01);
  box(fixed, [.20, .30, .07], [5.32, 2.30, -2.18], 'white', .03);
  const reader = new THREE.Mesh(new THREE.PlaneGeometry(.12, .05), lit(colors.mint));
  reader.position.set(5.32, 2.38, -2.14); root.add(reader);

  // Assembly bench: white top, brand apron, sorted trays, a vice and a monitor.
  box(fixed, [3.70, .19, 1.95], [-3.02, 1.60, -.35], 'white', .06);
  box(fixed, [3.30, .49, 1.12], [-3.02, 1.26, -.61], 'blue', .05);
  box(fixed, [3.34, .06, 1.16], [-3.02, 1.53, -.61], 'blueDeep', .02);
  for (const x of [-4.5, -1.55]) {
    for (const z of [-1.09, -.05]) box(fixed, [.14, 1.12, .14], [x, .55, z], 'steelDeep', .03);
    box(fixed, [.12, .10, 1.10], [x, .34, -.57], 'steelDeep', .03);
  }
  // An antistatic mat marks the working area Robi actually reaches into.
  box(fixed, [1.24, .016, .82], [-2.92, 1.705, -.20], 'blueSoft', .02);
  box(fixed, [1.12, .006, .70], [-2.92, 1.714, -.20], 'panel', .015);
  for (let i = 0; i < 3; i++) box(fixed, [.30, .09, .24], [-4.36, 1.745, -.92 + i * .30], ['blue', 'yellow', 'coral'][i], .02);
  box(fixed, [.22, .16, .30], [-1.92, 1.775, -.55], 'steelDeep', .03);
  box(fixed, [.14, .22, .14], [-1.92, 1.86, -.55], 'coral', .03);

  // One screen in the room, and it reports what Robi is actually doing.
  box(fixed, [.34, .05, .22], [-4.05, 1.72, -1.06], 'steelDeep', .02);
  rod(fixed, [-4.05, 1.74, -1.06], [-4.05, 2.32, -1.06], .035, 'steelDeep');
  const monitor = box(fixed, [1.30, .84, .07], [-4.05, 2.72, -1.05], 'ink', .05);
  monitor.rotation.y = .28;
  const screenCanvas = document.createElement('canvas'); screenCanvas.width = 256; screenCanvas.height = 160;
  const screenCtx = screenCanvas.getContext('2d');
  const screenTexture = new THREE.CanvasTexture(screenCanvas);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.16, .70), new THREE.MeshBasicMaterial({ map: screenTexture }));
  screen.rotation.y = .28;
  screen.position.set(-4.05 + Math.sin(.28) * .04, 2.72, -1.05 + Math.cos(.28) * .04);
  root.add(screen);

  // Tool wall: brand perforated panel carrying robot parts, not generic clutter.
  box(fixed, [2.34, 1.62, .09], [-.62, 3.78, -2.47], 'blue', .05);
  box(fixed, [2.16, 1.44, .04], [-.62, 3.78, -2.41], 'blueDeep', .03);
  for (let x = -1.52; x < .32; x += .26) for (let y = 3.20; y < 4.42; y += .26) {
    const hole = new THREE.Mesh(new THREE.CircleGeometry(.022, 6), materials.blue); hole.position.set(x, y, -2.386); fixed.add(hole);
  }
  ring(fixed, .19, [-1.24, 4.02, -2.34], 'yellow', .05);
  ring(fixed, .13, [-.86, 3.80, -2.34], 'steel', .045);
  const wheel = new THREE.Mesh(new THREE.CylinderGeometry(.20, .20, .09, 20), materials.ink);
  wheel.position.set(-.28, 4.00, -2.33); wheel.rotation.x = Math.PI / 2; fixed.add(wheel);
  ring(fixed, .10, [-.28, 4.00, -2.28], 'steel', .035);
  box(fixed, [.26, .34, .18], [.02, 3.44, -2.32], 'coral', .03);
  rod(fixed, [.02, 3.44, -2.22], [.02, 3.44, -2.10], .03, 'steelDeep');
  box(fixed, [.30, .22, .14], [-1.30, 3.36, -2.33], 'white', .03);
  for (let i = 0; i < 3; i++) box(fixed, [.24, .012, .012], [-1.30, 3.30 + i * .06, -2.25], 'mint', .004);

  // Component shelf with labelled bins, right of the tool wall.
  for (const y of [2.42, 3.42]) box(fixed, [2.30, .13, .62], [2.10, y, -2.20], 'white', .03);
  for (const x of [1.02, 3.18]) box(fixed, [.10, 1.30, .58], [x, 2.90, -2.20], 'steelDeep', .03);
  for (let i = 0; i < 3; i++) {
    box(fixed, [.56, .40, .44], [1.34 + i * .62, 2.71, -2.16], ['blue', 'coral', 'yellow'][i], .05);
    box(fixed, [.34, .09, .02], [1.34 + i * .62, 2.78, -1.93], 'white', .01);
  }
  box(fixed, [.52, .52, .40], [1.42, 3.75, -2.16], 'blueSoft', .09);
  ballMesh(fixed, .10, [1.42, 3.79, -1.94], 'white').scale.z = .35;

  // Bench-top printer: the room's one piece of slow, purposeful ambient motion.
  box(fixed, [1.34, .16, .96], [2.72, 1.61, -1.05], 'white', .04);
  for (const x of [2.16, 3.28]) for (const z of [-1.44, -.66]) box(fixed, [.10, 1.46, .10], [x, .84, z], 'steelDeep', .03);
  // A closed back and sides: the print head has something to read against.
  box(fixed, [1.34, 1.12, .06], [2.72, 2.26, -1.49], 'ink', .03);
  for (const x of [2.11, 3.33]) box(fixed, [.07, 1.12, .86], [x, 2.26, -1.05], 'white', .02);
  box(fixed, [1.40, .12, .90], [2.72, 2.86, -1.05], 'white', .03);
  for (const x of [2.28, 3.16]) rod(fixed, [x, 1.72, -1.20], [x, 2.74, -1.20], .03, 'steelDeep');
  box(fixed, [1.26, .07, .09], [2.72, 2.62, -1.20], 'steelDeep', .02);
  box(fixed, [1.10, .05, .78], [2.72, 1.72, -1.02], 'steel', .02);
  box(fixed, [.36, .26, .06], [2.72, 1.86, -.60], 'ink', .02);
  const printerHead = box(root, [.22, .26, .22], [2.72, 2.38, -1.05], 'blue', .04);
  const printerTip = new THREE.Mesh(new THREE.ConeGeometry(.05, .10, 10), materials.steelDeep);
  printerTip.position.set(0, -.17, 0); printerHead.add(printerTip);
  const printLed = new THREE.Mesh(new THREE.PlaneGeometry(.10, .035), lit(colors.mint));
  printLed.position.set(0, .05, .12); printerHead.add(printLed);

  // Robi's charging dock, on the floor where he rests between jobs.
  box(fixed, [1.10, .10, .78], [.55, .01, -1.55], 'blue', .04);
  box(fixed, [.94, .04, .62], [.55, .07, -1.55], 'blueDeep', .02);
  box(fixed, [1.06, .52, .12], [.55, .30, -1.90], 'blue', .05);
  const dockLed = new THREE.Mesh(new THREE.PlaneGeometry(.44, .05), lit(colors.blueSoft));
  dockLed.position.set(.55, .44, -1.83); root.add(dockLed);
  box(fixed, [4.6, .14, .14], [-3.4, .40, -2.44], 'steel', .05);
  box(fixed, [3.2, .14, .14], [3.1, .40, -2.44], 'steel', .05);

  // Interactive trio: LED task lamp, robot-soccer ball, modular robot cubes.
  const lamp = new THREE.Group(); root.add(lamp); lamp.userData.object = 'lamp';
  box(lamp, [.54, .09, .42], [-4.24, 1.76, -.49], 'blue', .03);
  rod(lamp, [-4.24, 1.78, -.49], [-4.30, 2.51, -.49], .045, 'steelDeep');
  rod(lamp, [-4.30, 2.51, -.49], [-3.76, 2.91, -.49], .045, 'steelDeep');
  ballMesh(lamp, .09, [-4.30, 2.51, -.49], 'blue');
  const shade = box(lamp, [.54, .16, .42], [-3.70, 2.83, -.49], 'yellow', .06);
  shade.rotation.z = -.38;
  box(lamp, [.46, .05, .34], [-3.70, 2.74, -.49], 'white', .02).rotation.z = -.38;
  const bulbMaterial = lit('#fff3cf');
  const bulb = new THREE.Mesh(new THREE.PlaneGeometry(.42, .30), bulbMaterial);
  bulb.rotation.set(-Math.PI / 2, 0, 0); bulb.position.set(-3.70, 2.735, -.49); lamp.add(bulb);
  const poolMaterial = new THREE.MeshBasicMaterial({ color: '#ffe7ad', transparent: true, opacity: .46, depthWrite: false });
  const pool = new THREE.Mesh(new THREE.CircleGeometry(.58, 32), poolMaterial); pool.rotation.x = -Math.PI / 2; pool.position.set(-3.6, 1.704, -.49); root.add(pool);

  const ball = ballMesh(root, .28, [2.89, .28, .40], 'panel'); ball.userData.object = 'ball';
  for (const across of [false, true]) {
    const seam = new THREE.Mesh(new THREE.TorusGeometry(.281, .016, 6, 32), materials.blue);
    if (across) seam.rotation.y = Math.PI / 2; ball.add(seam);
  }
  const ballRing = new THREE.Mesh(new THREE.TorusGeometry(.20, .022, 6, 24), lit(colors.yellow));
  ballRing.rotation.x = Math.PI / 2; ball.add(ballRing);

  const blocks = [], homes = [];
  for (let i = 0; i < 3; i++) {
    const home = new THREE.Vector3(-1.65, 1.87, -.65 + i * .36);
    const block = box(root, [.32, .32, .32], home.toArray(), ['blue', 'coral', 'yellow'][i], .045);
    // Connector studs read the cubes as a robotics kit rather than plain boxes.
    for (const [dx, dz] of [[-.08, -.08], [.08, -.08], [-.08, .08], [.08, .08]]) {
      const stud = new THREE.Mesh(new THREE.CylinderGeometry(.045, .045, .05, 10), materials.white);
      stud.position.set(dx, .18, dz); block.add(stud);
    }
    block.userData.object = 'blocks'; blocks.push(block); homes.push(home);
  }

  // Merge only immutable meshes sharing a material. Interactive objects stay separate.
  fixed.updateMatrixWorld(true);
  const groups = new Map();
  fixed.traverse(obj => {
    if (!obj.isMesh) return;
    const geometry = (obj.geometry.index ? obj.geometry.toNonIndexed() : obj.geometry.clone()).applyMatrix4(obj.matrixWorld);
    if (!groups.has(obj.material)) groups.set(obj.material, []);
    groups.get(obj.material).push(geometry); obj.geometry.dispose();
  });
  root.remove(fixed);
  for (const [material, list] of groups) {
    root.add(new THREE.Mesh(mergeGeometries(list), material)); list.forEach(g => g.dispose());
  }

  const shadowCanvas = document.createElement('canvas'); shadowCanvas.width = shadowCanvas.height = 64;
  const ctx = shadowCanvas.getContext('2d'), gradient = ctx.createRadialGradient(32, 32, 3, 32, 32, 31);
  gradient.addColorStop(0, 'rgba(31,74,132,.24)'); gradient.addColorStop(1, 'rgba(31,74,132,0)'); ctx.fillStyle = gradient; ctx.fillRect(0, 0, 64, 64);
  const shadowMaterial = new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(shadowCanvas), transparent: true, depthWrite: false });
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.45, 1.5), shadowMaterial); shadow.rotation.x = -Math.PI / 2; shadow.position.y = -.025; root.add(shadow);
  const ballShadow = new THREE.Mesh(new THREE.PlaneGeometry(.9, .7), shadowMaterial); ballShadow.rotation.x = -Math.PI / 2; ballShadow.position.set(ball.position.x, -.024, .40); root.add(ballShadow);

  const ringCanvas = document.createElement('canvas'); ringCanvas.width = ringCanvas.height = 128;
  const ringCtx = ringCanvas.getContext('2d');
  const ringGradient = ringCtx.createRadialGradient(64, 64, 30, 64, 64, 62);
  ringGradient.addColorStop(0, 'rgba(37,99,235,0)'); ringGradient.addColorStop(.6, 'rgba(37,99,235,.55)'); ringGradient.addColorStop(1, 'rgba(37,99,235,0)');
  ringCtx.fillStyle = ringGradient; ringCtx.fillRect(0, 0, 128, 128);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(ringCanvas), transparent: true, depthWrite: false, opacity: 0 }));
  halo.visible = false; root.add(halo);
  const haloSpots = { lamp: [shade, 1.5], ball: [ball, 1.35], blocks: [blocks[0], 1.2] };
  let hovered = null, haloLevel = 0;

  const contact = new THREE.Vector3(), start = new THREE.Vector3(), end = new THREE.Vector3();
  const tint = new THREE.Color();
  const shine = (mesh, color, level) => mesh.material.color.copy(tint.set(color)).multiplyScalar(level);
  let ambient = 0, screenFrame = -1, screenLine = '';
  function paintScreen(text, built, lampOn) {
    screenCtx.fillStyle = '#0f2954'; screenCtx.fillRect(0, 0, 256, 160);
    screenCtx.fillStyle = '#2563eb'; screenCtx.fillRect(0, 0, 256, 26);
    screenCtx.fillStyle = '#f8fbfe'; screenCtx.font = '600 13px system-ui, sans-serif';
    screenCtx.fillText('ITROBOTICS · СТЕНД', 10, 18);
    screenCtx.fillStyle = '#9dc4f6'; screenCtx.font = '12px system-ui, sans-serif';
    screenCtx.fillText(text.slice(0, 32), 10, 50);
    for (let i = 0; i < 3; i++) {
      screenCtx.fillStyle = i < built ? '#47c38b' : '#1b4bb0';
      screenCtx.fillRect(10 + i * 34, 62, 28, 12);
    }
    screenCtx.fillStyle = lampOn ? '#fab720' : '#1b4bb0';
    screenCtx.fillRect(214, 62, 32, 12);
    // A slow telemetry trace, so the panel is alive without ever flashing.
    screenCtx.strokeStyle = '#4b9dfa'; screenCtx.lineWidth = 2; screenCtx.beginPath();
    for (let x = 0; x <= 236; x += 4) {
      const y = 120 + Math.sin((x + ambient * 40) * .05) * 13 + Math.sin((x + ambient * 22) * .017) * 7;
      x ? screenCtx.lineTo(10 + x, y) : screenCtx.moveTo(10 + x, y);
    }
    screenCtx.stroke();
    screenTexture.needsUpdate = true;
  }
  paintScreen('Стенд готовий', 0, true);

  return {
    root, shadow, targets: [lamp, ball, ...blocks],
    // Pointing at a part is enough to see that it answers; the tap still decides.
    hover(name) { hovered = name && haloSpots[name] ? name : null; },
    lookTarget(task) { return task === 'ball' ? ball.position : task === 'lamp' ? shade.position : new THREE.Vector3(-1.65, 2, -.1); },
    update(brain, engaged, robot) {
      bulbMaterial.color.set(brain.world.lamp ? '#fff3cf' : '#7f93ad'); pool.visible = brain.world.lamp;
      if (engaged) ambient += 1 / 30;
      // Equipment keeps working at its own slow pace: a traversing print head
      // and steady status lights. Nothing blinks and nothing demands attention.
      printerHead.position.set(2.72 + Math.sin(ambient * .55) * .40, 2.38, -1.05 + Math.sin(ambient * .21) * .26);
      shine(printLed, colors.mint, .62 + .38 * Math.sin(ambient * 1.9));
      shine(dockLed, colors.blueSoft, .55 + .45 * Math.sin(ambient * .9));
      shine(reader, colors.mint, .58 + .42 * Math.sin(ambient * .7 + 1.4));
      shine(ballRing, colors.yellow, brain.ballAtVisitor ? .6 + .4 * Math.sin(ambient * 3.4) : .5);
      // The bench monitor repaints a few times a second, not every frame.
      if (brain.status !== screenLine || Math.floor(ambient * 5) !== screenFrame) {
        screenLine = brain.status; screenFrame = Math.floor(ambient * 5);
        paintScreen(screenLine, brain.world.blocks, brain.world.lamp);
      }
      haloLevel += ((hovered ? 1 : 0) - haloLevel) * .2;
      halo.visible = haloLevel > .01;
      if (halo.visible) {
        const [anchor, size] = haloSpots[hovered] ?? haloSpots.blocks;
        anchor.getWorldPosition(halo.position);
        if (hovered === 'blocks') halo.position.set(-1.60, 2.05, -.10);
        halo.scale.setScalar(size * (1 + .04 * Math.sin(ambient * 3.2)));
        halo.material.opacity = haloLevel * .85;
      }
      const t = engaged && brain.task === 'ball' && brain.phase === 'act' ? brain.elapsed : 0;
      const roll = brain.ballAtVisitor ? 1 : engaged && brain.ballReturning && brain.phase === 'notice' ? 1 - smooth(0, .85, brain.elapsed) : smooth(.5, 2.1, t);
      ball.position.set(2.65 + roll * 1.4, .28, .5 + roll * 1.15); ball.rotation.z = -roll * 5.9;
      ballShadow.position.set(ball.position.x, -.024, ball.position.z);
      blocks.forEach((block, i) => {
        block.rotation.set(0, 0, 0);
        if (i < brain.world.blocks) block.position.set(-1.55, 1.87 + i * .33, .43);
        else block.position.copy(homes[i]);
      });
      if (engaged && brain.task === 'build' && brain.phase === 'act' && brain.world.blocks < 3) {
        const i = brain.world.blocks, block = blocks[i], time = brain.elapsed;
        // All source positions are within the authored arm's reach. The block
        // stays on the bench until the palm arrives, then follows a short arc.
        start.copy(homes[i]); end.set(-1.55, 1.87 + i * .33, .43);
        const transfer = smooth(1.1, 2.6, time);
        block.position.copy(start);
        if (time > 1.1) { block.position.lerpVectors(start, end, transfer); block.position.y += Math.sin(transfer * Math.PI) * .15; }
        contact.copy(block.position); contact.x += .18;
        reachHand(robot, 0, contact, smooth(.20, .85, time) * (1 - smooth(2.85, 3.6, time)));
      }
    }
  };
}

const down = new THREE.Vector3(0, -1, 0), forward = new THREE.Vector3(0, 0, 1);
const target = new THREE.Vector3(), direction = new THREE.Vector3(), bend = new THREE.Vector3(), elbow = new THREE.Vector3();
const upper = new THREE.Quaternion(), lower = new THREE.Quaternion(), inverse = new THREE.Quaternion();
// Two-bone reach for authored workbench contacts; no arbitrary hand dragging.
export function reachHand(robot, index, worldTarget, weight) {
  if (weight <= 0) return;
  const arm = robot.arms[index]; robot.root.updateMatrixWorld(true);
  target.copy(worldTarget); arm.shoulder.parent.worldToLocal(target); target.sub(arm.shoulder.position);
  const a = .53, b = .51, distance = Math.min(a + b - .025, Math.max(.08, target.length()));
  direction.copy(target).normalize();
  bend.copy(forward).addScaledVector(direction, -direction.dot(forward)).normalize();
  const along = (a * a - b * b + distance * distance) / (2 * distance);
  elbow.copy(direction).multiplyScalar(along).addScaledVector(bend, Math.sqrt(Math.max(0, a * a - along * along)));
  upper.setFromUnitVectors(down, vector.copy(elbow).normalize());
  inverse.copy(upper).invert();
  lower.setFromUnitVectors(down, target.copy(direction).multiplyScalar(distance).sub(elbow).applyQuaternion(inverse).normalize());
  arm.shoulder.quaternion.slerp(upper, weight); arm.elbow.quaternion.slerp(lower, weight);
  robot.root.updateMatrixWorld(true);
}
