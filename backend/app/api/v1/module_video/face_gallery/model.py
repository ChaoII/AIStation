from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class FaceGalleryModel(ModelMixin, UserMixin):
    """人脸底库：一条记录 = 一张底图（或多张底图的其中一张）的归一化特征向量。

    存储约定（无 pgvector 时的可移植方案，见 ``store.py`` 的说明）：
    - ``embedding`` 存 JSON 数组（PG 为 JSONB，SQLite/MySQL 为 JSON），
      pgvector 不可用时**不建向量索引**，相似度在 Python 侧算余弦；
    - ``dimension`` 冗余记录向量维度，匹配时按维度快速过滤（避免跨模型误比）；
    - ``model_key`` 标识产出该特征的模型（如 ``w600k_r50`` / ``seetaface_1024``），
      仅同模型的特征才可比较（维度一致时仍可比，但语义上应按 model_key 分组维护）。

    同一人员允许多行（多张底图），匹配时取「与底库全部底图的最大相似度」。
    """

    __tablename__ = "video_face_gallery"
    __table_args__ = ({"comment": "人脸底库表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="人员姓名/标签"
    )
    person_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="工号/自定义编号"
    )
    model_key: Mapped[str] = mapped_column(
        String(64), default="unknown", nullable=False, comment="特征模型标识"
    )
    embedding: Mapped[list] = mapped_column(
        JSONB, nullable=False, comment="人脸特征向量（L2 归一化 float 数组）"
    )
    dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="特征维度"
    )
    face_image_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="底图引用（便于人工核对）"
    )
