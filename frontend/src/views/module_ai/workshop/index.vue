<!-- 无代码应用 Workshop（Palantir Foundry 支柱） -->
<template>
  <div class="app-container ai-mod ai-workshop-page">
    <PageHeader title="无代码应用" />
    <el-card shadow="never">
      <template #header>
        <div class="mw-head">
          <span>对象应用（Workshop 无代码应用）</span>
          <el-button type="primary" size="small" :icon="Plus" @click="openCreate">
            新建应用
          </el-button>
        </div>
      </template>
      <el-table :data="apps" size="small" border>
        <template #empty>
          <el-empty description="暂无对象应用，点击「新建应用」在业务对象上构建" :image-size="60" />
        </template>
        <el-table-column prop="name" label="应用" min-width="140" show-overflow-tooltip />
        <el-table-column prop="object_table" label="对象" min-width="150" show-overflow-tooltip />
        <el-table-column prop="view_type" label="视图" width="80">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.view_type === "form" ? "表单" : "看板" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="列" min-width="180">
          <template #default="{ row }">
            <el-tag
              v-for="c in row.columns"
              :key="c"
              size="small"
              effect="plain"
              style="margin: 0 2px"
            >
              {{ c }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="preview(row)">预览</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import { getWorkshopList, workshopPreview } from "@/api/module_ai/query";

const apps = ref<any[]>([]);
async function load() {
  try {
    const r = await getWorkshopList();
    apps.value = r.data?.data || [];
  } catch {
    apps.value = [];
  }
}
async function preview(row: any) {
  const r = await workshopPreview(row.id, 10);
  const d = r.data?.data || {};
  ElMessage.success(d.ok ? `${row.name} 读取到 ${(d.rows || []).length} 行` : d.msg);
}
function openCreate() {
  ElMessage.info("请在「智能问数→指标运营→应用」标签中新建对象应用");
}
onMounted(load);
</script>

<style scoped lang="scss">
.ai-workshop-page {
  padding: 12px;
}
.mw-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
