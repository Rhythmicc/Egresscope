"""Read-only presentation of the live core's explicit proxy listeners."""

import ipaddress
import socket
from pathlib import Path
from typing import Any

import yaml


def proxy_accounts(config: dict[str, Any], reveal: bool = False) -> list[dict[str, Any]]:
    accounts = []
    for value in config.get("authentication") or []:
        if not isinstance(value, str):
            continue
        username, separator, password = value.partition(":")
        account = {"id": len(accounts), "username": username}
        if reveal:
            if not separator:
                raise ValueError("控制器未返回代理密码")
            account["password"] = password
        accounts.append(account)
    return accounts


def proxy_credentials(config: dict[str, Any], paths: list[Path]) -> list[dict[str, Any]]:
    accounts = proxy_accounts(config)
    if not accounts:
        return []
    passwords = {value.partition(":")[0]: value.partition(":")[2] for value in config.get("authentication", []) if isinstance(value, str) and ":" in value}
    for path in paths:
        if all(account["username"] in passwords for account in accounts):
            break
        try:
            source = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(source, dict):
            continue
        for value in source.get("authentication") or []:
            if isinstance(value, str) and ":" in value:
                username, _, password = value.partition(":")
                passwords.setdefault(username, password)
    if any(account["username"] not in passwords for account in accounts):
        raise ValueError("已应用配置中找不到当前代理账户的密码")
    return [{**account, "password": passwords[account["username"]]} for account in accounts]


def proxy_host(config: dict[str, Any], lan_network: str) -> str | None:
    binding = str(config.get("bind-address") or "*")
    if binding not in {"*", "0.0.0.0", "::", "[::]"}:
        return binding.strip("[]")
    if not config.get("allow-lan", False):
        return "127.0.0.1"
    try:
        network = ipaddress.ip_network(lan_network, strict=False)
        family = socket.AF_INET6 if network.version == 6 else socket.AF_INET
        # UDP connect chooses a local interface without sending any packets.
        with socket.socket(family, socket.SOCK_DGRAM) as probe:
            probe.connect((str(network.network_address + 1), 9))
            address = ipaddress.ip_address(probe.getsockname()[0])
        if not address.is_loopback and not address.is_unspecified:
            return str(address)
    except (OSError, ValueError):
        pass
    return None


def proxy_access(config: dict[str, Any], lan_network: str) -> dict[str, Any]:
    host = proxy_host(config, lan_network)
    listeners = []
    for key, label in (("mixed-port", "HTTP / SOCKS5"), ("port", "HTTP"), ("socks-port", "SOCKS5")):
        port = config.get(key)
        if isinstance(port, int) and not isinstance(port, bool) and 0 < port <= 65535:
            address = f"[{host}]:{port}" if host and ":" in host else f"{host}:{port}" if host else None
            listeners.append({"id": key, "protocol": label, "host": host, "port": port, "address": address})
    return {
        "listeners": listeners,
        "allowLan": bool(config.get("allow-lan", False)),
        "bindAddress": str(config.get("bind-address") or "*"),
        "accounts": proxy_accounts(config),
        "skipAuthPrefixes": config.get("skip-auth-prefixes") or [],
        "lanAllowedIPs": config.get("lan-allowed-ips") or [],
        "lanDisallowedIPs": config.get("lan-disallowed-ips") or [],
    }
