"""x-anylabeling 导入健壮性单元/集成测试。"""
import io
import json
import os
import sqlite3
import zipfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.v1.module_annotation.dataset import x_anylabeling_importer as imp

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def _db():
    return sqlite3.connect(os.environ["DATABASE_NAME"] + ".db")


def test_safe_extract_rejects_zip_slip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    buf.seek(0)
    with zipfile.ZipFile(buf) as zf:
        with pytest.raises(ValueError):
            imp._safe_extract(zf, str(tmp_path / "out"))


def test_infer_task_type():
    assert imp._infer_task_type([{"shape_type": "rectangle"}]) == "detection"
    assert imp._infer_task_type([{"shape_type": "polygon"}]) == "segmentation"
    assert imp._infer_task_type([{"shape_type": "point"}]) == "keypoint"
    assert imp._infer_task_type([{"shape_type": "rotation"}]) == "rotated_detection"


def test_shape_rotation_to_rotated_box():
    shape = {
        "label": "t",
        "shape_type": "rotation",
        "points": [[10, 10], [30, 10], [30, 20], [10, 20]],
    }
    ann = imp._shape_to_annotation(shape, {"t": 0}, 100, 100)
    assert ann["type"] == "RotatedBox"
    assert 0 <= ann["cx"] <= 1 and 0 <= ann["cy"] <= 1
    assert ann["width"] > 0 and ann["height"] > 0


def _make_zip_bytes() -> bytes:
    """构造含两个同名 stem（不同目录）的 x-anylabeling 压缩包。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for d in ("d1", "d2"):
            zf.writestr(f"{d}/img.png", _FAKE_PNG)
            zf.writestr(
                f"{d}/img.json",
                json.dumps(
                    {
                        "imagePath": "img.png",
                        "imageHeight": 100,
                        "imageWidth": 200,
                        "shapes": [
                            {
                                "label": "cat",
                                "shape_type": "rectangle",
                                "points": [[10, 10], [50, 50]],
                            }
                        ],
                    }
                ),
            )
    return buf.getvalue()


def test_import_zip_no_collision_and_counts(
    test_client: TestClient, auth_headers: dict, monkeypatch
):
    """同名跨目录图片不互相覆盖，导入口径计数正确。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.ensure_bucket", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)

    name = f"xany-{uuid4().hex[:8]}"
    created = test_client.post(
        "/api/v1/annotation/dataset/create", json={"name": name}, headers=auth_headers
    )
    assert created.status_code == 200, created.text
    ds_id = created.json()["data"]["id"]

    resp = test_client.post(
        "/api/v1/annotation/dataset/import/x-anylabeling",
        params={"dataset_id": ds_id},
        files={"file": ("labels.zip", _make_zip_bytes(), "application/zip")},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()["data"]
    assert result["imported"] == 2
    assert result["total_images"] == 2
    assert result["total_annotations"] == 2
    assert result["class_mapping"] == {"cat": 0}

    con = _db()
    img_total = con.execute(
        "SELECT COUNT(*) FROM annotation_image WHERE dataset_id=?", (ds_id,)
    ).fetchone()[0]
    distinct_keys = con.execute(
        "SELECT COUNT(DISTINCT object_key) FROM annotation_image WHERE dataset_id=?", (ds_id,)
    ).fetchone()[0]
    rec_total = con.execute(
        "SELECT COUNT(*) FROM annotation_record WHERE task_id=?", (result["task_id"],)
    ).fetchone()[0]
    counts = con.execute(
        "SELECT image_count, annotated_count FROM annotation_dataset WHERE id=?", (ds_id,)
    ).fetchone()
    con.close()

    assert img_total == 2
    assert distinct_keys == 2
    assert rec_total == 2
    assert counts == (2, 2)
