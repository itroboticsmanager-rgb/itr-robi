import * as THREE from 'three';
import { MarchingCubes } from 'three/addons/objects/MarchingCubes.js';

// Smooth constructive surfaces are polygonized once, never in the frame loop.
export const blend = (a, b, k) => { const h = Math.max(k - Math.abs(a - b), 0) / k; return Math.min(a, b) - h * h * k * .25; };
export function rounded(x, y, z, hx, hy, hz, r) {
  const a = Math.abs(x) - hx + r, b = Math.abs(y) - hy + r, c = Math.abs(z) - hz + r;
  return Math.hypot(Math.max(a, 0), Math.max(b, 0), Math.max(c, 0)) + Math.min(Math.max(a, b, c), 0) - r;
}
export function ellipsoid(x, y, z, a, b, c) {
  const k0 = Math.hypot(x / a, y / b, z / c);
  const k1 = Math.hypot(x / (a * a), y / (b * b), z / (c * c));
  return k1 > 1e-9 ? k0 * (k0 - 1) / k1 : -Math.min(a, b, c);
}
export function segment(x, y, z, a, b, r) {
  const px = x - a[0], py = y - a[1], pz = z - a[2];
  const dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
  const t = Math.max(0, Math.min(1, (px * dx + py * dy + pz * dz) / (dx * dx + dy * dy + dz * dz)));
  return Math.hypot(px - t * dx, py - t * dy, pz - t * dz) - r;
}
export function sculpt(field, bounds, resolution = 48) {
  const tempMaterial = new THREE.MeshBasicMaterial();
  const mc = new MarchingCubes(resolution, tempMaterial, false, false, 60000);
  mc.isolation = 0;
  const [min, max] = bounds;
  const scale = max.map((v, i) => (v - min[i]) / 2);
  const center = max.map((v, i) => (v + min[i]) / 2);
  for (let z = 0; z < resolution; z++) for (let y = 0; y < resolution; y++) for (let x = 0; x < resolution; x++) {
    mc.field[x + y * resolution + z * resolution * resolution] = -field(
      center[0] + (x / resolution * 2 - 1) * scale[0],
      center[1] + (y / resolution * 2 - 1) * scale[1],
      center[2] + (z / resolution * 2 - 1) * scale[2]);
  }
  mc.update();
  if (mc.count >= 60000 * 3) throw new Error('Sculpt polygon budget exceeded');
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(mc.positionArray.slice(0, mc.count * 3), 3));
  geo.setAttribute('normal', new THREE.BufferAttribute(mc.normalArray.slice(0, mc.count * 3), 3));
  geo.scale(...scale); geo.translate(...center); geo.normalizeNormals();
  geo.computeBoundingBox(); geo.computeBoundingSphere();
  mc.geometry.dispose(); tempMaterial.dispose();
  return geo;
}

export function skin(geometry, weights) {
  const p = geometry.getAttribute('position');
  const indices = new Uint16Array(p.count * 4), values = new Float32Array(p.count * 4);
  for (let i = 0; i < p.count; i++) {
    const influences = weights(p.getX(i), p.getY(i), p.getZ(i));
    influences.forEach(([bone, weight], j) => { indices[i * 4 + j] = bone; values[i * 4 + j] = weight; });
  }
  geometry.setAttribute('skinIndex', new THREE.BufferAttribute(indices, 4));
  geometry.setAttribute('skinWeight', new THREE.BufferAttribute(values, 4));
  return geometry;
}

export function tubeGeometry() {
  const rings = 24, sides = 16, positions = new Float32Array((rings + 1) * (sides + 1) * 3), indices = [];
  for (let j = 0; j < rings; j++) for (let i = 0; i < sides; i++) {
    const a = j * (sides + 1) + i, b = a + sides + 1;
    indices.push(a, a + 1, b, b, a + 1, b + 1);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(positions, 3).setUsage(THREE.DynamicDrawUsage));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(positions.length), 3).setUsage(THREE.DynamicDrawUsage));
  g.setIndex(indices); g.userData = { rings, sides };
  return g;
}
const above = new THREE.Vector3(), below = new THREE.Vector3(), tangent = new THREE.Vector3(), cross = new THREE.Vector3(), up = new THREE.Vector3(1, 0, 0), normal = new THREE.Vector3(), c = new THREE.Vector3();
// Thigh and shin stay straight and only a short fillet rounds the knee itself.
// One quadratic across all three points instead left the whole limb as a single
// arc: it departed the hip some 17 degrees steeper than the thigh really points,
// which read as a backwards-curving shin and pushed the leg out through the
// shorts, whose cuff is skinned to the straight thigh bone.
const KNEE = .26;
export function bendTube(geo, start, middle, end) {
  const { rings, sides } = geo.userData, p = geo.getAttribute('position'), n = geo.getAttribute('normal');
  above.lerpVectors(start, middle, 1 - KNEE); below.lerpVectors(middle, end, KNEE);
  const enter = (1 - KNEE) / 2, leave = (1 + KNEE) / 2;
  for (let j = 0; j <= rings; j++) {
    const t = j / rings;
    if (t <= enter) { c.lerpVectors(start, middle, t * 2); tangent.subVectors(middle, start); }
    else if (t >= leave) { c.lerpVectors(middle, end, t * 2 - 1); tangent.subVectors(end, middle); }
    else {
      // Quadratic fillet, tangent to both limbs where it meets them.
      const w = (t - enter) / KNEE, v = 1 - w;
      c.copy(above).multiplyScalar(v * v).addScaledVector(middle, 2 * v * w).addScaledVector(below, w * w);
      tangent.subVectors(middle, above).multiplyScalar(v).addScaledVector(below, w).addScaledVector(middle, -w);
    }
    tangent.normalize();
    cross.crossVectors(tangent, up).normalize();
    normal.crossVectors(cross, tangent).normalize();
    const radius = .147 - .045 * t;
    for (let i = 0; i <= sides; i++) {
      const angle = i / sides * Math.PI * 2, a = Math.cos(angle), b = Math.sin(angle), index = j * (sides + 1) + i;
      const nx = normal.x * a + cross.x * b, ny = normal.y * a + cross.y * b, nz = normal.z * a + cross.z * b;
      p.setXYZ(index, c.x + radius * nx, c.y + radius * ny, c.z + radius * nz); n.setXYZ(index, nx, ny, nz);
    }
  }
  p.needsUpdate = n.needsUpdate = true;
}
