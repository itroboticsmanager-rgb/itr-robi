"""Close review of shirt seams on the saved neutral character."""
import bpy
from pathlib import Path
from mathutils import Vector
out=Path(__file__).resolve().parents[2]/'out'/'robi-sport'
scene=bpy.context.scene
camera=bpy.data.objects['Camera • ThreeQuarter'].copy()
camera.data=camera.data.copy(); scene.collection.objects.link(camera)
camera.name='Camera • ShirtDetail'
camera.location=(4,-10,3.3)
camera.rotation_euler=(Vector((0,0,2.0))-camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.ortho_scale=2.25
scene.camera=camera; scene.cycles.device='CPU'; scene.cycles.samples=32
scene.render.resolution_percentage=50
scene.render.filepath=str(out/'review-ShirtDetail.png')
bpy.ops.render.render(write_still=True)
print('SHIRT_REVIEW_COMPLETE',flush=True)
