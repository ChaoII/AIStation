from collections.abc import Sequence

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import FaceGalleryModel
from .schema import FaceGalleryEnrollSchema


class FaceGalleryCRUD(CRUDBase[FaceGalleryModel, FaceGalleryEnrollSchema, FaceGalleryEnrollSchema]):
    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=FaceGalleryModel, auth=auth)

    async def get_by_id_crud(self, id: int) -> FaceGalleryModel | None:
        return await self.get(id=id)

    async def get_list_crud(
        self, search: dict | None = None, order_by: list[dict[str, str]] | None = None
    ) -> Sequence[FaceGalleryModel]:
        return await self.list(search=search, order_by=order_by)
