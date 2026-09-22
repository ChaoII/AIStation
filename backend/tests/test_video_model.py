from app.api.v1.module_annotation.dataset.model import (
    AnnotationType,
    AnnotationVideoModel,
    DatasetModel,
    ImageStatus,
)


def test_video_detection_enum():
    assert AnnotationType.VIDEO_DETECTION == "video_detection"


def test_video_model_table_and_defaults():
    # 字段按项目约定通过列元数据校验：SQLAlchemy 的 column default 在 flush 时才
    # 落到实例属性上，瞬态对象上为 None，故此处校验列的默认值定义本身。
    assert AnnotationVideoModel.__tablename__ == "annotation_video"
    cols = AnnotationVideoModel.__table__.columns
    assert "dataset_id" in cols
    assert "name" in cols
    assert "object_key" in cols
    assert cols["frame_count"].default.arg == 0
    assert cols["width"].default.arg == 0
    assert cols["height"].default.arg == 0
    assert cols["duration"].default.arg == 0.0
    assert cols["fps"].default.arg == 0.0
    assert cols["annotation_count"].default.arg == 0
    assert cols["status"].default.arg is ImageStatus.UNANNOTATED


def test_video_status_enum_value():
    # 状态枚举的 .value 应等于 "unannotated"（与 brief 中 inst 校验语义一致）
    assert ImageStatus.UNANNOTATED.value == "unannotated"


def test_dataset_video_relationship_and_count():
    dcols = DatasetModel.__table__.columns
    assert "video_count" in dcols
    assert dcols["video_count"].default.arg == 0
    rels = DatasetModel.__mapper__.relationships
    assert "videos" in rels
    assert rels["videos"].argument == "AnnotationVideoModel"
