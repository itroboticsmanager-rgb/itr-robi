"""Checks topology, rig weights, independent motion, gaze and blink drivers."""
import bpy,bmesh,json,math
from pathlib import Path
r=bpy.data.objects['ROBI_SPORT_RIG']
objs=[o for o in bpy.data.collections['ROBI | Character'].objects if o.type=='MESH']
report={'meshes':len(objs),'bones':len(r.data.bones),'base_vertices':sum(len(o.data.vertices) for o in objs),'errors':[]}
for o in objs:
    if not any(m.type=='ARMATURE' and m.object==r for m in o.modifiers): report['errors'].append(o.name+': no rig')
    if any(abs(sum(g.weight for g in v.groups)-1)>1e-4 for v in o.data.vertices): report['errors'].append(o.name+': unnormalized weights')
    if any(not math.isfinite(x) for v in o.data.vertices for x in v.co): report['errors'].append(o.name+': nonfinite coordinates')
    bm=bmesh.new()
    if any(m.type=='SOLIDIFY' for m in o.modifiers):
        eo=o.evaluated_get(bpy.context.evaluated_depsgraph_get()); em=eo.to_mesh(); bm.from_mesh(em); eo.to_mesh_clear()
    else: bm.from_mesh(o.data)
    if any(not e.is_manifold for e in bm.edges): report['errors'].append(o.name+': open/nonmanifold surface')
    bm.free()

def bounds(name):
    o=bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get()); m=o.to_mesh()
    p=[o.matrix_world@v.co for v in m.vertices]; o.to_mesh_clear()
    return [min(v[i] for v in p) for i in range(3)]+[max(v[i] for v in p) for i in range(3)]
def update(): r.update_tag(refresh={'OBJECT'}); bpy.context.view_layer.update(); bpy.context.scene.frame_set(1)

for bone,obj,axis,angle in [('head','Head • soft blue housing',2,.23),('upper_arm.L','Hand • glove.L',2,.4),('shin.R','Sneaker • blue upper.R',0,.35),('finger_2.L','Hand • glove.L',0,.5)]:
    before=bounds(obj); r.pose.bones[bone].rotation_euler[axis]=angle; update(); after=bounds(obj)
    report[bone+'_movement']=max(abs(a-b) for a,b in zip(before,after))
    if report[bone+'_movement']<.005: report['errors'].append(bone+': no visible deformation')
    r.pose.bones[bone].rotation_euler=(0,0,0); update()
if 'Sport / animated screen' in bpy.data.materials:
    mat=bpy.data.materials['Sport / animated screen']
    panel=bpy.data.objects['Face • integrated display']
    report['face_is_surface_graphics']=not any(o.name.startswith(('Eye •','Mouth •')) for o in objs)
    if not report['face_is_surface_graphics']: report['errors'].append('Detached face geometry remains')
    report['screen_uv_loops']=len(panel.data.uv_layers['ScreenUV'].data)
    for prop in ['blink_L','blink_R','look_x','look_z','smile']:
        values=[]
        for value in ([0.,.5,1.] if prop.startswith('blink') or prop=='smile' else [-1.,0.,1.]):
            r[prop]=value; update()
            actual=mat.node_tree.nodes['Control / '+prop].outputs[0].default_value
            values.append(actual)
            if abs(actual-value)>1e-6: report['errors'].append(prop+': shader driver failed')
        report[prop+'_shader_values']=values
        r[prop]=0.; update()
    report['neutral_mouth']=r['smile']==0.
else:
    for side in ['L','R']:
        a=bounds('Eye • white.'+side); r['blink_'+side]=1.; update(); b=bounds('Eye • white.'+side)
        report['blink_'+side+'_ratio']=(b[5]-b[2])/(a[5]-a[2])
        if report['blink_'+side+'_ratio']>.05: report['errors'].append('Blink '+side+' failed')
        r['blink_'+side]=0.; update()
    for prop,axis,expected in [('look_x',0,.056),('look_z',2,.044)]:
        a=bounds('Eye • pupil.L'); r[prop]=.8; update(); b=bounds('Eye • pupil.L')
        report[prop+'_movement']=b[axis]-a[axis]
        if abs(report[prop+'_movement']-expected)>1e-4: report['errors'].append(prop+' failed')
        r[prop]=0.; update()
report['neutral_pose']=all(abs(a)<1e-6 for b in r.pose.bones for a in b.rotation_euler)
if r.get('natural_hand_rest'):
    for side in ['L','R']:
        hand=r.data.bones['hand.'+side]; forearm=r.data.bones['forearm.'+side]
        axis=(forearm.tail_local-forearm.head_local).normalized()
        alignment=axis.dot((hand.tail_local-hand.head_local).normalized())
        thumb=r.data.bones['thumb.'+side].head_local-hand.tail_local
        forward=(thumb-axis*thumb.dot(axis)).normalized()
        report['wrist_alignment_'+side]=alignment
        report['thumb_forward_'+side]=forward.y
        if alignment<.995 or forward.y>-.98: report['errors'].append('Unnatural hand rest: '+side)
report['lowest_point']=min(bounds(o.name)[2] for o in objs)
report['no_active_action']=not r.animation_data or not r.animation_data.action
out=Path(__file__).resolve().parents[2]/'out'/'robi-sport'/'validation.json'
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
