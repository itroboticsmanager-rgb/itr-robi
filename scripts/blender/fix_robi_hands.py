"""Correct the glove and finger rest frames: straight wrists, thumbs forward."""
import bpy, math
from mathutils import Vector, Matrix
from pathlib import Path


def correct_hand_rest():
    rig=bpy.data.objects['ROBI_SPORT_RIG']
    if rig.get('natural_hand_rest'): return []
    if any(b.matrix_basis!=Matrix.Identity(4) for b in rig.pose.bones):
        raise RuntimeError('Apply this rest correction in the neutral pose.')
    transforms={}; report=[]
    for side in ['L','R']:
        hand=rig.data.bones['hand.'+side]; forearm=rig.data.bones['forearm.'+side]
        wrist=hand.head_local.copy()
        axis=(forearm.tail_local-forearm.head_local).normalized()
        align=(hand.tail_local-hand.head_local).normalized().rotation_difference(axis).to_matrix()
        thumb=rig.data.bones['thumb.'+side]
        across=align@(thumb.head_local-hand.tail_local)
        across=(across-axis*across.dot(axis)).normalized()
        forward=Vector((0,-1,0)); forward=(forward-axis*forward.dot(axis)).normalized()
        angle=math.atan2(axis.dot(across.cross(forward)),across.dot(forward))
        rotation=Matrix.Rotation(angle,3,axis)@align
        delta=Matrix.Translation(wrist)@rotation.to_4x4()@Matrix.Translation(-wrist)
        transforms[side]=delta
        obj=bpy.data.objects['Hand • glove.'+side]
        world_delta=rig.matrix_world@delta@rig.matrix_world.inverted()
        obj.data.transform(obj.matrix_world.inverted()@world_delta@obj.matrix_world)
        obj.data.update()
        report.append({'side':side,'axial_correction_degrees':round(math.degrees(angle),2)})
    selected=list(bpy.context.selected_objects); active=bpy.context.view_layer.objects.active
    bpy.ops.object.select_all(action='DESELECT'); rig.select_set(True); bpy.context.view_layer.objects.active=rig
    bpy.ops.object.mode_set(mode='EDIT')
    for side,delta in transforms.items():
        for prefix in ['hand','thumb','finger_1','finger_2','finger_3']:
            rig.data.edit_bones[prefix+'.'+side].transform(delta)
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in selected: obj.select_set(True)
    bpy.context.view_layer.objects.active=active
    rig['natural_hand_rest']=True
    rig['hand_rest_notes']='Wrists aligned with forearms; thumbs toward front (-Y); mesh and finger rest bones corrected together. Pose rotations remain zero.'
    bpy.context.view_layer.update()
    return report


if __name__=='__main__':
    print('HAND_REST_CORRECTION',correct_hand_rest())
    root=Path(__file__).resolve().parents[2]
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'assets/3d/robi_sport_neutral.blend'))
