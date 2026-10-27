"""仅重新导出 agent-v2.glb（不做预览渲染），供改完 build_agent_v2.py 后快速重导。

用法：blender --background --python export_agent_v2.py
原理：把主脚本的 render_views / render_actions 替换为空，让它的 main() 只走到 GLB 导出。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(HERE, "build_agent_v2.py")

# 屏蔽预览渲染（会渲染大量 PNG，耗时且非本次需要）
import types
noop = lambda *a, **k: None

src = open(MAIN, encoding="utf-8").read()
# 在 main() 末尾替换两次渲染调用为空（保留 GLB 导出）
src = src.replace("    render_views(arm, \"\")\n", "    pass\n")
src = src.replace("    render_actions(arm, bpy.context.scene.camera)\n", "    pass\n")

g = {"__name__": "__main__", "__file__": MAIN}
exec(compile(src, MAIN, "exec"), g)
