"""Integrated, resolution-independent face graphics on the curved display UVs.

No eye or mouth meshes. Shader controls read the existing animation rig.
Can update an existing Sport file or be called by its generator.
"""
import bpy
from pathlib import Path


def apply_screen_face():
    rig = bpy.data.objects['ROBI_SPORT_RIG']
    panel = next(o for o in bpy.data.objects if o.name.startswith('Face •'))
    for obj in list(bpy.data.objects):
        if obj.name.startswith(('Eye •', 'Mouth •')):
            bpy.data.objects.remove(obj, do_unlink=True)
    panel.name = 'Face • integrated display'
    uv = panel.data.uv_layers.get('ScreenUV') or panel.data.uv_layers.new(name='ScreenUV')
    for loop in panel.data.loops:
        p = panel.data.vertices[loop.vertex_index].co
        uv.data[loop.index].uv = (p.x, p.z)

    mat = bpy.data.materials.get('Sport / animated screen') or bpy.data.materials.new('Sport / animated screen')
    mat.use_nodes = True
    mat.diffuse_color = (.12, .40, .90, 1)
    nodes = mat.node_tree.nodes; nodes.clear(); links = mat.node_tree.links
    def node(kind, label):
        n = nodes.new(kind); n.name = label; n.label = label
        return n
    def feed(socket, value):
        if hasattr(value, 'node'): links.new(value, socket)
        else: socket.default_value = value
    def calc(op, a, b=0, label=None):
        n = node('ShaderNodeMath', label or op); n.operation = op
        feed(n.inputs[0], a); feed(n.inputs[1], b)
        return n.outputs[0]
    def blend(a, b, mask, label):
        n = node('ShaderNodeMixRGB', label); n.blend_type = 'MIX'
        feed(n.inputs[0], mask); feed(n.inputs[1], a); feed(n.inputs[2], b)
        return n.outputs[0]
    def control(prop):
        n = node('ShaderNodeValue', 'Control / '+prop)
        f = n.outputs[0].driver_add('default_value'); d = f.driver
        d.type = 'SUM'; v = d.variables.new(); v.name = 'v'; v.type = 'SINGLE_PROP'
        v.targets[0].id = rig; v.targets[0].data_path = '["'+prop+'"]'
        return n.outputs[0]
    tex = node('ShaderNodeUVMap', 'Stable display coordinates'); tex.uv_map = 'ScreenUV'
    xyz = node('ShaderNodeSeparateXYZ', 'Display X / Z'); links.new(tex.outputs['UV'], xyz.inputs[0])
    x, z = xyz.outputs['X'], xyz.outputs['Y']
    def oval(cx, cz, rx, rz, label):
        dx = calc('DIVIDE', calc('SUBTRACT', x, cx), rx)
        dz = calc('DIVIDE', calc('SUBTRACT', z, cz), rz)
        dist = calc('SQRT', calc('ADD', calc('MULTIPLY', dx, dx), calc('MULTIPLY', dz, dz)))
        edge = node('ShaderNodeMapRange', label); edge.clamp = True; edge.interpolation_type = 'SMOOTHSTEP'
        feed(edge.inputs['Value'], dist)
        edge.inputs['From Min'].default_value = .985; edge.inputs['From Max'].default_value = 1.015
        edge.inputs['To Min'].default_value = 1; edge.inputs['To Max'].default_value = 0
        return edge.outputs[0]
    def clamp(a): return calc('MINIMUM', calc('MAXIMUM', a, 0), 1)

    # Mascot-blue display with white eyes. All graphics share the same surface.
    gradient = clamp(calc('MULTIPLY', calc('SUBTRACT', z, 3.02), .85))
    color = blend((.08,.29,.74,1), (.14,.43,.92,1), gradient, 'Mascot sky blue display field')
    eye_ink = (.94,.975,1,1)
    lookx = calc('MULTIPLY', control('look_x'), .08)
    lookz = calc('MULTIPLY', control('look_z'), .055)
    for s, side in [(1,'L'),(-1,'R')]:
        cx = s*.458; cz = 3.66
        blink = control('blink_'+side)
        height = calc('MAXIMUM', calc('MULTIPLY', calc('SUBTRACT',1,blink), .300), .016, 'Eye height / '+side)
        eye = oval(cx, cz, .277, height, 'Eye silhouette / '+side)
        color = blend(color, eye_ink, eye, 'Draw eye / '+side)
        px = calc('ADD', cx, lookx); pz = calc('ADD', cz, lookz)
        pupil = calc('MULTIPLY', oval(px,pz,.137,.177,'Pupil / '+side), eye)
        pupil = calc('MULTIPLY', pupil, clamp(calc('MULTIPLY',calc('SUBTRACT',1,blink),8)))
        color = blend(color,(.004,.007,.012,1),pupil,'Draw pupil / '+side)
        glint = oval(calc('SUBTRACT',px,.039),calc('ADD',pz,.068),.037,.041,'Graphic catchlight / '+side)
        glint = calc('MULTIPLY', glint, pupil)
        color = blend(color,(.91,1,1,1),glint,'Draw catchlight / '+side)
    # A straight, round-ended mouth is the rest state. Smile bends that same
    # stroke smoothly upward at its corners, rather than crossfading drawings.
    rig['smile'] = 0.
    rig.id_properties_ui('smile').update(min=0., max=1., description='0: neutral mouth; 1: closed smile')
    smile = control('smile')
    nearest_x = calc('MINIMUM',calc('MAXIMUM',x,-.18),.18)
    curve = calc('ADD',3.19,calc('MULTIPLY',smile,calc('MULTIPLY',1.7,calc('MULTIPLY',nearest_x,nearest_x))))
    dx = calc('SUBTRACT',x,nearest_x); dz = calc('SUBTRACT',z,curve)
    distance = calc('SQRT',calc('ADD',calc('MULTIPLY',dx,dx),calc('MULTIPLY',dz,dz)))
    mouth = node('ShaderNodeMapRange','Neutral mouth / soft edge')
    mouth.clamp = True; mouth.interpolation_type = 'SMOOTHSTEP'
    feed(mouth.inputs['Value'],distance)
    mouth.inputs['From Min'].default_value = .012
    mouth.inputs['From Max'].default_value = .016
    mouth.inputs['To Min'].default_value = 1
    mouth.inputs['To Max'].default_value = 0
    color = blend(color,(.006,.039,.16,1),mouth.outputs[0],'Draw neutral mouth')
    # Very subtle display scanlines, intentionally invisible at normal distance.
    line = calc('ADD',.993,calc('MULTIPLY',calc('SINE',calc('MULTIPLY',z,2100)),.007))
    color = blend((0,0,0,1),color,line,'Subtle display scanlines')
    bsdf = node('ShaderNodeBsdfPrincipled', 'Single glossy display surface')
    feed(bsdf.inputs['Base Color'],color); feed(bsdf.inputs['Emission Color'],color)
    bsdf.inputs['Emission Strength'].default_value = .12
    bsdf.inputs['Roughness'].default_value = .32
    bsdf.inputs['Specular IOR Level'].default_value = .18
    bsdf.inputs['Coat Weight'].default_value = .12
    bsdf.inputs['Coat Roughness'].default_value = .20
    out = node('ShaderNodeOutputMaterial','Screen output'); links.new(bsdf.outputs[0],out.inputs['Surface'])
    # Arrange a large but fully editable graph by dependency depth.
    depth = {}
    for n in nodes:
        depth[n.name] = max((depth.get(link.from_node.name,0)+1 for inp in n.inputs for link in inp.links),default=0)
    rows = {}
    for n in nodes:
        d = depth[n.name]; row = rows.get(d,0); rows[d] = row+1
        n.location = (d*220,-row*190); n.width = 195
    panel.data.materials.clear(); panel.data.materials.append(mat)
    rig['version'] = 'ROBI Sport / 1.2 mascot screen, neutral mouth'
    rig['face_style'] = 'Sky-blue mascot screen; white eyes; neutral mouth at smile=0; flat UV graphics'
    for p in ['blink_L','blink_R','look_x','look_z','smile']: rig[p] = 0.
    note = bpy.data.texts.get('START HERE • ROBI')
    if note:
        note.write('\nFACE 1.2: Sky-blue mascot display with flat white eyes and a neutral closed mouth.\nsmile=0 is neutral; smile=1 is a closed smile. Blink and gaze controls preserved.\nMaterial: Sport / animated screen, ScreenUV. No external textures or Python handlers.\n')
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    return panel


if __name__ == '__main__':
    apply_screen_face()
    root = Path(__file__).resolve().parents[2]
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'assets/3d/robi_sport_neutral.blend'))
    print('SCREEN_FACE_COMPLETE', flush=True)
