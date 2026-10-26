"""AI 办公室角色 v2：自己"画"一套更讨喜的卡通角色（低模，但脸做细）。

设计目标（对照用户意见）：
- 头是圆的（球体削下颌），不是方盒
- 亚洲感：黑发、深色杏眼（有眼白/瞳仁/高光）、细眉、小鼻、微笑
- 头发分块（刘海 + 侧发 + 后发），不是一顶帽子
- 身体：收腰衬衫 + 领口 + 袖口 + 腰带 + 口袋；手掌带拇指；鞋有鞋底
- 骨骼与 v1 一致（Hips/Spine/Chest/Neck/Head/四肢），动作沿用 v1 方案

产物：frontend/public/office/agent-v2.glb + docs/mockups/v2-*.png
"""

import math
import os

import bmesh
import bpy

ROOT = r"C:\Users\aichao\.local\share\opencode\worktree\ce637a15bb0a57b0b07a4b910025d9e2c851dcf4\lively-ferret"
OUT_GLB = os.path.join(ROOT, "frontend", "public", "office", "agent-v2.glb")
OUT_PV = os.path.join(ROOT, "docs", "mockups")

HEAD_Z = 1.60
HEAD_R = 0.165


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mat(name, rgb, rough=0.7):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    m.diffuse_color = (*rgb, 1)
    return m


def obj_mesh(name, verts, faces, material, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material)
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    return o


def box(name, size, loc, material, bevel=0.02, seg=2, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if bevel > 0:
        m = o.modifiers.new("b", "BEVEL")
        m.width = bevel
        m.segments = seg
        m.limit_method = "ANGLE"
        bpy.ops.object.modifier_apply(modifier=m.name)
    o.data.materials.append(material)
    bpy.ops.object.shade_flat()
    return o


def ball(name, r, loc, material, scale=(1, 1, 1), seg=24, ring=16, smooth=True):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=ring, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(material)
    if smooth:
        bpy.ops.object.shade_smooth()
    return o


def tube(name, profile, material, seg=20, cap_top=True, cap_bottom=True):
    """沿 Z 轴生成一整段管状肢体。

    profile = [(z, r), ...]（由下到上）。整段是一张连续曲面，关节处靠**顶点权重**
    平滑过渡，而不是拼两个圆柱加一个球——那样必然有接缝或鼓包。
    """
    verts, faces = [], []
    n = len(profile)
    for (z, r) in profile:
        for i in range(seg):
            a = 2 * math.pi * i / seg
            verts.append((r * math.cos(a), r * math.sin(a), z))
    for k in range(n - 1):
        for i in range(seg):
            a = k * seg + i
            b = k * seg + (i + 1) % seg
            c = (k + 1) * seg + i
            d = (k + 1) * seg + (i + 1) % seg
            faces.append((a, b, d, c))
    if cap_bottom:
        c0 = len(verts)
        verts.append((0, 0, profile[0][0]))
        for i in range(seg):
            faces.append((c0, (i + 1) % seg, i))
    if cap_top:
        c1 = len(verts)
        verts.append((0, 0, profile[-1][0]))
        base = (n - 1) * seg
        for i in range(seg):
            faces.append((c1, base + i, base + (i + 1) % seg))
    o = obj_mesh(name, verts, faces, material, smooth=True)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    return o


def weight_two(obj, bone_low, bone_high, z_low, z_high):
    """关节两侧按高度做平滑权重过渡（smoothstep），弯曲时才不会有"折叠"的硬折痕。"""
    g_low = obj.vertex_groups.new(name=bone_low)
    g_high = obj.vertex_groups.new(name=bone_high)
    for v in obj.data.vertices:
        t = (v.co.z - z_low) / max(1e-6, (z_high - z_low))
        t = max(0.0, min(1.0, t))
        t = t * t * (3 - 2 * t)
        g_high.add([v.index], t, "REPLACE")
        g_low.add([v.index], 1.0 - t, "REPLACE")
    return obj


def limb(name, r_top, r_bot, h, loc, material, rot=(0, 0, 0), seg=20):
    """锥形圆肢体（上下半径不同），平滑着色——比方块腿/臂自然。"""
    bpy.ops.mesh.primitive_cone_add(vertices=seg, radius1=r_bot, radius2=r_top, depth=h,
                                   location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def ring(name, major, minor, loc, material, seg=22, mat_rot=(0, 0, 0)):
    """圆环（袖口/腰带这类"套一圈"的部件）：没有端盖，不会和圆柱面打架。"""
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                    major_segments=seg, minor_segments=10,
                                    location=loc, rotation=mat_rot)
    o = bpy.context.active_object
    o.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return o


def joint(name, r, loc, material):
    o = ball(name, r, loc, material, (1, 1, 1), 18, 12, True)
    return o


def face_patch(name, material, r, cz, half_w, z_top, z_bot, nx=14, nz=16):
    """贴在球头正面的曲面贴片：沿球面取点，UV 铺满整张脸图。"""
    verts, faces, uvs = [], [], []
    for j in range(nz + 1):
        for i in range(nx + 1):
            u = i / nx
            v = j / nz
            x = (u * 2 - 1) * half_w
            z = z_bot + (z_top - z_bot) * v
            dz = z - cz
            inside = r * r - x * x - dz * dz
            y = -math.sqrt(inside) if inside > 1e-6 else 0.0
            verts.append((x, y, z))
            uvs.append((u, v))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            b = a + 1
            c = a + (nx + 1)
            d = c + 1
            faces.append((a, b, d, c))
    o = obj_mesh(name, verts, faces, material, smooth=True)
    uvl = o.data.uv_layers.new(name="UVMap")
    for poly in o.data.polygons:
        for li in poly.loop_indices:
            vi = o.data.loops[li].vertex_index
            uvl.data[li].uv = uvs[vi]
    return o


def taper_z(obj, top=1.0, bottom=1.0, z0=None, z1=None):
    me = obj.data
    zs = [v.co.z for v in me.vertices]
    a, b = (z0 if z0 is not None else min(zs)), (z1 if z1 is not None else max(zs))
    if b - a < 1e-6:
        return obj
    for v in me.vertices:
        t = max(0.0, min(1.0, (v.co.z - a) / (b - a)))
        k = bottom + (top - bottom) * t
        v.co.x *= k
        v.co.y *= k
    return obj


def cut_below(obj, z):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                           plane_co=(0, 0, z), plane_no=(0, 0, 1), clear_inner=True)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def cut_tilted(obj, z, tilt=0.55):
    """斜切：法线 (0, tilt, 1)。前面（y<0）切得高 = 前面发际线高，后面留长。

    平切会得到「钢盔」——额头被盖到眼睛，这是之前显丑的主因。
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    n = math.sqrt(1 + tilt * tilt)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                           plane_co=(0, 0, z), plane_no=(0, tilt / n, 1 / n), clear_inner=True)
    bm.to_mesh(obj.data)
    bm.free()
    return obj


def bevel(obj, width=0.02, seg=2, angle=35):
    """给圆柱类的上下边缘倒角，去掉"切面硬边"（比另加一个球盖更干净，不投阴影带）。"""
    bpy.context.view_layer.objects.active = obj
    m = obj.modifiers.new("bev", "BEVEL")
    m.width = width
    m.segments = seg
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    bpy.ops.object.modifier_apply(modifier=m.name)
    return obj


def oval(name, r_top, r_bot, h, loc, material, flat=0.62, seg=24):
    """椭圆截面的锥形圆柱：躯干/胯/腰带用它，比方块柔和。"""
    o = limb(name, r_top, r_bot, h, loc, material, seg=seg)
    o.scale = (1, flat, 1)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return o


# ---------------------------------------------------------------- 头 / 脸

def build_head(M):
    # 颅骨：球，下颌收窄
    head = ball("head", HEAD_R, (0, 0, HEAD_Z), M["skin"], (1.0, 0.97, 1.06))
    for v in head.data.vertices:
        t = max(0.0, (HEAD_Z - 0.02 - v.co.z) / HEAD_R)     # 下半部分
        k = 1 - 0.42 * (t ** 1.7)
        v.co.x *= k
        v.co.y *= k
        # 下巴略往前
        if v.co.z < HEAD_Z - 0.10:
            v.co.y -= 0.012
    head.data.update()

    # 耳朵
    for sx in (-1, 1):
        ball("ear_%d" % sx, 0.035, (sx * 0.155, 0.005, HEAD_Z - 0.01), M["skin"], (0.5, 1, 1.15), 14, 10)

    # 脸：曲面贴片（沿球面铺开，UV 铺满脸图；平板会插进球体导致眼睛被切）
    face_img = bpy.data.images.load(
        os.path.join(ROOT, "frontend", "public", "office", "face.png"), check_existing=True
    )
    fm = bpy.data.materials.new("mat_face")
    fm.use_nodes = True
    fm.blend_method = "BLEND"
    nt = fm.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = face_img
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.9
    # 贴片范围：上到发际线下方(+0.135)、下到下巴(-0.125)；脸图上眉毛 0.20 / 眼 0.38 /
    # 鼻 0.56 / 嘴 0.69 正好落在 +0.083 / +0.036 / -0.011 / -0.045
    face_patch("face_decal", fm, HEAD_R + 0.0025, HEAD_Z + 0.005,
               0.098, HEAD_Z + 0.135, HEAD_Z - 0.125)

    return head


def wavy_rim(obj, cut_z, tilt=0.55, amp=0.009, waves=9, band=0.038):
    """把发帽下沿做成起伏的"毛边"（头发不是一刀切的圆弧）。

    注意要按**切割平面**算距离：如果按最小 z 算，波浪只会出现在后脑勺，
    正面发际线还是一条光滑的弧 —— 那正是"半圆扣在头上"的观感来源。
    """
    n = math.sqrt(1 + tilt * tilt)
    for v in obj.data.vertices:
        d = (tilt / n) * v.co.y + (1.0 / n) * (v.co.z - cut_z)
        if d >= band or d < -0.02:
            continue
        k = 1.0 - max(0.0, d) / band
        a = math.atan2(v.co.y, v.co.x)
        v.co.z -= amp * k * (0.45 + 0.55 * math.sin(waves * a))
    obj.data.update()
    return obj


def strand(root, name, ang, z_top, length, w=0.028, thick=0.014, extra_r=0.006):
    """一缕头发：从发际线沿球面垂下来（用扁椭球近似，同色看不出接缝）。"""
    cz = HEAD_Z + 0.02
    R = HEAD_R + 0.019

    def r_at(z):
        dz = z - cz
        return math.sqrt(max(0.0009, R * R - dz * dz))

    z_bot = z_top - length
    rr = (r_at(z_top) + r_at(z_bot)) / 2 + extra_r
    o = ball(name, 1.0, (math.sin(ang) * rr, 0.012 - math.cos(ang) * rr, (z_top + z_bot) / 2),
             mat("mat_hair", (0.20, 0.18, 0.17)), (w, thick, length * 0.56), 14, 10)
    o.parent = root
    return o


def hair_mat():
    """发片材质：灰度发丝贴图 + alpha 裁剪（CLIP → glTF MASK）。"""
    m = bpy.data.materials.get("mat_haircard")
    if m:
        return m
    m = bpy.data.materials.new("mat_haircard")
    m.use_nodes = True
    m.blend_method = "CLIP"
    m.alpha_threshold = 0.32
    m.show_transparent_back = False
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(
        os.path.join(ROOT, "frontend", "public", "office", "hair_strand.png"), check_existing=True
    )
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    bsdf.inputs["Roughness"].default_value = 0.62
    m.diffuse_color = (0.22, 0.18, 0.16, 1)
    return m


def hair_cap_mat():
    """发帽材质：把发丝图铺到球面上（竖条纹绕经线，看着就有发丝，不再是一块光壳）。"""
    m = bpy.data.materials.get("mat_haircap")
    if m:
        return m
    m = bpy.data.materials.new("mat_haircap")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(
        os.path.join(ROOT, "frontend", "public", "office", "hair_strand.png"), check_existing=True
    )
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.55
    m.diffuse_color = (0.24, 0.20, 0.18, 1)
    return m


def texture_cap(obj, repeat_u=3.0):
    """把发帽的 UV 沿横向重复几遍（4 根发丝 → 12 根绕头一圈）。"""
    uvl = obj.data.uv_layers.active
    if not uvl:
        uvl = obj.data.uv_layers.new(name="UVMap")
    for d in uvl.data:
        d.uv.x *= repeat_u
    obj.data.materials.clear()
    obj.data.materials.append(hair_cap_mat())
    return obj


def hair_cards(root, tag, specs):
    """发片（hair cards）：每片是一张贴了发丝贴图的薄面，绕头一圈摆开。

    specs 里每项 = (角度 a, 顶部高度 z, 长度, 宽度, 外翻倾斜, 向下外扩量)
    a = 0 是正前方，±π/2 是左右，π 是后脑。
    """
    verts, faces, uvs = [], [], []
    cz = HEAD_Z + 0.02
    R = HEAD_R + 0.019
    for idx, (a, z_top, length, width, tilt, bend) in enumerate(specs):
        width *= 1.30      # 发片做宽一点，才像一撮头发而不是几根线
        z_top += 0.012     # 往上压一点，盖住发帽边缘的硬接缝
        # 长短/高低错开，否则一圈发片整齐得像梳子
        j = ((idx * 37) % 11) / 11.0 - 0.5
        length *= 1.0 + 0.26 * j
        z_top += 0.008 * j
        dz = z_top - cz
        r = math.sqrt(max(0.0009, R * R - dz * dz)) + 0.006
        px = math.sin(a) * r
        py = 0.012 - math.cos(a) * r
        ca, sa = math.cos(a), math.sin(a)
        base = len(verts)
        rows = ((0.0, 0.0, 1.0), (length * 0.5, bend * 0.55, 0.5), (length, bend, 0.0))
        for (down, out, v) in rows:
            # tilt：越往下越往外翻
            out2 = out + math.sin(tilt) * down
            for sx in (-1, 1):
                lx = sx * width / 2
                ly = -out2
                lz = -down
                x = px + lx * ca - ly * sa
                y = py + lx * sa + ly * ca
                verts.append((x, y, z_top + lz))
                uvs.append((0.0 if sx < 0 else 1.0, v))
        faces.append((base + 0, base + 1, base + 3, base + 2))
        faces.append((base + 2, base + 3, base + 5, base + 4))
    o = obj_mesh(tag + "_cards", verts, faces, hair_mat(), smooth=True)
    uvl = o.data.uv_layers.new(name="UVMap")
    for poly in o.data.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[o.data.loops[li].vertex_index]
    o.parent = root
    return o


def build_hair(M):
    """9 套发型（男女都有），每套的根节点叫 hair_N，碎发/后发都挂在根下。

    0 男生·偏分短发  1 男生·寸头   2 女生·侧分短发
    3 女生·长直发    4 女生·马尾   5 女生·丸子头
    6 女生·高马尾    7 女生·双马尾 8 女生·短波波
    """
    out = []

    def shell(name, dz, extra, cut_z, tilt, sx=1.02, sy=1.02, sz=1.02, amp=0.013, waves=7):
        cap = ball(name, HEAD_R + extra, (0, 0.012, HEAD_Z + dz), M["hair"], (sx, sy, sz), 32, 20)
        cut_tilted(cap, cut_z, tilt)
        wavy_rim(cap, cut_z, tilt, amp, waves)
        texture_cap(cap, 3.0)
        out.append(cap)
        return cap

    def attach(root, obj):
        obj.parent = root
        return obj

    def fringe(root, cut_z, n=3, span=0.062, drop=0.096, size=0.048, squash=0.62, y=-0.100):
        """前额碎发：几缕大小不一的发片压在发际线下沿"""
        for i in range(n):
            t = 0.0 if n == 1 else (i - (n - 1) / 2) / ((n - 1) / 2)
            s = 1.06 - 0.12 * abs(t)
            attach(root, ball("%s_t%d" % (root.name, i), size * s,
                              (t * span, y, cut_z + drop),
                              M["hair"], (1.24, 0.62, squash), 16, 12))

    # ---------- 0 男生短发：偏分，鬓角短
    h0 = shell("hair_0", 0.028, 0.011, HEAD_Z + 0.012, 0.55, amp=0.009, waves=9)

    # ---------- 1 男生寸头：极薄、贴头皮
    h1 = shell("hair_1", 0.018, 0.0050, HEAD_Z - 0.012, 0.62, amp=0.012, waves=16)

    # ---------- 2 女生学生头：齐刘海 + 齐下巴的波波
    h2 = shell("hair_2", 0.020, 0.015, HEAD_Z - 0.010, 0.67, amp=0.011, waves=7)
    bang = ball("hair_2_bang", 0.104, (0, -0.084, HEAD_Z + 0.116),
                M["hair"], (1.34, 0.50, 0.28), 22, 14)
    attach(h2, bang)
    texture_cap(bang, 1.4)

    # ---------- 3 女生长直发：后发垂到肩下 + 两侧长发片
    h3 = shell("hair_3", 0.024, 0.014, HEAD_Z - 0.005, 0.66, amp=0.010, waves=6)
    back = limb("hair_3_back", 0.112, 0.140, 0.34, (0, 0.165, HEAD_Z - 0.100), M["hair"], seg=24)
    attach(h3, back)
    texture_cap(back, 1.6)
    back.scale = (1, 0.28, 1)
    bpy.context.view_layer.objects.active = back
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for sx in (-1, 1):
        lock = ball("hair_3_lock%d" % sx, 0.070, (sx * 0.132, 0.012, HEAD_Z - 0.110),
                    M["hair"], (0.52, 0.80, 1.95), 16, 12)
        attach(h3, lock)
        texture_cap(lock, 1.2)
    # ---------- 4 女生马尾：短发 + 后脑一束
    h4 = shell("hair_4", 0.026, 0.012, HEAD_Z + 0.006, 0.55, amp=0.009, waves=9)
    tail = limb("hair_4_tail", 0.050, 0.026, 0.34, (0, 0.168, HEAD_Z - 0.095),
                M["hair"], rot=(math.radians(-16), 0, 0), seg=18)
    attach(h4, tail)
    texture_cap(tail, 1.2)
    attach(h4, ball("hair_4_tie", 0.040, (0, 0.140, HEAD_Z + 0.075), M["belt"], (1, 0.8, 0.62), 16, 10))

    # ---------- 5 女生丸子头：短发 + 顶后一个发髻
    h5 = shell("hair_5", 0.028, 0.011, HEAD_Z + 0.010, 0.55, amp=0.010, waves=8)
    bun5 = ball("hair_5_bun", 0.090, (0, 0.058, HEAD_Z + 0.246), M["hair"], (1, 1, 0.94), 24, 18)
    attach(h5, bun5)
    attach(h5, ring("hair_5_tie", 0.052, 0.010, (0, 0.050, HEAD_Z + 0.180), M["belt"]))
    texture_cap(bun5, 1.3)
    for sx in (-1, 1):
        attach(h5, ball("hair_5_burn%d" % sx, 0.052, (sx * 0.152, -0.004, HEAD_Z - 0.030),
                        M["hair"], (0.42, 0.88, 1.10), 14, 10))

    # ---------- 6 女生高马尾：发帽 + 头顶后侧一束高马尾
    h6 = shell("hair_6", 0.026, 0.012, HEAD_Z + 0.008, 0.55, amp=0.010, waves=9)
    tie = ball("hair_6_tie", 0.040, (0, 0.108, HEAD_Z + 0.132), M["belt"], (1, 0.85, 0.8), 16, 10)
    attach(h6, tie)
    tail6 = limb("hair_6_tail", 0.048, 0.026, 0.44, (0, 0.196, HEAD_Z - 0.110),
                 M["hair"], rot=(math.radians(-14), 0, 0), seg=18)
    attach(h6, tail6)
    texture_cap(tail6, 1.2)
    tail6.scale = (1, 0.75, 1)
    bpy.context.view_layer.objects.active = tail6
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # ---------- 7 女生双马尾：两侧各一束
    h7 = shell("hair_7", 0.024, 0.013, HEAD_Z - 0.004, 0.60, amp=0.012, waves=8)
    for sx in (-1, 1):
        attach(h7, ball("hair_7_tie%d" % sx, 0.034, (sx * 0.152, 0.026, HEAD_Z + 0.020),
                        M["belt"], (1, 0.85, 0.8), 14, 10))
        t = limb("hair_7_tail%d" % sx, 0.040, 0.022, 0.36,
                 (sx * 0.178, 0.040, HEAD_Z - 0.180), M["hair"],
                 rot=(0, math.radians(sx * 7), 0), seg=16)
        attach(h7, t)
        texture_cap(t, 1.0)

    # ---------- 8 女生短波波：到耳下的短发，没有刘海
    h8 = shell("hair_8", 0.022, 0.014, HEAD_Z - 0.030, 0.64, amp=0.010, waves=10)

    hair_cards(h0, "hair_0", [
        (-0.52, HEAD_Z + 0.108, 0.115, 0.070, -0.12, 0.012),
        (-0.20, HEAD_Z + 0.112, 0.130, 0.075, -0.10, 0.014),
        (0.14, HEAD_Z + 0.112, 0.135, 0.078, -0.10, 0.014),
        (0.46, HEAD_Z + 0.106, 0.120, 0.070, -0.12, 0.012),
        (-0.98, HEAD_Z + 0.070, 0.135, 0.060, -0.06, 0.010),
        (0.98, HEAD_Z + 0.070, 0.135, 0.060, -0.06, 0.010),
        (2.55, HEAD_Z + 0.060, 0.120, 0.110, 0.0, 0.008),
        (-2.55, HEAD_Z + 0.060, 0.120, 0.110, 0.0, 0.008),
    ])
    # 寸头不加发片（贴头皮，加了像假发）
    hair_cards(h2, "hair_2", [
        (-0.60, HEAD_Z + 0.100, 0.125, 0.075, -0.10, 0.012),
        (-0.22, HEAD_Z + 0.106, 0.140, 0.080, -0.08, 0.014),
        (0.18, HEAD_Z + 0.106, 0.140, 0.080, -0.08, 0.014),
        (0.56, HEAD_Z + 0.100, 0.125, 0.075, -0.10, 0.012),
        (-1.05, HEAD_Z + 0.062, 0.190, 0.075, -0.04, 0.010),
        (1.05, HEAD_Z + 0.062, 0.190, 0.075, -0.04, 0.010),
        (2.40, HEAD_Z + 0.050, 0.210, 0.120, 0.0, 0.008),
        (3.14, HEAD_Z + 0.050, 0.215, 0.130, 0.0, 0.008),
        (-2.40, HEAD_Z + 0.050, 0.210, 0.120, 0.0, 0.008),
    ])
    hair_cards(h3, "hair_3", [
        (-0.55, HEAD_Z + 0.095, 0.150, 0.070, -0.10, 0.012),
        (-0.10, HEAD_Z + 0.100, 0.160, 0.075, -0.08, 0.014),
        (0.35, HEAD_Z + 0.098, 0.155, 0.072, -0.10, 0.012),
        (-1.00, HEAD_Z + 0.060, 0.340, 0.085, -0.03, 0.010),
        (1.00, HEAD_Z + 0.060, 0.340, 0.085, -0.03, 0.010),
        (-1.45, HEAD_Z + 0.050, 0.320, 0.090, -0.02, 0.008),
        (1.45, HEAD_Z + 0.050, 0.320, 0.090, -0.02, 0.008),
        (2.35, HEAD_Z + 0.045, 0.360, 0.130, 0.0, 0.006),
        (3.14, HEAD_Z + 0.045, 0.370, 0.140, 0.0, 0.006),
        (-2.35, HEAD_Z + 0.045, 0.360, 0.130, 0.0, 0.006),
    ])
    hair_cards(h4, "hair_4", [
        (-0.50, HEAD_Z + 0.100, 0.120, 0.070, -0.10, 0.012),
        (0.00, HEAD_Z + 0.104, 0.130, 0.075, -0.08, 0.014),
        (0.48, HEAD_Z + 0.100, 0.120, 0.070, -0.10, 0.012),
        (-1.02, HEAD_Z + 0.065, 0.150, 0.070, -0.04, 0.010),
        (1.02, HEAD_Z + 0.065, 0.150, 0.070, -0.04, 0.010),
    ])
    hair_cards(h5, "hair_5", [
        (-0.52, HEAD_Z + 0.100, 0.115, 0.070, -0.10, 0.012),
        (0.00, HEAD_Z + 0.104, 0.125, 0.075, -0.08, 0.014),
        (0.50, HEAD_Z + 0.100, 0.115, 0.070, -0.10, 0.012),
        (-1.10, HEAD_Z + 0.066, 0.130, 0.068, 0.02, 0.008),
        (1.10, HEAD_Z + 0.066, 0.130, 0.068, 0.02, 0.008),
    ])
    hair_cards(h6, "hair_6", [
        (-0.50, HEAD_Z + 0.100, 0.115, 0.070, -0.10, 0.012),
        (0.00, HEAD_Z + 0.104, 0.125, 0.075, -0.08, 0.014),
        (0.50, HEAD_Z + 0.100, 0.115, 0.070, -0.10, 0.012),
        (-1.12, HEAD_Z + 0.064, 0.140, 0.068, 0.02, 0.008),
        (1.12, HEAD_Z + 0.064, 0.140, 0.068, 0.02, 0.008),
    ])
    hair_cards(h7, "hair_7", [
        (-0.48, HEAD_Z + 0.098, 0.115, 0.070, -0.10, 0.012),
        (0.02, HEAD_Z + 0.102, 0.125, 0.075, -0.08, 0.014),
        (0.52, HEAD_Z + 0.098, 0.115, 0.070, -0.10, 0.012),
        (-1.12, HEAD_Z + 0.062, 0.150, 0.068, 0.02, 0.008),
        (1.12, HEAD_Z + 0.062, 0.150, 0.068, 0.02, 0.008),
    ])
    hair_cards(h8, "hair_8", [
        (-0.55, HEAD_Z + 0.098, 0.105, 0.070, -0.10, 0.012),
        (-0.15, HEAD_Z + 0.102, 0.115, 0.075, -0.08, 0.014),
        (0.28, HEAD_Z + 0.100, 0.110, 0.072, -0.10, 0.012),
        (0.62, HEAD_Z + 0.096, 0.100, 0.068, -0.10, 0.012),
        (-1.12, HEAD_Z + 0.058, 0.120, 0.066, 0.02, 0.008),
        (1.12, HEAD_Z + 0.058, 0.120, 0.066, 0.02, 0.008),
    ])

    # 发束表面也贴几片发丝，避免变成一根光溜溜的管子
    hair_cards(h7, "hair_7b", [
        (-1.55, HEAD_Z + 0.010, 0.180, 0.070, -0.06, 0.010),
        (1.55, HEAD_Z + 0.010, 0.180, 0.070, -0.06, 0.010),
    ])
    hair_cards(h6, "hair_6b", [
        (3.00, HEAD_Z + 0.020, 0.220, 0.090, -0.04, 0.010),
    ])

    return out


# ---------------------------------------------------------------- 身体

def build_body(M):
    parts = {}
    # 衬衫：椭圆截面收腰（前胸窄、腰更窄），比方块柔和
    parts["body"] = bevel(oval("body", 0.168, 0.136, 0.40, (0, 0, 1.205), M["shirt"], flat=0.62), 0.045, 4)
    arm_body = parts["body"]
    # 领口（立领）
    bevel(oval("collar", 0.079, 0.085, 0.024, (0, -0.004, 1.428), M["white"], flat=0.80), 0.007, 2)
    # 门襟纽扣
    for i in range(3):
        ball("btn_%d" % i, 0.011, (0, -0.104, 1.335 - i * 0.095), M["button"], (1, 0.45, 1), 10, 8)
    # 腰带
    bevel(oval("belt", 0.138, 0.138, 0.038, (0, 0, 1.0), M["belt"], flat=0.62), 0.010, 2)
    box("buckle", (0.046, 0.02, 0.032), (0, -0.088, 1.0), M["button"], 0.006)
    # 短裙（只给女角色显示；坐姿时裙子短到臀部以上，不会插进椅面）
    parts["skirt"] = bevel(oval("skirt", 0.152, 0.196, 0.185, (0, 0, 0.905),
                                M["skirt"], flat=0.74), 0.018, 2)
    # 胯：收窄抬高（原来是块「围裙板」），裆部另用一个球补形
    parts["hips"] = bevel(oval("hips", 0.148, 0.126, 0.235, (0, 0, 0.925), M["pants"], flat=0.66), 0.034, 3)
    # 脖子
    parts["neck"] = oval("neck", 0.049, 0.046, 0.10, (0, 0, 1.44), M["skin"], flat=0.92)

    for side, sx in (("L", 1), ("R", -1)):
        X = sx * 0.172
        X_LEG = sx * 0.090

        # ---- 手臂：一整段（肩→腕）连续曲面，肘部靠权重过渡 ----
        # 被袖子盖住的那一段必须明显细于袖子（差 4mm 以上），否则两层曲面会打架出锯齿
        arm = tube("arm_%s" % side, [
            (0.930, 0.038), (0.960, 0.040), (1.000, 0.042), (1.060, 0.0435),
            (1.110, 0.0445), (1.160, 0.0450), (1.210, 0.0455), (1.270, 0.0460),
            (1.320, 0.0465), (1.355, 0.0465),
        ], M["skin"], 18)
        weight_two(arm, "LowerArm.%s" % side, "UpperArm.%s" % side, 1.105, 1.205)
        arm.location.x += X
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.transform_apply(location=True)
        parts["arm.%s" % side] = arm

        # ---- 袖子：从肩到肘上，顶端收圆当肩头（不再单独一个球） ----
        sleeve = tube("sleeve_%s" % side, [
            (1.135, 0.0490), (1.180, 0.0500), (1.240, 0.0500), (1.300, 0.0510),
            (1.345, 0.0510), (1.372, 0.0485), (1.390, 0.0420), (1.400, 0.0280),
            (1.404, 0.0100),
        ], M["shirt"], 20)
        sleeve.location.x += X
        bpy.context.view_layer.objects.active = sleeve
        bpy.ops.object.transform_apply(location=True)
        # 袖山上半段粘在躯干（Chest）、下半段跟上臂：抬手时肩头不会被"撕开"一条缝
        weight_two(sleeve, "UpperArm.%s" % side, "Chest", 1.285, 1.400)
        parts["sleeve.%s" % side] = sleeve

        # 袖口要套在**前臂**上（1.126，袖子下沿 1.135 之上），否则会从袖子里顶出来一圈白锯齿
        ring("cuff_%s" % side, 0.0465, 0.0090, (X, 0, 1.126), M["white"])

        # ---- 手掌（圆润）+ 拇指 ----
        # 手掌 + 四指 + 拇指（原来是圆角方块，太糊）
        parts["hand.%s" % side] = box("hand_%s" % side, (0.060, 0.040, 0.062),
                                      (X, 0, 0.912), M["skin"], 0.018, 3)
        for fi in range(4):
            fx = X + (fi - 1.5) * 0.0155
            box("finger%d_%s" % (fi, side), (0.0135, 0.019, 0.056),
                (fx, -0.002, 0.856), M["skin"], 0.005, 2)
        box("thumb_%s" % side, (0.019, 0.022, 0.044),
            (X - sx * 0.034, -0.010, 0.898), M["skin"], 0.008, 2,
            rot=(0, math.radians(sx * 24), 0))

        # ---- 腿：一整段（髋→鞋里）连续曲面，膝部靠权重过渡 ----
        leg = tube("leg_%s" % side, [
            (0.095, 0.0430), (0.140, 0.0445), (0.180, 0.0465), (0.220, 0.0500),
            (0.265, 0.0545), (0.325, 0.0585), (0.385, 0.0605), (0.445, 0.0590),
            (0.495, 0.0575), (0.525, 0.0572), (0.565, 0.0595), (0.625, 0.0635),
            (0.705, 0.0685), (0.785, 0.0730), (0.850, 0.0760), (0.890, 0.0745),
            (0.920, 0.0700),
        ], M["pants"], 20)
        weight_two(leg, "LowerLeg.%s" % side, "UpperLeg.%s" % side, 0.465, 0.575)
        leg.location.x += X_LEG
        bpy.context.view_layer.objects.active = leg
        bpy.ops.object.transform_apply(location=True)
        parts["leg.%s" % side] = leg

        # ---- 鞋：鞋面（圆头）+ 薄鞋底（不外扩成"松糕底"） ----
        box("shoe_upper_%s" % side, (0.112, 0.250, 0.098), (X_LEG, -0.046, 0.086),
            M["shoe"], 0.040, 4)
        # 鞋头压圆，正面/侧面看都不是方块
        ball("shoe_toe_%s" % side, 0.059, (X_LEG, -0.148, 0.066),
             M["shoe"], (0.95, 1.05, 0.86), 20, 14)
        # 鞋底：比鞋面窄 4mm、只厚 22mm，贴着地面，不外扩
        parts["foot.%s" % side] = box("shoes_%s" % side, (0.108, 0.258, 0.022),
                                      (X_LEG, -0.048, 0.017), M["sole"], 0.009, 3)

    return parts


# ---------------------------------------------------------------- 骨骼 / 动作（沿用 v1）

BONES = [
    ("Hips", (0, 0, 0.95), (0, 0, 1.10), None),
    ("Spine", (0, 0, 1.10), (0, 0, 1.26), "Hips"),
    ("Chest", (0, 0, 1.26), (0, 0, 1.42), "Spine"),
    ("Neck", (0, 0, 1.42), (0, 0, 1.49), "Chest"),
    ("Head", (0, 0, 1.49), (0, 0, 1.72), "Neck"),
    ("UpperArm.L", (0.09, 0, 1.38), (0.172, 0, 1.20), "Chest"),
    ("LowerArm.L", (0.172, 0, 1.20), (0.172, 0, 1.02), "UpperArm.L"),
    ("Hand.L", (0.172, 0, 1.02), (0.172, 0, 0.86), "LowerArm.L"),
    ("UpperArm.R", (-0.09, 0, 1.38), (-0.172, 0, 1.20), "Chest"),
    ("LowerArm.R", (-0.172, 0, 1.20), (-0.172, 0, 1.02), "UpperArm.R"),
    ("Hand.R", (-0.172, 0, 1.02), (-0.172, 0, 0.86), "LowerArm.R"),
    ("UpperLeg.L", (0.09, 0, 0.92), (0.09, 0, 0.52), "Hips"),
    ("LowerLeg.L", (0.09, 0, 0.52), (0.09, 0, 0.14), "UpperLeg.L"),
    ("Foot.L", (0.09, 0, 0.14), (0.09, -0.20, 0.05), "LowerLeg.L"),
    ("UpperLeg.R", (-0.09, 0, 0.92), (-0.09, 0, 0.52), "Hips"),
    ("LowerLeg.R", (-0.09, 0, 0.52), (-0.09, 0, 0.14), "UpperLeg.R"),
    ("Foot.R", (-0.09, 0, 0.14), (-0.09, -0.20, 0.05), "LowerLeg.R"),
]

BIND = {
    "body": "Chest", "collar": "Chest", "btn_0": "Chest", "btn_1": "Chest", "btn_2": "Chest",
    "belt": "Hips", "buckle": "Hips", "hips": "Hips", "neck": "Neck", "head": "Head",
    "ear_-1": "Head", "ear_1": "Head",
    "nose": "Head", "mouth_0": "Head", "mouth_1": "Head", "mouth_2": "Head",
}
for sx in (-1, 1):
    BIND["eye_white_%d" % sx] = "Head"
    BIND["eye_iris_%d" % sx] = "Head"
    BIND["eye_spark_%d" % sx] = "Head"
    BIND["eye_lid_%d" % sx] = "Head"
    BIND["brow_%d" % sx] = "Head"
for s in ("L", "R"):
    BIND["cuff_%s" % s] = "LowerArm.%s" % s
    BIND["hand_%s" % s] = "Hand.%s" % s
    for _fi in range(4):
        BIND["finger%d_%s" % (_fi, s)] = "Hand.%s" % s
    BIND["thumb_%s" % s] = "Hand.%s" % s
    BIND["skirt"] = "Hips"
    BIND["shoe_upper_%s" % s] = "Foot.%s" % s
    BIND["shoes_%s" % s] = "Foot.%s" % s


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


def skin(arm):
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        if not obj.vertex_groups:
            base = obj.name.split(".")[0]
            bone = BIND.get(base)
            if not bone:
                bone = "Head" if base.startswith(("hair", "eye", "brow", "nose", "mouth", "ear")) else "Chest"
            vg = obj.vertex_groups.new(name=bone)
            vg.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
        m = obj.modifiers.new("Armature", "ARMATURE")
        m.object = arm
        obj.parent = arm


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


def key_legs(arm, f, thigh=0.0, shin=0.0, foot=0.0):
    """给站姿动作补上腿部中立帧。

    关键：如果某个动作不 key 腿，播放时腿会**保留上一个动作的姿势**
    （比如刚坐下再站起来，腿还是弯的、鞋和腿分离）——所有站姿动作都必须自带腿。
    """
    for s_ in ("L", "R"):
        key(arm, "UpperLeg.%s" % s_, f, rot=(math.radians(thigh), 0, 0))
        key(arm, "LowerLeg.%s" % s_, f, rot=(math.radians(shin), 0, 0))
        key(arm, "Foot.%s" % s_, f, rot=(math.radians(foot), 0, 0))


def act_idle(arm, F):
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "Chest", f, rot=(math.radians(1.6) * ph, 0, 0))
        key(arm, "Head", f, rot=(math.radians(-1.4) * ph, 0, 0))
        key(arm, "UpperArm.L", f, rot=(0, 0, math.radians(-4)))
        key(arm, "UpperArm.R", f, rot=(0, 0, math.radians(4)))
        key(arm, "Hips", f, loc=(0, 0.008 * ph, 0))
        key_legs(arm, f)


def act_walk(arm, F):
    for f, s in ((1, 1), (F // 4 + 1, 0), (F // 2 + 1, -1), (F * 3 // 4 + 1, 0), (F + 1, 1)):
        key(arm, "UpperLeg.L", f, rot=(math.radians(27) * s, 0, 0))
        key(arm, "UpperLeg.R", f, rot=(-math.radians(27) * s, 0, 0))
        key(arm, "LowerLeg.L", f, rot=(max(0, -math.radians(24) * s), 0, 0))
        key(arm, "LowerLeg.R", f, rot=(max(0, math.radians(24) * s), 0, 0))
        key(arm, "UpperArm.L", f, rot=(-math.radians(24) * s, 0, 0))
        key(arm, "UpperArm.R", f, rot=(math.radians(24) * s, 0, 0))
        key(arm, "Hips", f, loc=(0, abs(s) * 0.012, 0))
        key(arm, "Chest", f, rot=(0, 0, math.radians(3) * s))


def act_sit(arm, F):
    """坐姿：双手**分开、平放在桌面上**（打字/握鼠标），不是两只手在胸前汇合。

    几何依据：坐下去后肩在 z≈0.96，椅子/桌面 0.75；上臂基本垂直、前臂水平前伸，
    手腕正好落在桌面高度，两肘间距 = 肩宽。
    """
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "Hips", f, loc=(0, -0.42, 0.02), rot=(math.radians(-7), 0, 0))
        key(arm, "Spine", f, rot=(math.radians(6), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(4), 0, 0))
        for s_, sgn in (("L", 1), ("R", -1)):
            # 大腿比水平再低 ~8°，膝盖略低于髋，小腿垂直、脚掌贴地
            key(arm, "UpperLeg.%s" % s_, f, rot=(math.radians(-70), 0, math.radians(sgn * 4)))
            key(arm, "LowerLeg.%s" % s_, f, rot=(math.radians(70), 0, 0))
            key(arm, "Foot.%s" % s_, f, rot=(math.radians(4), 0, 0))
            # 上臂几乎垂直、略向外（z 负 = 向外），前臂水平前伸
            key(arm, "UpperArm.%s" % s_, f, rot=(math.radians(-16),
                                                0, math.radians(-4 * sgn)))
            key(arm, "LowerArm.%s" % s_, f, rot=(math.radians(-74), 0, 0))
            key(arm, "Hand.%s" % s_, f, rot=(math.radians(-10), 0, 0))
        # 微微点头（呼吸感）
        key(arm, "Head", f, rot=(math.radians(-3 + 1.2 * ph), 0, 0))


def sit_legs_chair(arm, f, ph=0.0):
    """工位坐姿的腿（坐着的小动作都复用它，保证腿不会跳变）。"""
    key(arm, "Hips", f, loc=(0, -0.42, 0.02), rot=(math.radians(-7), 0, 0))
    for s_, sgn in (("L", 1), ("R", -1)):
        key(arm, "UpperLeg.%s" % s_, f, rot=(math.radians(-70), 0, math.radians(sgn * 4)))
        key(arm, "LowerLeg.%s" % s_, f, rot=(math.radians(70), 0, 0))
        key(arm, "Foot.%s" % s_, f, rot=(math.radians(4), 0, 0))


def act_sit_phone(arm, F):
    """坐着看手机：一只手抬到脸前，头低下去。"""
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        sit_legs_chair(arm, f)
        key(arm, "Spine", f, rot=(math.radians(4), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(5), 0, math.radians(-3)))
        key(arm, "Head", f, rot=(math.radians(17 + ph), 0, math.radians(-6)))
        key(arm, "UpperArm.R", f, rot=(math.radians(-34), 0, math.radians(26)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-104), 0, 0))
        key(arm, "Hand.R", f, rot=(math.radians(-16), 0, math.radians(-10)))
        key(arm, "UpperArm.L", f, rot=(math.radians(-12), 0, math.radians(-6)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-30), 0, 0))


def act_sit_look(arm, F):
    """坐着发呆：左右张望（腿保持坐姿）。"""
    for k, yaw in ((0.0, 0), (0.25, 1), (0.5, 0), (0.75, -1), (1.0, 0)):
        f = 1 + int(round(F * k))
        sit_legs_chair(arm, f)
        key(arm, "Spine", f, rot=(math.radians(3), 0, math.radians(4 * yaw)))
        key(arm, "Chest", f, rot=(math.radians(3), 0, math.radians(7 * yaw)))
        key(arm, "Head", f, rot=(math.radians(-2), math.radians(30 * yaw), 0))
        key(arm, "UpperArm.L", f, rot=(math.radians(-16), 0, math.radians(-4)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-74), 0, 0))
        key(arm, "Hand.L", f, rot=(math.radians(-10), 0, 0))
        key(arm, "UpperArm.R", f, rot=(math.radians(-16), 0, math.radians(4)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-74), 0, 0))
        key(arm, "Hand.R", f, rot=(math.radians(-10), 0, 0))


def act_sit_sofa(arm, F):
    """沙发坐姿：身体后靠、双手搭在腿上（不是往前伸着打字）。"""
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "Hips", f, loc=(0, -0.42, 0.05), rot=(math.radians(-12), 0, 0))
        key(arm, "Spine", f, rot=(math.radians(9), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(6), 0, 0))
        for s_, sgn in (("L", 1), ("R", -1)):
            key(arm, "UpperLeg.%s" % s_, f, rot=(math.radians(-74), 0, math.radians(sgn * 7)))
            key(arm, "LowerLeg.%s" % s_, f, rot=(math.radians(64), 0, 0))
            key(arm, "Foot.%s" % s_, f, rot=(math.radians(8), 0, 0))
            # 上臂略前、前臂搭在大腿上
            key(arm, "UpperArm.%s" % s_, f, rot=(math.radians(-14), 0, math.radians(-10 * sgn)))
            key(arm, "LowerArm.%s" % s_, f, rot=(math.radians(-44), 0, 0))
            key(arm, "Hand.%s" % s_, f, rot=(math.radians(16), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-2 + 1.5 * ph), 0, math.radians(3)))


def act_sit_stool(arm, F):
    """高脚凳坐姿：腿自然下垂（脚不落地），手搭在吧台边。"""
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "Hips", f, loc=(0, -0.40, 0.02), rot=(math.radians(-6), 0, 0))
        key(arm, "Spine", f, rot=(math.radians(5), 0, 0))
        for s_, sgn in (("L", 1), ("R", -1)):
            key(arm, "UpperLeg.%s" % s_, f, rot=(math.radians(-56), 0, math.radians(sgn * 5)))
            key(arm, "LowerLeg.%s" % s_, f, rot=(math.radians(34), 0, 0))
            key(arm, "Foot.%s" % s_, f, rot=(math.radians(-14), 0, 0))
            key(arm, "UpperArm.%s" % s_, f, rot=(math.radians(-14), 0, math.radians(-9 * sgn)))
            key(arm, "LowerArm.%s" % s_, f, rot=(math.radians(-46), 0, 0))
            key(arm, "Hand.%s" % s_, f, rot=(math.radians(6), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-3 + 1.2 * ph), 0, 0))


def act_stretch(arm, F):
    """伸懒腰：双臂上举、背微弓、抬头，再放下。"""
    for k, up in ((0.0, 0), (0.3, 1), (0.65, 1), (1.0, 0)):
        f = 1 + int(round(F * k))
        key(arm, "UpperArm.L", f, rot=(math.radians(-152 if up else 6), 0,
                                      math.radians(-18 if up else -5)))
        key(arm, "UpperArm.R", f, rot=(math.radians(-152 if up else 6), 0,
                                      math.radians(18 if up else 5)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-26 if up else -10), 0, 0))
        key(arm, "LowerArm.R", f, rot=(math.radians(-26 if up else -10), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(-7 if up else 1), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-14 if up else 0), 0, 0))
        key(arm, "Hips", f, loc=(0, 0.012 if up else 0, 0))
        key_legs(arm, f)


def act_phone(arm, F):
    """低头看手机：右手抬到胸前，头微低。"""
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "UpperArm.R", f, rot=(math.radians(-40), 0, math.radians(20)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-98), 0, 0))
        key(arm, "Hand.R", f, rot=(math.radians(-18), 0, math.radians(-8)))
        key(arm, "Head", f, rot=(math.radians(15 + ph), 0, math.radians(-5)))
        key(arm, "UpperArm.L", f, rot=(math.radians(-6), 0, math.radians(-6)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-20), 0, 0))
        key(arm, "Chest", f, rot=(math.radians(3), 0, 0))
        key_legs(arm, f)


def act_look(arm, F):
    """左右张望（发呆）。"""
    for k, yaw in ((0.0, 0), (0.25, 1), (0.5, 0), (0.75, -1), (1.0, 0)):
        f = 1 + int(round(F * k))
        key(arm, "Head", f, rot=(0, math.radians(34 * yaw), 0))
        key(arm, "Chest", f, rot=(0, math.radians(8 * yaw), 0))
        key_legs(arm, f)


def act_dance(arm, F):
    """四拍：左手前上 → 右手前上 → 双手举起 → 半蹲，再从头来。

    注意骨骼局部轴：X 是"前后摆"，Y 是沿骨的扭转（转了看不出动作），Z 是"左右张"。
    之前用 Y 扭，所以看起来只是站着。"""
    beats = [
        # (相位, 左手上举, 右手上举, 蹲)
        (0.00, True, False, False),
        (0.25, False, True, False),
        (0.50, True, True, False),
        (0.75, False, False, True),
        (1.00, True, False, False),
    ]
    for k, up_l, up_r, squat in beats:
        f = 1 + int(round(F * k))
        key(arm, "Hips", f, loc=(0, -0.05 if squat else 0.03, 0),
            rot=(0, 0, math.radians(-11 if up_l else 11)))
        key(arm, "Chest", f, rot=(math.radians(4 if squat else -4), 0,
                                  math.radians(7 if up_l else -7)))
        key(arm, "Head", f, rot=(math.radians(3 if squat else -7), 0,
                                 math.radians(-7 if up_l else 7)))
        # 手臂：X 轴往前往上摆
        key(arm, "UpperArm.L", f, rot=(math.radians(-132 if up_l else 12),
                                      0, math.radians(-26 if up_l else -8)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-38 if up_l else -16), 0, 0))
        key(arm, "UpperArm.R", f, rot=(math.radians(-132 if up_r else 12),
                                      0, math.radians(26 if up_r else 8)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-38 if up_r else -16), 0, 0))
        # 腿：左右交替屈膝，蹲拍两边都屈
        key(arm, "UpperLeg.L", f, rot=(math.radians(-16 if (squat or up_r) else 2), 0, 0))
        key(arm, "UpperLeg.R", f, rot=(math.radians(-16 if (squat or up_l) else 2), 0, 0))
        key(arm, "LowerLeg.L", f, rot=(math.radians(22 if (squat or up_r) else 3), 0, 0))
        key(arm, "LowerLeg.R", f, rot=(math.radians(22 if (squat or up_l) else 3), 0, 0))
        key(arm, "Foot.L", f, rot=(math.radians(-8 if squat else 0), 0, 0))
        key(arm, "Foot.R", f, rot=(math.radians(-8 if squat else 0), 0, 0))


def act_sing(arm, F):
    for f, ph in ((1, 0), (F // 2 + 1, 1), (F + 1, 0)):
        key(arm, "UpperArm.R", f, rot=(math.radians(-100 + 6 * ph), math.radians(34), math.radians(-16)))
        key(arm, "LowerArm.R", f, rot=(math.radians(-104 - 6 * ph), 0, 0))
        key(arm, "Head", f, rot=(math.radians(-9 - 3 * ph), 0, math.radians(-4)))
        key(arm, "Chest", f, rot=(math.radians(2), 0, math.radians(4)))
        key(arm, "Hips", f, loc=(0, 0.02 * ph, 0))
        key(arm, "UpperArm.L", f, rot=(0, math.radians(-26), math.radians(10)))
        key(arm, "LowerArm.L", f, rot=(math.radians(-22), 0, 0))
        key_legs(arm, f)


# ---------------------------------------------------------------- 预览

def setup_preview():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 40
    sc.cycles.use_denoising = True
    sc.cycles.device = "CPU"
    sc.render.resolution_x = 640
    sc.render.resolution_y = 860
    # AgX 会把肤色压灰；预览用 Standard，颜色更接近材质本身
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.world = bpy.data.worlds.new("W")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.64, 0.68, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 0.55
    bpy.ops.object.light_add(type="AREA", location=(2.2, -2.6, 3.2))
    key_l = bpy.context.active_object
    key_l.data.energy = 110
    key_l.data.size = 3.0
    key_l.rotation_euler = (math.radians(52), 0, math.radians(36))
    bpy.ops.object.light_add(type="AREA", location=(-2.4, -1.6, 1.8))
    fill = bpy.context.active_object
    fill.data.energy = 40
    fill.data.size = 4.0
    fill.rotation_euler = (math.radians(78), 0, math.radians(-52))

    bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
    g = bpy.context.active_object
    g.data.materials.append(mat("mat_ground", (0.86, 0.86, 0.85), 0.9))
    bpy.ops.object.camera_add(location=(0, -3.4, 1.45), rotation=(math.radians(84), 0, 0))
    cam = bpy.context.active_object
    cam.data.lens = 68
    sc.camera = cam
    return cam


def render_views(arm, tag=""):
    cam = setup_preview()
    shots = {
        "face": ((0, -0.85, 1.615), (math.radians(90), 0, 0), 85, (440, 470)),
        "front": ((0, -3.4, 0.95), (math.radians(90), 0, 0), 60, (620, 980)),
        "three-quarter": ((1.9, -2.7, 1.60), (math.radians(78), 0, math.radians(36)), 62, (620, 980)),
    }
    for nm, (loc, rot, lens, res) in shots.items():
        cam.location = loc
        cam.rotation_euler = rot
        cam.data.lens = lens
        bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y = res
        bpy.context.scene.render.filepath = os.path.join(OUT_PV, "v2-%s%s.png" % (nm, tag))
        bpy.ops.render.render(write_still=True)
        print("[preview]", nm)


def render_actions(arm, cam):
    """动作表：5 条动作各抽 3 帧，用来肉眼检查坐/走/蹦迪/唱歌有没有穿模。"""
    cam.location = (0, -3.6, 0.98)
    cam.rotation_euler = (math.radians(90), 0, 0)
    cam.data.lens = 55
    sc = bpy.context.scene
    sc.render.resolution_x = 420
    sc.render.resolution_y = 660
    for act in sorted(bpy.data.actions, key=lambda a: a.name):
        arm.animation_data.action = act
        f0, f1 = act.frame_range
        for i, k in enumerate((0.1, 0.45, 0.8)):
            sc.frame_set(int(f0 + (f1 - f0) * k))
            sc.render.filepath = os.path.join(OUT_PV, "v2-act-%s-%d.png" % (act.name, i))
            bpy.ops.render.render(write_still=True)
        print("[act]", act.name)
    arm.animation_data.action = None
    sc.frame_set(1)


def main():
    reset()
    M = {
        "skin": mat("mat_skin", (0.80, 0.58, 0.42)),
        "hair": mat("mat_hair", (0.035, 0.03, 0.032)),
        "shirt": mat("mat_shirt", (0.30, 0.52, 0.72)),
        "pants": mat("mat_pants", (0.22, 0.24, 0.30)),
        "shoe": mat("mat_shoe", (0.16, 0.14, 0.14)),
        "sole": mat("mat_sole", (0.10, 0.09, 0.09)),
        "white": mat("mat_white", (0.95, 0.95, 0.94)),
        "eye": mat("mat_eye", (0.09, 0.07, 0.06)),
        "mouth": mat("mat_mouth", (0.55, 0.28, 0.28)),
        "button": mat("mat_button", (0.85, 0.82, 0.72)),
        "belt": mat("mat_belt", (0.15, 0.13, 0.12)),
        "skirt": mat("mat_skirt", (0.24, 0.27, 0.36)),
    }
    build_head(M)
    hairs = build_hair(M)
    build_body(M)

    arm = build_armature()
    skin(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.context.scene.render.fps = 24
    make_action(arm, "idle", 48, act_idle)
    make_action(arm, "walk", 32, act_walk)
    make_action(arm, "sit", 48, act_sit)
    make_action(arm, "sit_sofa", 48, act_sit_sofa)
    make_action(arm, "sit_stool", 48, act_sit_stool)
    make_action(arm, "sit_phone", 60, act_sit_phone)
    make_action(arm, "sit_look", 72, act_sit_look)
    make_action(arm, "dance", 48, act_dance)
    make_action(arm, "sing", 48, act_sing)
    make_action(arm, "stretch", 56, act_stretch)
    make_action(arm, "phone", 60, act_phone)
    make_action(arm, "look", 72, act_look)
    arm.animation_data.action = None

    # 预览前把姿势清干净（否则会继承最后一条动作的 pose，看起来在半空劈叉）
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
        pb.scale = (1, 1, 1)
    arm.animation_data.action = None
    bpy.context.scene.frame_set(1)

    # 1) 先导出：三套发型都要留在 GLB 里（前端按人切换）
    os.makedirs(os.path.dirname(OUT_GLB), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for o in bpy.data.objects:
        keep = o.type == "ARMATURE" or (o.type == "MESH" and not o.name.startswith("Plane"))
        o.select_set(keep)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.gltf(
        filepath=OUT_GLB, export_format="GLB", use_selection=True, export_apply=False,
        export_animations=True, export_animation_mode="ACTIONS", export_skins=True, export_yup=True,
        export_cameras=False, export_lights=False,
    )
    print("[done]", OUT_GLB, os.path.getsize(OUT_GLB), "bytes")

    # 2) 预览只留短发（其余两套直接删掉，hide_render 对蒙皮对象不可靠）
    for o in list(bpy.data.objects):
        if o.name.startswith("hair_") and o.name.split("_")[1][:1] != "0":
            bpy.data.objects.remove(o, do_unlink=True)
    render_views(arm, "")
    render_actions(arm, bpy.context.scene.camera)


main()
