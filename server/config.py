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
    poll_interval: float = float(_env("EGRESSCOPE_POLL_INTERVAL", "SSSLAB_POLL_INTERVAL", "1"))
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
    geoip_mmdb_path: str = _env("EGRESSCOPE_GEOIP_MMDB", "SSSLAB_GEOIP_MMDB")
    geoip_online_service: str = _env("EGRESSCOPE_GEOIP_SERVICE_URL", "SSSLAB_GEOIP_SERVICE_URL")
    # 默认离线库下载源：jsDelivr 托管的 wp-statistics/GeoLite2-City（.mmdb.gz，定时更新，无需 key）。
    geoip_mmdb_url: str = _env("EGRESSCOPE_GEOIP_MMDB_URL", "SSSLAB_GEOIP_MMDB_URL", "https://cdn.jsdelivr.net/npm/geolite2-city/GeoLite2-City.mmdb.gz")
    # 出口探测：mihomo 混合端口与 IP 回显地址（探测结果用于二级地区 GeoIP 判定）。
    # 0 表示从 mihomo 配置自动读取 mixed-port（部署端口各异，如 7890/9999）。
    probe_mixed_port: int = int(_env("EGRESSCOPE_PROBE_MIXED_PORT", "SSSLAB_PROBE_MIXED_PORT", "0"))
    probe_echo_url: str = _env("EGRESSCOPE_PROBE_ECHO_URL", "SSSLAB_PROBE_ECHO_URL", "https://api.ipify.org")
    # mihomo 内核二进制暂存目录（部署时挂载给 mihomo 容器）。
    mihomo_bin_dir: str = _env("EGRESSCOPE_MIHOMO_BIN_DIR", "SSSLAB_MIHOMO_BIN_DIR", str(Path("/data") / "mihomo-bin"))
