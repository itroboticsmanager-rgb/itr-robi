"""Render still-pose checks or the full greeting to lossless PNG frames."""
import bpy,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[2]; out=root/'out/robi-greeting'; out.mkdir(parents=True,exist_ok=True)
s=bpy.context.scene; s.render.engine='BLENDER_EEVEE'
args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
s.render.image_settings.file_format='PNG'; s.render.image_settings.color_mode='RGB'
s.render.resolution_percentage=100
if '--animation' in args:
    s.render.resolution_x=960; s.render.resolution_y=960; s.eevee.taa_render_samples=32
    folder=out/'frames'; folder.mkdir(exist_ok=True)
    for f in range(1,181):
        path=folder/f'frame_{f:04d}.png'
        if path.exists(): continue
        s.frame_set(f); s.render.filepath=str(path); bpy.ops.render.render(write_still=True)
        print('GREETING_FRAME',f,flush=True)
else:
    s.render.resolution_x=720; s.render.resolution_y=720; s.eevee.taa_render_samples=16
    frames=[int(v) for v in args if v.isdigit()] or [1,68,86,102,148]
    for f in frames:
        s.frame_set(f); s.render.filepath=str(out/f'pose-{f:03d}.png')
        bpy.ops.render.render(write_still=True)
        print('GREETING_POSE',f,flush=True)
