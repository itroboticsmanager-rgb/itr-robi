"""Fresh ROBI character, neutral rest pose, animation rig and review studio.

Blender 5.x: blender --background --python scripts/blender/build_robi_neutral.py
Coordinates: metres, Z up, face towards -Y. No previous model is imported.
"""
import bpy
import math
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'out' / 'robi-polished'
DEST = ROOT / 'assets' / '3d' / 'robi_neutral.blend'
OUT.mkdir(parents=True, exist_ok=True)
DEST.parent.mkdir(parents=True, exist_ok=True)


def material(name, hexcode, rough=.35, coat=.18):
    rgb = [int(hexcode[i:i+2],16)/255 for i in (0,2,4)]
    rgb = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb,1)
    m.use_nodes = True
    n = m.node_tree.nodes.get('Principled BSDF')
    n.inputs['Base Color'].default_value = (*rgb,1)
    n.inputs['Roughness'].default_value = rough
    n.inputs['Coat Weight'].default_value = coat
    n.inputs['Coat Roughness'].default_value = .22
    n.inputs['Specular IOR Level'].default_value = .25
    return m


def move(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def finish(obj, name, mat, coll=None):
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    if obj.type == 'MESH':
        for p in obj.data.polygons:
            p.use_smooth = True
    move(obj, coll or geo)
    return obj


def mesh(name, verts, faces, mat):
    m = bpy.data.meshes.new(name + '.Mesh')
    m.from_pydata(verts, [], faces)
    m.update()
    o = bpy.data.objects.new(name, m)
    geo.objects.link(o)
    finish(o,name,mat)
    # Recalculate winding consistently, including end caps.
    bpy.context.view_layer.objects.active=o
    o.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    o.select_set(False)
    return o


def ellipsoid(name, loc, scale, mat, segments=48, rings=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=loc)
    o = bpy.context.object
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o,name,mat)


def rr_points(w,h,r,steps=16):
    points=[]
    for cx,cz,a0 in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for k in range(steps+1):
            a=math.radians(a0+90*k/steps)
            points.append((cx+r*math.cos(a),cz+r*math.sin(a)))
    return points


def rounded_shell(name, loc, w,h,d,r, edge, mat):
    # Rounded rectangle rings give a broad face, round outline and controlled depth.
    profiles=[]
    for k in range(9):
        t=(math.pi/2)*k/8
        profiles.append((-d/2+edge-edge*math.cos(t),edge*(1-math.sin(t))))
    profiles.append((d/2-edge,0))
    for k in range(1,9):
        t=(math.pi/2)*k/8
        profiles.append((d/2-edge+edge*math.sin(t),edge*(1-math.cos(t))))
    verts=[]
    for y,inset in profiles:
        for x,z in rr_points(w-2*inset,h-2*inset,max(.025,r-inset)):
            verts.append((x+loc[0],y+loc[1],z+loc[2]))
    n=len(rr_points(w,h,r))
    faces=[]
    for j in range(len(profiles)-1):
        for i in range(n):
            a=j*n+i; b=j*n+(i+1)%n
            faces.append((a,b,b+n,a+n))
    faces.extend([tuple(reversed(range(n))),tuple((len(profiles)-1)*n+i for i in range(n))])
    o=mesh(name,verts,faces,mat)
    # Keep the two broad planar faces flat; other surfaces are smoothly shaded.
    o.data.polygons[-1].use_smooth=False
    o.data.polygons[-2].use_smooth=False
    return o


BODY_A, BODY_B, BODY_C = 1.33, .445, 1.10
BODY_P, BODY_Q = 3.35, 4.65


def body_front(x,z):
    radius=(abs(x/BODY_A)**BODY_Q+abs((z-2.02)/BODY_C)**BODY_Q)**(BODY_P/BODY_Q)
    return -BODY_B*max(.00001,1-radius)**(1/BODY_P)


def pillow_body():
    # Six welded quad grids projected onto a rounded superellipsoid.
    # This produces continuous convex surfaces instead of a bevelled slab.
    verts=[]; faces=[]; indices={}; n=36
    def vertex(c):
        key=tuple(c)
        if key in indices: return indices[key]
        x,y,z=[v/n for v in c]
        norm=((abs(x)**BODY_Q+abs(z)**BODY_Q)**(BODY_P/BODY_Q)+abs(y)**BODY_P)**(1/BODY_P)
        indices[key]=len(verts)
        verts.append((BODY_A*x/norm,BODY_B*y/norm,2.02+BODY_C*z/norm))
        return indices[key]
    for axis in range(3):
        other=[i for i in range(3) if i!=axis]
        for side in [-1,1]:
            grid=[]
            for j in range(n+1):
                row=[]
                for i in range(n+1):
                    c=[0,0,0]; c[axis]=side*n; c[other[0]]=-n+2*i; c[other[1]]=-n+2*j
                    row.append(vertex(c))
                grid.append(row)
            for j in range(n):
                for i in range(n): faces.append((grid[j][i],grid[j][i+1],grid[j+1][i+1],grid[j+1][i]))
    o=mesh('Body • continuous rounded housing',verts,faces,blue)
    sub=o.modifiers.new('Continuous shell curvature','SUBSURF'); sub.levels=1; sub.render_levels=2
    return o


def face_inlay():
    # Thin inlay follows the same analytic curvature as the blue housing.
    verts=[]; faces=[]; contour=rr_points(2.04,1.38,.33,24); n=len(contour)
    factors=[1-i*.96/16 for i in range(17)]
    for back in [False,True]:
        for f in factors:
            for x,z in contour:
                x=x*f; z=2.19+z*f
                verts.append((x,body_front(x,z)+(.012 if back else -.012),z))
    half=n*len(factors)
    for offset in [0,half]:
        for j in range(len(factors)-1):
            for i in range(n):
                a=offset+j*n+i; b=offset+j*n+(i+1)%n
                faces.append((a,b,b+n,a+n))
        faces.append(tuple(offset+(len(factors)-1)*n+i for i in range(n)))
    for i in range(n):
        k=(i+1)%n; faces.append((i,k,k+half,i+half))
    return mesh('Face • inset sky panel',verts,faces,cyan)


def soft_boot(side,s,mat):
    # Broad planted dome, softly rolled sole, fuller toe and compact heel.
    profiles=[(0,.82),(.010,.91),(.028,.98),(.055,1),(.092,.994),(.14,.95),(.195,.85),(.244,.69),(.282,.46),(.304,.19),(.308,.045)]
    verts=[]; faces=[]; n=64
    for z,r in profiles:
        for i in range(n):
            t=math.tau*i/n
            verts.append((s*.65+.32*r*math.cos(t),-.105+.36*r*math.sin(t)+.055*(z/.308),z))
    for j in range(len(profiles)-1):
        for i in range(n):
            a=j*n+i; b=j*n+(i+1)%n; faces.append((a,b,b+n,a+n))
    faces.extend([tuple(reversed(range(n))),tuple((len(profiles)-1)*n+i for i in range(n))])
    o=mesh('Foot • soft boot.'+side,verts,faces,mat)
    o.data.polygons[-2].use_smooth=False
    sub=o.modifiers.new('Smooth boot contour','SUBSURF'); sub.levels=2; sub.render_levels=2
    return o


def tube(name, points, radii, mat, radial=24):
    verts=[]; faces=[]
    for j,p in enumerate(points):
        p=Vector(p)
        tangent=Vector(points[min(j+1,len(points)-1)])-Vector(points[max(0,j-1)])
        tangent.normalize()
        u=tangent.cross(Vector((0,1,0))).normalized()
        v=tangent.cross(u).normalized()
        for i in range(radial):
            a=2*math.pi*i/radial
            verts.append(p+radii[j]*(u*math.cos(a)+v*math.sin(a)))
    for j in range(len(points)-1):
        for i in range(radial):
            a=j*radial+i; b=j*radial+(i+1)%radial
            faces.append((a,b,b+radial,a+radial))
    faces.extend([tuple(reversed(range(radial))),tuple((len(points)-1)*radial+i for i in range(radial))])
    return mesh(name,verts,faces,mat)


def capsule(name, a,b,r,mat):
    a=Vector(a); b=Vector(b)
    axis=(b-a).normalized(); length=(b-a).length
    pts=[]; radii=[]
    for i in range(9):
        t=-math.pi/2+(math.pi/2)*i/8
        pts.append(a+axis*(r*math.sin(t)))
        radii.append(max(.0003,r*math.cos(t)))
    for i in range(1,9):
        t=math.pi/2*i/8
        pts.append(b+axis*(r*math.sin(t)))
        radii.append(max(.0003,r*math.cos(t)))
    return tube(name,pts,radii,mat)


def bezier(a,b,c,d,n=33):
    return [(1-t)**3*Vector(a)+3*(1-t)**2*t*Vector(b)+3*(1-t)*t*t*Vector(c)+t**3*Vector(d) for t in [i/(n-1) for i in range(n)]]


def rigid(obj,bone):
    vg=obj.vertex_groups.new(name=bone)
    vg.add(list(range(len(obj.data.vertices))),1,'REPLACE')
    mod=obj.modifiers.new('ROBI • skeletal deformation','ARMATURE')
    mod.object=rig
    obj.parent=rig


def skin_limb(obj,upper,lower,joint,axis=2):
    a=obj.vertex_groups.new(name=upper); b=obj.vertex_groups.new(name=lower)
    for v in obj.data.vertices:
        p=obj.matrix_world@v.co
        t=max(0,min(1,(p[axis]-joint+.26)/.52))
        t=t*t*(3-2*t)
        if t>0: a.add([v.index],t,'REPLACE')
        if t<1: b.add([v.index],1-t,'REPLACE')
    mod=obj.modifiers.new('ROBI • smooth joint weights','ARMATURE'); mod.object=rig
    mod.use_deform_preserve_volume=True
    sub=obj.modifiers.new('Surface finish','SUBSURF'); sub.levels=1; sub.render_levels=2
    obj.parent=rig


def prop_driver(owner,path,index,prop,expression):
    fc=owner.driver_add(path,index) if index is not None else owner.driver_add(path)
    d=fc.driver; d.type='SCRIPTED'; d.expression=expression
    v=d.variables.new(); v.name='v'; v.type='SINGLE_PROP'
    v.targets[0].id=rig; v.targets[0].data_path='["'+prop+'"]'


def build_geometry():
    global geo,studio,rigcol,blue,cyan,dark,white,rig,parts,limbs,eye_parts,hand_parts
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):
        if c.users==0 or c.name=='Collection': bpy.data.collections.remove(c)
    geo=bpy.data.collections.new('ROBI | Character'); bpy.context.scene.collection.children.link(geo)
    rigcol=bpy.data.collections.new('ROBI | Rig'); bpy.context.scene.collection.children.link(rigcol)
    studio=bpy.data.collections.new('STUDIO | Cameras and lights'); bpy.context.scene.collection.children.link(studio)
    blue=material('ROBI / cobalt blue polymer','287FF6',.54,.035)
    cyan=material('ROBI / sky blue face','6AB6FB',.53,.015)
    glove=material('ROBI / soft ice blue','9FD7FC',.57,.025)
    dark=material('ROBI / navy smile','123F87',.65,0)
    pupil=material('ROBI / glossy midnight pupils','070D15',.25,.13)
    white=material('ROBI / porcelain eye whites','F7FCFF',.42,.04)
    catch=material('ROBI / eye catchlights','FFFFFF',.16,.05)
    parts=[]; limbs=[]; eye_parts=[]; hand_parts=[]
    body=pillow_body()
    parts.append((body,'body'))
    panel=face_inlay()
    parts.append((panel,'body'))
    # Rear housing is intentionally quiet; no invented logos or machinery.
    for s,side in [(1,'L'),(-1,'R')]:
        ear=ellipsoid('Shoulder housing.'+side,(s*1.325,0,2.00),(.16,.245,.285),glove)
        parts.append((ear,'body'))
        a=(s*1.45,0,1.98); elbow=(s*1.68,-.005,1.58); wrist=(s*1.79,-.025,1.19)
        pts=bezier(a,(s*1.56,0,1.85),(s*1.75,-.025,1.46),wrist)
        arm=tube('Arm • flexible sleeve.'+side,pts,[.100+.006*math.sin(math.pi*i/32) for i in range(33)],blue)
        limbs.append((arm,'upper_arm.'+side,'forearm.'+side,1.58))
        palm=ellipsoid('Hand • palm.'+side,(s*1.83,-.028,1.047),(.207,.125,.186),glove)
        hand_components=[palm]
        fingers=[]
        for j,(offset,length) in enumerate([(-.142,.235),(0,.28),(.142,.245)]):
            x=s*(1.83+offset)
            start=(x,-.035,.984); end=(x+s*offset*.09,-.075,.984-length)
            f=capsule('Hand • finger '+str(j+1)+'.'+side,start,end,.067,glove)
            hand_components.append(f); fingers.append((start,end))
        thumb_start=(s*1.67,-.013,1.097); thumb_end=(s*1.567,-.080,.94)
        hand_components.append(capsule('Hand • thumb.'+side,thumb_start,thumb_end,.079,glove))
        bpy.ops.object.select_all(action='DESELECT')
        for o in hand_components: o.select_set(True)
        bpy.context.view_layer.objects.active=palm
        bpy.ops.object.join()
        # Fuse glove at the knuckles; voxel surface keeps fingers separated.
        rem=palm.modifiers.new('Glove union','REMESH'); rem.mode='VOXEL'; rem.voxel_size=.008; rem.use_smooth_shade=True
        bpy.ops.object.modifier_apply(modifier=rem.name)
        sm=palm.modifiers.new('Glove relaxation','SMOOTH'); sm.factor=.65; sm.iterations=9
        bpy.ops.object.modifier_apply(modifier=sm.name)
        bpy.ops.object.quadriflow_remesh(target_faces=2600,use_mesh_symmetry=False,use_preserve_sharp=False,use_preserve_boundary=False,smooth_normals=True,seed=5)
        print('GLOVE_RETOPOLOGY',side,len(palm.data.polygons),flush=True)
        finish(palm,'Hand • seamless glove.'+side,None)
        hand_parts.append((palm,side,fingers,(thumb_start,thumb_end)))
        hip=(s*.62,0,.99); knee=(s*.64,-.018,.65); ankle=(s*.65,-.04,.30)
        pts=bezier(hip,(s*.63,0,.8),(s*.65,-.04,.5),ankle)
        leg=tube('Leg • flexible sleeve.'+side,pts,[.111]*33,blue)
        limbs.append((leg,'thigh.'+side,'shin.'+side,.65))
        # A softly domed shoe with flat sole and a forward rounded toe.
        shoe=soft_boot(side,s,glove)
        parts.append((shoe,'foot.'+side))
    ant=capsule('Antenna • stem',(0,.01,3.06),(0,.01,3.40),.065,blue)
    parts.append((ant,'antenna'))
    bulb=ellipsoid('Antenna • soft tip',(0,.01,3.54),(.173,.173,.173),glove)
    parts.append((bulb,'antenna'))
    for s,side in [(1,'L'),(-1,'R')]:
        x=s*.482; z=2.255
        sclera=ellipsoid('Eye • white.'+side,(x,-.455,z),(.337,.069,.354),white)
        iris=ellipsoid('Eye • pupil.'+side,(x,-.515,z-.012),(.210,.039,.226),pupil)
        big=ellipsoid('Eye • large glint.'+side,(x-.060,-.552,z+.075),(.051,.007,.054),catch,32,20)
        small=ellipsoid('Eye • small glint.'+side,(x+.067,-.550,z-.089),(.020,.006,.022),catch,24,16)
        eye_parts.append((side,x,z,[sclera,iris,big,small]))
    points=[]
    for i in range(41):
        t=-1+2*i/40
        z=1.767+.098*t*t
        points.append((.174*t,body_front(.174*t,z)-.021,z))
    mouth=tube('Mouth • soft brand smile',points,[.024+.005*math.sin(math.pi*i/40) for i in range(41)],dark,16)
    for p in [points[0],points[-1]]:
        parts.append((ellipsoid('Mouth • rounded corner',p,(.024,.024,.024),dark,24,16),'body'))
    parts.append((mouth,'body'))
    # A dedicated body bone allows whole-shell acting while root stays on floor.
    arm=bpy.data.armatures.new('ROBI • animation skeleton')
    rig=bpy.data.objects.new('ROBI_RIG',arm); rigcol.objects.link(rig)
    rig.show_in_front=True
    bpy.context.view_layer.objects.active=rig
    bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    def bone(name,head,tail,parent=None,deform=True):
        b=arm.edit_bones.new(name); b.head=head; b.tail=tail; b.use_deform=deform
        if parent: b.parent=arm.edit_bones[parent]
        return b
    bone('root',(0,0,0),(0,0,.4),deform=False)
    bone('body',(0,0,1.0),(0,0,2.9),'root')
    bone('antenna',(0,.01,3.08),(0,.01,3.56),'body')
    for s,side in [(1,'L'),(-1,'R')]:
        bone('upper_arm.'+side,(s*1.45,0,1.98),(s*1.68,-.005,1.58),'body')
        bone('forearm.'+side,(s*1.68,-.005,1.58),(s*1.79,-.025,1.19),'upper_arm.'+side)
        bone('hand.'+side,(s*1.79,-.025,1.19),(s*1.83,-.04,.96),'forearm.'+side)
        bone('thigh.'+side,(s*.62,0,.99),(s*.64,-.018,.65),'body')
        bone('shin.'+side,(s*.64,-.018,.65),(s*.65,-.04,.30),'thigh.'+side)
        bone('foot.'+side,(s*.65,-.04,.30),(s*.65,-.34,.16),'shin.'+side)
    for hand,side,fingers,thumb in hand_parts:
        for j,(a,b) in enumerate(fingers): bone('finger_'+str(j+1)+'.'+side,a,b,'hand.'+side)
        bone('thumb.'+side,*thumb,'hand.'+side)
    bpy.ops.object.mode_set(mode='OBJECT')
    for o,b in parts: rigid(o,b)
    for args in limbs: skin_limb(*args)
    for hand,side,fingers,thumb in hand_parts:
        groups={name:hand.vertex_groups.new(name=name+'.'+side) for name in ['hand','finger_1','finger_2','finger_3','thumb']}
        for v in hand.data.vertices:
            p=hand.matrix_world@v.co
            thumb_strength=max(0,min(1,(1.73-abs(p.x))/.12))*max(0,min(1,(1.13-p.z)/.16))
            finger_strength=max(0,min(1,(.98-p.z)/.14))*(1-thumb_strength)
            idx=min(range(3),key=lambda i:abs(p.x-fingers[i][0][0]))
            weights={'hand':max(0,1-thumb_strength-finger_strength),'thumb':thumb_strength,'finger_'+str(idx+1):finger_strength}
            for name,w in weights.items():
                if w>0: groups[name].add([v.index],w,'REPLACE')
        mod=hand.modifiers.new('ROBI • finger deformation','ARMATURE'); mod.object=rig; mod.use_deform_preserve_volume=True
        sub=hand.modifiers.new('Glove surface finish','SUBSURF'); sub.levels=1; sub.render_levels=1
        hand.parent=rig
    for prop,default,low,high,desc in [('blink_L',0,0,1,'Close left eye'),('blink_R',0,0,1,'Close right eye'),('look_x',0,-1,1,'Horizontal gaze'),('look_z',0,-1,1,'Vertical gaze')]:
        rig[prop]=default; rig.id_properties_ui(prop).update(min=low,max=high,description=desc)
    for side,x,z,objs in eye_parts:
        for obj in objs:
            rigid(obj,'body')
            obj.shape_key_add(name='Basis',from_mix=False)
            key=obj.shape_key_add(name='Blink',from_mix=False)
            # Transform mesh in world space, then return to local coordinates.
            for v in key.data:
                p=obj.matrix_world@v.co
                p.z=z+(p.z-z)*.01
                p.y=-.395+(p.y-obj.location.y)*.12
                v.co=obj.matrix_world.inverted()@p
            prop_driver(key,'value',None,'blink_'+side,'v')
            if obj!=objs[0]:
                for prop,axis,extent in [('look_x',0,.088),('look_z',2,.065)]:
                    key=obj.shape_key_add(name=prop,from_mix=False)
                    key.slider_min=-1
                    for v in key.data: v.co[axis]+=extent
                    prop_driver(key,'value',None,prop,'v')
        # A closed eye is a clean navy arc, rather than a flattened white sphere.
        pts=[(x+.255*t,-.375,z+.035*(1-t*t)) for t in [-1+2*i/32 for i in range(33)]]
        lid=tube('Eye • closed lid.'+side,pts,[.018]*33,dark,12)
        rigid(lid,'body')
        lid.shape_key_add(name='Basis',from_mix=False)
        key=lid.shape_key_add(name='Blink',from_mix=False)
        for v in key.data: v.co.y=body_front(v.co.x,v.co.z)-.030
        prop_driver(key,'value',None,'blink_'+side,'max(0.0,(v-0.68)/0.32)')
    rig['asset_version']='ROBI neutral • 2.0 polished'
    rig['pose_notes']='Symmetric relaxed rest pose. Front = -Y. FK arms, legs, fingers. Face properties on rig.'
    for pb in rig.pose.bones:
        pb.rotation_mode='XYZ'
        if pb.name!='root': pb.lock_scale=(True,True,True)
    return rig


def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()


def build_motion_check():
    """Keep an optional greeting clip in the asset, with no action assigned."""
    poses=[(1,0,0,0),(12,-.40,-.60,0),(24,-.95,-1.0,.22),(32,-.95,-1.0,-.22),(40,-.95,-1.0,.22),(48,-.95,-1.0,-.22),(60,-.4,-.45,0),(72,0,0,0)]
    for frame,upper,lower,wrist in poses:
        for name,value in [('upper_arm.L',upper),('forearm.L',lower),('hand.L',wrist)]:
            pb=rig.pose.bones[name]; pb.rotation_euler[2]=value
            pb.keyframe_insert(data_path='rotation_euler',frame=frame,group='Greeting / arm')
        rig['look_x']=.30 if 12<=frame<=48 else 0.
        rig.keyframe_insert(data_path='["look_x"]',frame=frame,group='Greeting / face')
    for frame,value in [(1,0.),(13,0.),(16,1.),(19,0.),(49,0.),(52,1.),(55,0.),(72,0.)]:
        for prop in ['blink_L','blink_R']:
            rig[prop]=value; rig.keyframe_insert(data_path='["'+prop+'"]',frame=frame,group='Greeting / face')
    action=rig.animation_data.action
    action.name='ROBI • Greeting check (72 frames)'; action.use_fake_user=True
    rig.animation_data.action=None
    for pb in rig.pose.bones: pb.rotation_euler=(0,0,0)
    for prop in ['blink_L','blink_R','look_x','look_z']: rig[prop]=0.
    rig.update_tag(refresh={'OBJECT'})
    bpy.context.view_layer.update()


def build_studio():
    scene=bpy.context.scene
    scene.render.engine='CYCLES'; scene.cycles.samples=64
    scene.cycles.use_denoising=True
    scene.render.resolution_x=1600; scene.render.resolution_y=1600; scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGBA'
    scene.render.film_transparent=False
    scene.view_settings.view_transform='Standard'
    scene.view_settings.exposure=-.45
    scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.45,.45,.45,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.40
    floor=material('Studio / blue grey','DCE7F3',.72,0)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.0))
    finish(bpy.context.object,'Studio • seamless floor',floor,studio)
    for name,loc,power,size,color in [('Key',(-3.8,-5.2,7),500,4.5,(1,.98,.96)),('Fill',(4,-3,4.2),220,4,(.9,.95,1)),('Rim',(2.2,3,5.7),350,3.5,(.88,.94,1)),('Top',(-1,1,7),110,3,(1,.98,.95))]:
        data=bpy.data.lights.new('Studio • '+name,'AREA'); data.energy=power; data.shape='DISK'; data.size=size; data.color=color
        o=bpy.data.objects.new(data.name,data); studio.objects.link(o); o.location=loc; aim(o,(0,0,1.8))
    for name,loc,scale in [('Front',(0,-10,1.83),4.65),('ThreeQuarter',(5.1,-10,4.0),4.65),('Side',(10,0,1.83),4.65),('Back',(0,10,1.83),4.65),('FaceDetail',(2.2,-9,3.4),3.0)]:
        data=bpy.data.cameras.new('Camera • '+name); data.type='ORTHO'; data.ortho_scale=scale
        o=bpy.data.objects.new(data.name,data); studio.objects.link(o); o.location=loc
        aim(o,(0,0,1.83) if name!='FaceDetail' else (0,-.2,2.28))
    scene.camera=bpy.data.objects['Camera • ThreeQuarter']
    scene.render.fps=24; scene.frame_start=1; scene.frame_end=96; scene.frame_set(1)
    # No action is assigned: the saved asset opens in a truly neutral rest pose.
    for area in bpy.context.screen.areas if bpy.context.screen else []:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL'
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True); bpy.context.view_layer.objects.active=rig
    rig.show_in_front=False
    text=bpy.data.texts.new('START HERE • ROBI')
    text.write('ROBI / polished neutral character v2\n\nFront: -Y; up: Z. Frame 1 is the neutral rest pose.\nSelect ROBI_RIG, enter Pose Mode. FK: body, antenna, arms, legs, hands, fingers.\nObject custom properties: blink_L, blink_R (0..1), look_x, look_z (-1..1).\nHard shell stays rigid; flexible limbs have graduated weights.\nHide STUDIO collection for asset-only work. Cameras: Front, ThreeQuarter, Side, Back, FaceDetail.\nOptional Action: ROBI • Greeting check (72 frames). Assign it in Action Editor to preview. No action is assigned by default.\nThis is a base FK rig, not an IK or lip-sync production rig.\nSource: scripts/blender/build_robi_neutral.py\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(DEST))
    scene.render.filepath=str(OUT/'preview-three-quarter.png')


if __name__=='__main__':
    build_geometry()
    build_motion_check()
    build_studio()
    print('ROBI_BUILD_COMPLETE',str(DEST),flush=True)
