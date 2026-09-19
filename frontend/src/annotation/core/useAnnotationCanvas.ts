import { ref } from "vue";
import type { Point } from "./types";

export function useAnnotationCanvas() {
  const cw = ref(0); // 图像自然宽(px)
  const ch = ref(0); // 图像自然高(px)
  const dw = ref(0); // 图像显示宽(px)
  const dh = ref(0); // 图像显示高(px)
  const zoom = ref(1);
  const panX = ref(0);
  const panY = ref(0);

  const svgViewBox = () => `0 0 ${cw.value} ${ch.value}`;

  const svgStyle = () => ({
    width: dw.value + "px",
    height: dh.value + "px",
    transform: `translate(-50%,-50%) translate(${panX.value}px,${panY.value}px)`,
  });

  function setImageSize(w: number, h: number) {
    cw.value = w;
    ch.value = h;
  }

  function setDisplaySize(w: number, h: number) {
    dw.value = w;
    dh.value = h;
  }

  function fitZoom(containerW: number, containerH: number) {
    if (!cw.value || !ch.value || !containerW || !containerH) return;
    zoom.value = Math.min(containerW / cw.value, containerH / ch.value, 3);
    dw.value = cw.value * zoom.value;
    dh.value = ch.value * zoom.value;
  }

  // 图像左上角在容器内的偏移（图像居中 + pan）
  function imageOffset(containerW: number, containerH: number) {
    return {
      left: containerW / 2 - dw.value / 2 + panX.value,
      top: containerH / 2 - dh.value / 2 + panY.value,
    };
  }

  // 容器相对坐标(相对容器左上角) → 图像归一化坐标 [0,1]
  function containerToImage(cx: number, cy: number, containerW: number, containerH: number): Point {
    const off = imageOffset(containerW, containerH);
    if (dw.value <= 0 || dh.value <= 0) return { x: 0, y: 0 };
    return {
      x: (cx - off.left) / dw.value,
      y: (cy - off.top) / dh.value,
    };
  }

  function setPan(x: number, y: number) {
    panX.value = x;
    panY.value = y;
  }

  return {
    cw,
    ch,
    dw,
    dh,
    zoom,
    panX,
    panY,
    svgViewBox,
    svgStyle,
    setImageSize,
    setDisplaySize,
    fitZoom,
    containerToImage,
    imageOffset,
    setPan,
  };
}
