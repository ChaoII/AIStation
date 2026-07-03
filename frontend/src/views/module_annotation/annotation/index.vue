<template>
  <div class="ann-page">
    <div class="ann-header">
      <div class="ann-title">
        <el-button text :icon="ArrowLeft" @click="handleBack" />
        <el-tag :type="taskTypeTag" size="small">{{ taskTypeLabel }}</el-tag>
        <span class="task-name">{{ task?.name }}</span>
      </div>
      <div class="header-right">
        <span class="progress-text">{{ annotatedCount }}/{{ totalCount }}</span>
        <el-progress
          :percentage="progressPct"
          :stroke-width="6"
          :show-text="false"
          style="width: 100px"
        />
      </div>
    </div>
    <div class="ann-body">
      <!-- 左侧工具栏 -->
      <aside class="ann-leftbar">
        <div class="tool-list">
          <div
            v-for="t in displayTools"
            :key="t.name"
            class="tool-btn"
            :class="{ active: currentTool === t.name }"
            :title="t.tip"
            @click="setTool(t.name)"
          >
            <el-icon :size="18"><component :is="t.icon" /></el-icon>
            <span class="tool-label">{{ t.label }}</span>
          </div>
        </div>
      </aside>
      <!-- 画布 -->
      <main ref="canvasWrapRef" class="ann-canvas-area">
        <div
          ref="canvasRef"
          class="canvas-container"
          :style="{ cursor: toolCursor }"
          @mousedown="onMouseDown"
          @mousemove="onMouseMove"
          @mouseup="onMouseUp"
          @mouseenter="onMouseEnter"
          @mouseleave="onMouseLeave"
          @wheel.prevent="onWheel"
          @dblclick="onDblClick"
          @contextmenu.prevent
        >
          <!-- 十字线 -->
          <div
            v-show="showCrosshair"
            ref="cxXRef"
            class="crosshair crosshair-x"
            :style="[cxStyle, { height: annSettings.crosshairWidth + 'px' }]"
          />
          <div
            v-show="showCrosshair"
            ref="cxYRef"
            class="crosshair crosshair-y"
            :style="[cxStyle, { width: annSettings.crosshairWidth + 'px' }]"
          />
          <div
            v-show="showCrosshair && annSettings.crosshairCircle"
            ref="cxCircleRef"
            class="crosshair-circle"
          />
          <!-- 框预览（容器相对坐标） -->
          <div v-show="drawing" ref="boxPreviewRef" class="box-preview" />
          <img
            v-if="imgUrl"
            ref="imgRef"
            :src="imgUrl"
            :style="imgStyle"
            class="ann-img"
            draggable="false"
            @load="onImgLoad"
            @error="imgUrl = ''"
          />
          <svg v-if="imgUrl" class="ann-svg" :style="svgStyle" :viewBox="`0 0 ${cw} ${ch}`">
            <!-- 已有标注 -->
            <g
              v-for="ann in store.annotations"
              :key="ann.id"
              :data-ann-id="ann.id"
              @mousedown.left.prevent="onAnnMouseDown($event, ann)"
            >
              <template v-if="ann.type === 'AxisAlignedBox'">
                <rect
                  :x="ann.x1 * cw"
                  :y="ann.y1 * ch"
                  :width="(ann.x2 - ann.x1) * cw"
                  :height="(ann.y2 - ann.y1) * ch"
                  :stroke="clsColor(ann.class_id)"
                  :stroke-width="
                    store.selectedAnnotationId === ann.id
                      ? annSettings.selStrokeWidth
                      : annSettings.strokeWidth
                  "
                  :fill="
                    store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'none'
                  "
                  vector-effect="non-scaling-stroke"
                />
                <g v-if="store.selectedAnnotationId === ann.id">
                  <rect
                    v-for="h in boxHandles(ann)"
                    :key="h.key"
                    :x="h.x - 4"
                    :y="h.y - 4"
                    width="8"
                    height="8"
                    fill="#fff"
                    stroke="#1a1a1a"
                    stroke-width="1.5"
                    :data-handle="h.key"
                    class="handle"
                    vector-effect="non-scaling-stroke"
                  />
                </g>
                <g class="ann-label">
                  <rect
                    :x="ann.x1 * cw"
                    :y="ann.y1 * ch - (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) - 4"
                    :width="(labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)) + 4"
                    :height="(labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) + 4"
                    :fill="clsColor(ann.class_id)"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="0.5"
                    vector-effect="non-scaling-stroke"
                    rx="1"
                  />
                  <text
                    :x="ann.x1 * cw + 2"
                    :y="ann.y1 * ch - 2"
                    fill="#ffffff"
                    font-weight="500"
                    text-anchor="start"
                    font-family="Microsoft YaHei,sans-serif"
                    :font-size="annSettings.labelFontSize"
                    dominant-baseline="text-after-edge"
                  >
                    {{ getCls(ann.class_id)?.name }}
                  </text>
                </g>
              </template>
              <template v-if="ann.type === 'RotatedBox'">
                <rect
                  :x="ann.cx * cw - (ann.width * cw) / 2"
                  :y="ann.cy * ch - (ann.height * ch) / 2"
                  :width="ann.width * cw"
                  :height="ann.height * ch"
                  :stroke="clsColor(ann.class_id)"
                  :stroke-width="
                    store.selectedAnnotationId === ann.id
                      ? annSettings.selStrokeWidth
                      : annSettings.strokeWidth
                  "
                  :fill="
                    store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'none'
                  "
                  vector-effect="non-scaling-stroke"
                  :transform="`rotate(${(ann.angle * 180) / Math.PI} ${ann.cx * cw} ${ann.cy * ch})`"
                />
                <g class="ann-label">
                  <rect
                    :x="rbHandlePos(ann, 'tl', cw, ch).x"
                    :y="
                      rbHandlePos(ann, 'tl', cw, ch).y -
                      (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) -
                      4
                    "
                    :width="(labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)) + 4"
                    :height="(labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) + 4"
                    :fill="clsColor(ann.class_id)"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="0.5"
                    vector-effect="non-scaling-stroke"
                    rx="1"
                  />
                  <text
                    :x="rbHandlePos(ann, 'tl', cw, ch).x + 2"
                    :y="rbHandlePos(ann, 'tl', cw, ch).y - 2"
                    fill="#ffffff"
                    font-weight="500"
                    text-anchor="start"
                    font-family="Microsoft YaHei,sans-serif"
                    :font-size="annSettings.labelFontSize"
                    dominant-baseline="text-after-edge"
                  >
                    {{ getCls(ann.class_id)?.name }}
                  </text>
                </g>
                <template v-if="store.selectedAnnotationId === ann.id">
                  <rect
                    v-for="h in ['tl', 'tr', 'bl', 'br']"
                    :key="h"
                    :x="rbHandlePos(ann, h, cw, ch).x - 4"
                    :y="rbHandlePos(ann, h, cw, ch).y - 4"
                    width="8"
                    height="8"
                    fill="#fff"
                    stroke="#1a1a1a"
                    stroke-width="1.5"
                    :data-handle="h"
                    class="handle"
                    vector-effect="non-scaling-stroke"
                  />
                  <rect
                    :x="ann.cx * cw - 4"
                    :y="ann.cy * ch - 4"
                    width="8"
                    height="8"
                    fill="#fff"
                    stroke="#1a1a1a"
                    stroke-width="1.5"
                    data-handle="move"
                    class="handle"
                    vector-effect="non-scaling-stroke"
                  />
                  <line
                    :x1="rbHandlePos(ann, 'tc', cw, ch).x"
                    :y1="rbHandlePos(ann, 'tc', cw, ch).y"
                    :x2="rbRotateHandlePos(ann, cw, ch).x"
                    :y2="rbRotateHandlePos(ann, cw, ch).y"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="1"
                  />
                  <circle
                    :cx="rbRotateHandlePos(ann, cw, ch).x"
                    :cy="rbRotateHandlePos(ann, cw, ch).y"
                    r="3"
                    fill="#fff"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="1.5"
                    data-handle="rotate"
                    class="handle"
                  />
                </template>
              </template>
              <template v-if="ann.type === 'Polygon'">
                <path
                  :d="polygonPath(ann)"
                  :stroke="clsColor(ann.class_id)"
                  :stroke-width="
                    store.selectedAnnotationId === ann.id
                      ? annSettings.selStrokeWidth
                      : annSettings.strokeWidth
                  "
                  fill-rule="evenodd"
                  :fill="clsColor(ann.class_id) + '20'"
                  style="pointer-events: none"
                  vector-effect="non-scaling-stroke"
                />
                <rect
                  v-for="B in [polyBBox(ann)]"
                  :key="ann.id + '-bbox'"
                  :x="B.x"
                  :y="B.y"
                  :width="B.w"
                  :height="B.h"
                  :stroke="clsColor(ann.class_id)"
                  :stroke-width="
                    store.selectedAnnotationId === ann.id
                      ? annSettings.selStrokeWidth
                      : annSettings.strokeWidth
                  "
                  fill="transparent"
                  style="pointer-events: all"
                  vector-effect="non-scaling-stroke"
                />
                <g v-for="B in [polyBBox(ann)]" :key="ann.id + '-bb'" class="ann-label">
                  <rect
                    :x="B.x"
                    :y="B.y - (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) - 4"
                    :width="(labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)) + 4"
                    :height="(labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) + 4"
                    :fill="clsColor(ann.class_id)"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="0.5"
                    vector-effect="non-scaling-stroke"
                    rx="1"
                  />
                  <text
                    :x="B.x + 2"
                    :y="B.y - 2"
                    fill="#ffffff"
                    font-weight="500"
                    text-anchor="start"
                    font-family="Microsoft YaHei,sans-serif"
                    :font-size="annSettings.labelFontSize"
                    dominant-baseline="text-after-edge"
                  >
                    {{ getCls(ann.class_id)?.name }}
                  </text>
                </g>
                <template v-if="store.selectedAnnotationId === ann.id">
                  <rect
                    v-for="(p, i) in ann.points"
                    :key="i"
                    :x="p.x * cw - 3"
                    :y="p.y * ch - 3"
                    width="6"
                    height="6"
                    fill="#fff"
                    stroke="#1a1a1a"
                    stroke-width="1.5"
                    :data-handle="'poly-' + i"
                    class="handle"
                    vector-effect="non-scaling-stroke"
                  />
                </template>
              </template>
              <template v-if="ann.type === 'Keypoint'">
                <!-- Bounding box -->
                <rect v-if="ann.bounding_box"
                  :x="ann.bounding_box.cx * cw - (ann.bounding_box.width * cw) / 2"
                  :y="ann.bounding_box.cy * ch - (ann.bounding_box.height * ch) / 2"
                  :width="ann.bounding_box.width * cw" :height="ann.bounding_box.height * ch"
                  :stroke="clsColor(ann.class_id)"
                  :stroke-width="store.selectedAnnotationId === ann.id ? annSettings.selStrokeWidth : annSettings.strokeWidth"
                  fill="rgba(0,0,0,0.04)" style="pointer-events:all" vector-effect="non-scaling-stroke" />
                <!-- Label at top-left corner -->
                <g v-if="ann.bounding_box" class="ann-label">
                  <rect
                    :x="ann.bounding_box.cx * cw - (ann.bounding_box.width * cw) / 2"
                    :y="ann.bounding_box.cy * ch - (ann.bounding_box.height * ch) / 2 - (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) - 4"
                    :width="(labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)) + 4"
                    :height="(labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) + 4"
                    :fill="clsColor(ann.class_id)"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="0.5"
                    vector-effect="non-scaling-stroke"
                    rx="1"
                  />
                  <text
                    :x="ann.bounding_box.cx * cw - (ann.bounding_box.width * cw) / 2 + 2"
                    :y="ann.bounding_box.cy * ch - (ann.bounding_box.height * ch) / 2 - 2"
                    fill="#ffffff"
                    font-weight="500"
                    text-anchor="start"
                    font-family="Microsoft YaHei,sans-serif"
                    :font-size="annSettings.labelFontSize"
                    dominant-baseline="text-after-edge"
                  >
                    {{ getCls(ann.class_id)?.name }}
                  </text>
                </g>
                <!-- Bounding box handles when selected -->
                <template v-if="store.selectedAnnotationId === ann.id && ann.bounding_box">
                  <rect v-for="hkey in ['tl','tr','bl','br','tc','bc','ml','mr']" :key="hkey"
                    :x="kpRbHandlePos(ann.bounding_box, hkey, cw, ch).x - 4"
                    :y="kpRbHandlePos(ann.bounding_box, hkey, cw, ch).y - 4"
                    width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5"
                    :data-handle="hkey" class="handle" vector-effect="non-scaling-stroke" />
                  <rect :x="ann.bounding_box.cx * cw - 4" :y="ann.bounding_box.cy * ch - 4"
                    width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5"
                    data-handle="move" class="handle" vector-effect="non-scaling-stroke" />
                </template>
                <g v-for="(kp, i) in ann.keypoints" :key="i">
                  <circle
                    :cx="kp.x * cw"
                    :cy="kp.y * ch"
                    r="6"
                    :fill="kpColorByIndex(i, ann.class_id)"
                    :opacity="kp.visibility === 'Visible' ? 1 : 0.5"
                    stroke="#fff"
                    stroke-width="1.5"
                  />
                  <circle
                    :cx="kp.x * cw + 7"
                    :cy="kp.y * ch - 7"
                    r="5"
                    fill="#fff"
                    stroke="#1a1a1a"
                    stroke-width="1"
                  />
                  <text
                    :x="kp.x * cw + 7"
                    :y="kp.y * ch - 7"
                    fill="#1a1a1a"
                    font-size="6"
                    text-anchor="middle"
                    dominant-baseline="central"
                  >
                    {{ i + 1 }}
                  </text>
                  <text :x="kp.x * cw + 12" :y="kp.y * ch - 4" fill="#606266" font-size="5">
                    {{ kp.name }}
                  </text>
                  <rect v-if="store.selectedAnnotationId === ann.id" :x="kp.x * cw - 4" :y="kp.y * ch - 4" width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5" :data-handle="'kp-' + i" class="handle" vector-effect="non-scaling-stroke" />
                </g>
              </template>
              <template v-if="ann.type === 'Ocr'">
                <!-- 矩形模式 → 和检测框一样渲染 -->
                <template v-if="ann.source === 'rect'">
                  <template v-for="B in [ocrBBox(ann)]" :key="ann.id + '-box'">
                    <rect
                      :x="B.minX" :y="B.minY"
                      :width="B.maxX - B.minX" :height="B.maxY - B.minY"
                      :stroke="clsColor(ann.class_id)"
                      :stroke-width="store.selectedAnnotationId === ann.id ? annSettings.selStrokeWidth : annSettings.strokeWidth"
                      :fill="store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'rgba(255,255,0,0.08)'"
                      style="pointer-events: all"
                      :data-handle="store.selectedAnnotationId === ann.id ? 'move' : undefined"
                      vector-effect="non-scaling-stroke"
                    />
                    <template v-if="store.selectedAnnotationId === ann.id">
                      <rect v-for="h in ocrBoxHandles(ann)" :key="h.key"
                        :x="h.x - 4" :y="h.y - 4" width="8" height="8"
                        fill="#fff" stroke="#1a1a1a" stroke-width="1.5"
                        class="handle" vector-effect="non-scaling-stroke"
                        @mousedown.left.stop="startOcrRectResize($event, ann, h.edges)" />
                    </template>
                  </template>
                </template>
                <!-- 四边形模式 → 和多边形一样渲染 -->
                <template v-else>
                  <polygon
                    :points="ann.points.map((p: any) => `${p.x * cw},${p.y * ch}`).join(' ')"
                    :stroke="clsColor(ann.class_id)"
                    :stroke-width="store.selectedAnnotationId === ann.id ? annSettings.selStrokeWidth : annSettings.strokeWidth"
                    :fill="store.selectedAnnotationId === ann.id ? clsColor(ann.class_id) + '28' : 'rgba(255,255,0,0.08)'"
                    style="pointer-events: all"
                    :data-handle="store.selectedAnnotationId === ann.id ? 'move' : undefined"
                    vector-effect="non-scaling-stroke"
                  />
                  <template v-if="store.selectedAnnotationId === ann.id">
                    <rect v-for="(p, i) in ann.points" :key="i"
                      :x="p.x * cw - 3" :y="p.y * ch - 3" width="6" height="6"
                      fill="#fff" stroke="#1a1a1a" stroke-width="1.5"
                      :data-handle="'ocr-vertex-' + i" class="handle"
                      vector-effect="non-scaling-stroke" />
                  </template>
                </template>
                <template v-for="B in [ocrBBox(ann)]" :key="ann.id + '-bb'">
                  <rect class="ann-label"
                    :x="B.minX"
                    :y="B.minY - (labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) - 4"
                    :width="(labelTextRects.get(ann.id)?.w ?? labelWidthForClass(ann.class_id)) + 4"
                    :height="(labelTextRects.get(ann.id)?.h ?? LABEL_TAG_H) + 4"
                    :fill="clsColor(ann.class_id)"
                    :stroke="clsColor(ann.class_id)"
                    stroke-width="0.5" vector-effect="non-scaling-stroke" rx="1"
                  />
                  <text class="ann-label"
                    :x="B.minX + 2" :y="B.minY - 2" fill="#ffffff" font-weight="500"
                    text-anchor="start" font-family="Microsoft YaHei,sans-serif"
                    :font-size="annSettings.labelFontSize" dominant-baseline="text-after-edge"
                  >
                    {{ ann.text || getCls(ann.class_id)?.name }}
                  </text>
                </template>
              </template>
              <template v-if="ann.type === 'Classification'">
                <text
                  :x="10"
                  :y="20"
                  fill="#303133"
                  font-size="14"
                  font-weight="600"
                  font-family="Microsoft YaHei,sans-serif"
                >
                  {{
                    ann.class_ids?.length
                      ? ann.class_ids
                          .map((id: number) => getCls(id)?.name)
                          .filter(Boolean)
                          .join(", ")
                      : getCls(ann.class_id)?.name
                  }}
                </text>
              </template>
            </g>
            <!-- Rotated box 3-step preview -->
            <template v-if="currentTool === 'rotated_box' && rbStep === 1 && rbPt1">
              <circle
                :cx="rbPt1!.x"
                :cy="rbPt1!.y"
                r="5"
                :fill="cxColor"
                stroke="#fff"
                stroke-width="1.5"
              />
              <line
                v-if="cursorX && cursorY"
                :x1="rbPt1!.x"
                :y1="rbPt1!.y"
                :x2="cursorX"
                :y2="cursorY"
                :stroke="cxColor"
                stroke-width="1.5"
                stroke-dasharray="4,3"
                opacity="0.7"
              />
            </template>
            <template
              v-if="
                currentTool === 'rotated_box' && (rbStep === 2 || rbStep === 3) && rbPt1 && rbPt2
              "
            >
              <circle
                :cx="rbPt1.x"
                :cy="rbPt1.y"
                r="5"
                :fill="cxColor"
                stroke="#fff"
                stroke-width="1.5"
              />
              <circle
                :cx="rbPt2.x"
                :cy="rbPt2.y"
                r="5"
                :fill="cxColor"
                stroke="#fff"
                stroke-width="1.5"
              />
              <line
                :x1="rbPt1.x"
                :y1="rbPt1.y"
                :x2="rbPt2.x"
                :y2="rbPt2.y"
                :stroke="cxColor"
                stroke-width="2"
              />
              <!-- Step 3: perpendicular guide + live rect preview -->
              <template v-if="rbStep === 3 && cursorX && cursorY">
                <line
                  :x1="rbPerpFootX"
                  :y1="rbPerpFootY"
                  :x2="cursorX"
                  :y2="cursorY"
                  :stroke="cxColor"
                  stroke-width="1.5"
                  stroke-dasharray="4,3"
                  opacity="0.7"
                />
                <rect
                  v-if="rbPreviewRect"
                  :x="rbPreviewRect.x"
                  :y="rbPreviewRect.y"
                  :width="rbPreviewRect.w"
                  :height="rbPreviewRect.h"
                  :transform="`rotate(${rbPreviewRect.deg} ${rbPreviewRect.cx} ${rbPreviewRect.cy})`"
                  :stroke="cxColor"
                  stroke-width="1"
                  stroke-dasharray="4,3"
                  fill="rgba(59,130,246,0.06)"
                />
              </template>
            </template>
            <template v-if="currentTool === 'polygon' && polyDrawingPoints.length > 0">
              <polyline
                :points="polyDrawingPoints.map((p) => `${p.x * cw},${p.y * ch}`).join(' ')"
                :stroke="cxColor"
                stroke-width="1.5"
                fill="none"
              />
              <circle
                v-for="(p, i) in polyDrawingPoints"
                :key="i"
                :cx="p.x * cw"
                :cy="p.y * ch"
                r="3"
                :fill="cxColor"
              />
              <!-- 靠近第一个点时鼠标位置显示大圆提示 -->
              <circle
                v-if="polyNearFirst"
                :cx="cursorX"
                :cy="cursorY"
                r="8"
                fill="none"
                :stroke="cxColor"
                stroke-width="2"
              />
              <line
                v-if="cursorX && cursorY"
                :x1="polyDrawingPoints[polyDrawingPoints.length - 1].x * cw"
                :y1="polyDrawingPoints[polyDrawingPoints.length - 1].y * ch"
                :x2="cursorX"
                :y2="cursorY"
                :stroke="cxColor"
                stroke-width="1.5"
                stroke-dasharray="4,3"
                opacity="0.6"
              />
            </template>
            <!-- Keypoint phase 1: placing corners -->
            <template v-if="currentTool === 'keypoint' && kpPhase === 'corners'">
              <g v-for="(cp, i) in kpCorners" :key="i">
                <circle
                  :cx="cp.x * cw"
                  :cy="cp.y * ch"
                  r="8"
                  :fill="cxColor"
                  :opacity="cp.visibility === 2 ? 1 : 0.5"
                />
                <circle
                  :cx="cp.x * cw + 8"
                  :cy="cp.y * ch - 8"
                  r="5"
                  fill="#fff"
                  stroke="#1a1a1a"
                  stroke-width="1"
                />
                <text
                  :x="cp.x * cw + 8"
                  :y="cp.y * ch - 8"
                  fill="#1a1a1a"
                  font-size="6"
                  text-anchor="middle"
                  dominant-baseline="central"
                >
                  {{ i + 1 }}
                </text>
                <text :x="cp.x * cw + 12" :y="cp.y * ch - 4" fill="#606266" font-size="5">
                  {{ cp.name }}
                </text>
              </g>
              <template v-if="kpCorners.length < kpNames.length && cursorX && cursorY">
                <circle
                  :cx="cursorX"
                  :cy="cursorY"
                  r="8"
                  :fill="cxColor"
                  opacity="0.4"
                  stroke-dasharray="3,3"
                />
                <text :x="cursorX + 12" :y="cursorY" fill="#909399" font-size="5">
                  {{ kpNames[kpCorners.length] }}
                </text>
              </template>
            </template>
            <!-- Keypoint phase 2: drawing box -->
            <template v-if="currentTool === 'keypoint' && kpPhase === 'box'">
              <g v-for="(cp, i) in kpCorners" :key="i">
                <circle :cx="cp.x * cw" :cy="cp.y * ch" r="8" :fill="cxColor" />
                <circle
                  :cx="cp.x * cw + 8"
                  :cy="cp.y * ch - 8"
                  r="5"
                  fill="#fff"
                  stroke="#1a1a1a"
                  stroke-width="1"
                />
                <text
                  :x="cp.x * cw + 8"
                  :y="cp.y * ch - 8"
                  fill="#1a1a1a"
                  font-size="6"
                  text-anchor="middle"
                  dominant-baseline="central"
                >
                  {{ i + 1 }}
                </text>
              </g>
              <rect
                v-if="kpBoxPreview"
                :x="Math.min(kpBoxPreview.x1, kpBoxPreview.x2) * cw"
                :y="Math.min(kpBoxPreview.y1, kpBoxPreview.y2) * ch"
                :width="Math.abs(kpBoxPreview.x2 - kpBoxPreview.x1) * cw"
                :height="Math.abs(kpBoxPreview.y2 - kpBoxPreview.y1) * ch"
                :stroke="cxColor"
                stroke-width="1.5"
                stroke-dasharray="4,3"
                fill="rgba(59,130,246,0.06)"
              />
            </template>
            <!-- OCR 矩形模式预览 -->
            <template v-if="currentTool === 'ocr' && ocrRectMode && ocrDrawingPoints.length === 4">
              <template v-for="B in [{minX:Math.min(...ocrDrawingPoints.map(p=>p.x*cw)),minY:Math.min(...ocrDrawingPoints.map(p=>p.y*ch)),maxX:Math.max(...ocrDrawingPoints.map(p=>p.x*cw)),maxY:Math.max(...ocrDrawingPoints.map(p=>p.y*ch))}]">
                <rect :x="B.minX" :y="B.minY" :width="B.maxX-B.minX" :height="B.maxY-B.minY"
                  :stroke="cxColor" stroke-width="1.5" :fill="cxColor+'18'"
                  vector-effect="non-scaling-stroke" />
              </template>
            </template>
            <!-- OCR 四边形模式预览 -->
            <template v-if="currentTool === 'ocr' && !ocrRectMode && ocrDrawingPoints.length > 0">
              <!-- 未封闭时用 polyline -->
              <polyline v-if="!ocrTextInputVisible"
                :points="ocrDrawingPoints.map((p) => `${p.x * cw},${p.y * ch}`).join(' ')"
                :stroke="cxColor" stroke-width="1.5" fill="none" />
              <!-- 封闭后用 polygon -->
              <polygon v-else
                :points="ocrDrawingPoints.map((p) => `${p.x * cw},${p.y * ch}`).join(' ')"
                :stroke="cxColor" stroke-width="1.5" :fill="cxColor+'18'" />
              <circle v-for="(p, i) in ocrDrawingPoints" :key="i"
                :cx="p.x * cw" :cy="p.y * ch" r="3" :fill="cxColor" />
              <text v-for="(p, i) in ocrDrawingPoints" :key="'l' + i"
                :x="p.x * cw + 8" :y="p.y * ch + 4" fill="#606266" font-size="5">{{ i + 1 }}</text>
              <circle v-if="ocrNearFirst" :cx="cursorX" :cy="cursorY" r="8"
                fill="none" :stroke="cxColor" stroke-width="2" />
              <line v-if="cursorX && cursorY && ocrDrawingPoints.length > 0 && !ocrTextInputVisible"
                :x1="ocrDrawingPoints[ocrDrawingPoints.length - 1].x * cw"
                :y1="ocrDrawingPoints[ocrDrawingPoints.length - 1].y * ch"
                :x2="cursorX" :y2="cursorY"
                :stroke="cxColor" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.6" />
            </template>
          </svg>
          <div v-if="!imgUrl && store.currentImage" class="no-image">加载失败</div>
          <div v-else-if="!store.currentImage" class="no-image">No image loaded</div>
        </div>
      </main>
      <!-- 右侧面板 -->
      <aside class="ann-rightbar">
        <div class="panel">
          <!-- 设置 -->
          <div class="panel-section" style="flex: none; overflow: visible">
            <div
              class="section-title-row"
              style="cursor: pointer"
              @click="showSettings = !showSettings"
            >
              <span class="section-title">设置</span>
              <span class="text-xs text-gray-400">{{ showSettings ? "收起" : "展开" }}</span>
            </div>
            <div
              v-show="showSettings"
              style="display: flex; flex-direction: column; gap: 4px; padding: 2px 0"
            >
              <div class="setting-row">
                <span class="setting-label">框线</span>
                <ElSlider
                  v-model="annSettings.strokeWidth"
                  :min="0.5"
                  :max="5"
                  :step="0.5"
                  size="small"
                  style="flex: 1"
                />
              </div>
              <div class="setting-row">
                <span class="setting-label">选中框线</span>
                <ElSlider
                  v-model="annSettings.selStrokeWidth"
                  :min="0.5"
                  :max="5"
                  :step="0.5"
                  size="small"
                  style="flex: 1"
                />
              </div>
              <div class="setting-row">
                <span class="setting-label">十字线粗细</span>
                <ElSlider
                  v-model="annSettings.crosshairWidth"
                  :min="0.5"
                  :max="3"
                  :step="0.5"
                  size="small"
                  style="flex: 1"
                />
              </div>
              <div class="setting-row">
                <span class="setting-label">十字线中心圈</span>
                <ElSwitch v-model="annSettings.crosshairCircle" size="small" />
              </div>
              <div class="setting-row">
                <span class="setting-label">标签字号</span>
                <ElSlider
                  v-model="annSettings.labelFontSize"
                  :min="4"
                  :max="48"
                  :step="1"
                  size="small"
                  style="flex: 1"
                />
              </div>
            </div>
          </div>
          <div class="divider" />
          <div class="panel-section">
            <div class="section-title-row">
              <span class="section-title">图片列表</span>
              <span class="count-chip">{{ store.images.length }}</span>
            </div>
            <div class="scroll-area">
              <div
                v-for="(img, idx) in store.images"
                :key="img.id"
                class="image-item"
                :class="{ active: idx === store.currentImageIndex }"
                @click="goToImage(idx)"
              >
                <span
                  class="dot"
                  :class="img.status === 'annotated' ? 'dot-done' : 'dot-pending'"
                />
                <div class="img-info">
                  <span class="img-name">{{ img.filename }}</span>
                  <span class="img-meta">
                    {{ img.updated_by?.name || "--" }} {{ fmtTime(img.updated_time) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div class="divider" />
          <div class="panel-section">
            <div class="section-title-row">
              <span class="section-title">类别</span>
              <el-button text size="small" @click="showClassModal = true; kpCount = 0; clsForm.kpNames = []; clsForm.kpColors = []">+ 添加</el-button>
            </div>
            <div class="scroll-area">
              <div
                v-for="cls in taskClasses"
                :key="cls.id"
                class="class-item"
                :class="{ active: selectedClassId === cls.id }"
                @click="selectedClassId = cls.id"
              >
                <span class="dot-color" :style="{ background: cls.color }" />
                <span class="flex-1 text-sm">{{ cls.name }}</span>
                <span class="text-xs text-gray-400">{{ clsCount(cls.id) }}</span>
                <el-popconfirm
                  title="确定删除该类别？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="removeClass(cls.id)"
                  width="180"
                >
                  <template #reference>
                    <el-button text size="small" @click.stop>×</el-button>
                  </template>
                </el-popconfirm>
              </div>
              <div v-if="taskClasses.length === 0" class="empty-hint">请添加标签类别</div>
            </div>
          </div>
          <div v-if="taskType === 'classification'" class="divider" />
          <div v-if="taskType === 'classification'" class="panel-section">
            <div class="section-title-row"><span class="section-title">分类</span></div>
            <div class="scroll-area">
              <template v-if="classifMode === 'single'">
                <div
                  v-for="cls in taskClasses"
                  :key="cls.id"
                  class="class-item"
                  :class="{
                    active: store.annotations.some(
                      (a) => a.class_id === cls.id && a.type === 'Classification'
                    ),
                  }"
                  @click="toggleClassification(cls.id)"
                >
                  <span class="dot-color" :style="{ background: cls.color }" />
                  <span class="flex-1 text-sm">{{ cls.name }}</span>
                  <el-icon
                    v-if="
                      store.annotations.some(
                        (a) => a.class_id === cls.id && a.type === 'Classification'
                      )
                    "
                    size="14"
                    color="#67c23a"
                  >
                    <Check />
                  </el-icon>
                </div>
              </template>
              <template v-else>
                <div
                  v-for="cls in taskClasses"
                  :key="cls.id"
                  class="class-item"
                  :class="{
                    active: store.annotations.some(
                      (a) => a.type === 'Classification' && (a.class_ids || []).includes(cls.id)
                    ),
                  }"
                  @click="toggleClassification(cls.id)"
                >
                  <span class="dot-color" :style="{ background: cls.color }" />
                  <span class="flex-1 text-sm">{{ cls.name }}</span>
                  <ElCheckbox
                    :checked="
                      store.annotations.some(
                        (a) => a.type === 'Classification' && (a.class_ids || []).includes(cls.id)
                      )
                    "
                    size="small"
                  />
                </div>
              </template>
              <div v-if="taskClasses.length === 0" class="empty-hint">请添加标签类别</div>
            </div>
          </div>
          <div class="divider" />
          <div class="panel-section">
            <div class="section-title-row">
              <span class="section-title">标注列表</span>
              <ElBadge :value="store.annotations.length" :max="999" />
            </div>
            <div class="scroll-area">
              <div
                v-for="ann in store.annotations"
                :key="ann.id"
                class="ann-item"
                :class="{ active: store.selectedAnnotationId === ann.id }"
                @click="store.selectedAnnotationId = ann.id"
              >
                <span class="dot-color" :style="{ background: clsColor(ann.class_id) }" />
                <span class="flex-1 text-sm">{{ getCls(ann.class_id)?.name || "?" }}</span>
                <span class="text-xs text-gray-400">
                  {{
                    ann.type === "AxisAlignedBox"
                      ? "矩形"
                      : ann.type === "RotatedBox"
                        ? "旋转框"
                        : ann.type === "Polygon"
                          ? "多边形"
                          : ann.type === "Keypoint"
                            ? "关键点"
                            : ann.type === "Ocr"
                              ? "OCR"
                              : ann.type === "Classification"
                                ? "分类"
                                : ann.type
                  }}
                </span>
                <el-popconfirm
                  title="确定删除该标注？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="removeAnn(ann.id)"
                  width="180"
                >
                  <template #reference>
                    <el-button text size="small" type="danger" @click.stop>
                      ×
                    </el-button>
                  </template>
                </el-popconfirm>
              </div>
              <div v-if="store.annotations.length === 0" class="empty-hint">暂无标注</div>
            </div>
          </div>
        </div>
      </aside>
    </div>
    <!-- 底栏（固定，无需滚动） -->
    <footer class="ann-footer">
      <span class="hint">{{ toolHint }}</span>
      <span v-if="unsaved" class="unsaved-dot" title="未保存" />
      <span class="text-xs text-gray-400 font-mono">X:{{ cursorX }} Y:{{ cursorY }}</span>
      <span class="text-xs text-gray-400 font-mono">
        Z:{{ Math.round(store.zoom * 100) }}% | cw:{{ cw }}
      </span>
      <div class="sep" />
      <el-button size="small" :disabled="!store.currentImage" circle @click="prevImg">
        <el-icon><ArrowLeft /></el-icon>
      </el-button>
      <span class="nav-text">{{ store.currentImageIndex + 1 }}/{{ store.images.length }}</span>
      <el-button size="small" :disabled="!store.hasNext" circle @click="nextImg">
        <el-icon><ArrowRight /></el-icon>
      </el-button>
      <div class="sep" />
      <el-button
        size="small"
        type="primary"
        :loading="store.saving"
        :disabled="!store.currentImage"
        @click="saveAnn"
      >
        保存
      </el-button>
    </footer>
    <!-- 添加类别弹窗 -->
    <el-dialog v-model="showClassModal" title="添加类别" width="380px">
      <el-form :model="clsForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="clsForm.name" placeholder="类别名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <div style="display:flex;flex-wrap:wrap;gap:4px;align-items:center">
            <div
              v-for="c in PRESET_COLORS"
              :key="c"
              :style="{
                width:'20px',height:'20px',borderRadius:'4px',cursor:'pointer',
                background:c,
                border: clsForm.color === c ? '2px solid #303133' : '2px solid transparent',
                transform: clsForm.color === c ? 'scale(1.2)' : 'scale(1)',
                transition:'all .15s'
              }"
              @click="clsForm.color = c"
            />
            <el-color-picker v-model="clsForm.color" size="small" style="margin-left:4px" />
          </div>
        </el-form-item>
        <template v-if="taskType === 'keypoint'">
            <div style="margin-top:8px;font-size:12px;color:#909399;padding:0 0 4px">关键点列表（点击 ⊖ 删除）</div>
            <div v-for="(_, i) in kpCount" :key="i" style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
              <span style="width:24px;text-align:center;font-size:12px;color:#606266;flex-shrink:0">{{ i + 1 }}</span>
              <el-input v-model="clsForm.kpNames[i]" placeholder="名称" size="small" style="flex:1" />
               <div style="display:flex;gap:2px;flex-wrap:wrap;align-items:center">
                  <div
                    v-for="c in PRESET_COLORS"
                    :key="c"
                    :style="{
                      width:'14px',height:'14px',borderRadius:'3px',cursor:'pointer',
                      background:c,
                      border: clsForm.kpColors[i] === c ? '1.5px solid #303133' : '1.5px solid transparent'
                    }"
                    @click="clsForm.kpColors[i] = c"
                  />
                  <el-color-picker v-model="clsForm.kpColors[i]" size="small" style="width:24px" />
                </div>
              <el-button text size="small" type="danger" @click="removeKp(i)" style="font-size:16px;padding:0;width:20px">⊖</el-button>
            </div>
            <el-button size="small" text type="primary" @click="addKp" style="margin-top:4px">+ 添加关键点</el-button>
          </template>
      </el-form>
      <template #footer>
        <el-button @click="showClassModal = false">取消</el-button>
        <el-button type="primary" @click="addClass">添加</el-button>
      </template>
    </el-dialog>
    <el-dialog
      v-model="ocrTextInputVisible"
      title="输入 OCR 文本"
      width="360px"
      :close-on-click-modal="false"
    >
      <el-input
        v-model="ocrTextInput"
        placeholder="请输入识别到的文本内容..."
        @keydown.enter="confirmOcrText"
      />
      <template #footer>
        <el-button @click="ocrTextInputVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrText">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElBadge, ElSlider, ElSwitch, ElCheckbox } from "element-plus";
import { ArrowLeft, ArrowRight, Delete, Pointer, Check } from "@element-plus/icons-vue";
import { h } from "vue";
const DiamondIcon = {
  render() {
    return h(
      "svg",
      {
        viewBox: "0 0 24 24",
        width: 18,
        height: 18,
        fill: "none",
        stroke: "currentColor",
        "stroke-width": 2,
      },
      [h("polygon", { points: "12,3 21,12 12,21 3,12" })]
    );
  },
};
const PentagonIcon = {
  render() {
    return h(
      "svg",
      {
        viewBox: "0 0 24 24",
        width: 18,
        height: 18,
        fill: "none",
        stroke: "currentColor",
        "stroke-width": 2,
      },
      [h("polygon", { points: "12,2 22,9 18,21 6,21 2,9" })]
    );
  },
};
const CircleDotIcon = {
  render() {
    return h(
      "svg",
      {
        viewBox: "0 0 24 24",
        width: 18,
        height: 18,
        fill: "none",
        stroke: "currentColor",
        "stroke-width": 2,
      },
      [
        h("circle", { cx: "12", cy: "12", r: "8" }),
        h("circle", { cx: "12", cy: "12", r: "2", fill: "currentColor" }),
      ]
    );
  },
};
import { AnnotationAPI } from "@/api/module_annotation";
import { useAnnotationStore, type ToolName } from "./store";
import { useUserStoreHook } from "@/store";

const route = useRoute();
const router = useRouter();
const store = useAnnotationStore();

// Refs
const canvasRef = ref<HTMLElement | null>(null);
const canvasWrapRef = ref<HTMLElement | null>(null);
const imgRef = ref<HTMLImageElement | null>(null);
const cxXRef = ref<HTMLElement | null>(null);
const cxYRef = ref<HTMLElement | null>(null);
const cxCircleRef = ref<HTMLElement | null>(null);
const boxPreviewRef = ref<HTMLElement | null>(null);

// State
const imgUrl = ref("");
const cw = ref(1);
const ch = ref(1);
const cursorX = ref(0);
const cursorY = ref(0);
const showCrosshair = ref(false);
const selectedClassId = ref(0);
const currentTool = ref<ToolName>("select");
const taskType = ref("detection");
const task = ref<any>(null);
const taskClasses = ref<any[]>([]);
const showClassModal = ref(false);
const showSettings = ref(false);
const clsForm = ref({ name: "", color: "#409eff", kpNames: [] as string[], kpColors: [] as string[] })

// ---- 标注工作台设置（持久化到 localStorage）----
const settingsKey = "annotation-workbench-settings";
function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(settingsKey) || "{}");
  } catch {
    return {};
  }
}
function saveSettings() {
  localStorage.setItem(settingsKey, JSON.stringify(annSettings.value));
}
const annSettings = ref({
  strokeWidth: 1.5,
  selStrokeWidth: 2,
  crosshairWidth: 1,
  crosshairCircle: false,
  labelFontSize: 6,
  ...loadSettings(),
});
watch(annSettings, saveSettings, { deep: true });
watch(
  () => annSettings.value.labelFontSize,
  () => nextTick(() => measureLabelRects())
);

// ---- Constants (matching EasyLabelTauri) ----
const LABEL_TAG_H = 8;

// ---- Drag state (single object, matching EasyLabelTauri pattern) ----
interface DragState {
  active: boolean;
  type:
    | "move"
    | "pan"
    | "rotate"
    | "poly-vertex"
    | "kp-vertex"
    | "kp-move"
    | "kp-resize-tl"
    | "kp-resize-tr"
    | "kp-resize-bl"
    | "kp-resize-br"
    | "kp-resize-tc"
    | "kp-resize-bc"
    | "kp-resize-ml"
    | "kp-resize-mr"
    | "resize-tl"
    | "resize-tr"
    | "resize-bl"
    | "resize-br"
    | "resize-l"
    | "resize-r"
    | "resize-t"
    | "resize-b"
    | "resize-ocr"
    | "tl"
    | "tr"
    | "bl"
    | "br"
    | "";
  ann: any | null;
  orig: any | null;
  startX: number;
  startY: number;
  handle: string;
  polyVertexIndex?: number;
}
const drag = ref<DragState>({
  active: false,
  type: "",
  ann: null,
  orig: null,
  startX: 0,
  startY: 0,
  handle: "",
});

// ---- 测量文字实际宽高 ----
const labelTextRects = ref(new Map<string, { w: number; h: number; y: number }>());
async function measureLabelRects() {
  await nextTick();
  await new Promise((r) => setTimeout(r, 100));
  const annSvg = document.querySelector(".ann-svg");
  if (!annSvg) return;
  const texts = annSvg.querySelectorAll<SVGTextElement>(".ann-label text");
  const map = new Map<string, { w: number; h: number; y: number }>();
  texts.forEach((t) => {
    const annEl = t.closest<SVGGElement>("[data-ann-id]");
    if (!annEl) return;
    const id = annEl.getAttribute("data-ann-id");
    if (!id) return;
    const bbox = t.getBBox();
    if (bbox.width > 0 && bbox.height > 0) {
      map.set(id, { w: bbox.width, h: bbox.height, y: bbox.y });
    }
  });
  labelTextRects.value = map;
  // 调试输出
  if (map.size > 0) {
    for (const [id, r] of map) {
      const ann = store.annotations.find((a) => a.id === id);
      const clsName = ann ? getCls(ann.class_id)?.name || "?" : "?";
      const calcW = labelWidthForClass(ann?.class_id || 0);
      const calcH = LABEL_TAG_H;
      console.log(
        `[label] "${clsName}" 测量: w=${r.w.toFixed(1)} h=${r.h.toFixed(1)} y=${r.y.toFixed(1)} | 计算: w=${calcW} h=${calcH}`
      );
    }
  }
}

// ---- Box drawing (div overlay in container-relative coords) ----
const drawing = ref(false);
let bx = 0; // box start X (container-relative)
let by = 0; // box start Y (container-relative)
let drawStartImg = { x: 0, y: 0 }; // box start in image natural pixels

// ---- Rotated box drawing (3-step) ----
const rbStep = ref(0); // 0=idle, 1=placed p1, 2=placed p2+drag, 3=place p3
const rbPt1 = ref<{ x: number; y: number } | null>(null);
const rbPt2 = ref<{ x: number; y: number } | null>(null);
const rbDragging = ref(false);

const polyDrawingPoints = ref<{ x: number; y: number }[]>([]);

// ---- Keypoint (2-phase) ----
const kpPhase = ref<"corners" | "box" | null>(null);
const kpCorners = ref<{ x: number; y: number; name: string; visibility: number }[]>([]);
const kpNames = ref<string[]>(["top_left", "top_right", "bottom_right", "bottom_left"]);
const kpBoxPreview = ref<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
const pendingKpVisibility = ref(2);
let kpBoxDragStart: { x: number; y: number } | null = null;
const kpCount = ref(0)
function addKp() { clsForm.value.kpNames.push(""); clsForm.value.kpColors.push(clsForm.value.color); kpCount.value = clsForm.value.kpNames.length }
function removeKp(i: number) { clsForm.value.kpNames.splice(i, 1); clsForm.value.kpColors.splice(i, 1); kpCount.value = clsForm.value.kpNames.length }

// ---- OCR ----
const ocrDrawingPoints = ref<{ x: number; y: number }[]>([]);
const ocrTextInput = ref("");
const ocrTextInputVisible = ref(false);
const ocrRectMode = ref(false);
const ocrSource = ref<"rect" | "quad">("quad");
let ocrBoxStart = { x: 0, y: 0 };

// ---- Classification ----
const classifMode = ref<"single" | "multi">("single");

// ===== Tools =====
const baseTools: { name: ToolName; label: string; tip: string; icon: any }[] = [
  { name: "select", label: "选择", tip: "点击选择标注，拖拽移动", icon: "Pointer" },
  { name: "pan", label: "平移", tip: "拖拽平移画布", icon: "Rank" },
  { name: "zoom", label: "缩放", tip: "滚轮缩放", icon: "ZoomIn" },
];
const taskToolMap: Record<string, { name: ToolName; label: string; tip: string; icon: any }[]> = {
  detection: [{ name: "box", label: "矩形", tip: "拖拽创建矩形框", icon: "FullScreen" }],
  rotated_detection: [{ name: "rotated_box", label: "旋转框", tip: "旋转框", icon: DiamondIcon }],
  segmentation: [{ name: "polygon", label: "多边形", tip: "点击创建多边形", icon: PentagonIcon }],
  keypoint: [{ name: "keypoint", label: "关键点", tip: "放置关键点", icon: CircleDotIcon }],
  ocr: [{ name: "ocr", label: "OCR", tip: "文本标注", icon: "Document" }],
  classification: [{ name: "classification", label: "分类", tip: "图像分类", icon: "Collection" }],
};
const displayTools = computed(() => [...baseTools, ...(taskToolMap[taskType.value] || [])]);
const taskTypeLabel = computed(
  () =>
    ({
      detection: "检测",
      rotated_detection: "旋转框",
      segmentation: "分割",
      keypoint: "关键点",
      ocr: "OCR",
      classification: "分类",
    })[taskType.value] || taskType.value
);
const taskTypeTag = computed(
  () =>
    (
      ({
        detection: undefined,
        rotated_detection: "warning",
        segmentation: "danger",
        keypoint: "warning",
        ocr: "info",
        classification: "info",
      }) as Record<string, any>
    )[taskType.value]
);
const toolHint = computed(
  () =>
    ({
      select: "点击选择标注，拖拽移动",
      pan: "拖拽平移",
      zoom: "滚轮缩放",
      box: "拖拽创建矩形框",
      rotated_box: "三步旋转框",
      polygon: "点击创建多边形",
      keypoint: "放置关键点",
      ocr: "文本标注",
      classification: "选择类别",
    })[currentTool.value] || ""
);
const diamondCursor =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20'%3E%3Cpolygon points='10,2 18,10 10,18 2,10' fill='none' stroke='%23333' stroke-width='1.5'/%3E%3C/svg%3E\") 10 10, crosshair";
const toolCursor = computed(
  () =>
    ({
      select: "default",
      pan: "grab",
      zoom: "zoom-in",
      box: "crosshair",
      rotated_box: diamondCursor,
      polygon: "crosshair",
      keypoint: "crosshair",
      ocr: "crosshair",
      classification: "default",
    })[currentTool.value] || "default"
);
const polyNearFirst = computed(() => {
  if (polyDrawingPoints.value.length < 3 || !cursorX.value || !cursorY.value) return false;
  const fp = polyDrawingPoints.value[0];
  return Math.hypot(cursorX.value - fp.x * cw.value, cursorY.value - fp.y * ch.value) < 20;
});
const ocrNearFirst = computed(() => {
  if (ocrDrawingPoints.value.length < 3 || !cursorX.value || !cursorY.value) return false;
  const fp = ocrDrawingPoints.value[0];
  return Math.hypot(cursorX.value - fp.x * cw.value, cursorY.value - fp.y * ch.value) < 20;
});

const cxColor = computed(() => clsColor(selectedClassId.value) || "#3b82f6");
const cxStyle = computed(() => ({ background: cxColor.value + "80" }));

// ---- Rotated box step 3 preview computed ----
const rbPerpFootX = computed(() => {
  if (!rbPt1.value || !rbPt2.value) return 0;
  const vx = rbPt2.value.x - rbPt1.value.x;
  const vy = rbPt2.value.y - rbPt1.value.y;
  const w = Math.hypot(vx, vy);
  if (w < 1e-6) return 0;
  const t = ((cursorX.value - rbPt1.value.x) * vx + (cursorY.value - rbPt1.value.y) * vy) / (w * w);
  return rbPt1.value.x + t * vx;
});
const rbPerpFootY = computed(() => {
  if (!rbPt1.value || !rbPt2.value) return 0;
  const vx = rbPt2.value.x - rbPt1.value.x;
  const vy = rbPt2.value.y - rbPt1.value.y;
  const w = Math.hypot(vx, vy);
  if (w < 1e-6) return 0;
  const t = ((cursorX.value - rbPt1.value.x) * vx + (cursorY.value - rbPt1.value.y) * vy) / (w * w);
  return rbPt1.value.y + t * vy;
});
const rbPreviewRect = computed(() => {
  if (!rbPt1.value || !rbPt2.value) return null;
  const p3 = { x: cursorX.value, y: cursorY.value };
  const geom = rotatedBoxFromEdgeAndPoint(rbPt1.value, rbPt2.value, p3);
  if (!geom) return null;
  return {
    cx: geom.cx,
    cy: geom.cy,
    deg: (geom.angle * 180) / Math.PI,
    x: geom.cx - geom.width / 2,
    y: geom.cy - geom.height / 2,
    w: geom.width,
    h: geom.height,
  };
});

const annotatedCount = ref(0);
const totalCount = ref(0);
const progressPct = computed(() =>
  totalCount.value === 0 ? 0 : Math.round((annotatedCount.value / totalCount.value) * 100)
);

// ===== 更新进度 =====
function updateProgress() {
  annotatedCount.value = store.images.filter((i) => i.status === "annotated").length;
  totalCount.value = store.images.length;
}

// ===== 显示 =====
const dw = computed(() => cw.value * store.zoom);
const dh = computed(() => ch.value * store.zoom);

const imgStyle = computed(() => ({
  width: dw.value + "px",
  height: dh.value + "px",
  transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)`,
}));
const svgStyle = computed(() => ({
  width: dw.value + "px",
  height: dh.value + "px",
  transform: `translate(-50%,-50%) translate(${store.panX}px,${store.panY}px)`,
}));

// ===== 坐标：鼠标 → 图像自然像素 =====
function mouseToImage(e: MouseEvent): { x: number; y: number } | null {
  const c = canvasRef.value;
  if (!c || !cw.value || !ch.value) return null;
  const r = c.getBoundingClientRect();
  // 图像左上角在容器中的位置
  const imgL = r.width / 2 - dw.value / 2 + store.panX;
  const imgT = r.height / 2 - dh.value / 2 + store.panY;
  const relX = e.clientX - r.left - imgL;
  const relY = e.clientY - r.top - imgT;
  return {
    x: (Math.max(0, Math.min(dw.value, relX)) / dw.value) * cw.value,
    y: (Math.max(0, Math.min(dh.value, relY)) / dh.value) * ch.value,
  };
}

// ===== 图像加载 =====
function onImgLoad() {
  const el = imgRef.value;
  const c = canvasRef.value;
  if (!el || !c) return;
  cw.value = el.naturalWidth;
  ch.value = el.naturalHeight;
  const tryFit = () => {
    const r = c.getBoundingClientRect();
    if (r.width && r.height) {
      const z = Math.min(r.width / cw.value, r.height / ch.value);
      store.setZoom(Math.min(z, 3));
    }
    store.setPan(0, 0);
  };
  nextTick(tryFit);
}

// ===== Crosshair =====
function updCrosshair(e: MouseEvent) {
  const c = canvasRef.value;
  if (!c) return;
  const r = c.getBoundingClientRect();
  const x = e.clientX - r.left;
  const y = e.clientY - r.top;
  if (cxXRef.value) cxXRef.value.style.top = y + "px";
  if (cxYRef.value) cxYRef.value.style.left = x + "px";
  if (cxCircleRef.value) {
    cxCircleRef.value.style.left = x - 4 + "px";
    cxCircleRef.value.style.top = y - 4 + "px";
  }
}

// ===== 类别 =====
function getCls(id: number) {
  return taskClasses.value.find((c) => c.id === id);
}
function clsColor(id: number) {
  return getCls(id)?.color || "#3b82f6";
}
function clsCount(id: number) {
  return store.annotations.filter((a) => a.class_id === id).length;
}
function textPixelWidth(text: string): number {
  let w = 0;
  for (const ch of text) {
    w += /[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/.test(ch) ? 6 : 3;
  }
  return Math.round(w);
}
function labelWidthForClass(classId: number): number {
  const name = getCls(classId)?.name || "";
  return Math.max(14, textPixelWidth(name) + 6);
}
function addClass() {
  if (!clsForm.value.name.trim()) return;
  const id = taskClasses.value.length > 0 ? Math.max(...taskClasses.value.map((c) => c.id)) + 1 : 0;
  const cls: any = { id, name: clsForm.value.name, color: clsForm.value.color }
  if (taskType.value === "keypoint" && clsForm.value.kpNames.some(n => n.trim())) {
    cls.keypoint_names = clsForm.value.kpNames.filter(n => n.trim())
    cls.keypoint_colors = clsForm.value.kpColors.slice(0, cls.keypoint_names.length)
  }
  taskClasses.value.push(cls)
  clsForm.value = { name: "", color: "#409eff", kpNames: [], kpColors: [] };
  showClassModal.value = false;
  saveClassesToTask();
}
function removeClass(id: number) {
  taskClasses.value = taskClasses.value.filter((c) => c.id !== id);
  store.annotations = store.annotations.filter((a) => a.class_id !== id);
  if (selectedClassId.value === id) selectedClassId.value = taskClasses.value[0]?.id ?? 0;
  saveClassesToTask();
}
async function saveClassesToTask() {
  if (!task.value?.id) return;
  try {
    await AnnotationAPI.updateTask(task.value.id, { classes: taskClasses.value });
  } catch {}
}

// ===== Rotated box geometry =====
function rotatedBoxFromEdgeAndPoint(
  p1: { x: number; y: number },
  p2: { x: number; y: number },
  p3: { x: number; y: number }
): { cx: number; cy: number; width: number; height: number; angle: number } | null {
  const vx = p2.x - p1.x;
  const vy = p2.y - p1.y;
  const width = Math.hypot(vx, vy);
  if (width < 1e-6) return null;
  const mx = (p1.x + p2.x) / 2;
  const my = (p1.y + p2.y) / 2;
  const tx = vx / width;
  const ty = vy / width;
  const t = (p3.x - p1.x) * tx + (p3.y - p1.y) * ty;
  const footX = p1.x + t * tx;
  const footY = p1.y + t * ty;
  const offx = p3.x - footX;
  const offy = p3.y - footY;
  const height = Math.hypot(offx, offy);
  if (height < 1e-6) return null;
  const nx = offx / height;
  const ny = offy / height;
  return {
    cx: mx + (height / 2) * nx,
    cy: my + (height / 2) * ny,
    width,
    height,
    angle: Math.atan2(vy, vx),
  };
}

function rbHandlePos(ann: any, key: string, cw_val: number, ch_val: number) {
  const hw = (ann.width * cw_val) / 2;
  const hh = (ann.height * ch_val) / 2;
  const cos = Math.cos(ann.angle);
  const sin = Math.sin(ann.angle);
  const map: Record<string, [number, number]> = {
    tl: [-hw, -hh],
    tr: [hw, -hh],
    bl: [-hw, hh],
    br: [hw, hh],
    tc: [0, -hh],
    bc: [0, hh],
    ml: [-hw, 0],
    mr: [hw, 0],
  };
  const [lx, ly] = map[key] || [0, 0];
  return {
    x: ann.cx * cw_val + lx * cos - ly * sin,
    y: ann.cy * ch_val + lx * sin + ly * cos,
  };
}

function rbRotateHandlePos(ann: any, cw_val: number, ch_val: number) {
  const hh = (ann.height * ch_val) / 2;
  const offset = 25;
  const lx = 0;
  const ly = -hh - offset;
  const cos = Math.cos(ann.angle);
  const sin = Math.sin(ann.angle);
  return {
    x: ann.cx * cw_val + lx * cos - ly * sin,
    y: ann.cy * ch_val + lx * sin + ly * cos,
  };
}

function kpRbHandlePos(bb: any, h: string, cw: number, ch: number): { x: number; y: number } {
  const cos = Math.cos(bb.angle); const sin = Math.sin(bb.angle)
  const hw = (bb.width * cw) / 2; const hh = (bb.height * ch) / 2
  let lx = 0, ly = 0
  if (h === "tl") { lx = -hw; ly = -hh }
  else if (h === "tc") { lx = 0; ly = -hh }
  else if (h === "tr") { lx = hw; ly = -hh }
  else if (h === "mr") { lx = hw; ly = 0 }
  else if (h === "br") { lx = hw; ly = hh }
  else if (h === "bc") { lx = 0; ly = hh }
  else if (h === "bl") { lx = -hw; ly = hh }
  else if (h === "ml") { lx = -hw; ly = 0 }
  return { x: bb.cx * cw + lx * cos - ly * sin, y: bb.cy * ch + lx * sin + ly * cos }
}

const KP_COLORS = ["#FF6B6B","#FF9F43","#FECA57","#9CCC65","#26DE81","#20BF6B","#0BE881","#0FB9B1","#12CBC4","#0ABDE3","#2E86DE","#3863D4","#8854D0","#A55EEA","#D980FA","#F78FB3","#EE5A70"]
const PRESET_COLORS = ["#FF6B6B","#FF9F43","#FECA57","#9CCC65","#26DE81","#20BF6B","#0BE881","#0FB9B1","#12CBC4","#0ABDE3","#2E86DE","#3863D4","#8854D0","#A55EEA","#D980FA","#F78FB3","#EE5A70"]
function kpColorByIndex(index: number, classId: number): string {
  const cls = taskClasses.value.find(c => c.id === classId)
  if (cls?.keypoint_colors && cls.keypoint_colors.length > index) return cls.keypoint_colors[index]
  return KP_COLORS[index % KP_COLORS.length]
}

function polygonPath(ann: any): string {
  if (!ann.points || ann.points.length === 0) return "";
  const pts = ann.points.map((p: any) => `${p.x * cw.value},${p.y * ch.value}`).join(" L ");
  return `M ${pts} Z`;
}
function polyBBox(ann: any): { x: number; y: number; w: number; h: number } {
  if (!ann.points || ann.points.length === 0) return { x: 0, y: 0, w: 0, h: 0 };
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const p of ann.points) {
    const px = p.x * cw.value;
    const py = p.y * ch.value;
    if (px < minX) minX = px;
    if (py < minY) minY = py;
    if (px > maxX) maxX = px;
    if (py > maxY) maxY = py;
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function ocrBBox(ann: any) {
  const xs = ann.points.map((p: any) => p.x * cw.value);
  const ys = ann.points.map((p: any) => p.y * ch.value);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

function confirmOcrText() {
  if (ocrTextInput.value.trim() && ocrDrawingPoints.value.length >= 3) {
    let pts = ocrDrawingPoints.value.map((p) => ({ x: p.x, y: p.y }));
    // 去掉闭合时重复的首点
    if (pts.length > 3) {
      const last = pts[pts.length - 1];
      const first = pts[0];
      if (Math.abs(last.x - first.x) < 0.001 && Math.abs(last.y - first.y) < 0.001) {
        pts = pts.slice(0, -1);
      }
    }
    store.annotations.push({
      id: crypto.randomUUID(),
      type: "Ocr",
      class_id: selectedClassId.value || 0,
      points: pts,
      text: ocrTextInput.value.trim(),
      source: ocrSource.value,
    });
    ocrDrawingPoints.value = [];
    ocrTextInput.value = "";
    ocrTextInputVisible.value = false;
    nextTick(() => measureLabelRects());
  }
}

function toggleClassification(clsId: number) {
  if (classifMode.value === "single") {
    store.annotations = store.annotations.filter((a) => a.type !== "Classification");
    store.annotations.push({
      id: crypto.randomUUID(),
      type: "Classification",
      class_id: clsId,
    });
  } else {
    const existing = store.annotations.find((a) => a.type === "Classification");
    if (existing) {
      const ids = (existing.class_ids || []) as number[];
      if (ids.includes(clsId)) {
        existing.class_ids = ids.filter((id: number) => id !== clsId);
        if (existing.class_ids.length === 0) {
          store.annotations = store.annotations.filter((a) => a.id !== existing.id);
        }
      } else {
        existing.class_ids = [...ids, clsId];
      }
    } else {
      store.annotations.push({
        id: crypto.randomUUID(),
        type: "Classification",
        class_id: clsId,
        class_ids: [clsId],
      });
    }
  }
  markUnsaved();
  pushHistory();
}

// ===== Box 预览 div =====
function startBoxPreview(cx: number, cy: number) {
  const el = boxPreviewRef.value;
  if (!el) return;
  el.style.display = "block";
  el.style.left = cx + "px";
  el.style.top = cy + "px";
  el.style.width = "0px";
  el.style.height = "0px";
}
function updateBoxPreview(cx: number, cy: number) {
  const el = boxPreviewRef.value;
  if (!el) return;
  el.style.left = Math.min(bx, cx) + "px";
  el.style.top = Math.min(by, cy) + "px";
  el.style.width = Math.abs(cx - bx) + "px";
  el.style.height = Math.abs(cy - by) + "px";
}
function removeBoxPreview() {
  const el = boxPreviewRef.value;
  if (!el) return;
  el.style.display = "none";
  el.style.left = "0px";
  el.style.top = "0px";
  el.style.width = "0px";
  el.style.height = "0px";
}

// ===== 画布事件 =====
function onMouseEnter(e: MouseEvent) {
  if (
    currentTool.value === "box" ||
    currentTool.value === "rotated_box" ||
    currentTool.value === "keypoint" ||
    currentTool.value === "ocr"
  ) {
    showCrosshair.value = true;
    updCrosshair(e);
  }
}
function onMouseLeave() {
  showCrosshair.value = false;
  if (drag.value.active && drag.value.ann) {
    // restore original on leave
    if (drag.value.orig) Object.assign(drag.value.ann, drag.value.orig);
  }
  drag.value = { active: false, type: "", ann: null, orig: null, startX: 0, startY: 0, handle: "" };
  if (drawing.value) {
    drawing.value = false;
    removeBoxPreview();
  }
}

function onMouseDown(e: MouseEvent) {
  if (!store.currentImage) return;

  // ---- Select: deselect on empty-space click ----
  if (currentTool.value === "select") {
    store.selectedAnnotationId = null;
    return;
  }

  // ---- Pan ----
  if (currentTool.value === "pan") {
    drag.value = {
      active: true,
      type: "pan",
      ann: null,
      orig: null,
      startX: e.clientX,
      startY: e.clientY,
      handle: "",
    };
    return;
  }

  // ---- Box draw ----
  if (currentTool.value === "box") {
    if (taskClasses.value.length === 0) {
      ElMessage.warning("请先添加类别");
      return;
    }
    if (!selectedClassId.value && taskClasses.value.length > 0)
      selectedClassId.value = taskClasses.value[0].id;
    const pt = mouseToImage(e);
    if (!pt) return;
    const r = canvasRef.value?.getBoundingClientRect();
    if (!r) return;
    bx = e.clientX - r.left;
    by = e.clientY - r.top;
    drawStartImg = { x: pt.x, y: pt.y };
    startBoxPreview(bx, by);
    drawing.value = true;
    showCrosshair.value = true;
    updCrosshair(e);
    return;
  }

  // ---- Rotated box draw (3-step) ----
  if (currentTool.value === "rotated_box") {
    if (taskClasses.value.length === 0) {
      ElMessage.warning("请先添加类别");
      return;
    }
    if (!selectedClassId.value && taskClasses.value.length > 0)
      selectedClassId.value = taskClasses.value[0].id;
    const pt = mouseToImage(e);
    if (!pt) return;
    if (rbStep.value === 0) {
      rbPt1.value = { x: pt.x, y: pt.y };
      rbStep.value = 1;
    } else if (rbStep.value === 1) {
      rbPt2.value = { x: pt.x, y: pt.y };
      rbDragging.value = true;
      rbStep.value = 2;
    } else if (rbStep.value === 3) {
      const p1 = rbPt1.value!;
      const p2 = rbPt2.value!;
      const geom = rotatedBoxFromEdgeAndPoint(p1, p2, pt);
      if (!geom) return;
      store.annotations.push({
        id: crypto.randomUUID(),
        type: "RotatedBox",
        class_id: selectedClassId.value || 0,
        cx: geom.cx / cw.value,
        cy: geom.cy / ch.value,
        width: geom.width / cw.value,
        height: geom.height / ch.value,
        angle: geom.angle,
      });
      rbStep.value = 0;
      rbPt1.value = null;
      rbPt2.value = null;
    }
    return;
  }

  // ---- Polygon draw ----
  if (currentTool.value === "polygon") {
    if (taskClasses.value.length === 0) {
      ElMessage.warning("请先添加类别");
      return;
    }
    if (!selectedClassId.value && taskClasses.value.length > 0)
      selectedClassId.value = taskClasses.value[0].id;
    const pt = mouseToImage(e);
    if (!pt) return;
    if (polyDrawingPoints.value.length >= 3) {
      const first = polyDrawingPoints.value[0];
      const dist = Math.hypot(pt.x - first.x * cw.value, pt.y - first.y * ch.value);
      if (dist <= 20) {
        store.annotations.push({
          id: crypto.randomUUID(),
          type: "Polygon",
          class_id: selectedClassId.value || 0,
          points: polyDrawingPoints.value.map((p) => ({ x: p.x, y: p.y })),
        });
        polyDrawingPoints.value = [];
        return;
      }
    }
    polyDrawingPoints.value.push({ x: pt.x / cw.value, y: pt.y / ch.value });
    return;
  }

  // ---- Keypoint draw ----
  if (currentTool.value === "keypoint") {
    if (taskClasses.value.length === 0) {
      ElMessage.warning("请先添加类别");
      return;
    }
    if (!selectedClassId.value && taskClasses.value.length > 0)
      selectedClassId.value = taskClasses.value[0].id;
    const pt = mouseToImage(e);
    if (!pt) return;
    const norm = { x: pt.x / cw.value, y: pt.y / ch.value };

    if (kpPhase.value === null) {
      const cls = taskClasses.value.find(c => c.id === selectedClassId.value)
      if (cls?.keypoint_names?.length) {
        kpNames.value = cls.keypoint_names
      } else {
        kpNames.value = ["top_left", "top_right", "bottom_right", "bottom_left"]
      }
      kpPhase.value = "corners";
      kpCorners.value = [
        { x: norm.x, y: norm.y, name: kpNames.value[0], visibility: pendingKpVisibility.value },
      ];
    } else if (kpPhase.value === "corners") {
      const idx = kpCorners.value.length;
      if (idx < kpNames.value.length) {
        kpCorners.value.push({
          x: norm.x,
          y: norm.y,
          name: kpNames.value[idx],
          visibility: pendingKpVisibility.value,
        });
        if (kpCorners.value.length >= kpNames.value.length) {
          kpPhase.value = "box";
        }
      }
    } else if (kpPhase.value === "box") {
      kpBoxDragStart = { x: norm.x, y: norm.y };
      kpBoxPreview.value = { x1: norm.x, y1: norm.y, x2: norm.x, y2: norm.y };
    }
    return;
  }

  // ---- OCR draw ----
  if (currentTool.value === "ocr") {
    if (taskClasses.value.length === 0) {
      ElMessage.warning("请先添加类别");
      return;
    }
    if (!selectedClassId.value && taskClasses.value.length > 0)
      selectedClassId.value = taskClasses.value[0].id;
    const pt = mouseToImage(e);
    if (!pt) return;
    if (ocrRectMode.value) {
      ocrSource.value = "rect";
      const r = canvasRef.value?.getBoundingClientRect();
      if (!r) return;
      ocrBoxStart = { x: pt.x, y: pt.y };
      bx = e.clientX - r.left;
      by = e.clientY - r.top;
      startBoxPreview(bx, by);
      drawing.value = true;
      showCrosshair.value = true;
      updCrosshair(e);
    } else {
      if (ocrDrawingPoints.value.length >= 3) {
        const first = ocrDrawingPoints.value[0];
        const dist = Math.hypot(pt.x - first.x * cw.value, pt.y - first.y * ch.value);
        if (dist <= 20) {
          ocrDrawingPoints.value.push({ ...first });
          setTimeout(() => { ocrTextInputVisible.value = true; }, 400);
          return;
        }
      }
      if (ocrDrawingPoints.value.length >= 4) return;
      if (ocrDrawingPoints.value.length === 0) ocrSource.value = "quad";
      ocrDrawingPoints.value.push({ x: pt.x / cw.value, y: pt.y / ch.value });
    }
    return;
  }
}

function onMouseMove(e: MouseEvent) {
  if (!store.currentImage) return;
  const pt = mouseToImage(e);
  if (pt) {
    cursorX.value = Math.round(pt.x);
    cursorY.value = Math.round(pt.y);
  }
  if (showCrosshair.value) updCrosshair(e);

  // ---- Pan drag ----
  if (drag.value.active && drag.value.type === "pan") {
    const dx = e.clientX - drag.value.startX;
    const dy = e.clientY - drag.value.startY;
    store.setPan(store.panX + dx, store.panY + dy);
    drag.value.startX = e.clientX;
    drag.value.startY = e.clientY;
    return;
  }

  // ---- Rotated box / Keypoint move ----
  if (drag.value.active && (drag.value.type === "move" || drag.value.type === "kp-move") && drag.value.ann) {
    const dx = (e.clientX - drag.value.startX) / dw.value;
    const dy = (e.clientY - drag.value.startY) / dh.value;
    const o = drag.value.orig;
    if (drag.value.ann.type === "AxisAlignedBox") {
      drag.value.ann.x1 = Math.max(0, Math.min(1, o.x1 + dx));
      drag.value.ann.y1 = Math.max(0, Math.min(1, o.y1 + dy));
      drag.value.ann.x2 = Math.max(0, Math.min(1, o.x2 + dx));
      drag.value.ann.y2 = Math.max(0, Math.min(1, o.y2 + dy));
    } else if (drag.value.ann.type === "Ocr") {
      drag.value.ann.points = o.points.map((p: any) => ({
        x: Math.max(0, Math.min(1, p.x + dx)),
        y: Math.max(0, Math.min(1, p.y + dy)),
      }));
    } else if (drag.value.ann.type === "RotatedBox") {
      drag.value.ann.cx = Math.max(0, Math.min(1, o.cx + dx));
      drag.value.ann.cy = Math.max(0, Math.min(1, o.cy + dy));
    } else if (drag.value.ann.type === "Polygon") {
      drag.value.ann.points = o.points.map((p: any) => ({
        x: Math.max(0, Math.min(1, p.x + dx)),
        y: Math.max(0, Math.min(1, p.y + dy)),
      }));
    } else if (drag.value.ann.type === "Keypoint" && drag.value.type === "kp-move") {
      const bb = drag.value.ann.bounding_box; const bbO = o.bounding_box
      if (bb && bbO) {
        bb.cx = Math.max(0, Math.min(1, bbO.cx + dx))
        bb.cy = Math.max(0, Math.min(1, bbO.cy + dy))
        drag.value.ann.keypoints = o.keypoints.map((kp: any) => {
          const newX = Math.max(0, Math.min(1, kp.x + dx))
          const newY = Math.max(0, Math.min(1, kp.y + dy))
          return { ...kp, x: newX, y: newY }
        })
      }
    }
    return;
  }

  // ---- Polygon vertex drag ----
  if (drag.value.active && drag.value.type === "poly-vertex" && drag.value.ann) {
    const dx = (e.clientX - drag.value.startX) / dw.value;
    const dy = (e.clientY - drag.value.startY) / dh.value;
    const o = drag.value.orig;
    const idx = drag.value.polyVertexIndex!;
    if ((drag.value.ann.type === "Polygon" || drag.value.ann.type === "Ocr") && idx !== undefined && o.points?.[idx]) {
      drag.value.ann.points = o.points.map((p: any, i: number) =>
        i === idx
          ? { x: Math.max(0, Math.min(1, p.x + dx)), y: Math.max(0, Math.min(1, p.y + dy)) }
          : p
      );
    }
    return;
  }

  // ---- Keypoint vertex drag ----
  if (drag.value.active && drag.value.type === "kp-vertex" && drag.value.ann?.type === "Keypoint") {
    const dx = (e.clientX - drag.value.startX) / dw.value
    const dy = (e.clientY - drag.value.startY) / dh.value
    const o = drag.value.orig; const idx = drag.value.polyVertexIndex!
    const ann = drag.value.ann
    if (idx !== undefined && o.keypoints?.[idx]) {
      let newX = o.keypoints[idx].x + dx
      let newY = o.keypoints[idx].y + dy
      const bb = ann.bounding_box
      if (bb) {
        const aspect = ch.value / cw.value
        const cos = Math.cos(bb.angle); const sin = Math.sin(bb.angle)
        const dx2 = newX - bb.cx; const dy2 = newY - bb.cy
        const localX = Math.max(-bb.width/2, Math.min(bb.width/2, dx2 * cos + dy2 * aspect * sin))
        const localY = Math.max(-bb.height/2, Math.min(bb.height/2, -dx2/aspect * sin + dy2 * cos))
        newX = bb.cx + localX * cos - localY/aspect * sin
        newY = bb.cy + localX * aspect * sin + localY * cos
      }
      ann.keypoints = o.keypoints.map((kp: any, i: number) =>
        i === idx ? { ...kp, x: Math.max(0, Math.min(1, newX)), y: Math.max(0, Math.min(1, newY)) } : kp
      )
    }
    return
  }

  // ---- Resize annotation ----
  if (drag.value.active && drag.value.type.startsWith("resize-") && drag.value.ann) {
    const dx = (e.clientX - drag.value.startX) / dw.value;
    const dy = (e.clientY - drag.value.startY) / dh.value;
    const o = drag.value.orig;
    const ann = drag.value.ann;
    const h = drag.value.handle;
    if (ann.type === "AxisAlignedBox") {
      if (h.includes("l")) ann.x1 = Math.max(0, Math.min(o.x2 - 0.01, o.x1 + dx));
      if (h.includes("r")) ann.x2 = Math.min(1, Math.max(o.x1 + 0.01, o.x2 + dx));
      if (h.includes("t")) ann.y1 = Math.max(0, Math.min(o.y2 - 0.01, o.y1 + dy));
      if (h.includes("b")) ann.y2 = Math.min(1, Math.max(o.y1 + 0.01, o.y2 + dy));
    } else if (drag.value.type === "resize-ocr" && ann.type === "Ocr") {
      const ox1 = Math.min(...o.points.map((p: any) => p.x));
      const oy1 = Math.min(...o.points.map((p: any) => p.y));
      const ox2 = Math.max(...o.points.map((p: any) => p.x));
      const oy2 = Math.max(...o.points.map((p: any) => p.y));
      let nx1 = ox1, ny1 = oy1, nx2 = ox2, ny2 = oy2;
      if (h.includes("l")) nx1 = Math.max(0, Math.min(ox2 - 0.01, ox1 + dx));
      if (h.includes("r")) nx2 = Math.min(1, Math.max(ox1 + 0.01, ox2 + dx));
      if (h.includes("t")) ny1 = Math.max(0, Math.min(oy2 - 0.01, oy1 + dy));
      if (h.includes("b")) ny2 = Math.min(1, Math.max(oy1 + 0.01, oy2 + dy));
      ann.points = [
          { x: nx1, y: ny1 },
          { x: nx2, y: ny1 },
          { x: nx2, y: ny2 },
          { x: nx1, y: ny2 },
        ];
    } else if (ann.type === "RotatedBox" && pt) {
      const cos = Math.cos(o.angle);
      const sin = Math.sin(o.angle);
      const aspect = ch.value / cw.value;
      const fx = h.includes("l") ? 1 : h.includes("r") ? -1 : 1;
      const fy = h.includes("t") ? 1 : h.includes("b") ? -1 : 1;
      const mx = pt.x / cw.value;
      const my = pt.y / ch.value; // absolute mouse in normalized
      const fix_x = o.cx + ((fx * o.width) / 2) * cos - ((fy * o.height) / 2) * aspect * sin;
      const fix_y = o.cy + ((fx * o.width) / 2 / aspect) * sin + ((fy * o.height) / 2) * cos;
      const newCx = (fix_x + mx) / 2;
      const newCy = (fix_y + my) / 2;
      const dvx = (mx - newCx) * cw.value;
      const dvy = (my - newCy) * ch.value;
      const lx = dvx * cos + dvy * sin;
      const ly = -dvx * sin + dvy * cos;
      ann.width = Math.max(0.001, (Math.abs(lx) * 2) / cw.value);
      ann.height = Math.max(0.001, (Math.abs(ly) * 2) / ch.value);
      ann.cx = Math.max(0, Math.min(1, newCx));
      ann.cy = Math.max(0, Math.min(1, newCy));
    }
    return;
  }

  // ---- Rotate RotatedBox ----
  if (drag.value.active && drag.value.type === "rotate" && drag.value.ann?.type === "RotatedBox") {
    const c = canvasRef.value;
    if (!c) return;
    const r = c.getBoundingClientRect();
    const imgL = r.width / 2 - dw.value / 2 + store.panX;
    const imgT = r.height / 2 - dh.value / 2 + store.panY;
    const centerX = r.left + imgL + drag.value.ann.cx * dw.value;
    const centerY = r.top + imgT + drag.value.ann.cy * dh.value;
    const prevAngle = Math.atan2(drag.value.startY - centerY, drag.value.startX - centerX);
    const curAngle = Math.atan2(e.clientY - centerY, e.clientX - centerX);
    drag.value.ann.angle = drag.value.orig.angle + (curAngle - prevAngle);
    return;
  }

  // ---- Keypoint bbox resize ----
  if (drag.value.active && drag.value.type.startsWith("kp-resize-") && drag.value.ann?.type === "Keypoint") {
    const dx = (e.clientX - drag.value.startX) / dw.value
    const dy = (e.clientY - drag.value.startY) / dh.value
    const o = drag.value.orig; const ann = drag.value.ann; const h = drag.value.handle
    const bb = ann.bounding_box; const bbO = o.bounding_box
    if (!bb || !bbO) return
    const aspect = ch.value / cw.value
    const cos = Math.cos(bbO.angle); const sin = Math.sin(bbO.angle)
    const rawW = dx * cos + dy * sin
    const rawH = -dx * sin + dy * cos
    const wSign = (h.includes("l") && !h.includes("r")) ? -1 : (h.includes("r") && !h.includes("l")) ? 1 : 0
    const hSign = (h.includes("t") && !h.includes("b")) ? -1 : (h.includes("b") && !h.includes("t")) ? 1 : 0
    bb.width = Math.max(0.001, bbO.width + wSign * rawW)
    bb.height = Math.max(0.001, bbO.height + hSign * rawH)
    const dcx = (bb.width - bbO.width) / 2 * cos * wSign
    const dcy = (bb.width - bbO.width) / 2 * sin * wSign
    const dcx2 = -(bb.height - bbO.height) / 2 * sin * hSign
    const dcy2 = (bb.height - bbO.height) / 2 * cos * hSign
    bb.cx = Math.max(0, Math.min(1, bbO.cx + dcx + dcx2))
    bb.cy = Math.max(0, Math.min(1, bbO.cy + dcy + dcy2))
    // Clamp keypoints to stay inside bounding box
    if (ann.keypoints) {
      const minX = bb.cx - bb.width / 2
      const maxX = bb.cx + bb.width / 2
      const minY = bb.cy - bb.height / 2
      const maxY = bb.cy + bb.height / 2
      ann.keypoints.forEach((kp: any) => {
        kp.x = Math.max(minX, Math.min(maxX, kp.x))
        kp.y = Math.max(minY, Math.min(maxY, kp.y))
      })
    }
    return
  }

  // ---- Box drawing preview ----
  if (drawing.value && currentTool.value === "box") {
    const r = canvasRef.value?.getBoundingClientRect();
    if (!r) return;
    updateBoxPreview(e.clientX - r.left, e.clientY - r.top);
    updCrosshair(e);
    return;
  }

  // ---- Rotated box drawing preview ----
  if (currentTool.value === "rotated_box") {
    if (rbStep.value === 2 && pt) {
      rbPt2.value = { x: pt.x, y: pt.y };
    }
    if (rbStep.value === 1 || rbStep.value === 3) {
      updCrosshair(e);
    }
    return;
  }

  // ---- Keypoint box drag preview ----
  if (currentTool.value === "keypoint" && kpPhase.value === "box" && kpBoxDragStart && pt) {
    const norm = { x: pt.x / cw.value, y: pt.y / ch.value };
    kpBoxPreview.value = { x1: kpBoxDragStart.x, y1: kpBoxDragStart.y, x2: norm.x, y2: norm.y };
    return;
  }

  // ---- OCR rectangle mode drag preview ----
  if (currentTool.value === "ocr" && ocrRectMode.value && drawing.value) {
    const r = canvasRef.value?.getBoundingClientRect();
    if (!r) return;
    updateBoxPreview(e.clientX - r.left, e.clientY - r.top);
    updCrosshair(e);
    return;
  }
}

function onMouseUp(e: MouseEvent) {
  // ---- Finish box draw ----
  if (drawing.value && currentTool.value === "box") {
    drawing.value = false;
    removeBoxPreview();
    const pt = mouseToImage(e);
    if (!pt) return;
    const w = Math.abs(pt.x - drawStartImg.x);
    const h = Math.abs(pt.y - drawStartImg.y);
    if (w > 5 && h > 5) {
      store.annotations.push({
        id: crypto.randomUUID(),
        type: "AxisAlignedBox",
        class_id: selectedClassId.value || 0,
        x1: Math.min(drawStartImg.x, pt.x) / cw.value,
        y1: Math.min(drawStartImg.y, pt.y) / ch.value,
        x2: Math.max(drawStartImg.x, pt.x) / cw.value,
        y2: Math.max(drawStartImg.y, pt.y) / ch.value,
      });
    }
    return;
  }

  // ---- Rotated box step ----
  if (currentTool.value === "rotated_box" && rbStep.value === 2) {
    if (!rbDragging.value) {
      rbStep.value = 3;
    } else {
      const pt = mouseToImage(e);
      if (pt) rbPt2.value = { x: pt.x, y: pt.y };
      rbStep.value = 3;
      rbDragging.value = false;
    }
    return;
  }

  // ---- Keypoint box finish ----
  if (currentTool.value === "keypoint" && kpPhase.value === "box" && kpBoxPreview.value) {
    const w = Math.abs(kpBoxPreview.value.x2 - kpBoxPreview.value.x1) * cw.value;
    const h = Math.abs(kpBoxPreview.value.y2 - kpBoxPreview.value.y1) * ch.value;
    if (w > 5 && h > 5) {
      const vis = ["Hidden", "Occluded", "Visible"];
      store.annotations.push({
        id: crypto.randomUUID(),
        type: "Keypoint",
        class_id: selectedClassId.value || 0,
        keypoints: kpCorners.value.map((c) => ({
          x: c.x,
          y: c.y,
          visibility: vis[c.visibility],
          name: c.name,
        })),
        bounding_box: {
          cx: (kpBoxPreview.value.x1 + kpBoxPreview.value.x2) / 2,
          cy: (kpBoxPreview.value.y1 + kpBoxPreview.value.y2) / 2,
          width: Math.abs(kpBoxPreview.value.x2 - kpBoxPreview.value.x1),
          height: Math.abs(kpBoxPreview.value.y2 - kpBoxPreview.value.y1),
          angle: 0,
        },
      });
    }
    kpCorners.value = [];
    kpBoxPreview.value = null;
    kpPhase.value = null;
    kpBoxDragStart = null;
    return;
  }

  // ---- OCR rectangle mode finish ----
  if (currentTool.value === "ocr" && ocrRectMode.value && drawing.value) {
    drawing.value = false;
    removeBoxPreview();
    const pt = mouseToImage(e);
    if (pt && ocrBoxStart) {
      const w = Math.abs(pt.x - ocrBoxStart.x);
      const h = Math.abs(pt.y - ocrBoxStart.y);
      if (w > 5 && h > 5) {
        const x1 = Math.min(ocrBoxStart.x, pt.x) / cw.value;
        const y1 = Math.min(ocrBoxStart.y, pt.y) / ch.value;
        const x2 = Math.max(ocrBoxStart.x, pt.x) / cw.value;
        const y2 = Math.max(ocrBoxStart.y, pt.y) / ch.value;
        ocrDrawingPoints.value = [
          { x: x1, y: y1 },
          { x: x2, y: y1 },
          { x: x2, y: y2 },
          { x: x1, y: y2 },
        ];
        setTimeout(() => { ocrTextInputVisible.value = true; }, 400);
      }
    }
    return;
  }

  // ---- End drag ----
  if (drag.value.active) {
    if (
      drag.value.ann &&
      (drag.value.type === "move" ||
        drag.value.type.startsWith("resize-") ||
        drag.value.type === "poly-vertex" ||
        drag.value.type === "rotate" ||
        drag.value.type === "kp-vertex" ||
        drag.value.type === "kp-move" ||
        drag.value.type.startsWith("kp-resize-"))
    ) {
      markUnsaved();
      pushHistory();
    }
    drag.value.active = false;
  }
}

// Window-level mouseup catch (for safety when mouse leaves canvas)
function onWindowMouseUp() {
  if (drag.value.active) drag.value.active = false;
  if (drawing.value) {
    drawing.value = false;
    showCrosshair.value = false;
    removeBoxPreview();
  }
}

function onWheel(e: WheelEvent) {
  const d = e.deltaY > 0 ? -0.08 : 0.08;
  store.setZoom(Math.max(0.1, Math.min(10, store.zoom + d)));
}

function onDblClick(_e: MouseEvent) {
  if (currentTool.value === "polygon" && polyDrawingPoints.value.length >= 3) {
    store.annotations.push({
      id: crypto.randomUUID(),
      type: "Polygon",
      class_id: selectedClassId.value || 0,
      points: polyDrawingPoints.value.map((p) => ({ x: p.x, y: p.y })),
    });
    polyDrawingPoints.value = [];
  }

}

// ===== 标注选中 / 拖拽 =====
function startOcrRectResize(e: MouseEvent, ann: any, edges: string) {
  e.stopPropagation();
  e.preventDefault();
  store.selectedAnnotationId = ann.id;
  drag.value = {
    active: true,
    type: "resize-ocr",
    ann,
    orig: JSON.parse(JSON.stringify(ann)),
    startX: e.clientX,
    startY: e.clientY,
    handle: edges,
  };
}
function onAnnMouseDown(e: MouseEvent, ann: any) {
  e.stopPropagation();

  if (currentTool.value === "select" || currentTool.value === "pan" || currentTool.value === "ocr") {
    const t = e.target as HTMLElement;
    const handle = t.getAttribute("data-handle");

    // ---- AxisAlignedBox resize/edge handle ----
    if (handle && handle.startsWith("resize-")) {
      store.selectedAnnotationId = ann.id;
      drag.value = {
        active: true,
        type: handle as DragState["type"],
        ann,
        orig: JSON.parse(JSON.stringify(ann)),
        startX: e.clientX,
        startY: e.clientY,
        handle,
      };
      return;
    }

    // ---- Keypoint handles (must check before generic move) ----
    if (handle && ann.type === "Keypoint") {
      if (handle.startsWith("kp-")) {
        const idx = parseInt(handle.replace("kp-", ""), 10)
        if (!isNaN(idx)) { store.selectedAnnotationId = ann.id; drag.value = { active: true, type: "kp-vertex", ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle: "", polyVertexIndex: idx }; return }
      }
      if (handle === "move") { store.selectedAnnotationId = ann.id; drag.value = { active: true, type: "kp-move", ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle: "" }; return }
      if (["tl","tr","bl","br","tc","bc","ml","mr"].includes(handle)) { store.selectedAnnotationId = ann.id; drag.value = { active: true, type: ("kp-resize-" + handle) as any, ann, orig: JSON.parse(JSON.stringify(ann)), startX: e.clientX, startY: e.clientY, handle }; return }
    }

    // ---- RotatedBox handles (unprefixed) ----
    if (handle) {
      store.selectedAnnotationId = ann.id;
      if (handle === "move") {
        drag.value = {
          active: true,
          type: "move",
          ann,
          orig: JSON.parse(JSON.stringify(ann)),
          startX: e.clientX,
          startY: e.clientY,
          handle: "",
        };
        return;
      }
      if (handle === "rotate") {
        drag.value = {
          active: true,
          type: "rotate",
          ann,
          orig: JSON.parse(JSON.stringify(ann)),
          startX: e.clientX,
          startY: e.clientY,
          handle: "",
        };
        return;
      }
      if (["tl", "tr", "bl", "br"].includes(handle)) {
        drag.value = {
          active: true,
          type: ("resize-" + handle) as DragState["type"],
          ann,
          orig: JSON.parse(JSON.stringify(ann)),
          startX: e.clientX,
          startY: e.clientY,
          handle,
        };
        return;
      }
      // ---- Polygon vertex drag ----
      if (handle.startsWith("poly-") || handle.startsWith("ocr-vertex-")) {
        const prefix = handle.startsWith("poly-") ? "poly-" : "ocr-vertex-";
        const idx = parseInt(handle.replace(prefix, ""), 10);
        if (!isNaN(idx)) {
          store.selectedAnnotationId = ann.id;
          drag.value = {
            active: true,
            type: "poly-vertex",
            ann,
            orig: JSON.parse(JSON.stringify(ann)),
            startX: e.clientX,
            startY: e.clientY,
            handle: "",
            polyVertexIndex: idx,
          };
          return;
        }
      }
    }

    // ---- Select & move ----
    store.selectedAnnotationId = ann.id;
    drag.value = {
      active: true,
      type: ann.type === "Keypoint" ? "kp-move" : "move",
      ann,
      orig: JSON.parse(JSON.stringify(ann)),
      startX: e.clientX,
      startY: e.clientY,
      handle: "",
    };
  }
}

// ===== Handles =====
function boxHandles(ann: any) {
  const x1 = ann.x1 * cw.value;
  const y1 = ann.y1 * ch.value;
  const x2 = ann.x2 * cw.value;
  const y2 = ann.y2 * ch.value;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return [
    { key: "resize-tl", x: x1, y: y1 },
    { key: "resize-tr", x: x2, y: y1 },
    { key: "resize-bl", x: x1, y: y2 },
    { key: "resize-br", x: x2, y: y2 },
    { key: "resize-l", x: x1, y: my },
    { key: "resize-r", x: x2, y: my },
    { key: "resize-t", x: mx, y: y1 },
    { key: "resize-b", x: mx, y: y2 },
  ];
}
function ocrBoxHandles(ann: any) {
  const B = ocrBBox(ann);
  const mx = (B.minX + B.maxX) / 2;
  const my = (B.minY + B.maxY) / 2;
  return [
    { key: "resize-tl", x: B.minX, y: B.minY, edges: "l,t" },
    { key: "resize-tr", x: B.maxX, y: B.minY, edges: "r,t" },
    { key: "resize-bl", x: B.minX, y: B.maxY, edges: "l,b" },
    { key: "resize-br", x: B.maxX, y: B.maxY, edges: "r,b" },
    { key: "resize-l", x: B.minX, y: my, edges: "l" },
    { key: "resize-r", x: B.maxX, y: my, edges: "r" },
    { key: "resize-t", x: mx, y: B.minY, edges: "t" },
    { key: "resize-b", x: mx, y: B.maxY, edges: "b" },
  ];
}

// ===== 标注操作 =====
function removeAnn(id: string) {
  store.annotations = store.annotations.filter((a) => a.id !== id);
  if (store.selectedAnnotationId === id) store.selectedAnnotationId = null;
}

// ===== 自动保存（仅实际变更时触发）=====
let saveTimer: ReturnType<typeof setTimeout> | null = null;
const unsaved = ref(false);
let lastSavedKey = ""; // 当前已保存的标注快照 key

function annotKey(anns: any[]) {
  return anns
    .map((a: any) => {
      if (a.type === "RotatedBox")
        return `${a.id}:RotatedBox:${a.class_id}:${a.cx}:${a.cy}:${a.width}:${a.height}:${a.angle}`;
      if (a.type === "Polygon")
        return `${a.id}:Polygon:${a.class_id}:${(a.points || []).map((p: any) => `${p.x},${p.y}`).join(";")}`;
      if (a.type === "Keypoint")
        return `${a.id}:Keypoint:${a.class_id}:${(a.keypoints || []).map((k: any) => `${k.x},${k.y},${k.visibility},${k.name}`).join(";")}:${a.bounding_box ? `${a.bounding_box.cx},${a.bounding_box.cy},${a.bounding_box.width},${a.bounding_box.height},${a.bounding_box.angle}` : "0,0,0,0,0"}`;
      if (a.type === "Ocr")
        return `${a.id}:Ocr:${a.class_id}:${(a.points || []).map((p: any) => `${p.x},${p.y}`).join(";")}:${a.text || ""}`;
      return `${a.id}:AxisAlignedBox:${a.class_id}:${a.x1}:${a.y1}:${a.x2}:${a.y2}`;
    })
    .sort()
    .join("|");
}

async function autoSave() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    if (!store.currentImage) return;
    const key = annotKey(store.annotations);
    if (key === lastSavedKey) {
      unsaved.value = false;
      return;
    }
    try {
      await AnnotationAPI.saveAnnotations(store.currentImage.id, {
        task_id: store.taskId,
        image_id: store.currentImage.id,
        annotation_data: store.annotations,
      });
      lastSavedKey = key;
      const curUser = useUserStoreHook().getBasicInfo;
      const uname =
        (curUser as any).name || (curUser as any).nickname || (curUser as any).username || "";
      store.currentImage.status = store.annotations.length > 0 ? "annotated" : "unannotated";
      store.currentImage.annotation_count = store.annotations.length;
      store.currentImage.updated_by = uname
        ? { id: (curUser as any).id || 0, name: uname }
        : undefined;
      store.currentImage.updated_time = uname ? new Date().toISOString() : undefined;
      unsaved.value = false;
      updateProgress();
      fetchTaskProgress();
    } catch {}
  }, 3000);
}

function markUnsaved() {
  unsaved.value = true;
  autoSave();
}

// ===== 撤销/重做 (Ctrl+Z / Ctrl+Y) =====
let historyStack: string[] = [];
let historyIndex = -1;
const MAX_HISTORY = 50;

function pushHistory() {
  const key = annotKey(store.annotations);
  if (historyIndex >= 0 && historyStack[historyIndex] === key) return;
  historyStack = historyStack.slice(0, historyIndex + 1);
  historyStack.push(key);
  if (historyStack.length > MAX_HISTORY) historyStack.shift();
  historyIndex = historyStack.length - 1;
}
function undo() {
  if (historyIndex <= 0) return;
  historyIndex--;
  restoreHistory();
}
function redo() {
  if (historyIndex >= historyStack.length - 1) return;
  historyIndex++;
  restoreHistory();
}
function restoreHistory() {
  const key = historyStack[historyIndex];
  const items = key
    ? key
        .split("|")
        .filter(Boolean)
        .map((s: string) => {
          const parts = s.split(":");
          if (parts.length < 3) return null;
          const type = parts[1];
          if (type === "RotatedBox" && parts.length >= 8) {
            return {
              id: parts[0],
              type: "RotatedBox",
              class_id: Number(parts[2]),
              cx: Number(parts[3]),
              cy: Number(parts[4]),
              width: Number(parts[5]),
              height: Number(parts[6]),
              angle: Number(parts[7]),
            };
          }
          if (type === "Polygon" && parts.length >= 4) {
            const points = parts[3]
              .split(";")
              .filter(Boolean)
              .map((s: string) => {
                const [x, y] = s.split(",").map(Number);
                return { x, y };
              });
            return { id: parts[0], type: "Polygon", class_id: Number(parts[2]), points };
          }
          if (type === "Keypoint" && parts.length >= 5) {
            const kps = parts[3]
              .split(";")
              .filter(Boolean)
              .map((s: string) => {
                const [x, y, visibility, ...nameParts] = s.split(",");
                return { x: Number(x), y: Number(y), visibility, name: nameParts.join(",") };
              });
            const [cx, cy, bw, bh, ba] = parts[4].split(",").map(Number);
            return {
              id: parts[0],
              type: "Keypoint",
              class_id: Number(parts[2]),
              keypoints: kps,
              bounding_box: { cx, cy, width: bw, height: bh, angle: ba },
            };
          }
          if (type === "Ocr" && parts.length >= 5) {
            const points = parts[3]
              .split(";")
              .filter(Boolean)
              .map((s: string) => {
                const [x, y] = s.split(",").map(Number);
                return { x, y };
              });
            const text = parts.slice(4).join(":");
            return { id: parts[0], type: "Ocr", class_id: Number(parts[2]), points, text };
          }
          if (parts.length >= 6) {
            return {
              id: parts[0],
              type: "AxisAlignedBox",
              class_id: Number(parts[2]),
              x1: Number(parts[3]),
              y1: Number(parts[4]),
              x2: Number(parts[5]),
              y2: Number(parts[6]),
            };
          }
          return null;
        })
        .filter(Boolean)
    : [];
  store.annotations = items as any;
  markUnsaved();
}

// 标注变更时自动保存 + 记录历史
watch(
  () => store.annotations.length,
  () => {
    const key = annotKey(store.annotations);
    if (key !== lastSavedKey) {
      unsaved.value = true;
      autoSave();
      pushHistory();
    }
  }
);

// 拖拽/移动结束也要保存历史（通过 onMouseUp 的 markUnsaved 已处理保存）
// 额外在 create/delete/dragEnd 时 pushHistory
function afterEdit() {
  pushHistory();
}

// 拖拽/移动结束时也要记录历史
// (已有 markUnsaved 调用，但历史需要单独 push)
// 在 onMouseUp 的回调中 pushHistory

// 切图时重置 lastSavedKey
async function loadImg(imageId: number) {
  imgUrl.value = "";
  store.selectedAnnotationId = null;
  const idx = store.images.findIndex((i) => i.id === imageId);
  if (idx >= 0) store.currentImageIndex = idx;
  try {
    const r = await AnnotationAPI.getPresignedUrl(imageId, store.taskId);
    imgUrl.value = r.data?.data?.url || "";
    const ar = await AnnotationAPI.getAnnotations(store.taskId, imageId);
    store.annotations = ar.data?.data || [];
    lastSavedKey = annotKey(store.annotations);
    historyStack = [lastSavedKey];
    historyIndex = 0;
    // Lock this image for current user
    AnnotationAPI.lockImage(imageId, store.taskId).catch(() => {});
    await nextTick();
    measureLabelRects();
  } catch {
    imgUrl.value = "";
  }
  updateProgress();
}
async function goToImage(idx: number) {
  if (idx < 0 || idx >= store.images.length) return;
  // Unlock current image
  if (store.currentImage) {
    AnnotationAPI.unlockImage(store.currentImage.id, store.taskId).catch(() => {});
  }
  // 先保存当前图片的标注
  if (unsaved.value && store.currentImage) {
    if (saveTimer) clearTimeout(saveTimer);
    try {
      await AnnotationAPI.saveAnnotations(store.currentImage.id, {
        task_id: store.taskId,
        image_id: store.currentImage.id,
        annotation_data: store.annotations,
      });
      store.currentImage.status = store.annotations.length > 0 ? "annotated" : "unannotated";
      store.currentImage.annotation_count = store.annotations.length;
      updateProgress();
    } catch {}
  }
  unsaved.value = false;
  loadImg(store.images[idx].id);
}
function prevImg() {
  if (store.currentImageIndex > 0) goToImage(store.currentImageIndex - 1);
}
function nextImg() {
  if (store.currentImageIndex < store.images.length - 1) goToImage(store.currentImageIndex + 1);
}

// ===== 任务进度 =====
const taskProgress = ref(0);
async function fetchTaskProgress() {
  if (!task.value?.id) return;
  try {
    const r = await AnnotationAPI.getTaskProgress(task.value.id);
    const d = r.data?.data;
    if (d) {
      taskProgress.value = d.progress || 0;
    }
  } catch {}
}

async function saveAnn() {
  const img = store.currentImage;
  if (!img) return;
  store.saving = true;
  try {
    await AnnotationAPI.saveAnnotations(img.id, {
      task_id: store.taskId,
      image_id: img.id,
      annotation_data: store.annotations,
    });
    const now = new Date().toISOString();
    const curUser = useUserStoreHook().getBasicInfo;
    img.status = store.annotations.length > 0 ? "annotated" : "unannotated";
    img.annotation_count = store.annotations.length;
    img.updated_by = {
      id: (curUser as any).id || 0,
      name: (curUser as any).name || (curUser as any).username || "",
    };
    img.updated_time = now;
    unsaved.value = false;
    updateProgress();
    await fetchTaskProgress();
    ElMessage.success("保存成功");
  } finally {
    store.saving = false;
  }
}

function setTool(t: ToolName) {
  currentTool.value = t;
  store.setTool(t);
}
function handleBack() {
  router.push("/annotation/task");
}
function fmtTime(t?: string) {
  if (!t) return "";
  const d = new Date(t);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
}

// ===== 键盘 =====
const keyToolMap: Record<string, ToolName> = {
  "1": "select",
  s: "select",
  "2": "box",
  b: "box",
  "3": "rotated_box",
  r: "rotated_box",
  "4": "polygon",
  p: "polygon",
  "5": "keypoint",
  k: "keypoint",
  "6": "ocr",
  o: "ocr",
  "7": "classification",
  c: "classification",
};
function onKey(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const k = e.key.toLowerCase();
  if (e.ctrlKey && k === "s") {
    e.preventDefault();
    saveAnn();
    return;
  }
  if (e.ctrlKey && k === "z") {
    e.preventDefault();
    undo();
    return;
  }
  if (e.ctrlKey && k === "y") {
    e.preventDefault();
    redo();
    return;
  }
  if ((k === "delete" || k === "backspace") && store.selectedAnnotationId) {
    removeAnn(store.selectedAnnotationId);
    afterEdit();
    return;
  }
  if (k === "arrowleft" || k === "a") {
    prevImg();
    return;
  }
  if (k === "arrowright" || k === "d") {
    nextImg();
    return;
  }
  if (k === "escape") {
    drawing.value = false;
    showCrosshair.value = false;
    store.selectedAnnotationId = null;
    removeBoxPreview();
    rbStep.value = 0;
    rbPt1.value = null;
    rbPt2.value = null;
    polyDrawingPoints.value = [];
    kpCorners.value = [];
    kpBoxPreview.value = null;
    kpPhase.value = null;
    kpBoxDragStart = null;
    ocrDrawingPoints.value = [];
    ocrTextInputVisible.value = false;
    return;
  }
  if (k === "0" && kpPhase.value === "corners") {
    pendingKpVisibility.value = 0;
    return;
  }
  if (k === "1" && kpPhase.value === "corners") {
    pendingKpVisibility.value = 1;
    return;
  }
  if (k === "2" && kpPhase.value === "corners") {
    pendingKpVisibility.value = 2;
    return;
  }
  if (k === "enter" && ocrTextInputVisible.value) {
    confirmOcrText();
    return;
  }
  if (k === "t" && currentTool.value === "ocr") {
    ocrRectMode.value = !ocrRectMode.value;
    return;
  }
  if (k === "enter" && kpPhase.value === "box" && kpBoxPreview.value) {
    const w = Math.abs(kpBoxPreview.value.x2 - kpBoxPreview.value.x1) * cw.value;
    const h = Math.abs(kpBoxPreview.value.y2 - kpBoxPreview.value.y1) * ch.value;
    if (w > 5 && h > 5) {
      const vis = ["Hidden", "Occluded", "Visible"];
      store.annotations.push({
        id: crypto.randomUUID(),
        type: "Keypoint",
        class_id: selectedClassId.value || 0,
        keypoints: kpCorners.value.map((c) => ({
          x: c.x,
          y: c.y,
          visibility: vis[c.visibility],
          name: c.name,
        })),
        bounding_box: {
          cx: (kpBoxPreview.value.x1 + kpBoxPreview.value.x2) / 2,
          cy: (kpBoxPreview.value.y1 + kpBoxPreview.value.y2) / 2,
          width: Math.abs(kpBoxPreview.value.x2 - kpBoxPreview.value.x1),
          height: Math.abs(kpBoxPreview.value.y2 - kpBoxPreview.value.y1),
          angle: 0,
        },
      });
    }
    kpCorners.value = [];
    kpBoxPreview.value = null;
    kpPhase.value = null;
    kpBoxDragStart = null;
    return;
  }
  if (k === "enter" && kpPhase.value === "corners" && kpCorners.value.length >= 3) {
    const xs = kpCorners.value.map((c) => c.x);
    const ys = kpCorners.value.map((c) => c.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const vis = ["Hidden", "Occluded", "Visible"];
    store.annotations.push({
      id: crypto.randomUUID(),
      type: "Keypoint",
      class_id: selectedClassId.value || 0,
      keypoints: kpCorners.value.map((c) => ({
        x: c.x,
        y: c.y,
        visibility: vis[c.visibility],
        name: c.name,
      })),
      bounding_box: {
        cx: (minX + maxX) / 2,
        cy: (minY + maxY) / 2,
        width: maxX - minX,
        height: maxY - minY,
        angle: 0,
      },
    });
    kpCorners.value = [];
    kpBoxPreview.value = null;
    kpPhase.value = null;
    kpBoxDragStart = null;
    return;
  }
  const t = keyToolMap[k];
  if (t && displayTools.value.some((d) => d.name === t)) setTool(t);
}

// ===== 生命周期 =====
onMounted(async () => {
  const tid = Number(route.params.id || route.query.id || 0);
  if (!tid) return;
  store.loading = true;
  try {
    const dr = await AnnotationAPI.getTaskDetail(tid);
    const t = dr.data?.data;
    if (!t) return;
    task.value = t;
    taskType.value = t.task_type || "detection";
    taskClasses.value = t.classes || [];
    currentTool.value = "select";
    store.setTool("select");
    store.taskId = tid;
    if (taskClasses.value.length > 0) selectedClassId.value = taskClasses.value[0].id;
    const ir = await AnnotationAPI.getImages(t.dataset_id, tid);
    const imgs = ir.data?.data || [];
    store.images = imgs;
    if (imgs.length > 0) await loadImg(imgs[0].id);
    await fetchTaskProgress();
  } catch (e: any) {
    ElMessage.error("加载失败: " + (e?.msg || e?.message || ""));
  } finally {
    store.loading = false;
  }
  document.addEventListener("keydown", onKey);
  window.addEventListener("mouseup", onWindowMouseUp);
  watch(
    () => store.annotations.length,
    () => measureLabelRects()
  );
});
onBeforeUnmount(() => {
  document.removeEventListener("keydown", onKey);
  window.removeEventListener("mouseup", onWindowMouseUp);
  if (store.currentImage) {
    AnnotationAPI.unlockImage(store.currentImage.id, store.taskId).catch(() => {});
  }
});
</script>

<style scoped>
.ann-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  background: #f5f7fa;
  overflow: hidden;
}
.ann-header {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  gap: 10px;
  flex-shrink: 0;
  height: 44px;
}
.ann-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}
.task-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-text {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.ann-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.ann-leftbar {
  width: 52px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 2px;
  gap: 2px;
  flex-shrink: 0;
}
.tool-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
}
.tool-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 6px;
  cursor: pointer;
  color: #606266;
  transition: all 0.12s;
  border: 1px solid transparent;
}
.tool-btn:hover {
  background: #f0f2f5;
}
.tool-btn.active {
  background: #ecf5ff;
  border-color: #409eff;
  color: #409eff;
}
.tool-label {
  font-size: 9px;
  margin-top: 1px;
  line-height: 1;
}
.ann-canvas-area {
  flex: 1;
  overflow: hidden;
  position: relative;
  background: #f0f2f5;
}
.canvas-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}
.crosshair {
  position: absolute;
  pointer-events: none;
  z-index: 20;
}
.crosshair-x {
  left: 0;
  height: 1px;
  background: rgba(59, 130, 246, 0.5);
  width: 100%;
}
.crosshair-y {
  top: 0;
  width: 1px;
  background: rgba(59, 130, 246, 0.5);
  height: 100%;
}
.crosshair-circle {
  position: absolute;
  pointer-events: none;
  z-index: 20;
  width: 8px;
  height: 8px;
  border: 1px solid rgba(59, 130, 246, 0.5);
  border-radius: 50%;
}
.box-preview {
  position: absolute;
  pointer-events: none;
  z-index: 15;
  border: 2px dashed #3b82f6;
  background: rgba(59, 130, 246, 0.06);
}
.ann-svg {
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
}
.ann-img {
  position: absolute;
  top: 50%;
  left: 50%;
}
.ann-svg rect,
.ann-svg g {
  pointer-events: all;
  cursor: pointer;
}
.ann-svg .handle {
  cursor: pointer;
  pointer-events: all;
}
.ann-svg .ann-label {
  pointer-events: none;
}
.no-image {
  color: #909399;
  font-size: 13px;
}
.ann-rightbar {
  width: 240px;
  background: #fff;
  border-left: 1px solid #e4e7ed;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel {
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 0;
  flex: 1;
  min-height: 0;
}
.panel-section {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.section-title-row {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
  flex-shrink: 0;
}
.section-title {
  font-size: 11px;
  font-weight: 600;
  color: #909399;
  text-transform: uppercase;
  flex: 1;
  letter-spacing: 0.03em;
}
.count-chip {
  font-size: 10px;
  color: #909399;
  background: #f0f2f5;
  border: 1px solid #e4e7ed;
  padding: 0 5px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}
.setting-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #606266;
}
.setting-label {
  white-space: nowrap;
  min-width: 60px;
}
.divider {
  height: 1px;
  background: #e4e7ed;
  margin: 2px 0;
  flex-shrink: 0;
}
.scroll-area {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.image-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  border-left: 3px solid transparent;
}
.image-item:hover {
  background: #f0f2f5;
}
.image-item.active {
  background: #ecf5ff;
  border-left-color: #409eff;
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-done {
  background: #67c23a;
}
.dot-pending {
  background: #f56c6c;
}
.img-info {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex: 1;
}
.img-name {
  font-size: 11px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-meta {
  font-size: 9px;
  color: #909399;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.class-item,
.ann-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.class-item:hover,
.ann-item:hover {
  background: #f0f2f5;
}
.class-item.active,
.ann-item.active {
  background: #ecf5ff;
}
.dot-color {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.empty-hint {
  font-size: 11px;
  color: #c0c4cc;
  text-align: center;
  padding: 8px 0;
}
.text-xs {
  font-size: 11px;
}
.text-gray-400 {
  color: #909399;
}
.font-mono {
  font-family: monospace;
}
.flex-1 {
  flex: 1;
}
.ann-footer {
  height: 36px;
  background: #fff;
  border-top: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  padding: 0 10px;
  gap: 6px;
  flex-shrink: 0;
}
.hint {
  flex: 1;
  font-size: 11px;
  color: #909399;
}
.unsaved-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #e6a23c;
  flex-shrink: 0;
}
.sep {
  width: 1px;
  height: 14px;
  background: #e4e7ed;
  flex-shrink: 0;
}
.nav-text {
  font-size: 11px;
  color: #606266;
  font-family: monospace;
  min-width: 50px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
</style>
