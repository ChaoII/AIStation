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
