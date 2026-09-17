import base64
import logging
import math
from datetime import datetime
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.api.v1.module_video.inference.gating import rule_active_now
from app.api.v1.module_video.inference.temporal import (
    ABSENT_ALL,
    region_fingerprint,
    temporal_store,
    to_epoch,
)
from app.config.setting import settings
from app.utils.re_util import safe_regex_search

log = logging.getLogger(__name__)

# 时序叶子：需依赖跨事件的状态存储（temporal.py）
TEMPORAL_SUBJECTS = (
    "dwell",
    "count_window",
    "absence",
    "line_cross",
    "group_count",
    "group_coverage",
    "static",
    "track",
)

# static 叶子缺省最大位移阈值（归一化坐标下的欧氏距离）
_DEFAULT_MAX_MOVE = 0.02

# ── 关键点几何（keypoint_geometry 叶子）──────────────────────────────────────
# 事件契约：Agent 对姿态模型输出 objects[].keypoints = [[x, y, score], ...]（归一化 0~1）。
# 索引按 Ultralytics/COCO-17 人体姿态顺序（本叶子对「多出的点」容忍，只取所需索引）：
#   0 鼻 ｜ 1/2 左/右眼 ｜ 3/4 左/右耳 ｜ 5/6 左/右肩 ｜ 7/8 左/右肘 ｜ 9/10 左/右腕
#   11/12 左/右髋 ｜ 13/14 左/右膝 ｜ 15/16 左/右踝
_KP_NOSE = 0
_KP_EYES = (1, 2)
_KP_EARS = (3, 4)
_KP_SHOULDERS = (5, 6)
_KP_WRISTS = (9, 10)
_KP_HIPS = (11, 12)
# 关键点最低可见分数：低于该值视为未检出（避免 (0,0) 伪点污染几何）
_KP_MIN_SCORE = 0.3
# fall：躯干与竖直方向夹角缺省阈值（度；0=直立，90=水平）
_DEFAULT_FALL_ANGLE = 60.0
# climb：未提供 line 时的缺省高度阈值（归一化 y，越小越高）
_DEFAULT_CLIMB_Y = 0.5
# smoke_phone：腕-头归一化距离缺省阈值
_DEFAULT_HAND_HEAD_DIST = 0.15
# face_landmark：缺省最少有效关键点数（分数 >= _KP_MIN_SCORE 视为有效）
_DEFAULT_FACE_LANDMARK_MIN_KP = 5
# 需要时序轨迹状态的 keypoint 规则（smoke_phone 的 min_sec 持续性抑制）
_KEYPOINT_STATEFUL_RULES = frozenset({"smoke_phone"})


def pick_alarm_rule(rules: list, algorithm_type: str):
    """从多条候选规则中选一条：优先 alarm_type 精确匹配，否则第一条；空返回 None。"""
    if not rules:
        return None
    for r in rules:
        if getattr(r, "alarm_type", None) == algorithm_type:
            return r
    return rules[0]


def _as_float(raw) -> float | None:
    """尽力转换为 float；None/缺失/非数值返回 None。"""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _bbox_center(d: dict) -> tuple[float, float] | None:
    """取检测框中心点 (x + w/2, y + h/2)；bbox 缺失/非法返回 None。"""
    if not isinstance(d, dict):
        return None
    bbox = d.get("bbox")
    if not isinstance(bbox, dict):
        return None
    x = _as_float(bbox.get("x"))
    y = _as_float(bbox.get("y"))
    w = _as_float(bbox.get("width"))
    h = _as_float(bbox.get("height"))
    if None in (x, y, w, h):
        return None
    return (x + w / 2.0, y + h / 2.0)


def _region_of(leaf: dict) -> list[tuple[float, float]] | None:
    """解析归一化多边形区域。

    缺失/None 返回 None（表示不限定区域）；非法（非多边形 / 坐标非数值）返回空列表，
    由调用方判为不命中。
    """
    if not isinstance(leaf, dict):
        return []
    region = leaf.get("region")
    if region is None:
        return None
    if not isinstance(region, (list, tuple)) or len(region) < 3:
        return []
    pts: list[tuple[float, float]] = []
    for p in region:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return []
        x = _as_float(p[0])
        y = _as_float(p[1])
        if x is None or y is None:
            return []
        pts.append((x, y))
    return pts


def _point_on_segment(px, py, x1, y1, x2, y2, eps: float = 1e-9) -> bool:
    """判断点是否落在线段上（含端点），用于边界确定性判定。"""
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > eps:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= eps


def _point_in_polygon(x: float, y: float, pts: list[tuple[float, float]]) -> bool:
    """射线法判断点是否在多边形内；落在边界（含端点）视为命中。"""
    if not pts or len(pts) < 3:
        return False
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if _point_on_segment(x, y, xi, yi, xj, yj):
            return True
        if (yi > y) != (yj > y):
            x_cross = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_cross:
                inside = not inside
        j = i
    return inside


def _orient(a, b, c) -> float:
    """叉积 (B-A)×(C-A)：>0 表示 C 在有向线段 A→B 左侧。"""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(p1, p2, p3, p4, eps: float = 1e-12) -> bool:
    """两线段是否真正相交（严格跨立；共线/仅端点触碰视为不相交）。"""
    d1 = _orient(p3, p4, p1)
    d2 = _orient(p3, p4, p2)
    d3 = _orient(p1, p2, p3)
    d4 = _orient(p1, p2, p4)
    return (
        ((d1 > eps and d2 < -eps) or (d1 < -eps and d2 > eps))
        and ((d3 > eps and d4 < -eps) or (d3 < -eps and d4 > eps))
    )


def _parse_line(leaf: dict) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """解析绊线折线：取首尾两点构成有向线段；非法/退化返回 None。"""
    line = leaf.get("line")
    if not isinstance(line, (list, tuple)) or len(line) < 2:
        return None

    def _pt(p):
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        x = _as_float(p[0])
        y = _as_float(p[1])
        if x is None or y is None:
            return None
        return (x, y)

    a = _pt(line[0])
    b = _pt(line[-1])
    if a is None or b is None or a == b:
        return None
    return a, b


def _point_pass_region(pt, leaf: dict) -> bool:
    """点是否落在叶子 region 内；未限定 region 返回 True，非法区域返回 False。"""
    if not isinstance(leaf, dict) or leaf.get("region") is None:
        return True
    pts = _region_of(leaf)
    if not pts:
        return False
    return _point_in_polygon(pt[0], pt[1], pts)


def _matches_label(d: dict, leaf: dict) -> bool:
    """label/labels 过滤：labels 非空优先；都缺省表示任意目标。"""
    if not isinstance(d, dict) or not isinstance(leaf, dict):
        return False
    labels = leaf.get("labels")
    if isinstance(labels, (list, tuple)) and labels:
        return d.get("label") in labels
    label = leaf.get("label")
    if label is None:
        return True
    return d.get("label") == label


def _in_region(d: dict, leaf: dict) -> bool:
    """检测框中心是否落在区域多边形内；未限定区域返回 True，非法区域返回 False。"""
    if not isinstance(leaf, dict) or leaf.get("region") is None:
        return True
    pts = _region_of(leaf)
    if not pts:  # 非法区域
        return False
    center = _bbox_center(d)
    if center is None:
        return False
    return _point_in_polygon(center[0], center[1], pts)


def _leaf_needs_state(node: dict) -> bool:
    """叶子是否需要跨事件时序状态（决定是否写入观测）。

    - TEMPORAL_SUBJECTS 中的时序叶子恒为真；
    - keypoint_geometry 中带 ``min_sec`` 的持续性规则（smoke_phone）亦需轨迹状态。
    """
    subject = node.get("subject")
    if subject in TEMPORAL_SUBJECTS:
        return True
    if subject != "keypoint_geometry":
        return False
    rule = node.get("rule")
    if not isinstance(rule, str) or rule.strip().lower() not in _KEYPOINT_STATEFUL_RULES:
        return False
    return node.get("min_sec") is not None


def _iter_temporal_leaves(node) -> list[dict]:
    """遍历条件树，收集所有需要时序状态的叶子；脏节点安全跳过。"""
    found: list[dict] = []
    if not isinstance(node, dict):
        return found
    if node.get("op") in ("and", "or", "not"):
        kids = node.get("children") or []
        if isinstance(kids, (list, tuple)):
            for k in kids:
                found.extend(_iter_temporal_leaves(k))
        return found
    if _leaf_needs_state(node):
        found.append(node)
    return found


def _has_temporal_leaf(node) -> bool:
    """条件树是否含时序叶子（决定回调是否需要写入观测状态）。"""
    return bool(_iter_temporal_leaves(node))


def _leaf_scope(leaf: dict) -> tuple[str | None, bool]:
    """时序叶子的状态桶 scope。

    无 region → ("all", True)；region 合法 → (指纹, True)；非法 region → (None, False)。
    """
    if leaf.get("region") is None:
        return "all", True
    pts = _region_of(leaf)
    if not pts:
        return None, False
    fp = region_fingerprint(pts)
    if fp is None:
        return None, False
    return fp, True


def _leaf_labels(leaf: dict) -> list[str]:
    """时序叶子的标签过滤：labels 列表优先，其次单个 label；都缺省表示任意标签。"""
    labels = leaf.get("labels")
    if isinstance(labels, (list, tuple)):
        return [x for x in labels if isinstance(x, str)]
    label = leaf.get("label")
    if isinstance(label, str):
        return [label]
    return []


def _query_temporal(temporal, camera_id, alarm_type: str, leaf: dict, scope: str):
    """读取时序状态：{track_key: (first_seen, last_seen)}；无标签限制时聚合全部标签。"""
    labels = _leaf_labels(leaf)
    if not labels:
        return temporal.query(camera_id, alarm_type, None, scope)
    merged: dict = {}
    for lab in labels:
        merged.update(temporal.query(camera_id, alarm_type, lab, scope))
    return merged


def _query_positions(temporal, camera_id, alarm_type: str, leaf: dict, scope: str):
    """读取轨迹位置状态；无标签限制时聚合全部标签（与 _query_temporal 同构）。"""
    labels = _leaf_labels(leaf)
    if not labels:
        return temporal.query_positions(camera_id, alarm_type, None, scope)
    merged: dict = {}
    for lab in labels:
        merged.update(temporal.query_positions(camera_id, alarm_type, lab, scope))
    return merged


def _query_moves(temporal, camera_id, alarm_type: str, leaf: dict, scope: str):
    """读取轨迹最大位移状态；无标签限制时聚合全部标签（与 _query_temporal 同构）。"""
    labels = _leaf_labels(leaf)
    if not labels:
        return temporal.query_moves(camera_id, alarm_type, None, scope)
    merged: dict = {}
    for lab in labels:
        merged.update(temporal.query_moves(camera_id, alarm_type, lab, scope))
    return merged


def _track_id_of(field) -> int | None:
    """从轨迹键 ``t:{id}`` 解析有效 track_id（>=0）；非轨迹键/非法/负数返回 None。

    事件按 ``e:{ts}`` 成键（无 track_id 时按事件计数），不具有轨迹身份，故不视为轨迹。
    """
    if not isinstance(field, str) or not field.startswith("t:"):
        return None
    num = _as_float(field[2:])
    if num is None or num < 0:
        return None
    return int(num)


def _active_tracks(entries: dict, now: float, grace: float, min_sec: float = 0.0):
    """活跃轨迹列表 ``[(field, elapsed, idle)]``。

    仅保留携带有效 track_id（>=0）的轨迹；要求存在时长 >= min_sec 且距最近出现 <= grace。
    """
    out: list[tuple[str, float, float]] = []
    for field, (first, last) in entries.items():
        if _track_id_of(field) is None:
            continue
        elapsed = now - first
        if elapsed < min_sec:
            continue
        idle = now - last
        if idle > grace:
            continue
        out.append((field, elapsed, idle))
    return out


def _static_tracks(
    entries: dict, moves: dict, now: float, grace: float, min_sec: float, max_move: float
):
    """静止轨迹列表 ``[(field, elapsed, moved)]``：活跃且相对首帧最大位移 <= max_move。"""
    out: list[tuple[str, float, float]] = []
    for field, elapsed, _idle in _active_tracks(entries, now, grace, min_sec):
        moved = moves.get(field, 0.0)
        if moved <= max_move:
            out.append((field, elapsed, moved))
    return out


def _compare_count(value: float, op: str, target: float) -> bool:
    """计数比较：支持 >= / > / <= / < / ==。"""
    if op == ">=":
        return value >= target
    if op == ">":
        return value > target
    if op == "<=":
        return value <= target
    if op == "<":
        return value < target
    return value == target


# ── 关键点几何工具 ──────────────────────────────────────────────────────────
def _keypoints_of(d) -> list:
    """取检测的关键点列表；缺失/非列表返回空列表（fail-closed）。"""
    if not isinstance(d, dict):
        return []
    kps = d.get("keypoints")
    if not isinstance(kps, (list, tuple)):
        return []
    return list(kps)


def _kp_point(kps, idx, min_score: float = _KP_MIN_SCORE):
    """取第 idx 个关键点 (x, y)；越界/非数值/分数不足返回 None。

    容忍 2 元素点（缺 score 视为可见）；若给出 score 则必须为数值且 >= min_score。
    """
    if not isinstance(idx, int) or idx < 0 or idx >= len(kps):
        return None
    kp = kps[idx]
    if not isinstance(kp, (list, tuple)) or len(kp) < 2:
        return None
    x = _as_float(kp[0])
    y = _as_float(kp[1])
    if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
        return None
    if len(kp) >= 3:
        score = _as_float(kp[2])
        if score is None or score < min_score:
            return None
    return (x, y)


def _kp_mid(kps, idxs, min_score: float = _KP_MIN_SCORE):
    """取若干关键点的均值点；全部缺失返回 None。"""
    pts = [p for p in (_kp_point(kps, i, min_score) for i in idxs) if p is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _kp_head_point(kps):
    """头部参照点：鼻 → 双耳中点 → 双眼中点；均缺失返回 None。"""
    return (
        _kp_point(kps, _KP_NOSE)
        or _kp_mid(kps, _KP_EARS)
        or _kp_mid(kps, _KP_EYES)
    )


def _kp_torso(kps):
    """躯干两端点 (肩中点, 髋中点)；任一缺失返回 None。"""
    sh = _kp_mid(kps, _KP_SHOULDERS)
    hip = _kp_mid(kps, _KP_HIPS)
    if sh is None or hip is None:
        return None
    return sh, hip


def _kp_torso_angle(sh, hip):
    """躯干相对竖直方向夹角（度）：0=直立，90=水平；退化（零长度）返回 None。"""
    dx = sh[0] - hip[0]
    dy = sh[1] - hip[1]
    if math.hypot(dx, dy) <= 1e-9:
        return None
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def _is_above_line(l0, l1, pt) -> bool:
    """点是否位于线段所在直线的「上方」（图像坐标 y 向下，越小越高）。

    线段竖直（首尾 x 相同）时上下无定义；点恰好落线上亦不判为上方（均 fail-closed）。
    """
    dx = l1[0] - l0[0]
    if abs(dx) <= 1e-9:
        return False
    orient = _orient(l0, l1, pt)
    if orient == 0:
        return False
    # 直线上方 = 法向 y 分量为负的一侧：dx>0 时左侧为上，dx<0 时右侧为上
    return orient < 0 if dx > 0 else orient > 0


def _climb_body_center(kps):
    """攀爬判定用躯干中心（肩中点与髋中点的均值）；两者均缺失返回 None。"""
    pts = [p for p in (_kp_mid(kps, _KP_SHOULDERS), _kp_mid(kps, _KP_HIPS)) if p is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def _climb_threshold(leaf) -> tuple[float, bool]:
    """高度阈值解析：缺省 0.5；给出但非法（非数值/越界 0~1）返回 (0.0, False)。"""
    raw = leaf.get("value")
    if raw is None:
        return _DEFAULT_CLIMB_Y, True
    val = _as_float(raw)
    if val is None or val < 0 or val > 1:
        return 0.0, False
    return val, True


def _hand_head_distance(kps):
    """腕（9/10）到头参照的最小归一化距离；头或腕缺失返回 None。"""
    head = _kp_head_point(kps)
    if head is None:
        return None
    hands = [p for p in (_kp_point(kps, i) for i in _KP_WRISTS) if p is not None]
    if not hands:
        return None
    return min(math.hypot(h[0] - head[0], h[1] - head[1]) for h in hands)


def _kp_compare(value: float, op, target: float, default_op: str):
    """按 op（缺省 default_op）比较；op 非法返回 None（fail-closed）。"""
    if op is None:
        op = default_op
    if op not in (">=", ">", "<=", "<", "=="):
        return None
    return _compare_count(value, op, target)


def _smoke_phone_threshold(leaf) -> tuple[float, bool]:
    """手-头距离阈值解析：缺省 0.15；给出但非法（非数值/负数）返回 (0.0, False)。"""
    raw = leaf.get("value")
    if raw is None:
        return _DEFAULT_HAND_HEAD_DIST, True
    val = _as_float(raw)
    if val is None or val < 0:
        return 0.0, False
    return val, True


def _fall_hit(kps, leaf) -> bool:
    """跌倒：躯干与竖直方向夹角按 op（缺省 >=）与阈值（value，缺省 60°）比较。"""
    torso = _kp_torso(kps)
    if torso is None:
        return False
    angle = _kp_torso_angle(*torso)
    if angle is None:
        return False
    raw = leaf.get("value")
    if raw is None:
        threshold = _DEFAULT_FALL_ANGLE
    else:
        threshold = _as_float(raw)
        if threshold is None or threshold < 0 or threshold > 180:
            return False
    return _kp_compare(angle, leaf.get("op"), threshold, ">=") is True


def _climb_hit(kps, leaf) -> bool:
    """攀爬：有 line 时判躯干中心是否位于绊线上方；否则按高度阈值比较（缺省 <=）。"""
    center = _climb_body_center(kps)
    if center is None:
        return False
    if leaf.get("line") is not None:
        line = _parse_line(leaf)
        if line is None:
            return False
        return _is_above_line(line[0], line[1], center)
    threshold, ok = _climb_threshold(leaf)
    if not ok:
        return False
    return _kp_compare(center[1], leaf.get("op"), threshold, "<=") is True


def _smoke_phone_sustained(
    leaf, *, temporal, camera_id, alarm_type, now: float | None, alarm_interval
) -> bool:
    """min_sec 持续性：存在已持续 >= min_sec 且未过期（idle <= grace）的活跃轨迹。

    未配置 min_sec → True（单帧判定）；配置但非法/缺时序状态 → False（fail-closed）。
    """
    raw_min = leaf.get("min_sec")
    if raw_min is None:
        return True
    min_sec = _as_float(raw_min)
    if min_sec is None or min_sec < 0:
        return False
    if temporal is None or camera_id is None or now is None:
        return False
    scope, ok = _leaf_scope(leaf)
    if not ok:
        return False
    entries = _query_temporal(temporal, camera_id, alarm_type, leaf, scope)
    grace = max(min_sec, _as_float(alarm_interval) or 0.0)
    for _field, (first, last) in entries.items():
        if (now - first) >= min_sec and (now - last) <= grace:
            return True
    return False


def _smoke_phone_hit(
    kps, leaf, *, temporal, camera_id, alarm_type, now: float | None, alarm_interval
) -> bool:
    """抽烟/打电话：腕-头距离 <= 阈值（缺省 0.15），可选要求轨迹持续 >= min_sec。"""
    dist = _hand_head_distance(kps)
    if dist is None:
        return False
    threshold, ok = _smoke_phone_threshold(leaf)
    if not ok:
        return False
    if _kp_compare(dist, leaf.get("op"), threshold, "<=") is not True:
        return False
    return _smoke_phone_sustained(
        leaf,
        temporal=temporal,
        camera_id=camera_id,
        alarm_type=alarm_type,
        now=now,
        alarm_interval=alarm_interval,
    )


def _kp_visible_count(kps, min_score: float = _KP_MIN_SCORE) -> int:
    """统计有效关键点数：2 元素点视为可见；给出 score 时必须为数值且 >= min_score。

    与 ``_kp_point`` 同口径（坐标非数值/非有限值一律不计），保证「计数」与「取点」一致。
    """
    count = 0
    for kp in kps:
        if not isinstance(kp, (list, tuple)) or len(kp) < 2:
            continue
        x = _as_float(kp[0])
        y = _as_float(kp[1])
        if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
            continue
        if len(kp) >= 3:
            score = _as_float(kp[2])
            if score is None or score < min_score:
                continue
        count += 1
    return count


def _face_landmark_threshold(leaf) -> tuple[float, bool]:
    """人脸关键点最少有效点数解析：缺省 5；给出但非法（非数值/负数）返回 (0, False)。"""
    raw = leaf.get("value")
    if raw is None:
        return _DEFAULT_FACE_LANDMARK_MIN_KP, True
    val = _as_float(raw)
    if val is None or val < 0:
        return 0.0, False
    return val, True


def _face_landmark_hit(kps, leaf) -> bool:
    """人脸关键点（face_landmark）：有效点数（分数 >= 0.3）按 op 与阈值比较。

    契约：``{"subject":"keypoint_geometry","rule":"face_landmark","op"?,"value"?}``；
    value 语义为「最少有效关键点数」（缺省 5，op 缺省 >=）；阈值非法/op 非法 → 不命中。
    """
    min_count, ok = _face_landmark_threshold(leaf)
    if not ok:
        return False
    count = _kp_visible_count(kps)
    return _kp_compare(count, leaf.get("op"), min_count, ">=") is True


def _keypoint_geometry_hit(
    leaf: dict,
    detections: list,
    *,
    temporal=None,
    camera_id=None,
    alarm_type=None,
    now: float | None = None,
    alarm_interval=0,
) -> bool:
    """评估 keypoint_geometry 叶子（姿态/人脸几何）；异常/缺失输入一律不命中，绝不抛异常。

    契约：``{"subject":"keypoint_geometry","rule":"fall|climb|smoke_phone|face_landmark|gesture",
    "region"?,"min_sec"?,"line"?,"op"?,"value"?}``；区域过滤按检测框中心（与既有叶子一致）。

    规则语义（人体用 COCO-17 索引；关键点分数 < 0.3 视为未检出）：
    - fall：躯干（肩中点↔髋中点）与竖直方向夹角 >= 阈值（value 缺省 60°，op 缺省 >=）；
    - climb：躯干中心位于 line 上方（图像 y 向下，越小越高）；无 line 时与高度阈值
      value（缺省 0.5，op 缺省 <=）比较；line 竖直/非法 → 不命中；
    - smoke_phone：腕（9/10）到头参照（鼻→双耳中点→双眼中点）的最小归一化距离
      <= 阈值（value 缺省 0.15，op 缺省 <=）；配置 min_sec 时还要求存在已持续
      >= min_sec 的活跃轨迹（复用时序轨迹状态做持续性抑制）；
    - face_landmark：有效关键点数（2 元素点视为可见；分数 < 0.3 不计）与 value
      （缺省 5，op 缺省 >=）比较——「至少 N 个有效关键点」= 检出人脸关键点；
    - gesture：已声明但未实现（缺 21 点手部关键点模型），恒不命中（见 leaves.py 说明）。
    """
    if not isinstance(leaf, dict) or not isinstance(detections, (list, tuple)):
        return False
    rule = leaf.get("rule")
    if not isinstance(rule, str):
        return False
    rule = rule.strip().lower()
    if rule == "gesture":
        # 诚实的桩实现：不支持即不命中，绝不用几何近似冒充手势识别
        return False
    if rule not in ("fall", "climb", "smoke_phone", "face_landmark"):
        return False
    try:
        for d in detections:
            if not isinstance(d, dict):
                continue
            if not _in_region(d, leaf):
                continue
            kps = _keypoints_of(d)
            if not kps:
                continue
            if rule == "fall" and _fall_hit(kps, leaf):
                return True
            if rule == "climb" and _climb_hit(kps, leaf):
                return True
            if rule == "face_landmark" and _face_landmark_hit(kps, leaf):
                return True
            if rule == "smoke_phone" and _smoke_phone_hit(
                kps,
                leaf,
                temporal=temporal,
                camera_id=camera_id,
                alarm_type=alarm_type,
                now=now,
                alarm_interval=alarm_interval,
            ):
                return True
    except Exception:
        # 脏规则/脏关键点绝不向上抛异常（与 _match_conditions 同约定）
        return False
    return False


# ── 深度距离（distance 叶子）────────────────────────────────────────────────
# 事件契约：Agent depth 模型输出 objects[].depth = 深度（米，float）。
# 比较算子与 attribute 叶子一致（lt/gt/le/ge/eq）；depth 缺失/非法一律 fail-closed。
_DISTANCE_OPS = ("lt", "gt", "le", "ge", "eq")


def _distance_hit(leaf: dict, detections: list) -> bool:
    """评估 distance 叶子：任一 detection 的数值 depth 满足比较即命中。

    契约：``{"subject":"distance","op":"lt|gt|le|ge|eq","value":<米>,"label"?,"region"?}``。
    - depth 缺失/非数值/非有限值（NaN/Inf）→ 跳过该检测（fail-closed）；
    - value 非数值、op 非合法算子 → 整体不命中；
    - label/region 过滤与既有叶子同口径（region 按检测框中心）。
    """
    if not isinstance(leaf, dict) or not isinstance(detections, (list, tuple)):
        return False
    op = leaf.get("op")
    if op not in _DISTANCE_OPS:
        return False
    value = _as_float(leaf.get("value"))
    if value is None:
        return False
    for d in detections:
        if not isinstance(d, dict):
            continue
        if not _matches_label(d, leaf):
            continue
        if not _in_region(d, leaf):
            continue
        depth = _as_float(d.get("depth"))
        if depth is None or not math.isfinite(depth):
            continue
        if op == "lt" and depth < value:
            return True
        if op == "gt" and depth > value:
            return True
        if op == "le" and depth <= value:
            return True
        if op == "ge" and depth >= value:
            return True
        if op == "eq" and depth == value:
            return True
    return False


# ── 语义区域占比（region_ratio 叶子）────────────────────────────────────────
# 事件契约：sem 模型输出「整帧对象 + attributes={类别: 面积占比}」；占比由边缘在任务 ROI
# 内算好，云端只做数值比较（不重算多边形，故本叶子不登记 region）。
_RATIO_OPS = ("lt", "gt", "le", "ge", "eq")


def _ratio_categories(leaf: dict) -> list[str] | None:
    """解析参与比较的类别名：labels 列表优先，其次单个 label；都缺省返回 None（全部类别）。"""
    labels = leaf.get("labels")
    if isinstance(labels, (list, tuple)) and labels:
        return [str(x) for x in labels]
    label = leaf.get("label")
    if isinstance(label, str) and label:
        return [label]
    return None


def _ratio_compare(ratio: float, op: str, target: float) -> bool:
    """占比比较：支持 lt/gt/le/ge/eq（与 attribute/distance 叶子同算子名）。"""
    if op == "lt":
        return ratio < target
    if op == "gt":
        return ratio > target
    if op == "le":
        return ratio <= target
    if op == "ge":
        return ratio >= target
    return ratio == target


def _region_ratio_hit(leaf: dict, detections: list) -> bool:
    """评估 region_ratio 叶子：任一对象的某个类别占比满足比较即命中。

    契约：``{"subject":"region_ratio","op":"lt|gt|le|ge|eq","value":<占比0~1>,
    "label"?,"labels"?}``。
    - 类别来源：labels 列表 > label > attributes 全部键（任一满足即命中）；
    - 占比缺失/非数值/非有限值 → 跳过该项（fail-closed）；value 非数值、op 非法 → 不命中。
    """
    if not isinstance(leaf, dict) or not isinstance(detections, (list, tuple)):
        return False
    op = leaf.get("op")
    if op not in _RATIO_OPS:
        return False
    value = _as_float(leaf.get("value"))
    if value is None:
        return False
    categories = _ratio_categories(leaf)
    for d in detections:
        if not isinstance(d, dict):
            continue
        attrs = d.get("attributes")
        if not isinstance(attrs, dict):
            continue
        if categories is None:
            raw_items = list(attrs.values())
        else:
            raw_items = [attrs.get(k) for k in categories]
        for raw in raw_items:
            ratio = _as_float(raw)
            if ratio is None or not math.isfinite(ratio):
                continue
            if _ratio_compare(ratio, op, value):
                return True
    return False


# ── 码值匹配（code_match 叶子）──────────────────────────────────────────────
# 事件契约：barcode 解码结果复用 objects[].text 承载（与 OCR 同字段）。
_CODE_MATCH_OPS = ("in", "regex")


def _texts_of(detections: list) -> list[str]:
    """收集检测上的非空文本（去首尾空白后保序）；非字符串一律跳过。"""
    out: list[str] = []
    for d in detections:
        if not isinstance(d, dict):
            continue
        text = d.get("text")
        if isinstance(text, str) and text.strip():
            out.append(text.strip())
    return out


def _code_match_hit(leaf: dict, detections: list) -> bool:
    """评估 code_match 叶子：解码文本与码值名单/正则匹配。

    契约：``{"subject":"code_match","op":"in|regex","code_list"?:[...],"regex"?:str}``。
    - op=in（缺省）：与 code_list 逐项精确比对；名单为空/缺失 → 识别到任意非空码值即命中；
    - op=regex：任一文本命中正则即命中（安全执行，非法/危险模式不命中）；
    - 无有效文本 / op 非法 / 名单类型非法 → 不命中（fail-closed）。
    """
    if not isinstance(leaf, dict) or not isinstance(detections, (list, tuple)):
        return False
    op = leaf.get("op")
    if op is None:
        op = "in"
    if not isinstance(op, str) or op.strip().lower() not in _CODE_MATCH_OPS:
        return False
    op = op.strip().lower()
    texts = _texts_of(detections)
    if not texts:
        return False
    if op == "regex":
        pattern = leaf.get("regex")
        if not isinstance(pattern, str) or not pattern:
            return False
        return any(safe_regex_search(pattern, t) for t in texts)
    codes = leaf.get("code_list")
    if codes is None or (isinstance(codes, (list, tuple)) and not codes):
        # 未配置名单：识别到任意非空码值即命中（默认「检测到条码」语义）
        return True
    if not isinstance(codes, (list, tuple)):
        return False
    wanted = {
        str(c).strip()
        for c in codes
        if isinstance(c, (str, int, float))
        and not isinstance(c, bool)
        and str(c).strip()
    }
    if not wanted:
        return True
    return any(t in wanted for t in texts)


def _eval_temporal(
    subject: str,
    leaf: dict,
    temporal,
    camera_id,
    alarm_type,
    now: float | None,
    alarm_interval,
    group_camera_ids: list[int] | None = None,
) -> bool:
    """评估时序叶子；缺状态/时间或非法字段一律不命中，绝不抛异常。

    - dwell：某轨迹 first_seen 起持续 >= min_sec，且最近出现未超 grace
      （grace = max(min_sec, alarm_interval)）；可选 track_id 限定具体轨迹。
    - count_window：窗口 window_sec 内最近出现的去重目标数与 value 按 op 比较。
    - absence：距最近一次出现 >= gap_sec；无历史视为未过期 → 不命中。
    - static：某真实轨迹（有效 track_id）存在 >= min_sec、仍活跃，且相对首帧最大位移
      <= max_move（缺省 0.02）→ 命中；可选 track_id 限定具体轨迹。
    - track：存在至少一条活跃的真实轨迹（可选要求时长 >= min_sec）→ 命中。
    - group_count：跨相机窗口内去重目标数（键含 camera_id，跨相机同 track 不合并）。
    - group_coverage：窗口内有目标的相机数 / 组内相机总数（含离线，分母为组规模）。
      组聚合叶子无组上下文（group_camera_ids 为空）→ fail-closed 不命中。
    """
    if temporal is None or camera_id is None or now is None:
        return False
    scope, ok = _leaf_scope(leaf)
    if not ok:
        return False
    entries = _query_temporal(temporal, camera_id, alarm_type, leaf, scope)

    if subject in ("group_count", "group_coverage"):
        # 跨相机聚合：纯只读，无组上下文（group_camera_ids 空）→ fail-closed
        if not group_camera_ids:
            return False
        window = _as_float(leaf.get("window_sec"))
        if window is None or window < 0:
            return False
        op = leaf.get("op")
        if op not in (">=", ">", "<=", "<", "=="):
            return False
        target = _as_float(leaf.get("value"))
        if target is None:
            return False
        labels = _leaf_labels(leaf)
        merged: dict = {}
        for lab in labels or [None]:
            merged.update(
                temporal.query_multi(group_camera_ids, alarm_type, lab, scope)
            )
        start = now - window
        if subject == "group_count":
            count = sum(1 for _k, (_first, last) in merged.items() if last >= start)
            return _compare_count(count, op, target)
        active = {cam for (cam, _field), (_first, last) in merged.items() if last >= start}
        total = len(group_camera_ids)
        ratio = (len(active) / total) if total else 0.0
        return _compare_count(ratio, op, target)

    if subject == "dwell":
        min_sec = _as_float(leaf.get("min_sec"))
        if min_sec is None or min_sec < 0:
            return False
        want_field = None
        if leaf.get("track_id") is not None:
            num = _as_float(leaf.get("track_id"))
            if num is None:
                return False
            want_field = f"t:{int(num)}"
        grace = max(min_sec, _as_float(alarm_interval) or 0.0)
        for field, (first, last) in entries.items():
            if want_field is not None and field != want_field:
                continue
            if (now - first) >= min_sec and (now - last) <= grace:
                return True
        return False

    if subject == "count_window":
        window = _as_float(leaf.get("window_sec"))
        if window is None or window < 0:
            return False
        op = leaf.get("op")
        if op not in (">=", ">", "<=", "<", "=="):
            return False
        target = _as_float(leaf.get("value"))
        if target is None:
            return False
        start = now - window
        count = sum(1 for _first, last in entries.values() if last >= start)
        return _compare_count(count, op, target)

    if subject == "line_cross":
        line = _parse_line(leaf)
        if line is None:
            return False
        direction = leaf.get("dir", "A2B")
        if direction not in ("A2B", "B2A", "both"):
            return False
        l0, l1 = line
        positions = _query_positions(temporal, camera_id, alarm_type, leaf, scope)
        for _field, (prev, cur) in positions.items():
            if prev is None or cur is None:
                continue
            if not _point_pass_region(cur, leaf):
                continue
            if not _segments_cross(prev, cur, l0, l1):
                continue
            s_prev = _orient(l0, l1, prev)
            s_cur = _orient(l0, l1, cur)
            if direction == "both":
                return True
            if direction == "A2B" and s_prev > 0 > s_cur:
                return True
            if direction == "B2A" and s_prev < 0 < s_cur:
                return True
        return False

    if subject == "absence":
        gap = _as_float(leaf.get("gap_sec"))
        if gap is None or gap < 0:
            return False
        if not entries:
            return False
        last_seen = max(last for _first, last in entries.values())
        if (now - last_seen) < gap:
            return False
        # 同一节流窗口内不重复告警（alarm_interval<=0 表示不节流）
        label = leaf.get("label")
        mark_label = label if isinstance(label, str) and label else ABSENT_ALL
        fired = temporal.get_absent_fired(camera_id, alarm_type, mark_label, scope)
        interval = _as_float(alarm_interval) or 0.0
        if fired is not None and interval > 0 and (now - fired) < interval:
            return False
        return True

    if subject == "static":
        min_sec = _as_float(leaf.get("min_sec"))
        if min_sec is None or min_sec < 0:
            return False
        raw_max_move = leaf.get("max_move")
        if raw_max_move is None:
            max_move = _DEFAULT_MAX_MOVE
        else:
            max_move = _as_float(raw_max_move)
            if max_move is None or max_move < 0:
                return False
        want_field = None
        if leaf.get("track_id") is not None:
            num = _as_float(leaf.get("track_id"))
            if num is None:
                return False
            want_field = f"t:{int(num)}"
        grace = max(min_sec, _as_float(alarm_interval) or 0.0)
        moves = _query_moves(temporal, camera_id, alarm_type, leaf, scope)
        for field, _elapsed, _moved in _static_tracks(
            entries, moves, now, grace, min_sec, max_move
        ):
            if want_field is not None and field != want_field:
                continue
            return True
        return False

    if subject == "track":
        min_sec = 0.0
        raw_min = leaf.get("min_sec")
        if raw_min is not None:
            min_sec = _as_float(raw_min)
            if min_sec is None or min_sec < 0:
                return False
        grace = max(min_sec, _as_float(alarm_interval) or 0.0)
        return bool(_active_tracks(entries, now, grace, min_sec))

    return False


def _observe_temporal_event(camera_id, alarm_type: str, detections: list, now: float, conditions) -> None:
    """评估前把事件检测写入时序状态；按条件树中的区域分桶，失败仅告警不阻断告警流程。"""
    try:
        scopes: dict[str, dict | None] = {"all": None}
        for leaf in _iter_temporal_leaves(conditions):
            fp, ok = _leaf_scope(leaf)
            if not ok:
                continue
            scopes[fp] = leaf.get("region")
        for scope, region in scopes.items():
            if region is None:
                batch = detections
            else:
                batch = [d for d in detections if _in_region(d, {"region": region})]
            temporal_store.observe(camera_id, alarm_type, batch, now, scope=scope)
    except Exception as e:
        log.warning(f"时序状态写入失败: {e}")


def _mark_absence_fired(camera_id, alarm_type: str, conditions, now: float, temporal=None) -> None:
    """规则命中后写入 absence 触发标记，避免心跳在同一节流窗口内重复告警。"""
    temporal = temporal or temporal_store
    try:
        for leaf in _iter_temporal_leaves(conditions):
            if leaf.get("subject") != "absence":
                continue
            scope, ok = _leaf_scope(leaf)
            if not ok:
                continue
            label = leaf.get("label")
            if not isinstance(label, str) or not label:
                label = ABSENT_ALL
            temporal.set_absent_fired(camera_id, alarm_type, label, scope, now)
    except Exception as e:
        log.warning(f"absence 触发标记写入失败: {e}")


def _match_conditions(
    conditions: dict | None,
    detections: list[dict],
    *,
    temporal=None,
    camera_id=None,
    alarm_type=None,
    now: float | None = None,
    alarm_interval=0,
    group_camera_ids: list[int] | None = None,
) -> bool:
    """评估规则条件树；空/None 视为命中。

    叶子支持 attribute：{"subject":"attribute","field":名,"op":"lt|gt|le|ge|eq","value":数}。
    事件里 attributes 为 {属性名: 分数}（分数=具有该属性的概率）；违规=分数低于阈值。
    OCR 文本叶子：
    - text_match：{"subject":"text_match","regex":"..."}，任一 detection.text 命中正则即命中；
      非法正则视为不命中。
    - ocr_label：{"subject":"ocr_label","contains":"..."}，任一 detection.text 包含子串即命中。
    对象/区域/计数叶子（基于 bbox 中心与归一化多边形区域）：
    - object_present：{"subject":"object_present","label"?,"labels"?,"region"?,"min_confidence"?}
      存在满足 label/labels、位于 region 内、且置信度 >= min_confidence 的目标即命中。
    - zone_enter：{"subject":"zone_enter","label","region"}，目标中心落入区域即命中；
      未限定 region 时等价于 object_present（不限置信度）。
    - count：{"subject":"count","label"?,"region"?,"op":">=|>|<=|<|==","value":n}，
      统计满足条件的目标数并与 value 比较。
    时序叶子（读取 temporal 状态存储；需 camera_id/alarm_type/now）：
    - dwell：{"subject":"dwell","track_id"?,"label"?,"region"?,"min_sec":s}
      轨迹存在时长 >= min_sec 且仍活跃（last_seen 在 grace 内）。
    - count_window：{"subject":"count_window","label"?,"region"?,"window_sec":s,"op":..,"value":n}
      窗口内去重目标数（有 track_id 按轨迹，否则按事件）与 value 比较。
    - absence：{"subject":"absence","label"?,"region"?,"gap_sec":s}
      距最近一次出现 >= gap_sec（无历史视为未过期）。
    - line_cross：{"subject":"line_cross","line":[[x,y],…],"dir":"A2B|B2A|both","region"?}
      轨迹上一帧中心与当前帧中心连线是否真正穿越绊线（首尾两点），并按方向命中。
    - static：{"subject":"static","label"?,"labels"?,"region"?,"min_sec":s,"max_move"?,
      "track_id"?} 某真实轨迹存在 >= min_sec、仍活跃，且相对首帧最大位移 <= max_move。
    - track：{"subject":"track","label"?,"labels"?,"region"?,"min_sec"?}
      存在至少一条活跃的真实轨迹（可选要求时长 >= min_sec）。
    关键点几何叶子（读取 detection.keypoints，姿态/人脸模型输出 [[x,y,score],...] 归一化）：
    - keypoint_geometry：{"subject":"keypoint_geometry",
      "rule":"fall|climb|smoke_phone|face_landmark|gesture",
      "region"?,"min_sec"?,"line"?,"op"?,"value"?}
      fall=躯干（肩中点↔髋中点）与竖直方向夹角 >= 阈值（value 缺省 60°，op 缺省 >=）；
      climb=躯干中心位于 line 上方，无 line 时与高度阈值 value（缺省 0.5，op 缺省 <=）比较；
      smoke_phone=腕到头参照的最小距离 <= 阈值（value 缺省 0.15），min_sec 可选持续性抑制；
      face_landmark=有效关键点数（分数 >= 0.3）与阈值 value（缺省 5，op 缺省 >=）比较；
      gesture=已声明但未实现（缺手部关键点模型），恒不命中。区域过滤按检测框中心。
    深度安全距离叶子（读取 detection.depth，深度模型输出，单位米）：
    - distance：{"subject":"distance","op":"lt|gt|le|ge|eq","value":<米>,"label"?,"region"?}
      任一检测的数值 depth 满足比较即命中；depth 缺失/非数值/非有限值一律跳过（fail-closed）。
    语义区域占比叶子（读取 detection.attributes={类别: 面积占比}，sem 模型输出）：
    - region_ratio：{"subject":"region_ratio","op":"lt|gt|le|ge|eq","value":<占比>,
      "label"?,"labels"?} 任一对象的某个类别占比满足比较即命中，缺省对全部类别取任一满足。
    码值匹配叶子（读取 detection.text，barcode 解码结果）：
    - code_match：{"subject":"code_match","op":"in|regex","code_list"?,"regex"?}
      op=in 与名单精确比对（名单空=识别到任意非空码值）；op=regex 按正则匹配。
    其它叶子后续扩展；未知叶子不命中。
    本函数对异常输入（JSON null / 非数值 / 非 dict）一律按不命中处理，绝不向上抛异常，
    避免单条脏规则导致整个告警事件被丢弃。
    """
    # 对外行为与返回类型不变：委托 explain_conditions，仅取判定结果
    return explain_conditions(
        conditions,
        detections,
        temporal=temporal,
        camera_id=camera_id,
        alarm_type=alarm_type,
        now=now,
        alarm_interval=alarm_interval,
        group_camera_ids=group_camera_ids,
    )[0]


def explain_conditions(
    conditions: dict | None,
    detections: list[dict],
    *,
    temporal=None,
    camera_id=None,
    alarm_type=None,
    now: float | None = None,
    alarm_interval=0,
    group_camera_ids: list[int] | None = None,
) -> tuple[bool, list[dict]]:
    """在与 _match_conditions 完全相同的语义下求值，并额外返回命中叶子说明。

    返回 ``(是否命中, hits)``；hits 元素为
    ``{"path": "and/0", "subject": "object_present", "detail": "...", "negated": False}``。
    - 空/None 条件：命中且 hits 为空；非 dict 脏条件：不命中。
    - `and`：子节点全部命中才命中，返回所有命中子叶；`or`：只返回首个命中分支；
      `not`：命中（子节点均未命中）时，把子树叶子说明标记 ``negated=True`` 返回。
    - detail 为简洁中文友好描述，尽量携带关键量（置信度/计数/时长等）。
    本函数对异常输入一律按不命中处理，绝不向上抛异常。
    """
    if not conditions:
        return True, []
    if not isinstance(conditions, dict):
        # 非 dict 的脏条件不得抛异常，按不命中处理
        return False, []

    # 未显式传入状态存储时使用进程级单例（时序叶子）；非时序规则不受影响
    if temporal is None:
        temporal = temporal_store

    # 过滤脏检测项（非 dict 一律跳过），后续统一使用该列表
    raw_dets = detections if isinstance(detections, (list, tuple)) else []
    dets = [d for d in raw_dets if isinstance(d, dict)]

    def _to_float(raw) -> float | None:
        """尽力转换为 float；null/缺失/非数值返回 None，由调用方跳过该叶子。"""
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _texts() -> list[str]:
        """收集所有 detection 上的 OCR 文本（非字符串一律跳过）。"""
        return [d["text"] for d in dets if isinstance(d.get("text"), str)]

    def eval_leaf(leaf: dict) -> bool:
        subject = leaf.get("subject")
        if subject in TEMPORAL_SUBJECTS:
            return _eval_temporal(
                subject,
                leaf,
                temporal,
                camera_id,
                alarm_type,
                now,
                alarm_interval,
                group_camera_ids=group_camera_ids,
            )
        if subject == "attribute":
            field = leaf.get("field")
            op = leaf.get("op", "eq")
            value = _to_float(leaf.get("value"))
            if value is None:
                return False
            for d in dets:
                score = (d.get("attributes") or {}).get(field)
                score = _to_float(score)
                if score is None:
                    continue
                if op == "lt" and score < value:
                    return True
                if op == "gt" and score > value:
                    return True
                if op == "le" and score <= value:
                    return True
                if op == "ge" and score >= value:
                    return True
                if op == "eq" and score == value:
                    return True
            return False
        if subject == "distance":
            # 深度安全距离叶子（读取 detection.depth，单位米）
            return _distance_hit(leaf, dets)
        if subject == "region_ratio":
            # 语义区域占比叶子（读取 detection.attributes={类别: 占比}）
            return _region_ratio_hit(leaf, dets)
        if subject == "code_match":
            # 码值匹配叶子（读取 detection.text，条码/二维码解码结果）
            return _code_match_hit(leaf, dets)
        if subject == "text_match":
            pattern = leaf.get("regex")
            if not isinstance(pattern, str):
                return False
            # 安全执行：模式长度/灾难性回溯静态校验 + 编译缓存 + 文本截断（审计 #10）。
            # 不安全/非法模式视为不命中，避免单条脏规则拖垮事件循环。
            return any(safe_regex_search(pattern, text) for text in _texts())
        if subject == "ocr_label":
            needle = leaf.get("contains")
            if not isinstance(needle, str):
                return False
            return any(needle in text for text in _texts())
        if subject in ("object_present", "zone_enter"):
            min_conf = None
            if subject == "object_present":
                raw_min = leaf.get("min_confidence")
                if raw_min is not None:
                    min_conf = _as_float(raw_min)
                    if min_conf is None:
                        # min_confidence 非法（非数值）→ 不命中
                        return False
            for d in dets:
                if not _matches_label(d, leaf):
                    continue
                if not _in_region(d, leaf):
                    continue
                if min_conf is not None:
                    conf = _as_float(d.get("confidence"))
                    if conf is None or conf < min_conf:
                        continue
                return True
            return False
        if subject == "keypoint_geometry":
            # 姿态几何叶子（fall/climb/smoke_phone；gesture 为已声明桩实现）
            return _keypoint_geometry_hit(
                leaf,
                dets,
                temporal=temporal,
                camera_id=camera_id,
                alarm_type=alarm_type,
                now=now,
                alarm_interval=alarm_interval,
            )
        if subject == "count":
            op = leaf.get("op")
            if op not in (">=", ">", "<=", "<", "=="):
                return False
            target = _as_float(leaf.get("value"))
            if target is None:
                return False
            matched = sum(1 for d in dets if _matches_label(d, leaf) and _in_region(d, leaf))
            if op == ">=":
                return matched >= target
            if op == ">":
                return matched > target
            if op == "<=":
                return matched <= target
            if op == "<":
                return matched < target
            return matched == target
        return False

    def _fmt_num(v) -> str:
        """数值说明格式化：整数值去掉小数点，其余按原样。"""
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    def _label_text(leaf: dict) -> str:
        """叶子的标签展示文本：labels 列表优先，其次单个 label，都缺省为 *。"""
        labels = leaf.get("labels")
        if isinstance(labels, (list, tuple)) and labels:
            return "/".join(str(x) for x in labels)
        label = leaf.get("label")
        return str(label) if label is not None else "*"

    def _find_det(leaf: dict, subject: str) -> dict | None:
        """找出首个满足 object_present/zone_enter 的检测（仅用于生成说明，不参与判定）。"""
        min_conf = None
        if subject == "object_present":
            raw_min = leaf.get("min_confidence")
            if raw_min is not None:
                min_conf = _as_float(raw_min)
        for d in dets:
            if not _matches_label(d, leaf) or not _in_region(d, leaf):
                continue
            if min_conf is not None:
                conf = _as_float(d.get("confidence"))
                if conf is None or conf < min_conf:
                    continue
            return d
        return None

    def _object_detail(subject: str, leaf: dict) -> str:
        label = _label_text(leaf)
        d = _find_det(leaf, subject)
        if d is not None:
            conf = _as_float(d.get("confidence"))
            if conf is not None:
                return f"{d.get('label') or label} conf={conf:.2f}"
        raw_min = leaf.get("min_confidence")
        min_conf = _as_float(raw_min) if raw_min is not None else None
        if min_conf is not None:
            return f"{label} conf>={min_conf:.2f}"
        return f"{label} conf=-"

    def _attribute_detail(leaf: dict) -> str:
        field = leaf.get("field")
        op = leaf.get("op", "eq")
        value = _to_float(leaf.get("value"))
        for d in dets:
            score = _to_float((d.get("attributes") or {}).get(field))
            if score is None:
                continue
            hit = value is not None and (
                (op == "lt" and score < value)
                or (op == "gt" and score > value)
                or (op == "le" and score <= value)
                or (op == "ge" and score >= value)
                or (op == "eq" and score == value)
            )
            if hit:
                return f"{field}={score:.2f}{op}{_fmt_num(value)}"
        return f"{field}=?{op}{_fmt_num(leaf.get('value'))}"

    def _distance_detail(leaf: dict) -> str:
        """distance 叶子的关键量说明；无有效 depth 时给出可读回退。"""
        op = leaf.get("op")
        value = _as_float(leaf.get("value"))
        for d in dets:
            if not isinstance(d, dict):
                continue
            if not _matches_label(d, leaf) or not _in_region(d, leaf):
                continue
            depth = _as_float(d.get("depth"))
            if depth is None or not math.isfinite(depth):
                continue
            return f"depth {depth:.2f}{op}{_fmt_num(value)}"
        return f"depth ?{op}{_fmt_num(leaf.get('value'))}"

    def _region_ratio_detail(leaf: dict) -> str:
        """region_ratio 叶子的关键量说明；无有效占比时给出可读回退。"""
        op = leaf.get("op")
        value = _as_float(leaf.get("value"))
        categories = _ratio_categories(leaf)
        for d in dets:
            attrs = d.get("attributes") if isinstance(d, dict) else None
            if not isinstance(attrs, dict):
                continue
            pairs = (
                [(k, attrs.get(k)) for k in categories]
                if categories is not None
                else list(attrs.items())
            )
            for key, raw in pairs:
                ratio = _as_float(raw)
                if ratio is None or not math.isfinite(ratio):
                    continue
                return f"ratio {key}={ratio:.2f}{op}{_fmt_num(value)}"
        return f"ratio ?{op}{_fmt_num(leaf.get('value'))}"

    def _code_match_detail(leaf: dict) -> str:
        """code_match 叶子的关键量说明；无有效码值时给出可读回退。"""
        op = leaf.get("op") or "in"
        texts = _texts_of(dets)
        if op == "regex":
            pattern = leaf.get("regex")
            hit = next((t for t in texts if isinstance(pattern, str) and safe_regex_search(pattern, t)), None)
            return f"code {hit}~{pattern}" if hit else f"code ~{pattern}"
        codes = leaf.get("code_list")
        wanted = (
            {str(c).strip() for c in codes if isinstance(c, (str, int, float)) and not isinstance(c, bool)}
            if isinstance(codes, (list, tuple))
            else set()
        )
        if wanted:
            hit = next((t for t in texts if t in wanted), None)
            return f"code {hit or '?'} in list({len(wanted)})"
        return f"code {texts[0]}" if texts else "code -"

    def _temporal_detail(subject: str, leaf: dict) -> str:
        """时序叶子的关键量说明；缺状态时给出可读回退。"""
        scope, ok = _leaf_scope(leaf)
        entries: dict = {}
        if ok and temporal is not None and camera_id is not None and now is not None:
            entries = _query_temporal(temporal, camera_id, alarm_type, leaf, scope)
        if subject in ("group_count", "group_coverage"):
            window = _as_float(leaf.get("window_sec"))
            count = 0
            active_n = 0
            total = len(group_camera_ids or [])
            if ok and temporal is not None and now is not None and group_camera_ids and window is not None:
                merged: dict = {}
                for lab in _leaf_labels(leaf) or [None]:
                    merged.update(
                        temporal.query_multi(group_camera_ids, alarm_type, lab, scope)
                    )
                start = now - window
                count = sum(1 for _k, (_first, last) in merged.items() if last >= start)
                active_n = len(
                    {
                        cam
                        for (cam, _field), (_first, last) in merged.items()
                        if last >= start
                    }
                )
            if subject == "group_count":
                return f"group {count}{leaf.get('op')}{_fmt_num(leaf.get('value'))}"
            return f"group cov {active_n}/{total}{leaf.get('op')}{_fmt_num(leaf.get('value'))}"
        if subject == "dwell":
            elapsed = (
                max((now - first for first, _last in entries.values()), default=0.0)
                if now is not None
                else 0.0
            )
            return f"dwell {elapsed:.0f}s>={_fmt_num(leaf.get('min_sec'))}s"
        if subject == "count_window":
            window = _as_float(leaf.get("window_sec"))
            count = 0
            if window is not None and now is not None:
                start = now - window
                count = sum(1 for _first, last in entries.values() if last >= start)
            return f"window {count}{leaf.get('op')}{_fmt_num(leaf.get('value'))}"
        if subject == "absence":
            silent = 0.0
            if entries and now is not None:
                silent = now - max(last for _first, last in entries.values())
            return f"absence {silent:.0f}s>={_fmt_num(leaf.get('gap_sec'))}s"
        if subject == "line_cross":
            direction = leaf.get("dir", "A2B")
            line = _parse_line(leaf)
            if line is not None and ok and temporal is not None and camera_id is not None:
                l0, l1 = line
                positions = _query_positions(temporal, camera_id, alarm_type, leaf, scope)
                for _field, (prev, cur) in positions.items():
                    if prev is None or cur is None:
                        continue
                    if not _point_pass_region(cur, leaf):
                        continue
                    if not _segments_cross(prev, cur, l0, l1):
                        continue
                    return (
                        f"cross ({prev[0]:.2f},{prev[1]:.2f})->"
                        f"({cur[0]:.2f},{cur[1]:.2f}) dir={direction}"
                    )
            return f"cross dir={direction}"
        if subject == "static":
            min_sec = _as_float(leaf.get("min_sec"))
            max_move = _DEFAULT_MAX_MOVE
            raw_max_move = leaf.get("max_move")
            if raw_max_move is not None:
                parsed = _as_float(raw_max_move)
                if parsed is not None:
                    max_move = parsed
            if min_sec is None or min_sec < 0:
                return "static -"
            grace = max(min_sec, _as_float(alarm_interval) or 0.0)
            best_static = None
            best_any = None
            if ok and temporal is not None and camera_id is not None and now is not None:
                moves = _query_moves(temporal, camera_id, alarm_type, leaf, scope)
                for field, (first, last) in entries.items():
                    if _track_id_of(field) is None:
                        continue
                    elapsed = now - first
                    moved = moves.get(field, 0.0)
                    if best_any is None or elapsed > best_any[0]:
                        best_any = (elapsed, moved)
                    if elapsed >= min_sec and (now - last) <= grace and moved <= max_move:
                        if best_static is None or elapsed > best_static[0]:
                            best_static = (elapsed, moved)
            pick = best_static or best_any
            if pick is None:
                return "static -"
            return f"static {pick[0]:.0f}s move={pick[1]:.3f}"
        if subject == "track":
            min_sec = 0.0
            raw_min = leaf.get("min_sec")
            if raw_min is not None:
                parsed = _as_float(raw_min)
                if parsed is not None and parsed >= 0:
                    min_sec = parsed
            grace = max(min_sec, _as_float(alarm_interval) or 0.0)
            count = 0
            if ok and now is not None:
                count = len(_active_tracks(entries, now, grace, min_sec))
            return f"track {count}"
        return str(subject)

    def _keypoint_detail(leaf: dict) -> str:
        """关键点几何叶子的关键量说明；无法测量时给出可读回退。"""
        rule = leaf.get("rule")
        rule = rule.strip().lower() if isinstance(rule, str) else ""
        if rule == "gesture":
            return "gesture 未实现(缺 21 点手部关键点)"
        if rule not in ("fall", "climb", "smoke_phone", "face_landmark"):
            return str(leaf.get("subject"))
        op = leaf.get("op") or ("<=" if rule in ("climb", "smoke_phone") else ">=")
        for d in dets:
            if not _in_region(d, leaf):
                continue
            kps = _keypoints_of(d)
            if not kps:
                continue
            if rule == "fall":
                torso = _kp_torso(kps)
                angle = _kp_torso_angle(*torso) if torso is not None else None
                if angle is None:
                    continue
                raw = leaf.get("value")
                threshold = _DEFAULT_FALL_ANGLE if raw is None else _as_float(raw)
                if threshold is None:
                    return "fall -"
                return f"fall {angle:.0f}°{op}{_fmt_num(threshold)}°"
            if rule == "face_landmark":
                min_count, ok = _face_landmark_threshold(leaf)
                if not ok:
                    return "face_landmark -"
                return f"face_kp {_kp_visible_count(kps)}{op}{_fmt_num(min_count)}"
            if rule == "climb":
                center = _climb_body_center(kps)
                if center is None:
                    continue
                if leaf.get("line") is not None:
                    line = _parse_line(leaf)
                    if line is None:
                        return "climb line=?"
                    above = _is_above_line(line[0], line[1], center)
                    return "climb 位于绊线上方" if above else "climb 未越线"
                threshold, ok = _climb_threshold(leaf)
                if not ok:
                    return "climb -"
                return f"climb y={center[1]:.2f}{op}{_fmt_num(threshold)}"
            if rule == "smoke_phone":
                dist = _hand_head_distance(kps)
                if dist is None:
                    continue
                threshold, ok = _smoke_phone_threshold(leaf)
                if not ok:
                    return "smoke_phone -"
                suffix = ""
                if leaf.get("min_sec") is not None:
                    sustained = _smoke_phone_sustained(
                        leaf,
                        temporal=temporal,
                        camera_id=camera_id,
                        alarm_type=alarm_type,
                        now=now,
                        alarm_interval=alarm_interval,
                    )
                    suffix = f" sust={'Y' if sustained else 'N'}"
                return f"smoke_phone d={dist:.2f}{op}{threshold:.2f}{suffix}"
        return f"{rule} -"

    def leaf_detail(leaf: dict) -> str:
        """生成叶子说明；任何异常都回退为 subject 名，绝不影响判定结果。"""
        subject = leaf.get("subject")
        try:
            if subject in ("object_present", "zone_enter"):
                return _object_detail(subject, leaf)
            if subject == "count":
                op = leaf.get("op")
                matched = sum(1 for d in dets if _matches_label(d, leaf) and _in_region(d, leaf))
                return f"{matched}{op}{_fmt_num(leaf.get('value'))}"
            if subject == "attribute":
                return _attribute_detail(leaf)
            if subject == "distance":
                return _distance_detail(leaf)
            if subject == "region_ratio":
                return _region_ratio_detail(leaf)
            if subject == "code_match":
                return _code_match_detail(leaf)
            if subject == "text_match":
                return f"text~{leaf.get('regex')}"
            if subject == "ocr_label":
                return f"text⊃{leaf.get('contains')}"
            if subject == "keypoint_geometry":
                return _keypoint_detail(leaf)
            if subject in TEMPORAL_SUBJECTS:
                return _temporal_detail(subject, leaf)
        except Exception:
            pass
        return str(subject)

    def _leaf_hit(leaf: dict, path: str, *, negated: bool = False) -> dict:
        """构造命中叶子说明。"""
        return {
            "path": path,
            "subject": leaf.get("subject"),
            "detail": leaf_detail(leaf),
            "negated": negated,
        }

    def collect(node, path: str) -> list[dict]:
        """收集子树内所有叶子的说明（供 not 取反时使用）。"""
        if not isinstance(node, dict):
            return []
        op = node.get("op")
        if op in ("and", "or", "not"):
            out: list[dict] = []
            for i, k in enumerate(node.get("children") or []):
                out.extend(collect(k, f"{path}/{op}/{i}" if path else f"{op}/{i}"))
            return out
        return [_leaf_hit(node, path)]

    def eval_node(node, path: str) -> tuple[bool, list[dict]]:
        # 非 dict 节点（脏规则）不得抛异常，按不命中处理
        if not isinstance(node, dict):
            return False, []
        # 逻辑节点（and/or/not）与属性叶子都带 "op"，用逻辑算子集合区分：
        # 叶子 op 为 lt/gt/le/ge/eq 或比较符，若误当逻辑节点会直接不命中。
        op = node.get("op")
        if op in ("and", "or", "not"):
            kids = node.get("children") or []
            if op == "and":
                if not kids:
                    return True, []
                hits: list[dict] = []
                for i, k in enumerate(kids):
                    ok, kh = eval_node(k, f"{path}/and/{i}" if path else f"and/{i}")
                    if not ok:
                        return False, []
                    hits.extend(kh)
                return True, hits
            if op == "or":
                for i, k in enumerate(kids):
                    ok, kh = eval_node(k, f"{path}/or/{i}" if path else f"or/{i}")
                    if ok:
                        return True, kh
                return False, []
            # not：命中（子节点均未命中）时，把子树叶子说明标记取反返回
            for i, k in enumerate(kids):
                ok, _kh = eval_node(k, f"{path}/not/{i}" if path else f"not/{i}")
                if ok:
                    return False, []
            hits = []
            for i, k in enumerate(kids):
                kpath = f"{path}/not/{i}" if path else f"not/{i}"
                for h in collect(k, kpath):
                    hits.append({**h, "negated": True})
            return True, hits
        ok = eval_leaf(node)
        if not ok:
            return False, []
        return True, [_leaf_hit(node, path)]

    return eval_node(conditions, "")


def _event_id_kv(event_id) -> dict:
    """仅当事件携带 ``event_id`` 时附加到返回体，保持既有返回体兼容。"""
    return {"event_id": event_id} if event_id else {}


async def _publish_edge_event(row_id: int | None) -> None:
    """落库成功后广播事件详情（与 detail 接口同结构）；失败仅告警，不阻断告警链路。"""
    if not row_id:
        return
    try:
        from fastapi.encoders import jsonable_encoder
        from sqlalchemy import select

        from app.api.v1.module_video.edge.event_bus import publish_edge_event
        from app.api.v1.module_video.edge.model import EdgeEventModel
        from app.api.v1.module_video.edge.service import _event_detail
        from app.core.database import async_db_session

        async with async_db_session() as session:
            row = (
                await session.execute(select(EdgeEventModel).where(EdgeEventModel.id == row_id))
            ).scalars().first()
        if row is None:
            return
        await publish_edge_event(jsonable_encoder(_event_detail(row)))
    except Exception as e:
        log.warning(f"边缘事件广播失败: {e}")


async def _persist_edge_event(
    event: dict, *, matched: bool, rule_id, matched_leaves
) -> int | None:
    """落库边缘事件（薄封装）；任何失败仅告警，绝不阻断告警链路。

    仅当真正落库成功（非空事件、非重复 ``event_id``）才广播事件详情，
    广播失败不得影响返回的落库 id。
    """
    try:
        from app.api.v1.module_video.edge.store import record_edge_event

        row_id = await record_edge_event(
            event, matched=matched, rule_id=rule_id, matched_leaves=matched_leaves
        )
    except Exception as e:
        log.warning(f"边缘事件落库失败: {e}")
        return None

    if row_id:
        try:
            await _publish_edge_event(row_id)
        except Exception as e:
            log.warning(f"边缘事件广播失败: {e}")
    return row_id


async def _evaluate_rule(
    rule,
    event: dict,
    detections: list,
    camera_id,
    alarm_type: str,
    event_now: float,
    saved_snapshot_path,
    group_camera_ids: list[int] | None = None,
) -> dict | None:
    """对单条规则执行「观测 → 评估 → 建告警（+联动/通知）」。

    未命中返回 None；命中返回
    ``{"alarm_id": int, "rule_id": int | None, "rule_name": str | None, "hit_leaves": list}``。
    ``rule`` 为 None 表示无匹配规则时的历史兼容路径（直接建档，rule_matched 为 None）。
    ``group_camera_ids`` 供组作用域规则的跨相机聚合叶子使用（相机规则传入亦无害）。
    """
    from app.api.v1.module_video.alarm.model import AlarmRecordModel
    from app.core.database import async_db_session

    has_temporal = bool(
        rule is not None and rule.conditions and _has_temporal_leaf(rule.conditions)
    )
    hit_leaves: list = []
    if rule is not None and rule.conditions:
        # 时序叶子需先写入本次观测（按事件 ts），再评估；非时序规则行为不变。
        # 时序状态存储（TemporalStore）当前为同步 Redis 客户端，直接在事件循环里调用
        # 会在 Redis 抖动时阻塞整个事件循环（审计 §并发-5），故经线程池下发执行。
        if has_temporal:
            await run_in_threadpool(
                _observe_temporal_event,
                camera_id,
                alarm_type,
                detections,
                event_now,
                rule.conditions,
            )
        matched, hit_leaves = await run_in_threadpool(
            explain_conditions,
            rule.conditions,
            detections,
            camera_id=camera_id,
            alarm_type=alarm_type,
            now=event_now,
            alarm_interval=getattr(rule, "interval_seconds", 0) or 0,
            group_camera_ids=group_camera_ids,
        )
        if not matched:
            return None
        if has_temporal:
            # 命中后写入 absence 触发标记（纯读取的 _eval_temporal 不改状态）
            await run_in_threadpool(
                _mark_absence_fired, camera_id, alarm_type, rule.conditions, event_now
            )

    severity = rule.severity if rule else "WARNING"

    # v2 objects：优先取事件携带的；HTTP 兼容路径缺失时由 detections 派生
    raw_objects = event.get("objects")
    objects = (
        [o for o in raw_objects if isinstance(o, dict)] if isinstance(raw_objects, list) else []
    )
    if not objects and detections:
        objects = [
            {
                "label": d.get("label", ""),
                "label_id": d.get("label_id", 0),
                "confidence": d.get("confidence", 0.0),
                "bbox": d.get("bbox") or {},
                **({"track_id": d["track_id"]} if d.get("track_id") is not None else {}),
                **({"attributes": d["attributes"]} if isinstance(d.get("attributes"), dict) else {}),
                **({"text": d["text"]} if d.get("text") is not None else {}),
            }
            for d in detections
            if isinstance(d, dict)
        ]

    alarm_data = {
        "camera_id": camera_id,
        "rule_id": rule.id if rule else None,
        "alarm_type": alarm_type,
        "severity": severity,
        "snapshot_path": saved_snapshot_path,
        "ai_result": {
            "task_id": event.get("task_id"),
            "algorithm_type": event.get("algorithm_type"),
            "detections": detections,
            "objects": objects,
            "frame_timestamp": event.get("frame_timestamp"),
        },
        "description": (
            f"AI 检测到 {len(detections)} 个目标: "
            f"{', '.join(d.get('label', '') for d in detections[:5])}"
            if detections
            else (f"{rule.name}：区域内持续无目标" if rule else "区域内持续无目标")
        ),
        "status": "PENDING",
    }

    async with async_db_session.begin() as session:
        record = AlarmRecordModel(**alarm_data)
        session.add(record)
        await session.flush()
        alarm_id = record.id

    # 触发事件联动（ALARM 事件 → RECORD/通知等动作，逻辑闭环）
    try:
        from app.api.v1.module_video.event.service import EventService

        await EventService.execute_linkage_actions(camera_id, "ALARM")
    except Exception as e:
        log.warning(f"事件联动执行异常: {e}")

    # Async notification
    if rule:
        try:
            # dispatch_notification 只读 auth.db；提供真实会话而非构造 AuthSchema(db=None)
            from types import SimpleNamespace

            from app.utils.notification import dispatch_notification

            async with async_db_session() as notify_db:
                auth_like = SimpleNamespace(db=notify_db)
                alarm_dict = {
                    "id": alarm_id,
                    "camera_id": camera_id,
                    "alarm_type": event.get("algorithm_type"),
                    "severity": severity,
                    "alarm_time": datetime.now().isoformat(),
                    "description": alarm_data["description"],
                    "snapshot_path": saved_snapshot_path,
                    "camera": {"name": ""},
                    "rule_id": rule.id,
                }
                rule_dict = {
                    "id": rule.id,
                    "name": rule.name,
                    "severity": rule.severity,
                    "notify_channels": rule.notify_channels,
                }
                await dispatch_notification(auth_like, alarm_dict, rule_dict)
        except Exception as e:
            log.warning(f"通知分发失败: {e}")

    return {
        "alarm_id": alarm_id,
        "rule_id": rule.id if rule else None,
        "rule_name": rule.name if rule else None,
        "hit_leaves": hit_leaves,
    }


class InferenceService:

    @classmethod
    async def process_detection_callback(cls, event: dict) -> dict:
        """Process a detection event from a worker callback."""
        from sqlalchemy import or_, select

        from app.api.v1.module_video.alarm.model import AlarmRuleModel
        from app.api.v1.module_video.camera.model import CameraModel
        from app.core.database import async_db_session

        camera_id = event.get("camera_id")
        algorithm_type = event.get("algorithm_type")
        detections = event.get("detections", [])
        if not isinstance(detections, list):
            detections = []
        snapshot_data = event.get("snapshot_data")
        snapshot_path = event.get("snapshot_path")
        frame_timestamp = event.get("frame_timestamp")

        # Save snapshot
        saved_snapshot_path = None
        if snapshot_data:
            try:
                from app.api.v1.module_video.inference.snapshot import safe_detections_path

                detectors_dir = Path(settings.DETECTIONS_DIR)
                detectors_dir.mkdir(parents=True, exist_ok=True)
                snap_name = snapshot_path or f"{camera_id}_{int(datetime.now().timestamp())}.jpg"
                # 归一化并校验路径必须落在 DETECTIONS_DIR 内，拒绝目录穿越
                snap_full = safe_detections_path(snap_name)
                if snap_full is None:
                    log.warning(f"拒绝越界的快照写入路径: {snap_name!r}")
                else:
                    snap_full.parent.mkdir(parents=True, exist_ok=True)
                    img_bytes = base64.b64decode(snapshot_data)
                    snap_full.write_bytes(img_bytes)
                    saved_snapshot_path = str(snap_full)
            except Exception as e:
                log.warning(f"保存快照失败: {e}")
        elif snapshot_path:
            # 边缘事件：快照已由 Agent 上传对象存储，此处仅存相对引用
            saved_snapshot_path = snapshot_path

        alarm_type = algorithm_type or "AI_DETECTION"
        event_now = to_epoch(frame_timestamp)

        # 作用域查询：直绑该相机 OR 绑定该相机所属相机组（一条组规则覆盖组内多台相机）
        rules: list = []
        async with async_db_session() as session:
            # 用 scalars().all() 而非 scalar_one_or_none()，兼容既有测试的极简假会话
            group_rows = (
                await session.execute(
                    select(CameraModel.group_id).where(CameraModel.id == camera_id)
                )
            ).scalars().all()
            cam_group_id = group_rows[0] if group_rows else None

            scope_conds = [AlarmRuleModel.camera_id == camera_id]
            if cam_group_id is not None:
                scope_conds.append(AlarmRuleModel.group_id == cam_group_id)
            stmt = select(AlarmRuleModel).where(
                or_(*scope_conds),
                AlarmRuleModel.alarm_type == alarm_type,
                AlarmRuleModel.status.is_(True),
                AlarmRuleModel.is_deleted.is_(False),
            )
            rules = list((await session.execute(stmt)).scalars().all())

            # 组内相机 id 列表：仅当命中组作用域规则时才查（跨相机聚合叶子所需的上下文）
            group_camera_ids: list[int] = []
            if cam_group_id is not None and any(
                getattr(r, "group_id", None) is not None for r in rules
            ):
                group_cam_rows = (
                    await session.execute(
                        select(CameraModel.id).where(CameraModel.group_id == cam_group_id)
                    )
                ).scalars().all()
                group_camera_ids = [int(x) for x in group_cam_rows]

        # 任一规则含时序叶子（absence 等）时，空检测心跳仍需继续评估
        any_temporal = any(
            r.conditions and _has_temporal_leaf(r.conditions) for r in rules
        )
        if not detections and not any_temporal:
            return {"alarm_created": False, "reason": "no_detections"}

        event_id = event.get("event_id")
        # 无匹配规则时保留既有兼容路径：建一条 rule=None 的告警（rule_matched 为 None）
        candidates = rules if rules else [None]

        alarm_ids: list[int] = []
        matched_rule_names: list[str] = []
        first_matched_rule_id = None
        first_hit_leaves: list = []
        skipped: list[dict] = []
        rule_errors: list[dict] = []
        for rule in candidates:
            # 规则层灰度 gating：跳过者不观测、不评估、不落库（逐条独立）
            if rule is not None:
                active, reason = rule_active_now(
                    getattr(rule, "schedule_json", None),
                    getattr(rule, "rollout", None),
                    camera_id,
                    event_now,
                    rule_id=rule.id,
                )
                if not active:
                    log.info(f"规则 {rule.id} 灰度跳过（{reason}）: camera={camera_id}")
                    skipped.append({"rule_id": rule.id, "reason": reason})
                    continue
            # 单规则异常隔离：某规则抛错不得中断后续规则（审计 §6-4），
            # 失败规则单独记录并在返回体中可观测（不再让事件以 matched=True 掩盖）。
            try:
                res = await _evaluate_rule(
                    rule,
                    event,
                    detections,
                    camera_id,
                    alarm_type,
                    event_now,
                    saved_snapshot_path,
                    group_camera_ids=group_camera_ids,
                )
            except Exception as e:  # noqa: BLE001 - 逐规则隔离，继续评估其余规则
                rid = getattr(rule, "id", None)
                log.error(f"规则 {rid} 评估/落库失败，已跳过并继续其余规则: {e}")
                rule_errors.append({"rule_id": rid, "error": str(e)})
                continue
            if not res:
                continue
            if not alarm_ids:
                first_matched_rule_id = res.get("rule_id")
                first_hit_leaves = res.get("hit_leaves") or []
            if res.get("rule_name") is not None:
                matched_rule_names.append(res["rule_name"])
            alarm_ids.append(res["alarm_id"])

        if not alarm_ids:
            # 有规则但全部未命中：落一条未命中事件（便于回溯"为什么没命中"）
            # 被灰度跳过的规则不落库：仅当存在真正被评估的候选时才落未命中事件
            if len(skipped) < len(candidates):
                await _persist_edge_event(
                    event, matched=False, rule_id=rules[0].id if rules else None, matched_leaves=[]
                )
            result = {
                "alarm_created": False,
                "reason": "rule_not_matched",
                **_event_id_kv(event_id),
            }
            if skipped:
                result["rule_skipped_list"] = skipped
            if rule_errors:
                result["rule_error_list"] = rule_errors
            return result

        # 命中（或规则为空）建告警后落库；失败仅告警，不影响告警返回
        await _persist_edge_event(
            event,
            matched=True,
            rule_id=first_matched_rule_id,
            matched_leaves=first_hit_leaves,
        )

        result = {
            "alarm_id": alarm_ids[0],
            "alarm_created": True,
            "rule_matched": matched_rule_names[0] if matched_rule_names else None,
            "alarm_ids": alarm_ids,
            "rule_matched_list": matched_rule_names,
            **_event_id_kv(event_id),
        }
        # 单规则/无跳过路径保持返回体逐字节不变；仅在有跳过/失败时附加排查字段
        if skipped:
            result["rule_skipped_list"] = skipped
        if rule_errors:
            result["rule_error_list"] = rule_errors
        return result
