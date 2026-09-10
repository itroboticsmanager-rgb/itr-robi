"""Build the canonical ROBI mascot and render review views in Blender.

Run with:
    blender --background --python scripts/blender/build_robi.py

The file is intentionally procedural so proportions, materials, cameras, and
future animation anchors stay reproducible while the character is art-directed.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "out" / "robi-3d"
BLEND_PATH = ROOT / "assets" / "3d" / "robi_master.blend"


def srgb(hex_color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = hex_color.lstrip("#")
    rgb = [int(value[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    return (*rgb, alpha)


def signed_power(value: float, exponent: float) -> float:
    if abs(value) < 1e-10:
        return 0.0
    return math.copysign(abs(value) ** exponent, value)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def create_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if collection.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(collection)
    return collection


def move_to_collection(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for current in list(obj.users_collection):
        current.objects.unlink(obj)
    collection.objects.link(obj)


def set_input(node: bpy.types.Node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    roughness: float,
    metallic: float = 0.0,
    coat: float = 0.0,
    emission: tuple[float, float, float, float] | None = None,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = color
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    set_input(bsdf, "Base Color", color)
    set_input(bsdf, "Metallic", metallic)
    set_input(bsdf, "Roughness", roughness)
    set_input(bsdf, "Coat Weight", coat)
    set_input(bsdf, "Coat Roughness", max(0.05, roughness * 0.55))
    if emission is not None:
        set_input(bsdf, "Emission Color", emission)
        set_input(bsdf, "Emission Strength", emission_strength)
    return mat


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.append(mat)


def smooth_mesh(obj: bpy.types.Object) -> None:
    if obj.type != "MESH":
        return
    for polygon in obj.data.polygons:
        polygon.use_smooth = True


def create_superellipsoid(
    name: str,
    scale: tuple[float, float, float],
    location: tuple[float, float, float],
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    latitude_exponent: float = 0.62,
    longitude_exponent: float = 0.62,
    segments: int = 96,
    rings: int = 48,
) -> bpy.types.Object:
    a, b, c = scale
    vertices: list[tuple[float, float, float]] = [(0.0, 0.0, -c)]
    for ring in range(1, rings):
        latitude = -math.pi / 2 + math.pi * ring / rings
        ct = signed_power(math.cos(latitude), latitude_exponent)
        st = signed_power(math.sin(latitude), latitude_exponent)
        for segment in range(segments):
            longitude = -math.pi + 2 * math.pi * segment / segments
            vertices.append(
                (
                    a * ct * signed_power(math.cos(longitude), longitude_exponent),
                    b * ct * signed_power(math.sin(longitude), longitude_exponent),
                    c * st,
                )
            )
    top_index = len(vertices)
    vertices.append((0.0, 0.0, c))

    faces: list[tuple[int, ...]] = []
    first_ring = 1
    for segment in range(segments):
        nxt = (segment + 1) % segments
        faces.append((0, first_ring + nxt, first_ring + segment))

    for ring in range(rings - 2):
        lower = 1 + ring * segments
        upper = lower + segments
        for segment in range(segments):
            nxt = (segment + 1) % segments
            faces.append((lower + segment, lower + nxt, upper + nxt, upper + segment))

    last_ring = 1 + (rings - 2) * segments
    for segment in range(segments):
        nxt = (segment + 1) % segments
        faces.append((last_ring + segment, last_ring + nxt, top_index))

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    assign_material(obj, mat)
    smooth_mesh(obj)
    return obj


def create_squircle_panel(
    name: str,
    scale: tuple[float, float],
    depth: float,
    location: tuple[float, float, float],
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    exponent: float = 0.43,
    segments: int = 128,
) -> bpy.types.Object:
    width, height = scale
    vertices: list[tuple[float, float, float]] = []
    for y in (-depth / 2, depth / 2):
        for segment in range(segments):
            angle = 2 * math.pi * segment / segments
            vertices.append(
                (
                    width * signed_power(math.cos(angle), exponent),
                    y,
                    height * signed_power(math.sin(angle), exponent),
                )
            )

    faces: list[tuple[int, ...]] = []
    faces.append(tuple(reversed(range(segments))))
    faces.append(tuple(range(segments, segments * 2)))
    for segment in range(segments):
        nxt = (segment + 1) % segments
        faces.append((segment, nxt, segments + nxt, segments + segment))

    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.location = location
    assign_material(obj, mat)

    bevel = obj.modifiers.new("Soft edge", "BEVEL")
    bevel.width = 0.105
    bevel.segments = 6
    bevel.limit_method = "ANGLE"
    return obj


def create_uv_sphere(
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    segments: int = 64,
    rings: int = 32,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    move_to_collection(obj, collection)
    assign_material(obj, mat)
    smooth_mesh(obj)
    return obj


def create_curve(
    name: str,
    points: list[tuple[float, float, float]],
    radius: float,
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    resolution: int = 16,
) -> bpy.types.Object:
    curve_data = bpy.data.curves.new(f"{name}_Curve", "CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = resolution
    curve_data.bevel_resolution = 6
    curve_data.bevel_depth = radius
    curve_data.use_fill_caps = True
    spline = curve_data.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve_data)
    collection.objects.link(obj)
    assign_material(obj, mat)
    return obj


def create_capsule(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    radius: float,
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    objects = [create_curve(name, [start, end], radius, mat, collection, resolution=8)]
    objects.append(create_uv_sphere(f"{name}_Start", start, (radius, radius, radius), mat, collection, segments=32, rings=16))
    objects.append(create_uv_sphere(f"{name}_End", end, (radius, radius, radius), mat, collection, segments=32, rings=16))
    return objects


def create_smile(
    name: str,
    location_y: float,
    z: float,
    width: float,
    depth: float,
    mat: bpy.types.Material,
    collection: bpy.types.Collection,
) -> list[bpy.types.Object]:
    radius = 0.048
    points = [
        (-width / 2, location_y, z),
        (-width * 0.24, location_y - 0.008, z - depth * 0.72),
        (0.0, location_y - 0.012, z - depth),
        (width * 0.24, location_y - 0.008, z - depth * 0.72),
        (width / 2, location_y, z),
    ]
    curve = create_curve(
        name,
        points,
        radius,
        mat,
        collection,
        resolution=24,
    )
    left_cap = create_uv_sphere(
        f"{name}_Cap_L",
        points[0],
        (radius, radius * 0.72, radius),
        mat,
        collection,
        segments=32,
        rings=16,
    )
    right_cap = create_uv_sphere(
        f"{name}_Cap_R",
        points[-1],
        (radius, radius * 0.72, radius),
        mat,
        collection,
        segments=32,
        rings=16,
    )
    return [curve, left_cap, right_cap]


def create_empty(name: str, location: tuple[float, float, float], collection: bpy.types.Collection) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "CIRCLE"
    obj.empty_display_size = 0.3
    obj.location = location
    collection.objects.link(obj)
    return obj


def parent_many(parent: bpy.types.Object, objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        parent_keep_transform(obj, parent)


def parent_keep_transform(child: bpy.types.Object, parent: bpy.types.Object) -> None:
    bpy.context.view_layer.update()
    world_matrix = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    child.matrix_world = world_matrix
    bpy.context.view_layer.update()


def create_area_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
    target: tuple[float, float, float],
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.shape = "DISK"
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    aim_at(obj, target)
    return obj


def aim_at(obj: bpy.types.Object, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_camera(
    name: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float],
    lens: float,
) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    aim_at(obj, target)
    return obj


def add_reference_images(collection: bpy.types.Collection) -> None:
    reference_paths = [
        ROOT / "assets" / "references" / "robi-reference-front-flat.png",
        ROOT / "assets" / "references" / "robi-reference-3d-extended-arm.png",
        ROOT / "assets" / "references" / "robi-reference-3d-anniversary.png",
    ]
    for index, path in enumerate(reference_paths):
        image = bpy.data.images.load(str(path), check_existing=True)
        obj = bpy.data.objects.new(f"REF_{path.stem}", None)
        obj.empty_display_type = "IMAGE"
        obj.data = image
        obj.empty_display_size = 4.0
        obj.color[3] = 0.45
        obj.hide_render = True
        obj.hide_viewport = True
        obj.location = (8.0 + index * 4.5, 2.0, 3.0)
        collection.objects.link(obj)


def setup_world() -> None:
    scene = bpy.context.scene
    world = bpy.data.worlds.new("ROBI Studio World") if not scene.world else scene.world
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = srgb("DDEBFF")
    background.inputs["Strength"].default_value = 0.20

    floor_mat = material("Studio Floor", srgb("E9F2FF"), roughness=0.72)
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -0.22))
    floor = bpy.context.object
    floor.name = "Studio_Floor"
    assign_material(floor, floor_mat)

    create_area_light("Key_Softbox", (-5.5, -7.0, 8.0), 760, 5.0, (0.88, 0.94, 1.0), (0, 0, 2.4))
    create_area_light("Fill_Softbox", (5.5, -4.0, 4.0), 410, 4.0, (0.72, 0.86, 1.0), (0, 0, 2.3))
    create_area_light("Rim_Light", (3.5, 3.0, 7.0), 760, 3.0, (0.24, 0.58, 1.0), (0, 0, 2.8))
    create_area_light("Face_Card", (0.0, -5.0, 3.1), 190, 2.2, (1.0, 0.94, 0.84), (0, 0, 2.5))


def build_robi() -> dict[str, bpy.types.Object]:
    geo = create_collection("ROBI_Geometry")
    rig = create_collection("ROBI_Controls")
    refs = create_collection("ROBI_References")

    blue = material("ROBI Blue Plastic", srgb("0868E8"), roughness=0.23, coat=0.42)
    blue_dark = material("ROBI Blue Shadow", srgb("0347A9"), roughness=0.27, coat=0.32)
    cyan = material("ROBI Face Glass", srgb("4FA8F7"), roughness=0.20, coat=0.58)
    cyan_soft = material("ROBI Soft Cyan", srgb("8CCBFF"), roughness=0.31, coat=0.28)
    white = material("ROBI Eye White", srgb("FFFDF8"), roughness=0.18, coat=0.35)
    pupil = material("ROBI Pupil Glass", srgb("071329"), roughness=0.08, metallic=0.04, coat=0.74)
    navy = material("ROBI Smile", srgb("032B70"), roughness=0.42, coat=0.06)
    glow = material(
        "ROBI Catchlight",
        srgb("FFFFFF"),
        roughness=0.08,
        emission=srgb("DDF6FF"),
        emission_strength=1.8,
    )

    ctrl_root = create_empty("CTRL_ROBI_ROOT", (0, 0, 0), rig)
    ctrl_body = create_empty("CTRL_BODY", (0, 0, 2.4), rig)
    ctrl_face = create_empty("CTRL_FACE", (0, -0.9, 2.55), rig)
    parent_keep_transform(ctrl_body, ctrl_root)
    parent_keep_transform(ctrl_face, ctrl_body)

    body = create_superellipsoid(
        "ROBI_Body",
        (2.48, 0.78, 1.58),
        (0, 0, 2.42),
        blue,
        geo,
        latitude_exponent=0.53,
        longitude_exponent=0.50,
    )
    parent_keep_transform(body, ctrl_body)

    bezel = create_squircle_panel("ROBI_FaceBezel", (2.02, 0.89), 0.14, (0, -0.765, 2.57), blue_dark, geo)
    parent_keep_transform(bezel, ctrl_face)
    panel = create_squircle_panel("ROBI_FacePanel", (1.92, 0.80), 0.15, (0, -0.84, 2.57), cyan, geo)
    parent_keep_transform(panel, ctrl_face)

    eye_objects: list[bpy.types.Object] = []
    for side, x in (("L", -0.82), ("R", 0.82)):
        ctrl_eye = create_empty(f"CTRL_EYE_{side}", (x, -1.0, 2.67), rig)
        parent_keep_transform(ctrl_eye, ctrl_face)
        eye_white = create_superellipsoid(
            f"EyeWhite_{side}",
            (0.59, 0.115, 0.67),
            (x, -0.965, 2.66),
            white,
            geo,
            latitude_exponent=1.0,
            longitude_exponent=1.0,
            segments=64,
            rings=36,
        )
        iris = create_superellipsoid(
            f"Pupil_{side}",
            (0.365, 0.085, 0.445),
            (x, -1.085, 2.65),
            pupil,
            geo,
            latitude_exponent=1.0,
            longitude_exponent=1.0,
            segments=64,
            rings=36,
        )
        highlight = create_uv_sphere(
            f"Catchlight_Main_{side}",
            (x - 0.13, -1.175, 2.84),
            (0.105, 0.035, 0.135),
            glow,
            geo,
            segments=40,
            rings=20,
        )
        highlight_small = create_uv_sphere(
            f"Catchlight_Small_{side}",
            (x + 0.16, -1.176, 2.51),
            (0.047, 0.025, 0.057),
            glow,
            geo,
            segments=32,
            rings=16,
        )
        parent_many(ctrl_eye, [eye_white, iris, highlight, highlight_small])
        eye_objects.extend([eye_white, iris, highlight, highlight_small])

    smile_parts = create_smile("Mouth_Happy", -1.15, 2.13, 0.56, 0.13, navy, geo)
    parent_many(ctrl_face, smile_parts)

    left_ear = create_superellipsoid("EarPad_L", (0.25, 0.50, 0.52), (-2.56, -0.01, 2.44), cyan_soft, geo)
    right_ear = create_superellipsoid("EarPad_R", (0.25, 0.50, 0.52), (2.56, -0.01, 2.44), cyan_soft, geo)
    left_ring = create_superellipsoid("EarRing_L", (0.13, 0.55, 0.39), (-2.43, 0.0, 2.44), blue_dark, geo)
    right_ring = create_superellipsoid("EarRing_R", (0.13, 0.55, 0.39), (2.43, 0.0, 2.44), blue_dark, geo)
    parent_many(ctrl_body, [left_ear, right_ear, left_ring, right_ring])

    antenna = create_curve("Antenna_Stem", [(0, 0.0, 3.96), (-0.03, 0.0, 4.35), (-0.10, -0.02, 4.57)], 0.105, blue_dark, geo)
    antenna_tip = create_uv_sphere("Antenna_Tip", (-0.11, -0.02, 4.77), (0.25, 0.25, 0.27), cyan_soft, geo)
    parent_many(ctrl_body, [antenna, antenna_tip])

    ctrl_arm_l = create_empty("CTRL_ARM_L", (-2.45, 0, 2.35), rig)
    ctrl_arm_r = create_empty("CTRL_ARM_R", (2.45, 0, 2.70), rig)
    parent_keep_transform(ctrl_arm_l, ctrl_body)
    parent_keep_transform(ctrl_arm_r, ctrl_body)

    arm_l = create_curve(
        "Arm_L",
        [(-2.42, 0.06, 2.40), (-3.05, 0.04, 2.10), (-3.24, -0.03, 1.68), (-2.91, -0.12, 1.48)],
        0.19,
        blue,
        geo,
    )
    hand_l = create_superellipsoid(
        "Palm_L",
        (0.39, 0.27, 0.38),
        (-2.84, -0.18, 1.18),
        cyan_soft,
        geo,
        latitude_exponent=0.78,
        longitude_exponent=0.78,
        segments=64,
        rings=36,
    )
    wrist_l = create_superellipsoid(
        "WristCuff_L",
        (0.23, 0.29, 0.21),
        (-2.91, -0.10, 1.48),
        cyan_soft,
        geo,
        latitude_exponent=0.82,
        longitude_exponent=0.82,
        segments=48,
        rings=28,
    )
    fingers_l: list[bpy.types.Object] = []
    fingers_l += create_capsule("Finger_Index_L", (-3.08, -0.22, 0.90), (-3.12, -0.22, 0.46), 0.108, cyan_soft, geo)
    fingers_l += create_capsule("Finger_Middle_L", (-2.91, -0.23, 0.88), (-2.92, -0.23, 0.38), 0.116, cyan_soft, geo)
    fingers_l += create_capsule("Finger_Ring_L", (-2.74, -0.23, 0.88), (-2.70, -0.23, 0.42), 0.111, cyan_soft, geo)
    fingers_l += create_capsule("Finger_Pinky_L", (-2.58, -0.22, 0.91), (-2.49, -0.22, 0.52), 0.098, cyan_soft, geo)
    fingers_l += create_capsule("Thumb_L", (-3.14, -0.23, 1.20), (-3.40, -0.23, 0.90), 0.113, cyan_soft, geo)
    parent_many(ctrl_arm_l, [arm_l, wrist_l, hand_l, *fingers_l])

    arm_r = create_curve(
        "Arm_R",
        [(2.42, 0.05, 2.75), (2.92, 0.02, 3.22), (3.18, -0.02, 3.88), (3.18, -0.08, 4.30)],
        0.19,
        blue,
        geo,
    )
    palm_r = create_superellipsoid(
        "Palm_R",
        (0.39, 0.25, 0.43),
        (3.18, -0.10, 4.52),
        cyan_soft,
        geo,
        latitude_exponent=0.72,
        longitude_exponent=0.72,
        segments=64,
        rings=36,
    )
    fingers: list[bpy.types.Object] = []
    fingers += create_capsule("Finger_Index_R", (2.96, -0.11, 4.72), (2.89, -0.11, 5.24), 0.125, cyan_soft, geo)
    fingers += create_capsule("Finger_Middle_R", (3.13, -0.11, 4.79), (3.14, -0.11, 5.38), 0.132, cyan_soft, geo)
    fingers += create_capsule("Finger_Ring_R", (3.31, -0.11, 4.77), (3.39, -0.11, 5.29), 0.124, cyan_soft, geo)
    fingers += create_capsule("Finger_Pinky_R", (3.46, -0.11, 4.67), (3.59, -0.11, 5.08), 0.11, cyan_soft, geo)
    fingers += create_capsule("Thumb_R", (2.92, -0.13, 4.45), (2.66, -0.13, 4.67), 0.125, cyan_soft, geo)
    parent_many(ctrl_arm_r, [arm_r, palm_r, *fingers])

    ctrl_leg_l = create_empty("CTRL_LEG_L", (-1.18, 0, 0.80), rig)
    ctrl_leg_r = create_empty("CTRL_LEG_R", (1.18, 0, 0.80), rig)
    parent_keep_transform(ctrl_leg_l, ctrl_body)
    parent_keep_transform(ctrl_leg_r, ctrl_body)
    leg_l = create_curve("Leg_L", [(-1.18, 0.04, 0.95), (-1.23, 0.02, 0.42), (-1.31, -0.02, 0.18)], 0.18, blue, geo)
    leg_r = create_curve("Leg_R", [(1.18, 0.04, 0.95), (1.23, 0.02, 0.42), (1.31, -0.02, 0.18)], 0.18, blue, geo)
    shoe_l = create_superellipsoid(
        "Shoe_L",
        (0.59, 0.66, 0.29),
        (-1.40, -0.12, 0.05),
        cyan_soft,
        geo,
        latitude_exponent=0.66,
        longitude_exponent=0.60,
        segments=64,
        rings=36,
    )
    shoe_r = create_superellipsoid(
        "Shoe_R",
        (0.59, 0.66, 0.29),
        (1.40, -0.12, 0.05),
        cyan_soft,
        geo,
        latitude_exponent=0.66,
        longitude_exponent=0.60,
        segments=64,
        rings=36,
    )
    parent_many(ctrl_leg_l, [leg_l, shoe_l])
    parent_many(ctrl_leg_r, [leg_r, shoe_r])

    add_reference_images(refs)
    return {"root": ctrl_root, "body": ctrl_body, "face": ctrl_face}


def configure_render() -> None:
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.render.use_file_extension = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.45


def render_views() -> None:
    scene = bpy.context.scene
    cameras = [
        ("robi_front", create_camera("CAM_Front", (0.0, -14.8, 3.0), (0.0, 0.0, 2.55), 58)),
        ("robi_three_quarter", create_camera("CAM_ThreeQuarter", (7.7, -13.8, 5.8), (0.0, 0.0, 2.55), 63)),
        ("robi_face", create_camera("CAM_Face", (0.0, -6.25, 2.75), (0.0, 0.0, 2.64), 68)),
    ]
    for filename, camera in cameras:
        scene.camera = camera
        scene.render.filepath = str(OUT_DIR / f"{filename}.png")
        bpy.ops.render.render(write_still=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BLEND_PATH.parent.mkdir(parents=True, exist_ok=True)
    clear_scene()
    configure_render()
    setup_world()
    build_robi()
    render_views()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    print(f"Saved ROBI master: {BLEND_PATH}")
    print(f"Rendered review images: {OUT_DIR}")


if __name__ == "__main__":
    main()
