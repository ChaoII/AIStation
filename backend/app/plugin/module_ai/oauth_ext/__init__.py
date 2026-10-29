"""AI 集成开放平台 —— 阶段 3a：通用 OAuth client（平台代用户访问外部资源）。

平台充当 OAuth client，代平台用户访问外部第三方 OAuth 保护资源：
- ``model``：外部服务连接（``ai_oauth_ext_services``）+ 用户级 token（``ai_oauth_ext_tokens``）。
- ``security``：Fernet 加密封装（外部 access/refresh 可还原用于注入）。
- ``schema`` / ``service`` / ``controller``：管理面服务 CRUD + 用户面授权/刷新/撤销。

设计见 ``docs/superpowers/specs/2026-10-29-ext-oauth-client-design.md``。
"""

# 末尾导入 model，确保注册进 MappedBase.metadata（供 create_all 建表）。
from . import model  # noqa: E402,F401  # isort: skip
