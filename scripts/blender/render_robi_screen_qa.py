"""Render changed expression and grazing profile; restore neutral state."""
import bpy
from pathlib import Path
from mathutils import Vector
out=Path(__file__).resolve().parents[2]/'out'/'robi-sport'
s=bpy.context.scene; r=bpy.data.objects['ROBI_SPORT_RIG']; camera=s.camera
s.cycles.samples=24; s.render.resolution_percentage=50
cam=bpy.data.objects['Camera • FaceDetail']; loc=cam.location.copy(); rot=cam.rotation_euler.copy()
try:
    s.camera=cam
    r['blink_L']=1.; r['look_x']=-.7; r['look_z']=.4
    r.update_tag(refresh={'OBJECT'}); s.frame_set(1); bpy.context.view_layer.update()
    s.render.filepath=str(out/'screen-qa-wink.png'); bpy.ops.render.render(write_still=True)
    for p in ['blink_L','blink_R','look_x','look_z']: r[p]=0.
    r.update_tag(refresh={'OBJECT'}); s.frame_set(1); bpy.context.view_layer.update()
    cam.location=(11,-3,3.6); cam.rotation_euler=(Vector((0,0,3.55))-cam.location).to_track_quat('-Z','Y').to_euler()
    s.render.filepath=str(out/'screen-qa-profile.png'); bpy.ops.render.render(write_still=True)
finally:
    for p in ['blink_L','blink_R','look_x','look_z']: r[p]=0.
    cam.location=loc; cam.rotation_euler=rot; s.camera=camera
    r.update_tag(refresh={'OBJECT'}); s.frame_set(1); bpy.context.view_layer.update()
print('SCREEN_QA_RENDER_COMPLETE',flush=True)
