import request from "@/utils/request";

const BASE = "/ai/knowledge/bases";
const DS = "/ai/knowledge/datasources";

// ---------- 知识库 ----------
export function getAiKnowledgeList(params?: { category_id?: number | null }) {
  return request({ url: `${BASE}/list`, method: "get", params });
}

export function getAiKnowledgeDetail(id: number) {
  return request({ url: `${BASE}/detail/${id}`, method: "get" });
}

export function createAiKnowledge(data: any) {
  return request({ url: `${BASE}/create`, method: "post", data });
}

export function updateAiKnowledge(id: number, data: any) {
  return request({ url: `${BASE}/update/${id}`, method: "put", data });
}

export function deleteAiKnowledge(ids: number[]) {
  return request({ url: `${BASE}/delete`, method: "delete", data: ids });
}

// ---------- 知识库分类（左侧分类树） ----------
const CAT = "/ai/knowledge/categories";

export interface AiKnowledgeCategoryNode {
  id: number;
  name: string;
  parent_id?: number | null;
  owner?: string;
  remark?: string;
  sort?: number;
  count?: number;
  children?: AiKnowledgeCategoryNode[];
}

export function getAiKnowledgeCategoryTree() {
  return request({ url: `${CAT}/tree`, method: "get" });
}
export function createAiKnowledgeCategory(data: {
  name: string;
  parent_id?: number | null;
  owner?: string;
  remark?: string;
  sort?: number;
}) {
  return request({ url: `${CAT}/create`, method: "post", data });
}
export function updateAiKnowledgeCategory(
  id: number,
  data: { name?: string; parent_id?: number | null; owner?: string; remark?: string; sort?: number }
) {
  return request({ url: `${CAT}/update/${id}`, method: "put", data });
}
export function deleteAiKnowledgeCategory(ids: number[]) {
  return request({ url: `${CAT}/delete`, method: "delete", data: ids });
}

// ---------- 入库 / 检索 / 分块 ----------
export function ingestAiKnowledge(id: number, data: any) {
  return request({ url: `${BASE}/${id}/ingest`, method: "post", data });
}

export function searchAiKnowledge(
  id: number,
  query: string,
  topK = 5,
  useGraph = true,
  mode = "hybrid",
  vectorWeight = 0.5,
  fulltextWeight = 0.5,
  opts: Record<string, any> = {}
) {
  return request({
    url: `${BASE}/${id}/search`,
    method: "post",
    data: {
      query,
      top_k: topK,
      use_graph: useGraph,
      mode,
      vector_weight: vectorWeight,
      fulltext_weight: fulltextWeight,
      ...opts,
    },
  });
}

export function askAiKnowledge(id: number, query: string, topK = 6, mode = "hybrid") {
  return request({
    url: `${BASE}/${id}/ask`,
    method: "post",
    data: { query, top_k: topK, mode },
  });
}

export function rebuildAiKnowledge(id: number) {
  return request({ url: `${BASE}/${id}/rebuild`, method: "post" });
}

export function getAiKnowledgeGraph(id: number) {
  return request({ url: `${BASE}/${id}/graph`, method: "get" });
}

// ---------- 图谱编辑（实体/关系 CRUD） ----------
export function createAiKnowledgeGraphEntity(
  id: number,
  data: { name: string; etype?: string; weight?: number; description?: string }
) {
  return request({ url: `${BASE}/${id}/graph/entity`, method: "post", data });
}
export function updateAiKnowledgeGraphEntity(
  id: number,
  entityId: number,
  data: { name?: string; etype?: string; weight?: number; description?: string }
) {
  return request({ url: `${BASE}/${id}/graph/entity/${entityId}`, method: "put", data });
}
export function deleteAiKnowledgeGraphEntities(id: number, ids: number[]) {
  return request({ url: `${BASE}/${id}/graph/entity`, method: "delete", data: ids });
}
export function createAiKnowledgeGraphRelation(
  id: number,
  data: { source: string; target: string; weight?: number; rtype?: string }
) {
  return request({ url: `${BASE}/${id}/graph/relation`, method: "post", data });
}
export function deleteAiKnowledgeGraphRelations(id: number, ids: number[]) {
  return request({ url: `${BASE}/${id}/graph/relation`, method: "delete", data: ids });
}

export function getAiKnowledgeChunks(id: number) {
  return request({ url: `${BASE}/${id}/chunks`, method: "get" });
}

export function deleteAiKnowledgeChunk(id: number, chunkId: number) {
  return request({ url: `${BASE}/${id}/chunks/${chunkId}`, method: "delete" });
}

export function updateAiKnowledgeChunk(id: number, chunkId: number, content: string) {
  return request({
    url: `${BASE}/${id}/chunks/${chunkId}`,
    method: "put",
    data: { content },
  });
}

// ---------- 分块标注 ----------
export function addAiKnowledgeChunkAnnotation(
  id: number,
  chunkId: number,
  text: string,
  kind = "alias",
  query?: string,
  source = "manual"
) {
  return request({
    url: `${BASE}/${id}/chunks/${chunkId}/annotations`,
    method: "post",
    data: { text, kind, query, source },
  });
}
export function removeAiKnowledgeChunkAnnotation(id: number, chunkId: number, index: number) {
  return request({
    url: `${BASE}/${id}/chunks/${chunkId}/annotations/${index}`,
    method: "delete",
  });
}
export function suggestAiKnowledgeAnnotate(id: number, query: string, topN = 5) {
  return request({
    url: `${BASE}/${id}/suggest-annotate`,
    method: "get",
    params: { query, top_n: topN },
  });
}
export function getAiKnowledgeAnnotationLogs(id: number) {
  return request({ url: `${BASE}/${id}/annotation-logs`, method: "get" });
}
export function getAiKnowledgeSearchStats(id: number, days = 30) {
  return request({
    url: `${BASE}/${id}/search-stats`,
    method: "get",
    params: { days },
  });
}
export function getAiKnowledgeChunkEntities(id: number, chunkId: number) {
  return request({ url: `${BASE}/${id}/chunks/${chunkId}/entities`, method: "get" });
}

// ---------- 实体 ↔ 分块 绑定 ----------
export function getAiKnowledgeEntityChunks(id: number, entityId: number) {
  return request({ url: `${BASE}/${id}/entities/${entityId}/chunks`, method: "get" });
}
export function bindAiKnowledgeEntityChunks(id: number, entityId: number, chunkIds: number[]) {
  return request({
    url: `${BASE}/${id}/entities/${entityId}/bind`,
    method: "post",
    data: { chunk_ids: chunkIds },
  });
}
export function unbindAiKnowledgeEntityChunks(id: number, entityId: number, chunkIds: number[]) {
  return request({
    url: `${BASE}/${id}/entities/${entityId}/unbind`,
    method: "post",
    data: { chunk_ids: chunkIds },
  });
}

// ---------- 图谱关系编辑 ----------
export function updateAiKnowledgeGraphRelation(
  id: number,
  relId: number,
  data: { source?: string; target?: string; weight?: number; rtype?: string }
) {
  return request({ url: `${BASE}/${id}/graph/relation/${relId}`, method: "put", data });
}
export function saveAiKnowledgeGraphLayout(
  id: number,
  items: { id: number; x: number; y: number }[]
) {
  return request({ url: `${BASE}/${id}/graph/layout`, method: "put", data: { items } });
}
export function clearAiKnowledgeGraphLayout(id: number) {
  return request({ url: `${BASE}/${id}/graph/layout`, method: "delete" });
}
// ---------- 关系类型模板 ----------
export function getAiRelationTypes() {
  return request({ url: `/ai/knowledge/relation-types`, method: "get" });
}
export function createAiRelationType(data: { name: string; color?: string }) {
  return request({ url: `/ai/knowledge/relation-types`, method: "post", data });
}
export function deleteAiRelationType(rid: number) {
  return request({ url: `/ai/knowledge/relation-types/${rid}`, method: "delete" });
}
// ---------- 文档管理（wikiLLM/ima 式） ----------
export function getAiKnowledgeDocuments(id: number) {
  return request({ url: `${BASE}/${id}/documents`, method: "get" });
}
export function uploadAiKnowledgeDocument(
  id: number,
  file: File,
  chunkSize = 500,
  overlap = 50,
  strategy = "fixed",
  useOcr = true
) {
  const form = new FormData();
  form.append("file", file);
  form.append("chunk_size", String(chunkSize));
  form.append("overlap", String(overlap));
  form.append("strategy", strategy);
  form.append("use_ocr", String(useOcr));
  return request({
    url: `${BASE}/${id}/documents/upload`,
    method: "post",
    data: form,
    headers: { "Content-Type": "multipart/form-data" },
  });
}
export function deleteAiKnowledgeDocument(id: number, docId: number) {
  return request({ url: `${BASE}/${id}/documents/${docId}`, method: "delete" });
}
export function getAiKnowledgeDocumentContent(id: number, docId: number) {
  return request({ url: `${BASE}/${id}/documents/${docId}/content`, method: "get" });
}
export function reparseAiKnowledgeDocument(id: number, docId: number) {
  return request({ url: `${BASE}/${id}/documents/${docId}/reparse`, method: "post" });
}
export function downloadAiKnowledgeDocument(id: number, docId: number) {
  return request({
    url: `${BASE}/${id}/documents/${docId}/download`,
    method: "get",
    responseType: "blob",
  });
}
export function getAiKnowledgeFaq(id: number, format = "json") {
  return request({ url: `${BASE}/${id}/faq`, method: "get", params: { format } });
}
export function copyAiKnowledge(id: number) {
  return request({ url: `${BASE}/${id}/copy`, method: "post" });
}

// ---------- 数据源 ----------
export function getAiDatasourceList() {
  return request({ url: `${DS}/list`, method: "get" });
}

export function createAiDatasource(data: any) {
  return request({ url: `${DS}/create`, method: "post", data });
}

export function updateAiDatasource(id: number, data: any) {
  return request({ url: `${DS}/update/${id}`, method: "put", data });
}

export function deleteAiDatasource(ids: number[]) {
  return request({ url: `${DS}/delete`, method: "delete", data: ids });
}

export function testAiDatasource(id: number) {
  return request({ url: `${DS}/${id}/test`, method: "post" });
}

export function syncAiDatasource(id: number, data: any) {
  return request({ url: `${DS}/${id}/sync`, method: "post", data });
}

// ---------- RAG 后台任务 ----------
const TASK = "/ai/knowledge/tasks";

export function getAiRagTask(taskId: number) {
  return request({ url: `${TASK}/${taskId}`, method: "get" });
}

export function getAiRagTaskList(params?: Record<string, any>) {
  return request({ url: TASK, method: "get", params });
}

export function cancelAiRagTask(taskId: number) {
  return request({ url: `${TASK}/${taskId}/cancel`, method: "post" });
}
// ---------- 检索评测 ----------
const EVAL = "/ai/knowledge/eval";

export function getAiEvalSets() {
  return request({ url: `${EVAL}/sets`, method: "get" });
}

export function createAiEvalSet(data: any) {
  return request({ url: `${EVAL}/sets`, method: "post", data });
}

export function getAiEvalItems(setId: number) {
  return request({ url: `${EVAL}/sets/${setId}/items`, method: "get" });
}

export function createAiEvalItem(setId: number, data: any) {
  return request({ url: `${EVAL}/sets/${setId}/items`, method: "post", data });
}

export function runAiEval(kbId: number, data: any) {
  return request({ url: `${BASE}/${kbId}/eval/run`, method: "post", data });
}

export function getAiEvalRuns(kbId: number) {
  return request({ url: `${BASE}/${kbId}/eval/runs`, method: "get" });
}
