import { ref } from "vue";
import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
import KeypointCanvas from "./KeypointCanvas.vue";
import KeypointPreview from "./KeypointPreview.vue";
import { useKeypointTool } from "./useKeypointTool";

export const keypointPlugin: AnnotationTaskPlugin = {
  name: "keypoint",
  label: "关键点",
  color: "danger",
  renderer: KeypointCanvas,
  tools: [{ name: "keypoint", label: "关键点", title: "依次放点，双击后拉出包围框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "Keypoint") return false;
    const kps = shape.keypoints || [];
    if (kps.length === 0) return false;
    return kps.every((k: any) => 0 <= k.x && k.x <= 1 && 0 <= k.y && k.y <= 1);
  },
  tool: (() => {
    const kp = useKeypointTool();
    const boxDrafting = ref(false);
    const visibility = ref("Visible");
    return {
      name: "keypoint",
      preview: KeypointPreview,
      state: { pending: kp.pending, boxStart: kp.boxStart, boxEnd: kp.boxEnd, boxDrafting },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        if (kp.boxMode.value) {
          kp.setBoxStart(p);
          boxDrafting.value = true;
          return null;
        }
        const kpNames =
          ctx.classes?.find((c) => c.id === ctx.selectedClassId)?.keypoint_names || [];
        kp.setNames(kpNames);
        kp.addPoint(p, visibility.value);
        return null;
      },
      keydown(e) {
        if (["0", "1", "2"].includes(e.key)) {
          const map: Record<string, string> = { "0": "Hidden", "1": "Occluded", "2": "Visible" };
          visibility.value = map[e.key];
          return true;
        }
        return false;
      },
      move(ctx) {
        const p = ctx.point;
        if (boxDrafting.value && p) kp.updateBox(p);
      },
      up() {
        if (!boxDrafting.value) return null;
        boxDrafting.value = false;
        return kp.build();
      },
      dblclick() {
        kp.beginBox();
        return null;
      },
      reset() {
        boxDrafting.value = false;
        kp.pending.value = [];
        kp.boxMode.value = false;
        kp.boxStart.value = null;
        kp.boxEnd.value = null;
      },
    };
  })(),
  interaction: {
    move(ctx: DragContext): void {
      const { ann, orig, dx, dy } = ctx;
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      if (ann.bounding_box && orig.bounding_box) {
        ann.bounding_box.cx = nc(orig.bounding_box.cx + dx);
        ann.bounding_box.cy = nc(orig.bounding_box.cy + dy);
      }
      ann.keypoints = (orig.keypoints || []).map((k: any) => ({
        ...k,
        x: nc(k.x + dx),
        y: nc(k.y + dy),
      }));
      ctx.trigger();
    },
    resize(ctx: DragContext): void {
      const { ann, orig, handle, dx, dy } = ctx;
      const b = ann.bounding_box;
      if (!b || !orig.bounding_box) return;
      const o = orig.bounding_box;
      let x1 = o.cx - o.width / 2,
        y1 = o.cy - o.height / 2,
        x2 = o.cx + o.width / 2,
        y2 = o.cy + o.height / 2;
      if (handle.includes("l")) x1 = Math.min(x2 - 0.01, x1 + dx);
      if (handle.includes("r")) x2 = Math.max(x1 + 0.01, x2 + dx);
      if (handle.includes("t")) y1 = Math.min(y2 - 0.01, y1 + dy);
      if (handle.includes("b")) y2 = Math.max(y1 + 0.01, y2 + dy);
      const nw = Math.max(0.01, x2 - x1);
      const nh = Math.max(0.01, y2 - y1);
      const oW = o.width || 1;
      const oH = o.height || 1;
      (orig.keypoints || []).forEach((k: any, i: number) => {
        const rx = ((k.x - (o.cx - oW / 2)) / oW + 1) / 2;
        const ry = ((k.y - (o.cy - oH / 2)) / oH + 1) / 2;
        if (ann.keypoints?.[i]) {
          ann.keypoints[i].x = Math.max(0, Math.min(1, x1 + rx * nw));
          ann.keypoints[i].y = Math.max(0, Math.min(1, y1 + ry * nh));
        }
      });
      b.cx = (x1 + x2) / 2;
      b.cy = (y1 + y2) / 2;
      b.width = nw;
      b.height = nh;
      ctx.trigger();
    },
    vertexMove(ctx: DragContext): void {
      const kp = ctx.ann.keypoints?.[Number(ctx.handle)];
      if (!kp || !ctx.point) return;
      kp.x = Math.max(0, Math.min(1, ctx.point.x));
      kp.y = Math.max(0, Math.min(1, ctx.point.y));
      ctx.trigger();
    },
    vertexDelete(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.keypoints?.length) return;
      if (ann.keypoints.length <= 1) return;
      ann.keypoints.splice(idx, 1);
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const b = ann.bounding_box;
      if (!b) return { x: 0, y: 0 };
      return { x: b.cx - b.width / 2, y: b.cy - b.height / 2 };
    },
  },
};
