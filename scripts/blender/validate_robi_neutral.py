"""Geometry, weights, drivers and FK motion checks. Rest pose restored after checks."""
import bpy, bmesh, json, math
from pathlib import Path
from mathutils import Vector
rig=bpy.data.objects['ROBI_RIG']
objects=[o for o in bpy.data.collections['ROBI | Character'].objects if o.type=='MESH']
report={'meshes':len(objects),'bones':len(rig.data.bones),'vertices':sum(len(o.data.vertices) for o in objects),'errors':[]}
for obj in objects:
    if not any(m.type=='ARMATURE' and m.object==rig for m in obj.modifiers): report['errors'].append(obj.name+': no rig')
    for v in obj.data.vertices:
        if not all(math.isfinite(c) for c in v.co): report['errors'].append(obj.name+': nonfinite vertex'); break
        if abs(sum(g.weight for g in v.groups)-1)>1e-4: report['errors'].append(obj.name+': nonnormalized weights'); break
    bm=bmesh.new(); bm.from_mesh(obj.data)
    if any(not e.is_manifold for e in bm.edges): report['errors'].append(obj.name+': nonmanifold edges')
    bm.free()

def extent(name):
    deps=bpy.context.evaluated_depsgraph_get(); obj=bpy.data.objects[name].evaluated_get(deps)
    m=obj.to_mesh(); coords=[obj.matrix_world@v.co for v in m.vertices]
    obj.to_mesh_clear()
    return [min(v[i] for v in coords) for i in range(3)],[max(v[i] for v in coords) for i in range(3)]

def update():
    rig.update_tag(refresh={'OBJECT'})
    bpy.context.view_layer.update()
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)

before=extent('Hand • seamless glove.L')
rig.pose.bones['upper_arm.L'].rotation_euler[2]=.35
update()
after=extent('Hand • seamless glove.L')
report['arm_moves_hand']=max(abs(before[0][i]-after[0][i]) for i in range(3))>.10
rig.pose.bones['upper_arm.L'].rotation_euler=(0,0,0)
update()
before=extent('Foot • soft boot.R')
rig.pose.bones['shin.R'].rotation_euler[0]=.4
update()
after=extent('Foot • soft boot.R')
report['shin_moves_foot']=max(abs(before[0][i]-after[0][i]) for i in range(3))>.04
rig.pose.bones['shin.R'].rotation_euler=(0,0,0)
update()
before=extent('Hand • seamless glove.R')
rig.pose.bones['finger_2.R'].rotation_euler[0]=.6
update()
after=extent('Hand • seamless glove.R')
report['finger_deforms_glove']=max(abs(before[0][i]-after[0][i]) for i in range(3))>.005
rig.pose.bones['finger_2.R'].rotation_euler=(0,0,0)
update()
for side in ['L','R']:
    name='Eye • white.'+side
    a,b=extent(name); height=b[2]-a[2]
    rig['blink_'+side]=1.; update()
    a,b=extent(name)
    report['blink_'+side+'_ratio']=(b[2]-a[2])/height
    if report['blink_'+side+'_ratio']>.10: report['errors'].append('Blink driver failed '+side)
    rig['blink_'+side]=0.; update()
for prop in ['look_x','look_z']:
    a,b=extent('Eye • pupil.L')
    rig[prop]=.8; update()
    c,d=extent('Eye • pupil.L'); axis=0 if prop=='look_x' else 2
    report[prop+'_displacement']=c[axis]-a[axis]
    expected=.0704 if prop=='look_x' else .052
    if abs(c[axis]-a[axis]-expected)>1e-4: report['errors'].append('Gaze driver failed '+prop)
    if any(abs(c[i]-a[i])>1e-4 for i in range(3) if i!=axis): report['errors'].append('Gaze affects unrelated axis '+prop)
    rig[prop]=0.; update()
report['rest_pose']=all(abs(a)<1e-7 for p in rig.pose.bones for a in p.rotation_euler)
report['lowest_character_point']=min(extent(o.name)[0][2] for o in objects)
action=bpy.data.actions.get('ROBI • Greeting check (72 frames)')
if action:
    rig.animation_data.action=action
    bpy.context.scene.frame_set(24)
    report['greeting_clip_moves_arm']=abs(rig.pose.bones['upper_arm.L'].rotation_euler.z)>.8
    bpy.context.scene.frame_set(16)
    report['greeting_clip_blinks']=rig['blink_L']>.99 and rig['blink_R']>.99
    bpy.context.scene.frame_set(72)
    report['greeting_returns_neutral']=all(abs(a)<1e-6 for pb in rig.pose.bones for a in pb.rotation_euler) and abs(rig['look_x'])<1e-6
    rig.animation_data.action=None
    for pb in rig.pose.bones: pb.rotation_euler=(0,0,0)
    for prop in ['blink_L','blink_R','look_x','look_z']: rig[prop]=0.
    bpy.context.scene.frame_set(1); update()
    for check in ['greeting_clip_moves_arm','greeting_clip_blinks','greeting_returns_neutral']:
        if not report[check]: report['errors'].append(check+' failed')
if not report['arm_moves_hand']: report['errors'].append('Arm FK does not move glove')
if not report['shin_moves_foot']: report['errors'].append('Shin FK does not move foot')
if not report['finger_deforms_glove']: report['errors'].append('Finger FK does not deform glove')
if not report['rest_pose']: report['errors'].append('Not in rest pose')
out=Path(__file__).resolve().parents[2]/'out'/'robi-polished'/'validation.json'
out.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(report,indent=2,ensure_ascii=False))
