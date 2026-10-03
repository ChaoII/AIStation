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

export function searchAiKnowledge(id: number, query: string, topK = 5, useGraph = true) {
  return request({
    url: `${BASE}/${id}/search`,
    method: "post",
    data: { query, top_k: topK, use_graph: useGraph },
  });
}

export function getAiKnowledgeGraph(id: number) {
  return request({ url: `${BASE}/${id}/graph`, method: "get" });
}

export function getAiKnowledgeChunks(id: number) {
  return request({ url: `${BASE}/${id}/chunks`, method: "get" });
}

export function deleteAiKnowledgeChunk(id: number, chunkId: number) {
  return request({ url: `${BASE}/${id}/chunks/${chunkId}`, method: "delete" });
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
