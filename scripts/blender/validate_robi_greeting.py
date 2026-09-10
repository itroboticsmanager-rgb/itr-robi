import bpy,math,json
from pathlib import Path
from mathutils.bvhtree import BVHTree
s=bpy.context.scene;r=bpy.data.objects['ROBI_SPORT_RIG']
report={'errors':[],'frames':180,'fps':30,'max_joint_step_degrees':0.,'collision_frames':[]}
def bvh(name):
    obj=bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get()); mesh=obj.to_mesh()
    result=BVHTree.FromPolygons([obj.matrix_world@v.co for v in mesh.vertices],[list(p.vertices) for p in mesh.polygons])
    obj.to_mesh_clear();return result
previous={}; neutral=None; foot=None
for f in range(1,182):
    s.frame_set(f)
    current={b.name:b.rotation_quaternion.copy() for b in r.pose.bones}
    if f==1:
        neutral=current
        foot={name:r.pose.bones[name].matrix.copy() for name in ['foot.L','foot.R']}
    for name,q in current.items():
        if not all(math.isfinite(x) for x in q): report['errors'].append('Nonfinite quaternion')
        if name in previous:
            angle=math.degrees(q.rotation_difference(previous[name]).angle)
            angle=min(angle,360-angle)
            report['max_joint_step_degrees']=max(report['max_joint_step_degrees'],angle)
    for name,m in foot.items():
        if max(abs(m[i][j]-r.pose.bones[name].matrix[i][j]) for i in range(4) for j in range(4))>1e-5:
            report['errors'].append('Foot moved at '+str(f))
    if f in [35,50,65,80,92,103,114,126,145]:
        h=bvh('Head • soft blue housing')
        for name in ['Hand • glove.L','Arm • blue flexible sleeve.L']:
            if h.overlap(bvh(name)): report['collision_frames'].append([f,name])
    if f in [16,86,135]:
        mat=bpy.data.materials['Sport / animated screen']
        for prop in ['smile','blink_L','blink_R']:
            actual=mat.node_tree.nodes['Control / '+prop].outputs[0].default_value
            if abs(actual-r[prop])>1e-5: report['errors'].append('Screen mismatch '+prop+' at '+str(f))
    previous=current
report['returns_to_neutral']=all(abs(abs(q.dot(neutral[name]))-1)<1e-5 for name,q in current.items())
if report['collision_frames']: report['errors'].append('Head/arm intersections')
if report['max_joint_step_degrees']>12: report['errors'].append('Abrupt joint step')
if not report['returns_to_neutral']: report['errors'].append('End pose differs from neutral')
s.frame_set(1)
path=Path(__file__).resolve().parents[2]/'out/robi-greeting/validation.json'
path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2),flush=True)
