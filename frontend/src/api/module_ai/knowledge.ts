import request from "@/utils/request";

const BASE = "/ai/knowledge/bases";
const DS = "/ai/knowledge/datasources";

// ---------- 知识库 ----------
export function getAiKnowledgeList() {
  return request({ url: `${BASE}/list`, method: "get" });
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
  fulltextWeight = 0.5
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
    },
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
  data: { name: string; etype?: string; weight?: number }
) {
  return request({ url: `${BASE}/${id}/graph/entity`, method: "post", data });
}
export function updateAiKnowledgeGraphEntity(id: number, entityId: number, data: any) {
  return request({ url: `${BASE}/${id}/graph/entity/${entityId}`, method: "put", data });
}
export function deleteAiKnowledgeGraphEntities(id: number, ids: number[]) {
  return request({ url: `${BASE}/${id}/graph/entity`, method: "delete", data: ids });
}
export function createAiKnowledgeGraphRelation(
  id: number,
  data: { source: string; target: string; weight?: number }
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
  data: { source?: string; target?: string; weight?: number }
) {
  return request({ url: `${BASE}/${id}/graph/relation/${relId}`, method: "put", data });
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
