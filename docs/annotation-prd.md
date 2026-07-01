# AIStation 数据标注系统 — PRD v1.0

## 1. 概述

### 1.1 产品背景
AIStation 现有视频监控平台中已有 AI 推理检测能力（目标检测、车牌识别等），但缺乏**人工标注**模块。团队需要一套**多用户协同标注系统**，用于：
- 为 AI 模型训练准备标注数据集
- 多人协作完成大规模数据标注任务
- 标注结果可追踪、可审计

### 1.2 核心能力
- 支持 6 种标注类型：矩形框、旋转框、多边形、关键点、OCR 文本、图像分类
- 多用户协同：创建任务 → 指派协作者 → 实时协作标注
- 数据集存储在 RustFS（S3 兼容对象存储），通过 docker-compose 统一管理
- 标注结果持久化到 PostgreSQL，支持版本追溯

### 1.3 术语表

| 术语 | 说明 |
|------|------|
| 数据集 (Dataset) | 一组图片的集合，存储在 RustFS 的 bucket 中 |
| 标注任务 (Task) | 一个标注工作单元，包含数据集、目标类别和指派成员 |
| 标注 (Annotation) | 单张图片上的一个标注结果（框/多边形/关键点等） |
| 协作者 (Collaborator) | 被指派参与标注任务的其他系统用户 |
| 标注会话 (Session) | 用户打开图片开始标注到保存的完整过程 |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (Vue 3 + Element Plus)                        │
│  ┌───────────────────┐  ┌─────────────────────────────┐ │
│  │ 标注工作台          │  │ 任务管理/数据集管理/统计面板 │ │
│  │ - Canvas + SVG     │  │                             │ │
│  │ - 工具面板          │  │                             │ │
│  │ - 标注列表          │  │                             │ │
│  │ - 类别面板          │  │                             │ │
│  └───────┬───────────┘  └─────────────┬───────────────┘ │
└──────────┼───────────────────────────┼──────────────────┘
           │ REST API / WebSocket       │ REST API
           ▼                            ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI + SQLAlchemy)                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ module_annotation/                                 │  │
│  │  dataset/ → CRUD, schema                         │  │
│  │  task/ → CRUD, assignment, progress              │  │
│  │  annotation/ → CRUD, batch, history              │  │
│  │  collaboration/ → WebSocket, lock, notify        │  │
│  └──────────────────────┬───────────────────────────┘  │
└─────────────────────────┼──────────────────────────────┘
                          │ S3 SDK
                          ▼
┌─────────────────────────────────────────────────────────┐
│  RustFS (S3-Compatible Object Storage)                  │
│  Bucket: aistation-annotation                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │ datasets/{dataset_id}/images/{filename}          │  │
│  │ datasets/{dataset_id}/thumbnails/{filename}      │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
1. 上传图片 → HTTP multipart → Backend → RustFS (PUT object)
2. 加载图片 → Backend → 生成 presigned URL → Frontend <img src="...">
3. 保存标注 → Frontend (JSON) → Backend → PostgreSQL (annotations table)
4. 实时协作 → WebSocket → Backend → 广播标注变更给协作者
```

---

## 3. 功能需求

### 3.1 数据集管理

| 功能 | 说明 |
|------|------|
| 创建数据集 | 名称、描述、标注类型（6 种之一） |
| 上传图片 | 单张/批量上传（drag-and-drop），自动生成缩略图 |
| 导入图片 | 从现有目录批量导入，支持格式：png/jpg/jpeg/bmp/webp/tiff |
| 数据集列表 | 分页、搜索、统计（图片数、已标注数、标注总数） |
| 数据集详情 | 图片网格视图，标注状态过滤（全部/未标注/已标注/进行中） |

### 3.2 标注任务管理

| 功能 | 说明 |
|------|------|
| 创建任务 | 选择数据集、标注类型、设置标注类别（classes） |
| 指派协作者 | 从系统用户中选择，可多选 |
| 任务进度 | 协作者维度 × 图片维度的完成度统计 |
| 任务锁定 | 一个协作者打开某张图片后，锁定防止冲突（带超时自动解锁） |
| 任务完成 | 所有图片标注完成 → 标记任务结束 → 通知创建者 |

### 3.3 标注工作台

核心交互逻辑参照 EasyLabelTauri 项目，包括：

#### 3.3.1 支持的标注类型

| 类型 | 绘制方式 | 交互参考 |
|------|---------|---------|
| **AxisAlignedBox** (矩形框) | 拖拽绘制 | EasyLabel Box 工具 |
| **RotatedBox** (旋转框) | 三步绘制：角点→方向→高度 | EasyLabel RotatedBox 工具 |
| **Polygon** (多边形) | 逐点点击，Enter/双击闭合 | EasyLabel Polygon 工具 |
| **Keypoint** (关键点) | 放置角点 + 包络框 | EasyLabel Keypoint 工具 |
| **OCR** (文本检测) | 矩形拖拽 / 四边形四点 | EasyLabel OCR 工具 |
| **Classification** (分类) | 类别复选框 | EasyLabel 分类工具 |

#### 3.3.2 交互层

```
┌──────────────────────────────────────────────────────────┐
│  Annotation Workbench                                     │
│  ┌──────────┐  ┌────────────────────┐  ┌──────────────┐  │
│  │ 工具面板   │  │  Canvas (SVG 叠加) │  │ 标注列表      │  │
│  │ - 选择(V) │  │  img + SVG overlay│  │ 类别面板      │  │
│  │ - 矩形(B) │  │  缩放/平移/绘制   │  │ 属性编辑      │  │
│  │ - 旋转(R) │  │  键盘快捷键       │  │              │  │
│  │ - 多边形(P)│  │                   │  │              │  │
│  │ - 关键点(K)│  │                   │  │              │  │
│  │ - OCR(O)  │  │                   │  │              │  │
│  │ - 分类(C) │  │                   │  │              │  │
│  │           │  │                   │  │              │  │
│  │ 状态栏    │  │                   │  │              │  │
│  │ 图片导航   │  │                   │  │              │  │
│  └──────────┘  └────────────────────┘  └──────────────┘  │
└──────────────────────────────────────────────────────────┘
```

#### 3.3.3 标注数据结构

```typescript
// 6 种标注类型的联合类型
type Annotation = AxisAlignedBox | RotatedBox | PolygonAnnotation
                 | KeypointAnnotation | OcrAnnotation | ClassificationAnnotation;

// 坐标全部归一化 [0, 1]
interface AxisAlignedBox {
  id: string;           // UUID
  type: "AxisAlignedBox";
  class_id: number;
  x1: number; y1: number; x2: number; y2: number;  // 归一化 0-1
  created_by: number;    // 用户 ID
  created_at: string;    // ISO 时间戳
  confidence?: number;   // 人工标注默认为 1.0
}

// 其余类型同 EasyLabel 的 types.ts
```

#### 3.3.4 键盘快捷键

同 EasyLabel：`1-7` 切换工具、`Delete` 删除、`Ctrl+S` 保存、`←/→` 翻页、`Enter` 完成绘制、`Escape` 取消、`H` 孔洞模式等。

#### 3.3.5 实时协作

| 事件 | 方向 | 说明 |
|------|------|------|
| `annotate:create` | → 广播 | 协作者创建了新标注 |
| `annotate:update` | → 广播 | 协作者修改了标注 |
| `annotate:delete` | → 广播 | 协作者删除了标注 |
| `image:lock` | → 服务端 | 锁定当前图片 |
| `image:lock_expired` | → 广播 | 图片锁超时释放 |
| `image:focus` | → 广播 | 协作者切换到某张图片 |

标注冲突策略：**乐观锁 + 最后写入者胜出**。前端在保存时带上 `updated_at` 时间戳，服务端检测冲突后返回 409，前端提示用户刷新。

### 3.4 标注结果管理

| 功能 | 说明 |
|------|------|
| 标注历史 | 每次保存记录快照，可回滚 |
| 审计追踪 | 记录谁、何时、修改了什么标注 |
| 导出格式 | YOLO / COCO JSON / PaddleOCR / CSV（同 EasyLabel） |
| 导出范围 | 按任务 / 按数据集 / 按用户导出 |

### 3.5 统计与看板

| 功能 | 说明 |
|------|------|
| 个人工作量 | 今日标注数、本周标注数、累计标注数 |
| 任务进度 | 总体完成率、各用户完成率 |
| 数据集统计 | 图片数量、类别分布、标注密度 |

---

## 4. 数据库设计

### 4.1 新增模型

#### annotation_dataset（数据集）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| name | varchar(128) | 数据集名称 |
| description | text | 描述 |
| annotation_type | enum | detection/rotated_detection/segmentation/keypoint/ocr/classification |
| bucket_name | varchar(64) | RustFS bucket 名 |
| image_count | int | 图片总数 |
| annotated_count | int | 已标注图片数 |
| status | varchar(16) | active/archived |
| created_id | int FK | 创建者 |

#### annotation_task（标注任务）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| dataset_id | int FK | 关联数据集 |
| name | varchar(128) | 任务名称 |
| task_type | enum | annotation/review |
| status | varchar(16) | pending/in_progress/completed |
| assignees | int[] FK | 协作者列表（JSON array）|
| classes | jsonb | 类别定义 [{id, name, color}] |
| progress | int | 完成百分比 0-100 |
| created_id | int FK | |
| completed_at | datetime | |

#### annotation_record（标注记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| task_id | int FK | |
| image_id | int FK→annotation_image |
| annotation_data | jsonb | 完整标注 JSON（标注列表） |
| version | int | 版本号（递增） |
| created_id | int FK | 标注者 |
| updated_at | datetime | |

#### annotation_image（数据集图片）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int PK | |
| dataset_id | int FK | |
| filename | varchar(255) | 原文件名 |
| object_key | varchar(512) | RustFS 中的 key |
| width | int | 图片宽度 |
| height | int | 图片高度 |
| status | varchar(16) | unannotated/in_progress/annotated |
| locked_by | int FK nullable | 当前锁定的用户 |
| locked_at | datetime nullable | 锁定时间 |
| annotation_count | int | 当前标注数量 |

### 4.2 模型继承

所有模型继承 `ModelMixin`（自动获得 `id`, `uuid`, `status`, `created_time`, `updated_time`, `is_deleted`, `deleted_time`）。

`UserMixin` 提供 `created_id`, `updated_id` 用于审计追踪。

---

## 5. API 设计

### 5.1 REST API

| 端点 | 方法 | 说明 | 权限 |
|------|------|------|------|
| `/annotation/dataset` | GET/POST | 数据集列表/创建 | `query`/`create` |
| `/annotation/dataset/{id}` | GET/PUT/DELETE | 数据集详情/更新/删除 | `query`/`update`/`delete` |
| `/annotation/dataset/{id}/upload` | POST | 上传图片（multipart） | `create` |
| `/annotation/dataset/{id}/images` | GET | 图片列表 | `query` |
| `/annotation/task` | GET/POST | 任务列表/创建 | `query`/`create` |
| `/annotation/task/{id}` | GET/PUT/DELETE | 任务详情/更新/删除 | `query`/`update`/`delete` |
| `/annotation/task/{id}/assign` | POST | 指派协作者 | `update` |
| `/annotation/task/{id}/progress` | GET | 任务进度统计 | `query` |
| `/annotation/task/{id}/export` | POST | 导出标注（YOLO/COCO等） | `query` |
| `/annotation/image/{id}/lock` | POST/DELETE | 锁定/解锁图片 | `update` |
| `/annotation/image/{id}/annotations` | GET/PUT | 获取/保存标注 | `query`/`update` |
| `/annotation/image/{id}/annotations/history` | GET | 标注历史版本 | `query` |
| `/annotation/image/{id}/presigned-url` | GET | 获取图片 presigned URL | `query` |
| `/annotation/stats` | GET | 个人工作量统计 | `query` |
| `/annotation/ws` | WebSocket | 实时协作通道 | `update` |

### 5.2 WebSocket 消息格式

```typescript
// 客户端 → 服务端
type WsClientMsg = {
  type: "annotate:create" | "annotate:update" | "annotate:delete" | "image:lock" | "image:focus";
  data: Annotation | { image_id: number };
};

// 服务端 → 客户端
type WsServerMsg = {
  type: WsClientMsg["type"] | "image:lock_expired" | "error";
  user: { id: number; name: string };
  data?: any;
};
```

### 5.3 图片访问流程

```
1. 前端请求 /annotation/image/{id}/presigned-url
2. 后端生成 RustFS presigned URL（有效 1 小时）
3. 前端用此 URL 加载 <img>
4. 标注完成后提交标注数据
```

---

## 6. RustFS 集成

### 6.1 docker-compose 配置

```yaml
rustfs:
  container_name: aistation-rustfs
  image: rustfs/rustfs:latest
  restart: always
  ports:
    - "9000:9000"   # S3 API
    - "9001:9001"   # Web Console
  environment:
    - RUSTFS_ACCESS_KEY=aistation
    - RUSTFS_SECRET_KEY=aistation_secret_key_change_in_prod
    - RUSTFS_CONSOLE_ENABLE=true
  volumes:
    - ./devops/rustfs/data:/data
  command: ["--console-enable", "/data"]

# 初始化数据目录权限
rustfs_perms:
  image: alpine
  user: root
  volumes:
    - ./devops/rustfs/data:/data
  command: chown -R 10001:10001 /data
```

### 6.2 后端 S3 客户端

使用 `boto3`/`aioboto3` 或 RustFS 官方 SDK。配置项：

| 配置 | 说明 |
|------|------|
| `RUSTFS_ENDPOINT` | `http://127.0.0.1:9000` |
| `RUSTFS_ACCESS_KEY` | `aistation` |
| `RUSTFS_SECRET_KEY` | `aistation_secret_key_change_in_prod` |
| `RUSTFS_BUCKET_PREFIX` | `aistation-annotation` |

### 6.3 存储结构

```
bucket: aistation-annotation-{env}
  ├─ datasets/{dataset_id}/images/{filename}
  ├─ datasets/{dataset_id}/thumbnails/{filename}
  └─ exports/{task_id}/yolo/...
```

---

## 7. 前端架构

### 7.1 组件树

```vue
module_annotation/
├── dataset/
│   ├── index.vue          # 数据集列表（CRUD 页面）
│   └── components/
│       ├── ImageGrid.vue  # 图片网格（缩略图视图）
│       └── UploadDialog.vue # 上传图片弹窗
├── task/
│   ├── index.vue          # 任务列表（CRUD 页面）
│   └── components/
│       ├── ProgressPanel.vue  # 进度面板
│       └── AssignDialog.vue   # 指派协作者弹窗
├── annotation/
│   ├── workbench.vue      # 标注工作台（主视图）
│   └── components/
│       ├── AnnotationCanvas.vue   # Canvas + SVG 叠加层
│       ├── ToolPanel.vue          # 左侧工具面板
│       ├── AnnotationList.vue     # 右侧标注列表
│       ├── ClassPanel.vue         # 类别面板
│       ├── ImageNavigator.vue     # 图片导航栏
│       ├── StatusBar.vue          # 状态栏
│       ├── ClassificationPanel.vue # 分类专用面板
│       └── CollaboratorCursor.vue # 协作者光标（实时协作）
└── stats/
    └── index.vue          # 工作量统计
```

### 7.2 状态管理

```typescript
// Pinia stores
useAnnotationStore {
  // 当前画布状态
  currentTool: ToolName;
  currentClassId: number;
  zoom: number;
  pan: { x, y };
  
  // 当前图片标注
  currentImageId: number;
  annotations: Annotation[];
  selectedAnnotationId: string | null;
  
  // 绘图状态（进行中的标注）
  drawingState: DrawingState | null;  // idle | placing | dragging ...
  
  // 协作状态
  collaborators: Map<number, { name, cursor, currentImage }>;
  lockedBy: number | null;
}
```

---

## 8. 菜单与权限

### 8.1 菜单结构

```
数据标注 (type=1, icon="menu-detail", route="/annotation")
├── 数据集管理 (type=2, route="/annotation/dataset")
├── 标注任务 (type=2, route="/annotation/task")
├── 标注工作台 (type=2, route="/annotation/workbench/:taskId", hidden=true)
└── 工作量统计 (type=2, route="/annotation/stats")
```

### 8.2 权限定义

| 权限字符串 | 说明 |
|-----------|------|
| `annotation:dataset:query` | 查看数据集 |
| `annotation:dataset:create` | 创建数据集 |
| `annotation:dataset:update` | 编辑数据集 |
| `annotation:dataset:delete` | 删除数据集 |
| `annotation:task:query` | 查看任务 |
| `annotation:task:create` | 创建任务 |
| `annotation:task:update` | 编辑任务/指派 |
| `annotation:task:delete` | 删除任务 |
| `annotation:task:export` | 导出标注 |
| `annotation:workbench:query` | 进入标注工作台 |
| `annotation:stats:query` | 查看统计 |

---

## 9. 标注工具交互细节

### 9.1 实现参考

核心 Canvas 交互逻辑**直接复用 EasyLabelTauri 前端代码**（`Canvas.vue`、`AnnotationView.vue`、`stores/app.ts`、`utils/types.ts`），差异点：

| EasyLabel | AIStation 标注模块 |
|-----------|-------------------|
| 文件系统存储图片 | RustFS S3 + presigned URL |
| 本地 JSON 文件存标注 | PostgreSQL 持久化 |
| 单用户 | 多用户 + 实时协作 |
| Tauri invoke 命令 | REST API + WebSocket |
| no undo/redo | 标注历史版本可回滚 |
| 本地项目 | 服务端统一管理 |

### 9.2 关键迁移工作

1. **替换数据加载**：`invoke("load_image")` → `GET /presigned-url` → `<img>`
2. **替换数据保存**：`invoke("save_annotations")` → `PUT /annotations`
3. **替换数据存储**：本地 JSON → 服务端 PostgreSQL
4. **新增协作层**：WebSocket 事件广播 + 图片锁定

---

## 10. 实施计划

### Phase 1 — 基础设施（3天）
- [ ] docker-compose 增加 RustFS 服务
- [ ] 后端 S3 工具类（上传、presigned URL、bucket 管理）
- [ ] 环境配置项

### Phase 2 — 后端 API（5天）
- [ ] Dataset CRUD + 图片上传
- [ ] Task CRUD + 指派协作者
- [ ] Annotation CRUD + 版本管理
- [ ] WebSocket 实时协作通道
- [ ] 导出功能

### Phase 3 — 前端（7天）
- [ ] 数据集管理页面
- [ ] 任务管理页面
- [ ] **标注工作台**（核心，移植 EasyLabel 画布逻辑）
- [ ] 实时协作前端集成
- [ ] 统计页面

### Phase 4 — 集成与测试（3天）
- [ ] 菜单/权限注册
- [ ] 端到端测试
- [ ] 性能优化

---

## 11. 未来扩展

- AI 辅助标注（接入现有 ONNX 推理引擎）
- 标注审核工作流（创建→标注→审核→完成）
- 标注质量评分
- 视频帧标注（从视频流提取关键帧）
- 导出到模型训练流水线（直接触发训练任务）