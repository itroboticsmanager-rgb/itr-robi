"""Render the saved neutral asset, without modifying its geometry."""
import bpy
import sys
from pathlib import Path

OUT=Path(__file__).resolve().parents[2]/'out'/'robi-polished'
OUT.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else ['ThreeQuarter']
draft='--draft' in args
args=[a for a in args if a!='--draft']
scene.cycles.samples=24 if draft else 64
scene.render.resolution_percentage=50 if draft else 75
scene.cycles.device='CPU'
for name in args:
    rig=bpy.data.objects['ROBI_RIG']
    if name in ['Greeting','Blink']:
        rig.animation_data.action=bpy.data.actions['ROBI • Greeting check (72 frames)']
        scene.frame_set(24 if name=='Greeting' else 16)
        scene.camera=bpy.data.objects['Camera • ThreeQuarter']
    else:
        rig.animation_data.action=None
        for pb in rig.pose.bones: pb.rotation_euler=(0,0,0)
        for prop in ['look_x','look_z','blink_L','blink_R']: rig[prop]=0.
        rig.update_tag(refresh={'OBJECT'}); scene.frame_set(1)
        scene.camera=bpy.data.objects['Camera • '+name]
    scene.render.filepath=str(OUT/('review-'+name+'.png'))
    bpy.ops.render.render(write_still=True)
print('REVIEW_RENDER_COMPLETE',flush=True)
