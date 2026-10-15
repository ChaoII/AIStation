<!-- MCP 服务器管理：配置 CRUD + 连接测试 + 启停 -->
<template>
  <div class="app-container ai-mcp-page">
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <el-input
          v-model="keyword"
          class="search-input"
          :prefix-icon="Search"
          placeholder="搜索服务器名称"
          clearable
        />
        <el-button
          v-hasPerm="['module_ai:mcp:create']"
          type="primary"
          :icon="Plus"
          @click="openDialog()"
        >
          新增服务器
        </el-button>
        <el-tag size="small" type="info" effect="plain">
          共 {{ filtered.length }} 个服务器 · 启用 {{ enabledCount }}
        </el-tag>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table v-loading="loading" :data="filtered" border stripe>
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="传输方式" width="140">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.transport }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="地址/命令" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.transport === 'stdio'">
              {{ row.command }} {{ (row.args || []).join(" ") }}
            </span>
            <span v-else>{{ row.url }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || "—" }}</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :disabled="!canUpdate"
              @change="(v: any) => toggle(row as any, v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :icon="Link" @click="testServer(row as any)">测试</el-button>
            <el-button
              v-hasPerm="['module_ai:mcp:update']"
              size="small"
              :icon="Edit"
              @click="openDialog(row as any)"
            >
              编辑
            </el-button>
            <el-button
              v-hasPerm="['module_ai:mcp:delete']"
              size="small"
              type="danger"
              :icon="Delete"
              @click="removeServer(row as any)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !filtered.length" description="暂无 MCP 服务器，点击右上角新增" />
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="form.id ? '编辑 MCP 服务器' : '新增 MCP 服务器'"
      width="600px"
      append-to-body
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="128" placeholder="如：本地文件服务" />
        </el-form-item>
        <el-form-item label="传输方式" prop="transport">
          <el-radio-group v-model="form.transport">
            <el-radio-button value="stdio">stdio</el-radio-button>
            <el-radio-button value="sse">sse</el-radio-button>
            <el-radio-button value="streamable-http">streamable-http</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <template v-if="form.transport === 'stdio'">
          <el-form-item label="启动命令" prop="command">
            <el-input v-model="form.command" placeholder="如：npx 或 python" />
          </el-form-item>
          <el-form-item label="命令参数">
            <el-input
              v-model="argsText"
              type="textarea"
              :rows="2"
              placeholder="每行一个参数，例如：&#10;-y&#10;@modelcontextprotocol/server-filesystem&#10;D:/data"
            />
          </el-form-item>
          <el-form-item label="环境变量">
            <el-input
              v-model="envText"
              type="textarea"
              :rows="2"
              placeholder="每行 KEY=VALUE，例如：&#10;API_KEY=xxx"
            />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="服务地址" prop="url">
            <el-input v-model="form.url" placeholder="https://example.com/mcp" />
          </el-form-item>
          <el-form-item label="请求头">
            <el-input
              v-model="headersText"
              type="textarea"
              :rows="2"
              placeholder="每行 KEY=VALUE，例如：&#10;Authorization=Bearer xxx"
            />
          </el-form-item>
          <el-form-item label="鉴权方式">
            <el-select v-model="form.auth_type" class="full-width">
              <el-option label="无" value="none" />
              <el-option label="Bearer Token" value="bearer" />
              <el-option label="自定义请求头" value="custom" />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Delete, Edit, Link, Plus, Search } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type FormInstance } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import {
  createMcp,
  deleteMcp,
  getMcpList,
  testMcp,
  toggleMcp,
  updateMcp,
  type McpServer,
} from "@/api/module_ai/mcp";
import { ROLE_ROOT } from "@/constants";
import { useUserStore } from "@/store";

defineOptions({ name: "AiMcp" });

const userStore = useUserStore();
const canUpdate = computed(() => {
  const roles = userStore.basicInfo.roles?.map((r) => r.code) || [];
  return roles.includes(ROLE_ROOT) || userStore.prems.includes("module_ai:mcp:update");
});

const loading = ref(false);
const rows = ref<McpServer[]>([]);
const keyword = ref("");

const dialogVisible = ref(false);
const saving = ref(false);
const formRef = ref<FormInstance>();
const form = reactive({
  id: 0,
  name: "",
  transport: "streamable-http",
  command: "",
  url: "",
  auth_type: "none",
  description: "",
  enabled: true,
});
const argsText = ref("");
const envText = ref("");
const headersText = ref("");

const rules = {
  name: [{ required: true, message: "请输入名称", trigger: "blur" }],
  command: [{ required: true, message: "stdio 方式必须填写启动命令", trigger: "blur" }],
  url: [{ required: true, message: "必须填写服务地址", trigger: "blur" }],
};

const filtered = computed(() =>
  rows.value.filter((r) => !keyword.value || r.name.includes(keyword.value))
);
const enabledCount = computed(() => rows.value.filter((r) => r.enabled).length);

function parseLines(text: string): string[] {
  return text
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseKv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of parseLines(text)) {
    const idx = line.indexOf("=");
    if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return out;
}

async function load() {
  loading.value = true;
  try {
    const res: any = await getMcpList();
    rows.value = res.data || [];
  } finally {
    loading.value = false;
  }
}

function openDialog(row?: McpServer) {
  if (row) {
    form.id = row.id;
    form.name = row.name;
    form.transport = row.transport;
    form.command = row.command;
    form.url = row.url;
    form.auth_type = row.auth_type;
    form.description = row.description;
    form.enabled = row.enabled;
    argsText.value = (row.args || []).join("\n");
    envText.value = Object.entries(row.env || {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
    headersText.value = Object.entries(row.headers || {})
      .map(([k, v]) => `${k}=${v}`)
      .join("\n");
  } else {
    form.id = 0;
    form.name = "";
    form.transport = "streamable-http";
    form.command = "";
    form.url = "";
    form.auth_type = "none";
    form.description = "";
    form.enabled = true;
    argsText.value = "";
    envText.value = "";
    headersText.value = "";
  }
  dialogVisible.value = true;
}

async function save() {
  if (!formRef.value) return;
  await formRef.value.validate();
  const payload: any = {
    name: form.name,
    transport: form.transport,
    command: form.command,
    url: form.url,
    auth_type: form.auth_type,
    description: form.description,
    enabled: form.enabled,
  };
  if (form.transport === "stdio") {
    payload.args = parseLines(argsText.value);
    payload.env = parseKv(envText.value);
    payload.url = "";
  } else {
    payload.headers = parseKv(headersText.value);
    payload.command = "";
    payload.args = [];
  }
  saving.value = true;
  try {
    if (form.id) {
      await updateMcp(form.id, payload);
      ElMessage.success("修改成功");
    } else {
      await createMcp(payload);
      ElMessage.success("创建成功");
    }
    dialogVisible.value = false;
    load();
  } finally {
    saving.value = false;
  }
}

async function toggle(row: McpServer, value: any) {
  const enabled = Boolean(value);
  await toggleMcp(row.id, enabled);
  row.enabled = enabled;
  ElMessage.success(enabled ? "已启用" : "已停用");
}

async function testServer(row: McpServer) {
  const res: any = await testMcp(row.id);
  const data = res.data || {};
  if (data.reachable) {
    ElMessage.success(`连接正常：${data.detail}`);
  } else {
    ElMessage.warning(`连接失败：${data.detail}`);
  }
}

async function removeServer(row: McpServer) {
  await ElMessageBox.confirm(
    `将删除 MCP 服务器「${row.name}」，绑定它的智能体将失去该服务器的工具。是否继续？`,
    "删除确认",
    { confirmButtonText: "删除", cancelButtonText: "取消", type: "warning" }
  );
  await deleteMcp([row.id]);
  ElMessage.success("删除成功");
  load();
}

onMounted(load);
</script>

<style lang="scss" scoped>
.toolbar-card {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  width: 240px;
}

.full-width {
  width: 100%;
}
</style>
