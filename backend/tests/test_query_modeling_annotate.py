"""S3-T4：对象/属性标注自动生成（解析 + 落库）。"""
import asyncio
from types import SimpleNamespace

from app.plugin.module_ai.query.modeling import parse_annotations


def test_parse_annotations_filters_unknown_object():
    valid = {"coal_batch": {"fields": [{"code": "FUELKINDNAME"}]}}
    text = ('[{"object_code":"coal_batch","object_name":"入厂煤批次","description":"入厂煤批次记录",'
            '"fields":[{"code":"FUELKINDNAME","name":"煤种","options":[]}]},'
            '{"object_code":"ghost","object_name":"幽灵","fields":[]}]')
    out = parse_annotations(text, valid)
    assert len(out) == 1 and out[0]["object_code"] == "coal_batch"


def test_parse_annotations_drops_unknown_fields():
    valid = {"coal_batch": {"fields": [{"code": "FUELKINDNAME"}]}}
    text = ('[{"object_code":"coal_batch","object_name":"入厂煤批次",'
            '"fields":[{"code":"FUELKINDNAME","name":"煤种"},{"code":"NOPE","name":"不存在"}]}]')
    out = parse_annotations(text, valid)
    codes = [f["code"] for f in out[0]["fields"]]
    assert codes == ["FUELKINDNAME"]


def test_generate_annotations_writes_name_and_description(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import modeling as M

        async def _fake_collect(datasource, max_objects):
            return [{"code": "coal_batch", "name": "coal_batch", "table": "T",
                     "fields": [{"code": "FUELKINDNAME", "name": "FUELKINDNAME"}]}]

        async def _fake_llm(prompt, **k):
            return ('[{"object_code":"coal_batch","object_name":"入厂煤批次",'
                    '"description":"入厂煤批次记录","fields":[{"code":"FUELKINDNAME","name":"煤种"}]}]')

        writes = {"obj": [], "prop": []}

        async def _fake_obj(code, name, description):
            writes["obj"].append((code, name, description))

        async def _fake_prop(object_code, code, name, options):
            writes["prop"].append((object_code, code, name))

        monkeypatch.setattr(M, "collect_objects", _fake_collect)
        monkeypatch.setattr(M, "model_llm", _fake_llm)
        monkeypatch.setattr(M, "_annotate_object", _fake_obj)
        monkeypatch.setattr(M, "_annotate_property", _fake_prop)

        auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
        out = await M.generate_annotations("ds:4", auth, max_objects=5)
        return out, writes

    out, writes = asyncio.run(_go())
    assert out["saved"] == 1
    assert writes["obj"] and writes["obj"][0][1] == "入厂煤批次"
    assert writes["prop"] and writes["prop"][0][2] == "煤种"
