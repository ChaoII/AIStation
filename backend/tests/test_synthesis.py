"""数据合成：车牌合成接口端到端测试（真实 S3/DB）。"""


def _first_dataset_id(auth_headers, test_client):
    r = test_client.get(
        "/api/v1/annotation/dataset/list",
        params={"page_no": 1, "page_size": 1},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    items = r.json().get("data", {}).get("items", [])
    return items[0]["id"] if items else None


def test_synthesis_providers(auth_headers, test_client):
    r = test_client.get("/api/v1/synthesis/providers", headers=auth_headers)
    assert r.status_code == 200, r.text
    provs = r.json()["data"]
    keys = [p["key"] for p in provs]
    assert "license_plate" in keys
    lp = next(p for p in provs if p["key"] == "license_plate")
    assert lp["plate_types"], "应返回车牌类型选项"


def test_synthesis_generate_plate_upload(auth_headers, test_client):
    dataset_id = _first_dataset_id(auth_headers, test_client)
    body = {"count": 2, "upload": bool(dataset_id)}
    if dataset_id:
        body["dataset_id"] = dataset_id
    r = test_client.post(
        "/api/v1/synthesis/license-plate/generate", json=body, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert len(data["items"]) == 2
    assert data["job_id"] is not None
    for it in data["items"]:
        assert it["text"]
        assert it["bbox"]["x1"] < it["bbox"]["x2"]
        assert it["preview_base64"]
        if dataset_id:
            assert it["image_id"] is not None
            assert it["object_key"]


def test_synthesis_plate_types(auth_headers, test_client):
    """全部车牌类型都能生成合法 bbox。"""
    for plate_type in [
        "blue", "green", "green_large", "yellow", "yellow_double", "black",
        "embassy", "consulate", "hk_mo", "coach", "police", "motorcycle", "light_motorcycle",
    ]:
        r = test_client.post(
            "/api/v1/synthesis/license-plate/generate",
            json={"count": 1, "plate_type": plate_type, "upload": False},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        it = r.json()["data"]["items"][0]
        b = it["bbox"]
        assert it["plate_type"] == plate_type, f"{plate_type} 类型不匹配"
        assert 0 < b["x1"] < b["x2"] < 1, f"{plate_type} bbox x 非法"
        assert 0 < b["y1"] < b["y2"] < 1, f"{plate_type} bbox y 非法"


def test_synthesis_jobs_persist(auth_headers, test_client):
    r = test_client.get("/api/v1/synthesis/jobs", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert "items" in data and "total" in data
    # 生成至少一条记录后可查询到
    post = test_client.post(
        "/api/v1/synthesis/license-plate/generate",
        json={"count": 1, "plate_type": "yellow_double", "upload": False},
        headers=auth_headers,
    )
    job_id = post.json()["data"]["job_id"]
    r2 = test_client.get("/api/v1/synthesis/jobs?page_size=50", headers=auth_headers)
    ids = [j["id"] for j in r2.json()["data"]["items"]]
    assert job_id in ids
