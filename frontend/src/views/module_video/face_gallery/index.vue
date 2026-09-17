<template>
  <div class="app-container">
    <el-tabs v-model="activeKind" class="gallery-kind-tabs" @tab-change="handleKindChange">
      <el-tab-pane label="人脸底库" name="face" />
      <el-tab-pane label="跨镜底库" name="reid" />
    </el-tabs>

    <PageSearch
      ref="searchRef"
      :search-config="searchConfig"
      @query-click="handleQueryClick"
      @reset-click="handleResetClick"
    />

    <div class="gallery-summary">
      <el-tag type="info" size="small">{{ kindMeta.label }}总数：{{ gallerySummary.total }}</el-tag>
      <el-tag v-if="gallerySummary.dimensions.length" type="info" size="small" effect="plain">
        当前页特征维度：{{ gallerySummary.dimensions.join(" / ") }}
      </el-tag>
      <el-tag v-if="gallerySummary.total === 0" type="warning" size="small">
        {{ kindMeta.emptyTip }}
      </el-tag>
    </div>

    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, removeIds, cols }">
        <CrudToolbarLeft
          :remove-ids="removeIds"
          :perm-create="['module_video:face_gallery:create']"
          :perm-delete="['module_video:face_gallery:delete']"
          @add="handleOpenDialog('create')"
          @delete="onToolbar('delete')"
        />
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>

      <template #table="{ data, loading, tableRef, onSelectionChange }">
        <div class="data-table__content">
          <el-table
            :ref="tableRef as any"
            v-loading="loading"
            row-key="id"
            :data="data"
            height="100%"
            border
            stripe
            @selection-change="onSelectionChange"
          >
            <template #empty>
              <el-empty :image-size="80" :description="kindMeta.emptyListTip" />
            </template>
            <el-table-column
              v-if="galleryCols.find((c) => c.prop === 'selection')?.show"
              type="selection"
              width="55"
              align="center"
            />
            <el-table-column
              v-if="galleryCols.find((c) => c.prop === 'index')?.show"
              type="index"
              fixed
              label="序号"
              width="60"
              align="center"
            />
            <el-table-column label="姓名/标签" prop="name" min-width="130" show-overflow-tooltip />
            <el-table-column label="类型" prop="kind" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="row.kind === 'reid' ? 'warning' : 'success'" size="small">
                  {{ row.kind === "reid" ? "跨镜" : "人脸" }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column
              label="工号/编号"
              prop="person_no"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column
              label="特征模型"
              prop="model_key"
              min-width="130"
              show-overflow-tooltip
            />
            <el-table-column label="维度" prop="dimension" width="90" align="center" />
            <el-table-column
              label="底图引用"
              prop="face_image_url"
              min-width="160"
              show-overflow-tooltip
            />
            <el-table-column
              label="更新时间"
              prop="updated_time"
              width="170"
              show-overflow-tooltip
            />
            <el-table-column
              v-if="galleryCols.find((c) => c.prop === 'operation')?.show"
              fixed="right"
              label="操作"
              align="center"
              min-width="150"
            >
              <template #default="scope">
                <el-button
                  v-hasPerm="['module_video:face_gallery:create']"
                  type="primary"
                  size="small"
                  link
                  @click="handleOpenDialog('update', scope.row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_video:face_gallery:delete']"
                  type="danger"
                  size="small"
                  link
                  @click="handleRowDelete(scope.row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <EnhancedDialog
      v-model="dialogVisible.visible"
      :title="dialogVisible.title"
      append-to-body
      width="640px"
      @close="handleCloseDialog"
    >
      <el-alert
        v-if="dialogVisible.type === 'create'"
        class="gallery-dialog__tip"
        type="info"
        :closable="false"
        show-icon
        title="粘贴特征向量（支持 JSON 数组 / 逗号分隔 / f16b64 base64），或从文件导入"
      />
      <el-alert
        v-else
        class="gallery-dialog__tip"
        type="info"
        :closable="false"
        show-icon
        title="特征向量留空表示不修改，仅更新姓名/工号/底图引用"
      />

      <el-form ref="dataFormRef" :model="formData" label-width="100px" size="default">
        <el-form-item label="底库类型" prop="kind">
          <el-select
            v-model="formData.kind"
            :disabled="dialogVisible.type === 'update'"
            placeholder="请选择底库类型"
            style="width: 100%"
          >
            <el-option label="人脸底库（FACE_REC / STRANGER）" value="face" />
            <el-option label="跨镜底库（REID_TRACK）" value="reid" />
          </el-select>
        </el-form-item>
        <el-form-item
          label="姓名/标签"
          prop="name"
          :rules="[{ required: true, message: '请输入姓名或标签', trigger: 'blur' }]"
        >
          <el-input v-model="formData.name" placeholder="如：张三" />
        </el-form-item>
        <el-form-item label="工号/编号" prop="person_no">
          <el-input v-model="formData.person_no" placeholder="可选，如：E1001" />
        </el-form-item>
        <el-form-item label="特征模型" prop="model_key">
          <el-input
            v-model="formData.model_key"
            placeholder="如：w600k_r50（需与边缘人脸模型一致）"
          />
        </el-form-item>
        <el-form-item label="底图引用" prop="face_image_url">
          <el-input v-model="formData.face_image_url" placeholder="可选：底图 URL 或对象存储路径" />
        </el-form-item>
        <el-form-item label="特征向量" prop="embeddingText">
          <el-input
            v-model="formData.embeddingText"
            type="textarea"
            :rows="4"
            placeholder="[0.0123, -0.0456, ...] 或 0.0123,-0.0456,... 或 f16b64 字符串"
          />
          <div class="gallery-dialog__embedding-actions">
            <el-button size="small" @click="triggerFilePick">从文件导入</el-button>
            <span v-if="parsedDimension" class="gallery-dialog__dim">
              解析维度：{{ parsedDimension }}
            </span>
            <span
              v-else-if="formData.embeddingText"
              class="gallery-dialog__dim gallery-dialog__dim--bad"
            >
              无法解析特征向量
            </span>
          </div>
          <input
            ref="fileInputRef"
            class="gallery-dialog__file"
            type="file"
            accept=".json,.txt,text/plain,application/json"
            @change="handleFileChange"
          />
        </el-form-item>
        <el-form-item label="备注" prop="description">
          <el-input v-model="formData.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleCloseDialog">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import {
  deleteFaceGallery,
  enrollFaceGallery,
  getFaceGalleryList,
  type FaceGalleryItem,
} from "@/api/module_video/face_gallery";
import type { IContentConfig, ISearchConfig } from "@/components/CURD/types";
import { useCrudList } from "@/components/CURD/useCrudList";

interface TablePageQuery {
  page_no: number;
  page_size: number;
  [key: string]: any;
}

const { searchRef, contentRef, handleQueryClick, handleResetClick, refreshList } = useCrudList();

/** 当前管理的底库类型：face=人脸 / reid=跨镜重识别（后端同一张表按 kind 隔离） */
const activeKind = ref("face");

/** 底库类型对应的文案（列表/摘要/空态按类型切换） */
const kindMeta = computed(() =>
  activeKind.value === "reid"
    ? {
        label: "跨镜底库",
        emptyTip: "跨镜底库为空：REID_TRACK 规则不会命中，请先录入跨镜特征",
        emptyListTip: "跨镜底库为空：启用 REID_TRACK 规则前请先录入跨镜特征",
      }
    : {
        label: "人脸底库",
        emptyTip: "人脸底库为空：FACE_REC / STRANGER 规则不会命中，请先录入人脸特征",
        emptyListTip: "人脸底库为空：启用 FACE_REC / STRANGER 规则前请先录入人脸特征",
      }
);

const submitLoading = ref(false);
const dataFormRef = ref();
const fileInputRef = ref<HTMLInputElement>();

const searchConfig = reactive<ISearchConfig>({
  permPrefix: "module_video:face_gallery",
  colon: true,
  isExpandable: true,
  showNumber: 2,
  form: { labelWidth: "auto" },
  formItems: [
    {
      prop: "name",
      label: "姓名/标签",
      type: "input",
      attrs: { placeholder: "姓名/标签", clearable: true, style: { width: "180px" } },
    },
    {
      prop: "person_no",
      label: "工号/编号",
      type: "input",
      attrs: { placeholder: "工号/编号", clearable: true, style: { width: "180px" } },
    },
    {
      prop: "model_key",
      label: "特征模型",
      type: "input",
      attrs: { placeholder: "特征模型", clearable: true, style: { width: "180px" } },
    },
  ],
});

const galleryCols = reactive<Array<{ prop?: string; label?: string; show?: boolean }>>([
  { prop: "selection", label: "选择框", show: true },
  { prop: "index", label: "序号", show: true },
  { prop: "operation", label: "操作", show: true },
]);

/** 底库概要：总条数 + 当前页出现的维度集合（列表/概览用） */
const gallerySummary = reactive<{ total: number; dimensions: number[] }>({
  total: 0,
  dimensions: [],
});

const contentConfig = reactive<IContentConfig<TablePageQuery>>({
  permPrefix: "module_video:face_gallery",
  pk: "id",
  cols: galleryCols as IContentConfig["cols"],
  hideColumnFilter: false,
  toolbar: [],
  defaultToolbar: ["refresh", "filter"],
  pagination: { pageSize: 10, pageSizes: [10, 20, 30, 50] },
  request: { page_no: "page_no", page_size: "page_size" },
  indexAction: async (params) => {
    const res = await getFaceGalleryList({
      ...(params as TablePageQuery),
      kind: activeKind.value,
    });
    const items = (res.data.data.items ?? []) as FaceGalleryItem[];
    gallerySummary.total = res.data.data.total ?? 0;
    gallerySummary.dimensions = Array.from(new Set(items.map((i) => i.dimension))).sort(
      (a, b) => a - b
    );
    return { total: res.data.data.total, list: items };
  },
  deleteAction: async (ids) => {
    await deleteFaceGallery(
      ids
        .split(",")
        .map((s: string) => Number(s.trim()))
        .filter((n: number) => !Number.isNaN(n))
    );
  },
  deleteConfirm: { title: "警告", message: "确认删除所选人脸底库条目?", type: "warning" },
});

const dialogVisible = reactive({
  title: "",
  visible: false,
  type: "create" as "create" | "update",
});

const formData = reactive({
  id: undefined as number | undefined,
  kind: "face" as "face" | "reid",
  name: "",
  person_no: "",
  model_key: "w600k_r50",
  description: "",
  face_image_url: "",
  embeddingText: "",
});

const initialFormData = { ...formData };

/** 解析后的特征向量（新增时必填；编辑时可为空表示不变更） */
const parsedEmbedding = computed<number[] | null>(() => parseEmbedding(formData.embeddingText));
const parsedDimension = computed<number | null>(() => parsedEmbedding.value?.length ?? null);

/** 半精度（IEEE-754 binary16）→ 双精度；用于解码 f16b64 紧凑上报格式 */
function halfToFloat(h: number): number {
  const sign = h & 0x8000 ? -1 : 1;
  const exp = (h >> 10) & 0x1f;
  const frac = h & 0x3ff;
  if (exp === 0) return sign * 2 ** -14 * (frac / 1024);
  if (exp === 31) return frac ? NaN : sign * Infinity;
  return sign * 2 ** (exp - 15) * (1 + frac / 1024);
}

function decodeF16B64(text: string): number[] | null {
  try {
    const binary = atob(text);
    if (!binary.length || binary.length % 2 !== 0) return null;
    const buffer = new ArrayBuffer(binary.length);
    const view = new DataView(buffer);
    for (let i = 0; i < binary.length; i += 1) view.setUint8(i, binary.charCodeAt(i));
    const out: number[] = [];
    for (let i = 0; i < binary.length; i += 2) out.push(halfToFloat(view.getUint16(i, true)));
    return out;
  } catch {
    return null;
  }
}

function toNumbers(values: unknown[]): number[] | null {
  if (!values.length) return null;
  const out: number[] = [];
  for (const v of values) {
    const n = typeof v === "number" ? v : Number(v);
    if (!Number.isFinite(n)) return null;
    out.push(n);
  }
  return out;
}

/**
 * 解析粘贴/导入的特征向量：
 * 1) JSON 数组（`[0.1, 0.2, ...]`）；
 * 2) f16b64（base64 小端 float16，边缘上报的紧凑格式）；
 * 3) 逗号/空白/分号分隔的数值。
 * 无法解析返回 null（不抛异常）。
 */
function parseEmbedding(raw: string): number[] | null {
  const text = (raw || "").trim();
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      const nums = toNumbers(parsed);
      if (nums) return nums;
    }
  } catch {
    /* 非 JSON，继续尝试其它格式 */
  }
  if (text.length >= 4 && /^[A-Za-z0-9+/]+={0,2}$/.test(text)) {
    const vec = decodeF16B64(text);
    if (vec && vec.length && vec.every((n) => Number.isFinite(n))) return vec;
  }
  return toNumbers(text.split(/[\s,;]+/));
}

function handleRowDelete(id: number) {
  contentRef.value?.handleDelete(id);
}

/** 切换底库类型：刷新列表（搜索条件由使用方决定是否保留） */
function handleKindChange() {
  refreshList();
}

function triggerFilePick() {
  fileInputRef.value?.click();
}

async function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  try {
    formData.embeddingText = (await file.text()).trim();
  } catch {
    ElMessage.error("读取文件失败");
  }
}

async function resetForm() {
  if (dataFormRef.value) {
    dataFormRef.value.resetFields();
    dataFormRef.value.clearValidate();
  }
  Object.assign(formData, initialFormData);
}

async function handleCloseDialog() {
  dialogVisible.visible = false;
  await resetForm();
}

function handleOpenDialog(type: "create" | "update", row?: any) {
  dialogVisible.type = type;
  if (type === "update" && row) {
    dialogVisible.title = "编辑底库条目";
    formData.id = row.id;
    formData.kind = row.kind === "reid" ? "reid" : "face";
    formData.name = row.name;
    formData.person_no = row.person_no ?? "";
    formData.model_key = row.model_key ?? "w600k_r50";
    formData.description = row.description ?? "";
    formData.face_image_url = row.face_image_url ?? "";
    formData.embeddingText = "";
  } else {
    dialogVisible.title = "录入底库条目";
    resetForm();
    formData.kind = activeKind.value === "reid" ? "reid" : "face";
  }
  dialogVisible.visible = true;
}

async function handleSubmit() {
  dataFormRef.value.validate(async (valid: boolean) => {
    if (!valid) return;
    const embedding = parsedEmbedding.value;
    if (dialogVisible.type === "create" && !embedding) {
      ElMessage.warning("请粘贴或导入有效的特征向量");
      return;
    }
    if (formData.embeddingText && !embedding) {
      ElMessage.warning("特征向量无法解析，请检查格式");
      return;
    }
    submitLoading.value = true;
    try {
      await enrollFaceGallery({
        id: formData.id,
        name: formData.name,
        person_no: formData.person_no || null,
        // 仅新增时指定类型；更新省略 kind → 后端保持原类型不变
        kind: dialogVisible.type === "create" ? formData.kind : undefined,
        model_key: formData.model_key || "unknown",
        description: formData.description || null,
        face_image_url: formData.face_image_url || null,
        embedding,
        dimension: embedding ? embedding.length : null,
      });
      ElMessage.success(formData.id ? "更新成功" : "录入成功");
      dialogVisible.visible = false;
      await resetForm();
      refreshList();
    } finally {
      submitLoading.value = false;
    }
  });
}
</script>

<style scoped>
.gallery-kind-tabs {
  margin-bottom: 4px;
}
.gallery-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.gallery-dialog__tip {
  margin-bottom: 12px;
}
.gallery-dialog__embedding-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}
.gallery-dialog__dim {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.gallery-dialog__dim--bad {
  color: var(--el-color-danger);
}
.gallery-dialog__file {
  display: none;
}
</style>
