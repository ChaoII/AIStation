"""开放面能力 handler —— 标准 CRUD 资产（app / model / prompt / provider 品类）。

复用既有 service 的 list/get/create/update/delete 方法。创建/更新身份由
:func:`create_auth` 按应用上下文决定（B 应用以 owner 身份创建、默认不公开；
平台级以服务账号创建、默认公开），并叠加可见性过滤与公开资源只读守卫；
删除须 ``confirm``。
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..registry import Capability, register
from ._common import (
    bad_request,
    create_auth,
    ensure_resource_writable,
    need_int,
    not_found,
    require_confirm,
)


def _register(category: str, defs: list[tuple]) -> None:
    """批量登记同一品类的能力。"""
    for code, perm, name, desc, schema, returns, handler, approval in defs:
        register(
            Capability(
                code=code,
                category=category,
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=code.replace(".", "_"),
                requires_approval=approval,
            )
        )


def _schema(schema_path: str, schema_name: str):
    import importlib

    return getattr(importlib.import_module(schema_path), schema_name)


async def _visible(app_ctx: Any, model_path: str, model_name: str):
    """构造某品类资源的可见性过滤条件（按 app_ctx 的 owner/平台级）。"""
    import importlib

    from app.plugin.module_ai.develop.visibility import app_visible_where

    model = getattr(importlib.import_module(model_path), model_name)
    return await app_visible_where(app_ctx, model)


def _get_existing(service, name, target, where):
    """统一取「可见范围内」资源 dict；存在性 + created_id 供只读守卫。"""
    return None


# ---------------- App ----------------
async def _app_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.apps.service import AiAppService

    where = await _visible(app_ctx, "app.plugin.module_ai.apps.model", "AiAppModel")
    items = await AiAppService.list_apps(visible_where=where)
    return {"items": items, "total": len(items)}


async def _app_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.apps.service import AiAppService

    where = await _visible(app_ctx, "app.plugin.module_ai.apps.model", "AiAppModel")
    row = await AiAppService.get_app(need_int(payload, "app_id"), visible_where=where)
    if row is None:
        raise not_found("应用")
    return row


async def _app_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.apps.service import AiAppService

    cls = _schema("app.plugin.module_ai.apps.schema", "AiAppCreateSchema")
    try:
        data = cls(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiAppService.create(data, await create_auth(app_ctx))


async def _app_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.apps.service import AiAppService

    app_id = need_int(payload, "app_id")
    where = await _visible(app_ctx, "app.plugin.module_ai.apps.model", "AiAppModel")
    existing = await AiAppService.get_app(app_id, visible_where=where)
    if existing is None:
        raise not_found("应用")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "应用")
    cls = _schema("app.plugin.module_ai.apps.schema", "AiAppUpdateSchema")
    try:
        data = cls(**{k: v for k, v in payload.items() if k != "app_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiAppService.update(app_id, data, await create_auth(app_ctx))
    if row is None:
        raise not_found("应用")
    return row


async def _app_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.apps.service import AiAppService

    app_id = need_int(payload, "app_id")
    require_confirm(payload, "删除应用")
    where = await _visible(app_ctx, "app.plugin.module_ai.apps.model", "AiAppModel")
    existing = await AiAppService.get_app(app_id, visible_where=where)
    if existing is None:
        raise not_found("应用")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "应用")
    await AiAppService.delete([app_id])
    return {"deleted": app_id}


# ---------------- Model ----------------
async def _model_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.models.service import AiModelService

    where = await _visible(app_ctx, "app.plugin.module_ai.models.model", "AiModelModel")
    items = await AiModelService.list_models(visible_where=where)
    return {"items": items, "total": len(items)}


async def _model_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.models.service import AiModelService

    where = await _visible(app_ctx, "app.plugin.module_ai.models.model", "AiModelModel")
    row = await AiModelService.get_model(need_int(payload, "model_id"), visible_where=where)
    if row is None:
        raise not_found("模型")
    return row


async def _model_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.models.service import AiModelService

    cls = _schema("app.plugin.module_ai.models.schema", "AiModelCreateSchema")
    try:
        data = cls(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiModelService.create(data, await create_auth(app_ctx))


async def _model_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.models.service import AiModelService

    model_id = need_int(payload, "model_id")
    where = await _visible(app_ctx, "app.plugin.module_ai.models.model", "AiModelModel")
    existing = await AiModelService.get_model(model_id, visible_where=where)
    if existing is None:
        raise not_found("模型")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "模型")
    cls = _schema("app.plugin.module_ai.models.schema", "AiModelUpdateSchema")
    try:
        data = cls(**{k: v for k, v in payload.items() if k != "model_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiModelService.update(model_id, data, await create_auth(app_ctx))
    if row is None:
        raise not_found("模型")
    return row


async def _model_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.models.service import AiModelService

    model_id = need_int(payload, "model_id")
    require_confirm(payload, "删除模型")
    where = await _visible(app_ctx, "app.plugin.module_ai.models.model", "AiModelModel")
    existing = await AiModelService.get_model(model_id, visible_where=where)
    if existing is None:
        raise not_found("模型")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "模型")
    await AiModelService.delete([model_id])
    return {"deleted": model_id}


# ---------------- Prompt ----------------
async def _prompt_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.prompts.service import AiPromptService

    where = await _visible(app_ctx, "app.plugin.module_ai.prompts.model", "AiPromptModel")
    items = await AiPromptService.list_prompts(visible_where=where)
    return {"items": items, "total": len(items)}


async def _prompt_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.prompts.service import AiPromptService

    where = await _visible(app_ctx, "app.plugin.module_ai.prompts.model", "AiPromptModel")
    row = await AiPromptService.get_prompt(need_int(payload, "prompt_id"), visible_where=where)
    if row is None:
        raise not_found("提示词")
    return row


async def _prompt_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.prompts.service import AiPromptService

    cls = _schema("app.plugin.module_ai.prompts.schema", "AiPromptCreateSchema")
    try:
        data = cls(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiPromptService.create(data, await create_auth(app_ctx))


async def _prompt_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.prompts.service import AiPromptService

    prompt_id = need_int(payload, "prompt_id")
    where = await _visible(app_ctx, "app.plugin.module_ai.prompts.model", "AiPromptModel")
    existing = await AiPromptService.get_prompt(prompt_id, visible_where=where)
    if existing is None:
        raise not_found("提示词")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "提示词")
    cls = _schema("app.plugin.module_ai.prompts.schema", "AiPromptUpdateSchema")
    try:
        data = cls(**{k: v for k, v in payload.items() if k != "prompt_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiPromptService.update(prompt_id, data, await create_auth(app_ctx))
    if row is None:
        raise not_found("提示词")
    return row


async def _prompt_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.prompts.service import AiPromptService

    prompt_id = need_int(payload, "prompt_id")
    require_confirm(payload, "删除提示词")
    where = await _visible(app_ctx, "app.plugin.module_ai.prompts.model", "AiPromptModel")
    existing = await AiPromptService.get_prompt(prompt_id, visible_where=where)
    if existing is None:
        raise not_found("提示词")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "提示词")
    await AiPromptService.delete([prompt_id])
    return {"deleted": prompt_id}


# ---------------- Provider ----------------
async def _provider_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.providers.service import AiProviderService

    where = await _visible(app_ctx, "app.plugin.module_ai.providers.model", "AiProviderModel")
    items = await AiProviderService.list_providers(visible_where=where)
    return {"items": items, "total": len(items)}


async def _provider_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.providers.service import AiProviderService

    where = await _visible(app_ctx, "app.plugin.module_ai.providers.model", "AiProviderModel")
    row = await AiProviderService.get_provider(need_int(payload, "provider_id"), visible_where=where)
    if row is None:
        raise not_found("供应商")
    return row


async def _provider_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.providers.service import AiProviderService

    cls = _schema("app.plugin.module_ai.providers.schema", "AiProviderCreateSchema")
    try:
        data = cls(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiProviderService.create(data, await create_auth(app_ctx))


async def _provider_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.providers.service import AiProviderService

    provider_id = need_int(payload, "provider_id")
    where = await _visible(app_ctx, "app.plugin.module_ai.providers.model", "AiProviderModel")
    existing = await AiProviderService.get_provider(provider_id, visible_where=where)
    if existing is None:
        raise not_found("供应商")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "供应商")
    cls = _schema("app.plugin.module_ai.providers.schema", "AiProviderUpdateSchema")
    try:
        data = cls(**{k: v for k, v in payload.items() if k != "provider_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiProviderService.update(provider_id, data, await create_auth(app_ctx))
    if row is None:
        raise not_found("供应商")
    return row


async def _provider_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.providers.service import AiProviderService

    provider_id = need_int(payload, "provider_id")
    require_confirm(payload, "删除供应商")
    where = await _visible(app_ctx, "app.plugin.module_ai.providers.model", "AiProviderModel")
    existing = await AiProviderService.get_provider(provider_id, visible_where=where)
    if existing is None:
        raise not_found("供应商")
    ensure_resource_writable(app_ctx, existing.get("created_id"), "供应商")
    await AiProviderService.delete([provider_id])
    return {"deleted": provider_id}


def register_catalog_capabilities() -> None:
    """注册 app / model / prompt / provider 品类能力。"""
    _register(
        "app",
        [
            ("app.list", "integration:app:query", "应用列表", "列出全部 AI 应用", {}, "items: array, total: int", _app_list, False),
            ("app.get", "integration:app:query", "应用详情", "按 ID 查询应用", {"type": "object", "properties": {"app_id": {"type": "integer"}}, "required": ["app_id"]}, "应用对象", _app_get, False),
            ("app.create", "integration:app:create", "创建应用", "创建一个 AI 应用", {"type": "object", "properties": {}, "additionalProperties": True}, "应用对象（含 id）", _app_create, False),
            ("app.update", "integration:app:update", "更新应用", "更新 AI 应用", {"type": "object", "properties": {"app_id": {"type": "integer"}}, "required": ["app_id"]}, "更新后的应用对象", _app_update, False),
            ("app.delete", "integration:app:delete", "删除应用", "删除 AI 应用（须 confirm=true）", {"type": "object", "properties": {"app_id": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["app_id", "confirm"]}, "deleted: int", _app_delete, True),
        ],
    )
    _register(
        "model",
        [
            ("model.list", "integration:model:query", "模型列表", "列出全部模型配置", {}, "items: array, total: int", _model_list, False),
            ("model.get", "integration:model:query", "模型详情", "按 ID 查询模型配置", {"type": "object", "properties": {"model_id": {"type": "integer"}}, "required": ["model_id"]}, "模型对象", _model_get, False),
            ("model.create", "integration:model:create", "创建模型", "创建一个模型配置", {"type": "object", "properties": {}, "additionalProperties": True}, "模型对象（含 id）", _model_create, False),
            ("model.update", "integration:model:update", "更新模型", "更新模型配置", {"type": "object", "properties": {"model_id": {"type": "integer"}}, "required": ["model_id"]}, "更新后的模型对象", _model_update, False),
            ("model.delete", "integration:model:delete", "删除模型", "删除模型配置（须 confirm=true）", {"type": "object", "properties": {"model_id": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["model_id", "confirm"]}, "deleted: int", _model_delete, True),
        ],
    )
    _register(
        "prompt",
        [
            ("prompt.list", "integration:prompt:query", "提示词列表", "列出全部提示词", {}, "items: array, total: int", _prompt_list, False),
            ("prompt.get", "integration:prompt:query", "提示词详情", "按 ID 查询提示词", {"type": "object", "properties": {"prompt_id": {"type": "integer"}}, "required": ["prompt_id"]}, "提示词对象", _prompt_get, False),
            ("prompt.create", "integration:prompt:create", "创建提示词", "创建一个提示词", {"type": "object", "properties": {}, "additionalProperties": True}, "提示词对象（含 id）", _prompt_create, False),
            ("prompt.update", "integration:prompt:update", "更新提示词", "更新提示词", {"type": "object", "properties": {"prompt_id": {"type": "integer"}}, "required": ["prompt_id"]}, "更新后的提示词对象", _prompt_update, False),
            ("prompt.delete", "integration:prompt:delete", "删除提示词", "删除提示词（须 confirm=true）", {"type": "object", "properties": {"prompt_id": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["prompt_id", "confirm"]}, "deleted: int", _prompt_delete, True),
        ],
    )
    _register(
        "provider",
        [
            ("provider.list", "integration:provider:query", "供应商列表", "列出全部模型供应商", {}, "items: array, total: int", _provider_list, False),
            ("provider.get", "integration:provider:query", "供应商详情", "按 ID 查询模型供应商", {"type": "object", "properties": {"provider_id": {"type": "integer"}}, "required": ["provider_id"]}, "供应商对象", _provider_get, False),
            ("provider.create", "integration:provider:create", "创建供应商", "创建一个模型供应商", {"type": "object", "properties": {}, "additionalProperties": True}, "供应商对象（含 id）", _provider_create, False),
            ("provider.update", "integration:provider:update", "更新供应商", "更新模型供应商", {"type": "object", "properties": {"provider_id": {"type": "integer"}}, "required": ["provider_id"]}, "更新后的供应商对象", _provider_update, False),
            ("provider.delete", "integration:provider:delete", "删除供应商", "删除模型供应商（须 confirm=true）", {"type": "object", "properties": {"provider_id": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["provider_id", "confirm"]}, "deleted: int", _provider_delete, True),
        ],
    )
