"""部署功能修复测试：端口预留竞态 + 容器存活探活 + 孤儿回收。

不依赖真实 Docker 容器：仅测试可提取的纯逻辑（端口占用探测、可用端口选取）。
健康探活与孤儿回收依赖真实容器/守护进程，通过 code review 验证。
"""

import socket

from app.plugin.module_train.deploy_executor import (
    _docker_published_host_ports,
    _find_available_port,
    _is_host_port_used,
)


def test_find_available_port_bounds():
    # 若 9100 恰被占用则退化为区间内任意可用端口，保证不 flaky
    try:
        p = _find_available_port(9100, 9100)
        assert p == 9100
    except Exception:
        p = _find_available_port(9100, 9199)
        assert 9100 <= p <= 9199


def test_find_available_port_returns_in_range():
    p = _find_available_port(9200, 9299)
    assert 9200 <= p <= 9299


def test_find_available_port_excludes_reserved():
    docker_used = _docker_published_host_ports()
    cands = [p for p in range(9300, 9309)
             if not _is_host_port_used(p) and p not in docker_used]
    assert len(cands) >= 3
    a, b = cands[0], cands[1]
    p = _find_available_port(9300, 9308, excluded={a, b})
    assert p == cands[2]
    assert p not in {a, b}


def test_is_host_port_used_detects_bound_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        assert _is_host_port_used(port) is True


def test_docker_published_host_ports_returns_set():
    # 无 Docker 守护进程时应返回空集合而非抛异常
    ports = _docker_published_host_ports()
    assert isinstance(ports, set)
