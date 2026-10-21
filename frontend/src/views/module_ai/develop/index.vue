<!-- AI 集成开放平台：应用管理 / 调用日志 / MCP 会话 / 接入文档 -->
<template>
  <div class="app-container ai-develop-page">
    <el-card shadow="never" class="develop-shell" :body-style="{ padding: '0 16px 12px' }">
      <el-tabs v-model="activeTab" class="develop-tabs" @tab-change="onTabChange">
        <!-- ============ 应用管理 ============ -->
        <el-tab-pane label="应用管理" name="apps">
          <el-form :inline="true" :model="appSearch" class="develop-search">
            <el-form-item label="关键字">
              <el-input
                v-model="appSearch.keyword"
                placeholder="名称 / appid"
                clearable
                style="width: 220px"
                @keyup.enter="loadApps()"
              />
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadApps()">查询</el-button>
            </el-form-item>
          </el-form>

          <div class="develop-toolbar">
            <div class="develop-toolbar__left">
              <span class="develop-toolbar__hint">
                为外部平台创建接入应用，分配能力权限点并下发凭证。
              </span>
              <el-tag size="small" type="info" effect="plain" class="summary-tag">
                共 {{ appTotal }} 个应用
              </el-tag>
            </div>
            <el-button
              v-hasPerm="['module_ai:develop:create']"
              type="primary"
              :icon="Plus"
              @click="openCreate"
            >
              新增应用
            </el-button>
          </div>

          <el-table v-loading="appLoading" :data="apps" row-key="id" border stripe>
            <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
            <el-table-column label="AppID" min-width="170">
              <template #default="{ row }">
                <div class="appid-cell">
                  <span class="appid-cell__value">{{ row.appid_masked || "—" }}</span>
                  <el-tooltip content="复制完整 AppID" placement="top">
                    <el-button text type="primary" size="small" @click="copyText(row.appid)">
                      <el-icon><CopyDocument /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-switch
                  v-hasPerm="['module_ai:develop:update']"
                  :model-value="row.enabled !== false"
                  @change="(v) => onToggle(row, Boolean(v))"
                />
              </template>
            </el-table-column>
            <el-table-column label="到期时间" width="150">
              <template #default="{ row }">
                <span :class="{ 'text-muted': !row.expire_at }">
                  {{ fmtDateTime(row.expire_at) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="权限点" min-width="200">
              <template #default="{ row }">
                <template v-if="row.capabilities && row.capabilities.length">
                  <el-tooltip
                    v-for="perm in row.capabilities"
                    :key="perm"
                    :content="perm"
                    placement="top"
                  >
                    <el-tag size="small" effect="plain" class="cap-tag">
                      {{ perm.replace("integration:", "") }}
                    </el-tag>
                  </el-tooltip>
                </template>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column prop="call_count" label="调用次数" width="90" align="center" />
            <el-table-column label="操作" width="250" fixed="right">
              <template #default="{ row }">
                <el-button
                  v-hasPerm="['module_ai:develop:query']"
                  link
                  type="primary"
                  @click="openEmbed(row)"
                >
                  嵌入
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:update']"
                  link
                  type="primary"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:reset']"
                  link
                  type="primary"
                  @click="openKeyDialog(row)"
                >
                  AppKey
                </el-button>
                <el-button
                  v-hasPerm="['module_ai:develop:delete']"
                  link
                  type="danger"
                  @click="onDelete(row)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty :image-size="80" description="暂无应用，点击「新增应用」创建" />
            </template>
          </el-table>

          <div v-if="appTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="appPage"
              v-model:page-size="appPageSize"
              :total="appTotal"
              :page-sizes="[10, 20, 50, 100]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadApps(false)"
              @size-change="
                () => {
                  appPage = 1;
                  loadApps(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ 调用日志 ============ -->
        <el-tab-pane label="调用日志" name="logs">
          <el-form :inline="true" :model="logFilter" class="develop-search">
            <el-form-item label="应用">
              <el-select
                v-model="logFilter.app_id"
                placeholder="全部"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="品类">
              <el-select
                v-model="logFilter.category"
                placeholder="全部"
                clearable
                style="width: 140px"
              >
                <el-option
                  v-for="(label, code) in CATEGORIES"
                  :key="code"
                  :label="label"
                  :value="code"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="出海口">
              <el-select
                v-model="logFilter.method"
                placeholder="全部"
                clearable
                style="width: 140px"
              >
                <el-option label="REST" value="REST" />
                <el-option label="MCP" value="MCP" />
                <el-option label="EMBED" value="EMBED" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select
                v-model="logFilter.status"
                placeholder="全部"
                clearable
                style="width: 140px"
              >
                <el-option label="成功" value="success" />
                <el-option label="失败" value="failed" />
                <el-option label="拒绝" value="denied" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadLogs()">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="logLoading" :data="logs" row-key="id" border stripe>
            <el-table-column label="时间" width="165" show-overflow-tooltip>
              <template #default="{ row }">{{ fmtDateTime(row.created_time) }}</template>
            </el-table-column>
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column label="品类" width="85">
              <template #default="{ row }">
                {{ CATEGORIES[row.category || ""] || row.category }}
              </template>
            </el-table-column>
            <el-table-column prop="capability" label="能力" min-width="145" show-overflow-tooltip />
            <el-table-column prop="method" label="出海口" width="80" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="logStatusType(row.status)">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="latency_ms" label="耗时(ms)" width="85" align="right" />
            <el-table-column prop="cost_tokens" label="Tokens" width="78" align="right" />
            <el-table-column
              prop="request_path"
              label="请求路径"
              min-width="150"
              show-overflow-tooltip
            />
            <el-table-column
              prop="result_summary"
              label="结果摘要"
              min-width="160"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" description="暂无调用日志" />
            </template>
          </el-table>

          <div v-if="logTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="logPage"
              v-model:page-size="logPageSize"
              :total="logTotal"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadLogs(false)"
              @size-change="
                () => {
                  logPage = 1;
                  loadLogs(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ MCP 会话 ============ -->
        <el-tab-pane label="MCP 会话" name="mcp">
          <el-form :inline="true" :model="mcpFilter" class="develop-search">
            <el-form-item label="应用">
              <el-select
                v-model="mcpFilter.app_id"
                placeholder="全部"
                clearable
                filterable
                style="width: 180px"
              >
                <el-option v-for="a in appOptions" :key="a.id" :label="a.name" :value="a.id" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button :icon="Search" @click="loadMcps()">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="mcpLoading" :data="mcps" row-key="id" border stripe>
            <el-table-column label="AppID" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.appid || "—" }}</template>
            </el-table-column>
            <el-table-column label="会话ID" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono-text">{{ row.session_id || "—" }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="transport" label="传输" width="100" />
            <el-table-column
              prop="client_info"
              label="客户端"
              min-width="120"
              show-overflow-tooltip
            />
            <el-table-column label="开始时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column label="结束时间" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.ended_at, "—") }}</template>
            </el-table-column>
            <el-table-column prop="duration_s" label="时长(s)" width="80" align="right" />
            <el-table-column prop="tool_calls" label="工具调用" width="85" align="right" />
            <el-table-column
              prop="close_reason"
              label="关闭原因"
              min-width="120"
              show-overflow-tooltip
            />
            <template #empty>
              <el-empty :image-size="80" description="暂无 MCP 会话" />
            </template>
          </el-table>

          <div v-if="mcpTotal > 0" class="develop-pagination">
            <el-pagination
              v-model:current-page="mcpPage"
              v-model:page-size="mcpPageSize"
              :total="mcpTotal"
              :page-sizes="[10, 20, 50]"
              layout="total, sizes, prev, pager, next"
              background
              @current-change="() => loadMcps(false)"
              @size-change="
                () => {
                  mcpPage = 1;
                  loadMcps(false);
                }
              "
            />
          </div>
        </el-tab-pane>

        <!-- ============ 接入文档 ============ -->
        <el-tab-pane label="接入文档" name="docs">
          <div class="docs-wrap">
            <el-alert
              title="接入凭证说明"
              type="info"
              :closable="false"
              show-icon
              class="docs-alert"
              description="AppID 与 AppKey 只用于「服务端换票」：调用 POST /api/v1/ai/develop-api/auth/token 换取短期 access_token，嵌入页再用 Bearer token 访问 /ai/embed/*。切勿把 AppKey 写入网页或嵌入代码；AppKey 仅在创建或重置时展示一次。"
            />
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>REST 接入</span>
                  <el-tag size="small">HTTP</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                服务端持
                <code>appid:appkey</code>
                调用：能力清单、能力调用（统一入口
                <code>/capabilities/{code}</code>
                ）、对话与网页嵌入换票。响应统一为
                <code>{ code, msg, data }</code>
                。
              </p>
              <pre class="doc-code">{{ restExample }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>MCP 接入</span>
                  <el-tag size="small" type="success">Streamable HTTP</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                平台同时是 MCP Server：工具即能力，
                <code>tools/list</code>
                只返回该应用已授权的能力，调用与 REST 共用同一套鉴权、限流与审计。
              </p>
              <pre class="doc-code">{{ mcpExample }}</pre>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>开放能力清单</span>
                  <el-tag size="small" type="info">共 {{ capabilities.length }} 项</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                能力与权限点一一对应：应用只有被授予对应权限点，才会在能力清单与 MCP
                工具列表里看到它。
              </p>
              <el-table v-loading="capLoading" :data="capabilities" border stripe>
                <el-table-column prop="name" label="能力" min-width="130" show-overflow-tooltip />
                <el-table-column prop="code" label="能力码" width="130" />
                <el-table-column label="品类" width="100">
                  <template #default="{ row }">
                    {{ CATEGORIES[row.category] || row.category }}
                  </template>
                </el-table-column>
                <el-table-column prop="perm" label="所需权限点" width="200" />
                <el-table-column prop="mcp_tool" label="MCP 工具名" width="140">
                  <template #default="{ row }">
                    <span v-if="row.mcp_tool" class="mono-text">{{ row.mcp_tool }}</span>
                    <span v-else class="text-muted">—</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="description"
                  label="说明"
                  min-width="240"
                  show-overflow-tooltip
                />
                <template #empty>
                  <el-empty :image-size="80" description="暂无开放能力" />
                </template>
              </el-table>
            </el-card>
            <el-card shadow="never" class="doc-card">
              <template #header>
                <div class="doc-card__header">
                  <span>网页嵌入</span>
                  <el-tag size="small">Embed</el-tag>
                </div>
              </template>
              <p class="doc-card__desc">
                两种嵌入形态（iframe 直嵌 / Script SDK）。token
                由服务端换票下发；过期时宿主重新换票并调用
                <code>setToken()</code>
                续期，对话不中断。
              </p>
              <pre class="doc-code">{{ embedExample }}</pre>
              <div class="doc-events">
                <span class="doc-events__label">postMessage 事件</span>
                <el-tag
                  v-for="e in docEvents"
                  :key="e.name"
                  size="small"
                  effect="plain"
                  class="doc-events__tag"
                  :title="e.desc"
                >
                  {{ e.name }}
                </el-tag>
              </div>
              <p class="doc-card__desc doc-card__desc--foot">
                完整契约见「应用管理 → 嵌入」弹窗与下方示例注释；上行信封
                <code>{ source: "ai-embed", version: 1, event, payload }</code>
                。
              </p>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ============ 新增 / 编辑应用弹窗 ============ -->
    <EnhancedDialog
      v-model="dialog.visible"
      :title="dialog.title"
      append-to-body
      width="600px"
      @close="dialog.visible = false"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：合作伙伴平台接入" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
        <el-form-item label="授权能力">
          <div class="cap-groups">
            <div v-for="(catLabel, catCode) in CATEGORIES" :key="catCode" class="cap-group">
              <div class="cap-group__title">
                {{ catLabel }}
                <span class="cap-group__count">
                  {{ selectedCount(CATEGORY_PERMS[catCode]) }}/{{ CATEGORY_PERMS[catCode].length }}
                </span>
              </div>
              <el-checkbox-group v-model="form.capabilities">
                <el-checkbox
                  v-for="perm in CATEGORY_PERMS[catCode]"
                  :key="perm"
                  :value="perm"
                  class="cap-check"
                >
                  {{ perm.replace("integration:", "") }}
                </el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="凭证过期时间">
          <el-date-picker
            v-model="form.expire_at"
            type="datetime"
            placeholder="留空表示永久有效"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">保存</el-button>
      </template>
    </EnhancedDialog>

    <!-- ============ AppKey 查看 / 重置弹窗 ============ -->
    <el-dialog
      v-model="keyDialog.visible"
      :title="`AppKey · ${keyDialog.name || ''}`"
      width="520px"
      append-to-body
      @close="closeKeyDialog"
    >
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="AppID">
          <div class="appid-cell">
            <span class="mono-text">{{ keyDialog.appid || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(keyDialog.appid)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="AppKey">
          <template v-if="keyDialog.appkey">
            <div class="appid-cell">
              <span class="mono-text key-text">{{ keyDialog.appkey }}</span>
              <el-button text type="primary" size="small" @click="copyText(keyDialog.appkey)">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
          </template>
          <span v-else class="text-muted">
            AppKey 已加密存储，仅在创建或重置时显示一次，请先点击「重置 AppKey」获取。
          </span>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="keyDialog.visible = false">关闭</el-button>
        <el-button
          v-hasPerm="['module_ai:develop:reset']"
          type="primary"
          :loading="keyLoading"
          @click="onResetKey(keyDialog.row)"
        >
          重置 AppKey
        </el-button>
      </template>
    </el-dialog>

    <!-- ============ 创建成功：一次性展示 AppKey ============ -->
    <el-dialog
      v-model="reveal.visible"
      title="创建成功"
      width="520px"
      append-to-body
      :close-on-click-modal="false"
      @close="closeReveal"
    >
      <el-alert
        title="请立即保存 AppKey"
        type="warning"
        :closable="false"
        show-icon
        class="docs-alert"
        description="AppKey 仅在此处显示一次，关闭后将无法再次查看，请及时复制并妥善保存。"
      />
      <el-descriptions :column="1" border size="small" class="reveal-desc">
        <el-descriptions-item label="AppID">
          <div class="appid-cell">
            <span class="mono-text">{{ reveal.appid || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(reveal.appid)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="AppKey">
          <div class="appid-cell">
            <span class="mono-text key-text">{{ reveal.appkey || "—" }}</span>
            <el-button text type="primary" size="small" @click="copyText(reveal.appkey)">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="reveal.visible = false">我已保存</el-button>
      </template>
    </el-dialog>

    <!-- ============ 嵌入管理弹窗 ============ -->
    <EmbedDialog v-model="embedVisible" :app="embedRow" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Search, CopyDocument } from "@element-plus/icons-vue";
import {
  createApp,
  deleteApp,
  getCallLogs,
  getCapabilities,
  getDevelopAppList,
  getMcpSessions,
  resetAppkey,
  toggleApp,
  updateApp,
} from "@/api/module_ai/develop";
import EnhancedDialog from "@/components/CURD/EnhancedDialog.vue";
import EmbedDialog from "./components/EmbedDialog.vue";

defineOptions({ name: "AiDevelopManage" });

// ---- 能力品类目录（与后端 capabilities.py 保持一致） ----
const CATEGORIES: Record<string, string> = {
  train: "模型训练",
  agent: "智能体",
  chat: "对话",
  bot: "机器人",
  embed: "网页嵌入",
};
const CATEGORY_PERMS: Record<string, string[]> = {
  train: [
    "integration:train:create",
    "integration:train:query",
    "integration:train:start",
    "integration:train:stop",
  ],
  agent: [
    "integration:agent:create",
    "integration:agent:query",
    "integration:agent:update",
    "integration:agent:delete",
  ],
  chat: ["integration:chat:send", "integration:chat:query"],
  bot: ["integration:bot:use"],
  embed: ["integration:embed:use"],
};

interface AppRow {
  id: number;
  appid: string;
  appid_masked?: string;
  name: string;
  description?: string;
  enabled: boolean;
  expire_at?: string | null;
  capabilities?: string[];
  call_count?: number;
}
interface LogRow {
  id: number;
  created_time?: string;
  appid?: string;
  category?: string;
  capability?: string;
  method?: string;
  status?: string;
  latency_ms?: number;
  cost_tokens?: number;
  request_path?: string;
  result_summary?: string;
}
interface McpRow {
  id: number;
  created_time?: string;
  appid?: string;
  session_id?: string;
  transport?: string;
  client_info?: string;
  started_at?: string;
  ended_at?: string;
  duration_s?: number;
  tool_calls?: number;
  close_reason?: string;
}

const activeTab = ref("apps");

// ============ 应用管理 ============
const appLoading = ref(false);
const apps = ref<AppRow[]>([]);
const appTotal = ref(0);
const appPage = ref(1);
const appPageSize = ref(10);
const appSearch = reactive({ keyword: "" });

// 用于日志/MCP 过滤的应用下拉选项
const appOptions = ref<{ id: number; name: string }[]>([]);

async function loadAppOptions() {
  try {
    const res = await getDevelopAppList({ page_no: 1, page_size: 100 });
    const items = res.data?.data?.items || [];
    appOptions.value = items.map((i: any) => ({ id: i.id, name: i.name }));
  } catch {
    // 下拉仅作过滤辅助，加载失败不阻断主列表
  }
}

async function loadApps(resetPage = true) {
  if (resetPage) appPage.value = 1;
  appLoading.value = true;
  try {
    const res = await getDevelopAppList({
      keyword: appSearch.keyword || undefined,
      page_no: appPage.value,
      page_size: appPageSize.value,
    });
    const d = res.data?.data || {};
    apps.value = d.items || [];
    appTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    appLoading.value = false;
  }
}

// ---- 新增 / 编辑弹窗 ----
const dialog = reactive({ visible: false, title: "" });
const isEdit = ref(false);
const submitLoading = ref(false);
const form = reactive({
  id: undefined as number | undefined,
  name: "",
  description: "",
  capabilities: [] as string[],
  expire_at: "" as string,
  enabled: true,
});

function resetForm() {
  Object.assign(form, {
    id: undefined,
    name: "",
    description: "",
    capabilities: [],
    expire_at: "",
    enabled: true,
  });
}

function selectedCount(perms: string[]) {
  return form.capabilities.filter((p) => perms.includes(p)).length;
}

function openCreate() {
  resetForm();
  isEdit.value = false;
  dialog.title = "新增应用";
  dialog.visible = true;
}

function openEdit(row: any) {
  resetForm();
  isEdit.value = true;
  dialog.title = `编辑应用：${row.name}`;
  Object.assign(form, {
    id: row.id,
    name: row.name,
    description: row.description || "",
    capabilities: row.capabilities || [],
    expire_at: row.expire_at ? fmtDateTime(row.expire_at) : "",
    enabled: row.enabled !== false,
  });
  dialog.visible = true;
}

async function handleSubmit() {
  if (!form.name.trim()) {
    ElMessage.warning("请填写应用名称");
    return;
  }
  const payload: any = {
    name: form.name.trim(),
    description: form.description?.trim() || null,
    capabilities: form.capabilities,
    expire_at: form.expire_at || null,
    enabled: form.enabled,
  };
  submitLoading.value = true;
  try {
    if (form.id) {
      await updateApp(form.id, payload);
      dialog.visible = false;
      ElMessage.success("保存成功");
      await loadApps(false);
    } else {
      const res = await createApp(payload);
      dialog.visible = false;
      // 创建成功：一次性展示明文 AppKey
      const d = res.data?.data || {};
      Object.assign(reveal, { visible: true, appid: d.appid || "", appkey: d.appkey || "" });
      await loadApps(false);
    }
  } catch (e: any) {
    ElMessage.error(e?.msg || "保存失败");
  } finally {
    submitLoading.value = false;
  }
}

// ---- 启用 / 停用：局部刷新，只更新对应行 ----
async function onToggle(row: any, enabled: boolean) {
  try {
    await toggleApp(row.id, enabled);
    row.enabled = enabled;
    ElMessage.success(enabled ? "已启用" : "已停用");
  } catch (e: any) {
    ElMessage.error(e?.msg || "操作失败");
  }
}

// ---- 删除：二次确认 ----
async function onDelete(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认删除应用「${row.name}」？删除后其 AppID/AppKey 立即失效，历史调用日志与 MCP 会话将无法关联该应用，且不可恢复。`,
      "删除确认",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  try {
    await deleteApp([row.id]);
    await loadApps(false);
    ElMessage.success("删除成功");
  } catch (e: any) {
    ElMessage.error(e?.msg || "删除失败");
  }
}

// ---- AppKey 查看 / 重置 ----
const keyDialog = reactive({
  visible: false,
  row: null as AppRow | null,
  name: "",
  appid: "",
  appkey: "",
});
const keyLoading = ref(false);

function openKeyDialog(row: any) {
  keyDialog.row = row;
  keyDialog.name = row.name;
  keyDialog.appid = row.appid;
  keyDialog.appkey = "";
  keyDialog.visible = true;
}
function closeKeyDialog() {
  // 不持久化明文 AppKey
  keyDialog.appkey = "";
  keyDialog.row = null;
}
async function onResetKey(row: any) {
  if (!row) return;
  try {
    await ElMessageBox.confirm(
      `重置后应用「${row.name}」的原 AppKey 将立即失效，所有已下发的调用凭证都需更换，且不可恢复。是否继续？`,
      "重置 AppKey",
      { type: "warning", confirmButtonText: "重置", cancelButtonText: "取消" }
    );
  } catch {
    return;
  }
  keyLoading.value = true;
  try {
    const res = await resetAppkey(row.id);
    const d = res.data?.data || {};
    keyDialog.appid = d.appid || row.appid;
    keyDialog.appkey = d.appkey || "";
    ElMessage.success("AppKey 已重置");
  } catch (e: any) {
    ElMessage.error(e?.msg || "重置失败");
  } finally {
    keyLoading.value = false;
  }
}

// ---- 创建成功 reveal 弹窗 ----
const reveal = reactive({ visible: false, appid: "", appkey: "" });
function closeReveal() {
  // 一次性展示，关闭后清空，不持久化
  reveal.appid = "";
  reveal.appkey = "";
}

// ============ 调用日志 ============
const logLoading = ref(false);
const logs = ref<LogRow[]>([]);
const logTotal = ref(0);
const logPage = ref(1);
const logPageSize = ref(10);
const logFilter = reactive({
  app_id: undefined as number | undefined,
  category: "",
  method: "",
  status: "",
});

async function loadLogs(resetPage = true) {
  if (resetPage) logPage.value = 1;
  logLoading.value = true;
  try {
    const res = await getCallLogs({
      app_id: toNum(logFilter.app_id),
      category: logFilter.category || undefined,
      method: logFilter.method || undefined,
      status: logFilter.status || undefined,
      page_no: logPage.value,
      page_size: logPageSize.value,
    });
    const d = res.data?.data || {};
    logs.value = d.items || [];
    logTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    logLoading.value = false;
  }
}

function logStatusType(status?: string) {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "denied") return "warning";
  return "info";
}

// ============ MCP 会话 ============
const mcpLoading = ref(false);
const mcps = ref<McpRow[]>([]);
const mcpTotal = ref(0);
const mcpPage = ref(1);
const mcpPageSize = ref(10);
const mcpFilter = reactive({ app_id: undefined as number | undefined });

async function loadMcps(resetPage = true) {
  if (resetPage) mcpPage.value = 1;
  mcpLoading.value = true;
  try {
    const res = await getMcpSessions({
      app_id: toNum(mcpFilter.app_id),
      page_no: mcpPage.value,
      page_size: mcpPageSize.value,
    });
    const d = res.data?.data || {};
    mcps.value = d.items || [];
    mcpTotal.value = d.total || 0;
  } catch (e: any) {
    ElMessage.error(e?.msg || "加载失败");
  } finally {
    mcpLoading.value = false;
  }
}

function onTabChange(name: string | number) {
  const key = String(name);
  if (key === "logs") loadLogs(false);
  else if (key === "mcp") loadMcps(false);
  else if (key === "docs" && !capabilities.value.length) loadCapabilities();
}

// ---- 开放能力清单（接入文档页签） ----
const capabilities = ref<any[]>([]);
const capLoading = ref(false);

async function loadCapabilities() {
  capLoading.value = true;
  try {
    const res = await getCapabilities();
    capabilities.value = res.data?.data?.items || [];
  } catch (e: any) {
    ElMessage.error(e?.msg || "能力清单加载失败");
  } finally {
    capLoading.value = false;
  }
}

// ---- 通用工具 ----
function fmtDateTime(v?: string | null, emptyText = "永久"): string {
  if (!v) return emptyText;
  return String(v).replace("T", " ").slice(0, 19);
}

function toNum(v: unknown): number | undefined {
  if (v === "" || v === null || v === undefined) return undefined;
  const n = Number(v);
  return Number.isNaN(n) ? undefined : n;
}

async function copyText(text?: string) {
  if (!text) return;
  const doCopy = async () => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    throw new Error("clipboard unavailable");
  };
  try {
    await doCopy();
    ElMessage.success("已复制");
  } catch {
    // 降级方案：兼容非 https / 非 localhost 场景
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      ElMessage.success("已复制");
    } catch {
      ElMessage.error("复制失败，请手动复制");
    } finally {
      document.body.removeChild(ta);
    }
  }
}

// ---- 接入文档示例（纯文本，避免模板解析脚本标签） ----
const restExample = `# 1. 凭证校验：确认应用状态与已授权能力
curl -X GET "https://<host>/api/v1/ai/develop-api/auth/verify" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 2. 能力清单：只返回本应用**已授权**的能力
curl -X GET "https://<host>/api/v1/ai/develop-api/capabilities" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 3. 调用能力（统一入口）：code 取自能力清单，body 固定为 {"payload": {...}}
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/agent.create" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"agent_name": "外部创建助手"}}'

# 4. 对话（聚合回复，非流式）
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/chat.send" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"kind": "workflow", "target_id": 12, "message": "你好"}}'

# 5. 网页嵌入换票（浏览器面不接触 appkey）
curl -X POST "https://<host>/api/v1/ai/develop-api/auth/token" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"kind": "agent", "target_id": 123}'`;

const mcpExample = `// 端点（Streamable HTTP）：https://<host>/api/v1/ai/develop-api/mcp
// 鉴权：请求头 Authorization: Bearer {appid}:{appkey}（与 REST 同一套凭证）

// 方式一：客户端原生支持自定义请求头（推荐）
{
  "mcpServers": {
    "aistation": {
      "type": "http",
      "url": "https://<host>/api/v1/ai/develop-api/mcp",
      "headers": { "Authorization": "Bearer {appid}:{appkey}" }
    }
  }
}

// 方式二：客户端只支持 stdio（用 mcp-remote 代理转发请求头）
{
  "mcpServers": {
    "aistation": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://<host>/api/v1/ai/develop-api/mcp",
        "--header", "Authorization: Bearer {appid}:{appkey}"
      ]
    }
  }
}

// 工具 = 能力：tools/list 只返回该应用已授权的能力；每次调用都写审计。`;

const embedExample =
  `<!-- 方式一：iframe 直嵌（token 由服务端换票注入） -->
<iframe src="https://<host>/web/#/embed?token={access_token}"
        width="420" height="620" style="border:0;border-radius:12px"></iframe>

<!-- 方式二：Script SDK（推荐：事件回调 + 续期） -->
<script src="https://<host>/api/v1/ai/embed/sdk.js"></scr` +
  `ipt>
<div id="ai-assistant" style="width:420px;height:620px"></div>
<script>
  const ai = AiAssistant.init({
    container: "#ai-assistant",
    token: "{access_token}",
    apiBase: "https://<host>/api/v1/ai",
    webBase: "https://<host>/web",
    theme: { primary: "#409eff" }
  });
  ai.on("token_expired", async () => {
    ai.setToken(await fetchTokenFromYourBackend());  // 服务端重新换票
  });
</scr` +
  `ipt>`;

/** postMessage 事件契约（完整载荷见「嵌入」弹窗）。 */
const docEvents = [
  { name: "ready", desc: "初始化完成" },
  { name: "user_message", desc: "用户消息" },
  { name: "reply_start", desc: "开始回复" },
  { name: "reply_delta", desc: "流式增量" },
  { name: "reply_done", desc: "回复完成" },
  { name: "error", desc: "错误（网络/限流）" },
  { name: "token_expired", desc: "凭证过期" },
];

// ---- 嵌入管理弹窗 ----
const embedVisible = ref(false);
const embedRow = ref<any>(null);
function openEmbed(row: any) {
  embedRow.value = row;
  embedVisible.value = true;
}

onMounted(() => {
  loadApps();
  loadAppOptions();
});
</script>

<style scoped>
.develop-search {
  margin-bottom: 4px;
}

.develop-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.develop-toolbar__left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.develop-toolbar__hint {
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-secondary);
}

.summary-tag {
  flex-shrink: 0;
}

.develop-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.cap-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}

.appid-cell {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.appid-cell__value {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.mono-text {
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.key-text {
  color: var(--el-color-primary);
  word-break: break-all;
}

.text-muted {
  color: var(--el-text-color-placeholder);
}

.cap-groups {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.cap-group {
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.cap-group__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-primary);
}

.cap-group__count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.cap-check {
  margin-right: 12px;
}

.docs-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.docs-alert {
  margin-bottom: 0;
}

.doc-card {
  border: 1px solid var(--el-border-color-lighter);
}

.doc-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.doc-card__desc {
  margin: 0 0 12px;
  font-size: var(--el-font-size-base);
  color: var(--el-text-color-regular);
}

.doc-code {
  padding: 12px 14px;
  margin: 0;
  overflow-x: auto;
  font-family: var(--el-font-family-mono, monospace);
  font-size: var(--el-font-size-base);
  line-height: 1.6;
  color: var(--el-text-color-primary);
  white-space: pre;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
}

.reveal-desc {
  margin-top: 12px;
}
.doc-events {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-top: 10px;
}

.doc-events__label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.doc-events__tag {
  font-family: var(--el-font-family-mono, monospace);
}

.doc-card__desc--foot {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.doc-card__desc--foot code {
  padding: 0 3px;
  font-family: var(--el-font-family-mono, monospace);
}
</style>
<style lang="scss">
/* 页面外壳与「能力市场」一致：12px 留白 + 白色面板 + 页签独立滚动 */
.app-container.ai-develop-page {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px;
  overflow: hidden;
}

.ai-develop-page .develop-shell {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.ai-develop-page .develop-shell > .el-card__body {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.ai-develop-page .develop-tabs {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 0;
}

.ai-develop-page .develop-tabs > .el-tabs__header {
  flex: 0 0 auto;
  margin-bottom: 8px;
}

.ai-develop-page .develop-tabs > .el-tabs__content {
  flex: 1 1 auto;
  min-height: 0;
  padding-top: 4px;
  padding-right: 4px;
  overflow-y: auto;
}
</style>
