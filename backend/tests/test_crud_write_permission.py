"""CRUDBase 写路径(delete/set/restore/clear)数据权限过滤测试。

F1 修复验证：写操作必须与读路径一致地应用数据范围权限，防止越权
删除/批量修改/恢复他人数据。用独立内存 SQLite + 受限用户/超管对比。
"""
import asyncio
from datetime import datetime
from types import SimpleNamespace as SN

from sqlalchemy import ForeignKey, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.common.enums import PermissionFilterStrategy
from app.core.base_crud import CRUDBase


class _Base(DeclarativeBase):
    pass


class ItemModel(_Base):
    """测试模型：带 created_id 与数据范围策略(默认 DATA_SCOPE)。"""

    __tablename__ = "test_item"
    __permission_strategy__ = PermissionFilterStrategy.DATA_SCOPE

    id: Mapped[int] = mapped_column(primary_key=True)
    created_id: Mapped[int | None] = mapped_column(default=None)
    name: Mapped[str] = mapped_column(default="")
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_time: Mapped[datetime | None] = mapped_column(default=None)
    deleted_id: Mapped[int | None] = mapped_column(default=None)


class TreeModel(_Base):
    """自引用树模型：用于 tree_list 子节点权限剪枝(F5)测试。"""

    __tablename__ = "test_tree"
    __permission_strategy__ = PermissionFilterStrategy.DATA_SCOPE

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_tree.id"), default=None
    )
    created_id: Mapped[int | None] = mapped_column(default=None)
    name: Mapped[str] = mapped_column(default="")
    children: Mapped[list["TreeModel"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        foreign_keys="TreeModel.parent_id",
    )
    parent: Mapped["TreeModel | None"] = relationship(
        back_populates="children",
        remote_side="TreeModel.id",
        foreign_keys="TreeModel.parent_id",
    )


def _auth(db, uid, is_superuser=False):
    """构造测试用认证上下文（仅提供权限过滤所需字段）。"""
    return SN(
        db=db,
        user=SN(id=uid, is_superuser=is_superuser, dept_id=None, roles=[]),
        check_data_scope=True,
    )


def test_crud_write_respects_data_scope():
    """非超管不能删除/批改他人数据；可操作自己数据；超管不受限。"""

    async def inner():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as session:
            session.add_all(
                [
                    ItemModel(id=1, created_id=100, name="a", is_deleted=False),
                    ItemModel(id=2, created_id=200, name="b", is_deleted=False),
                ]
            )
            await session.commit()

            # 用户A(100)：无角色、非超管、检查数据权限 → 仅本人数据
            auth = _auth(session, 100)
            crud = CRUDBase(ItemModel, auth)

            # 删除他人数据(200 创建)：不应生效
            await crud.delete([2])
            await session.flush()
            row2 = (
                await session.execute(select(ItemModel).where(ItemModel.id == 2))
            ).scalar_one()
            assert row2.is_deleted is False, "越权删除他人数据应不生效"

            # 单行删除(200 创建)：同样不生效
            await crud.delete([2, 1])
            await session.flush()
            row2b = (
                await session.execute(select(ItemModel).where(ItemModel.id == 2))
            ).scalar_one()
            assert row2b.is_deleted is False, "越权删除(单行)应不生效"
            row1b = (
                await session.execute(select(ItemModel).where(ItemModel.id == 1))
            ).scalar_one()
            assert row1b.is_deleted is True, "删除自己的数据应生效"

            # set 批量修改：越权修改他人数据不生效
            await crud.set([2], name="hack")
            await session.flush()
            row2c = (
                await session.execute(select(ItemModel).where(ItemModel.id == 2))
            ).scalar_one()
            assert row2c.name == "b", "越权批量修改他人数据应不生效"

            # restore 恢复：他人已删除数据不生效（这里先由超管删除 id=2 再验证）
            await session.flush()
            super_auth = _auth(session, 1, is_superuser=True)
            super_crud = CRUDBase(ItemModel, super_auth)
            await super_crud.delete([2])
            await super_crud.restore([2])
            await session.flush()
            row2d = (
                await session.execute(select(ItemModel).where(ItemModel.id == 2))
            ).scalar_one()
            assert row2d.is_deleted is False, "超管恢复自身范围内数据应生效"

            # 超管不受数据范围限制：可改他人数据
            await super_crud.set([2], name="ok")
            await session.flush()
            row2e = (
                await session.execute(select(ItemModel).where(ItemModel.id == 2))
            ).scalar_one()
            assert row2e.name == "ok", "超管不受数据范围限制"
        await engine.dispose()

    asyncio.run(inner())


def test_tree_list_prunes_unauthorized_children():
    """tree_list 的子树经 selectinload 加载，子节点须按数据权限剪枝(F5)。"""

    async def inner():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as session:
            # 根节点(1)由用户A(100)创建；子节点(2)由他人(200)创建
            root = TreeModel(id=1, created_id=100, name="root")
            child = TreeModel(id=2, parent_id=1, created_id=200, name="child")
            session.add_all([root, child])
            await session.commit()

            # 无权限限制时（超管）返回完整树（扁平列表：root + child 都在顶层）
            super_auth = _auth(session, 1, is_superuser=True)
            super_crud = CRUDBase(TreeModel, super_auth)
            full = await super_crud.tree_list()
            assert len(full) == 2, "超管应看到全部节点(扁平列表)"
            assert len(full[0].children) == 1, "超管应看到完整子树"

            # 用户A(100)：仅本人创建的节点有权限 → 子树中他人子节点被剪掉
            auth = _auth(session, 100)
            crud = CRUDBase(TreeModel, auth)
            pruned = await crud.tree_list()
            assert len(pruned) == 1, "根节点属于用户A，应保留"
            assert len(pruned[0].children) == 0, "他人创建的子节点应被剪枝"

        await engine.dispose()

    asyncio.run(inner())
