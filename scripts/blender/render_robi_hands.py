"""Neutral wrist and thumb orientation review from a three-quarter angle."""
import bpy
from pathlib import Path
from mathutils import Vector
out=Path(__file__).resolve().parents[2]/'out'/'robi-sport'
scene=bpy.context.scene
camera=bpy.data.objects['Camera • ThreeQuarter'].copy(); camera.data=camera.data.copy()
scene.collection.objects.link(camera); camera.name='Camera • HandsDetail'
camera.location=(4,-10,3.2)
camera.rotation_euler=(Vector((0,-.03,1.8))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.ortho_scale=3.7; scene.camera=camera
scene.cycles.device='CPU'; scene.cycles.samples=24; scene.render.resolution_percentage=50
scene.render.filepath=str(out/'review-HandsDetail.png')
bpy.ops.render.render(write_still=True)
print('HAND_REVIEW_COMPLETE',flush=True)
