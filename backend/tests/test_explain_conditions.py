"""命中叶子解释测试：与 _match_conditions 判定必须逐例一致（对拍）。"""
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM, ALGO = 1, "DET_ZONE"


def _det(label="person", conf=0.9, cx=0.5, cy=0.5, w=0.2, h=0.2, track_id=None, attrs=None, text=None):
    d = {"label": label, "confidence": conf,
         "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h}}
    if track_id is not None:
        d["track_id"] = track_id
    if attrs:
        d["attributes"] = attrs
    if text is not None:
        d["text"] = text
    return d


ROI = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _explain(cond, dets, **kw):
    return explain_conditions(cond, dets, temporal=kw.pop("temporal", TemporalStore(prefer_redis=False)),
                              camera_id=CAM, alarm_type=ALGO, now=kw.pop("now", 1000), **kw)


def test_and_hits_paths():
    cond = {"op": "and", "children": [
        {"subject": "object_present", "label": "person"},
        {"subject": "count", "op": ">=", "value": 1},
    ]}
    ok, hits = _explain(cond, [_det()])
    assert ok is True
    assert [h["path"] for h in hits] == ["and/0", "and/1"]
    assert hits[0]["subject"] == "object_present"


def test_or_reports_only_matched_branch():
    cond = {"op": "or", "children": [
        {"subject": "object_present", "label": "car"},
        {"subject": "object_present", "label": "person"},
    ]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is True
    assert [h["path"] for h in hits] == ["or/1"]


def test_not_marks_negated():
    cond = {"op": "not", "children": [{"subject": "object_present", "label": "car"}]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is True
    assert hits and hits[0]["negated"] is True


def test_no_hits_when_unmatched():
    cond = {"op": "and", "children": [{"subject": "object_present", "label": "car"}]}
    ok, hits = _explain(cond, [_det(label="person")])
    assert ok is False and hits == []


def test_temporal_leaf_detail():
    store = TemporalStore(prefer_redis=False)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    cond = {"op": "and", "children": [{"subject": "dwell", "label": "person", "min_sec": 5}]}
    ok, hits = _explain(cond, [], temporal=store, now=1006)
    assert ok is True
    assert "dwell" in hits[0]["detail"]


def test_matches_match_conditions_everywhere():
    """对拍：任何条件下两者判定必须一致。"""
    store = TemporalStore(prefer_redis=False)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    cases = [
        ({"op": "and", "children": [{"subject": "object_present", "label": "person"}]}, [_det()]),
        ({"op": "or", "children": [{"subject": "count", "op": ">=", "value": 5}]}, [_det()]),
        ({"op": "not", "children": [{"subject": "object_present", "label": "car"}]}, [_det()]),
        ({"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}, [_det(attrs={"work_uniform": 0.2})]),
        ({"subject": "text_match", "regex": "京"}, [_det(text="京A12345")]),
        ({"subject": "dwell", "label": "person", "min_sec": 5}, []),
        ({"subject": "object_present", "label": "person", "region": ROI}, [_det()]),
        ({}, [_det()]),
    ]
    for cond, dets in cases:
        a = _match_conditions(cond, dets, temporal=store, camera_id=CAM, alarm_type=ALGO, now=1006, alarm_interval=0)
        b = explain_conditions(cond, dets, temporal=store, camera_id=CAM, alarm_type=ALGO, now=1006, alarm_interval=0)[0]
        assert a == b, cond
