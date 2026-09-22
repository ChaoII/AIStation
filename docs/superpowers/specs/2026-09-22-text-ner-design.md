# 文本 NER 标注（TextNER）设计

> 为标注系统新增「文本」媒体类型，支持用户上传文本文件并在其上做**实体 + 关系**标注（字符级连续 span），产物为 `EntitySpan`（实体）+ `Relation`（关系），导出为**字符级 BIO/BIESO** 序列标注与关系 JSON。

## 1. 背景与目标

当前标注系统仅支持**图片**与**视频**两类媒体：`AnnotationImageModel`（单图）、`AnnotationVideoModel`（视频帧），前端工作台以「图片/视频」光栅化方式加载与标注。平台上**无任何纯文本内容标注能力**（`AnnotationType` 无 text/NER；`TaskMedia` 仅 `image|video`；最近似的 OCR 仍是对图片框区域 + 存转写文本，非文档文本、非 NER）。后端无分词/NER 工具。

**目标**：新增「文本」媒体类型与 `text_ner` 标注任务，让标注者上传文本文件、在正文上拖动鼠标选取**字符级连续 span** 标记为实体（人名/地名/机构…），并把**同句内**两个实体连成**关系**；产物 `EntitySpan` + `Relation`，导出为字符级 BIO/BIESO 序列标注（供 NER 训练/评估）。

**上下文**：本功能是「文本 NER → 音频 → 时间序列」三类标注增量中第一项（视频标注已交付）。后续音频/时间序列不在本 spec。

## 2. 范围

| 项 | 内容 |
|----|------|
| 媒体来源 | 用户上传文本文件至标注数据集（存 RustFS 对象存储），后端探测/规范化文本内容入库 |
| 标注任务 | `text_ner`；`AnnotationType` 新增 `TEXT_NER` |
| 标注形式 | **实体 + 关系**。实体为字符级连续 span（`[start, end)` 字符偏移）；关系连接同句内两个实体 |
| 类型配置 | 任务 `classes` 内同时定义**实体类型**与**关系类型**（`{entities:[...], relations:[...]}`） |
| 内容呈现 | CodeMirror 6 只读文本 + Mark-decoration 高亮实体；鼠标拖选生成实体；点击/列表编辑 |
| 导出 | **字符级 BIO / BIESO** 序列标注（每文本一行 `字符\t标签`，句间空行）+ 关系 `relations.jsonl` |

**非目标（YAGNI）**：
- 不做跨句关系（仅同句内）、不做关系方向/多跳推理、不做嵌套实体的中间表示优化（默认不重叠）。
- 不做自动分词/词性/预标注（仅人工 span 标注）。
- 不做富文本编辑/段落重排（正文只读，禁止改动原文）。
- 不做音频/时间序列（后续子项目）。

## 3. 选型（编辑器/构造器类交互，用户强制：必须成熟第三方库）

文本 span 标注属「编辑器/构造器」类交互，遵循 `AGENTS.md` 强制要求采用成熟第三方库、禁止手写（含用 `el-card`+`el-tree` 自拼）。

| 候选 | 许可 | 最近发布 | 评估 |
|------|------|----------|------|
| **CodeMirror 6**（`@codemirror/*`，本项目已内置） | MIT | 活跃 | 纯文本 doc + 字符 offset；内建「只读 + 鼠标拖选 + `MarkDecoration` 高亮」能力，天然契合「只读文本→选区→实体 span」；已在项目 `components/CodeEditor` 使用 ● **首选** |
| `@tiptap/vue-3` / ProseMirror | MIT | 活跃 | 富文本 HTML 模型，实体锚定与「正文只读、仅选区加 mark」的交互复杂，偏移与后端对齐难 |
| Vue3 专用 NER 标注库 | — | 基本无成熟/活跃 Vue3 库 | 落选 |

**结论**：选 **CodeMirror 6**。理由：现有依赖、纯文本偏移与后端数字对齐（UTF-16 code unit）、只读 + 选区 + decoration 一步到位，避免富文本偏移与只读模式复杂度。

**交互实现**（CodeMirror）：
- 正文 readOnly（`EditorState.readOnly` 阻止输入，但允许鼠标/键盘选区）。
- 通过 `EditorView` 选区（`state.selection`）取 `[from, to)`（UTF-16 offset），生成 `EntitySpan`。
- 用 `MarkDecoration`（`Decoration.mark`，带 `class`）高亮已标注实体 span；`click` 已高亮处弹类型选择。
- **关系连线**：不在文本框上画 SVG 线（避免覆盖层复杂度），改为**右侧关系列表 + 联动高亮**：点击/悬停关系时两端实体高亮（闪烁/更强边框），支持新建/编辑/删除关系。

## 4. 数据模型（后端）

在 `backend/app/api/v1/module_annotation/dataset/model.py` 与 `annotation/model.py`：

- `AnnotationType` 新增：
  ```python
  TEXT_NER = "text_ner"
  ```

- 新增 `AnnotationDocumentModel`（表 `annotation_document`，继承 `ModelMixin, UserMixin`）：
  | 字段 | 类型 | 说明 |
  |------|------|------|
  | `dataset_id` | FK → `annotation_dataset.id` | 所属数据集 |
  | `filename` | String(255) | 原文件名 |
  | `object_key` | String(512) | RustFS key（已规范化为 UTF-8 的文本内容） |
  | `content_hash` | String(64) | sha256 去重 |
  | `encoding` | String(32) | 探测出的原始编码 |
  | `character_count` | Integer | 解码后字符数 |
  | `line_count` | Integer | 行数（`text.count('\n') + 1`） |
  | `status` | Enum(ImageStatus) 复用 | 未标注/进行中/已标注 |
  | `locked_by` / `locked_at` | Integer / DateTime nullable | 文档锁占用者 |
  | `annotation_count` | Integer | 已标注文档数（语义：该文档已被标注） |

  `DatasetModel` 增加 `documents` 关系（`annotation_document`）与 `document_count` 字段。

- `AnnotationRecordModel`（表 `annotation_record`）增加：
  | 字段 | 说明 |
  |------|------|
  | `document_id` | FK → `annotation_document.id`，nullable；与 `image_id`/`video_id` 三方互斥，文本任务用 |

  `annotation_data` 继续为 `JSONB list[dict]`，`text_ner` 形状：
  ```python
  # 实体 span
  {"id": "<uuid>", "type": "EntitySpan", "start": 0, "end": 12, "label_id": 1, "text": "鲁迅"}
  # 关系（from/to 为实体 id，仅同句内）
  {"id": "<uuid>", "type": "Relation", "from": "<实体id>", "to": "<实体id>", "relation_type": 1}
  ```
  索引 `(task_id, document_id, version)`。

### 字符偏移统一（关键坑）

- **全系统字符偏移统一采用 UTF-16 code unit**（与 JS 默认一致，CodeMirror 原生返回 UTF-16 offset）。
- 前端拖选与 `EntitySpan.start/end` 用 CodeMirror 原生 UTF-16 offset。
- 后端存储原样保存；**BIO 导出**与后端校验在需要时做 Python code point ↔ UTF-16 换算（用 `len(s.encode('utf-16-le'))//2` 思路），避免中文/emoji 双端不一致。
- `EntitySpan.text` 冗余存实体原文（前后端渲染/展示用），即使 offset 有偏差也便于核对。

## 5. 任务 `classes` 结构（实体 + 关系）

`text_ner` 任务的 `classes` 为 **dict**（与图片/视频任务的 list 区分）：
```python
classes = {
  "entities": [{"id": 1, "name": "人名", "color": "#f56c6c"}, {"id": 2, "name": "地名", "color": "#409eff"}],
  "relations": [{"id": 1, "name": "任职"}, {"id": 2, "name": "位于"}],
}
```
- 实体类型沿用现有「类别」语义（长度/颜色/类名）。
- 关系类型为**新增**配置段。任务创建 UI 对 `text_ner` 额外提供「关系类型」配置（名称），沿用现有 classes 编辑表单范式。
- 后端 `AnnotationTaskModel.classes` 仍为 `JSONB`，不做结构强约束；但 `text_ner` 分支校验 `classes` 需含 `entities`/`relations` 两个键。

## 6. 后端接口（对齐视频，前缀 `/annotation`）

- **文档上传**：`POST /document/upload`（multipart）→ 校验文本扩展名白名单（`.txt/.text/.md/.csv/.tsv/.json/.log` 等），RustFS 上传，探测编码（utf-8 → gbk → latin1 兜底）并**重新以 UTF-8 规范化写回**，算 `character_count/line_count/content_hash`，入库 `annotation_document`，`document_count` 递增；失败清理。
- **列表**：`GET /document/list?dataset_id=`。
- **详情**：`GET /document/detail/{id}`（元数据，不含全文）。
- **内容**：`GET /document/content/{id}` → `text/plain` 返回 UTF-8 文本全文（前端 CodeMirror 渲染用）。
- **文档锁**：`POST /document/lock/{id}` / `unlock`（复用图片/视频锁语义，按文档整体锁）。
- **标注读写**（`document_id` 锚定）：
  - `POST /annotation/document/save`：`{task_id, document_id, annotations: list[dict]}`（前端显式传 `task_id`，同视频）。
  - `GET /annotation/document/load?task_id=&d_id=`。
  - 两端点先做任务级校验（`_verify_task_access` + `_verify_document_task_relation`，仿视频），再调用 service。

## 7. 前端工作台

### 插件
- `TaskMedia` 新增 `"text"`（`core/types.ts`）。
- 新增 `textNerPlugin`（`annotation/tasks/textNer/index.ts`）：`name:"text_ner"`, `media:"text"`，**自定义渲染器**（CodeMirror 文本 + decoration 高亮）与**工具**（拖选生成实体），`panel` 为实体/关系列表。不含几何 shape，不改 SVG 坐标系路径。

### 工作台 `text` 模式
- `isTextTask = plugin.media === "text"`。
- 文本模式：`getDocumentList → getDocumentDetail → getDocumentContent`，加载全文进 CodeMirror（readOnly + decoration），非光栅 `cw/ch`。
- 实体/关系状态：`annotations` 保存 `EntitySpan[] + Relation[]`（同一 `annotation_data` 列表）。
- 交互：
  1. 鼠标拖选正文段落 → 弹出实体类型选择（`--el-*` 风格，用 task `classes.entities`）→ 生成 `EntitySpan`（decoration 高亮）。
  2. 点击已标注实体 → 可改类型/删除（删除二次确认）。
  3. 右侧 panel：实体列表 + 关系列表；「新建关系」从实体列表选 `from/to`（限同句）+ 选关系类型 → 存 `Relation`；点击关系联动高亮两端实体。
  4. 保存：`saveTextAnnotations(task_id, document_id, annotations)`；文档锁复用。
- 无帧导航/时间轴（文本上下滚动）。

## 8. 交互与 UI 规范

- 全部沿用 `el-card/el-form/el-dialog/el-tag/el-select` 与 `--el-*` 变量，不自定义主题化外壳、不写死 `font-size`。
- 删除实体/关系必须二次确认（`ElMessageBox.confirm`，写明影响）。
- `v-hasPerm` 权限 + 后端权限校验。
- 局部刷新：实体/关系变更只更新对应 decoration/列表项，不整页重渲染。

## 9. 错误处理

- 文本解码失败 / 非文本扩展名 / 超过大小上限（如 2MB，字符数上限如 20 万）→ 拒绝并明确提示。
- 编码探测兜底：无法确定时按 UTF-8 且不报错，content 以对应 encoding 读。
- 关系校验：`from/to` 实体必须存在（同任务）、同句内、`relation_type` 在 `classes.relations` 中。
- 重叠实体：默认不允许同一字符属于多个实体；拖选若与已有 span 重叠 → 提示并阻止。
- 文档锁冲突：提示「该文档被 xx 标注中」。

## 10. 导出（字符级 BIO/BIESO + 关系）

- `export_service` 增加 `text_ner` 分支 `_export_text_ner`：对每个文档读全文 + `load_text_annotations`。
- 生成 `<stem>_{document_id}.txt`：按换行分句，每句逐字符一行 `字符\tBIO标签`，句间空行（B = 实体首字符，I = 实体其余字符，O = 非实体；支持 BIESO 参数可换）。
- 生成 `<stem>_{document_id}.relations.jsonl`：每行 `{"text":<句子>,"entities":[{...}],"relations":[...]}`（或纯关系列表）。
- 标签名取 `classes.entities` 中 `label_id` 对应的 `name`；关联 relation 同句校验。
- 复用现有导出框架的「下载导出 / 训练导出」入口（`annotation_task_id` 正确地传入，参考视频导出修复）。

## 11. 测试

- 后端：`AnnotationDocumentModel`/`TEXT_NER` 枚举迁移、文档上传（mock RustFS + 编码探测）、content 读取、文档标注读写（含任务级校验、`document_id` 归属）、关系/重叠校验、BIO/BIESO 导出——单元/接口测试。
- 前端：UTF-16 offset 与 span 工具函数、实体/关系状态、BIO 序列生成（若前端含）——Vitest 单测。
- e2e：上传文本 → 创建 `text_ner` 任务（含关系类型配置）→ 拖选实体 → 建关系 → 保存 → 导出（BIO + relations）。

## 12. 约束与选型

- 复用 CodeMirror 6（现有依赖）；关系用「列表 + 联动高亮」，不在文本框画线。
- 字符偏移统一 UTF-16 code unit；`EntitySpan.text` 冗余原文。
- 实体 + 关系类型在任务 `classes` 内定义（`entities`/`relations` 两段）；关系仅同句内。
- 遵循 `AGENTS.md`：局部刷新、`el-*` 组件/变量、删除二次确认、单根组件、中文注释/提交、编辑器/构造器用成熟库。

## 13. 相关文件

- 后端：`app/api/v1/module_annotation/{dataset,annotation,task}/model.py`、`dataset/document_service.py`（新增）、`dataset/document_controller.py`（新增）、`annotation/service.py`、`annotation/controller.py`、`dataset/export_service.py`、`app/alembic/versions/`。
- 前端：`src/annotation/index.ts`（注册 `textNerPlugin`）、`src/annotation/tasks/textNer/`（新增）、`src/annotation/core/types.ts`（`TaskMedia`+`"text"`）、`src/annotation/core/AnnotationWorkbench.vue`（text 模式）、`src/api/module_annotation/`（文档接口）、`src/views/module_annotation/annotation/index.vue`（任务 classes 关系类型配置）。
- e2e：`frontend/e2e/create-text-ner.spec.ts`。
