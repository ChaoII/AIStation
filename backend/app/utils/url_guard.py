"""出站 HTTP URL 安全校验（SSRF 防护，审计 #12）。

用于边缘控制面 ``control_url`` 等由用户/设备写入、随后由后端主动请求的地址。
设计取舍（向后兼容优先）：

- **一律拒绝**：非 ``http``/``https`` 协议（``file://``/``gopher://``/``ftp://``/``data:``
  等）、云元数据地址与主机名、链路本地（169.254.0.0/16、fe80::/10）、
  未指定/保留/组播地址；
- **默认放行内网/环回**：边缘 Agent 合法部署在局域网或本机（``127.0.0.1:19090``、
  ``192.168.x.x``），默认放行以保持可用；需要更严时可开启 ``block_private=True``
  严格模式拒绝环回/私有地址；
- **主机白名单**：``allowed_hosts`` 非空时仅放行其中主机；
- **DNS 重绑定**：开启 ``resolve=True`` 时解析主机名并逐个校验解析出的 IP
  （覆盖“域名解析到元数据/链路本地”的情况）；受限于 httpx 无法固定解析结果，
  解析与请求之间仍存在重绑定窗口，属已知残余风险，可用严格模式或白名单收紧。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

# 允许的协议：仅 HTTP(S)
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

# 云元数据服务固定 IP（AWS/GCP/Azure/Aliyun 等）
_METADATA_IPS: frozenset[str] = frozenset(
    {
        "169.254.169.254",  # AWS/GCP/Azure IMDS
        "169.254.170.2",  # AWS ECS 任务元数据
        "100.100.100.200",  # 阿里云
        "fd00:ec2::254",  # AWS IPv6 IMDS
    }
)

# 云元数据服务主机名（解析前后都拒绝）
_METADATA_HOSTS: frozenset[str] = frozenset(
    {
        "metadata.google.internal",
        "metadata.goog",
        "metadata",
        "instance-data",
        "instance-data.ec2.internal",
    }
)


class UnsafeUrlError(ValueError):
    """URL 不满足出站安全策略。"""


def _blocked_ip_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, block_private: bool) -> str | None:
    """返回 IP 被拒绝的原因；允许时返回 ``None``。"""
    if ip.is_link_local:
        return "链路本地地址"
    if ip.is_multicast:
        return "组播地址"
    if ip.is_unspecified or ip.is_reserved:
        return "未指定/保留地址"
    if (ip.is_loopback or ip.is_private) and block_private:
        return "环回/私有地址（严格模式）"
    return None


def _check_ip_literal(host: str, *, block_private: bool) -> None:
    """主机为 IP 字面量时按策略校验。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if str(ip) in _METADATA_IPS:
        raise UnsafeUrlError(f"禁止访问云元数据地址：{host}")
    reason = _blocked_ip_reason(ip, block_private=block_private)
    if reason:
        raise UnsafeUrlError(f"禁止访问 {reason}：{host}")


def validate_outbound_url(
    url: str,
    *,
    block_private: bool = False,
    allowed_hosts: set[str] | frozenset[str] | None = None,
    resolve: bool = False,
) -> str:
    """校验出站 URL，通过时原样返回；不通过抛 :class:`UnsafeUrlError`。

    参数:
    - url (str): 待校验地址（如边缘控制面基址）。
    - block_private (bool): 严格模式，拒绝环回/私有地址（默认 False，兼容局域网部署）。
    - allowed_hosts (set[str] | None): 非空时仅放行其中主机（小写、去尾点）。
    - resolve (bool): 是否解析主机名并校验解析出的 IP（防御“域名指向元数据地址”）。

    异常:
    - UnsafeUrlError: 协议、主机或解析结果不满足安全策略。
    """
    raw = (url or "").strip()
    if not raw:
        raise UnsafeUrlError("URL 不能为空")

    parts = urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"仅允许 http/https 协议，实际为 {parts.scheme!r}")

    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise UnsafeUrlError("URL 缺少主机名")

    if allowed_hosts:
        allowed = {h.strip().lower().rstrip(".") for h in allowed_hosts}
        if host not in allowed:
            raise UnsafeUrlError(f"主机不在允许白名单内：{host}")

    if host in _METADATA_HOSTS:
        raise UnsafeUrlError(f"禁止访问云元数据主机：{host}")
    _check_ip_literal(host, block_private=block_private)

    if resolve and not _looks_like_ip(host):
        try:
            infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except OSError:
            # 解析失败不在此处阻断：交由实际请求报错，避免 DNS 暂时不可用时误拒
            return raw
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
            except ValueError:
                continue
            if str(ip) in _METADATA_IPS:
                raise UnsafeUrlError(f"主机 {host} 解析到云元数据地址：{addr}")
            reason = _blocked_ip_reason(ip, block_private=block_private)
            if reason:
                raise UnsafeUrlError(f"主机 {host} 解析到 {reason}：{addr}")
    return raw


def _looks_like_ip(host: str) -> bool:
    """主机是否可解析为 IP 字面量。"""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
