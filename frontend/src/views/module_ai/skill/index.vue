<!-- AI 技能广场：分类 tab + 卡片网格 + 新建/编辑弹窗 + 精选/启用切换 -->
<template>
  <div class="app-container ai-skill-page">
    <!-- 分类 tab -->
    <el-card shadow="never" class="skill-cat-card">
      <div class="skill-cat-bar">
        <el-input
          v-model="searchKeyword"
          class="skill-search"
          :prefix-icon="Search"
          placeholder="搜索技能名称/描述/分类"
          clearable
        />
        <el-button
          v-hasPerm="['module_ai:skill:create']"
          type="primary"
          :icon="Plus"
          @click="openSkillDialog()"
        >
          新建技能
        </el-button>
        <el-tabs v-model="activeTab" class="skill-tabs">
          <el-tab-pane label="全部" name="all" />
          <el-tab-pane
            v-for="c in categories"
            :key="c.name"
            :label="`${c.name} (${c.count})`"
            :name="c.name"
          />
        </el-tabs>
      </div>
    </el-card>

    <!-- 批量操作 / 统计摘要 -->
    <div class="skill-batchbar">
      <el-checkbox
        :model-value="allSelected"
        :indeterminate="isIndeterminate"
        @change="toggleSelectAll"
      >
        全选
      </el-checkbox>
      <el-button size="small" :disabled="!skillSelIds.length" @click="batchSkill(true)">
        批量启用
      </el-button>
      <el-button size="small" :disabled="!skillSelIds.length" @click="batchSkill(false)">
        批量停用
      </el-button>
      <el-tag size="small" type="info" effect="plain" class="summary-tag">
        共 {{ skillSummary.total }} 个技能 · 启用 {{ skillSummary.enabled }} · 停用
        {{ skillSummary.disabled }}
      </el-tag>
    </div>

    <el-row v-loading="loading" :gutter="12">
      <el-col v-for="s in pagedSkills" :key="s.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
        <el-card shadow="hover" class="skill-card" :body-style="{ padding: '16px' }">
          <div class="skill-card__head">
            <el-checkbox
              :model-value="isSelected(s)"
              class="skill-card__check"
              @change="toggleSelect(s)"
            />
            <div class="skill-icon">{{ s.icon || "🧩" }}</div>
            <div class="skill-card__meta">
              <div class="skill-card__name">
                {{ s.name }}
                <el-tag v-if="s.featured" size="small" type="warning" effect="plain">精选</el-tag>
                <el-tag
                  v-if="!s.enabled"
                  size="small"
                  type="info"
                  effect="plain"
                  class="skill-card__off"
                >
                  停用
                </el-tag>
              </div>
              <div class="skill-card__sub">
                <el-tag size="small" effect="plain">{{ skillTypeLabel(s.skill_type) }}</el-tag>
                <span v-if="s.version" class="skill-version">v{{ s.version }}</span>
              </div>
            </div>
          </div>
          <div class="skill-card__desc">{{ s.description || "暂无描述" }}</div>
          <div class="skill-card__meta-row">
            <span class="skill-author">{{ s.author || "—" }}</span>
            <span class="skill-install">{{ s.install_count || 0 }} 次安装</span>
          </div>
          <div class="skill-card__actions">
            <el-button
              v-hasPerm="['module_ai:skill:query']"
              size="small"
              :icon="View"
              @click="viewSkill(s)"
            >
              详情
            </el-button>
            <el-button
              v-hasPerm="['module_ai:skill:update']"
              size="small"
              :icon="Edit"
              @click="openSkillDialog(s)"
            >
              编辑
            </el-button>
            <el-button
              v-if="s.enabled"
              v-hasPerm="['module_ai:skill:update']"
              size="small"
              :icon="Star"
              @click="toggleFeatured(s)"
            >
              精选
            </el-button>
            <el-button
              v-hasPerm="['module_ai:agent:update']"
              size="small"
              :icon="Link"
              @click="openInstallDialog(s)"
            >
              安装
            </el-button>
            <el-button
              v-hasPerm="['module_ai:skill:create']"
              size="small"
              :icon="CopyDocument"
              @click="copySkill(s)"
            >
              复制
            </el-button>
            <el-button
              v-hasPerm="['module_ai:skill:delete']"
              size="small"
              type="danger"
              :icon="Delete"
              @click="deleteSkill(s)"
            />
          </div>
        </el-card>
      </el-col>
      <el-col v-if="!loading && filteredSkills.length === 0" :span="24">
        <el-empty description="暂无技能，点击「新建技能」创建" />
      </el-col>
    </el-row>

    <div v-if="filteredSkills.length > 0" class="skill-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="filteredSkills.length"
        :page-sizes="[12, 24, 48]"
        layout="total, sizes, prev, pager, next"
        background
      />
    </div>

    <!-- 技能编辑弹窗 -->
    <el-dialog
      v-model="skillDialogVisible"
      :title="editingSkill ? '编辑技能' : '新建技能'"
      width="620px"
      append-to-body
      destroy-on-close
    >
      <el-form :model="skillForm" label-width="90px" size="default">
        <el-form-item label="名称" required>
          <el-input v-model="skillForm.name" placeholder="技能名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="skillForm.skill_type" style="width: 100%">
            <el-option label="指令 (instruction)" value="instruction" />
            <el-option label="工具 (tool)" value="tool" />
            <el-option label="自定义 (custom)" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="skillForm.category" placeholder="分类标签（可选）" />
        </el-form-item>
        <el-form-item label="作者">
          <el-input v-model="skillForm.author" placeholder="作者（可选）" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="skillForm.version" placeholder="1.0" style="width: 160px" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="skillForm.icon" placeholder="emoji 或图片URL" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="skillForm.description"
            type="textarea"
            :rows="2"
            placeholder="简要描述这个技能"
          />
        </el-form-item>
        <el-form-item label="技能内容">
          <div class="skill-md-editor">
            <el-radio-group v-model="skillContentMode" size="small" class="skill-md-editor__tabs">
              <el-radio-button label="edit">编辑</el-radio-button>
              <el-radio-button label="preview">预览</el-radio-button>
            </el-radio-group>
            <el-input
              v-if="skillContentMode === 'edit'"
              v-model="skillForm.content"
              type="textarea"
              :rows="8"
              placeholder="Markdown 指令/使用说明，支持 {{变量}}，绑定到智能体后并入系统提示词"
            />
            <div v-else class="skill-md-editor__preview" v-html="renderMd(skillForm.content)"></div>
          </div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="skillForm.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="skillForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="skillDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingSkill" @click="saveSkill">保存</el-button>
      </template>
    </el-dialog>

    <!-- 技能详情弹窗 -->
    <el-dialog v-model="detailVisible" title="技能详情" width="620px" append-to-body>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">
          {{ skillTypeLabel(detail.skill_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="分类">{{ detail.category || "—" }}</el-descriptions-item>
        <el-descriptions-item label="版本">{{ detail.version || "—" }}</el-descriptions-item>
        <el-descriptions-item label="作者">{{ detail.author || "—" }}</el-descriptions-item>
        <el-descriptions-item label="安装次数">
          {{ detail.install_count || 0 }}
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">
          {{ detail.description || "—" }}
        </el-descriptions-item>
        <el-descriptions-item label="技能内容" :span="2">
          <div class="skill-md" v-html="renderMd(detail.content)"></div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="installVisible" title="安装技能到智能体" width="520px" append-to-body>
      <el-form label-position="top" size="small">
        <el-form-item label="选择智能体">
          <el-select
            v-model="installAgentId"
            filterable
            placeholder="选择智能体"
            style="width: 100%"
          >
            <el-option v-for="a in agentOptions" :key="a.id" :label="a.agent_name" :value="a.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="installVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="installing"
          :disabled="!installAgentId"
          @click="confirmInstall"
        >
          安装
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  Plus,
  Edit,
  Delete,
  View,
  Star,
  Link,
  CopyDocument,
  Search,
} from "@element-plus/icons-vue";
import MarkdownIt from "markdown-it";
import {
  getAiSkillList,
  getAiSkillCategories,
  getAiSkillDetail,
  createAiSkill,
  updateAiSkill,
  deleteAiSkill,
  toggleAiSkillFeatured,
  installAiSkillToAgent,
  batchSkillStatus,
} from "@/api/module_ai/skill";
import { getAiAgentList } from "@/api/module_ai/agent";

defineOptions({ name: "AiSkill" });

const loading = ref(false);
const skills = ref<any[]>([]);
const categories = ref<any[]>([]);
const activeTab = ref("all");
const searchKeyword = ref("");
const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
const skillContentMode = ref("edit");
function renderMd(text: string) {
  return md.render(text || "");
}

// 安装技能到智能体
const installVisible = ref(false);
const installing = ref(false);
const installAgentId = ref<number | null>(null);
const agentOptions = ref<any[]>([]);
let currentSkill: any = null;

async function openInstallDialog(s: any) {
  currentSkill = s;
  installAgentId.value = null;
  installVisible.value = true;
  if (!agentOptions.value.length) {
    try {
      const res = await getAiAgentList({});
      agentOptions.value = (res.data?.data || []).map((a: any) => ({
        id: a.id,
        agent_name: a.agent_name,
      }));
    } catch {
      agentOptions.value = [];
    }
  }
}

async function confirmInstall() {
  if (!currentSkill || !installAgentId.value) return;
  installing.value = true;
  try {
    await installAiSkillToAgent(installAgentId.value, currentSkill.id);
    ElMessage.success("安装成功");
    installVisible.value = false;
    await loadData();
  } catch {
    ElMessage.error("安装失败，请重试");
  } finally {
    installing.value = false;
  }
}

function skillTypeLabel(t: string) {
  return { instruction: "指令", tool: "工具", custom: "自定义" }[t] || t;
}

const filteredSkills = computed(() => {
  let list = skills.value;
  if (activeTab.value !== "all") {
    list = list.filter((s) => (s.category || "未分类") === activeTab.value);
  }
  const kw = searchKeyword.value.trim().toLowerCase();
  if (kw) {
    list = list.filter(
      (s) =>
        (s.name || "").toLowerCase().includes(kw) ||
        (s.description || "").toLowerCase().includes(kw) ||
        (s.category || "").toLowerCase().includes(kw)
    );
  }
  return list;
});

// ---- 分页 ----
const page = ref(1);
const pageSize = ref(12);
const pagedSkills = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredSkills.value.slice(start, start + pageSize.value);
});

// ---- 批量选择 / 启停 ----
const skillSelIds = ref<number[]>([]);
const skillSelSet = computed(() => new Set(skillSelIds.value));
function isSelected(s: any) {
  return skillSelSet.value.has(s.id);
}
function toggleSelect(s: any) {
  skillSelIds.value = skillSelIds.value.includes(s.id)
    ? skillSelIds.value.filter((id) => id !== s.id)
    : [...skillSelIds.value, s.id];
}
const allSelected = computed(() => {
  const ids = filteredSkills.value.map((s) => s.id);
  return ids.length > 0 && ids.every((id) => skillSelSet.value.has(id));
});
const isIndeterminate = computed(() => {
  const ids = filteredSkills.value.map((s) => s.id);
  const n = ids.filter((id) => skillSelSet.value.has(id)).length;
  return n > 0 && n < ids.length;
});
function toggleSelectAll(checked: boolean | string | number) {
  if (checked) {
    const ids = filteredSkills.value.map((s) => s.id);
    skillSelIds.value = Array.from(new Set([...skillSelIds.value, ...ids]));
  } else {
    const pageIds = new Set(filteredSkills.value.map((s) => s.id));
    skillSelIds.value = skillSelIds.value.filter((id) => !pageIds.has(id));
  }
}

// ---- 统计摘要 ----
const skillSummary = ref({ total: 0, enabled: 0, disabled: 0 });

async function batchSkill(enabled: boolean) {
  if (!skillSelIds.value.length) return;
  try {
    const r = await batchSkillStatus(skillSelIds.value, enabled);
    ElMessage.success(`已${enabled ? "启用" : "停用"} ${r.data?.data?.count || 0} 个技能`);
    skillSelIds.value = [];
    await loadData();
  } catch (e: any) {
    ElMessage.error(e?.msg || e?.message || "操作失败");
  }
}

// 切换分类/关键字时回到第一页
watch([activeTab, searchKeyword], () => {
  page.value = 1;
});

async function copySkill(s: any) {
  try {
    await createAiSkill({
      name: `${s.name}（副本）`,
      skill_type: s.skill_type,
      category: s.category || null,
      author: s.author || null,
      version: s.version || "1.0",
      icon: s.icon || null,
      description: s.description,
      content: s.content,
      sort_order: 0,
      enabled: s.enabled !== false,
    });
    ElMessage.success("已复制技能");
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "复制失败");
  }
}

const loadData = async () => {
  loading.value = true;
  try {
    const [sr, cr] = await Promise.all([getAiSkillList({}), getAiSkillCategories()]);
    skills.value = sr.data?.data || [];
    categories.value = cr.data?.data || [];
    skillSummary.value = {
      total: skills.value.length,
      enabled: skills.value.filter((x: any) => x.enabled).length,
      disabled: skills.value.filter((x: any) => !x.enabled).length,
    };
  } catch (e: any) {
    ElMessage.error(e?.message || "加载失败");
  } finally {
    loading.value = false;
  }
};

// ---------- 新建/编辑 ----------
const skillDialogVisible = ref(false);
const savingSkill = ref(false);
const editingSkill = ref<any>();
const skillForm = reactive<any>({});

function openSkillDialog(s?: any) {
  editingSkill.value = s || undefined;
  if (s) {
    Object.assign(skillForm, {
      ...s,
      content: s.content || "",
      description: s.description || "",
      category: s.category || "",
      author: s.author || "",
      icon: s.icon || "",
      version: s.version || "1.0",
    });
  } else {
    Object.assign(skillForm, {
      name: "",
      skill_type: "instruction",
      category: "",
      author: "",
      version: "1.0",
      icon: "",
      description: "",
      content: "",
      sort_order: 0,
      enabled: true,
    });
  }
  skillDialogVisible.value = true;
}

async function saveSkill() {
  if (!skillForm.name) {
    ElMessage.warning("请填写技能名称");
    return;
  }
  savingSkill.value = true;
  try {
    const payload: any = {
      name: skillForm.name,
      skill_type: skillForm.skill_type,
      category: skillForm.category || null,
      author: skillForm.author || null,
      version: skillForm.version || "1.0",
      icon: skillForm.icon || null,
      description: skillForm.description,
      content: skillForm.content,
      sort_order: skillForm.sort_order || 0,
      enabled: skillForm.enabled,
    };
    if (editingSkill.value) {
      await updateAiSkill(editingSkill.value.id, payload);
    } else {
      await createAiSkill(payload);
    }
    ElMessage.success("保存成功");
    skillDialogVisible.value = false;
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    savingSkill.value = false;
  }
}

// ---------- 详情 ----------
const detailVisible = ref(false);
const detail = ref<any>({});

async function viewSkill(s: any) {
  const r = await getAiSkillDetail(s.id);
  detail.value = r.data?.data || s;
  detailVisible.value = true;
}

// ---------- 精选 / 删除 ----------
async function toggleFeatured(s: any) {
  try {
    await toggleAiSkillFeatured(s.id, !s.featured);
    ElMessage.success(s.featured ? "已取消精选" : "已设为精选");
    loadData();
  } catch (e: any) {
    ElMessage.error(e?.message || "操作失败");
  }
}

function deleteSkill(s: any) {
  ElMessageBox.confirm(`确定删除技能「${s.name}」吗？删除后不可恢复。`, "删除确认", {
    confirmButtonText: "删除",
    cancelButtonText: "取消",
    type: "warning",
  })
    .then(async () => {
      await deleteAiSkill([s.id]);
      ElMessage.success("删除成功");
      loadData();
    })
    .catch(() => {
      /* 取消 */
    });
}

onMounted(loadData);
</script>

<style scoped lang="scss">
.ai-skill-page {
  height: 100%;
  overflow: auto;
}

.skill-batchbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.skill-card__check {
  flex-shrink: 0;
}

.skill-card__off {
  margin-left: 4px;
}

.summary-tag {
  margin-left: 4px;
}

.skill-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
}

.skill-cat-card {
  margin-bottom: 12px;

  .skill-cat-bar {
    display: flex;
    align-items: center;
    gap: 16px;

    .skill-search {
      width: 260px;
      flex-shrink: 0;
    }

    .skill-tabs {
      flex: 1;

      :deep(.el-tabs__nav-wrap::after) {
        display: none;
      }
    }
  }
}

.skill-card {
  margin-bottom: 12px;

  .skill-card__head {
    display: flex;
    gap: 10px;
    align-items: center;
  }

  .skill-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    font-size: 22px;
    border-radius: 10px;
    background: var(--el-fill-color-light);
  }

  .skill-card__meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .skill-card__name {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: var(--el-font-size-base);
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .skill-card__sub {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .skill-version,
  .skill-install {
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }

  .skill-card__desc {
    margin: 10px 0;
    font-size: 12px;
    color: var(--el-text-color-secondary);
    min-height: 34px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .skill-card__meta-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
  }

  .skill-author {
    font-size: 12px;
    color: var(--el-text-color-regular);
  }

  .skill-card__actions {
    display: flex;
    gap: 8px;

    :deep(.el-button + .el-button) {
      margin-left: 0;
    }
  }
}

.skill-content-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--el-font-family);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}
.skill-md {
  line-height: 1.7;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  word-break: break-word;
}
.skill-md-editor {
  width: 100%;
}
.skill-md-editor__tabs {
  margin: 6px 0 8px;
}
.skill-md-editor__preview {
  min-height: 160px;
  line-height: 1.7;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
  word-break: break-word;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px;
  max-height: 40vh;
  overflow: auto;
}
.skill-md-editor__preview :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 6px;
  overflow: auto;
}
.skill-md :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 10px;
  border-radius: 6px;
  overflow: auto;
}
.skill-md :deep(code) {
  font-family: var(--el-font-family-mono, monospace);
}
.skill-md :deep(h1),
.skill-md :deep(h2),
.skill-md :deep(h3) {
  margin: 0.5em 0;
}
</style>
