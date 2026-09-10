"""Six-second greeting, baked FK animation and animated display controls."""
import bpy, math
from pathlib import Path
from mathutils import Vector, Matrix, Quaternion
ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'assets/3d/robi_greeting.blend'
OUT=ROOT/'out/robi-greeting'; OUT.mkdir(parents=True,exist_ok=True)

def smooth(a,b,f):
    t=max(0.,min(1.,(f-a)/(b-a)))
    return t*t*t*(t*(t*6-15)+10)
def pulse(a,b,c,d,f): return smooth(a,b,f)*(1-smooth(c,d,f))

def create_greeting():
    r=bpy.data.objects['ROBI_SPORT_RIG']; s=bpy.context.scene
    r.animation_data_clear()
    for driver in bpy.data.materials['Sport / animated screen'].node_tree.animation_data.drivers:
        driver.driver.type='SUM'
    for b in r.pose.bones:
        b.rotation_mode='QUATERNION'; b.location=(0,0,0); b.rotation_quaternion=(1,0,0,0); b.scale=(1,1,1)
    rest={b.name:b.matrix_local.copy() for b in r.data.bones}
    upper=r.data.bones['upper_arm.L']; lower=r.data.bones['forearm.L']; hand=r.data.bones['hand.L']
    shoulder=upper.head_local.copy(); wrist=Vector((1.40,-.36,2.82))
    reach=wrist-shoulder; d=reach.length; axis=reach.normalized()
    l1=upper.length; l2=lower.length
    a=(d*d+l1*l1-l2*l2)/(2*d); h=math.sqrt(max(0,l1*l1-a*a))
    pole=Vector((1,0,-.5)); pole=(pole-axis*pole.dot(axis)).normalized()
    elbow=shoulder+axis*a+pole*h
    def aim(bone,direction):
        return (bone.tail_local-bone.head_local).normalized().rotation_difference(direction.normalized())@bone.matrix_local.to_quaternion()
    peak_upper=aim(upper,elbow-shoulder); peak_lower=aim(lower,wrist-elbow)
    # Face the palm toward the viewer, with thumb toward the character's head.
    hand_axis=Vector((.05,-.05,1)).normalized()
    initial=(hand.tail_local-hand.head_local).normalized().rotation_difference(hand_axis)
    thumb=initial@(r.data.bones['thumb.L'].head_local-hand.tail_local)
    thumb=(thumb-hand_axis*thumb.dot(hand_axis)).normalized()
    goal=Vector((-1,0,0)); goal=(goal-hand_axis*goal.dot(hand_axis)).normalized()
    roll=math.atan2(hand_axis.dot(thumb.cross(goal)),thumb.dot(goal))
    peak_hand=Quaternion(hand_axis,roll)@initial@hand.matrix_local.to_quaternion()
    animated=['chest','head','antenna','upper_arm.L','forearm.L','hand.L','upper_arm.R','forearm.R',
              'finger_1.L','finger_2.L','finger_3.L','thumb.L']
    props=['blink_L','blink_R','look_x','look_z','smile']
    previous={}
    for f in range(1,182):
        s.frame_set(f)
        lift=pulse(22,65,126,167,f)
        present=pulse(8,50,130,177,f)
        wave_window=pulse(62,74,114,129,f)
        wave=math.sin((f-70)*math.tau/22)*wave_window
        # Feet and pelvis stay planted. Motion is a small upper-body greeting.
        chest=r.pose.bones['chest']
        chest.rotation_quaternion=Quaternion((0,0,1),-.023*present)@Quaternion((1,0,0),.025*present)
        r.pose.bones['head'].rotation_quaternion=Quaternion((1,0,0),.04*present+.018*math.sin((f-25)*math.tau/90)*present)@Quaternion((0,0,1),-.035*present)
        r.pose.bones['antenna'].rotation_quaternion=Quaternion((1,0,0),.035*math.sin((f-18)*math.tau/37)*present)
        bpy.context.view_layer.update()
        chest_delta=chest.matrix@rest['chest'].inverted()
        q_upper=rest['upper_arm.L'].to_quaternion().slerp(peak_upper,lift)
        q_lower=rest['forearm.L'].to_quaternion().slerp(peak_lower,lift)
        q_lower=Quaternion((0,1,0),.065*wave)@q_lower
        q_hand=rest['hand.L'].to_quaternion().slerp(peak_hand,pulse(25,67,127,169,f))
        q_hand=Quaternion((0,1,0),.19*wave)@q_hand
        p=shoulder.copy()
        for name,q,length in [('upper_arm.L',q_upper,l1),('forearm.L',q_lower,l2),('hand.L',q_hand,hand.length)]:
            pb=r.pose.bones[name]
            pb.matrix=chest_delta@Matrix.LocRotScale(p,q,Vector((1,1,1)))
            pb.location=(0,0,0); pb.scale=(1,1,1)
            p=p+q@Vector((0,length,0))
            bpy.context.view_layer.update()
        r.pose.bones['upper_arm.R'].rotation_quaternion=Quaternion((0,0,1),.028*present)
        r.pose.bones['forearm.R'].rotation_quaternion=Quaternion((1,0,0),.04*present)
        for j in range(1,4):
            r.pose.bones['finger_'+str(j)+'.L'].rotation_quaternion=Quaternion((1,0,0),.035*lift+(.010*math.sin((f-70)*math.tau/22+j)*wave_window))
        r.pose.bones['thumb.L'].rotation_quaternion=Quaternion((1,0,0),-.06*lift)
        for name in animated:
            pb=r.pose.bones[name]; q=pb.rotation_quaternion.copy()
            if name in previous and q.dot(previous[name])<0: q.negate()
            if f in [1,181]: q=Quaternion()
            pb.rotation_quaternion=q; previous[name]=q.copy()
            pb.keyframe_insert(data_path='rotation_quaternion',frame=f,group=name)
        blink=pulse(13,16,17,21,f)+pulse(132,135,136,140,f)
        r['blink_L']=blink; r['blink_R']=blink
        r['look_x']=.10*pulse(23,43,118,150,f); r['look_z']=.08*present
        r['smile']=.85*pulse(14,48,135,176,f)
        for prop in props: r.keyframe_insert(data_path='["'+prop+'"]',frame=f,group='Screen expressions')
    action=r.animation_data.action; action.name='ROBI • Friendly greeting • 6 seconds'; action.use_fake_user=True
    # Dense FK samples use linear interpolation; the analytic motion itself has
    # zero-speed, zero-acceleration ease at every entrance and exit.
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points: key.interpolation='LINEAR'
    s.render.fps=30; s.frame_start=1; s.frame_end=180
    for marker in list(s.timeline_markers): s.timeline_markers.remove(marker)
    for name,frame in [('Neutral',1),('Anticipation',18),('Raise hand',35),('Wave',76),('Lower hand',130),('Neutral return',180)]:
        s.timeline_markers.new(name,frame=frame)
    s.camera=bpy.data.objects['Camera • ThreeQuarter']
    s.camera.location=(3,-12,4.4)
    s.camera.rotation_euler=(Vector((0,0,2.45))-s.camera.location).to_track_quat('-Z','Y').to_euler()
    s.camera.data.ortho_scale=5.85
    s.render.engine='BLENDER_EEVEE'; s.render.resolution_x=960; s.render.resolution_y=960; s.render.resolution_percentage=100
    s.eevee.taa_render_samples=32
    s.eevee.shadow_ray_count=2
    s.render.image_settings.file_format='PNG'; s.render.filepath=str(OUT/'frames'/'frame_')
    s['greeting_notes']='6 sec, 30 fps; planted feet; wave with head, antenna, blink and smile. Frame 1 and 181 are neutral.'
    s.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(DEST))
    print('GREETING_CREATED',str(DEST),flush=True)

if __name__=='__main__': create_greeting()
