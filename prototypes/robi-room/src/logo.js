import * as THREE from 'three';
import { SVGLoader } from 'three/addons/loaders/SVGLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import source from './logo.svg?raw';

// The exported sign carries its colours in a <style> block, which the SVG
// loader does not resolve, and its wheel rings are strokes, which cannot be
// extruded. Both are settled here so the loader only ever sees inline fills.
function readStylesheet(svg) {
  const block = /<style>([\s\S]*?)<\/style>/.exec(svg);
  const rules = {};
  if (!block) return rules;
  for (const [, selectors, body] of block[1].matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const declarations = {};
    for (const [, key, value] of body.matchAll(/([\w-]+)\s*:\s*([^;]+)/g)) declarations[key] = value.trim();
    for (const selector of selectors.split(',')) {
      const name = selector.trim().replace(/^\./, '');
      if (name) rules[name] = { ...rules[name], ...declarations };
    }
  }
  return rules;
}

function ring(cx, cy, outer, inner) {
  // Opposite windings so the loader reads the inner circle as a hole.
  const arc = (r, sweep) => `a${r},${r} 0 1,${sweep} ${2 * r},0a${r},${r} 0 1,${sweep} ${-2 * r},0`;
  return `M${cx - outer},${cy}${arc(outer, 0)}ZM${cx - inner},${cy}${arc(inner, 1)}Z`;
}

function inlineStyles(svg) {
  const rules = readStylesheet(svg);
  const circles = /<circle class="([\w-]+)"\s+cx="([\d.]+)"\s+cy="([\d.]+)"\s+r="([\d.]+)"\s*\/>/g;
  return svg.replace(circles, (whole, name, cx, cy, r) => {
    const rule = rules[name] ?? {};
    if (rule.fill && rule.fill !== 'none') return whole;
    const half = parseFloat(rule['stroke-width'] ?? 0) / 2;
    if (!half) return whole;
    return `<path fill="${rule.stroke}" d="${ring(+cx, +cy, +r + half, +r - half)}"/>`;
  }).replace(/class="([\w-]+)"/g, (whole, name) => {
    const fill = rules[name]?.fill;
    return fill ? `fill="${fill}"` : whole;
  });
}

// Each region retains the original SVG colours. Fine artwork is a shallow
// relief; only the large letters have substantial depth.
const WHEELS = [{ x: 475.73, y: 100.72 }, { x: 651.4, y: 100.72 }];
const WHITE = '#edf5ff', YELLOW = '#ffe21c';
const tint = new THREE.Color();
function isYellow(fill) {
  return tint.set(fill).getHSL({ h: 0, s: 0, l: 0 }).s > .4;
}
function region(box) {
  const at = box.getCenter(new THREE.Vector3());
  if (box.max.x < 195) return 'emblem';
  if (box.min.y > 140) return 'caption';
  if (box.max.y < 50 && box.min.x > 700) return 'mascot';
  const wheel = WHEELS.findIndex(w => Math.hypot(at.x-w.x,at.y-w.y)<38);
  if (wheel >= 0) return `wheel${wheel}`;
  return at.x < 340 ? 'it' : at.x < 440 ? 'r' : at.x < 610 ? 'b' : at.x < 754 ? 't' : at.x < 800 ? 'i' : at.x < 885 ? 'c' : 's';
}

export function createLogo({ width = 6 } = {}) {
  const paths = new SVGLoader().parse(inlineStyles(source)).paths;
  const regions = new Map();
  const clock = { value: 0 };
  function faceMaterial(color) {
    return new THREE.ShaderMaterial({
      uniforms: { ink: { value: new THREE.Color(color) }, clock },
      vertexShader: `varying vec2 art; void main(){art=position.xy; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
      fragmentShader: `varying vec2 art; uniform vec3 ink; uniform float clock;
        void main(){
          float scan=mod(clock,12.)*145.-220.;
          float glint=exp(-pow((art.x+art.y*.3-scan)/26.,2.))*.20;
          gl_FragColor=vec4(mix(ink,vec3(1.),glint),1.);
          #include <colorspace_fragment>
        }`,
    });
  }
  const materials = [faceMaterial(YELLOW), new THREE.MeshStandardMaterial({color:'#b88d07',roughness:.32,metalness:.35}),
    faceMaterial(WHITE), new THREE.MeshStandardMaterial({color:'#769abc',roughness:.38,metalness:.25})];
  for (const [layer,path] of paths.entries()) {
    const fill = path.userData?.style?.fill;
    if (!fill || fill === 'none') continue;
    const shapes = path.toShapes(); if (!shapes.length) continue;
    const flat = new THREE.ShapeGeometry(shapes, 18); flat.computeBoundingBox();
    const name = region(flat.boundingBox); flat.dispose();
    const fine = name === 'emblem' || name === 'caption' || name.startsWith('wheel') || name === 'mascot';
    const depth = name === 'caption' ? 1 : fine ? 1.8 : 10;
    const geo = new THREE.ExtrudeGeometry(shapes, {depth,curveSegments:18,steps:1,
      bevelEnabled:!fine,bevelThickness:.22,bevelSize:.22,bevelSegments:2});
    // Front faces share a reference plane; depth extends backwards. This keeps
    // narrow counters open instead of thickening every SVG line from the front.
    geo.translate(0,0,-depth + layer*.001);
    const colorOffset = isYellow(fill) ? 0 : 2;
    if (!regions.has(name)) regions.set(name,[]);
    regions.get(name).push({geo,colorOffset});
  }
  const group = new THREE.Group(), components = {}, wheels = [];
  for (const [name,parts] of regions) {
    const merged = mergeGeometries(parts.map(p=>p.geo));
    merged.clearGroups(); let offset=0;
    for (const {geo,colorOffset} of parts) {
      for (const g of geo.groups) merged.addGroup(offset+g.start,g.count,colorOffset+g.materialIndex);
      offset+=geo.attributes.position.count;
    }
    // Batch by material inside each moving region, rather than one draw per
    // tiny SVG path. Keep every original cap/side assignment.
    const ordered = [...merged.groups].sort((a,b)=>a.materialIndex-b.materialIndex);
    for (const attribute of Object.values(merged.attributes)) {
      const data = new attribute.array.constructor(attribute.array.length);
      let cursor=0;
      for (const g of ordered) {
        const from=g.start*attribute.itemSize, count=g.count*attribute.itemSize;
        data.set(attribute.array.subarray(from,from+count),cursor);cursor+=count;
      }
      attribute.array=data;
    }
    merged.clearGroups();let cursor=0;
    for (const materialIndex of [0,1,2,3]) {
      const count=ordered.filter(g=>g.materialIndex===materialIndex).reduce((sum,g)=>sum+g.count,0);
      if(count)merged.addGroup(cursor,count,materialIndex);cursor+=count;
    }
    merged.computeBoundingBox();
    const center=merged.boundingBox.getCenter(new THREE.Vector3()); center.z=0;
    if (name.startsWith('wheel')) {const w=WHEELS[Number(name.slice(-1))];center.set(w.x,w.y,0);}
    const pivot=new THREE.Group(); pivot.position.copy(center);
    // Keep original art coordinates in the shader for one continuous highlight.
    const mesh=new THREE.Mesh(merged,materials); mesh.position.copy(center).negate(); mesh.castShadow=true;
    pivot.add(mesh); group.add(pivot); components[name]={pivot,home:center.clone()};
    if(name.startsWith('wheel')) wheels.push(pivot);
    parts.forEach(p=>p.geo.dispose());
  }
  const box=new THREE.Box3().setFromObject(group), scale=width/box.getSize(new THREE.Vector3()).x;
  group.scale.set(scale,-scale,scale);
  const root=new THREE.Group();root.add(group);
  box.setFromObject(root);group.position.sub(box.getCenter(new THREE.Vector3()));
  root.userData={wheels,components,clock,materials,height:box.getSize(new THREE.Vector3()).y};
  return root;
}
