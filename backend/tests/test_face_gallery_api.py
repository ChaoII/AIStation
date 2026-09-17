"""人脸底库 API 测试：录入/更新、列表、删除、比对（余弦相似度 top-k）。

覆盖 B3 云侧底库资产：``video_face_gallery`` 表 + ``/video/face-gallery`` 路由。
用例结束自清（删除本用例录入的行），避免影响后续依赖「底库为空」的目录提示断言。
"""
from app.api.v1.module_video.face_gallery.store import face_gallery_store

BASE = "/api/v1/video/face-gallery"
E_A = [1.0, 0.0, 0.0, 0.0]
E_B = [0.0, 1.0, 0.0, 0.0]


def _enroll(client, headers, **overrides):
    payload = {
        "name": "B3 测试人员",
        "person_no": "B3-001",
        "model_key": "w600k_r50",
        "embedding": E_A,
    }
    payload.update(overrides)
    return client.post(f"{BASE}/enroll", json=payload, headers=headers)


def test_face_gallery_lifecycle_crud_and_match(test_client, auth_headers):
    """完整生命周期：录入 → 列表 → 比对 → 更新 → 删除 → 底库清空。"""
    created_ids: list[int] = []
    try:
        # 1) 录入（维度按 embedding 长度自动推导）
        resp = _enroll(test_client, auth_headers)
        assert resp.status_code == 200, resp.text
        item = resp.json()["data"]
        created_ids.append(item["id"])
        assert item["name"] == "B3 测试人员"
        assert item["dimension"] == 4
        # 响应体不得回传特征向量（避免响应膨胀/泄露）
        assert "embedding" not in item

        # 2) 列表可查且不含 embedding
        resp = test_client.get(f"{BASE}/list", headers=auth_headers, params={"name": "B3 测试人员"})
        assert resp.status_code == 200, resp.text
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["id"] == item["id"]
        assert "embedding" not in items[0]

        # 3) 比对：同向量 score≈1.0，命中该条目
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "top_k": 5}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        matched = resp.json()["data"]["items"]
        assert len(matched) == 1
        assert matched[0]["id"] == item["id"]
        assert matched[0]["score"] == 1.0

        # 4) 比对：正交向量低于阈值 → 不返回
        resp = test_client.post(
            f"{BASE}/match",
            json={"embedding": E_B, "threshold": 0.6},
            headers=auth_headers,
        )
        assert resp.json()["data"]["items"] == []

        # 5) 更新：按 id 改姓名与特征（enroll 幂等 upsert）
        resp = _enroll(test_client, auth_headers, id=item["id"], name="B3 改名", embedding=E_B)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["name"] == "B3 改名"
        # 更新后旧特征不再命中（阈值 0.6），新特征命中
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "threshold": 0.6}, headers=auth_headers
        )
        assert resp.json()["data"]["items"] == []
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_B, "threshold": 0.6}, headers=auth_headers
        )
        assert resp.json()["data"]["items"][0]["name"] == "B3 改名"

        # 6) 删除后底库清空，比对不再返回
        resp = test_client.request(
            "DELETE", f"{BASE}/delete", json=created_ids, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        created_ids.clear()
        resp = test_client.get(f"{BASE}/list", headers=auth_headers, params={"name": "B3"})
        assert resp.json()["data"]["total"] == 0
        resp = test_client.post(f"{BASE}/match", json={"embedding": E_B}, headers=auth_headers)
        assert resp.json()["data"]["items"] == []
    finally:
        if created_ids:
            test_client.request("DELETE", f"{BASE}/delete", json=created_ids, headers=auth_headers)
        face_gallery_store.clear()


def test_face_gallery_match_empty_gallery_returns_empty(test_client, auth_headers):
    """空底库比对必须返回空列表（fail-closed），不得报错。"""
    resp = test_client.post(f"{BASE}/match", json={"embedding": E_A}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] == {"items": [], "total": 0}


def test_face_gallery_enroll_validation(test_client, auth_headers):
    """维度不一致/空向量/超维 一律 422（脏特征不得入库）。"""
    resp = _enroll(test_client, auth_headers, embedding=[1.0, 0.0], dimension=4)
    assert resp.status_code == 422, resp.text
    resp = _enroll(test_client, auth_headers, embedding=[])
    assert resp.status_code == 422, resp.text
    resp = _enroll(test_client, auth_headers, embedding=[1.0] * 5000)
    assert resp.status_code == 422, resp.text


def test_face_gallery_create_requires_embedding(test_client, auth_headers):
    """新增（无 id）时 embedding 必填 → 422。"""
    resp = test_client.post(f"{BASE}/enroll", json={"name": "无特征"}, headers=auth_headers)
    assert resp.status_code == 422, resp.text


def test_face_gallery_update_name_without_embedding(test_client, auth_headers):
    """按 id 更新可只改名（省略 embedding，特征保持不变）。"""
    ids: list[int] = []
    try:
        resp = _enroll(test_client, auth_headers, name="B3 待改名")
        item = resp.json()["data"]
        ids.append(item["id"])
        resp = test_client.post(
            f"{BASE}/enroll",
            json={"id": item["id"], "name": "B3 已改名", "person_no": "B3-001", "model_key": "w600k_r50"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["name"] == "B3 已改名"
        # 特征未变：原向量仍可命中
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "threshold": 0.6}, headers=auth_headers
        )
        assert resp.json()["data"]["items"][0]["name"] == "B3 已改名"
    finally:
        if ids:
            test_client.request("DELETE", f"{BASE}/delete", json=ids, headers=auth_headers)
        face_gallery_store.clear()


def test_face_gallery_enroll_refreshes_leaf_cache(test_client, auth_headers):
    """录入/删除必须同步刷新进程内底库缓存（规则叶子立即可用）。"""
    ids: list[int] = []
    try:
        resp = _enroll(test_client, auth_headers, name="B3 缓存刷新")
        ids.append(resp.json()["data"]["id"])
        assert face_gallery_store.size() >= 1
    finally:
        if ids:
            test_client.request("DELETE", f"{BASE}/delete", json=ids, headers=auth_headers)
        # 删除后缓存应回到空（该库中无其他底库行）
        assert face_gallery_store.size() == 0


# ── B4：kind 底库类型（face/reid 复用同一张表，API/匹配严格隔离）──────────────
def test_gallery_kind_lifecycle_and_isolation(test_client, auth_headers):
    """录入跨镜底库（kind=reid）后可列表过滤、按 kind 比对，且不与人脸底库串味。"""
    ids: list[int] = []
    try:
        # 1) 录入 cross（reid）与 face，默认 kind=face
        resp = test_client.post(
            f"{BASE}/enroll",
            json={"name": "B4 跨镜", "kind": "reid", "model_key": "osnet_x1_0", "embedding": E_A},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        reid_item = resp.json()["data"]
        ids.append(reid_item["id"])
        assert reid_item["kind"] == "reid"

        resp = _enroll(test_client, auth_headers, name="B4 人脸")
        face_item = resp.json()["data"]
        ids.append(face_item["id"])
        assert face_item["kind"] == "face"

        # 2) 列表按 kind 过滤
        resp = test_client.get(
            f"{BASE}/list", headers=auth_headers, params={"kind": "reid", "name": "B4"}
        )
        names = {i["name"] for i in resp.json()["data"]["items"]}
        assert names == {"B4 跨镜"}
        resp = test_client.get(
            f"{BASE}/list", headers=auth_headers, params={"kind": "face", "name": "B4"}
        )
        names = {i["name"] for i in resp.json()["data"]["items"]}
        assert names == {"B4 人脸"}

        # 3) 比对按 kind 隔离：reid 向量只命中 reid 底库
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "kind": "reid"}, headers=auth_headers
        )
        matched = resp.json()["data"]["items"]
        assert len(matched) == 1 and matched[0]["kind"] == "reid"
        assert matched[0]["name"] == "B4 跨镜"
        # 同一向量在 face 底库也有一条（B4 人脸用 E_A），face 查询只返回 face 条目
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "kind": "face"}, headers=auth_headers
        )
        matched = resp.json()["data"]["items"]
        assert all(m["kind"] == "face" for m in matched)
        assert {m["name"] for m in matched} == {"B4 人脸"}

        # 4) kind 非法 → 422
        resp = test_client.post(
            f"{BASE}/enroll",
            json={"name": "坏类型", "kind": "car", "embedding": E_A},
            headers=auth_headers,
        )
        assert resp.status_code == 422, resp.text
        resp = test_client.post(
            f"{BASE}/match", json={"embedding": E_A, "kind": "car"}, headers=auth_headers
        )
        assert resp.status_code == 422, resp.text

        # 5) 按 id 仅改名时 kind 不变
        resp = test_client.post(
            f"{BASE}/enroll",
            json={"id": reid_item["id"], "name": "B4 跨镜改名", "model_key": "osnet_x1_0"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["kind"] == "reid"
    finally:
        if ids:
            test_client.request("DELETE", f"{BASE}/delete", json=ids, headers=auth_headers)
        face_gallery_store.clear()
