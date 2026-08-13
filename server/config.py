from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, legacy: str, default: str = "") -> str:
    """Read a current setting while preserving compatibility with legacy names."""
    return os.getenv(name, os.getenv(legacy, default))


@dataclass(frozen=True)
class Settings:
    controller_url: str = os.getenv("MIHOMO_CONTROLLER_URL", "http://127.0.0.1:9090").rstrip("/")
    controller_secret: str = os.getenv("MIHOMO_CONTROLLER_SECRET", "")
    allow_insecure_controller: bool = os.getenv("MIHOMO_ALLOW_INSECURE_CONTROLLER", "false").lower() == "true"
    config_path: Path = Path(os.getenv("MIHOMO_CONFIG_PATH", "/mihomo/config.yaml"))
    data_dir: Path = Path(_env("EGRESSCOPE_DATA_DIR", "SSSLAB_DATA_DIR", "/data"))
    static_dir: Path = Path(_env("EGRESSCOPE_STATIC_DIR", "SSSLAB_STATIC_DIR", "/app/static"))
    session_secret: str = _env("EGRESSCOPE_SESSION_SECRET", "SSSLAB_SESSION_SECRET")
    admin_username: str = _env("EGRESSCOPE_ADMIN_USERNAME", "SSSLAB_ADMIN_USERNAME", "admin")
    admin_password: str = _env("EGRESSCOPE_ADMIN_PASSWORD", "SSSLAB_ADMIN_PASSWORD")
    secure_cookie: bool = _env("EGRESSCOPE_SECURE_COOKIE", "SSSLAB_SECURE_COOKIE", "true").lower() == "true"
    retention_days: int = int(_env("EGRESSCOPE_AUDIT_RETENTION_DAYS", "SSSLAB_AUDIT_RETENTION_DAYS", "30"))
    event_retention_days: int = int(_env("EGRESSCOPE_EVENT_RETENTION_DAYS", "SSSLAB_EVENT_RETENTION_DAYS", "90"))
    poll_interval: float = float(_env("EGRESSCOPE_POLL_INTERVAL", "SSSLAB_POLL_INTERVAL", "2"))
    device_aliases_path: Path = Path(_env("EGRESSCOPE_DEVICE_ALIASES", "SSSLAB_DEVICE_ALIASES", "/data/devices.json"))
    default_rule_sets_path: Path = Path(
        _env(
            "EGRESSCOPE_DEFAULT_RULE_SETS",
            "SSSLAB_DEFAULT_RULE_SETS",
            str(Path(__file__).with_name("default-rule-sets.json")),
        )
    )
    timezone: str = _env("EGRESSCOPE_TIMEZONE", "SSSLAB_TIMEZONE", "Asia/Shanghai")
    lan_network: str = _env("EGRESSCOPE_LAN_NETWORK", "SSSLAB_LAN_NETWORK", "192.168.31.0/24")
    subscription_allowed_ports: str = _env(
        "EGRESSCOPE_SUBSCRIPTION_ALLOWED_PORTS",
        "SSSLAB_SUBSCRIPTION_ALLOWED_PORTS",
        "80,443,8080,8443",
    )
    infrastructure_source_ips: str = os.getenv(
        "EGRESSCOPE_INFRASTRUCTURE_SOURCE_IPS",
        os.getenv(
            "SSSLAB_INFRASTRUCTURE_SOURCE_IPS",
            "127.0.0.1,::1,198.18.0.1,172.17.0.2,172.18.0.3",
        ),
    )
