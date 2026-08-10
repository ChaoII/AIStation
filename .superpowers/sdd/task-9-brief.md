### Task 9: 部署功能修正 — 端口竞态 + 容器存活探活 + 回收

**Files:**
- Modify: `backend/app/plugin/module_train/deploy_executor.py`
- Modify: `backend/app/plugin/module_train/service.py`
- Test: `backend/tests/test_deploy_fixes.py`（新建）

**Interfaces:**
- Consumes: `TaskExecutor` 基类（可选复用）
- Produces: `_find_available_port` 支持占位预留、`start_deployment` 幂等、运行中容器健康探活

- [ ] **Step 1: 写失败测试 — 端口预留**

`backend/tests/test_deploy_fixes.py`:

```python
"""部署修复测试。"""


def test_find_available_port_bounds():
    from app.plugin.module_train.deploy_executor import _find_available_port
    p = _find_available_port(9100, 9100)
    assert p == 9100
```

- [ ] **Step 2: 运行确认通过**

Run: `cd backend && uv run pytest tests/test_deploy_fixes.py -v`
Expected: PASS

- [ ] **Step 3: 端口占用竞态修复**

`deploy_executor.py` 中 `_execute_deployment` 修改：选定端口后立即写入 DB `host_port` 并持有"预留锁"，再启动容器；失败回滚端口。将 `_find_available_port` 改为同时检查 Docker 已发布端口：

```python
def _find_available_port(start: int = 9001, end: int = 9999) -> int:
    import socket
    import docker
    client = docker.from_env()
    used = set()
    try:
        for c in client.containers.list(all=True):
            for _, bindings in (c.attrs.get("HostConfig", {}).get("PortBindings") or {}).items():
                for b in bindings:
                    used.add(int(b["HostPort"]))
    except Exception:
        pass
    for port in range(start, end + 1):
        if port in used:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise Exception("no available port found")
```

- [ ] **Step 4: 探活与回收**

启动后 `_execute_deployment` 中等待 server.py 健康检查（最多 60s），通过 `requests.get(f"{api_url}/health")` 轮询；运行中容器用 `container.status` 轮询，异常退出标记 failed 并移除。`stop_deployment` 已存在；增加 `recover_orphan_deploys()` 在启动时把 `running` 状态但无容器的部署标记 `failed`。

- [ ] **Step 5: 运行测试**

Run: `cd backend && uv run pytest tests/test_deploy_fixes.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/deploy_executor.py backend/app/plugin/module_train/service.py backend/tests/test_deploy_fixes.py
git commit -m "fix(train): deploy port reservation, health probe, orphan recovery"
```

---


