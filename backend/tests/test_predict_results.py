"""预测结果重签与兼容性测试。"""
from app.plugin.module_train.service import sign_predict_results
from app.utils import s3_client as s3mod


def test_sign_converts_keys_preserves_urls(monkeypatch):
    """对象键转签名 URL，历史 http URL 原样保留。"""
    seen = []
    monkeypatch.setattr(
        "app.utils.s3_client.s3_client.presigned_url",
        lambda k, *a, **kw: seen.append(k) or f"https://signed/{k}",
    )
    row = {
        "result_images": ["train/predict/1/a.png", "https://old/url.png"],
        "result_zip_path": "train/predict/1/results.zip",
    }
    out = sign_predict_results(row)
    assert out["result_images"][0] == "https://signed/train/predict/1/a.png"
    assert out["result_images"][1] == "https://old/url.png"  # 历史 URL 保留
    assert out["result_zip_path"] == "https://signed/train/predict/1/results.zip"
    assert seen == ["train/predict/1/a.png", "train/predict/1/results.zip"]


def test_sign_handles_none():
    """空结果与 None 值不报错。"""
    assert sign_predict_results({"result_images": None, "result_zip_path": None}) == {
        "result_images": None,
        "result_zip_path": None,
    }


def test_sign_handles_none_predict():
    """predict 为 None 时原样返回。"""
    assert sign_predict_results(None) is None


def test_delete_prefix_lists_and_deletes(monkeypatch):
    """delete_prefix 删除前缀下全部对象并返回数量。"""
    deleted = []

    class FakeS3:
        def list_objects_v2(self, Bucket, Prefix):
            assert Prefix == "train/predict/7/"
            return {
                "Contents": [
                    {"Key": "train/predict/7/a.png"},
                    {"Key": "train/predict/7/results.zip"},
                ]
            }

        def delete_objects(self, Bucket, Delete):
            # delete_prefix 现走批量删除（分片并发）
            for obj in Delete["Objects"]:
                deleted.append((Bucket, obj["Key"]))

    fake = FakeS3()
    monkeypatch.setattr(s3mod.s3_client, "client", fake)
    n = s3mod.s3_client.delete_prefix("train/predict/7/")
    assert n == 2
    assert sorted(deleted) == sorted([
        (s3mod.s3_client._bucket(), "train/predict/7/a.png"),
        (s3mod.s3_client._bucket(), "train/predict/7/results.zip"),
    ])
