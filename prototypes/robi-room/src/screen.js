import * as THREE from 'three';

// Everything expressive is emitted by one flat screen. No eyeball/mouth meshes.
export function createScreen() {
  const material = new THREE.ShaderMaterial({
    uniforms: { look: { value: new THREE.Vector2() }, blink: { value: 0 }, smile: { value: 0 }, surprise: { value: 0 }, curiosity: { value: 0 }, screenTop: { value: new THREE.Color('#8ad4ff') }, screenBottom: { value: new THREE.Color('#65b6f4') }, faceInk: { value: new THREE.Color('#08418d') } },
    vertexShader: `varying vec2 screenUV;
      void main(){ screenUV = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`,
    fragmentShader: `
      varying vec2 screenUV;
      uniform vec2 look;
      uniform float blink, smile, surprise, curiosity;
      uniform vec3 screenTop, screenBottom, faceInk;
      void main(){
        vec2 resolution=vec2(96.,64.);
        vec2 p=(floor(screenUV*resolution)+.5)/resolution;
        vec3 background=mix(screenBottom,screenTop,screenUV.y);
        vec3 color=background;
        for(int i=0;i<2;i++){
          float side=float(i)*2.-1.;
          vec2 centre=vec2(.5+side*.225,.59+side*.020*curiosity);
          float openness=max(.025,1.-blink);
          float height=(.238+surprise*.016+side*.015*curiosity-smile*.018)*openness;
          vec2 local=p-centre;
          float eye=1.-smoothstep(.98,1.02,length(local/vec2(.170,height)));
          vec2 pupilOffset=look*vec2(.048,.045)+vec2(-side*.009,.014);
          vec2 pupilLocal=local-vec2(pupilOffset.x,pupilOffset.y*openness);
          float pupil=1.-smoothstep(.98,1.02,length(pupilLocal/vec2(.095,.140*openness)));
          float highlight=1.-smoothstep(.95,1.05,length((pupilLocal-vec2(-.031,.046*openness))/vec2(.030,.044*openness)));
          float glint=1.-smoothstep(.90,1.10,length((pupilLocal-vec2(.035,-.052*openness))/vec2(.012,.018*openness)));
          vec3 eyeColor=mix(vec3(.91,.96,1.),vec3(.003,.010,.025),pupil);
          eyeColor=mix(eyeColor,vec3(1.),highlight*pupil);
          eyeColor=mix(eyeColor,vec3(.33,.54,.72),glint*pupil);
          // The lid closes the complete eye, including pupil and reflections.
          color=mix(color,eyeColor,eye*smoothstep(.08,.25,openness));
          float lid=1.-smoothstep(.008,.017,abs(local.y));
          lid*=1.-smoothstep(.11,.14,abs(local.x));
          color=mix(color,faceInk,lid*(1.-smoothstep(.08,.25,openness)));
        }
        float neutralY=.265;
        float x=p.x-.5;
        float smileCurve=neutralY + smile * (.75*x*x - .012) * 8.;
        float mouth=max(abs(p.y-smileCurve)-.011,abs(x)-mix(.063,.112,smile));
        float oh=(length((p-vec2(.5,.25))/vec2(.043,.063))-1.)*.043;
        float ink=mix(1.-smoothstep(-.003,.003,mouth),1.-smoothstep(-.003,.003,oh),smoothstep(.08,.60,surprise));
        color=mix(color,faceInk,ink);
        vec2 cell=fract(screenUV*resolution);
        float pixelAA=max(fwidth(screenUV.x)*resolution.x,fwidth(screenUV.y)*resolution.y);
        float led=smoothstep(.07-pixelAA*.5,.07+pixelAA*.5,min(min(cell.x,1.-cell.x),min(cell.y,1.-cell.y)));
        float gridStrength=1.-smoothstep(.20,.55,pixelAA);
        color=mix(background,color,mix(1.,mix(.88,1.,led),gridStrength));
        // Quiet glass reflection, confined to the physical display.
        float reflection=smoothstep(.77,.82,screenUV.x*.35+screenUV.y)*.012;
        color+=vec3(reflection);
        gl_FragColor=vec4(color,1.);
        #include <colorspace_fragment>
      }`,
  });
  material.toneMapped = false;
  return material;
}
export function updateScreen(material, p) {
  material.uniforms.look.value.set(p.lookX, p.lookY);
  for (const name of ['blink', 'smile', 'surprise', 'curiosity']) material.uniforms[name].value = p[name] ?? 0;
}
