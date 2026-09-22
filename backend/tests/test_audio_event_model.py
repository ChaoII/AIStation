from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import (
    AnnotationAudioModel,
    AnnotationType,
    DatasetModel,
    ImageStatus,
)


def test_audio_event_enum():
    assert AnnotationType.AUDIO_EVENT == "audio_event"


def test_audio_model_table_and_defaults():
    assert AnnotationAudioModel.__tablename__ == "annotation_audio"
    cols = AnnotationAudioModel.__table__.columns
    assert "dataset_id" in cols
    assert "name" in cols
    assert "object_key" in cols
    assert "duration" in cols
    assert "sample_rate" in cols
    assert "channels" in cols
    assert "bitrate" in cols
    assert "size_bytes" in cols
    assert cols["duration"].default.arg == 0.0
    assert cols["sample_rate"].default.arg == 0
    assert cols["channels"].default.arg == 0
    assert cols["size_bytes"].default.arg == 0
    assert cols["annotation_count"].default.arg == 0
    assert cols["status"].default.arg is ImageStatus.UNANNOTATED


def test_audio_model_nullable_fields():
    cols = AnnotationAudioModel.__table__.columns
    assert cols["bitrate"].nullable is True
    assert cols["locked_by"].nullable is True
    assert cols["locked_at"].nullable is True


def test_dataset_audio_relationship_and_count():
    dcols = DatasetModel.__table__.columns
    assert "audio_count" in dcols
    assert dcols["audio_count"].default.arg == 0
    rels = DatasetModel.__mapper__.relationships
    assert "audios" in rels
    assert rels["audios"].argument == "AnnotationAudioModel"


def test_annotation_record_audio_id():
    cols = AnnotationRecordModel.__table__.columns
    assert "audio_id" in cols
    assert cols["audio_id"].nullable is True


def test_annotation_record_audio_composite_index():
    indexes = {idx.name: idx for idx in AnnotationRecordModel.__table__.indexes}
    assert "ix_annotation_record_task_audio_version" in indexes
    assert set(indexes["ix_annotation_record_task_audio_version"].columns.keys()) == {
        "task_id",
        "audio_id",
        "version",
    }
