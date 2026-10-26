"""用 Blender headless 生成 AI 办公室的角色模型（低模 + 骨骼 + 4 个动作）。

用法：
  blender -b -P tools/blender/build_agent.py

产物：
  frontend/public/office/agent.glb          角色（glTF Binary，内嵌材质）
  docs/mockups/agent-preview-*.png          三个角度的预览渲染

设计：
- 身高 1.70，脚底 z=0，面朝 -Y（Blender），导出后 glTF 里是 +Z 面向
- 每个部件是独立 mesh，rigid 绑到一根骨（100% 权重）——低模风格，像 Crossy Road
- 部件命名 hair_* / shirt_* / pants_* / shoes_* / body，运行时按名字换装
- 四个动作：idle / walk / dance / sing
"""

import math
import os

import bpy

ROOT = r"C:\Users\aichao\.local\share\opencode\worktree\ce637a15bb0a57b0b07a4b910025d9e2c851dcf4\lively-ferret"
OUT_GLB = os.path.join(ROOT, "frontend", "public", "office", "agent.glb")
OUT_PREVIEW = os.path.join(ROOT, "docs", "mockups")

# ---------------------------------------------------------------- 基础

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough=0.65):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)   # Workbench 预览用这个
    return m


def box(name, size, loc, material, bevel=0.02, segments=2):
    """带倒角的方块（低模的圆润感靠 bevel，不加细分）。"""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = (size[0], size[1], size[2])
    # 关键：把 location 也烘焙进网格（否则骨modifier 会把部件按对象原点错位）
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel > 0:
        m = o.modifiers.new("bev", "BEVEL")
        m.width = bevel
        m.segments = segments
        m.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.materials.append(material)
    bpy.ops.object.shade_flat()
    return o


def taper(obj, top=1.0, bottom=1.0):
    """按高度把顶点在 XY 上缩放：top/bottom 是上下端比例（做肩膀、收腰）。"""
    import bmesh
    me = obj.data
    zs = [v.co.z for v in me.vertices]
    z0, z1 = min(zs), max(zs)
    if z1 - z0 < 1e-6:
        return obj
    for v in me.vertices:
        t = (v.co.z - z0) / (z1 - z0)
        k = bottom + (top - bottom) * t
        v.co.x *= k
        v.co.y *= k
    return obj


def smooth(obj, levels=1):
    m = obj.modifiers.new("sub", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.ops.object.shade_smooth()
    return obj


def sphere(name, r, loc, material, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=16, ring_count=10, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


# ---------------------------------------------------------------- 角色

COL = {
    "skin": (0.95, 0.78, 0.64),
    "hair": (0.16, 0.13, 0.12),
    "shirt": (0.24, 0.48, 0.72),
    "pants": (0.24, 0.26, 0.32),
    "shoe": (0.14, 0.14, 0.16),
    "accent": (0.93, 0.93, 0.95),
}


def build_body():
    M = {k: mat("mat_" + k, v) for k, v in COL.items()}
    M["eye"] = mat("mat_eye", (0.10, 0.10, 0.12), 0.35)

    parts = {}

    # 躯干（衬衫）—— 卡通比例：头大、身子短
    parts["body"] = taper(box("body", (0.34, 0.21, 0.40), (0, 0, 1.20), M["shirt"], 0.06, 3), 1.12, 0.92)
    # 腰/臀
    parts["hips"] = taper(box("hips", (0.31, 0.20, 0.17), (0, 0, 0.99), M["pants"], 0.05), 1.0, 0.92)
    # 脖子
    parts["neck"] = box("neck", (0.11, 0.11, 0.07), (0, 0, 1.425), M["skin"], 0.02)
    # 头（大 + 圆润：大倒角后再细分一级）
    parts["head"] = smooth(box("head", (0.30, 0.30, 0.30), (0, 0, 1.575), M["skin"], 0.11, 4), 1)
    # 眼睛（贴在 -Y 正面）
    for i, sx in enumerate((-1, 1)):
        e = sphere(f"eye_{i}", 0.023, (sx * 0.068, -0.142, 1.60), M["eye"])
        e.parent = parts["head"]
    # 嘴（一条小横块）
    mo = box("mouth", (0.058, 0.014, 0.014), (0, -0.145, 1.525), M["eye"], 0.005)
    mo.parent = parts["head"]
    for sx in (-1, 1):
        br = box("brow_%d" % (sx > 0), (0.055, 0.014, 0.012), (sx * 0.068, -0.146, 1.638), M["eye"], 0.004)
        br.rotation_euler = (0, math.radians(-6 * sx), 0)
        br.parent = parts["head"]

    # 领口
    box("collar", (0.22, 0.17, 0.03), (0, 0, 1.398), M["accent"], 0.008)

    # 手臂：上臂 / 前臂 / 手
    for side, sx in (("L", 1), ("R", -1)):
        parts[f"upperarm.{side}"] = box(
            f"upperarm_{side}", (0.10, 0.10, 0.26), (sx * 0.215, 0, 1.29), M["shirt"], 0.035
        )
        parts[f"lowerarm.{side}"] = box(
            f"lowerarm_{side}", (0.088, 0.088, 0.24), (sx * 0.215, 0, 1.04), M["skin"], 0.032
        )
        parts[f"hand.{side}"] = box(
            f"hand_{side}", (0.095, 0.08, 0.11), (sx * 0.215, 0, 0.885), M["skin"], 0.032
        )

    # 腿：大腿 / 小腿 / 鞋
    for side, sx in (("L", 1), ("R", -1)):
        parts[f"upperleg.{side}"] = taper(box(
            f"upperleg_{side}", (0.135, 0.14, 0.40), (sx * 0.09, 0, 0.70), M["pants"], 0.045
        ), 1.06, 0.86)
        parts[f"lowerleg.{side}"] = box(
            f"lowerleg_{side}", (0.115, 0.12, 0.36), (sx * 0.09, 0, 0.34), M["pants"], 0.035
        )
        parts[f"foot.{side}"] = box(
            f"shoes_{side}", (0.155, 0.30, 0.115), (sx * 0.09, -0.055, 0.06), M["shoe"], 0.04
        )

    return parts, M


def build_hair(M):
    """三种发型：短发帽 / 波波头 / 丸子头。命名 hair_0..2。"""
    hair_mat = M["hair"]
    out = []

    # 0：短发（包住头顶，前额略高）
    h0 = smooth(box("hair_0", (0.315, 0.315, 0.17), (0, 0.008, 1.665), hair_mat, 0.09, 3), 1)
    bang = box("hair_0_bang", (0.20, 0.06, 0.075), (0, -0.135, 1.66), hair_mat, 0.025)
    bang.parent = h0
    out.append(h0)

    # 1：波波头（两侧垂下来）
    h1 = box("hair_1", (0.322, 0.315, 0.175), (0, 0.008, 1.665), hair_mat, 0.075, 3)
    for sx in (-1, 1):
        s = box("hair_1_side", (0.06, 0.24, 0.28), (sx * 0.155, 0.01, 1.535), hair_mat, 0.025)
        s.parent = h1
    out.append(h1)

    # 2：丸子头（短发 + 顶上一个球）
    h2 = box("hair_2", (0.315, 0.31, 0.145), (0, 0.008, 1.68), hair_mat, 0.07, 3)
    bun = sphere("hair_2_bun", 0.085, (0, 0.03, 1.775), hair_mat, (1, 1, 0.9))
    bun.parent = h2
    out.append(h2)

    return out


# ---------------------------------------------------------------- 骨骼

BONES = [
    # name, head, tail, parent
    ("Hips", (0, 0, 0.95), (0, 0, 1.10), None),
    ("Spine", (0, 0, 1.10), (0, 0, 1.26), "Hips"),
    ("Chest", (0, 0, 1.26), (0, 0, 1.42), "Spine"),
    ("Neck", (0, 0, 1.42), (0, 0, 1.50), "Chest"),
    ("Head", (0, 0, 1.50), (0, 0, 1.72), "Neck"),
    ("UpperArm.L", (0.10, 0, 1.40), (0.225, 0, 1.19), "Chest"),
    ("LowerArm.L", (0.225, 0, 1.19), (0.225, 0, 0.97), "UpperArm.L"),
    ("Hand.L", (0.225, 0, 0.97), (0.225, 0, 0.87), "LowerArm.L"),
    ("UpperArm.R", (-0.10, 0, 1.40), (-0.225, 0, 1.19), "Chest"),
    ("LowerArm.R", (-0.225, 0, 1.19), (-0.225, 0, 0.97), "UpperArm.R"),
    ("Hand.R", (-0.225, 0, 0.97), (-0.225, 0, 0.87), "LowerArm.R"),
    ("UpperLeg.L", (0.085, 0, 0.92), (0.085, 0, 0.52), "Hips"),
    ("LowerLeg.L", (0.085, 0, 0.52), (0.085, 0, 0.12), "UpperLeg.L"),
    ("Foot.L", (0.085, 0, 0.12), (0.085, -0.20, 0.06), "LowerLeg.L"),
    ("UpperLeg.R", (-0.085, 0, 0.92), (-0.085, 0, 0.52), "Hips"),
    ("LowerLeg.R", (-0.085, 0, 0.52), (-0.085, 0, 0.12), "UpperLeg.R"),
    ("Foot.R", (-0.085, 0, 0.12), (-0.085, -0.20, 0.06), "LowerLeg.R"),
]

# 部件 -> 骨
BIND = {
    "body": "Chest",
    "hips": "Hips",
    "neck": "Neck",
    "head": "Head",
    "upperarm_L": "UpperArm.L",
    "lowerarm_L": "LowerArm.L",
    "hand_L": "Hand.L",
    "upperarm_R": "UpperArm.R",
    "lowerarm_R": "LowerArm.R",
    "hand_R": "Hand.R",
    "upperleg_L": "UpperLeg.L",
    "lowerleg_L": "LowerLeg.L",
    "shoes_L": "Foot.L",
    "upperleg_R": "UpperLeg.R",
    "lowerleg_R": "LowerLeg.R",
    "shoes_R": "Foot.R",
    "hair_0": "Head",
    "hair_1": "Head",
    "hair_1_side": "Head",
    "hair_2": "Head",
    "hair_2_bun": "Head",
}


def build_armature():
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    arm = bpy.context.active_object
    arm.name = "AgentRig"
    eb = arm.data.edit_bones
    for b in list(eb):
        eb.remove(b)
    made = {}
    for name, head, tail, parent in BONES:
        b = eb.new(name)
        b.head = head
        b.tail = tail
        if parent:
            b.parent = made[parent]
        made[name] = b
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def skin(parts, arm):
    """每个部件 100% 绑到一根骨（低模 articulation，不做平滑蒙皮）。"""
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        base = obj.name.split(".")[0]
        bone = BIND.get(base)
        if not bone:
            # 眼睛/嘴/领口等小件：跟随头/胸
            bone = "Head" if base.startswith(("eye", "mouth")) else "Chest"
        vg = obj.vertex_groups.new(name=bone)
        vg.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
        mod = obj.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        obj.parent = arm


# ---------------------------------------------------------------- 动作

def key(arm, bone, frame, rot=None, loc=None):
    pb = arm.pose.bones[bone]
    pb.rotation_mode = "XYZ"
    if rot is not None:
        pb.rotation_euler = rot
        pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = loc
        pb.keyframe_insert("location", frame=frame)


def make_action(arm, name, frames, fn):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data_create()
    arm.animation_data.action = act
    fn(arm, frames)
    return act


def act_idle(arm, F):
    for i, f in enumerate((1, F // 2 + 1, F + 1)):
        ph = 0 if i == 0 else (1 if i == 1 else 0)
        key(arm, "Chest", f, rot=(math.radians(1.5) * ph, 0, 0))
        key(arm, "Head", f, rot=(math.radians(-1.2) * ph, 0, 0))
        key(arm, "UpperArm.L", f, rot=(0, 0, math.radians(-3)))
        key(arm, "UpperArm.R", f, rot=(0, 0, math.radians(3)))
        key(arm, "Hips", f, loc=(0, 0, 0.008 * ph))


def act_walk(arm, F):
    # 一左一右两个半周期
    for f, s in ((1, 1), (F // 4 + 1, 0), (F // 2 + 1, -1), (F * 3 // 4 + 1, 0), (F + 1, 1)):
        key(arm, "UpperLeg.L", f, rot=(math.radians(26) * s, 0, 0))
        key(arm, "UpperLeg.R", f, rot=(-math.radians(26) * s, 0, 0))
        key(arm, "LowerLeg.L", f, rot=(max(0, -math.radians(22) * s), 0, 0))
        key(arm, "LowerLeg.R", f, rot=(max(0, math.radians(22) * s), 0, 0))
        key(arm, "UpperArm.L", f, rot=(-math.radians(22) * s, 0, 0))
        key(arm, "UpperArm.R", f, rot=(math.radians(22) * s, 0, 0))
        key(arm, "Hips", f, loc=(0, 0, abs(s) * 0.012))
        key(arm, "Chest", f, rot=(0, 0, math.radians(3) * s))


def act_dance(arm, F):
    beats = (1, F // 4 + 1, F // 2 + 1, F * 3 // 4 + 1, F + 1)
    for i, f in enumerate(beats):
        up = 1 if i % 2 == 0 else 0
        key(arm, "Hips", f, loc=(0, 0, 0.05 * up), rot=(0, 0, math.radians(8) * (1 if up else -1)))
        key(arm, "Chest", f, rot=(math.radians(-4) if up else math.radians(2), 0, math.radians(-6) * (1 if up else -1)))
        key(arm, "Head", f, rot=(math.radians(-8) if up else 0, 0, math.radians(6) * (1 if up else -1)))
        # 双臂举起摆动
        key(arm, "UpperArm.L", f, rot=(0, math.radians(-70 if up else -110), math.radians(20)))
        key(arm, "UpperArm.R", f, rot=(0, math.radians(70 if up else 110), math.radians(-20)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-30), 0, 0))
        key(arm, "LowerArm.R", f, rot=(math.radians(-30), 0, 0))
        key(arm, "UpperLeg.L", f, rot=(math.radians(10), 0, 0))
        key(arm, "UpperLeg.R", f, rot=(math.radians(-10), 0, 0))
        key(arm, "LowerLeg.L", f, rot=(math.radians(4), 0, 0))
        key(arm, "LowerLeg.R", f, rot=(math.radians(4), 0, 0))


def act_sit(arm, F):
    """坐着办公：胯下沉、大腿前抬、小腿垂、手臂前伸放桌面。"""
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "Hips", f, loc=(0, -0.44, 0.02), rot=(math.radians(-4), 0, 0))
        key(arm, "UpperLeg.L", f, rot=(math.radians(-75), 0, 0))
        key(arm, "UpperLeg.R", f, rot=(math.radians(-78), 0, 0))
        key(arm, "LowerLeg.L", f, rot=(math.radians(72), 0, 0))
        key(arm, "LowerLeg.R", f, rot=(math.radians(76), 0, 0))
        key(arm, "Foot.L", f, rot=(math.radians(6), 0, 0))
        key(arm, "Foot.R", f, rot=(math.radians(6), 0, 0))
        key(arm, "UpperArm.L", f, rot=(math.radians(-38 - 2 * ph), 0, math.radians(16)))
        key(arm, "UpperArm.R", f, rot=(math.radians(-38 + 2 * ph), 0, math.radians(-16)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-52), 0, 0))
        key(arm, "LowerArm.R", f, rot=(math.radians(-52), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(2), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-3 + 1.5 * ph), 0, 0))


def act_sing(arm, F):
    # 右手（Hand.R 所在臂）举到嘴边，头微仰
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "UpperArm.R", f, rot=(math.radians(-95 + 6 * ph), math.radians(38), math.radians(-18)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-100 - 8 * ph), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-10 - 3 * ph), 0, math.radians(-4)))
        key(arm, "Chest", f, rot=(math.radians(2), 0, math.radians(4)))
        key(arm, "Hips", f, loc=(0, 0, 0.02 * ph))
        key(arm, "UpperLeg.L", f, rot=(0, 0, 0))
        key(arm, "UpperLeg.R", f, rot=(0, 0, 0))
        key(arm, "LowerLeg.L", f, rot=(0, 0, 0))
        key(arm, "LowerLeg.R", f, rot=(0, 0, 0))
        key(arm, "UpperArm.L", f, rot=(0, math.radians(-28), math.radians(12)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-20), 0, 0))


# ---------------------------------------------------------------- 渲染预览

def setup_preview():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
    sc.display.render_aa = "8"
    sc.render.resolution_x = 640
    sc.render.resolution_y = 900
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("W")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.94, 0.93, 0.91, 1)

    # 地面
    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    g = bpy.context.active_object
    gm = mat("mat_ground", (0.88, 0.87, 0.85), 0.9)
    g.data.materials.append(gm)

    # 相机
    bpy.ops.object.camera_add(location=(2.4, -3.2, 1.9), rotation=(math.radians(72), 0, math.radians(37)))
    cam = bpy.context.active_object
    cam.data.lens = 62
    sc.camera = cam
    return cam


def clear_pose(arm):
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    if arm.animation_data:
        arm.animation_data.action = None


def render_views(arm):
    clear_pose(arm)
    cam = setup_preview()
    views = {
        "front": ((0, -3.6, 1.35), (math.radians(84), 0, 0)),
        "three-quarter": ((2.5, -3.0, 1.9), (math.radians(72), 0, math.radians(39))),
        "side": ((3.6, 0.2, 1.35), (math.radians(84), 0, math.radians(90))),
    }
    for name, (loc, rot) in views.items():
        cam.location = loc
        cam.rotation_euler = rot
        bpy.context.scene.render.filepath = os.path.join(OUT_PREVIEW, f"agent-preview-{name}.png")
        bpy.ops.render.render(write_still=True)
        print("[preview]", name)


# ---------------------------------------------------------------- 主流程

def main():
    reset()
    parts, M = build_body()
    hairs = build_hair(M)
    # 只保留一种发型参与预览（其余隐藏但导出）
    def hide_tree(o, hide):
        o.hide_render = hide
        for c in o.children:
            hide_tree(c, hide)
    for i, h in enumerate(hairs):
        hide_tree(h, i != 0)

    arm = build_armature()
    skin(parts, arm)
    bpy.context.view_layer.objects.active = arm

    # 动作（帧率 24）
    bpy.context.scene.render.fps = 24
    make_action(arm, "idle", 48, act_idle)
    make_action(arm, "sit", 48, act_sit)
    make_action(arm, "walk", 32, act_walk)
    make_action(arm, "dance", 48, act_dance)
    make_action(arm, "sing", 48, act_sing)
    arm.animation_data.action = None

    # 预览
    render_views(arm)

    # 动作预览：坐 / 蹦迪 / 主唱
    cam = bpy.context.scene.camera
    if cam is None:
        cam = setup_preview()
    cam.location = (2.5, -3.0, 1.9)
    cam.rotation_euler = (math.radians(72), 0, math.radians(39))
    for nm, fr in (("sit", 12), ("dance", 12), ("sing", 12)):
        act = bpy.data.actions.get(nm)
        if not act:
            continue
        clear_pose(arm)
        arm.animation_data.action = act
        bpy.context.scene.frame_set(fr)
        bpy.context.scene.render.filepath = os.path.join(OUT_PREVIEW, "agent-pose-%s.png" % nm)
        bpy.ops.render.render(write_still=True)
    arm.animation_data.action = None

    # 导出：只导角色（隐藏地面的预览件）
    for o in list(bpy.data.objects):
        if o.name.startswith("Plane") or o.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(o, do_unlink=True)

    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=OUT_GLB,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_skins=True,
        export_yup=True,
        export_cameras=False,
        export_lights=False,
    )
    print("[done]", OUT_GLB, os.path.getsize(OUT_GLB), "bytes")


main()
