<!-- AI 技能广场：分类 tab + 卡片网格 + 新建/编辑弹窗 + 精选/启用切换 -->
<template>
  <div class="app-container ai-skill-page">
    <!-- 分类 tab -->
    <el-card shadow="never" class="skill-cat-card">
      <div class="skill-cat-bar">
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

    <el-row v-loading="loading" :gutter="12">
      <el-col v-for="s in filteredSkills" :key="s.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
        <el-card shadow="hover" class="skill-card" :body-style="{ padding: '16px' }">
          <div class="skill-card__head">
            <div class="skill-icon">{{ s.icon || "🧩" }}</div>
            <div class="skill-card__meta">
              <div class="skill-card__name">
                {{ s.name }}
                <el-tag v-if="s.featured" size="small" type="warning" effect="plain">精选</el-tag>
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
        <el-empty description="暂无技能" />
      </el-col>
    </el-row>

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
          <el-input
            v-model="skillForm.content"
            type="textarea"
            :rows="6"
            placeholder="Markdown 指令/使用说明，绑定到智能体后并入系统提示词"
          />
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
          <pre class="skill-content-pre">{{ detail.content || "—" }}</pre>
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
import { ref, reactive, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Edit, Delete, View, Star, Link } from "@element-plus/icons-vue";
import {
  getAiSkillList,
  getAiSkillCategories,
  getAiSkillDetail,
  createAiSkill,
  updateAiSkill,
  deleteAiSkill,
  toggleAiSkillFeatured,
  installAiSkillToAgent,
} from "@/api/module_ai/skill";
import { getAiAgentList } from "@/api/module_ai/agent";

defineOptions({ name: "AiSkill" });

const loading = ref(false);
const skills = ref<any[]>([]);
const categories = ref<any[]>([]);
const activeTab = ref("all");

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
  return list;
});

const loadData = async () => {
  loading.value = true;
  try {
    const [sr, cr] = await Promise.all([getAiSkillList({}), getAiSkillCategories()]);
    skills.value = sr.data?.data || [];
    categories.value = cr.data?.data || [];
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

.skill-cat-card {
  margin-bottom: 12px;

  .skill-cat-bar {
    display: flex;
    align-items: center;
    gap: 16px;

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
</style>
