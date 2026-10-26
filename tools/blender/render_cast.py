"""把下载到的所有角色 glb 渲染成"半身像"，方便人眼挑选脸。

用法：blender -b -P tools/blender/render_cast.py
产物：docs/mockups/cast/<包>__<文件名>.png
"""

import math
import os

import bpy

ROOT = r"C:\Users\aichao\.local\share\opencode\worktree\ce637a15bb0a57b0b07a4b910025d9e2c851dcf4\lively-ferret"
CHARS = os.path.join(ROOT, "frontend", "public", "office", "characters")
OUT = os.path.join(ROOT, "docs", "mockups", "cast")


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_shadows = True
    sc.display.shading.show_cavity = True
    sc.display.render_aa = "8"
    sc.render.resolution_x = 560
    sc.render.resolution_y = 720
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("W")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.86, 0.87, 1)


def bbox_of_meshes():
    import mathutils

    lo = mathutils.Vector((1e9, 1e9, 1e9))
    hi = mathutils.Vector((-1e9, -1e9, -1e9))
    found = False
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        found = True
        for c in o.bound_box:
            v = o.matrix_world @ mathutils.Vector(c)
            lo.x, lo.y, lo.z = min(lo.x, v.x), min(lo.y, v.y), min(lo.z, v.z)
            hi.x, hi.y, hi.z = max(hi.x, v.x), max(hi.y, v.y), max(hi.z, v.z)
    if not found:
        return None
    return lo, hi


def render_one(path, out_png):
    reset()
    try:
        bpy.ops.import_scene.gltf(filepath=path)
    except Exception as e:  # noqa: BLE001
        print("[skip]", os.path.basename(path), e)
        return False
    bb = bbox_of_meshes()
    if not bb:
        print("[skip-empty]", os.path.basename(path))
        return False
    lo, hi = bb
    height = hi.z - lo.z
    cx = (lo.x + hi.x) / 2
    # 半身像：取头部往下到胸口
    frame_h = max(0.62, 0.44 * height)          # 半身：头 + 胸
    head_z = hi.z - 0.40 * frame_h               # 画面中心（顶端留一点空）

    setup_render()
    bpy.ops.object.camera_add(location=(cx, lo.y - 2.2, head_z))
    cam = bpy.context.active_object
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = frame_h
    cam.rotation_euler = (math.radians(90), 0, 0)  # 正视 -Y
    bpy.context.scene.camera = cam

    bpy.context.scene.render.filepath = out_png
    bpy.ops.render.render(write_still=True)
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    packs = [d for d in os.listdir(CHARS) if os.path.isdir(os.path.join(CHARS, d))]
    total = 0
    for pack in packs:
        pdir = os.path.join(CHARS, pack)
        files = []
        for root2, _dirs, fns in os.walk(pdir):
            for fn in fns:
                if fn.lower().endswith(".glb") and "Animation" not in fn:
                    files.append(os.path.join(root2, fn))
        for full in sorted(files):
            fn = os.path.basename(full)
            out = os.path.join(OUT, f"{pack}__{fn[:-4]}.png")
            ok = render_one(full, out)
            if ok:
                total += 1
                print("[cast]", pack, fn)
    print("[done]", total)


main()
