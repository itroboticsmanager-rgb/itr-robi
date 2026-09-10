import { smooth } from './motion.js';

// All motion returns to the original art. Caption never follows the letter wave.
export function logoMotion(t) {
  const waveTime = t % 12;
  const glyphs = ['it','r','b','t','i','c','s'].map((name,i) => {
    const phase = waveTime - 1.3 - i*.17;
    const lift = smooth(0,.65,phase) * (1-smooth(.85,1.65,phase));
    return {name,y:-5.5*lift,z:4*lift,tilt:.025*Math.sin(phase*3)*lift};
  });
  const notice = smooth(4.6,5.2,waveTime)*(1-smooth(6.2,7,waveTime));
  return {glyphs,wheels:[-t*.48,t*.48],emblem:Math.sin(t*.8)*.055,
    mascot:{y:-5*notice,tilt:Math.sin((waveTime-4.6)*3.2)*.14*notice}};
}
export function animateLogo(logo,t,flourishTime=t) {
  const {components,clock}=logo.userData, m=logoMotion(flourishTime), continuous=logoMotion(t); clock.value=flourishTime;
  for(const g of m.glyphs) {
    const c=components[g.name];if(!c)continue;
    c.pivot.position.copy(c.home);c.pivot.position.y+=g.y;c.pivot.position.z+=g.z;c.pivot.rotation.z=g.tilt;
  }
  for(const i of [0,1]) if(components[`wheel${i}`]) components[`wheel${i}`].pivot.rotation.z=continuous.wheels[i];
  if(components.emblem) components.emblem.pivot.rotation.z=continuous.emblem;
  if(components.mascot){const c=components.mascot;c.pivot.position.y=c.home.y+m.mascot.y;c.pivot.rotation.z=m.mascot.tilt;}
}
