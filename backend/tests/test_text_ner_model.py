from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import (
    AnnotationDocumentModel,
    AnnotationType,
    DatasetModel,
    ImageStatus,
)


def test_text_ner_enum():
    assert AnnotationType.TEXT_NER == "text_ner"


def test_document_model_table_and_defaults():
    assert AnnotationDocumentModel.__tablename__ == "annotation_document"
    cols = AnnotationDocumentModel.__table__.columns
    assert "dataset_id" in cols
    assert "filename" in cols
    assert "object_key" in cols
    assert "content_hash" in cols
    assert "encoding" in cols
    assert "character_count" in cols
    assert "line_count" in cols
    assert cols["character_count"].default.arg == 0
    assert cols["line_count"].default.arg == 0
    assert cols["annotation_count"].default.arg == 0
    assert cols["status"].default.arg is ImageStatus.UNANNOTATED


def test_document_model_nullable_fields():
    cols = AnnotationDocumentModel.__table__.columns
    assert cols["locked_by"].nullable is True
    assert cols["locked_at"].nullable is True
    assert cols["content_hash"].nullable is False
    assert cols["encoding"].nullable is False


def test_dataset_document_relationship_and_count():
    dcols = DatasetModel.__table__.columns
    assert "document_count" in dcols
    assert dcols["document_count"].default.arg == 0
    rels = DatasetModel.__mapper__.relationships
    assert "documents" in rels
    assert rels["documents"].argument == "AnnotationDocumentModel"


def test_annotation_record_document_id():
    cols = AnnotationRecordModel.__table__.columns
    assert "document_id" in cols
    assert cols["document_id"].nullable is True
