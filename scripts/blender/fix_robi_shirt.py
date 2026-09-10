"""Fit shirt stitching to actual fabric and keep it attached during posing."""
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from pathlib import Path


def fit_shirt_trims():
    shirt=bpy.data.objects['Shirt • continuous yellow fabric']
    rig=bpy.data.objects['ROBI_SPORT_RIG']
    evaluated=shirt.evaluated_get(bpy.context.evaluated_depsgraph_get())
    surface=evaluated.to_mesh()
    points=[evaluated.matrix_world@v.co for v in surface.vertices]
    bvh=BVHTree.FromPolygons(points,[list(p.vertices) for p in surface.polygons])
    kd=KDTree(len(points))
    for i,p in enumerate(points): kd.insert(p,i)
    kd.balance()
    group_names={g.index:g.name for g in shirt.vertex_groups}
    changed=[]
    for obj in list(bpy.data.objects):
        if not obj.name.startswith(('Shirt • side stitch','Shirt • sleeve seam')): continue
        if obj.get('fabric_attached'): continue
        closed='sleeve seam' in obj.name
        sides=10 if closed else 8
        centers=[sum((obj.matrix_world@v.co for v in obj.data.vertices[i:i+sides]),Vector())/sides
                 for i in range(0,len(obj.data.vertices),sides)]
        fitted=[bvh.find_nearest(p)[0] for p in centers]
        verts=[]; weights=[]; faces=[]
        width=.010 if closed else .005
        for j,p in enumerate(fitted):
            before=fitted[(j-1)%len(fitted)] if closed else fitted[max(0,j-1)]
            after=fitted[(j+1)%len(fitted)] if closed else fitted[min(len(fitted)-1,j+1)]
            normal=bvh.find_nearest(p)[1]
            across=(after-before).normalized().cross(normal).normalized()
            for sign in [-1,1]:
                point,n,_,_=bvh.find_nearest(p+sign*width*.5*across)
                verts.append(obj.matrix_world.inverted()@(point+n*.0008))
                # The same deform groups as the surrounding fabric, followed by
                # a surface fit after posing, avoid a separate rigid trim motion.
                w={}; total=0.
                for _,index,distance in kd.find_n(point,3):
                    influence=1/max(distance,.00001); total+=influence
                    for g in surface.vertices[index].groups:
                        name=group_names[g.group]; w[name]=w.get(name,0)+influence*g.weight
                weights.append({name:value/total for name,value in w.items()})
        for j in range(len(fitted) if closed else len(fitted)-1):
            a=2*j; b=2*((j+1)%len(fitted)); faces.append((a,a+1,b+1,b))
        mesh=bpy.data.meshes.new(obj.name+' • fitted ribbon')
        mesh.from_pydata(verts,[],faces); mesh.update()
        for material in obj.data.materials: mesh.materials.append(material)
        obj.data=mesh
        obj.vertex_groups.clear(); groups={name:obj.vertex_groups.new(name=name) for name in group_names.values()}
        for i,w in enumerate(weights):
            for name,value in w.items():
                if value>0: groups[name].add([i],value,'REPLACE')
        obj.modifiers.clear()
        arm=obj.modifiers.new('Follow fabric skeleton','ARMATURE'); arm.object=rig; arm.use_deform_preserve_volume=True
        fit=obj.modifiers.new('Stay on shirt surface','SHRINKWRAP'); fit.target=shirt
        fit.wrap_method='NEAREST_SURFACEPOINT'; fit.wrap_mode='ON_SURFACE'; fit.offset=.0008
        shell=obj.modifiers.new('Fine stitching thickness','SOLIDIFY'); shell.thickness=.0016; shell.offset=0
        shell.use_even_offset=True
        for p in mesh.polygons: p.use_smooth=True
        obj['fabric_attached']=True; changed.append(obj.name)
    evaluated.to_mesh_clear()
    bpy.context.view_layer.update()
    return changed


if __name__=='__main__':
    print('FITTED_TRIMS',fit_shirt_trims())
    root=Path(__file__).resolve().parents[2]
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'assets/3d/robi_sport_neutral.blend'))
