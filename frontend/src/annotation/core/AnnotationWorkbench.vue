<template>
  <div class="ann-workbench">
    <el-alert
      v-if="lockedByOther"
      type="warning"
      :closable="false"
      show-icon
      title="该图片已被其他用户锁定，当前为只读模式"
      class="ann-lock-banner"
    />
    <div class="ann-header">
      <div class="ann-title">
        <el-tag :type="taskTagType" size="small">{{ taskTypeLabel }}</el-tag>
        <span class="task-name">{{ store.task?.name }}</span>
      </div>
      <div class="header-right">
        <span v-if="props.collab" class="collab-online">
          在线 {{ props.collab.onlineUsers.value.length }}
        </span>
        <span v-if="isTextTask && docMeta" class="doc-meta">
          {{ docMeta.filename }} · {{ docMeta.character_count }} 字符
        </span>
        <span class="progress-text">{{ store.annotatedCount }}/{{ store.totalCount }}</span>
        <el-progress
          :percentage="store.progress"
          :stroke-width="6"
          :show-text="false"
          style="width: 100px"
        />
      </div>
    </div>
    <component :is="plugin.panel" v-if="plugin.panel" :ctx="panelCtx" class="ann-plugin-panel" />
    <div class="ann-body">
      <template v-if="isTextTask">
        <main class="ann-canvas-area text-ner-main">
          <component
            :is="plugin.renderer"
            :content="docContent"
            :entities="textEntities"
            :selected-id="store.selectedAnnotationId"
            :highlight-ids="activeRelationHighlightIds"
            :classes="textEntityClasses"
            :entity-color="textEntityColor"
            @select="onTextSelect"
            @span-click="onSpanClick"
          />
        </main>
        <TextNerPanel
          :entities="textEntities"
          :relations="textRelations"
          :entity-classes="textEntityClasses"
          :relation-classes="textRelationClasses"
          :selected-id="store.selectedAnnotationId"
          :active-relation-id="activeRelationId"
          @select-entity="store.selectedAnnotationId = $event"
          @new-relation="openRelationDialog"
          @delete-entity="deleteEntity"
        @delete-relation="deleteRelation"
        @click-relation="activeRelationId = $event"
      />
      </template>
      <template v-else-if="isAudioTask">
        <main class="ann-canvas-area audio-main">
          <component
            :is="plugin.renderer"
            :url="audioUrl"
            :segments="audioSegments"
            :classes="taskClasses"
            :selected-id="store.selectedAnnotationId"
            :color-for="audioSegmentColor"
            @create-region="onAudioCreateRegion"
            @update-region="onAudioUpdateRegion"
            @remove-region="onAudioRemoveRegion"
            @region-click="onAudioRegionClick"
            @ready="audioDuration = $event"
            @timeupdate="audioCurrentTime = $event"
          />
        </main>
        <AudioEventPanel
          :segments="audioSegments"
          :classes="taskClasses"
          :selected-id="store.selectedAnnotationId"
          @select="store.selectedAnnotationId = $event"
          @new="openAudioNewDialog"
          @edit="openAudioEditDialog"
          @delete="deleteAudioSegment"
        />
      </template>
      <template v-else-if="isTimeSeriesTask">
        <main class="ann-canvas-area time-series-main">
          <component
            :is="plugin.renderer"
            :data="seriesData"
            :segments="timeSeriesSegments"
            :classes="taskClasses"
            :selected-id="store.selectedAnnotationId"
            :color-for="timeSeriesSegmentColor"
            :range="seriesRange"
            @create-region="onTimeSeriesCreateRegion"
            @update-region="onTimeSeriesUpdateRegion"
            @region-click="onTimeSeriesRegionClick"
          />
        </main>
        <TimeSeriesPanel
          :segments="timeSeriesSegments"
          :classes="taskClasses"
          :selected-id="store.selectedAnnotationId"
          :value-columns="seriesMeta?.value_columns || []"
          :value-column="seriesValueColumn"
          :time-unit="seriesMeta?.time_unit || ''"
          :row-count="seriesData.length"
          :range-start="seriesMeta?.start_time ?? 0"
          :range-end="seriesMeta?.end_time ?? 0"
          @select="store.selectedAnnotationId = $event"
          @new="openTimeSeriesNewDialog"
          @edit="openTimeSeriesEditDialog"
          @delete="deleteTimeSeriesSegment"
          @change-column="onTimeSeriesChangeColumn"
        />
      </template>
      <template v-else-if="isVideoEventTask">
        <main class="ann-canvas-area video-event-main">
          <component
            :is="plugin.renderer"
            :duration="videoEventDuration"
            :segments="videoEventSegments"
            :classes="taskClasses"
            :selected-id="store.selectedAnnotationId"
            :color-for="videoSegmentColor"
            @create-region="onVideoEventCreateRegion"
            @update-region="onVideoEventUpdateRegion"
            @remove-region="onVideoEventRemoveRegion"
            @region-click="onVideoEventRegionClick"
          />
        </main>
        <VideoEventPanel
          :segments="videoEventSegments"
          :classes="taskClasses"
          :selected-id="store.selectedAnnotationId"
          @select="store.selectedAnnotationId = $event"
          @new="openVideoEventNewDialog"
          @edit="openVideoEventEditDialog"
          @delete="deleteVideoEventSegment"
        />
      </template>
      <template v-else>
      <AnnotationToolbar
        :tools="displayTools"
        :current-tool="currentToolForBar"
        @select="setTool"
        @undo="undo"
        @redo="redo"
        @delete="deleteSelected"
      />
      <main ref="canvasAreaRef" class="ann-canvas-area">
        <AnnotationCanvas
          ref="canvasRef"
          :img-url="imgUrl"
          :video-url="videoUrl"
          :media="isVideoTask ? 'video' : 'image'"
          :image-loaded="imageLoaded"
          :cursor="toolCursor"
          :canvas="canvas"
          @img-load="onImgLoad"
          @img-error="onImgError"
          @video-loaded="onVideoLoaded"
          @video-seeked="onVideoSeeked"
          @mousedown="onCanvasDown"
          @dblclick="onDblClick"
          @wheel="onWheel"
          @contextmenu.prevent="onRootContextmenu"
        >
          <DetectionTrackOverlay
            v-if="isVideoTask && trackShow"
            :paths="trackPaths"
            :cw="cw"
            :ch="ch"
          />
          <component
            :is="plugin.renderer"
            :annotations="displayAnnotations"
            :cw="cw"
            :ch="ch"
            :selected-id="store.selectedAnnotationId"
            :color="clsColor"
            :cls-name="clsName"
            :font-size="fontSize"
            :tag-h="tagH"
            :stroke="strokeW"
            :sel-stroke="selStrokeW"
            :pointer-none="isDrawing"
            @ann-down="onAnnDown"
            @handle-down="onHandleDown"
            @rotate-down="onRotateDown"
          />
          <component
            :is="activeTool?.preview"
            v-if="activeTool && activeTool.preview"
            :state="activeTool.state"
            :cw="cw"
            :ch="ch"
            :zoom="canvas.zoom.value"
            :font-size="fontSize"
          />
          <line
            v-if="crossVisible"
            :x1="crosshair.x * cw"
            :y1="0"
            :x2="crosshair.x * cw"
            :y2="ch"
            :stroke="currentClassColor"
            stroke-width="1"
            stroke-dasharray="3 3"
            class="cross-svg"
          />
          <line
            v-if="crossVisible"
            :x1="0"
            :y1="crosshair.y * ch"
            :x2="cw"
            :y2="crosshair.y * ch"
            :stroke="currentClassColor"
            stroke-width="1"
            stroke-dasharray="3 3"
            class="cross-svg"
          />
        </AnnotationCanvas>
        <div v-if="isVideoTask" class="track-bar">
          <el-switch v-model="trackShow" size="small" active-text="显示轨迹" />
          <el-select
            v-model="selectedTrackId"
            size="small"
            clearable
            placeholder="选择轨迹"
            class="track-select"
          >
            <el-option v-for="tid in trackOptions" :key="tid" :label="`轨迹 ${shortTrack(tid)}`" :value="tid" />
          </el-select>
          <el-button size="small" :disabled="!selectedTrackId" @click="goTrackFrame(-1)">上一帧</el-button>
          <el-button size="small" :disabled="!selectedTrackId" @click="goTrackFrame(1)">下一帧</el-button>
          <el-button size="small" :disabled="!selectedTrackId" @click="openInterpolateDialog">插值中间帧</el-button>
        </div>
        <div class="ann-label-layer">
          <div v-for="a in displayAnnotations" :key="a.id" class="ann-tag" :style="tagStyle(a)">
            {{ clsName(a) }}
          </div>
        </div>
        <div
          v-if="brushPopover.visible"
          class="brush-popover"
          :style="{ left: brushPopover.x + 'px', top: brushPopover.y + 'px' }"
          @click.stop
          @contextmenu.prevent
        >
          <div class="brush-popover-head">画笔大小</div>
          <div class="brush-popover-mode">
            <el-radio-group v-model="brushMode" size="small">
              <el-radio-button value="paint">涂抹</el-radio-button>
              <el-radio-button value="lasso">套索</el-radio-button>
            </el-radio-group>
          </div>
          <div class="brush-popover-body">
            <div
              class="brush-cursor-preview"
              :style="{
                width: Math.min(Math.max(brushSizeVal * (canvas.zoom.value || 1), 6), 120) + 'px',
                height: Math.min(Math.max(brushSizeVal * (canvas.zoom.value || 1), 6), 120) + 'px'
              }"
            />
            <el-slider
              :model-value="brushSizeVal"
              @input="setBrushSize"
              :min="1"
              :max="80"
              size="small"
              class="brush-popover-slider"
            />
            <span class="brush-popover-val">{{ brushSizeVal }}px</span>
          </div>
          <div class="brush-popover-tip">左键描画 · 按 [ ] 调整 · 右键再开</div>
        </div>
      </main>
      <AnnotationRightPanel
        :ann-settings="annSettings"
        :image-filter="imageFilter"
        :filtered-images="filteredImages"
        :images="store.images"
        :current-image-id="store.currentImage?.id ?? null"
        :task-classes="taskClasses"
        :selected-class-id="selectedClassId"
        :plugin-name="plugin.name"
        :classification-mode="config.classificationMode"
        :annotations="store.annotations"
        :selected-annotation-id="store.selectedAnnotationId"
        :cls-color="clsColor"
        :cls-name="clsName"
        :cls-count="clsCount"
        :is-cls-selected="isClsSelected"
        @update-image-filter="imageFilter = $event"
        @go-image="goToImage"
        @add-class="openAddClass"
        @edit-class="openEditClass"
        @select-class="selectedClassId = $event"
        @remove-class="removeClass"
        @change-class-color="changeClassColor"
        @toggle-classification="toggleClassification"
        @select-annotation="store.selectedAnnotationId = $event"
        @edit-annotation="openEditDialog"
        @contextmenu-annotation="openContextMenu"
        @delete-annotation="deleteById"
      />
      </template>
    </div>
    <VideoPlayerBar
      v-if="isVideoTask && !isVideoEventTask"
      :current-frame="currentFrame"
      :frame-count="frameCount"
      :duration="videoDuration"
      :current-time="videoCurrentTime"
      :fps="videoFps"
      :playing="videoPlaying"
      :zoom="canvas.zoom.value"
      @prev="goToFrame(currentFrame - 1)"
      @next="goToFrame(currentFrame + 1)"
      @seek="onSliderSeek"
      @toggle-play="togglePlay"
      @zoom-in="zoomStep(1.2)"
      @zoom-out="zoomStep(1 / 1.2)"
    />
    <AnnotationHistoryBar
      :has-current-image="!!store.currentImage || isVideoTask || isAudioTask || isTextTask || isTimeSeriesTask"
      :current-index="store.currentImageIndex"
      :total="store.images.length"
      :unsaved="store.unsaved"
      :cursor-x="cursorPos.x"
      :cursor-y="cursorPos.y"
      :zoom="canvas.zoom.value"
      :cw="canvas.cw.value"
      :hint="hintText"
      :can-prev="store.currentImageIndex > 0"
      :can-next="store.currentImageIndex < store.images.length - 1"
      :locked="lockedByOther"
      :show-coordinate="!isTextTask && !isAudioTask && !isTimeSeriesTask && !isVideoEventTask"
      @save="saveAnn"
      @prev="prevImg"
      @next="nextImg"
      @history="openHistory"
      @help="showHelpModal = true"
    />

    <div
      v-if="annMenu.visible"
      class="ctx-backdrop"
      @click="closeMenu"
      @contextmenu.prevent="closeMenu"
    />
    <div
      v-if="annMenu.visible"
      class="ctx-menu"
      :style="{ left: annMenu.x + 'px', top: annMenu.y + 'px' }"
    >
      <div class="ctx-item" @click.stop="menuEdit">
        <el-icon :size="14"><Edit /></el-icon>
        <span>编辑标注</span>
      </div>
      <div class="ctx-item" @click.stop="menuCopy">
        <el-icon :size="14"><CopyDocument /></el-icon>
        <span>复制标注</span>
      </div>
      <div class="ctx-item" @click.stop="menuLayerTop">
        <el-icon :size="14"><ArrowUp /></el-icon>
        <span>置顶</span>
      </div>
      <div class="ctx-item" @click.stop="menuLayerBottom">
        <el-icon :size="14"><ArrowDown /></el-icon>
        <span>置底</span>
      </div>
      <div
        v-if="isVideoTask && annMenu.ann?.type === 'AxisAlignedBox'"
        class="ctx-item"
        @click.stop="menuTrack"
      >
        <el-icon :size="14"><Connection /></el-icon>
        <span>关联到轨迹</span>
      </div>
      <div
        v-if="isVideoTask && annMenu.ann?.track_id"
        class="ctx-item"
        @click.stop="menuClearTrack"
      >
        <el-icon :size="14"><Close /></el-icon>
        <span>取消轨迹关联</span>
      </div>
      <div class="ctx-item ctx-danger" @click.stop="menuDelete">
        <el-icon :size="14"><Delete /></el-icon>
        <span>删除标注</span>
      </div>
    </div>

    <div
      v-if="editAnnVisible"
      class="edit-bubble"
      :style="{ left: editPos.x + 'px', top: editPos.y + 'px' }"
      @click.stop
      @contextmenu.prevent
    >
      <div class="bubble-arrow" />
      <div class="bubble-head">
        <span>编辑标注</span>
        <el-icon :size="14" class="bubble-close" @click="editAnnVisible = false"><Close /></el-icon>
      </div>
      <el-form label-width="72px">
        <el-form-item label="类别">
          <el-select
            v-model="editForm.class_id"
            size="small"
            style="width: 100%"
            @change="editClassChange"
          >
            <el-option v-for="c in taskClasses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editForm.ann?.type === 'Ocr'" label="OCR文本">
          <el-input
            v-model="editForm.text"
            size="small"
            placeholder="编辑OCR文本"
            @change="editTextChange"
          />
        </el-form-item>
        <el-form-item v-if="editForm.ann?.type === 'Keypoint'" label="关键点">
          <div style="width: 100%">
            <div
              v-for="(kp, i) in editForm.keypoints"
              :key="i"
              style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px"
            >
              <el-input
                v-model="kp.name"
                size="small"
                placeholder="名称"
                style="flex: 1"
                @change="editKpChange"
              />
              <el-select
                v-model="kp.visibility"
                size="small"
                style="width: 110px"
                @change="editKpChange"
              >
                <el-option v-for="v in KP_VISIBILITY" :key="v" :label="v" :value="v" />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <div class="bubble-footer">
        <el-button size="small" @click="editAnnVisible = false">关闭</el-button>
        <el-button size="small" type="danger" @click="editDelete">删除该标注</el-button>
      </div>
    </div>
    <el-dialog
      v-model="showClassModal"
      :title="editingClassId !== null ? '编辑类别' : '添加类别'"
      width="400px"
      append-to-body
    >
      <el-form :model="clsForm" label-width="60px">
        <el-form-item label="名称">
          <el-input v-model="clsForm.name" placeholder="类别名称" />
        </el-form-item>
        <el-form-item label="颜色">
          <div style="width: 100%">
            <div class="preset-palette">
              <span
                v-for="col in PRESET_COLORS"
                :key="col"
                class="preset-dot"
                :class="{ active: clsForm.color === col }"
                :style="{ background: col }"
                @click="clsForm.color = col"
              />
            </div>
            <el-color-picker v-model="clsForm.color" size="small" class="custom-color" />
          </div>
        </el-form-item>
        <el-form-item v-if="plugin.name === 'keypoint'" label="关键点">
          <div style="width: 100%">
            <div
              v-for="(kp, i) in clsForm.kpNames"
              :key="i"
              style="display: flex; gap: 6px; align-items: center; margin-bottom: 4px"
            >
              <el-input v-model="clsForm.kpNames[i]" size="small" placeholder="关键点名称" />
              <el-color-picker v-model="clsForm.kpColors[i]" size="small" />
              <el-button
                text
                size="small"
                type="danger"
                @click="
                  clsForm.kpNames.splice(i, 1);
                  clsForm.kpColors.splice(i, 1);
                "
              >
                ×
              </el-button>
            </div>
            <el-button
              size="small"
              @click="
                clsForm.kpNames.push('');
                clsForm.kpColors.push('#409eff');
              "
            >
              + 关键点
            </el-button>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showClassModal = false">取消</el-button>
        <el-button type="primary" @click="addClass">
          {{ editingClassId !== null ? "保存" : "添加" }}
        </el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="ocrInputVisible" title="输入 OCR 文本" width="380px" append-to-body>
      <el-input v-model="ocrInput" placeholder="OCR 文本" @keydown.enter="confirmOcr" />
      <template #footer>
        <el-button @click="cancelOcr">取消</el-button>
        <el-button type="primary" @click="confirmOcr">确定</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="showHelpModal" title="快捷键" width="420px" append-to-body>
      <div class="shortcut-grid">
        <div v-for="s in shortcutList" :key="s.keys" class="shortcut-row">
          <span class="shortcut-keys">{{ s.keys }}</span>
          <span class="shortcut-desc">{{ s.desc }}</span>
        </div>
      </div>
    </el-dialog>

    <!-- 视频目标跟踪：关联到轨迹 -->
    <el-dialog v-model="trackDialogVisible" title="关联到轨迹" width="460px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="关联方式">
          <el-radio-group v-model="trackDialogMode">
            <el-radio value="new">新建轨迹</el-radio>
            <el-radio value="existing">选择已有轨迹</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="trackDialogMode === 'existing'" label="轨迹">
          <el-select
            v-model="trackDialogExisting"
            size="small"
            style="width: 100%"
            placeholder="选择已有轨迹"
          >
            <el-option v-for="tid in trackOptions" :key="tid" :label="`轨迹 ${shortTrack(tid)}`" :value="tid" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="trackDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmTrack">确定</el-button>
      </template>
    </el-dialog>

    <!-- 视频目标跟踪：关键帧线性插值 -->
    <el-dialog v-model="interpolateDialogVisible" title="插值中间帧" width="460px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="轨迹">
          <el-tag size="small">轨迹 {{ shortTrack(selectedTrackId) }}</el-tag>
        </el-form-item>
        <el-form-item label="关键帧 A">
          <el-select v-model="interpolateFrameA" size="small" style="width: 100%" placeholder="选择关键帧 A">
            <el-option v-for="f in interpolateFrameOptions" :key="f" :label="`第 ${f} 帧`" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键帧 B">
          <el-select v-model="interpolateFrameB" size="small" style="width: 100%" placeholder="选择关键帧 B">
            <el-option v-for="f in interpolateFrameOptions" :key="f" :label="`第 ${f} 帧`" :value="f" />
          </el-select>
        </el-form-item>
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="将在两个关键帧之间为该轨迹插值生成中间帧框（同轨迹覆盖、其它轨迹保留，关键帧不动）"
        />
      </el-form>
      <template #footer>
        <el-button @click="interpolateDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="interpolateLoading" @click="confirmInterpolate">插值</el-button>
      </template>
    </el-dialog>

    <!-- 文本 NER：实体类型选择 -->
    <el-dialog v-model="entityDialogVisible" title="选择实体类型" width="500px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="实体类型">
          <el-select v-model="entityLabelId" size="small" style="width: 100%">
            <el-option
              v-for="c in textEntityClasses"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="entityDialogVisible = false; selRange = null">取消</el-button>
        <el-button type="primary" @click="confirmEntity">确定</el-button>
      </template>
    </el-dialog>

    <!-- 文本 NER：编辑实体 -->
    <el-dialog v-model="editSpanVisible" title="编辑实体" width="500px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="实体类型">
          <el-select v-model="editSpanLabelId" size="small" style="width: 100%">
            <el-option
              v-for="c in textEntityClasses"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editSpanVisible = false">取消</el-button>
        <el-button type="danger" @click="deleteEditSpan">删除</el-button>
        <el-button type="primary" @click="saveEditSpan">保存</el-button>
      </template>
    </el-dialog>

    <!-- 文本 NER：新建关系 -->
    <el-dialog v-model="relationDialogVisible" title="新建关系" width="520px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="起点实体">
          <el-select
            v-model="relationForm.from"
            size="small"
            style="width: 100%"
            placeholder="选择起点实体"
            @change="onRelationFromChange"
          >
            <el-option
              v-for="e in textEntities"
              :key="e.id"
              :label="`${e.text}（${entityLabelName(e)}）`"
              :value="e.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="终点实体">
          <el-select v-model="relationForm.to" size="small" style="width: 100%" placeholder="选择终点实体">
            <el-option
              v-for="e in relationToCandidates"
              :key="e.id"
              :label="`${e.text}（${entityLabelName(e)}）`"
              :value="e.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="relationForm.relation_type" size="small" style="width: 100%" placeholder="选择关系类型">
            <el-option
              v-for="r in textRelationClasses"
              :key="r.id"
              :label="r.name"
              :value="r.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="relationDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmRelation">创建关系</el-button>
      </template>
    </el-dialog>

    <!-- 音频事件：创建/编辑片段 -->
    <el-dialog
      v-model="audioDialogVisible"
      :title="audioDialogMode === 'create' ? '新建事件片段' : '编辑事件片段'"
      width="500px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="开始时间">
          <el-input-number
            v-model="audioDialogRange.start"
            :min="0"
            :max="audioDuration"
            :step="0.1"
            :precision="2"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-input-number
            v-model="audioDialogRange.end"
            :min="0"
            :max="audioDuration"
            :step="0.1"
            :precision="2"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="事件类别">
          <el-select v-model="audioDialogLabelId" size="small" style="width: 100%" placeholder="选择事件类别">
            <el-option v-for="c in taskClasses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="audioDialogVisible = false">取消</el-button>
        <el-button
          v-if="audioDialogMode === 'edit'"
          type="danger"
          @click="audioDialogVisible = false; deleteAudioSegment(audioDialogId)"
        >
          删除
        </el-button>
        <el-button v-if="audioDialogMode === 'edit'" type="primary" @click="confirmAudioDialog">保存</el-button>
        <el-button v-else type="primary" @click="confirmAudioDialog">确定</el-button>
      </template>
    </el-dialog>

    <!-- 视频事件：创建/编辑片段 -->
    <el-dialog
      v-model="videoEventDialogVisible"
      :title="videoEventDialogMode === 'create' ? '新建事件片段' : '编辑事件片段'"
      width="500px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="开始时间">
          <el-input-number
            v-model="videoEventDialogRange.start"
            :min="0"
            :max="videoEventDuration"
            :step="0.1"
            :precision="2"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-input-number
            v-model="videoEventDialogRange.end"
            :min="0"
            :max="videoEventDuration"
            :step="0.1"
            :precision="2"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="事件类别">
          <el-select v-model="videoEventDialogLabelId" size="small" style="width: 100%" placeholder="选择事件类别">
            <el-option v-for="c in taskClasses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="videoEventDialogVisible = false">取消</el-button>
        <el-button
          v-if="videoEventDialogMode === 'edit'"
          type="danger"
          @click="videoEventDialogVisible = false; deleteVideoEventSegment(videoEventDialogId)"
        >
          删除
        </el-button>
        <el-button v-if="videoEventDialogMode === 'edit'" type="primary" @click="confirmVideoEventDialog">保存</el-button>
        <el-button v-else type="primary" @click="confirmVideoEventDialog">确定</el-button>
      </template>
    </el-dialog>

    <!-- 时间序列事件：创建/编辑区间 -->
    <el-dialog
      v-model="tsDialogVisible"
      :title="tsDialogMode === 'create' ? '新建事件区间' : '编辑事件区间'"
      width="500px"
      append-to-body
    >
      <el-form label-width="80px">
        <el-form-item label="开始时间">
          <el-input-number
            v-model="tsDialogRange.start"
            :min="tsDialogRangeMin"
            :max="tsDialogRangeMax"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-input-number
            v-model="tsDialogRange.end"
            :min="tsDialogRangeMin"
            :max="tsDialogRangeMax"
            size="small"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="事件类别">
          <el-select v-model="tsDialogLabelId" size="small" style="width: 100%" placeholder="选择事件类别">
            <el-option v-for="c in taskClasses" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="tsDialogVisible = false">取消</el-button>
        <el-button
          v-if="tsDialogMode === 'edit'"
          type="danger"
          @click="tsDialogVisible = false; deleteTimeSeriesSegment(tsDialogId)"
        >
          删除
        </el-button>
        <el-button v-if="tsDialogMode === 'edit'" type="primary" @click="confirmTimeSeriesDialog">保存</el-button>
        <el-button v-else type="primary" @click="confirmTimeSeriesDialog">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  shallowRef,
  triggerRef,
  reactive,
  unref,
  onMounted,
  onBeforeUnmount,
  watch,
} from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import { useUserStore } from "@/store";
import {
  Select,
  FullScreen,
  ZoomIn,
  Close,
  Edit,
  CopyDocument,
  ArrowUp,
  ArrowDown,
  Delete,
  Connection,
} from "@element-plus/icons-vue";
import AnnotationCanvas from "./AnnotationCanvas.vue";
import AnnotationHistoryBar from "./AnnotationHistoryBar.vue";
import AnnotationToolbar from "./AnnotationToolbar.vue";
import VideoPlayerBar from "./VideoPlayerBar.vue";
import AnnotationRightPanel from "./AnnotationRightPanel.vue";
import DetectionTrackOverlay from "../tasks/detection/DetectionTrackOverlay.vue";
import {
  collectTrackIds,
  newTrackId,
  nearestTrackFrame,
  trackPathFromFrames,
  trackColor,
  findBoxByTrack,
} from "../tasks/detection/track";
import { interpolateBoxes } from "../tasks/detection/interpolate";
import { useAnnotationCanvas } from "./useAnnotationCanvas";
import { useAnnotationStore } from "./useAnnotationStore";
import type { Annotation, AnnotationTaskPlugin, PluginPanelContext } from "./types";
import type { WorkbenchApi, WorkbenchConfig, CollabAdapter } from "./annotationTypes";
import { frameIndexToTime, timeToFrameIndex } from "./workbenchFrame";
import {
  getVideoList,
  getVideoDetail,
  getVideoPlayUrl,
  lockVideo,
  unlockVideo,
  saveVideoAnnotations,
  loadVideoAnnotations,
  interpolateVideoFrames,
} from "@/api/module_annotation/video";
import {
  getDocumentList,
  getDocumentDetail,
  getDocumentContent,
  lockDocument,
  unlockDocument,
  saveTextAnnotations,
  loadTextAnnotations,
  type TextDocumentMeta,
  type EntitySpan,
  type Relation,
} from "@/api/module_annotation/document";
import {
  createEntitySpan,
  findOverlappingSpan,
  sameSentence,
} from "../tasks/textNer/useTextNerTool";
import TextNerPanel from "../tasks/textNer/TextNerPanel.vue";
import {
  getAudioList,
  getAudioDetail,
  getAudioContentUrl,
  lockAudio,
  unlockAudio,
  saveAudioAnnotations,
  loadAudioAnnotations,
  type AudioSegment,
} from "@/api/module_annotation/audio";
import {
  createAudioSegment,
  hasAudioOverlap,
  hasOverlapExcluding,
  findOverlappingSegment,
  segmentToRange,
  clampAudioRange,
} from "../tasks/audioEvent/useAudioEventTool";
import AudioEventPanel from "../tasks/audioEvent/AudioEventPanel.vue";
import {
  getTimeSeriesList,
  getTimeSeriesDetail,
  getTimeSeriesContent,
  lockTimeSeries,
  unlockTimeSeries,
  saveTimeSeriesAnnotations,
  loadTimeSeriesAnnotations,
  type TimeSeriesMeta,
  type TimeSeriesSegment,
} from "@/api/module_annotation/timeSeries";
import {
  createTimeSeriesSegment,
  hasTimeSeriesOverlap,
  hasOverlapExcluding as hasTsOverlapExcluding,
  findOverlappingSegment as findTsOverlappingSegment,
  segmentToRange as tsSegmentToRange,
  clampTimeRange,
  formatSeriesTime,
} from "../tasks/timeSeriesEvent/useTimeSeriesEventTool";
import { parseSeriesCsv } from "../tasks/timeSeriesEvent/parseTimeSeriesCsv";
import TimeSeriesPanel from "../tasks/timeSeriesEvent/TimeSeriesPanel.vue";
import {
  saveVideoEventAnnotations,
  loadVideoEventAnnotations,
  type VideoSegment,
} from "@/api/module_annotation/videoEvent";
import {
  createVideoSegment,
  hasVideoEventOverlap,
  hasOverlapExcluding as hasVideoOverlapExcluding,
  findOverlappingSegment as findVideoOverlappingSegment,
  segmentToRange as videoSegmentToRange,
  clampVideoRange,
} from "../tasks/videoEvent/useVideoEventTool";
import VideoEventPanel from "../tasks/videoEvent/VideoEventPanel.vue";

const props = defineProps<{
  plugins: AnnotationTaskPlugin[];
  api: WorkbenchApi;
  config: WorkbenchConfig;
  taskId: number;
  collab?: CollabAdapter;
}>();

const store = useAnnotationStore();
const emit = defineEmits<{ (e: "open-history"): void }>();
const canvasRef = ref<InstanceType<typeof AnnotationCanvas> | null>(null);
const canvas = useAnnotationCanvas();
const currentTool = ref("select");
// 画笔子工具（涂抹/套索），若插件工具未显式提供 subTools 则回退到该默认项
const BRUSH_SUBS = [
  { value: "paint", label: "涂抹" },
  { value: "lasso", label: "套索" },
];
// 需要预先建类别才能标注的任务类型（画布上按 taskClasses 分类标注）。
// 文本/视频事件/音频/时间序列类任务的类别在其专用面板管理，不在此列。
const TASKS_REQUIRE_CLASS = new Set([
  "detection",
  "rotated_detection",
  "segmentation",
  "semantic_segmentation",
  "panoptic_segmentation",
  "polyline",
  "cuboid",
  "keypoint",
  "ocr",
  "classification",
]);
const imageLoaded = ref(false);
const lockedByOther = ref(false);
const lockedByUser = ref<any>(null);
const imgUrl = ref("");
// ==== 视频帧级标注状态 ====
const videoUrl = ref("");
const videoId = ref<number | null>(null);
const currentFrame = ref(0);
const videoFps = ref(1);
const frameCount = ref(0);
const videoDuration = ref(0);
const videoPlaying = ref(false);
const videoCurrentTime = ref(0);
// 待定位的目标帧：用于在 seeked 回调中过滤过期 seek，保证加载的标注与最终定位帧一致
let pendingSeekFrame = -1;
// ==== 视频目标跟踪（track_id 关联 + 轨迹显示/导航）====
const trackShow = ref(false); // 显示轨迹开关
const selectedTrackId = ref(""); // 当前选中的轨迹（用于高亮与按轨迹导航）
// 已访问帧的标注缓存：帧号 -> 该帧 AxisAlignedBox[]，供轨迹跨帧连线与按轨迹导航使用（局部刷新，不整表刷新）
const frameCache = new Map<number, Annotation[]>();
// 轨迹/插值缓存已访问帧标注，长会话会线性增长；超出上限时淘汰最早缓存帧，避免内存无限膨胀。
const MAX_FRAME_CACHE = 500;
const trackTick = ref(0); // 轨迹数据变更计数器：缓存更新/关联轨迹后自增，强制轨迹层重算
function bumpTrack() {
  trackTick.value++;
}
const selectedClassId = ref<number | null>(null);
const crosshair = reactive({ x: 0, y: 0 });

const cursorPos = reactive({ x: 0, y: 0 });
const imageFilter = ref<"all" | "annotated" | "unannotated">("all");
const filteredImages = computed(() => {
  if (imageFilter.value === "all") return store.images;
  return store.images.filter(
    (i) => (imageFilter.value === "annotated") === (i.status === "annotated")
  );
});
const showHelpModal = ref(false);
const spaceHeld = ref(false);
const shortcutList = computed(() => {
  const base = [
    { keys: "1-7 / s b r p k o c", desc: "切换标注工具" },
    { keys: "Ctrl+S", desc: "保存当前图" },
    { keys: "Ctrl+Z / Ctrl+Y", desc: "撤销 / 重做" },
    { keys: "Ctrl+C / Ctrl+V", desc: "复制 / 粘贴标注" },
    { keys: "Delete / Backspace", desc: "删除选中标注" },
    { keys: "Esc", desc: "取消绘制" },
    { keys: "←→ / a d", desc: "上一张 / 下一张" },
  ];
  const extra: any[] = [];
  if (plugin.value.name === "keypoint")
    extra.push({ keys: "0/1/2", desc: "关键点可见性 Hidden/Occluded/Visible" });
  if (plugin.value.name === "ocr") extra.push({ keys: "t", desc: "矩形 / 四边形模式切换" });
  return [...base, ...extra];
});
const fontSize = ref(6);
const strokeW = ref(1.5);
const selStrokeW = ref(2);
const tagH = computed(() => Math.max(8, fontSize.value + 6));
const settingsKey = "annotation-workbench-settings";
function loadSettings(): any {
  try {
    return JSON.parse(localStorage.getItem(settingsKey) || "{}");
  } catch {
    return {};
  }
}
const annSettings = reactive({
  labelFontSize: 6,
  strokeWidth: 1.5,
  selStrokeWidth: 2,
  ...loadSettings(),
});
fontSize.value = annSettings.labelFontSize;
strokeW.value = annSettings.strokeWidth;
selStrokeW.value = annSettings.selStrokeWidth;
watch(
  annSettings,
  () => {
    fontSize.value = annSettings.labelFontSize;
    strokeW.value = annSettings.strokeWidth;
    selStrokeW.value = annSettings.selStrokeWidth;
    localStorage.setItem(settingsKey, JSON.stringify(annSettings));
  },
  { deep: true }
);
// 协作：锁定被拒提示 + 远程标注同步刷新（顶层 watch，随组件卸载自动清理）
watch(
  () => props.collab?.lockDeniedTick?.value ?? 0,
  () => {
    if (props.collab?.lockDeniedTick?.value) ElMessage.warning("保存被拒绝：图片已被其他用户锁定");
  }
);
watch(
  () => props.collab?.remoteAnnotationTick?.value ?? 0,
  () => {
    if (props.collab?.remoteAnnotationTick?.value && store.currentImageId) {
      loadCurrentImage(store.currentImageId).catch(() => {});
    }
  }
);

const baseTools = [
  { name: "select", label: "选择", icon: Select },
  { name: "pan", label: "平移", icon: FullScreen },
  { name: "zoom", label: "缩放", icon: ZoomIn },
];
const plugin = computed(
  () => props.plugins.find((p) => p.name === (store.task?.task_type || "")) ?? props.plugins[0]
);
const isVideoTask = computed(() => plugin.value.media === "video");
// video_event 与 video_detection 同为 video 媒体，但 video_event 走时间轴而非帧画布；用插件名区分。
const isVideoEventTask = computed(() => plugin.value.name === "video_event");
const isTextTask = computed(() => plugin.value.media === "text");
const isAudioTask = computed(() => plugin.value.media === "audio");
const isTimeSeriesTask = computed(() => plugin.value.media === "time_series");
// ==== 音频事件标注状态 ====
const audioId = ref<number | null>(null);
const audioUrl = ref("");
const audioDuration = ref(0);
const audioCurrentTime = ref(0);
// ==== 视频事件标注状态 ====
const videoEventId = ref<number | null>(null);
const videoEventDuration = ref(0);
// ==== 时间序列事件标注状态 ====
const timeSeriesId = ref<number | null>(null);
const seriesMeta = ref<TimeSeriesMeta | null>(null);
const seriesData = ref<{ time: number; value: number }[]>([]);
const seriesValueColumn = ref("");
const seriesCsvRaw = ref("");
const seriesRange = computed(() => {
  const m = seriesMeta.value;
  if (!m) return undefined;
  return { start: m.start_time, end: m.end_time };
});
// ==== 文本 NER 文档状态 ====
const documentId = ref<number | null>(null);
const docContent = ref("");
const docMeta = ref<TextDocumentMeta | null>(null);
let lockedDocumentId: number | null = null;
const displayTools = computed(() => {
  const out: any[] = [...baseTools];
  const tm = plugin.value.toolMap as any;
  for (const t of plugin.value.tools) {
    const st = tm?.[t.name]?.state;
    const subs = st?.subTools ?? (st?.setBrushMode ? BRUSH_SUBS : null);
    if (subs && subs.length) {
      for (const s of subs) {
        out.push({
          ...t,
          name: t.name + "-" + s.value,
          label: s.label,
          title: s.label,
          _tool: t.name,
          _mode: s.value,
        });
      }
    } else {
      out.push(t);
    }
  }
  return out;
});
const taskTypeLabel = computed(() => plugin.value.label);
const taskTagType = computed(() => (plugin.value.color as any) || "primary");
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const dw = computed(() => canvas.dw.value);
const dh = computed(() => canvas.dh.value);
const activeTool = computed(
  () =>
    plugin.value.toolMap?.[currentTool.value] ??
    (currentTool.value === plugin.value.tool?.name ? plugin.value.tool : undefined)
);
const isDrawing = computed(() => !!activeTool.value);
const isBrushTool = computed(() => currentTool.value === "brush");
const currentToolForBar = computed(() => {
  const st = activeTool.value?.state;
  const subs: any[] = st?.subTools ?? (st?.setBrushMode ? BRUSH_SUBS : []);
  const mode = unref(st?.mode);
  // 始终返回带模式后缀的按钮名（如 brush-paint / brush-lasso），
  // 与 displayTools 生成的按钮 name 一致，保证对应的子工具按钮正确高亮。
  const found = mode && subs.find((s) => s.value === mode);
  if (found) return currentTool.value + "-" + mode;
  return currentTool.value;
});

// 当前高亮/选中类别的颜色（用于十字线等）
const currentClassColor = computed(() =>
  selectedClassId.value != null
    ? taskClasses.value.find((c) => c.id === selectedClassId.value)?.color ?? "#909399"
    : "#909399"
);

// 画笔工具的笔刷粗细（仅画笔工具 state 提供 brushSize 时显示控件）
const brushSizeVal = computed(() => {
  const bs = activeTool.value?.state?.brushSize;
  return bs ? unref(bs) : 8;
});
function setBrushSize(v: number | number[]) {
  const bs = activeTool.value?.state?.brushSize;
  const val = Array.isArray(v) ? v[0] : v;
  if (!bs) return;
  bs.value = Math.max(1, Math.min(120, Math.round(val)));
}
const brushMode = computed({
  get: () => (unref(activeTool.value?.state?.mode) as "paint" | "lasso") ?? "paint",
  set: (v: "paint" | "lasso") => activeTool.value?.state?.setBrushMode?.(v),
});
const canvasAreaRef = ref<HTMLElement | null>(null);
const brushPopover = reactive({ visible: false, x: 0, y: 0 });
function openBrushPopover(e: MouseEvent) {
  const area = canvasAreaRef.value;
  if (!area) return;
  const r = area.getBoundingClientRect();
  const x = Math.max(4, Math.min(e.clientX - r.left + 8, r.width - 210));
  const y = Math.max(4, Math.min(e.clientY - r.top + 8, r.height - 150));
  brushPopover.x = x;
  brushPopover.y = y;
  brushPopover.visible = true;
}
function closeBrushPopover() {
  brushPopover.visible = false;
}
const toolCursor = computed(() => {
  if (spaceHeld.value) return "grab";
  if (isBrushTool.value) return BRUSH_CURSOR;
  return isDrawing.value ? "crosshair" : "default";
});
const crossVisible = computed(() => isDrawing.value && !isBrushTool.value);
// 画笔光标：ri-brush-fill 白色实心版（data URI），hotspot 在笔身
const BRUSH_CURSOR =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23ffffff' stroke='%23555555' stroke-width='1' d='M13.2886 6.21301L18.2278 2.37142C18.6259 2.0618 19.1922 2.09706 19.5488 2.45367L22.543 5.44787C22.8997 5.80448 22.9349 6.37082 22.6253 6.76891L18.7847 11.7068C19.0778 12.8951 19.0836 14.1721 18.7444 15.4379C17.8463 18.7897 14.8142 20.9986 11.5016 20.9986C8 20.9986 3.5 19.4967 1 17.9967C4.97978 14.9967 4.04722 13.1865 4.5 11.4967C5.55843 7.54658 9.34224 5.23935 13.2886 6.21301ZM16.7015 8.09161C16.7673 8.15506 16.8319 8.21964 16.8952 8.28533L18.0297 9.41984L20.5046 6.23786L18.7589 4.4921L15.5769 6.96698L16.7015 8.09161Z'/%3E%3C/svg%3E\") 10 14, crosshair";
const hintText = computed(() => {
  const t = displayTools.value.find((x) => (x as any)?._tool === currentTool.value);
  // 关键点：动态显示「放置进度 + 名称」或「矩形绑定」提示
  if (currentTool.value === "keypoint") {
    const kpState = activeTool.value?.state as any;
    if (kpState?.boxMode?.value)
      return "关键点已放满，请拖出矩形框绑定为对象（完成）";
    const n = kpState?.pending?.value?.length ?? 0;
    const names: string[] =
      taskClasses.value.find((c: any) => c.id === selectedClassId.value)?.keypoint_names ?? [];
    if (names.length)
      return `请逐点放置关键点（${n}/${names.length}）：${names.join("、")}`;
  }
  // 3D 目标检测：动态绘制步骤提示
  if (currentTool.value === "cuboid") {
    const st = activeTool.value?.state as any;
    const step = st?.step?.value ?? 0;
    if (step === 1) return "已放置第 1 个角点，点击放置第 2 个角点（底面一条边）";
    if (step === 2) return "已放置一条边，点击放置第 3 个角点确定底面平行四边形";
    if (step === 3) return "底面已确定，向上移动鼠标拖出高度，点击生成 3D 框";
    return "第 1 步：点击放置底面角点";
  }
  return (t as any)?.title || (t as any)?.tip || "";
});

let panState: { startX: number; startY: number; px: number; py: number } | null = null;
let dragState: {
  type:
    | "move"
    | "resize"
    | "rotate"
    | "poly-vertex"
    | "kp-vertex"
    | "kp-move"
    | "kp-resize"
    | "cuboid-height";
  ann: Annotation;
  handle: string;
  startX: number;
  startY: number;
  orig: Annotation;
} | null = null;
const draftAnn = shallowRef<Annotation | null>(null);
const displayAnnotations = computed<Annotation[]>(() => {
  const d = draftAnn.value;
  const list = d ? store.annotations.map((a) => (a.id === d.id ? d : a)) : store.annotations;
  // 分类无几何，标签由 ClassificationCanvas 渲染，跳过 HTML 标签层避免左上角重复
  return list.filter((a) => a.type !== "Classification");
});
function draftOf(ann: Annotation): Annotation {
  const d = JSON.parse(JSON.stringify(ann));
  draftAnn.value = d;
  return d;
}
let loadImgToken = 0;
let fittedForImage = false;
const FULL_CACHE_MAX = 20;
const fullUrlCache = new Map<number, string>();
function addToCache(id: number, url: string) {
  if (fullUrlCache.has(id)) fullUrlCache.delete(id);
  fullUrlCache.set(id, url);
  if (fullUrlCache.size > FULL_CACHE_MAX) {
    const first = fullUrlCache.keys().next().value;
    if (first !== undefined) fullUrlCache.delete(first);
  }
}
function warmFull(id: number, url: string) {
  const img = new Image();
  img.onload = () => {
    if (img.decode) img.decode().catch(() => {});
  };
  img.onerror = () => {};
  img.src = url;
}
function preloadFull(fullUrl: string, imageId: number, myToken: number) {
  const img = new Image();
  const cache = () => {
    if (myToken !== loadImgToken) return;
    addToCache(imageId, fullUrl);
  };
  const swap = () => {
    if (myToken !== loadImgToken) return;
    if (imgUrl.value !== fullUrl) imgUrl.value = fullUrl;
  };
  img.onload = () => {
    if (!img.decode) {
      cache();
      swap();
      return;
    }
    img.decode().then(cache).then(swap).catch(cache);
  };
  img.onerror = () => {};
  img.src = fullUrl;
}
function prefetchNeighbors() {
  const idx = store.currentImageIndex;
  const targets: number[] = [];
  if (idx > 0) targets.push(store.images[idx - 1]?.id);
  if (idx < store.images.length - 1) targets.push(store.images[idx + 1]?.id);
  for (const id of targets) {
    if (!id) continue;
    if (fullUrlCache.has(id)) {
      warmFull(id, fullUrlCache.get(id)!);
      continue;
    }
    props.api
      .getPresignedUrl(id, store.taskId)
      .then((r: any) => {
        const u = r?.data?.data?.url;
        if (u) {
          addToCache(id, u);
          warmFull(id, u);
        }
      })
      .catch(() => {});
  }
}
let lockRenewTimer: number | null = null;
let lockedImageId: number | null = null;
let lockedVideoId: number | null = null;
let lockedAudioId: number | null = null;
let lockedTimeSeriesId: number | null = null;
let unmounted = false;
let _resizeObserver: ResizeObserver | null = null;

function clearLockRenewal() {
  if (lockRenewTimer) {
    clearInterval(lockRenewTimer);
    lockRenewTimer = null;
  }
}
function unlockCurrent() {
  clearLockRenewal();
  if (lockedImageId) {
    props.api.unlockImage(lockedImageId, store.taskId).catch(() => {});
    lockedImageId = null;
  }
  if (lockedVideoId) {
    unlockVideo(lockedVideoId).catch(() => {});
    lockedVideoId = null;
  }
  if (lockedAudioId) {
    unlockAudio(lockedAudioId).catch(() => {});
    lockedAudioId = null;
  }
  if (lockedTimeSeriesId) {
    unlockTimeSeries(lockedTimeSeriesId).catch(() => {});
    lockedTimeSeriesId = null;
  }
  if (lockedDocumentId) {
    unlockDocument(lockedDocumentId).catch(() => {});
    lockedDocumentId = null;
  }
}
function lockCurrentVideo(id: number) {
  lockVideo(id)
    .then((lr: any) => {
      const d = lr?.data?.data;
      if (d?.locked) {
        lockedByOther.value = true;
        lockedByUser.value = d.locked_by ?? null;
      } else {
        lockedByOther.value = false;
        lockedByUser.value = null;
      }
      lockedVideoId = id;
      clearLockRenewal();
      lockRenewTimer = window.setInterval(() => {
        lockVideo(id).catch(() => {});
      }, 180000);
    })
    .catch(() => {});
}

// ==== 音频事件：锁定（按音频整体加锁，定期续期）====
function lockCurrentAudio(id: number) {
  lockAudio(id)
    .then((lr: any) => {
      const d = lr?.data?.data;
      if (d?.locked) {
        lockedByOther.value = true;
        lockedByUser.value = d.locked_by ?? null;
      } else {
        lockedByOther.value = false;
        lockedByUser.value = null;
      }
      lockedAudioId = id;
      clearLockRenewal();
      lockRenewTimer = window.setInterval(() => {
        lockAudio(id).catch(() => {});
      }, 180000);
    })
    .catch(() => {});
}

// ==== 时间序列事件：锁定（按序列整体加锁，定期续期）====
function lockCurrentTimeSeries(id: number) {
  lockTimeSeries(id)
    .then((lr: any) => {
      const d = lr?.data?.data;
      if (d?.locked) {
        lockedByOther.value = true;
        lockedByUser.value = d.locked_by ?? null;
      } else {
        lockedByOther.value = false;
        lockedByUser.value = null;
      }
      lockedTimeSeriesId = id;
      clearLockRenewal();
      lockRenewTimer = window.setInterval(() => {
        lockTimeSeries(id).catch(() => {});
      }, 180000);
    })
    .catch(() => {});
}

const audioSegments = computed<AudioSegment[]>(() =>
  store.annotations.filter((a) => (a as any).type === "AudioSegment") as unknown as AudioSegment[]
);
function audioSegmentColor(segment: AudioSegment, classes: any[]): string {
  const c = classes.find((x) => x.id === segment.label_id);
  if (c?.color) return c.color;
  return "var(--el-color-primary)";
}

const timeSeriesSegments = computed<TimeSeriesSegment[]>(() =>
  store.annotations.filter((a) => (a as any).type === "TimeSeriesSegment") as unknown as TimeSeriesSegment[]
);
// 时间序列事件片段类别颜色：优先用户类别色，缺失回退 Element 主色变量
function timeSeriesSegmentColor(segment: TimeSeriesSegment, classes: any[]): string {
  const c = classes.find((x) => x.id === segment.label_id);
  if (c?.color) return c.color;
  return "var(--el-color-primary)";
}

const videoEventSegments = computed<VideoSegment[]>(() =>
  store.annotations.filter((a) => (a as any).type === "VideoSegment") as unknown as VideoSegment[]
);
// 视频事件片段类别颜色：优先用户类别色，缺失回退 Element 主色变量
function videoSegmentColor(segment: VideoSegment, classes: any[]): string {
  const c = classes.find((x) => x.id === segment.label_id);
  if (c?.color) return c.color;
  return "var(--el-color-primary)";
}

// ==== 音频事件：创建/编辑/删除 ====
const audioDialogVisible = ref(false);
const audioDialogMode = ref<"create" | "edit">("create");
const audioDialogId = ref("");
const audioDialogRange = reactive({ start: 0, end: 0 });
const audioDialogLabelId = ref<number | null>(null);

function formatAudioTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

function openAudioCreateDialog(start: number, end: number) {
  if (lockedByOther.value) return;
  const range = clampAudioRange(start, end, audioDuration.value || end);
  if (range.end <= range.start) {
    ElMessage.warning("区间无效，请重新拖选");
    return;
  }
  if (hasAudioOverlap(audioSegments.value, range.start, range.end)) {
    ElMessage.warning("该区间与已有事件片段重叠，无法创建");
    return;
  }
  audioDialogMode.value = "create";
  audioDialogId.value = "";
  audioDialogRange.start = range.start;
  audioDialogRange.end = range.end;
  audioDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  audioDialogVisible.value = true;
}

function onAudioCreateRegion(region: { id: string; start: number; end: number }) {
  openAudioCreateDialog(region.start, region.end);
}

function onAudioUpdateRegion(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === region.id) as AudioSegment | undefined;
  if (!seg) return;
  if (Math.abs(seg.start - region.start) < 0.001 && Math.abs(seg.end - region.end) < 0.001) return;
  // 拖拽/拉伸路径与对话框编辑一致：排除自身，校验调整后的区间是否与其它片段重叠
  if (hasOverlapExcluding(audioSegments.value, seg.id, region.start, region.end)) {
    const conflicting = findOverlappingSegment(
      audioSegments.value.filter((s) => s.id !== seg.id),
      region.start,
      region.end
    );
    const conflictText = conflicting
      ? `（与 ${formatAudioTime(conflicting.start)} - ${formatAudioTime(conflicting.end)} 冲突）`
      : "";
    ElMessage.warning(`调整后的区间与已有事件片段重叠，无法保存${conflictText}`);
    // 还原 region：先临时改为拖拽后的区间再恢复原始值，触发子组件 syncRegions 将波形区间落回原处
    const original = segmentToRange(seg);
    seg.start = region.start;
    seg.end = region.end;
    seg.start = original.start;
    seg.end = original.end;
    return;
  }
  seg.start = region.start;
  seg.end = region.end;
  store.markUnsaved();
}

function onAudioRemoveRegion(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  if (!store.annotations.some((a) => a.id === region.id)) return;
  deleteAudioSegment(region.id);
}

function onAudioRegionClick(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = region.id;
  openAudioEditDialog(region.id);
}

function openAudioNewDialog() {
  if (lockedByOther.value) return;
  const start = Math.min(audioCurrentTime.value, audioDuration.value || audioCurrentTime.value);
  const end = Math.min(audioDuration.value || start + 1, start + 1);
  audioDialogMode.value = "create";
  audioDialogId.value = "";
  audioDialogRange.start = start;
  audioDialogRange.end = end > start ? end : start + 1;
  audioDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  audioDialogVisible.value = true;
}

function openAudioEditDialog(id: string) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === id);
  if (!seg) return;
  audioDialogMode.value = "edit";
  audioDialogId.value = id;
  audioDialogRange.start = seg.start;
  audioDialogRange.end = seg.end;
  audioDialogLabelId.value = seg.label_id;
  audioDialogVisible.value = true;
}

function confirmAudioDialog() {
  const labelId = audioDialogLabelId.value;
  if (audioDialogMode.value !== "edit" && labelId == null) {
    ElMessage.warning("请选择事件类别");
    return;
  }
  const start = audioDialogRange.start;
  const end = audioDialogRange.end;
  if (!(start < end)) {
    ElMessage.warning("区间无效，结束时间需大于开始时间");
    return;
  }
  if (audioDialogMode.value === "create") {
    if (hasAudioOverlap(audioSegments.value, start, end)) {
      ElMessage.warning("该区间与已有事件片段重叠，无法创建");
      return;
    }
    if (labelId == null) {
      ElMessage.warning("请选择事件类别");
      return;
    }
    const seg = createAudioSegment(start, end, labelId);
    store.annotations.push(seg as any);
    store.selectedAnnotationId = seg.id;
    store.markUnsaved();
    pushHistory();
  } else {
    // 编辑分支：先排除自身片段，校验调整后的区间是否与其它片段重叠
    if (hasOverlapExcluding(audioSegments.value, audioDialogId.value, start, end)) {
      ElMessage.warning("调整后的区间与已有事件片段重叠，无法保存");
      return;
    }
    const seg = store.annotations.find((a) => a.id === audioDialogId.value) as AudioSegment | undefined;
    if (seg && labelId != null) {
      seg.start = start;
      seg.end = end;
      seg.label_id = labelId;
      store.markUnsaved();
      pushHistory();
    }
  }
  audioDialogVisible.value = false;
}

function deleteAudioSegment(id: string) {
  const seg = store.annotations.find((a) => a.id === id) as AudioSegment | undefined;
  if (!seg) return;
  ElMessageBox.confirm(
    `将删除该音频事件片段（${formatAudioTime(seg.start)} - ${formatAudioTime(seg.end)}），且不可恢复。`,
    "删除事件片段",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  )
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        if (store.selectedAnnotationId === id) store.selectedAnnotationId = "";
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}

// ==== 视频事件：创建/编辑/删除 ====
const videoEventDialogVisible = ref(false);
const videoEventDialogMode = ref<"create" | "edit">("create");
const videoEventDialogId = ref("");
const videoEventDialogRange = reactive({ start: 0, end: 0 });
const videoEventDialogLabelId = ref<number | null>(null);

function formatVideoEventTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function openVideoEventCreateDialog(start: number, end: number) {
  if (lockedByOther.value) return;
  const range = clampVideoRange(start, end, videoEventDuration.value || end);
  if (range.end <= range.start) {
    ElMessage.warning("区间无效，请重新拖选");
    return;
  }
  if (hasVideoEventOverlap(videoEventSegments.value, range.start, range.end)) {
    ElMessage.warning("该区间与已有事件片段重叠，无法创建");
    return;
  }
  videoEventDialogMode.value = "create";
  videoEventDialogId.value = "";
  videoEventDialogRange.start = range.start;
  videoEventDialogRange.end = range.end;
  videoEventDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  videoEventDialogVisible.value = true;
}

function onVideoEventCreateRegion(region: { id: string; start: number; end: number }) {
  openVideoEventCreateDialog(region.start, region.end);
}

function onVideoEventUpdateRegion(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === region.id) as VideoSegment | undefined;
  if (!seg) return;
  if (Math.abs(seg.start - region.start) < 0.001 && Math.abs(seg.end - region.end) < 0.001) return;
  // 拖拽/拉伸路径与对话框编辑一致：排除自身，校验调整后的区间是否与其它片段重叠
  if (hasVideoOverlapExcluding(videoEventSegments.value, seg.id, region.start, region.end)) {
    const conflicting = findVideoOverlappingSegment(
      videoEventSegments.value.filter((s) => s.id !== seg.id),
      region.start,
      region.end
    );
    const conflictText = conflicting
      ? `（与 ${formatVideoEventTime(conflicting.start)} - ${formatVideoEventTime(conflicting.end)} 冲突）`
      : "";
    ElMessage.warning(`调整后的区间与已有事件片段重叠，无法保存${conflictText}`);
    // 还原 region：先临时改为拖拽后的区间再恢复原始值，触发子组件将区间落回原处
    const original = videoSegmentToRange(seg);
    seg.start = region.start;
    seg.end = region.end;
    seg.start = original.start;
    seg.end = original.end;
    return;
  }
  seg.start = region.start;
  seg.end = region.end;
  store.markUnsaved();
}

function onVideoEventRemoveRegion(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  if (!store.annotations.some((a) => a.id === region.id)) return;
  deleteVideoEventSegment(region.id);
}

function onVideoEventRegionClick(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = region.id;
  openVideoEventEditDialog(region.id);
}

function openVideoEventNewDialog() {
  if (lockedByOther.value) return;
  if (videoEventDuration.value <= 0) {
    ElMessage.warning("视频时长未知，无法新建事件");
    return;
  }
  const end = Math.min(videoEventDuration.value, 5);
  videoEventDialogMode.value = "create";
  videoEventDialogId.value = "";
  videoEventDialogRange.start = 0;
  videoEventDialogRange.end = end > 0 ? end : 1;
  videoEventDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  videoEventDialogVisible.value = true;
}

function openVideoEventEditDialog(id: string) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === id);
  if (!seg) return;
  videoEventDialogMode.value = "edit";
  videoEventDialogId.value = id;
  videoEventDialogRange.start = seg.start;
  videoEventDialogRange.end = seg.end;
  videoEventDialogLabelId.value = seg.label_id;
  videoEventDialogVisible.value = true;
}

function confirmVideoEventDialog() {
  const labelId = videoEventDialogLabelId.value;
  if (videoEventDialogMode.value !== "edit" && labelId == null) {
    ElMessage.warning("请选择事件类别");
    return;
  }
  const start = videoEventDialogRange.start;
  const end = videoEventDialogRange.end;
  if (!(start < end)) {
    ElMessage.warning("区间无效，结束时间需大于开始时间");
    return;
  }
  if (videoEventDialogMode.value === "create") {
    if (hasVideoEventOverlap(videoEventSegments.value, start, end)) {
      ElMessage.warning("该区间与已有事件片段重叠，无法创建");
      return;
    }
    if (labelId == null) {
      ElMessage.warning("请选择事件类别");
      return;
    }
    const seg = createVideoSegment(start, end, labelId);
    store.annotations.push(seg as any);
    store.selectedAnnotationId = seg.id;
    store.markUnsaved();
    pushHistory();
  } else {
    // 编辑分支：先排除自身片段，校验调整后的区间是否与其它片段重叠
    if (hasVideoOverlapExcluding(videoEventSegments.value, videoEventDialogId.value, start, end)) {
      ElMessage.warning("调整后的区间与已有事件片段重叠，无法保存");
      return;
    }
    const seg = store.annotations.find((a) => a.id === videoEventDialogId.value) as VideoSegment | undefined;
    if (seg && labelId != null) {
      seg.start = start;
      seg.end = end;
      seg.label_id = labelId;
      store.markUnsaved();
      pushHistory();
    }
  }
  videoEventDialogVisible.value = false;
}

function deleteVideoEventSegment(id: string) {
  const seg = store.annotations.find((a) => a.id === id) as VideoSegment | undefined;
  if (!seg) return;
  ElMessageBox.confirm(
    `将删除该视频事件片段（${formatVideoEventTime(seg.start)} - ${formatVideoEventTime(seg.end)}），且不可恢复。`,
    "删除事件片段",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  )
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        if (store.selectedAnnotationId === id) store.selectedAnnotationId = "";
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}

// ==== 时间序列事件：创建/编辑/删除 ====
const tsDialogVisible = ref(false);
const tsDialogMode = ref<"create" | "edit">("create");
const tsDialogId = ref("");
const tsDialogRange = reactive({ start: 0, end: 0 });
const tsDialogLabelId = ref<number | null>(null);
/** 时间序列弹窗时间输入的范围（序列时间范围 [start_time, end_time]），越界钳制。 */
const tsDialogRangeMin = computed(() => seriesRange.value?.start ?? 0);
const tsDialogRangeMax = computed(() => seriesRange.value?.end ?? 1);

function formatSeriesTimeValue(value: number): string {
  return formatSeriesTime(value, seriesMeta.value?.time_unit || "");
}

function assertSeriesRange(start: number, end: number) {
  const meta = seriesMeta.value;
  if (meta) {
    return clampTimeRange(start, end, meta.start_time, meta.end_time);
  }
  return { start, end };
}

function openTimeSeriesCreateDialog(start: number, end: number) {
  if (lockedByOther.value) return;
  const range = assertSeriesRange(start, end);
  if (range.end <= range.start) {
    ElMessage.warning("区间无效，请重新拖选");
    return;
  }
  if (hasTimeSeriesOverlap(timeSeriesSegments.value, range.start, range.end)) {
    ElMessage.warning("该区间与已有事件区间重叠，无法创建");
    return;
  }
  tsDialogMode.value = "create";
  tsDialogId.value = "";
  tsDialogRange.start = range.start;
  tsDialogRange.end = range.end;
  tsDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  tsDialogVisible.value = true;
}

function onTimeSeriesCreateRegion(region: { id: string; start: number; end: number }) {
  openTimeSeriesCreateDialog(region.start, region.end);
}

function onTimeSeriesUpdateRegion(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === region.id) as TimeSeriesSegment | undefined;
  if (!seg) return;
  if (Math.abs(seg.start - region.start) < 0.001 && Math.abs(seg.end - region.end) < 0.001) return;
  // 拖拽/拉伸路径与对话框编辑一致：排除自身，校验调整后的区间是否与其它片段重叠
  if (hasTsOverlapExcluding(timeSeriesSegments.value, seg.id, region.start, region.end)) {
    const conflicting = findTsOverlappingSegment(
      timeSeriesSegments.value.filter((s) => s.id !== seg.id),
      region.start,
      region.end
    );
    const conflictText = conflicting
      ? `（与 ${formatSeriesTimeValue(conflicting.start)} - ${formatSeriesTimeValue(conflicting.end)} 冲突）`
      : "";
    ElMessage.warning(`调整后的区间与已有事件区间重叠，无法保存${conflictText}`);
    // 还原 region：先临时改为拖拽后的区间再恢复原始值，触发子组件 syncRegions 将区间落回原处
    const original = tsSegmentToRange(seg);
    seg.start = region.start;
    seg.end = region.end;
    seg.start = original.start;
    seg.end = original.end;
    return;
  }
  seg.start = region.start;
  seg.end = region.end;
  store.markUnsaved();
}

function onTimeSeriesRegionClick(region: { id: string; start: number; end: number }) {
  if (lockedByOther.value) return;
  store.selectedAnnotationId = region.id;
  openTimeSeriesEditDialog(region.id);
}

function openTimeSeriesNewDialog() {
  if (lockedByOther.value) return;
  if (!seriesData.value.length) {
    ElMessage.warning("暂无序列数据，无法新建事件");
    return;
  }
  const start = seriesData.value[0].time;
  const end = seriesData.value[seriesData.value.length - 1].time;
  tsDialogMode.value = "create";
  tsDialogId.value = "";
  tsDialogRange.start = start;
  tsDialogRange.end = end > start ? end : start + 1;
  tsDialogLabelId.value = taskClasses.value[0]?.id ?? null;
  tsDialogVisible.value = true;
}

function openTimeSeriesEditDialog(id: string) {
  if (lockedByOther.value) return;
  const seg = store.annotations.find((a) => a.id === id);
  if (!seg) return;
  tsDialogMode.value = "edit";
  tsDialogId.value = id;
  tsDialogRange.start = seg.start;
  tsDialogRange.end = seg.end;
  tsDialogLabelId.value = seg.label_id;
  tsDialogVisible.value = true;
}

function confirmTimeSeriesDialog() {
  const labelId = tsDialogLabelId.value;
  if (tsDialogMode.value !== "edit" && labelId == null) {
    ElMessage.warning("请选择事件类别");
    return;
  }
  // 弹窗录入的 start/end 钳制到序列时间范围 [start_time, end_time]，越界时按边界收口（与拖选路径一致）；
  // 再校验 end > start，失败则拒绝保存。
  let start = tsDialogRange.start;
  let end = tsDialogRange.end;
  const meta = seriesMeta.value;
  if (meta) {
    start = Math.max(meta.start_time, Math.min(meta.end_time, start));
    end = Math.max(meta.start_time, Math.min(meta.end_time, end));
  }
  if (!(start < end)) {
    ElMessage.warning("区间无效，结束时间需大于开始时间");
    return;
  }
  if (tsDialogMode.value === "create") {
    if (hasTimeSeriesOverlap(timeSeriesSegments.value, start, end)) {
      ElMessage.warning("该区间与已有事件区间重叠，无法创建");
      return;
    }
    if (labelId == null) {
      ElMessage.warning("请选择事件类别");
      return;
    }
    const seg = createTimeSeriesSegment(start, end, labelId);
    store.annotations.push(seg as any);
    store.selectedAnnotationId = seg.id;
    store.markUnsaved();
    pushHistory();
  } else {
    // 编辑分支：先排除自身片段，校验调整后的区间是否与其它片段重叠
    if (hasTsOverlapExcluding(timeSeriesSegments.value, tsDialogId.value, start, end)) {
      ElMessage.warning("调整后的区间与已有事件区间重叠，无法保存");
      return;
    }
    const seg = store.annotations.find((a) => a.id === tsDialogId.value) as TimeSeriesSegment | undefined;
    if (seg && labelId != null) {
      seg.start = start;
      seg.end = end;
      seg.label_id = labelId;
      store.markUnsaved();
      pushHistory();
    }
  }
  tsDialogVisible.value = false;
}

function deleteTimeSeriesSegment(id: string) {
  const seg = store.annotations.find((a) => a.id === id) as TimeSeriesSegment | undefined;
  if (!seg) return;
  ElMessageBox.confirm(
    `将删除该时间序列事件区间（${formatSeriesTimeValue(seg.start)} - ${formatSeriesTimeValue(seg.end)}），且不可恢复。`,
    "删除事件区间",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  )
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        if (store.selectedAnnotationId === id) store.selectedAnnotationId = "";
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}

async function initTimeSeries() {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return;
  resetDrawingState();
  try {
    const lr = await getTimeSeriesList(datasetId);
    const items = lr?.data?.data?.items || [];
    const series = items[0];
    if (!series) return;
    timeSeriesId.value = series.id;
    const dr = await getTimeSeriesDetail(series.id);
    seriesMeta.value = dr?.data?.data ?? series;
    const cr = await getTimeSeriesContent(series.id);
    seriesCsvRaw.value = cr?.data ?? "";
    const parsed = parseSeriesCsv(seriesCsvRaw.value, seriesMeta.value);
    seriesValueColumn.value = parsed.valueColumn;
    seriesData.value = parsed.points;
    const ar = await loadTimeSeriesAnnotations({ task_id: store.taskId, t_id: series.id });
    store.annotations = (ar?.data?.data?.annotation_data || []) as any;
    store.selectedAnnotationId = "";
    store.unsaved = false;
    store.totalCount = 1;
    store.annotatedCount = store.annotations.length ? 1 : 0;
    lockCurrentTimeSeries(series.id);
  } catch (e) {
    console.error("加载时间序列事件任务失败", e);
    ElMessage.error("时间序列数据加载失败，请稍后重试");
  }
}

function onTimeSeriesChangeColumn(valueColumn: string) {
  if (!seriesMeta.value) return;
  const parsed = parseSeriesCsv(seriesCsvRaw.value, seriesMeta.value, valueColumn);
  seriesValueColumn.value = parsed.valueColumn;
  seriesData.value = parsed.points;
}

async function initAudio() {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return;
  resetDrawingState();
  try {
    const lr = await getAudioList(datasetId);
    const items = lr?.data?.data?.items || [];
    const audio = items[0];
    if (!audio) return;
    audioId.value = audio.id;
    const dr = await getAudioDetail(audio.id);
    const d = dr?.data?.data;
    audioDuration.value = d?.duration || 0;
    audioUrl.value = getAudioContentUrl(audio.id);
    const ar = await loadAudioAnnotations({ task_id: store.taskId, audio_id: audio.id });
    store.annotations = (ar?.data?.data?.annotation_data || []) as any;
    store.selectedAnnotationId = "";
    store.unsaved = false;
    store.totalCount = 1;
    store.annotatedCount = store.annotations.length ? 1 : 0;
    lockCurrentAudio(audio.id);
  } catch (e) {
    console.error("加载音频事件任务失败", e);
    ElMessage.error("音频事件数据加载失败，请稍后重试");
  }
}

async function initVideoEvent() {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return;
  resetDrawingState();
  try {
    const lr = await getVideoList(datasetId);
    const items = lr?.data?.data?.items || [];
    const video = items[0];
    if (!video) return;
    videoEventId.value = video.id;
    const dr = await getVideoDetail(video.id);
    const d = dr?.data?.data;
    videoEventDuration.value = d?.duration || 0;
    const ar = await loadVideoEventAnnotations({ task_id: store.taskId, video_id: video.id });
    store.annotations = (ar?.data?.data?.annotation_data || []) as any;
    store.selectedAnnotationId = "";
    store.unsaved = false;
    store.totalCount = 1;
    store.annotatedCount = store.annotations.length ? 1 : 0;
    lockCurrentVideo(video.id);
  } catch (e) {
    console.error("加载视频事件任务失败", e);
    ElMessage.error("视频事件数据加载失败，请稍后重试");
  }
}

const MAX_HISTORY = 50;
let historyStack: string[] = [];
let historyIndex = -1;
let lastSavedKey = "";
function annotKey() {
  return JSON.stringify(store.annotations);
}
function shallowEqual(a: any, b: any): boolean {
  if (a === b) return true;
  const ka = Object.keys(a);
  const kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  return ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && Object.is(a[k], b[k]));
}
function pushHistory() {
  const key = annotKey();
  if (historyIndex >= 0 && historyStack[historyIndex] === key) return;
  historyStack = historyStack.slice(0, historyIndex + 1);
  historyStack.push(key);
  if (historyStack.length > MAX_HISTORY) historyStack.shift();
  historyIndex = historyStack.length - 1;
}
function undo() {
  if (lockedByOther.value) return;
  if (historyIndex <= 0) return;
  historyIndex--;
  restoreHistory();
}
function redo() {
  if (lockedByOther.value) return;
  if (historyIndex >= historyStack.length - 1) return;
  historyIndex++;
  restoreHistory();
}
function restoreHistory() {
  const key = historyStack[historyIndex];
  try {
    store.annotations = key ? JSON.parse(key) : [];
  } catch {
    store.annotations = [];
  }
  if (annotKey() !== lastSavedKey && historyIndex < historyStack.length - 1) store.markUnsaved();
}
function deleteAnnotation(id: string) {
  if (lockedByOther.value) return;
  const target = store.annotations.find((a) => a.id === id);
  if (!target) return;
  ElMessageBox.confirm(`将删除 1 个${target.type}标注，且不可恢复。`, "删除标注", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}
function deleteSelected() {
  deleteAnnotation(store.selectedAnnotationId);
}

// ==== 文本 NER：实体 / 关系编辑 ====
const selRange = ref<{ from: number; to: number } | null>(null);
const entityDialogVisible = ref(false);
const entityLabelId = ref<number | null>(null);
const editSpanVisible = ref(false);
const editSpanId = ref("");
const editSpanLabelId = ref<number | null>(null);
const relationDialogVisible = ref(false);
const relationForm = reactive({ from: "", to: "", relation_type: null as number | null });

// 句子边界按 \n 切分；「同一句」判断交由 useTextNerTool 的同名工具函数（sameSentence）
// 新建关系时，终点候选限制为与起点实体同句的实体（按 \n 切分），提交时仍保留校验兜底。
const relationToCandidates = computed<any[]>(() => {
  if (!relationForm.from) return textEntities.value;
  const from = textEntities.value.find((e) => e.id === relationForm.from);
  if (!from) return textEntities.value;
  return textEntities.value.filter((e) => e.id !== from.id && sameSentence(docContent.value, from, e));
});
function onRelationFromChange() {
  if (!relationForm.to) return;
  const from = textEntities.value.find((e) => e.id === relationForm.from);
  const to = textEntities.value.find((e) => e.id === relationForm.to);
  if (!from || !to || !sameSentence(docContent.value, from, to)) relationForm.to = "";
}

function entityLabelName(e: EntitySpan): string {
  return textEntityClasses.value.find((c) => c.id === e.label_id)?.name ?? `#${e.label_id}`;
}
function onTextSelect(range: { from: number; to: number }) {  if (lockedByOther.value) return;
  if (!range || range.to <= range.from) return;
  const overlap = findOverlappingSpan(textEntities.value, range.from, range.to);
  if (overlap) {
    ElMessage.warning("该选区与已有实体重叠，无法创建实体");
    return;
  }
  selRange.value = range;
  entityLabelId.value = textEntityClasses.value[0]?.id ?? null;
  entityDialogVisible.value = true;
}
function confirmEntity() {
  const range = selRange.value;
  if (!range || entityLabelId.value == null) return;
  const span = createEntitySpan(docContent.value, range, entityLabelId.value);
  store.annotations.push(span as any);
  store.selectedAnnotationId = span.id;
  store.markUnsaved();
  pushHistory();
  entityDialogVisible.value = false;
  selRange.value = null;
}
function onSpanClick(span: EntitySpan) {
  if (lockedByOther.value) return;
  editSpanId.value = span.id;
  editSpanLabelId.value = span.label_id;
  editSpanVisible.value = true;
}
function saveEditSpan() {
  const s = store.annotations.find((a) => a.id === editSpanId.value) as EntitySpan | undefined;
  if (s && editSpanLabelId.value != null) {
    s.label_id = editSpanLabelId.value;
    store.markUnsaved();
    pushHistory();
  }
  editSpanVisible.value = false;
}
function deleteEditSpan() {
  const id = editSpanId.value;
  editSpanVisible.value = false;
  if (id) deleteEntity(id);
}
function deleteEntity(id: string) {
  const ent = textEntities.value.find((e) => e.id === id);
  if (!ent) return;
  const relCount = textRelations.value.filter(
    (r) => r.from === id || r.to === id
  ).length;
  ElMessageBox.confirm(
    `将删除实体「${ent.text || "?"}」及关联的 ${relCount} 个关系，且不可恢复。`,
    "删除实体",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  )
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter(
        (a) =>
          a.id !== id &&
          !((a as any).type === "Relation" && ((a as any).from === id || (a as any).to === id))
      );
      if (store.annotations.length !== before) {
        if (store.selectedAnnotationId === id) store.selectedAnnotationId = "";
        store.markUnsaved();
        pushHistory();
      }
    })
    .catch(() => {});
}
function openRelationDialog() {
  if (lockedByOther.value) return;
  if (textEntities.value.length < 2) {
    ElMessage.warning("至少需要两个实体才能创建关系");
    return;
  }
  relationForm.from = "";
  relationForm.to = "";
  relationForm.relation_type = textRelationClasses.value[0]?.id ?? null;
  relationDialogVisible.value = true;
}
function confirmRelation() {
  const { from, to, relation_type } = relationForm;
  if (!from || !to) {
    ElMessage.warning("请选择关系两端的实体");
    return;
  }
  if (from === to) {
    ElMessage.warning("关系两端不能是同一实体");
    return;
  }
  const a = textEntities.value.find((e) => e.id === from);
  const b = textEntities.value.find((e) => e.id === to);
  if (!a || !b) return;
  if (!sameSentence(docContent.value, a, b)) {
    ElMessage.warning("关系两端实体必须位于同一句（同一行）");
    return;
  }
  if (relation_type == null) {
    ElMessage.warning("请选择关系类型");
    return;
  }
  store.annotations.push({
    id: crypto.randomUUID(),
    type: "Relation",
    from,
    to,
    relation_type,
  } as any);
  store.markUnsaved();
  pushHistory();
  relationDialogVisible.value = false;
  relationForm.from = "";
  relationForm.to = "";
  relationForm.relation_type = null;
}
function deleteRelation(id: string) {
  const rel = textRelations.value.find((r) => r.id === id);
  if (!rel) return;
  ElMessageBox.confirm("将删除该关系，且不可恢复。", "删除关系", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      const before = store.annotations.length;
      store.annotations = store.annotations.filter((a) => a.id !== id);
      if (store.annotations.length !== before) {
        store.markUnsaved();
        pushHistory();
      }
      if (activeRelationId.value === id) activeRelationId.value = "";
    })
    .catch(() => {});
}


// 复制 / 粘贴标注
let annClipboard: any = null;
function copySelected() {
  const ann = store.annotations.find((a) => a.id === store.selectedAnnotationId);
  if (!ann) {
    ElMessage.info("请先选中一个标注");
    return;
  }
  annClipboard = JSON.parse(JSON.stringify(ann));
  ElMessage.success("已复制标注");
}
function pasteCopied() {
  if (lockedByOther.value) return;
  if (!annClipboard) {
    ElMessage.info("剪贴板为空，先 Ctrl+C 复制标注");
    return;
  }
  const copy = JSON.parse(JSON.stringify(annClipboard));
  copy.id = crypto.randomUUID();
  const clamp = (v: number) => Math.max(0, Math.min(1, v));
  if (copy.x1 !== undefined) {
    copy.x1 = clamp(copy.x1 + 0.01);
    copy.x2 = clamp(copy.x2 + 0.01);
    copy.y1 = clamp(copy.y1 + 0.01);
    copy.y2 = clamp(copy.y2 + 0.01);
  } else if (copy.cx !== undefined) {
    copy.cx = clamp(copy.cx + 0.01);
    copy.cy = clamp(copy.cy + 0.01);
  } else if (copy.points) {
    copy.points = copy.points.map((p: any) => ({ x: clamp(p.x + 0.01), y: clamp(p.y + 0.01) }));
  } else if (copy.keypoints) {
    copy.keypoints = copy.keypoints.map((k: any) => ({
      ...k,
      x: clamp(k.x + 0.01),
      y: clamp(k.y + 0.01),
    }));
  }
  store.annotations.push(copy);
  store.selectedAnnotationId = copy.id;
  store.markUnsaved();
  pushHistory();
}

const taskClasses = ref<any[]>(Array.isArray(props.config.classes) ? [...(props.config.classes || [])] : []);
watch(
  () => props.config.classes,
  (val) => {
    taskClasses.value = Array.isArray(val) ? [...(val || [])] : [];
  },
  { deep: true }
);
watch(
  () => [...taskClasses.value],
  (arr) => {
    if (!arr.length) selectedClassId.value = null;
    else if (!arr.some((c) => c.id === selectedClassId.value)) selectedClassId.value = arr[0].id;
  },
  { immediate: true }
);
// ==== 文本 NER：classes 为字典 {entities, relations} ====
const textEntityClasses = computed<any[]>(() => {
  const c = store.task?.classes;
  if (!isTextTask.value || !c || Array.isArray(c)) return [];
  return c.entities || [];
});
const textRelationClasses = computed<any[]>(() => {
  const c = store.task?.classes;
  if (!isTextTask.value || !c || Array.isArray(c)) return [];
  return c.relations || [];
});
const textEntities = computed<EntitySpan[]>(() =>
  store.annotations.filter((a) => (a as any).type === "EntitySpan") as unknown as EntitySpan[]
);
const textRelations = computed<Relation[]>(() =>
  store.annotations.filter((a) => (a as any).type === "Relation") as unknown as Relation[]
);
// 实体颜色：优先用类别 color，缺失回退固定色（避免与 Element 主色冲突）
const TEXT_PRESET = ["#409eff", "#67c23a", "#e6a23c", "#f56c6c", "#9b59b6", "#00bcd4"];
const textEntityColor = (span: EntitySpan, _classes: any[]) => {
  const c = textEntityClasses.value.find((x) => x.id === span.label_id);
  if (c?.color) return c.color;
  return TEXT_PRESET[Math.abs(span.label_id) % TEXT_PRESET.length];
};
// 关系两端实体高亮：由关系列表 hover/click 驱动
const activeRelationId = ref("");
const activeRelationHighlightIds = computed<string[]>(() => {
  if (!activeRelationId.value) return [];
  const rel = textRelations.value.find((r) => r.id === activeRelationId.value);
  return rel ? [rel.from, rel.to] : [];
});
const panelCtx = computed<PluginPanelContext>(() => ({
  classes: taskClasses.value,
  selectedClassId: selectedClassId.value,
  commit: (ann: Annotation) => commitCreated(ann),
  annotations: store.annotations,
  remove: (ids: string[]) => {
    if (!ids.length) return;
    const before = store.annotations.length;
    store.annotations = store.annotations.filter((a) => !ids.includes(a.id));
    if (store.annotations.length !== before) {
      store.selectedAnnotationId = "";
      store.markUnsaved();
      pushHistory();
    }
  },
  selectedAnnotationId: store.selectedAnnotationId,
  // 图像像素尺寸：面板要用它做「归一化 ↔ 像素 ↔ 米制」的换算
  // （如 cuboid 由 3D 框反推底面投影）。此前面板拿不到尺寸，只能显示不能换算。
  imageWidth: cw.value,
  imageHeight: ch.value,
  update: (ann: Annotation) => {
    const idx = store.annotations.findIndex((a) => a.id === ann.id);
    if (idx < 0) return;
    // 「值未变」守卫：面板输入 blur 时若值未变化则不推 history / 不标记未保存
    if (shallowEqual(store.annotations[idx], ann)) return;
    store.annotations = store.annotations.map((a) => (a.id === ann.id ? ann : a));
    store.markUnsaved();
    pushHistory();
  },
}));
const showClassModal = ref(false);
const editingClassId = ref<number | null>(null);
const PRESET_COLORS = [
  "#409eff",
  "#67c23a",
  "#e6a23c",
  "#f56c6c",
  "#909399",
  "#9b59b6",
  "#00bcd4",
  "#ff9800",
  "#795548",
  "#607d8b",
  "#e91e63",
  "#8bc34a",
];
const clsForm = reactive({
  name: "",
  color: "#409eff",
  kpNames: [] as string[],
  kpColors: [] as string[],
});

function openAddClass() {
  editingClassId.value = null;
  clsForm.name = "";
  clsForm.color = PRESET_COLORS[0];
  clsForm.kpNames = [];
  clsForm.kpColors = [];
  showClassModal.value = true;
}
function openEditClass(c: any) {
  editingClassId.value = c.id;
  clsForm.name = c.name || "";
  clsForm.color = c.color || PRESET_COLORS[0];
  clsForm.kpNames = [...(c.keypoint_names || [])];
  clsForm.kpColors = [...(c.keypoint_colors || [])];
  showClassModal.value = true;
}
const ocrInputVisible = ref(false);
const ocrInput = ref("");
let pendingOcr: Annotation | null = null;

async function addClass() {
  if (lockedByOther.value) return;
  if (!clsForm.name.trim()) return;
  const kpNames = clsForm.kpNames.filter((n) => n.trim());
  if (editingClassId.value !== null) {
    const c = taskClasses.value.find((x) => x.id === editingClassId.value);
    if (c) {
      c.name = clsForm.name.trim();
      c.color = clsForm.color;
      c.keypoint_names = kpNames.length ? kpNames : undefined;
      c.keypoint_colors = kpNames.length ? clsForm.kpColors.slice(0, kpNames.length) : undefined;
    }
  } else {
    const id =
      taskClasses.value.length > 0 ? Math.max(...taskClasses.value.map((c) => c.id)) + 1 : 0;
    taskClasses.value.push({
      id,
      name: clsForm.name.trim(),
      color: clsForm.color,
      keypoint_names: kpNames.length ? kpNames : undefined,
      keypoint_colors: kpNames.length ? clsForm.kpColors.slice(0, kpNames.length) : undefined,
    });
  }
  clsForm.name = "";
  clsForm.kpNames = [];
  clsForm.kpColors = [];
  showClassModal.value = false;
  await saveClasses();
}
async function removeClass(id: number) {
  if (lockedByOther.value) return;
  taskClasses.value = taskClasses.value.filter((c) => c.id !== id);
  const before = store.annotations.length;
  store.annotations = store.annotations.filter((a: any) => {
    const uses = a.class_id === id || (Array.isArray(a.class_ids) && a.class_ids.includes(id));
    return !uses;
  });
  if (store.annotations.length !== before) {
    store.markUnsaved();
    pushHistory();
  }
  if (selectedClassId.value === id) selectedClassId.value = taskClasses.value[0]?.id ?? null;
  await saveClasses();
}
function clsCount(classId: number) {
  return store.annotations.filter((a) => a.class_id === classId).length;
}
async function changeClassColor(id: number, color: string) {
  const c = taskClasses.value.find((x) => x.id === id);
  if (!c) return;
  c.color = color;
  // 颜色为响应式，标注框颜色（clsColor）会自动联动更新
  await saveClasses();
}
async function saveClasses() {
  if (!store.taskId || lockedByOther.value) return;
  try {
    await props.api.updateTask(store.taskId, { classes: taskClasses.value });
  } catch {
    /* ignore */
  }
}

function clsName(a: Annotation) {
  const c = taskClasses.value.find((c) => c.id === a.class_id);
  if (c) return c.name;
  // 多标签聚合并集显示
  if (Array.isArray(a.class_ids) && a.class_ids.length) {
    return a.class_ids
      .map((id) => taskClasses.value.find((c) => c.id === id)?.name)
      .filter(Boolean)
      .join(" / ");
  }
  return "";
}
function clsColor(a: Annotation) {
  return taskClasses.value.find((c) => c.id === a.class_id)?.color || "#3b82f6";
}

let _canvasEl: HTMLElement | null = null;
function getCanvasEl(): HTMLElement | null {
  if (!_canvasEl || !document.contains(_canvasEl)) {
    _canvasEl = document.querySelector(".annotation-canvas") as HTMLElement | null;
  }
  return _canvasEl;
}

const canvasRect = { left: 0, top: 0, width: 0, height: 0 };
const rectTick = ref(0);
function measureCanvas() {
  const el = getCanvasEl();
  if (!el) return;
  const r = el.getBoundingClientRect();
  canvasRect.left = r.left;
  canvasRect.top = r.top;
  canvasRect.width = r.width;
  canvasRect.height = r.height;
}
function canvasR() {
  return canvasRect;
}

function toImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const r = canvasR();
  if (!r.width || !r.height) return null;
  return canvas.containerToImage(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
}

function toolFor(name: string) {
  return (
    plugin.value.toolMap?.[name] ??
    (name === plugin.value.tool?.name ? plugin.value.tool : undefined)
  );
}
function resetAllDraftTools() {
  const tm = plugin.value.toolMap;
  if (tm) for (const k in tm) tm[k]?.reset?.();
  if (plugin.value.tool) plugin.value.tool.reset?.();
}
function setTool(t: string) {
  const prev = currentTool.value;
  const entry = (displayTools.value as any[]).find((x) => x.name === t);
  const base = entry?._tool ?? t;
  const mode = entry?._mode ?? null;
  if (prev !== base) {
    // 重置即将离开的工具，防止其部分绘制状态残留（如多边形半成品顶点）
    const prevTool = toolFor(prev);
    prevTool?.reset?.();
    // 兼容旧版单工具插件：切换时同样重置其工具
    if (plugin.value.tool && plugin.value.tool !== prevTool) plugin.value.tool.reset?.();
  }
  currentTool.value = base;
  // 设置子工具模式（涂抹/套索、矩形/多边形等）
  if (mode != null) {
    const st = activeTool.value?.state;
    if (st?.setMode) st.setMode(mode);
    else if (st?.setBrushMode) st.setBrushMode(mode);
  }
  resetDrawingState();
}
function resetDrawingState() {
  draftAnn.value = null;
  dragState = null;
  activeTool.value?.reset?.();
}

function onKeyUp(e: KeyboardEvent) {
  if (e.code === "Space") spaceHeld.value = false;
}
function onDocClick(e: MouseEvent) {
  // 点击编辑气泡外部 → 自动关闭气泡
  if (editAnnVisible.value && !(e.target as Element)?.closest?.(".edit-bubble")) {
    // 若点击的是右键菜单/气泡自身则忽略
    if (
      (e.target as Element)?.closest?.(".edit-bubble") ||
      (e.target as Element)?.closest?.(".ctx-menu")
    )
      return;
    editAnnVisible.value = false;
  }
}
function onImgLoad(w: number, h: number) {
  imageLoaded.value = true;
  resetAllDraftTools();
  measureCanvas();
  if (!canvas.cw.value && w && h) canvas.setImageSize(w, h);
  if (!fittedForImage) {
    const r = canvasR();
    if (r.width && r.height && canvas.cw.value && canvas.ch.value) {
      canvas.fitZoom(r.width, r.height);
      fittedForImage = true;
    }
  }
}

function onVideoLoaded(e: Event) {
  const el = e.target as HTMLVideoElement;
  imageLoaded.value = true;
  bindVideoEvents(el);
  resetAllDraftTools();
  measureCanvas();
  if (!canvas.cw.value && el.videoWidth && el.videoHeight) {
    canvas.setImageSize(el.videoWidth, el.videoHeight);
  }
  if (!fittedForImage) {
    const r = canvasR();
    if (r.width && r.height && canvas.cw.value && canvas.ch.value) {
      canvas.fitZoom(r.width, r.height);
      fittedForImage = true;
    }
  }
}

async function loadFrameAnnotations(idx: number) {
  if (!videoId.value || !store.taskId) return;
  resetDrawingState();
  const vr = await loadVideoAnnotations(store.taskId, videoId.value, idx);
  store.annotations = (vr?.data?.data || []) as Annotation[];
  store.selectedAnnotationId = "";
  store.unsaved = false;
  // 缓存该帧标注，供轨迹连线与按轨迹导航使用；并触发轨迹层重算
  frameCache.set(idx, store.annotations);
  if (frameCache.size > MAX_FRAME_CACHE) {
    const oldest = frameCache.keys().next().value;
    if (oldest != null) frameCache.delete(oldest);
  }
  bumpTrack();
}

// ==== 轨迹层计算（跨帧连线 / 轨迹列表 / 按轨迹导航）====
/** 各轨迹出现的帧及框（按帧序），来自已访问帧缓存。 */
const trackFrameMap = computed(() => {
  void trackTick.value;
  const map = new Map<string, { frameIndex: number; box: Annotation }[]>();
  for (const [fi, anns] of frameCache) {
    for (const a of anns) {
      if (a.type !== "AxisAlignedBox" || !a.track_id) continue;
      const arr = map.get(a.track_id);
      if (arr) arr.push({ frameIndex: fi, box: a });
      else map.set(a.track_id, [{ frameIndex: fi, box: a }]);
    }
  }
  for (const arr of map.values()) arr.sort((x, y) => x.frameIndex - y.frameIndex);
  return map;
});
/** 轨迹列表（用于「选择已有轨迹」与轨迹选择下拉）。 */
const trackOptions = computed(() => {
  void trackTick.value;
  return [...trackFrameMap.value.keys()].sort();
});
/** 当前帧出现的轨迹 id 集合。 */
const currentTrackIds = computed(() => {
  void trackTick.value;
  return new Set(collectTrackIds(store.annotations));
});
/** 待绘制轨迹路径：当前帧的轨迹 + 选中的轨迹（高亮），取其中心点跨帧连线。 */
const trackPaths = computed(() => {
  void trackTick.value;
  const out: { trackId: string; points: { x: number; y: number }[]; color: string; selected: boolean }[] = [];
  for (const [tid, frames] of trackFrameMap.value) {
    if (!currentTrackIds.value.has(tid) && tid !== selectedTrackId.value) continue;
    const path = trackPathFromFrames(frames);
    out.push({
      trackId: tid,
      points: path.map((f) => f.point),
      color: trackColor(tid),
      selected: tid === selectedTrackId.value,
    });
  }
  return out;
});
/** 某轨迹出现的帧号列表（用于前后跳转）。 */
function framesOfTrack(trackId: string): number[] {
  const frames = trackFrameMap.value.get(trackId);
  return frames ? frames.map((f) => f.frameIndex) : [];
}
/** 按轨迹跳转到前/后一帧（该 track 出现的其它已访问帧）。 */
function goTrackFrame(dir: 1 | -1) {
  if (!selectedTrackId.value) return;
  const target = nearestTrackFrame(framesOfTrack(selectedTrackId.value), currentFrame.value, dir);
  if (target != null) goToFrame(target);
}
/** 轨迹 id 的简短展示。 */
function shortTrack(trackId: string): string {
  return trackId.length > 8 ? trackId.slice(0, 8) : trackId;
}

async function onVideoSeeked() {
  if (!videoId.value) return;
  const ve = canvasRef.value?.getVideoEl?.();
  let landed = ve ? timeToFrameIndex(ve.currentTime, videoFps.value) : pendingSeekFrame;
  // 兜底：定位到末尾（currentTime==duration）时 round 可能越界到 frameCount，统一收口到最后一帧。
  if (frameCount.value > 0) landed = Math.min(frameCount.value - 1, landed);
  // 守卫：若实际定位到的帧仍不是最新目标帧，说明还有更晚的 seek 未完成，
  // 跳过本次，等待最终 seeked 定位到目标帧后再加载（避免加载过期帧）。
  if (pendingSeekFrame >= 0 && landed !== pendingSeekFrame) return;
  pendingSeekFrame = -1;
  currentFrame.value = landed;
  await loadFrameAnnotations(landed);
}

function goToFrame(idx: number) {
  if (idx < 0 || (frameCount.value > 0 && idx >= frameCount.value)) return;
  currentFrame.value = idx;
  pendingSeekFrame = idx;
  const ve = canvasRef.value?.getVideoEl?.();
  if (ve) ve.currentTime = frameIndexToTime(idx, videoFps.value);
}

// ==== 视频播放器控制 ====
let boundVideoEl: HTMLVideoElement | null = null;
function bindVideoEvents(el: HTMLVideoElement) {
  if (boundVideoEl === el) return;
  boundVideoEl = el;
  el.addEventListener("play", onVideoPlay);
  el.addEventListener("pause", onVideoPause);
  el.addEventListener("timeupdate", onVideoTimeUpdate);
}
function onVideoPlay() {
  videoPlaying.value = true;
}
function onVideoPause() {
  videoPlaying.value = false;
}
function onVideoTimeUpdate() {
  const ve = canvasRef.value?.getVideoEl?.();
  if (ve) videoCurrentTime.value = ve.currentTime;
}
function togglePlay() {
  const ve = canvasRef.value?.getVideoEl?.();
  if (!ve) return;
  if (ve.paused) ve.play().catch(() => {});
  else ve.pause();
}
function onSliderSeek(time: number) {
  const ve = canvasRef.value?.getVideoEl?.();
  if (!ve) return;
  let idx = timeToFrameIndex(time, videoFps.value);
  if (frameCount.value > 0) idx = Math.max(0, Math.min(frameCount.value - 1, idx));
  currentFrame.value = idx;
  pendingSeekFrame = idx;
  ve.currentTime = frameIndexToTime(idx, videoFps.value);
}
function zoomStep(factor: number) {
  const r = canvasR();
  if (!r.width || !r.height) return;
  zoomAt(factor, r.left + r.width / 2, r.top + r.height / 2);
}

function onWheel(e: WheelEvent) {
  if (!cw.value || !ch.value) return;
  const r = canvasR();
  const cx = e.clientX - r.left;
  const cy = e.clientY - r.top;
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  zoomAt(factor, cx, cy);
}
function boxZoom(factor: number, clientX: number, clientY: number) {
  const r = canvasR();
  zoomAt(factor, clientX - r.left, clientY - r.top);
}
function zoomAt(factor: number, cx: number, cy: number) {
  if (!cw.value || !ch.value) return;
  const r = canvasR();
  const newZoom = Math.min(3, Math.max(0.1, canvas.zoom.value * factor));
  // 光标下的图像点（归一化）
  const off = canvas.imageOffset(r.width, r.height);
  const ix = (cx - off.left) / dw.value;
  const iy = (cy - off.top) / dh.value;
  canvas.zoom.value = newZoom;
  canvas.dw.value = cw.value * newZoom;
  canvas.dh.value = ch.value * newZoom;
  // 缩放后让该图像点仍落在光标位置（修正 pan）
  const newLeft = cx - ix * canvas.dw.value;
  const newTop = cy - iy * canvas.dh.value;
  canvas.setPan(
    newLeft - r.width / 2 + canvas.dw.value / 2,
    newTop - r.height / 2 + canvas.dh.value / 2
  );
}

function onRootContextmenu(e: MouseEvent) {
  // 画笔工具下：右键弹出画笔大小设置
  if (isBrushTool.value) {
    openBrushPopover(e);
    return;
  }
  const el = (e.target as Element).closest?.("[data-ann-id]");
  if (!el) return;
  const id = el.getAttribute("data-ann-id");
  if (!id) return;
  const ann = store.annotations.find((a) => a.id === id);
  if (!ann) return;
  openContextMenu(e, ann);
}

async function onImgError() {
  const imageId = store.currentImageId;
  if (!imageId) return;
  if (!fullUrlCache.has(imageId)) {
    imageLoaded.value = false;
    return;
  }
  fullUrlCache.delete(imageId);
  try {
    const r = await props.api.getPresignedUrl(imageId, store.taskId);
    const fu = r?.data?.data?.url || "";
    if (fu) {
      addToCache(imageId, fu);
      imgUrl.value = fu;
    }
  } catch {
    /* handled by interceptor */
  }
}

async function loadCurrentImage(imageId: number) {
  const myToken = ++loadImgToken;
  resetDrawingState();
  // 切图：先释放上一张锁
  if (lockedImageId && lockedImageId !== imageId) unlockCurrent();
  imgUrl.value = "";
  imageLoaded.value = false;
  fittedForImage = false;
  store.selectedAnnotationId = "";
  store.annotations = [];
  store.unsaved = false;
  lockedByOther.value = false;
  lockedByUser.value = null;
  const imgInfo = store.images.find((i) => i.id === imageId);
  if (imgInfo?.width && imgInfo?.height) canvas.setImageSize(imgInfo.width, imgInfo.height);
  // 先显示缩略图（秒开）；无缩略图则留空，由后续全图填充
  imgUrl.value = imgInfo?.thumbnail_url || "";
  try {
    // 已缓存的全图 URL：直接显示，秒开
    const cachedUrl = fullUrlCache.get(imageId);
    if (cachedUrl) {
      imgUrl.value = cachedUrl;
    } else if (!imgInfo?.thumbnail_url) {
      // 无缩略图：去请求全图
      const r = await props.api.getPresignedUrl(imageId, store.taskId);
      if (myToken !== loadImgToken) return;
      const fu = r?.data?.data?.url || "";
      if (fu) {
        addToCache(imageId, fu);
        imgUrl.value = fu;
      }
    } else {
      // 有缩略图（已显示）：后台请求全图并渐进替换
      props.api
        .getPresignedUrl(imageId, store.taskId)
        .then((r: any) => {
          if (myToken !== loadImgToken) return;
          const fu = r?.data?.data?.url || "";
          if (fu) preloadFull(fu, imageId, myToken);
        })
        .catch(() => {});
    }
    const ar = await props.api.loadAnnotations(store.taskId, imageId);
    if (myToken !== loadImgToken) return;
    store.annotations = ar?.data?.data || [];
    lockedImageId = imageId;
    props.collab?.focus(imageId);
    // 锁定当前图 + 定期续期（后端 5 分钟过期）
    props.api
      .lockImage(imageId, store.taskId)
      .then((lr: any) => {
        if (myToken !== loadImgToken) return;
        const d = lr?.data?.data;
        if (d?.locked) {
          lockedByOther.value = true;
          lockedByUser.value = d.locked_by ?? null;
        } else {
          lockedByOther.value = false;
          lockedByUser.value = null;
        }
        clearLockRenewal();
        lockRenewTimer = window.setInterval(() => {
          props.api.lockImage(imageId, store.taskId).catch(() => {});
        }, 180000);
      })
      .catch(() => {});
  } catch {
    /* handled by interceptor */
  }
}

const IMAGE_PAGE_SIZE = 200;
const imageTotal = ref(0);
const imagePrefetching = ref(false);
let imageLoadedPages = 0;

async function loadImagePage(p: number, silent = false): Promise<any[]> {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return [];
  const r = await props.api.getImages(datasetId, store.taskId, p, IMAGE_PAGE_SIZE, { silent });
  const d = r?.data?.data;
  imageTotal.value = d?.total ?? imageTotal.value;
  return d?.items || [];
}

async function prefetchRemainingImages() {
  if (imagePrefetching.value) return;
  imagePrefetching.value = true;
  try {
    const totalPages = Math.ceil(imageTotal.value / IMAGE_PAGE_SIZE);
    for (let p = imageLoadedPages + 1; p <= totalPages; p++) {
      if (unmounted) return;
      try {
        const items = await loadImagePage(p, true);
        if (unmounted) return;
        if (items.length) store.images.push(...items);
        imageLoadedPages = p;
      } catch {
        return;
      }
      await new Promise((res) => setTimeout(res, 800));
    }
  } finally {
    imagePrefetching.value = false;
  }
}

async function ensureMoreImages(idx: number) {
  const datasetId = store.task?.dataset_id;
  if (!datasetId || imagePrefetching.value || unmounted) return;
  const totalPages = Math.ceil(imageTotal.value / IMAGE_PAGE_SIZE);
  if (imageLoadedPages >= totalPages) return;
  if (idx < store.images.length - 10) return;
  try {
    const items = await loadImagePage(imageLoadedPages + 1);
    if (items.length) store.images.push(...items);
    imageLoadedPages += 1;
  } catch {
    /* ignore */
  }
}

async function fetchTaskProgress() {
  try {
    const r = await props.api.getTaskProgress(store.taskId);
    const d = r?.data?.data;
    if (d) {
      store.totalCount = d.total_images ?? store.totalCount;
      store.annotatedCount = d.annotated_images ?? store.annotatedCount;
    }
  } catch {
    /* ignore */
  }
}

async function initVideo() {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return;
  const vr = await getVideoList(datasetId);
  const items = vr?.data?.data?.items || [];
  const vid = items[0];
  if (!vid) return;
  videoId.value = vid.id;
  const dr = await getVideoDetail(vid.id);
  const d = dr?.data?.data;
  videoFps.value = d?.fps || 1;
  frameCount.value = d?.frame_count || 0;
  videoDuration.value = d?.duration || 0;
  if (d?.width && d?.height) canvas.setImageSize(d.width, d.height);
  const ur = await getVideoPlayUrl(vid.id);
  videoUrl.value = ur?.data?.data?.play_url || "";
  store.totalCount = 1;
  store.annotatedCount = 0;
  currentFrame.value = 0;
  await loadFrameAnnotations(0);
  lockCurrentVideo(vid.id);
}

async function init() {
  store.reset();
  store.taskId = props.taskId;
  store.loading = true;
  try {
    const dr = await props.api.getTaskDetail(props.taskId);
    const t = dr?.data?.data;
    if (!t) return;
    store.task = t;
    props.collab?.connect(store.taskId);
    if (isVideoEventTask.value) {
      imageTotal.value = 0;
      imageLoadedPages = 0;
      await initVideoEvent();
      return;
    }
    if (isVideoTask.value) {
      imageTotal.value = 0;
      imageLoadedPages = 0;
      await initVideo();
      return;
    }
    if (isAudioTask.value) {
      imageTotal.value = 0;
      imageLoadedPages = 0;
      await initAudio();
      return;
    }
    if (isTimeSeriesTask.value) {
      imageTotal.value = 0;
      imageLoadedPages = 0;
      await initTimeSeries();
      return;
    }
    if (isTextTask.value) {
      await initText();
      return;
    }
    imageTotal.value = 0;
    imageLoadedPages = 0;
    const imgs = await loadImagePage(1);
    store.images = imgs;
    imageLoadedPages = 1;
    store.totalCount = imageTotal.value;
    store.annotatedCount = store.images.filter((i) => i.status === "annotated").length;
    if (store.images.length) {
      store.currentImageIndex = 0;
      await loadCurrentImage(store.images[0].id);
      prefetchNeighbors();
    }
    fetchTaskProgress();
    prefetchRemainingImages();
  } catch {
    /* handled */
  } finally {
    store.loading = false;
  }
}

async function initText() {
  const datasetId = store.task?.dataset_id;
  if (!datasetId) return;
  resetDrawingState();
  const lr = await getDocumentList(datasetId);
  const items = lr?.data?.data?.items || [];
  const doc = items[0];
  if (!doc) return;
  documentId.value = doc.id;
  // 按 spec「list → detail → content」：列表仅作筛选定位，文档元数据以 detail 为准
  const dr = await getDocumentDetail(doc.id);
  docMeta.value = dr?.data?.data ?? doc;
  const cr = await getDocumentContent(doc.id);
  docContent.value = cr?.data ?? "";
  const ar = await loadTextAnnotations(store.taskId, doc.id);
  store.annotations = (ar?.data?.data?.annotation_data || []) as any;
  store.selectedAnnotationId = "";
  store.unsaved = false;
  store.totalCount = 1;
  store.annotatedCount = store.annotations.length ? 1 : 0;
  // 按文档整体加锁 + 定期续期（后端 5 分钟过期）
  lockDocument(doc.id)
    .then((lr: any) => {
      const d = lr?.data?.data;
      if (d?.locked) {
        lockedByOther.value = true;
        lockedByUser.value = d.locked_by ?? null;
      } else {
        lockedByOther.value = false;
        lockedByUser.value = null;
      }
      lockedDocumentId = doc.id;
      clearLockRenewal();
      lockRenewTimer = window.setInterval(() => {
        lockDocument(doc.id).catch(() => {});
      }, 180000);
    })
    .catch(() => {});
}

function goToImage(idx: number) {
  if (idx < 0 || idx >= store.images.length) return;
  const doSwitch = () => {
    store.currentImageIndex = idx;
    ensureMoreImages(idx);
    loadCurrentImage(store.images[idx].id);
    prefetchNeighbors();
  };
  if (store.unsaved) {
    ElMessageBox({
      title: "未保存",
      message: "当前图有未保存的修改，是否先保存？",
      confirmButtonText: "保存并切换",
      cancelButtonText: "不保存",
      distinguishCancelAndClose: true,
      closeOnClickModal: false,
      type: "warning",
    })
      .then(async (action: any) => {
        if (action === "confirm") await saveAnn();
        if (action === "confirm" || action === "cancel") doSwitch();
        // action === 'close' => 留在当前图，不切换
      })
      .catch(() => {});
    return;
  }
  doSwitch();
}
function prevImg() {
  if (store.currentImageIndex > 0) goToImage(store.currentImageIndex - 1);
}
function nextImg() {
  if (store.currentImageIndex < store.images.length - 1) goToImage(store.currentImageIndex + 1);
}

async function saveAnn() {
  if (!store.taskId) return;
  if (lockedByOther.value) return;
  if (isVideoEventTask.value) {
    if (!videoEventId.value) return;
    await saveVideoEventAnnotations({
      task_id: store.taskId,
      video_id: videoEventId.value,
      segments: store.annotations as any,
    });
    store.unsaved = false;
    lastSavedKey = annotKey();
    historyStack = [lastSavedKey];
    historyIndex = 0;
    return;
  }
  if (isVideoTask.value) {
    if (!videoId.value) return;
    await saveVideoAnnotations(
      store.taskId,
      videoId.value,
      currentFrame.value,
      store.annotations as any
    );
    store.unsaved = false;
    lastSavedKey = annotKey();
    historyStack = [lastSavedKey];
    historyIndex = 0;
    return;
  }
  if (isAudioTask.value) {
    if (!audioId.value) return;
    await saveAudioAnnotations({
      task_id: store.taskId,
      audio_id: audioId.value,
      annotations: store.annotations as any,
    });
    store.unsaved = false;
    lastSavedKey = annotKey();
    historyStack = [lastSavedKey];
    historyIndex = 0;
    return;
  }
  if (isTextTask.value) {
    if (!documentId.value) return;
    await saveTextAnnotations({
      task_id: store.taskId,
      document_id: documentId.value,
      annotations: store.annotations as any,
    });
    store.unsaved = false;
    lastSavedKey = annotKey();
    historyStack = [lastSavedKey];
    historyIndex = 0;
    return;
  }
  if (isTimeSeriesTask.value) {
    if (!timeSeriesId.value) return;
    await saveTimeSeriesAnnotations({
      task_id: store.taskId,
      time_series_id: timeSeriesId.value,
      annotations: store.annotations as any,
    });
    store.unsaved = false;
    lastSavedKey = annotKey();
    historyStack = [lastSavedKey];
    historyIndex = 0;
    return;
  }
  if (!store.currentImageId) return;
  await props.api.saveAnnotations(store.taskId, store.currentImageId, store.annotations);
  store.unsaved = false;
  lastSavedKey = annotKey();
  historyStack = [lastSavedKey];
  historyIndex = 0;
  const img = store.images[store.currentImageIndex];
  if (img) {
    // 保存后本地同步该图的标注状态与「标注人/标注时间」
    // （后端 get_images 以最新标注记录的 created_id/created_time 填充，此处保持一致）
    const hasData = store.annotations.length > 0;
    img.status = hasData ? "annotated" : "unannotated";
    const ui = useUserStore().basicInfo;
    img.updated_by =
      hasData && ui?.id ? { id: ui.id, name: ui.name || ui.username } : null;
    img.updated_time = hasData ? new Date().toISOString() : null;
  }
  fetchTaskProgress();
}

function openHistory() {
  // 历史抽屉由外层路由包装层承载（保持组件库解耦），此处仅触发事件
  emit("open-history");
}

// ==== 绘制/编辑（同阶段0-5a 逻辑） ====
function commitCreated(created: Annotation | null): void {
  if (!created || !plugin.value.create(created)) return;
  // 仅当标注尚未有真实类别（绘制工具以 class_id:0 占位）时才用当前选中类别补齐，
  // 避免覆盖面板等已写入的（如背景）真实类 id。
  if (!created.class_id && selectedClassId.value != null) created.class_id = selectedClassId.value;
  if (created.type === "Ocr") {
    store.annotations.push(created);
    pendingOcr = created;
    ocrInput.value = created.text || "";
    ocrInputVisible.value = true;
    return;
  }
  store.annotations.push(created);
  store.markUnsaved();
  pushHistory();
}
function onDblClick(e: MouseEvent) {
  e.preventDefault();
  // 双击已有标注 → 打开编辑弹窗
  const hit = (e.target as Element)?.closest?.("[data-ann-id]");
  if (hit) {
    const id = hit.getAttribute("data-ann-id");
    const ann = store.annotations.find((a) => a.id === id);
    if (ann) {
      openEditDialog(ann);
      return;
    }
  }
  const tool = activeTool.value;
  if (tool && TASKS_REQUIRE_CLASS.has(plugin.value.name) && taskClasses.value.length === 0) {
    ElMessage.warning("请先创建至少一个类别，再进行标注");
    return;
  }
  if (tool) {
    const p = toImagePoint(e);
    const created = tool.dblclick?.({
      point: p ?? undefined,
      event: e,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
    });
    if (created) commitCreated(created);
    return;
  }
}
function onCanvasDown(e: MouseEvent) {
  e.preventDefault();
  if (e.button !== 0 || lockedByOther.value) return;
  closeBrushPopover();
  const p = toImagePoint(e);
  if (!p) return;
  store.selectedAnnotationId = "";
  // 按住空格 = 平移（类似 PS 抓手），无需切到平移工具
  if (spaceHeld.value) {
    panState = {
      startX: e.clientX,
      startY: e.clientY,
      px: canvas.panX.value,
      py: canvas.panY.value,
    };
    return;
  }
  if (currentTool.value === "pan") {
    panState = {
      startX: e.clientX,
      startY: e.clientY,
      px: canvas.panX.value,
      py: canvas.panY.value,
    };
    return;
  }
  if (currentTool.value === "zoom") {
    boxZoom(e.altKey ? 0.8 : 1.25, e.clientX, e.clientY);
    return;
  }
  const tool = activeTool.value;
  if (tool && TASKS_REQUIRE_CLASS.has(plugin.value.name) && taskClasses.value.length === 0) {
    ElMessage.warning("请先创建至少一个类别，再进行标注");
    return;
  }
  if (tool) {
    const created = tool.down?.({
      point: p,
      event: e,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
      cw: cw.value,
      ch: ch.value,
      zoom: canvas.zoom.value,
    });
    if (created) commitCreated(created);
    return;
  }
}
function cancelOcr() {
  if (pendingOcr) {
    const i = store.annotations.findIndex((a) => a.id === pendingOcr!.id);
    if (i >= 0) store.annotations.splice(i, 1);
    store.markUnsaved();
  }
  pendingOcr = null;
  ocrInputVisible.value = false;
}
function confirmOcr() {
  if (pendingOcr) {
    pendingOcr.text = ocrInput.value;
    pendingOcr.class_id = selectedClassId.value ?? pendingOcr.class_id;
    store.markUnsaved();
    pushHistory();
  }
  pendingOcr = null;
  ocrInputVisible.value = false;
}
function onAnnDown(e: MouseEvent, ann: Annotation) {
  if (e.button !== 0 || lockedByOther.value) return;
  if (spaceHeld.value) {
    panState = {
      startX: e.clientX,
      startY: e.clientY,
      px: canvas.panX.value,
      py: canvas.panY.value,
    };
    return;
  }
  store.selectedAnnotationId = ann.id;
  dragState = {
    type: "move",
    ann: draftOf(ann),
    handle: "",
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}
function onHandleDown(e: MouseEvent, ann: Annotation, handle: string) {
  if (e.button !== 0 || lockedByOther.value) return;
  if (spaceHeld.value) {
    panState = {
      startX: e.clientX,
      startY: e.clientY,
      px: canvas.panX.value,
      py: canvas.panY.value,
    };
    return;
  }
  store.selectedAnnotationId = ann.id;
  if (handle.startsWith("kpb-")) {
    const h = handle.replace("kpb-", "");
    if (h === "move") {
      dragState = {
        type: "kp-move",
        ann: draftOf(ann),
        handle: "",
        startX: e.clientX,
        startY: e.clientY,
        orig: JSON.parse(JSON.stringify(ann)),
      };
    } else {
      dragState = {
        type: "kp-resize",
        ann: draftOf(ann),
        handle: h,
        startX: e.clientX,
        startY: e.clientY,
        orig: JSON.parse(JSON.stringify(ann)),
      };
    }
    return;
  }
  if (handle.startsWith("kp-")) {
    const idx = handle.replace("kp-", "");
    if (e.altKey) {
      const interaction = plugin.value.interaction;
      if (interaction?.vertexDelete) {
        interaction.vertexDelete(ann, idx);
        store.markUnsaved();
        pushHistory();
        return;
      }
    }
    dragState = {
      type: "kp-vertex",
      ann: draftOf(ann),
      handle: idx,
      startX: e.clientX,
      startY: e.clientY,
      orig: JSON.parse(JSON.stringify(ann)),
    };
    return;
  }
  if (handle.startsWith("ocr-")) {
    const rest = handle.replace("ocr-", "");
    // 矩形角点（含 l/r/t/b）→ 整体缩放；多边形顶点 → 逐点编辑
    if (/^[lrtb]{1,2}$/.test(rest)) {
      dragState = {
        type: "resize",
        ann: draftOf(ann),
        handle: rest,
        startX: e.clientX,
        startY: e.clientY,
        orig: JSON.parse(JSON.stringify(ann)),
      };
      return;
    }
    const idx = Number(rest);
    if (e.altKey) {
      const interaction = plugin.value.interaction;
      if (interaction?.vertexDelete) {
        interaction.vertexDelete(ann, String(idx));
        store.markUnsaved();
        pushHistory();
        return;
      }
      if (ann.points?.length > 4) {
        ann.points.splice(idx, 1);
        store.markUnsaved();
        pushHistory();
      }
      return;
    }
    dragState = {
      type: "poly-vertex",
      ann: draftOf(ann),
      handle: String(idx),
      startX: e.clientX,
      startY: e.clientY,
      orig: JSON.parse(JSON.stringify(ann)),
    };
    return;
  }
  if (handle.startsWith("poly-ins-")) {
    const interaction = plugin.value.interaction;
    if (interaction?.vertexInsert) {
      interaction.vertexInsert(ann, handle.replace("poly-ins-", ""));
      store.markUnsaved();
      return;
    }
    const idx = parseInt(handle.replace("poly-ins-", ""), 10);
    if (!isNaN(idx) && ann.points?.length) {
      const a = ann.points[idx],
        b = ann.points[(idx + 1) % ann.points.length];
      ann.points.splice(idx + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
      store.markUnsaved();
    }
    return;
  }
  if (handle.startsWith("poly-")) {
    const idx = Number(handle.replace("poly-", ""));
    if (e.altKey) {
      const interaction = plugin.value.interaction;
      if (interaction?.vertexDelete) {
        interaction.vertexDelete(ann, String(idx));
        store.markUnsaved();
        pushHistory();
        return;
      }
      if (ann.points?.length > 3) {
        ann.points.splice(idx, 1);
        store.markUnsaved();
        pushHistory();
      }
      return;
    }
    dragState = {
      type: "poly-vertex",
      ann: draftOf(ann),
      handle: String(idx),
      startX: e.clientX,
      startY: e.clientY,
      orig: JSON.parse(JSON.stringify(ann)),
    };
    return;
  }
  if (handle === "cuboid-h") {
    dragState = {
      type: "cuboid-height",
      ann: draftOf(ann),
      handle: "",
      startX: e.clientX,
      startY: e.clientY,
      orig: JSON.parse(JSON.stringify(ann)),
    };
    return;
  }
  dragState = {
    type: "resize",
    ann: draftOf(ann),
    handle,
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}
function onRotateDown(e: MouseEvent, ann: Annotation) {
  if (e.button !== 0 || lockedByOther.value) return;
  if (spaceHeld.value) {
    panState = {
      startX: e.clientX,
      startY: e.clientY,
      px: canvas.panX.value,
      py: canvas.panY.value,
    };
    return;
  }
  store.selectedAnnotationId = ann.id;
  dragState = {
    type: "rotate",
    ann: draftOf(ann),
    handle: "",
    startX: e.clientX,
    startY: e.clientY,
    orig: JSON.parse(JSON.stringify(ann)),
  };
}
let pendingMove: MouseEvent | null = null;
let moveRafId = 0;
function scheduleMove(e: MouseEvent) {
  pendingMove = e;
  if (moveRafId) return;
  moveRafId = requestAnimationFrame(() => {
    moveRafId = 0;
    const ev = pendingMove;
    pendingMove = null;
    if (ev) onMove(ev);
  });
}
function onMove(e: MouseEvent) {
  e.preventDefault();
  if (lockedByOther.value) return;
  const crossPt = toImagePoint(e);
  if (crossPt) {
    crosshair.x = crossPt.x;
    crosshair.y = crossPt.y;
  }
  if (panState) {
    canvas.setPan(
      panState.px + (e.clientX - panState.startX),
      panState.py + (e.clientY - panState.startY)
    );
    return;
  }
  const ip = toImagePoint(e);
  if (ip) {
    cursorPos.x = Math.round(ip.x * (canvas.cw.value || 0));
    cursorPos.y = Math.round(ip.y * (canvas.ch.value || 0));
  }
  const tool = activeTool.value;
  if (tool) {
    tool.move?.({
      point: ip,
      event: e,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
      cw: cw.value,
      ch: ch.value,
      zoom: canvas.zoom.value,
    });
    return;
  }
  if (dragState) {
    const o = dragState.orig;
    const ann = dragState.ann;
    const dx = (e.clientX - dragState.startX) / dw.value;
    const dy = (e.clientY - dragState.startY) / dh.value;
    const nc = (v: number) => Math.max(0, Math.min(1, v));
    const movePoints = (pts: any[]) =>
      pts.map((p: any) => ({ ...p, x: nc(p.x + dx), y: nc(p.y + dy) }));

    if (dragState.type === "kp-move") {
      const interaction = plugin.value.interaction;
      if (interaction?.move) {
        interaction.move({
          ann,
          orig: o,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
      if (ann.bounding_box) {
        ann.bounding_box.cx = nc(o.bounding_box.cx + dx);
        ann.bounding_box.cy = nc(o.bounding_box.cy + dy);
      }
      ann.keypoints = (o.keypoints || []).map((k: any) => ({
        ...k,
        x: nc(k.x + dx),
        y: nc(k.y + dy),
      }));
      triggerRef(draftAnn);
      return;
    }
    if (dragState.type === "kp-resize") {
      const interaction = plugin.value.interaction;
      if (interaction?.resize) {
        interaction.resize({
          ann,
          orig: o,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
    }
    if (dragState.type === "kp-vertex") {
      const interaction = plugin.value.interaction;
      if (interaction?.vertexMove) {
        interaction.vertexMove({
          ann: dragState.ann,
          orig: dragState.orig,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          point: toImagePoint(e) ?? undefined,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
    }
    if (dragState.type === "poly-vertex") {
      const interaction = plugin.value.interaction;
      if (interaction?.vertexMove) {
        interaction.vertexMove({
          ann: dragState.ann,
          orig: dragState.orig,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          point: toImagePoint(e) ?? undefined,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
    }
    if (dragState.type === "cuboid-height") {
      const nc = (v: number) => Math.max(0, Math.min(1, v));
      const dy = (e.clientY - dragState.startY) / dh.value;
      const o = dragState.orig;
      dragState.ann.top_cy = nc((o.top_cy ?? 0) - dy);
      dragState.ann.depth = dragState.ann.top_cy;
      triggerRef(draftAnn);
      return;
    }
    if (dragState.type === "rotate") {
      const interaction = plugin.value.interaction;
      if (interaction?.rotate) {
        const r = canvasR();
        const off = canvas.imageOffset(r.width, r.height);
        interaction.rotate({
          ann: dragState.ann,
          orig: dragState.orig,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          center: {
            x: r.left + off.left + dragState.ann.cx * dw.value,
            y: r.top + off.top + dragState.ann.cy * dh.value,
          },
          start: { x: dragState.startX, y: dragState.startY },
          client: { x: e.clientX, y: e.clientY },
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
    }
    if (dragState.type === "move") {
      const interaction = plugin.value.interaction;
      if (interaction?.move) {
        interaction.move({
          ann,
          orig: o,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
      // 默认（无插件交互）
      if (ann.type === "AxisAlignedBox") {
        ann.x1 = nc(o.x1 + dx);
        ann.x2 = nc(o.x2 + dx);
        ann.y1 = nc(o.y1 + dy);
        ann.y2 = nc(o.y2 + dy);
      } else if (ann.type === "RotatedBox") {
        ann.cx = nc(o.cx + dx);
        ann.cy = nc(o.cy + dy);
      } else if (ann.type === "Polygon") {
        ann.points = movePoints(o.points);
      } else if (ann.type === "Ocr") {
        ann.points = movePoints(o.points);
      }
      triggerRef(draftAnn);
      return;
    }
    if (dragState.type === "resize") {
      const interaction = plugin.value.interaction;
      if (interaction?.resize) {
        interaction.resize({
          ann,
          orig: o,
          handle: dragState.handle,
          dx,
          dy,
          cw: cw.value,
          ch: ch.value,
          point: toImagePoint(e) ?? undefined,
          trigger: () => triggerRef(draftAnn),
        });
        return;
      }
      if (ann.type === "AxisAlignedBox") {
        if (dragState.handle.includes("l")) ann.x1 = nc(Math.min(o.x2 - 0.01, o.x1 + dx));
        if (dragState.handle.includes("r")) ann.x2 = nc(Math.max(o.x1 + 0.01, o.x2 + dx));
        if (dragState.handle.includes("t")) ann.y1 = nc(Math.min(o.y2 - 0.01, o.y1 + dy));
        if (dragState.handle.includes("b")) ann.y2 = nc(Math.max(o.y1 + 0.01, o.y2 + dy));
      } else if (ann.type === "Ocr") {
        const ox = {
          x1: Math.min(...o.points.map((p: any) => p.x)),
          x2: Math.max(...o.points.map((p: any) => p.x)),
        };
        const oy = {
          y1: Math.min(...o.points.map((p: any) => p.y)),
          y2: Math.max(...o.points.map((p: any) => p.y)),
        };
        let x1 = ox.x1,
          y1 = oy.y1,
          x2 = ox.x2,
          y2 = oy.y2;
        if (dragState.handle.includes("l")) x1 = nc(Math.min(x2 - 0.01, x1 + dx));
        if (dragState.handle.includes("r")) x2 = nc(Math.max(x1 + 0.01, x2 + dx));
        if (dragState.handle.includes("t")) y1 = nc(Math.min(y2 - 0.01, y1 + dy));
        if (dragState.handle.includes("b")) y2 = nc(Math.max(y1 + 0.01, y2 + dy));
        ann.points = [
          { x: x1, y: y1 },
          { x: x2, y: y1 },
          { x: x2, y: y2 },
          { x: x1, y: y2 },
        ];
      }
      triggerRef(draftAnn);
      return;
    }
  }
}
function onUp(e: MouseEvent) {
  if (panState) {
    panState = null;
    return;
  }
  const tool = activeTool.value;
  if (tool) {
    const created = tool.up?.({
      event: e,
      point: toImagePoint(e) ?? undefined,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
      cw: cw.value,
      ch: ch.value,
    });
    if (created) commitCreated(created);
    return;
  }
  if (dragState) {
    const d = draftAnn.value;
    if (d) {
      const target = store.annotations.find((a) => a.id === d.id);
      if (target) {
        Object.assign(target, d);
        store.markUnsaved();
        pushHistory();
        // 拖拽/缩放当前帧轨迹框后，使其轨迹连线实时跟随（局部刷新，仅重算轨迹层）
        if (isVideoTask.value && (d as any)?.track_id) bumpTrack();
      }
    }
    draftAnn.value = null;
  }
  dragState = null;
}

// ==== 历史（undo/redo）====
const editAnnVisible = ref(false);
const editPos = reactive({ x: 0, y: 0 });
const editForm = reactive({ ann: null as any, class_id: 0, text: "", keypoints: [] as any[] });
const KP_VISIBILITY = ["Visible", "Occluded", "Hidden"];
const annMenu = reactive({ visible: false, ann: null as any, x: 0, y: 0 });

function openContextMenu(e: MouseEvent, ann: Annotation) {
  annMenu.ann = ann;
  annMenu.x = e.clientX;
  annMenu.y = e.clientY;
  annMenu.visible = true;
}
function closeMenu() {
  annMenu.visible = false;
}
function annScreenPos(ann: any) {
  if (!dw.value || !dh.value) return { x: 0, y: 0 };
  const r = canvasR();
  const off = canvas.imageOffset(r.width, r.height);
  let nx = 0.5,
    ny = 0.5;
  if (ann.x1 !== undefined) {
    nx = (ann.x1 + ann.x2) / 2;
    ny = (ann.y1 + ann.y2) / 2;
  } else if (ann.cx !== undefined) {
    nx = ann.cx;
    ny = ann.cy;
  } else if (ann.bounding_box) {
    nx = ann.bounding_box.cx;
    ny = ann.bounding_box.cy;
  } else if (Array.isArray(ann.points) && ann.points.length) {
    nx = ann.points.reduce((s: number, p: any) => s + p.x, 0) / ann.points.length;
    ny = ann.points.reduce((s: number, p: any) => s + p.y, 0) / ann.points.length;
  }
  return { x: r.left + off.left + nx * dw.value, y: r.top + off.top + ny * dh.value };
}

// HTML 标签覆盖层：用固定屏幕像素字号，不随 zoom 缩放，背景 span 自动贴合文字
function tagStyle(ann: any): any {
  let lx = 0,
    ty = 0;
  // 标签层 .ann-label-layer 位于画布容器内（absolute inset:0），坐标相对画布容器，不含浏览器视口偏移
  if (dw.value && dh.value) {
    void rectTick.value;
    const r = canvasR();
    const off = canvas.imageOffset(r.width, r.height);
    let nx = 0,
      ny = 0;
    const anchor = plugin.value.interaction?.tagAnchor?.(ann, cw.value, ch.value);
    if (anchor) {
      nx = anchor.x;
      ny = anchor.y;
    } else if (ann.x1 !== undefined) {
      nx = ann.x1;
      ny = ann.y1;
    } else if (ann.type === "RotatedBox" && ann.cx !== undefined) {
      // 像素空间计算左上角，再转回归一化（非方形图片必做 cw/ch 换算）
      const hw = (ann.width * cw.value) / 2;
      const hh = (ann.height * ch.value) / 2;
      const cos = Math.cos(ann.angle),
        sin = Math.sin(ann.angle);
      nx = (ann.cx * cw.value + -hw * cos - -hh * sin) / cw.value;
      ny = (ann.cy * ch.value + -hw * sin + -hh * cos) / ch.value;
    } else if (ann.cx !== undefined) {
      nx = ann.cx;
      ny = ann.cy;
    } else if (ann.bounding_box) {
      nx = ann.bounding_box.cx - ann.bounding_box.width / 2;
      ny = ann.bounding_box.cy - ann.bounding_box.height / 2;
    } else if (Array.isArray(ann.points) && ann.points.length) {
      const xs = ann.points.map((p: any) => p.x);
      const ys = ann.points.map((p: any) => p.y);
      nx = Math.min(...xs);
      ny = Math.min(...ys);
    }
    lx = off.left + nx * dw.value;
    ty = off.top + ny * dh.value;
  }
  return {
    left: lx + "px",
    top: ty + "px",
    transform: "translateY(-100%)",
    background: clsColor(ann),
    color: "#fff",
    fontSize: annSettings.labelFontSize + "px",
    lineHeight: "1.2",
    padding: "1px 5px",
    borderRadius: "2px",
    cursor: "default",
    pointerEvents: "none",
    whiteSpace: "nowrap" as const,
    border: "1px solid " + clsColor(ann),
  };
}
function openEditDialog(ann: any) {
  if (!ann) return;
  editForm.ann = ann;
  editForm.class_id = ann.class_id;
  editForm.text = ann.text || "";
  editForm.keypoints =
    ann.type === "Keypoint" ? JSON.parse(JSON.stringify(ann.keypoints || [])) : [];
  const pos = annScreenPos(ann);
  editPos.x = pos.x;
  editPos.y = pos.y;
  editAnnVisible.value = true;
}
function menuEdit() {
  const ann = annMenu.ann;
  closeMenu();
  openEditDialog(ann);
}
function menuDelete() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  deleteSelected();
}
function menuCopy() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  copySelected();
}
function layerMove(ann: any, toTop: boolean) {
  if (!ann) return;
  store.selectedAnnotationId = ann.id;
  const rest = store.annotations.filter((a) => a.id !== ann.id);
  store.annotations = toTop ? [ann, ...rest] : [...rest, ann];
  store.markUnsaved();
  pushHistory();
}
function menuLayerTop() {
  const ann = annMenu.ann;
  closeMenu();
  layerMove(ann, true);
}
function menuLayerBottom() {
  const ann = annMenu.ann;
  closeMenu();
  layerMove(ann, false);
}
function deleteById(id: string) {
  deleteAnnotation(id);
}
// ==== 视频目标跟踪：关联到轨迹 / 取消关联 ====
const trackDialogVisible = ref(false);
const trackDialogMode = ref<"new" | "existing">("new");
const trackDialogExisting = ref("");
const trackDialogAnn = ref<Annotation | null>(null);
function menuTrack() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann || ann.type !== "AxisAlignedBox") return;
  store.selectedAnnotationId = ann.id;
  trackDialogAnn.value = ann;
  trackDialogMode.value = ann.track_id ? "existing" : "new";
  trackDialogExisting.value = ann.track_id || "";
  trackDialogVisible.value = true;
}
function confirmTrack() {
  const ann = trackDialogAnn.value;
  if (!ann) return;
  if (trackDialogMode.value === "new") {
    // 新建轨迹：生成唯一 id 并赋给当前框
    ann.track_id = newTrackId();
  } else {
    const tid = trackDialogExisting.value;
    if (!tid) {
      ElMessage.warning("请选择已有轨迹");
      return;
    }
    // 一帧一框一目标：当前帧已含同轨迹的其它框则拒绝（与后端校验一致）
    if (store.annotations.some((a) => a.id !== ann.id && a.track_id === tid)) {
      ElMessage.warning("当前帧已有该轨迹的框，一帧一框一目标");
      return;
    }
    ann.track_id = tid;
  }
  trackDialogVisible.value = false;
  store.markUnsaved();
  pushHistory();
  bumpTrack();
}
function menuClearTrack() {
  const ann = annMenu.ann;
  closeMenu();
  if (!ann) return;
  ElMessageBox.confirm("将取消该框的轨迹关联，此操作只影响当前框，且不可恢复。", "取消轨迹关联", {
    confirmButtonText: "取消关联",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(() => {
      delete ann.track_id;
      store.markUnsaved();
      pushHistory();
      bumpTrack();
    })
    .catch(() => {});
}
// ==== 视频目标跟踪：关键帧线性插值 ====
const interpolateDialogVisible = ref(false);
const interpolateLoading = ref(false);
const interpolateFrameA = ref<number | null>(null);
const interpolateFrameB = ref<number | null>(null);
/** 关键帧候选：选中轨迹已访问的帧号（升序）。 */
const interpolateFrameOptions = computed(() => framesOfTrack(selectedTrackId.value));
/** 切换选中轨迹时，清空残留的 A/B 选择，避免跨轨迹错配。 */
watch(selectedTrackId, () => {
  if (!interpolateDialogVisible.value) {
    interpolateFrameA.value = null;
    interpolateFrameB.value = null;
  }
});
/** 打开插值弹窗：默认取当前帧前后最近的两个该轨迹关键帧。 */
function openInterpolateDialog() {
  const tid = selectedTrackId.value;
  if (!tid) return;
  const frames = framesOfTrack(tid);
  if (frames.length < 2) {
    ElMessage.warning("该轨迹还没有两个已标注关键帧，请先标注两个关键帧");
    return;
  }
  const cur = currentFrame.value;
  // 当前帧本身是该轨迹关键帧时，以其为端点（A 或 B），避免该关键帧被包进 (A,B) 中间区间被插值覆盖
  if (frames.includes(cur)) {
    const next = nearestTrackFrame(frames, cur, 1);
    const prev = nearestTrackFrame(frames, cur, -1);
    if (next != null) {
      // 向后插值：A=当前关键帧，B=其后一关键帧
      interpolateFrameA.value = cur;
      interpolateFrameB.value = next;
    } else {
      // 无后一关键帧则向前插值：A=其前一关键帧，B=当前关键帧
      interpolateFrameA.value = prev ?? frames[0];
      interpolateFrameB.value = cur;
    }
  } else {
    // 当前帧非关键帧：A 取前一关键帧（无则首帧），B 取后一关键帧（无则末帧）
    const prev = nearestTrackFrame(frames, cur, -1);
    const next = nearestTrackFrame(frames, cur, 1);
    interpolateFrameA.value = prev ?? frames[0];
    interpolateFrameB.value = next ?? frames[frames.length - 1];
  }
  interpolateDialogVisible.value = true;
}
/** 提交插值：生成中间帧框并调用后端批量插值接口，局部刷新。 */
async function confirmInterpolate() {
  const tid = selectedTrackId.value;
  if (!tid || !videoId.value || !store.taskId) return;
  const A = interpolateFrameA.value;
  const B = interpolateFrameB.value;
  if (A == null || B == null) {
    ElMessage.warning("请选择关键帧 A 与关键帧 B");
    return;
  }
  if (B <= A) {
    ElMessage.warning("关键帧 B 必须大于关键帧 A");
    return;
  }
  // 两个关键帧都必须含该轨迹的框（从已访问帧缓存读取）
  const boxA = findBoxByTrack(frameCache.get(A) || [], tid);
  const boxB = findBoxByTrack(frameCache.get(B) || [], tid);
  if (!boxA || !boxB) {
    ElMessage.warning(`关键帧 A(${A}) / B(${B}) 必须都含该轨迹的框`);
    return;
  }
  // 计算 (A, B) 之间全部中间帧；排除该轨迹已占据（关键帧）的帧，确保关键帧不被覆盖
  const ownedFrames = new Set(framesOfTrack(tid));
  const middle: number[] = [];
  for (let k = A + 1; k < B; k++) if (!ownedFrames.has(k)) middle.push(k);
  const results = interpolateBoxes(
    { frameIndex: A, box: boxA },
    { frameIndex: B, box: boxB },
    middle
  );
  if (!results.length) {
    ElMessage.warning("两个关键帧之间没有中间帧");
    return;
  }
  const frames = results.map((r) => ({
    frame_index: r.frame_index,
    annotations: r.annotations,
  }));
  await ElMessageBox.confirm(
    `将在关键帧 ${A} 与 ${B} 之间为轨迹插值生成 ${results.length} 个中间帧框（同轨迹覆盖、其它轨迹保留，关键帧不动），且不可恢复。`,
    "插值中间帧",
    { confirmButtonText: "插值", cancelButtonText: "取消", type: "warning" }
  )
    .then(async () => {
      interpolateLoading.value = true;
      try {
        await interpolateVideoFrames({
          task_id: store.taskId,
          video_id: videoId.value!,
          track_id: tid,
          frame_a: A,
          frame_b: B,
          frames,
        });
        // 局部刷新：仅更新被插值的中间帧缓存，与后端合并语义一致——保留其它 track 框、仅替换本 track
        for (const r of results) {
          const existing = frameCache.get(r.frame_index) || [];
          frameCache.set(r.frame_index, [
            ...existing.filter((x) => x.track_id !== tid),
            ...(r.annotations as unknown as Annotation[]),
          ]);
        }
        bumpTrack();
        // 若当前帧恰为一个中间帧，刷新当前帧标注显示
        if (middle.includes(currentFrame.value)) {
          await loadFrameAnnotations(currentFrame.value);
        }
        ElMessage.success(`已插值生成 ${results.length} 个中间帧`);
        interpolateDialogVisible.value = false;
      } finally {
        interpolateLoading.value = false;
      }
    })
    .catch(() => {});
}

function editClassChange() {
  if (editForm.ann) editForm.ann.class_id = editForm.class_id;
}

function editTextChange() {
  if (editForm.ann) editForm.ann.text = editForm.text;
}
function editKpChange() {
  if (editForm.ann?.type === "Keypoint") {
    editForm.ann.keypoints = JSON.parse(JSON.stringify(editForm.keypoints));
  }
}
function editDelete() {
  if (editForm.ann) store.selectedAnnotationId = editForm.ann.id;
  editAnnVisible.value = false;
  deleteSelected();
}
function onKey(e: KeyboardEvent) {
  if (e.code === "Space") {
    e.preventDefault();
    spaceHeld.value = true;
    return;
  }
  if (e.ctrlKey && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveAnn();
    return;
  }
  if (e.ctrlKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    undo();
    return;
  }
  if (e.ctrlKey && e.key.toLowerCase() === "y") {
    e.preventDefault();
    redo();
    return;
  }
  if (e.ctrlKey && e.key.toLowerCase() === "c") {
    e.preventDefault();
    copySelected();
    return;
  }
  if (e.ctrlKey && e.key.toLowerCase() === "v") {
    e.preventDefault();
    pasteCopied();
    return;
  }
  if (e.key === "Escape") {
    resetDrawingState();
    return;
  }
  // 方向键 / a d ：上一下一张（select 工具下）
  if (currentTool.value === "select") {
    if (e.key === "ArrowRight" || e.key.toLowerCase() === "d") {
      nextImg();
      return;
    }
    if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a") {
      prevImg();
      return;
    }
  }
  // 画笔工具 [ ] 调整笔刷粗细
  if (isBrushTool.value) {
    if (e.key === "[") {
      e.preventDefault();
      setBrushSize(brushSizeVal.value - 2);
      return;
    }
    if (e.key === "]") {
      e.preventDefault();
      setBrushSize(brushSizeVal.value + 2);
      return;
    }
  }
  if (e.key === "Delete" || e.key === "Backspace") {
    deleteSelected();
    return;
  }
  // 当前绘制工具专属快捷键（如 keypoint 0/1/2 可见性、ocr t 切换），优先于切工具
  const tool = activeTool.value;
  if (tool) {
    if (tool.keydown?.(e)) return;
  }
  if (["1", "s"].includes(e.key)) setTool("select");
  else if (["2", "b"].includes(e.key)) setTool("box");
  else if (["3", "r"].includes(e.key)) setTool("rotated_box");
  else if (["4", "p"].includes(e.key)) setTool("polygon");
  else if (["5", "k"].includes(e.key)) setTool("keypoint");
  else if (["6", "o"].includes(e.key)) setTool("ocr");
  else if (["7", "c"].includes(e.key)) setTool("classification");
}
function toggleClassification(clsId: number) {
  if (lockedByOther.value) return;
  if (props.config.classificationMode === "single") {
    const existing = store.annotations.find((a) => a.type === "Classification");
    if (existing && existing.class_id === clsId) {
      store.annotations = store.annotations.filter((a) => a.id !== existing.id);
    } else {
      store.annotations = store.annotations.filter((a) => a.type !== "Classification");
      store.annotations.push({ id: crypto.randomUUID(), type: "Classification", class_id: clsId });
    }
  } else {
    const existing = store.annotations.find((a) => a.type === "Classification");
    if (existing) {
      const ids = (existing.class_ids || []) as number[];
      if (ids.includes(clsId)) {
        existing.class_ids = ids.filter((id) => id !== clsId);
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
  store.markUnsaved();
  pushHistory();
}
function isClsSelected(clsId: number) {
  const a = store.annotations.find((x) => x.type === "Classification");
  if (!a) return false;
  if (Array.isArray(a.class_ids)) return a.class_ids.includes(clsId);
  return a.class_id === clsId;
}

onMounted(() => {
  window.addEventListener("mousemove", scheduleMove);
  window.addEventListener("mouseup", onUp);
  window.addEventListener("beforeunload", onBeforeUnload);
  document.addEventListener("keydown", onKey);
  document.addEventListener("keyup", onKeyUp);
  document.addEventListener("click", onDocClick);
  init();
  measureCanvas();
  if (getCanvasEl()) {
    _resizeObserver = new ResizeObserver(() => {
      measureCanvas();
      rectTick.value++;
    });
    _resizeObserver.observe(getCanvasEl()!);
  }
});
onBeforeUnmount(() => {
  unmounted = true;
  fullUrlCache.clear();
  if (moveRafId) {
    cancelAnimationFrame(moveRafId);
    moveRafId = 0;
  }
  pendingMove = null;
  window.removeEventListener("mousemove", scheduleMove);
  window.removeEventListener("mouseup", onUp);
  window.removeEventListener("beforeunload", onBeforeUnload);
  document.removeEventListener("keydown", onKey);
  document.removeEventListener("keyup", onKeyUp);
  document.removeEventListener("click", onDocClick);
  if (_resizeObserver) {
    _resizeObserver.disconnect();
    _resizeObserver = null;
  }
  if (store.unsaved && !lockedByOther.value) {
    if (isVideoEventTask.value && videoEventId.value) {
      saveVideoEventAnnotations({
        task_id: store.taskId,
        video_id: videoEventId.value,
        segments: store.annotations as any,
      }).catch(() => {});
    } else if (isVideoTask.value && videoId.value) {
      saveVideoAnnotations(
        store.taskId,
        videoId.value,
        currentFrame.value,
        store.annotations as any
      ).catch(() => {});
    } else if (isAudioTask.value && audioId.value) {
      saveAudioAnnotations({
        task_id: store.taskId,
        audio_id: audioId.value,
        annotations: store.annotations as any,
      }).catch(() => {});
    } else if (isTextTask.value && documentId.value) {
      saveTextAnnotations({
        task_id: store.taskId,
        document_id: documentId.value,
        annotations: store.annotations as any,
      }).catch(() => {});
    } else if (isTimeSeriesTask.value && timeSeriesId.value) {
      saveTimeSeriesAnnotations({
        task_id: store.taskId,
        time_series_id: timeSeriesId.value,
        annotations: store.annotations as any,
      }).catch(() => {});
    } else if (store.currentImageId) {
      props.api
        .saveAnnotations(store.taskId, store.currentImageId, store.annotations)
        .catch(() => {});
    }
  }
  unlockCurrent();
  props.collab?.close();
});
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (store.unsaved) {
    e.preventDefault();
    e.returnValue = "";
  }
}

defineExpose({
  refreshCurrent() {
    if (store.currentImageId) loadCurrentImage(store.currentImageId);
  },
  getCurrentImageId() {
    return store.currentImageId;
  },
  goToFrame,
});
</script>

<style scoped>
.ann-workbench {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  position: relative;
  background: #fff;
  user-select: none;
  -webkit-user-select: none;
}
.ann-plugin-panel {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 8;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--el-bg-color, #fff);
  box-shadow: var(--el-box-shadow-light);
  border: 1px solid var(--el-border-color-lighter);
  max-width: 240px;
}
.ann-lock-banner {
  margin: 8px;
}
.ann-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.ann-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-text {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
.doc-meta {
  color: var(--el-text-color-regular);
  font-size: 12px;
}
.collab-online {
  color: var(--el-color-success);
  font-size: 12px;
}
.ann-body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.ann-canvas-area {
  flex: 1;
  min-width: 0;
  position: relative;
}
.brush-popover {
  position: absolute;
  z-index: 10;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--el-bg-color, #fff);
  box-shadow: var(--el-box-shadow-light);
  border: 1px solid var(--el-border-color-lighter);
}
.brush-popover-head {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}
.brush-popover-mode {
  margin-bottom: 8px;
}
.brush-popover-body {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brush-cursor-preview {
  border-radius: 50%;
  background: var(--el-color-primary);
  border: 1px solid var(--el-color-primary-light-9);
  flex-shrink: 0;
}
.brush-popover-slider {
  width: 160px;
}
.brush-popover-val {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  min-width: 38px;
}
.brush-popover-tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
  white-space: nowrap;
}
/* 文本模式：允许 CodeMirror 内部拖选文字 */
.text-ner-main {
  overflow: hidden;
  user-select: text;
  -webkit-user-select: text;
}
/* 音频模式：波形渲染区留白 */
.audio-main {
  padding: 12px;
  overflow: hidden;
}
/* 视频事件模式：时间轴渲染区留白 */
.video-event-main {
  padding: 12px;
  overflow: hidden;
}
/* 时间序列模式：折线图渲染区留白 */
.time-series-main {
  padding: 12px;
  overflow: hidden;
}
.ctx-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
}
.ctx-menu {
  position: fixed;
  z-index: 1001;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
  padding: 4px 0;
  min-width: 120px;
}
.ctx-item {
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.ctx-item:hover {
  background: var(--el-fill-color-light);
}
.ctx-danger {
  color: var(--el-color-danger);
}
.cross-svg {
  pointer-events: none;
}
.empty-hint {
  color: #c0c4cc;
  font-size: 12px;
  padding: 4px;
}
.shortcut-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.shortcut-row {
  display: flex;
  gap: 12px;
  align-items: center;
}
.shortcut-keys {
  min-width: 160px;
  color: var(--el-color-primary);
  font-weight: 500;
}
.shortcut-desc {
  color: #606266;
}
.preset-palette {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.preset-dot {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  border: 2px solid transparent;
}
.preset-dot.active {
  border-color: #fff;
  box-shadow: 0 0 0 2px var(--el-color-primary);
}
.custom-color {
  vertical-align: middle;
}
.ann-label-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.track-bar {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-light);
  border-radius: 6px;
  box-shadow: var(--el-box-shadow-light);
}
.track-select {
  width: 150px;
}
.ann-tag {
  position: absolute;
  font-family: "Microsoft YaHei", sans-serif;
  user-select: none;
  box-sizing: border-box;
}
.edit-bubble {
  position: fixed;
  z-index: 2000;
  transform: translate(-50%, calc(-100% - 14px));
  width: 300px;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  box-shadow: var(--el-box-shadow-light);
  padding: 10px 12px;
}
.bubble-arrow {
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  width: 0;
  height: 0;
  border-left: 8px solid transparent;
  border-right: 8px solid transparent;
  border-top: 8px solid var(--el-border-color-light);
}
.bubble-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}
.bubble-close {
  cursor: pointer;
  color: #909399;
}
.bubble-close:hover {
  color: #303133;
}
.bubble-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
