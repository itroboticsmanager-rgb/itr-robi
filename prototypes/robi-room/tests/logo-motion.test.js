import test from 'node:test';
import assert from 'node:assert/strict';
import { logoMotion } from '../src/logo-motion.js';

test('letter flourish closes without position or velocity discontinuity', () => {
  const a=logoMotion(12-1e-5),b=logoMotion(12+1e-5);
  for(let i=0;i<a.glyphs.length;i++) {
    assert.ok(Math.abs(a.glyphs[i].y)<1e-9);assert.ok(Math.abs(b.glyphs[i].y)<1e-9);
    assert.equal(a.glyphs[i].z,0);assert.equal(b.glyphs[i].z,0);
  }
  assert.ok(Math.abs(a.mascot.tilt-b.mascot.tilt)<1e-6);
});
test('the caption is stationary, and moving letters remain bounded and finite', () => {
  for(let t=0;t<36;t+=1/120) {
    const m=logoMotion(t);
    assert.ok(!m.glyphs.some(g=>g.name==='caption'));
    for(const g of m.glyphs){assert.ok(g.y>=-5.5-1e-9&&g.y<=1e-9);assert.ok(g.z>=-1e-9&&g.z<=4+1e-9);assert.ok(Number.isFinite(g.tilt));}
    assert.ok(Math.abs(m.emblem)<=.055);
  }
});
test('wheels rotate continuously through the flourish boundary', () => {
  const a=logoMotion(11.9999),b=logoMotion(12.0001);
  for(const i of [0,1])assert.ok(Math.abs(a.wheels[i]-b.wheels[i])<.001);
});
