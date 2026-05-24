<template>
  <el-card shadow="hover">
    <div class="dept-tree-toolbar">
      <el-input v-model="groupName" placeholder="分组名称" class="dept-tree-search">
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-button
        type="primary"
        link
        size="small"
        class="dept-tree-expand-btn"
        @click="toggleTreeExpandAll"
      >
        <el-icon :size="14"><Switch /></el-icon>
        <span>{{ treeExpanded ? "收起" : "展开" }}</span>
      </el-button>
    </div>
    <el-tree
      ref="groupTreeRef"
      class="mt-2"
      node-key="value"
      :data="groupOptions"
      :props="{ children: 'children', label: 'label', disabled: 'disabled' }"
      :expand-on-click-node="false"
      :filter-node-method="handleFilter"
      default-expand-all
      highlight-current
      @node-click="handleNodeClick"
    >
      <template #empty>
        <el-empty :image-size="80" description="暂无数据" />
      </template>
    </el-tree>
  </el-card>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeMount } from "vue";
import { Switch } from "@element-plus/icons-vue";
import { getCameraGroupList } from "@/api/module_video/camera";
import { formatTree } from "@/utils/common";
import { useVModel } from "@vueuse/core";
import type { FilterNodeMethodFunction, TreeInstance } from "element-plus";

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: undefined,
  },
});

const groupOptions = ref<any[]>([]);
const groupTreeRef = ref<TreeInstance>();
const groupName = ref();
const treeExpanded = ref(true);

const emits = defineEmits(["node-click", "update:modelValue"]);

const groupId = useVModel(props, "modelValue", emits);

watch(groupName, (val) => {
  groupTreeRef.value?.filter(val);
});

type TreeStoreNode = {
  childNodes?: TreeStoreNode[];
  expand: () => void;
  collapse: () => void;
};

function getTreeRoot() {
  const tree = groupTreeRef.value as TreeInstance & { store?: { root: TreeStoreNode } };
  return tree?.store?.root;
}

function expandAllTreeNodes() {
  const root = getTreeRoot();
  if (!root) return;
  const walk = (node: TreeStoreNode) => {
    node.childNodes?.forEach((child) => {
      if (child.childNodes?.length) {
        child.expand();
        walk(child);
      }
    });
  };
  walk(root);
}

function collapseAllTreeNodes() {
  const root = getTreeRoot();
  if (!root) return;
  const walk = (node: TreeStoreNode) => {
    node.childNodes?.forEach((child) => {
      walk(child);
      child.collapse();
    });
  };
  walk(root);
}

function toggleTreeExpandAll() {
  if (treeExpanded.value) {
    collapseAllTreeNodes();
    treeExpanded.value = false;
  } else {
    expandAllTreeNodes();
    treeExpanded.value = true;
  }
}

interface Tree {
  [key: string]: any;
}

const handleFilter: FilterNodeMethodFunction = (value: string, data: Tree) => {
  if (!value) return true;
  return data.label.includes(value);
};

function handleNodeClick(data: { [key: string]: any }) {
  groupId.value = data.value;
  emits("node-click");
}

onBeforeMount(async () => {
  try {
    const res = await getCameraGroupList();
    groupOptions.value = formatTree(res.data.data || []);
  } catch {
    groupOptions.value = [];
  }
});
</script>

<style scoped lang="scss">
.dept-tree-toolbar {
  display: flex;
  gap: 4px;
  align-items: center;
  .dept-tree-search {
    flex: 1;
    min-width: 0;
  }
  .dept-tree-expand-btn {
    flex-shrink: 0;
    height: auto;
    min-height: unset;
    padding: 0 4px;
    font-size: 12px;
  }
}
</style>
