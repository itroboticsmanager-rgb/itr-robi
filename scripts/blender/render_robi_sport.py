import bpy,sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]/'out'/'robi-sport'; OUT.mkdir(exist_ok=True)
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else ['Front','ThreeQuarter']
draft='--draft' in args; args=[a for a in args if a!='--draft']
s=bpy.context.scene; s.cycles.device='CPU'; s.cycles.samples=24 if draft else 64
s.render.resolution_percentage=50 if draft else 75
for name in args:
    s.camera=bpy.data.objects['Camera • '+name]
    s.render.filepath=str(OUT/('review-'+name+'.png'))
    bpy.ops.render.render(write_still=True)
print('SPORT_RENDERS_COMPLETE',flush=True)
