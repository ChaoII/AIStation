"""个人空间请求/响应 Schema。"""
from pydantic import BaseModel, Field


class SpaceFolderCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="文件夹名称")
    parent_id: int | None = Field(default=None, description="父文件夹ID（空为根目录）")


class SpaceFolderUpdateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="文件夹名称")


class SpaceFileMoveSchema(BaseModel):
    file_id: int = Field(..., description="文件ID")
    folder_id: int | None = Field(default=None, description="目标文件夹ID（空为根目录）")


class SpaceFileRenameSchema(BaseModel):
    file_id: int = Field(..., description="文件ID")
    name: str = Field(..., min_length=1, max_length=255, description="新文件名（含扩展名）")


class SpaceQuotaRequestSchema(BaseModel):
    target_mb: int = Field(..., gt=0, description="申请目标配额（MB）")
    reason: str = Field(default="", max_length=500, description="申请理由")


class SpaceQuotaReviewSchema(BaseModel):
    approve: bool = Field(..., description="是否通过")
    quota_mb: int | None = Field(default=None, gt=0, description="通过时生效配额（MB，默认取申请值）")
    note: str = Field(default="", max_length=500, description="审核备注")
