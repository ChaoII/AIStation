"""算法出参 model_file_config 密钥脱敏测试（审计 #13）。

覆盖：
- 出参对密钥类字段（key/password/secret/token 等）脱敏，保留 format 等非敏感项；
- 更新时把回传的脱敏占位符还原为库中真实值（避免前端回写抹掉密钥）；
- 接口层：创建后详情不回显明文密钥，回传脱敏值更新后仍保留原值。
"""
import asyncio
import uuid

from app.api.v1.module_video.algorithm import service as algorithm_service
from app.api.v1.module_video.algorithm.schema import (
    REDACTED_VALUE,
    AlgorithmOutSchema,
    redact_model_file_config,
    restore_redacted_secrets,
)
from app.api.v1.module_video.algorithm.service import AlgorithmService

_SECRET_CFG = {
    "format": "onnx",
    "encrypt": {"enabled": True, "method": "aes-256", "key": "super-secret-key"},
    "password": "p@ssw0rd",
    "nested": [{"token": "tok-123", "note": "keep"}],
}


def test_redact_masks_secret_fields_only():
    out = redact_model_file_config(_SECRET_CFG)
    assert out["format"] == "onnx"
    assert out["encrypt"]["enabled"] is True
    assert out["encrypt"]["method"] == "aes-256"  # 非密钥字段保留
    assert out["encrypt"]["key"] == REDACTED_VALUE
    assert out["password"] == REDACTED_VALUE
    assert out["nested"][0]["token"] == REDACTED_VALUE
    assert out["nested"][0]["note"] == "keep"


def test_restore_redacted_secrets_recovers_masked_values():
    masked = redact_model_file_config(_SECRET_CFG)
    restored = restore_redacted_secrets(masked, _SECRET_CFG)
    assert restored["encrypt"]["key"] == "super-secret-key"
    assert restored["password"] == "p@ssw0rd"
    assert restored["nested"][0]["token"] == "tok-123"
    assert restored["format"] == "onnx"


def test_out_schema_serializes_redacted():
    class _Row:
        id = 1
        uuid = "u"
        status = "0"
        description = None
        created_time = None
        updated_time = None
        is_deleted = False
        deleted_time = None
        name = "alg"
        code = "A"
        version = "1.0.0"
        algorithm_type = "DET_ZONE"
        scene_type = None
        model_path = "m.onnx"
        plugin_path = None
        previous_model_path = None
        previous_version = None
        model_file_config = _SECRET_CFG
        runtime_config = None
        preset_params = None
        param_meta = None
        input_params = None
        output_schema = None

    dumped = AlgorithmOutSchema.model_validate(_Row()).model_dump()
    assert dumped["model_file_config"]["encrypt"]["key"] == REDACTED_VALUE
    assert dumped["model_file_config"]["format"] == "onnx"


def test_update_restores_masked_secret(monkeypatch):
    """更新时收到脱敏占位符 → 写库前还原为库中真实值。"""
    algorithm = _Simple(
        id=1,
        name="alg",
        code="A",
        version="1.0.0",
        algorithm_type="DET_ZONE",
        model_path="m.onnx",
        model_file_config={"format": "onnx", "encrypt": {"key": "REAL-KEY"}},
        previous_model_path=None,
        previous_version=None,
    )
    updates: list = []

    class _FakeCRUD:
        def __init__(self, auth=None):
            pass

        async def get_by_id_crud(self, id):
            return algorithm

        async def update(self, id, data):
            values = data if isinstance(data, dict) else data.model_dump(exclude_unset=True)
            updates.append(values)
            return algorithm

    monkeypatch.setattr(algorithm_service, "AlgorithmCRUD", _FakeCRUD)

    from app.api.v1.module_video.algorithm.schema import AlgorithmUpdateSchema

    asyncio.run(
        AlgorithmService.update_algorithm_service(
            id=1,
            data=AlgorithmUpdateSchema(
                algorithm_type="DET_ZONE",
                model_file_config={
                    "format": "onnx",
                    "encrypt": {"key": REDACTED_VALUE},
                },
            ),
            auth=None,
        )
    )
    assert updates[0]["model_file_config"]["encrypt"]["key"] == "REAL-KEY"


class _Simple:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_api_detail_masks_secret_and_update_preserves(test_client, auth_headers):
    suffix = uuid.uuid4().hex[:8]
    created = test_client.post(
        "/api/v1/video/algorithm/create",
        headers=auth_headers,
        json={
            "name": f"sec-alg-{suffix}",
            "code": f"SEC{suffix}",
            "algorithm_type": "DET_ZONE",
            "scene_type": "DET_ZONE",
            "model_path": "any",
            "model_file_config": {"format": "onnx", "encrypt": {"key": "api-secret"}},
        },
    )
    assert created.status_code == 200, created.text
    algorithm_id = created.json()["data"]["id"]

    detail = test_client.get(f"/api/v1/video/algorithm/detail/{algorithm_id}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    cfg = detail.json()["data"]["model_file_config"]
    assert cfg["encrypt"]["key"] == REDACTED_VALUE
    assert cfg["format"] == "onnx"

    # 回传脱敏值更新：不应报错，且详情仍为脱敏（真实值在库中保留，见单测）
    updated = test_client.put(
        f"/api/v1/video/algorithm/update/{algorithm_id}",
        headers=auth_headers,
        json={"algorithm_type": "DET_ZONE", "model_file_config": cfg},
    )
    assert updated.status_code == 200, updated.text
    detail2 = test_client.get(
        f"/api/v1/video/algorithm/detail/{algorithm_id}", headers=auth_headers
    )
    assert detail2.json()["data"]["model_file_config"]["encrypt"]["key"] == REDACTED_VALUE
