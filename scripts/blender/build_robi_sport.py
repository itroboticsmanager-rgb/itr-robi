"""ROBI Sport: yellow shirt, navy shorts and blue/yellow sneakers.

New character proportions, neutral A-pose, independent head/torso FK rig.
Uses the earlier generator's geometry helpers, never loads the earlier asset.
"""
import bpy, math, json, sys
from pathlib import Path
from mathutils import Vector, Matrix
sys.path.insert(0,str(Path(__file__).parent))
import build_robi_neutral as H

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'out'/'robi-sport'; OUT.mkdir(parents=True,exist_ok=True)
DEST=ROOT/'assets'/'3d'/'robi_sport_neutral.blend'
rigid_parts=[]; flexible=[]; hands=[]


def tag(o,bone): rigid_parts.append((o,bone)); return o
def sphere(name,p,s,mat,bone=None):
    o=H.ellipsoid(name,p,s,mat)
    return tag(o,bone) if bone else o


def subdiv(o,level=1):
    m=o.modifiers.new('Surface finish','SUBSURF'); m.levels=level; m.render_levels=2
    return o


def sweep(name,pts,radii,mat,flatten=1.,sides=32,closed=False):
    verts=[]; faces=[]
    for j,p in enumerate(pts):
        p=Vector(p)
        t=Vector(pts[(j+1)%len(pts)] if closed else pts[min(j+1,len(pts)-1)])-Vector(pts[(j-1)%len(pts)] if closed else pts[max(0,j-1)])
        t.normalize(); u=t.cross(Vector((0,1,0)))
        if u.length<.01: u=t.cross(Vector((0,0,1)))
        u.normalize(); v=t.cross(u).normalized()
        for i in range(sides):
            a=math.tau*i/sides
            verts.append(p+radii[j]*(math.cos(a)*u+flatten*math.sin(a)*v))
    count=len(pts) if closed else len(pts)-1
    for j in range(count):
        for i in range(sides):
            a=j*sides+i; b=j*sides+(i+1)%sides; c=((j+1)%len(pts))*sides
            faces.append((a,b,c+(i+1)%sides,c+i))
    if not closed: faces += [tuple(reversed(range(sides))),tuple((len(pts)-1)*sides+i for i in range(sides))]
    return H.mesh(name,verts,faces,mat)


def ellipse_ring(name,center,rx,ry,r,mat,bone,axis='Z'):
    pts=[]
    for i in range(96):
        a=math.tau*i/96
        if axis=='Z': v=(rx*math.cos(a),ry*math.sin(a),0)
        else: v=(0,ry*math.sin(a),rx*math.cos(a))
        pts.append(Vector(center)+Vector(v))
    return tag(sweep(name,pts,[r]*len(pts),mat,sides=12,closed=True),bone)


def loft(name,profiles,mat,centerx=0,cap=True):
    # z, x-radius, y-radius, y-offset; rounded rectangle section.
    verts=[];faces=[]; n=64
    for z,rx,ry,cy in profiles:
        for i in range(n):
            a=math.tau*i/n
            x=math.copysign(abs(math.cos(a))**.85,math.cos(a))
            y=math.copysign(abs(math.sin(a))**.85,math.sin(a))
            verts.append((centerx+rx*x,cy+ry*y,z))
    for j in range(len(profiles)-1):
        for i in range(n):
            a=j*n+i; b=j*n+(i+1)%n; faces.append((a,b,b+n,a+n))
    if cap: faces += [tuple(reversed(range(n))),tuple((len(profiles)-1)*n+i for i in range(n))]
    o=H.mesh(name,verts,faces,mat)
    return o


def union_remesh(name,objects,mat,quads=3000,voxel=.012):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects: o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]; bpy.ops.object.join(); o=objects[0]
    m=o.modifiers.new('Unified surface','REMESH'); m.mode='VOXEL'; m.voxel_size=voxel; m.use_smooth_shade=True
    bpy.ops.object.modifier_apply(modifier=m.name)
    m=o.modifiers.new('Surface relaxation','SMOOTH'); m.factor=.6; m.iterations=6
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.quadriflow_remesh(target_faces=quads,use_mesh_symmetry=False,use_preserve_sharp=False,smooth_normals=True,seed=9)
    o.data.materials.clear(); o.data.materials.append(mat); o.name=name
    return o


def head_front(x,z): return H.body_front(x/.94,(z-3.45)/.87+2.02)*1.08


def build_head():
    transform=Matrix.Translation((0,0,3.45-.87*2.02))@Matrix.Diagonal((.94,1.08,.87,1))
    H.blue=blue; H.cyan=faceblue
    head=H.pillow_body(); head.name='Head • soft blue housing'; head.data.transform(transform); tag(head,'head')
    panel=H.face_inlay(); panel.name='Face • sky blue inlay'; panel.data.transform(transform); tag(panel,'head')
    for s,side in [(1,'L'),(-1,'R')]:
        sphere('Ear • blue rim.'+side,(s*1.235,.005,3.43),(.17,.28,.31),trimblue,'head')
        sphere('Ear • pale cap.'+side,(s*1.335,-.012,3.43),(.09,.235,.263),ice,'head')
    pts=H.bezier((0,0,4.35),(-.07,0,4.57),(-.27,0,4.68),(-.45,0,4.72),33)
    tag(subdiv(sweep('Antenna • curved stem',pts,[.059]*33,blue)),'antenna')
    sphere('Antenna • blue pearl',(-.49,0,4.745),(.169,.169,.169),ice,'antenna')
    eyes=[]
    for s,side in [(1,'L'),(-1,'R')]:
        x=s*.458; z=3.66
        objects=[sphere('Eye • white.'+side,(x,-.486,z),(.320,.078,.337),white),
                 sphere('Eye • pupil.'+side,(x,-.558,z+.008),(.186,.045,.207),black),
                 sphere('Eye • large glint.'+side,(x-.057,-.602,z+.084),(.048,.008,.050),white),
                 sphere('Eye • small glint.'+side,(x+.064,-.598,z-.071),(.018,.005,.020),white)]
        eyes.append((side,x,z,objects))
    # Open, friendly smile with a subtly curved upper lip and rounded lower bowl.
    outline=[]
    segments=[((-.18,3.255),(-.08,3.218),(.08,3.218),(.18,3.255)),
              ((.18,3.255),(.22,3.22),(.13,3.09),(0,3.09)),
              ((0,3.09),(-.13,3.09),(-.22,3.22),(-.18,3.255))]
    for a,b,c,d in segments:
        for i in range(20):
            t=i/20
            p=(1-t)**3*Vector(a)+3*(1-t)**2*t*Vector(b)+3*(1-t)*t*t*Vector(c)+t**3*Vector(d)
            outline.append((p.x,head_front(p.x,p.y)-.030,p.y))
    n=len(outline); verts=outline+[(x,y+.025,z) for x,y,z in outline]
    faces=[tuple(reversed(range(n))),tuple(n+i for i in range(n))]+[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    mouth=tag(H.mesh('Mouth • open friendly smile',verts,faces,navy),'head')
    bevel=mouth.modifiers.new('Soft smile edge','BEVEL'); bevel.width=.009; bevel.segments=3
    sphere('Mouth • inner blue bounce',(0,-.510,3.125),(.095,.01,.024),trimblue,'head')
    return eyes


def build_clothes():
    neck=H.capsule('Neck • flexible blue',(0,0,2.40),(0,0,2.63),.165,blue); tag(neck,'neck')
    shirt=loft('Shirt • tailored yellow body',[(1.54,.69,.365,0),(1.565,.701,.374,0),(1.61,.69,.367,0),(1.76,.637,.352,0),(1.97,.62,.352,0),(2.17,.663,.344,0),(2.32,.68,.315,0),(2.40,.51,.279,0),(2.45,.28,.224,0),(2.452,.246,.20,0)],yellow,cap=True)
    shirt_pieces=[shirt]
    ellipse_ring('Shirt • collar piping',(0,0,2.455),.252,.206,.024,gold,'chest')
    ellipse_ring('Shirt • rolled hem',(0,0,1.565),.699,.374,.019,gold,'chest')
    sphere('Shirt • blue round badge',(0,-.363,2.04),(.146,.018,.146),blue,'chest')
    for s,side in [(1,'L'),(-1,'R')]:
        a=Vector((s*.49,0,2.28)); b=Vector((s*.83,0,2.16))
        pts=[a.lerp(b,i/8) for i in range(9)]
        sleeve=sweep('Shirt • short sleeve.'+side,pts,[.205+.014*math.sin(math.pi*i/8) for i in range(9)],yellow)
        shirt_pieces.append(sleeve)
        tangent=(b-a).normalized(); u=tangent.cross(Vector((0,1,0))).normalized(); v=tangent.cross(u)
        ring=[b+.207*(math.cos(math.tau*i/64)*u+math.sin(math.tau*i/64)*v) for i in range(64)]
        tag(sweep('Shirt • sleeve seam.'+side,ring,[.014]*64,gold,sides=10,closed=True),'upper_arm.'+side)
        pts=H.bezier((s*.63,-.20,1.60),(s*.575,-.22,1.78),(s*.585,-.24,1.97),(s*.61,-.20,2.13),25)
        tag(sweep('Shirt • side stitch.'+side,pts,[.0045]*25,gold,sides=8),'chest')
    shirt=union_remesh('Shirt • continuous yellow fabric',shirt_pieces,yellow,4800,.010)
    flexible.append((shirt,'shirt'))
    pelvis=sphere('Shorts base',(0,0,1.54),(.61,.33,.235),shortmat)
    pieces=[pelvis]
    for s in [-1,1]:
        pieces.append(loft('Shorts leg',[(1.075,.298,.315,0),(1.11,.31,.33,0),(1.40,.32,.34,0),(1.64,.29,.30,0)],shortmat,s*.323))
    shorts=union_remesh('Shorts • navy fabric',pieces,shortmat,3600,.013)
    flexible.append((shorts,'shorts'))
    for s,side in [(1,'L'),(-1,'R')]:
        cuff=loft('Shorts • turned cuff.'+side,[(1.07,.296,.314,0),(1.084,.317,.331,0),(1.13,.32,.335,0),(1.17,.31,.33,0)],shorttrim,s*.323)
        tag(subdiv(cuff),'thigh.'+side)
        pts=H.bezier((s*.613,0,1.16),(s*.646,0,1.33),(s*.634,0,1.51),(s*.578,0,1.62),25)
        tag(sweep('Shorts • side seam.'+side,pts,[.007]*25,shorttrim,sides=10),'pelvis')


def build_sneaker(side,s):
    x=s*.37; bone='foot.'+side
    sole=loft('Sneaker • yellow sole.'+side,[(.016,.237,.404,-.16),(.024,.270,.44,-.16),(.055,.280,.450,-.16),(.117,.280,.447,-.16),(.143,.264,.427,-.16)],yellow,x)
    tag(subdiv(sole,2),bone)
    ellipse_ring('Sneaker • sole welt.'+side,(x,-.16,.129),.269,.434,.014,gold,bone)
    upper=loft('Sneaker • blue upper.'+side,[(.121,.245,.407,-.16),(.16,.252,.410,-.16),(.225,.241,.385,-.147),(.29,.215,.323,-.105),(.36,.183,.258,-.040),(.43,.174,.215,.008),(.485,.163,.191,.035),(.50,.149,.173,.035)],blue,x)
    tag(subdiv(upper,2),bone)
    ellipse_ring('Sneaker • padded ankle collar.'+side,(x,.034,.482),.158,.182,.028,ice,bone)
    pts=H.bezier((x,-.48,.24),(x,-.40,.32),(x,-.20,.47),(x,-.13,.46),25)
    tongue=sweep('Sneaker • blue tongue.'+side,pts,[.112]*25,trimblue,flatten=.20)
    tag(subdiv(tongue),bone)
    for j,(y,z,w) in enumerate([(-.416,.301,.137),(-.317,.377,.13),(-.216,.442,.122)]):
        pts=H.bezier((x-w,y+.015,z-.012),(x-w*.5,y-.038,z+.020),(x+w*.5,y-.038,z+.020),(x+w,y+.015,z-.012),25)
        tag(sweep('Sneaker • pale lace '+str(j+1)+'.'+side,pts,[.020]*25,ice,sides=16),bone)
    pts=[]
    for i in range(41):
        t=-1+2*i/40
        pts.append((x+.225*t,-.34-.12*(1-t*t),.238-.029*t*t))
    tag(sweep('Sneaker • toe stitching.'+side,pts,[.005]*41,trimblue,sides=8),bone)
    # Physical tread is on the bottom, visible when a foot is lifted.
    for j in range(6):
        pts=[(x-.17,-.46+j*.115,.019),(x+.17,-.46+j*.115,.019)]
        tag(sweep('Sneaker • outsole tread '+str(j)+'.'+side,pts,[.010]*2,gold,sides=8),bone)


def build_limbs():
    for s,side in [(1,'L'),(-1,'R')]:
        pts=H.bezier((s*.75,0,2.245),(s*.99,0,2.11),(s*1.22,-.018,1.77),(s*1.33,-.030,1.58),41)
        arm=sweep('Arm • blue flexible sleeve.'+side,pts,[.138-.010*i/40 for i in range(41)],blue)
        flexible.append((arm,'arm.'+side))
        a=Vector((s*1.33,-.030,1.58)); b=Vector((s*1.365,-.035,1.51)); t=(b-a).normalized(); u=t.cross(Vector((0,1,0))).normalized(); v=t.cross(u)
        pts=[a+.137*(math.cos(math.tau*i/64)*u+math.sin(math.tau*i/64)*v) for i in range(64)]
        tag(sweep('Glove • rolled cuff.'+side,pts,[.024]*64,ice,sides=12,closed=True),'hand.'+side)
        palm=sphere('Palm',(s*1.395,-.043,1.425),(.183,.118,.182),ice)
        pieces=[palm]; fingers=[]
        for j,(off,length) in enumerate([(-.126,.21),(0,.245),(.126,.22)]):
            a=(s*(1.395+off),-.047,1.375); b=(s*(1.395+off*1.10),-.072,1.375-length)
            pieces.append(H.capsule('Finger',a,b,.062,ice)); fingers.append((a,b))
        a=(s*1.251,-.03,1.47); b=(s*1.16,-.09,1.325)
        pieces.append(H.capsule('Thumb',a,b,.075,ice))
        hand=union_remesh('Hand • glove.'+side,pieces,ice,2600,.009)
        hands.append((hand,side,fingers,(a,b)))
        pts=H.bezier((s*.325,0,1.45),(s*.35,.015,1.15),(s*.37,-.008,.75),(s*.37,.026,.40),49)
        leg=sweep('Leg • blue flexible.'+side,pts,[.166-.019*i/48 for i in range(49)],blue)
        flexible.append((leg,'leg.'+side))
        build_sneaker(side,s)


def build_rig(eyes):
    arm=bpy.data.armatures.new('ROBI Sport Skeleton'); rig=bpy.data.objects.new('ROBI_SPORT_RIG',arm); H.rigcol.objects.link(rig); H.rig=rig
    bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); bpy.context.view_layer.objects.active=rig; bpy.ops.object.mode_set(mode='EDIT')
    def bone(name,h,t,parent=None,deform=True):
        b=arm.edit_bones.new(name); b.head=h; b.tail=t; b.use_deform=deform
        if parent: b.parent=arm.edit_bones[parent]
    bone('root',(0,0,0),(0,0,.4),deform=False)
    bone('pelvis',(0,0,1.3),(0,0,1.7),'root')
    bone('chest',(0,0,1.7),(0,0,2.43),'pelvis')
    bone('neck',(0,0,2.4),(0,0,2.62),'chest')
    bone('head',(0,0,2.58),(0,0,4.20),'neck')
    bone('antenna',(0,0,4.35),(-.49,0,4.745),'head')
    for s,side in [(1,'L'),(-1,'R')]:
        bone('upper_arm.'+side,(s*.65,0,2.32),(s*1.08,-.008,1.965),'chest')
        bone('forearm.'+side,(s*1.08,-.008,1.965),(s*1.33,-.030,1.58),'upper_arm.'+side)
        bone('hand.'+side,(s*1.33,-.030,1.58),(s*1.395,-.047,1.375),'forearm.'+side)
        bone('thigh.'+side,(s*.325,0,1.45),(s*.36,-.018,.91),'pelvis')
        bone('shin.'+side,(s*.36,-.018,.91),(s*.37,.026,.43),'thigh.'+side)
        bone('foot.'+side,(s*.37,.026,.43),(s*.37,-.37,.17),'shin.'+side)
    for obj,side,fingers,thumb in hands:
        for i,(a,b) in enumerate(fingers): bone('finger_'+str(i+1)+'.'+side,a,b,'hand.'+side)
        bone('thumb.'+side,*thumb,'hand.'+side)
    bpy.ops.object.mode_set(mode='OBJECT')
    for obj,b in rigid_parts: H.rigid(obj,b)
    for obj,kind in flexible:
        if kind.startswith('arm'): H.skin_limb(obj,'upper_arm.'+kind[-1],'forearm.'+kind[-1],1.965)
        elif kind.startswith('leg'): H.skin_limb(obj,'thigh.'+kind[-1],'shin.'+kind[-1],.91)
        elif kind=='shorts':
            groups={n:obj.vertex_groups.new(name=n) for n in ['pelvis','thigh.L','thigh.R']}
            for v in obj.data.vertices:
                p=obj.matrix_world@v.co; w=max(0,min(1,(1.54-p.z)/.34)); side='L' if p.x>0 else 'R'
                groups['pelvis'].add([v.index],1-w,'REPLACE'); groups['thigh.'+side].add([v.index],w,'REPLACE')
            mod=obj.modifiers.new('Shorts deformation','ARMATURE'); mod.object=rig; mod.use_deform_preserve_volume=True; subdiv(obj); obj.parent=rig
        elif kind=='shirt':
            groups={n:obj.vertex_groups.new(name=n) for n in ['chest','upper_arm.L','upper_arm.R']}
            for v in obj.data.vertices:
                p=obj.matrix_world@v.co
                w=max(0,min(1,(abs(p.x)-.49)/.34))*max(0,min(1,(p.z-1.99)/.19))
                w=w*w*(3-2*w)
                groups['chest'].add([v.index],1-w,'REPLACE')
                groups['upper_arm.L' if p.x>0 else 'upper_arm.R'].add([v.index],w,'REPLACE')
            mod=obj.modifiers.new('Shoulder fabric deformation','ARMATURE'); mod.object=rig; mod.use_deform_preserve_volume=True; subdiv(obj,2); obj.parent=rig
    for obj,side,fingers,thumb in hands:
        names=['hand','thumb','finger_1','finger_2','finger_3']; groups={n:obj.vertex_groups.new(name=n+'.'+side) for n in names}
        for v in obj.data.vertices:
            p=obj.matrix_world@v.co
            wt=max(0,min(1,(1.29-abs(p.x))/.115))*max(0,min(1,(1.52-p.z)/.15))
            wf=max(0,min(1,(1.39-p.z)/.14))*(1-wt)
            idx=min(range(3),key=lambda i:abs(p.x-fingers[i][0][0]))
            for name,w in [('hand',1-wt-wf),('thumb',wt),('finger_'+str(idx+1),wf)]:
                if w>0: groups[name].add([v.index],w,'REPLACE')
        mod=obj.modifiers.new('Glove deformation','ARMATURE'); mod.object=rig; mod.use_deform_preserve_volume=True; subdiv(obj); obj.parent=rig
    for p in ['blink_L','blink_R','look_x','look_z']:
        rig[p]=0.; rig.id_properties_ui(p).update(min=0 if 'blink' in p else -1,max=1)
    for side,x,z,objects in eyes:
        for obj in objects:
            H.rigid(obj,'head'); obj.shape_key_add(name='Basis',from_mix=False); k=obj.shape_key_add(name='Blink',from_mix=False)
            for v in k.data:
                p=obj.matrix_world@v.co; p.z=z+(p.z-z)*.01; p.y=-.385+(p.y-obj.location.y)*.10; v.co=obj.matrix_world.inverted()@p
            H.prop_driver(k,'value',None,'blink_'+side,'v')
            if obj!=objects[0]:
                for prop,axis,d in [('look_x',0,.07),('look_z',2,.055)]:
                    k=obj.shape_key_add(name=prop,from_mix=False); k.slider_min=-1
                    for v in k.data: v.co[axis]+=d
                    H.prop_driver(k,'value',None,prop,'v')
        pts=[(x+.245*t,-.36,z+.04*(1-t*t)) for t in [-1+2*i/32 for i in range(33)]]
        lid=sweep('Eye • closed lid.'+side,pts,[.015]*33,navy,sides=12); H.rigid(lid,'head')
        lid.shape_key_add(name='Basis',from_mix=False); k=lid.shape_key_add(name='Blink',from_mix=False)
        for v in k.data: v.co.y=head_front(v.co.x,v.co.z)-.032
        H.prop_driver(k,'value',None,'blink_'+side,'max(0,(v-.68)/.32)')
    for pb in rig.pose.bones: pb.rotation_mode='XYZ'
    rig['version']='ROBI Sport / 1.0'; rig['notes']='Neutral A-pose. Front -Y. Independent head, chest, pelvis. FK limbs/fingers. No IK or lip sync.'
    return rig


def studio(rig):
    H.rig=rig; H.DEST=DEST; H.OUT=OUT; H.build_studio()
    scene=bpy.context.scene
    for name,loc,target,scale in [('Front',(0,-12,2.43),(0,0,2.43),5.75),('ThreeQuarter',(6,-12,5.0),(0,0,2.43),5.8),('Side',(12,0,2.43),(0,0,2.43),5.75),('Back',(0,12,2.43),(0,0,2.43),5.75),('FaceDetail',(3,-12,4.5),(0,0,3.55),3.05)]:
        o=bpy.data.objects['Camera • '+name]; o.location=loc; H.aim(o,target); o.data.ortho_scale=scale
    scene.camera=bpy.data.objects['Camera • ThreeQuarter']; scene.view_settings.exposure=-.38
    for obj in H.studio.objects:
        if obj.type=='LIGHT': obj.data.energy*=1.30; H.aim(obj,(0,0,2.5))
    note=bpy.data.texts.get('START HERE • ROBI'); note.clear()
    note.write('ROBI SPORT\nYellow shirt, navy shorts, sneakers. Neutral A-pose.\nSelect ROBI_SPORT_RIG > Pose Mode. Independent pelvis, chest, neck, head, antenna. FK arms, legs, fingers.\nCustom properties: blink_L/R (0..1), look_x/z (-1..1).\nReference: assets/references/robi-sport-reference.png\nNo background gear, no active animation. No IK or lip-sync rig.\nGenerator: scripts/blender/build_robi_sport.py\n')
    bpy.ops.wm.save_as_mainfile(filepath=str(DEST))


if __name__=='__main__':
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections): bpy.data.collections.remove(c)
    H.geo=bpy.data.collections.new('ROBI | Character'); H.rigcol=bpy.data.collections.new('ROBI | Rig'); H.studio=bpy.data.collections.new('STUDIO | Cameras and lights')
    for c in [H.geo,H.rigcol,H.studio]: bpy.context.scene.collection.children.link(c)
    blue=H.material('Sport / cobalt blue','1469F4',.37,.16)
    trimblue=H.material('Sport / blue detail','277BE7',.43,.08)
    faceblue=H.material('Sport / sky display','62AEF8',.46,.06)
    ice=H.material('Sport / pale blue gloves','90C8FF',.43,.08)
    yellow=H.material('Sport / sunshine yellow','FFD526',.45,.045)
    gold=H.material('Sport / golden seams','EEB915',.53,.015)
    shortmat=H.material('Sport / navy shorts','253651',.64,.0)
    shorttrim=H.material('Sport / navy cuffs','1B2B45',.61,0)
    white=H.material('Sport / eye white','F8FCFF',.30,.08)
    black=H.material('Sport / glossy pupils','070B12',.20,.22)
    navy=H.material('Sport / mouth navy','083A95',.50,.03)
    eyes=build_head(); build_clothes(); build_limbs()
    for obj,bone in rigid_parts:
        if bone.startswith('foot.'): obj.location.z-=.009
    rig=build_rig(eyes)
    from fix_robi_hands import correct_hand_rest
    correct_hand_rest()
    from fix_robi_shirt import fit_shirt_trims
    fit_shirt_trims()
    from robi_screen_face import apply_screen_face
    apply_screen_face()
    studio(rig)
    print('ROBI_SPORT_COMPLETE',str(DEST),flush=True)
