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
