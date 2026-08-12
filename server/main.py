from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
import httpcore
import websockets
import yaml
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import connect as connect_database
from .database import migrate as migrate_database


logger = logging.getLogger("egresscope")


def _env(name: str, legacy: str, default: str = "") -> str:
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
    default_rule_sets_path: Path = Path(_env("EGRESSCOPE_DEFAULT_RULE_SETS", "SSSLAB_DEFAULT_RULE_SETS", str(Path(__file__).with_name("default-rule-sets.json"))))
    timezone: str = _env("EGRESSCOPE_TIMEZONE", "SSSLAB_TIMEZONE", "Asia/Shanghai")
    lan_network: str = _env("EGRESSCOPE_LAN_NETWORK", "SSSLAB_LAN_NETWORK", "192.168.31.0/24")
    subscription_allowed_ports: str = _env("EGRESSCOPE_SUBSCRIPTION_ALLOWED_PORTS", "SSSLAB_SUBSCRIPTION_ALLOWED_PORTS", "80,443,8080,8443")
    infrastructure_source_ips: str = os.getenv(
        "EGRESSCOPE_INFRASTRUCTURE_SOURCE_IPS",
        os.getenv(
            "SSSLAB_INFRASTRUCTURE_SOURCE_IPS",
        "127.0.0.1,::1,198.18.0.1,172.17.0.2,172.18.0.3",
        ),
    )


settings = Settings()
DISPLAY_TIMEZONE = ZoneInfo(settings.timezone)
INFRASTRUCTURE_SOURCE_IPS = frozenset(
    address.strip() for address in settings.infrastructure_source_ips.split(",") if address.strip()
)
MIHOMO_FAKE_IP_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("fc00::/7"),
)
DASHBOARD_TIMELINE_RANGES: dict[str, tuple[int, int, str]] = {
    "live": (15 * 60, 10, "%H:%M:%S"),
    "1h": (60 * 60, 60, "%H:%M"),
    "6h": (6 * 60 * 60, 5 * 60, "%H:%M"),
    "24h": (24 * 60 * 60, 15 * 60, "%H:%M"),
    "7d": (7 * 24 * 60 * 60, 60 * 60, "%m-%d %H:%M"),
    "14d": (14 * 24 * 60 * 60, 2 * 60 * 60, "%m-%d %H:%M"),
    "month": (31 * 24 * 60 * 60, 24 * 60 * 60, "%m-%d"),
}
CONNECTION_HISTORY_RANGES = {
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
    "30d": 30 * 24 * 60 * 60,
}


def _is_infrastructure_source(address: str) -> bool:
    """Return whether an observed source belongs to mihomo/Docker, not an end device."""
    return address in INFRASTRUCTURE_SOURCE_IPS


def _display_datetime(timestamp: int | float | None = None) -> datetime:
    return datetime.now(DISPLAY_TIMEZONE) if timestamp is None else datetime.fromtimestamp(timestamp, DISPLAY_TIMEZONE)


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    legacy_path = settings.data_dir / "ssslab-proxy.db"
    database_path = legacy_path if legacy_path.exists() else settings.data_dir / "egresscope.db"
    connection = connect_database(database_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _record_audit(
    actor_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    result: str = "ok",
    detail: dict[str, Any] | None = None,
) -> None:
    with _db() as connection:
        connection.execute(
            "INSERT INTO audit_log(actor_id,action,resource_type,resource_id,result,detail_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (actor_id, action, resource_type, resource_id, result, json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")), int(time.time())),
        )


def _record_gateway_event(
    level: str,
    category: str,
    title: str,
    message: str = "",
    detail: dict[str, Any] | None = None,
    event_key: str | None = None,
) -> None:
    normalized_level = level if level in {"info", "warning", "error"} else "info"
    now = int(time.time())
    with _db() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO gateway_events(event_key,level,category,title,message,detail_json,created_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                event_key,
                normalized_level,
                category[:40],
                title[:120],
                message[:1200],
                json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
                now,
            ),
        )
        connection.execute(
            "DELETE FROM gateway_events WHERE created_at < ?",
            (now - max(1, settings.event_retention_days) * 86400,),
        )


def _calendar_start(period: str, timestamp: int | float | None = None) -> int:
    current = _display_datetime(timestamp)
    if period == "day":
        start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "year":
        start = current.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"unsupported calendar period: {period}")
    return int(start.timestamp())


def _range_window(range_key: str, now: int | None = None) -> tuple[int, int, int, str]:
    current = int(time.time()) if now is None else now
    seconds, bucket_seconds, time_format = DASHBOARD_TIMELINE_RANGES[range_key]
    start = _calendar_start("month", current) if range_key == "month" else current - seconds
    return start, max(1, current - start), bucket_seconds, time_format


def _traffic_timeline(rows: list[Any], time_format: str) -> list[dict[str, Any]]:
    """Return consumed bytes per bucket; never turn historical traffic into an average rate."""
    return [
        {
            "time": _display_datetime(int(row["bucket"])).strftime(time_format),
            "up": int(row["up"] or 0),
            "down": int(row["down"] or 0),
        }
        for row in rows
    ]


def _traffic_summary(rows: list[Any]) -> dict[str, int]:
    up = sum(int(row["up"] or 0) for row in rows)
    down = sum(int(row["down"] or 0) for row in rows)
    return {"up": up, "down": down, "traffic": up + down}


def _exclusive_exit_usage(rows: list[Any], expected_total: int, group_names: set[str]) -> list[dict[str, Any]]:
    """Collapse each complete path into one mutually exclusive leaf exit mode."""
    usage: dict[str, int] = defaultdict(int)
    for row in rows:
        raw_chain = str(row["chain"] or "")
        try:
            parsed = json.loads(raw_chain)
            chain = [str(item) for item in parsed] if isinstance(parsed, list) else [raw_chain]
        except (json.JSONDecodeError, TypeError):
            chain = [raw_chain]
        cleaned = [_clean_name(item) for item in chain if item]
        if "DIRECT" in cleaned:
            exit_mode = "DIRECT"
        else:
            policy_path = [item for item in cleaned if item in group_names]
            exit_mode = policy_path[-1] if policy_path else (cleaned[-1] if cleaned else "未归类")
        usage[exit_mode] += int(row["total"] or 0)

    attributed_total = sum(usage.values())
    if expected_total > attributed_total:
        usage["历史未细分"] += expected_total - attributed_total
    denominator = sum(usage.values()) or 1
    return [
        {"name": name, "value": value, "percent": round(value / denominator * 100, 1)}
        for name, value in sorted(usage.items(), key=lambda item: item[1], reverse=True)
        if value > 0
    ]


def _backfill_daily_rollups(connection: sqlite3.Connection) -> None:
    """Repair recent rollups from raw rows without replacing the oldest partial-retention day."""
    offset = int(_display_datetime().utcoffset().total_seconds())
    first_full_day = _calendar_start("day", int(time.time()) - settings.retention_days * 86400) + 86400
    connection.execute(
        """
        INSERT OR REPLACE INTO traffic_daily_rollups(day_start,device,chain,up_bytes,down_bytes,active_peak,samples)
        SELECT ((ts + ?) / 86400) * 86400 - ?, device, chain,
               SUM(up_bytes), SUM(down_bytes), MAX(active), COUNT(*)
        FROM traffic_samples WHERE ts >= ?
        GROUP BY ((ts + ?) / 86400), device, chain
        """,
        (offset, offset, first_full_day, offset),
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO traffic_detail_daily_rollups(day_start,device,service,host,exit_mode,up_bytes,down_bytes,connections)
        SELECT ((ts + ?) / 86400) * 86400 - ?, device, service, host, exit_mode,
               SUM(up_bytes), SUM(down_bytes), SUM(connections)
        FROM traffic_detail_samples WHERE ts >= ?
        GROUP BY ((ts + ?) / 86400), device, service, host, exit_mode
        """,
        (offset, offset, first_full_day, offset),
    )


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 420_000)
    return f"pbkdf2_sha256$420000${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def _password_matches(password: str, encoded: str) -> bool:
    try:
        _, rounds, salt, expected = encoded.split("$", 3)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt), int(rounds))
        return hmac.compare_digest(base64.urlsafe_b64encode(digest).decode(), expected)
    except (ValueError, TypeError):
        return False


class AuthStore:
    def __init__(self) -> None:
        self.session_secret = settings.session_secret

    def initialize(self) -> None:
        if len(self.session_secret) < 32:
            raise RuntimeError("EGRESSCOPE_SESSION_SECRET is required and must contain at least 32 characters")
        with _db() as connection:
            migrate_database(connection)
            database_path = Path(connection.execute("PRAGMA database_list").fetchone()[2])
            os.chmod(database_path, 0o600)
            _backfill_daily_rollups(connection)
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                if not settings.admin_password:
                    raise RuntimeError("EGRESSCOPE_ADMIN_PASSWORD is required for the initial administrator")
                connection.execute(
                    "INSERT INTO users(username,password_hash,role,allowed_devices,created_at) VALUES(?,?,?,?,?)",
                    (settings.admin_username, _password_hash(settings.admin_password), "admin", "[]", int(time.time())),
                )

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with _db() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not _password_matches(password, row["password_hash"]):
            return None
        return self.public_user(row)

    def list_users(self) -> list[dict[str, Any]]:
        with _db() as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY created_at, id").fetchall()
        return [self.public_user(row) for row in rows]

    def create_user(self, username: str, password: str, role: str, allowed_devices: list[str]) -> dict[str, Any]:
        username = username.strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", username):
            raise ValueError("用户名只能包含字母、数字、点、下划线和连字符，长度 3–64 位")
        if len(password) < 12:
            raise ValueError("密码至少需要 12 个字符")
        if role not in {"admin", "viewer"}:
            raise ValueError("角色必须是 admin 或 viewer")
        allowed = sorted({item.strip() for item in allowed_devices if item.strip()})
        try:
            with _db() as connection:
                cursor = connection.execute(
                    "INSERT INTO users(username,password_hash,role,allowed_devices,created_at) VALUES(?,?,?,?,?)",
                    (username, _password_hash(password), role, json.dumps(allowed), int(time.time())),
                )
                row = connection.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("用户名已存在") from exc
        return self.public_user(row)

    def update_user(self, user_id: int, role: str | None, allowed_devices: list[str] | None, password: str | None) -> dict[str, Any]:
        updates: list[str] = []
        values: list[Any] = []
        if role is not None:
            if role not in {"admin", "viewer"}:
                raise ValueError("角色必须是 admin 或 viewer")
            updates.append("role = ?")
            values.append(role)
        if allowed_devices is not None:
            updates.append("allowed_devices = ?")
            values.append(json.dumps(sorted({item.strip() for item in allowed_devices if item.strip()})))
        if password is not None:
            if len(password) < 12:
                raise ValueError("密码至少需要 12 个字符")
            updates.append("password_hash = ?")
            values.append(_password_hash(password))
            updates.append("session_version = session_version + 1")
        if not updates:
            raise ValueError("没有需要更新的字段")
        values.append(user_id)
        with _db() as connection:
            result = connection.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            if result.rowcount != 1:
                raise ValueError("用户不存在")
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self.public_user(row)

    @staticmethod
    def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "allowedDevices": json.loads(row["allowed_devices"] or "[]"),
        }

    def token(self, user: dict[str, Any]) -> str:
        with _db() as connection:
            row = connection.execute("SELECT session_version FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row is None:
            raise ValueError("user no longer exists")
        payload = json.dumps(
            {"sub": user["id"], "ver": int(row["session_version"]), "exp": int(time.time()) + 12 * 3600},
            separators=(",", ":"),
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self.session_secret.encode(), encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def verify(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(self.session_secret.encode(), encoded.encode(), hashlib.sha256).digest()
            actual = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
            if not hmac.compare_digest(expected, actual):
                return None
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if payload["exp"] < time.time():
                return None
            with _db() as connection:
                row = connection.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
            if not row or int(payload.get("ver", 0)) != int(row["session_version"]):
                return None
            return self.public_user(row)
        except (ValueError, KeyError, json.JSONDecodeError):
            return None


auth = AuthStore()


class LoginRateLimiter:
    """Small in-process limiter for the single-worker appliance deployment."""

    def __init__(self, attempts: int = 8, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            failures = self._failures[key]
            while failures and failures[0] <= now - self.window_seconds:
                failures.popleft()
            if len(failures) < self.attempts:
                return 0
            return max(1, round(self.window_seconds - (now - failures[0])))

    def failure(self, key: str) -> None:
        with self._lock:
            self._failures[key].append(time.monotonic())

    def success(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = LoginRateLimiter()


class MihomoClient:
    def __init__(self) -> None:
        self.client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        headers = {"Authorization": f"Bearer {settings.controller_secret}"} if settings.controller_secret else {}
        self.client = httpx.AsyncClient(base_url=settings.controller_url, headers=headers, timeout=8)

    async def close(self) -> None:
        if self.client:
            await self.client.aclose()

    async def get(self, path: str) -> dict[str, Any]:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.get(path)
        response.raise_for_status()
        return response.json()

    async def select(self, group: str, name: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put(f"/proxies/{quote(group, safe='')}", json={"name": name})
        response.raise_for_status()

    async def reload_config(self, payload: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put("/configs?force=true", json={"payload": payload})
        response.raise_for_status()

    async def refresh_rule_provider(self, provider: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.put(f"/providers/rules/{quote(provider, safe='')}")
        response.raise_for_status()

    async def delete(self, path: str) -> None:
        if not self.client:
            raise RuntimeError("mihomo client is not started")
        response = await self.client.delete(path)
        response.raise_for_status()

    async def close_connections(self, connection_ids: list[str]) -> tuple[int, int]:
        semaphore = asyncio.Semaphore(16)

        async def close_one(connection_id: str) -> bool:
            async with semaphore:
                try:
                    await self.delete(f"/connections/{quote(connection_id, safe='')}")
                    return True
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:  # connection ended on its own
                        return False
                    raise

        results = await asyncio.gather(*(close_one(connection_id) for connection_id in connection_ids), return_exceptions=True)
        closed = sum(result is True for result in results)
        failed = sum(isinstance(result, Exception) for result in results)
        return closed, failed


mihomo = MihomoClient()


RULE_OPTIONS = {"no-resolve"}
RULE_BUILTIN_POLICIES = {"DIRECT", "REJECT", "REJECT-DROP", "PASS"}


def _rule_parts(content: str) -> list[str]:
    """Split a mihomo rule without breaking commas inside logical expressions."""
    parts: list[str] = []
    start = 0
    depth = 0
    quote_char = ""
    escaped = False
    for index, char in enumerate(content):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote_char:
            if char == quote_char:
                quote_char = ""
            continue
        if char in {"'", '"'}:
            quote_char = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(content[start:index].strip())
            start = index + 1
    parts.append(content[start:].strip())
    return parts


def _parsed_rule(content: str) -> dict[str, Any]:
    parts = _rule_parts(content)
    rule_type = parts[0].upper() if parts and parts[0] else "UNKNOWN"
    option_start = len(parts)
    while option_start > 1 and parts[option_start - 1].lower() in RULE_OPTIONS:
        option_start -= 1
    policy_index = option_start - 1
    policy = parts[policy_index] if policy_index >= 1 else ""
    matcher = ",".join(parts[1:policy_index]) if policy_index > 1 else ""
    return {"type": rule_type, "matcher": matcher, "policy": policy, "options": parts[option_start:]}


SUBSCRIPTION_MAX_BYTES = 8 * 1024 * 1024
SUBSCRIPTION_REFRESH_SEMAPHORE = asyncio.Semaphore(4)
MAX_SUBSCRIPTIONS_PER_USER = 32
SUBSCRIPTION_TYPES = {"ss", "ssr", "vmess", "vless", "trojan", "anytls", "hysteria", "hysteria2", "tuic", "socks5", "http"}
REGION_HINTS: dict[str, tuple[str, ...]] = {
    "香港": ("香港", "hong kong", "🇭🇰"),
    "日本": ("日本", "japan", "tokyo", "osaka", "🇯🇵"),
    "美国": ("美国", "united states", "los angeles", "san jose", "seattle", "🇺🇸", "🇺🇲"),
    "新加坡": ("新加坡", "狮城", "singapore", "🇸🇬"),
    "英国": ("英国", "united kingdom", "london", "🇬🇧"),
    "台湾": ("台湾", "taiwan", "🇹🇼", "🇨🇳"),
    "德国": ("德国", "germany", "berlin", "🇩🇪"),
}


def _subscription_region(name: str) -> str | None:
    lowered = name.casefold()
    return next((region for region, hints in REGION_HINTS.items() if any(hint.casefold() in lowered for hint in hints)), None)


def _surge_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _surge_proxy(name: str, value: str) -> dict[str, Any] | None:
    parts = [item.strip() for item in value.split(",")]
    if len(parts) < 3:
        return None
    proxy_type = parts[0].lower()
    if proxy_type == "direct":
        return None
    if proxy_type not in SUBSCRIPTION_TYPES:
        return None
    try:
        port = int(parts[2])
    except ValueError:
        return None
    parameters = {key.strip().lower(): item.strip() for part in parts[3:] if "=" in part for key, item in [part.split("=", 1)]}
    proxy: dict[str, Any] = {"name": name.strip(), "type": proxy_type, "server": parts[1], "port": port}
    if proxy_type == "ss":
        proxy.update({"cipher": parameters.get("encrypt-method", parameters.get("cipher", "aes-256-gcm")), "password": parameters.get("password", "")})
    elif proxy_type in {"trojan", "anytls", "hysteria", "hysteria2"}:
        proxy["password"] = parameters.get("password", parameters.get("auth", ""))
    elif proxy_type in {"vmess", "vless"}:
        proxy["uuid"] = parameters.get("username", parameters.get("uuid", ""))
        if proxy_type == "vmess":
            proxy["alterId"] = int(parameters.get("alter-id", parameters.get("alterid", "0")) or 0)
            proxy["cipher"] = parameters.get("encrypt-method", parameters.get("cipher", "auto"))
    elif proxy_type in {"socks5", "http"}:
        if parameters.get("username"):
            proxy["username"] = parameters["username"]
        if parameters.get("password"):
            proxy["password"] = parameters["password"]
    for source, target in (("sni", "sni"), ("server-name", "servername"), ("client-fingerprint", "client-fingerprint"), ("network", "network")):
        if parameters.get(source):
            proxy[target] = parameters[source]
    for source, target in (("skip-cert-verify", "skip-cert-verify"), ("tfo", "tfo"), ("udp-relay", "udp"), ("tls", "tls")):
        if source in parameters:
            proxy[target] = _surge_bool(parameters[source])
    return proxy


def _normalize_subscription_nodes(nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(nodes, list):
        raise ValueError("订阅中没有 proxies 节点列表")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in nodes:
        if not isinstance(raw, dict):
            continue
        node = dict(raw)
        name = str(node.get("name") or "").strip()
        proxy_type = str(node.get("type") or "").lower().strip()
        server = str(node.get("server") or "").strip()
        try:
            port = int(node.get("port") or 0)
        except (TypeError, ValueError):
            continue
        if not name or name in names or not proxy_type or not server or not 1 <= port <= 65535:
            continue
        node.update({"name": name, "type": proxy_type, "server": server, "port": port})
        names.add(name)
        normalized.append(node)
    if not normalized:
        raise ValueError("订阅中没有可用的 mihomo 节点")
    if len(normalized) > 2000:
        raise ValueError("单个订阅最多允许 2000 个节点")
    return normalized


def _parse_subscription(content: bytes) -> tuple[str, list[dict[str, Any]]]:
    text = content.decode("utf-8-sig", "replace").strip()
    if not text:
        raise ValueError("订阅内容为空")
    if re.search(r"^\[Proxy\]\s*$", text, re.MULTILINE | re.IGNORECASE):
        section = ""
        nodes: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line.casefold()
                continue
            if section != "[proxy]" or not line or line.startswith(("#", ";")) or "=" not in line:
                continue
            name, value = line.split("=", 1)
            parsed = _surge_proxy(name, value)
            if parsed:
                nodes.append(parsed)
        return "surge", _normalize_subscription_nodes(nodes)
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError("订阅不是有效的 Surge 或 Mihomo 配置") from exc
    if isinstance(payload, dict) and isinstance(payload.get("proxies"), list):
        return "mihomo", _normalize_subscription_nodes(payload["proxies"])
    raise ValueError("目前支持 Surge 配置和包含 proxies 的 Mihomo/Clash YAML")


def _subscription_usage(value: str | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in (value or "").split(";"):
        if "=" not in item:
            continue
        key, raw = item.split("=", 1)
        if key.strip() in {"upload", "download", "total", "expire"}:
            try:
                result[key.strip()] = int(raw.strip())
            except ValueError:
                continue
    return result


def _masked_subscription_url(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.hostname or '未知来源'}/••••"


def _overlay_subscription_nodes(config: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    old_nodes = [item for item in (config.get("proxies") or []) if isinstance(item, dict) and item.get("name")]
    old_names = {str(item["name"]) for item in old_nodes}
    new_names = [str(item["name"]) for item in nodes]
    group_names = {str(item.get("name")) for item in (config.get("proxy-groups") or []) if item.get("name")}
    collisions = sorted(group_names.intersection(new_names))
    if collisions:
        raise ValueError(f"订阅节点名称与策略组冲突：{collisions[0]}")
    config["proxies"] = nodes
    for group in config.get("proxy-groups") or []:
        members = group.get("proxies")
        if not isinstance(members, list):
            continue
        replaced = [str(item) for item in members if str(item) in old_names]
        if not replaced:
            continue
        preserved = [str(item) for item in members if str(item) not in old_names]
        region = _subscription_region(str(group.get("name") or ""))
        if region is None:
            member_regions = {_subscription_region(item) for item in replaced}
            member_regions.discard(None)
            region = next(iter(member_regions)) if len(member_regions) == 1 else None
        candidates = [name for name in new_names if region is None or _subscription_region(name) == region]
        if not candidates:
            raise ValueError(f"订阅没有可用于策略组 {str(group.get('name') or '').strip()} 的节点")
        group["proxies"] = list(dict.fromkeys([*preserved, *candidates]))
    return config


DELIVERY_TEST_URL = "https://www.gstatic.com/generate_204"
SURGE_DELIVERY_TEST_URL = "http://www.gstatic.com/generate_204"
REGION_EMOJIS = {
    "香港": "🇭🇰",
    "日本": "🇯🇵",
    "美国": "🇺🇸",
    "新加坡": "🇸🇬",
    "英国": "🇬🇧",
    "台湾": "🇹🇼",
    "德国": "🇩🇪",
    "其他": "🌐",
}
DELIVERY_MAIN_POLICY = "🚀 节点选择"
DELIVERY_MANUAL_POLICY = "🔧 手动切换"
DELIVERY_DIRECT_POLICY = "🎯 全球直连"
DELIVERY_REJECT_POLICY = "🛑 全球拦截"
DELIVERY_CLEAN_POLICY = "🍃 应用净化"
DELIVERY_FINAL_POLICY = "🐟 漏网之鱼"
DELIVERY_SERVICE_POLICIES = (
    "🌍 国外媒体",
    "📲 电报信息",
    "🍎 苹果服务",
    "💬 Ai平台",
    "📢 谷歌FCM",
    "📹 油管视频",
    "📺 哔哩哔哩",
    "Ⓜ️ 微软云盘",
    "🎮 游戏平台",
    "🌏 国内媒体",
    "🎥 奈飞视频",
    "Ⓜ️ 微软服务",
    "📺 巴哈姆特",
    "Ⓜ️ 微软Bing",
)


def _delivery_region_policy(region: str) -> str:
    return f"{REGION_EMOJIS.get(region, '🌐')} {region}"


def _delivery_rule_sets() -> list[dict[str, Any]]:
    """Load the shared, credential-free delivery rule catalog in its declared order."""
    try:
        payload = json.loads(settings.default_rule_sets_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("无法读取交付规则集目录") from exc
    result: list[dict[str, Any]] = []
    for item in payload.get("ruleSets") or []:
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        url = str(item.get("url") or "").strip()
        policy = str(item.get("policy") or "").strip()
        if not url.startswith(("https://", "http://")) or not policy:
            continue
        result.append(item)
    return result


def _delivery_policy(policy: str, regions: list[tuple[str, list[str]]]) -> str:
    """Fall back safely when a shared rule targets a region absent from this subscription."""
    available = {_delivery_region_policy(region) for region, _ in regions}
    regional = {_delivery_region_policy(region) for region in REGION_EMOJIS}
    return policy if policy not in regional or policy in available else DELIVERY_MAIN_POLICY


def _delivery_regions(nodes: list[dict[str, Any]]) -> list[tuple[str, list[str]]]:
    """Group nodes by the regions already understood by the gateway UI."""
    grouped: dict[str, list[str]] = defaultdict(list)
    other: list[str] = []
    for node in nodes:
        name = str(node.get("name") or "")
        region = _subscription_region(name)
        (grouped[region] if region else other).append(name)
    result = [(region, grouped[region]) for region in REGION_HINTS if grouped.get(region)]
    if other:
        result.append(("其他", other))
    return result


def _clash_delivery(name: str, nodes: list[dict[str, Any]]) -> str:
    regions = _delivery_regions(nodes)
    regional_groups = [_delivery_region_policy(region) for region, _ in regions]
    policy_choices = [DELIVERY_MAIN_POLICY, DELIVERY_DIRECT_POLICY, DELIVERY_MANUAL_POLICY, *regional_groups]
    proxy_groups: list[dict[str, Any]] = [
        {"name": DELIVERY_MAIN_POLICY, "type": "select", "proxies": [*regional_groups, DELIVERY_MANUAL_POLICY, "DIRECT"]},
        {"name": DELIVERY_MANUAL_POLICY, "type": "select", "proxies": [*[str(node["name"]) for node in nodes], "DIRECT"]},
    ]
    proxy_groups.extend({"name": policy, "type": "select", "proxies": policy_choices} for policy in DELIVERY_SERVICE_POLICIES)
    proxy_groups.extend(
        [
            {"name": DELIVERY_DIRECT_POLICY, "type": "select", "proxies": ["DIRECT", DELIVERY_MAIN_POLICY]},
            {"name": DELIVERY_REJECT_POLICY, "type": "select", "proxies": ["REJECT", DELIVERY_DIRECT_POLICY]},
            {"name": DELIVERY_CLEAN_POLICY, "type": "select", "proxies": ["REJECT", DELIVERY_DIRECT_POLICY]},
            {"name": DELIVERY_FINAL_POLICY, "type": "select", "proxies": policy_choices},
        ]
    )
    for region, members in regions:
        policy = _delivery_region_policy(region)
        best = f"{policy}最佳"
        sticky = f"{policy}智能"
        proxy_groups.extend(
            [
                {"name": policy, "type": "select", "proxies": [best, sticky, DELIVERY_MANUAL_POLICY]},
                {
                    "name": best,
                    "type": "url-test",
                    "proxies": members,
                    "url": DELIVERY_TEST_URL,
                    "expected-status": 204,
                    "interval": 300,
                    "timeout": 5000,
                    "tolerance": 80,
                    "lazy": True,
                },
                {
                    "name": sticky,
                    "type": "load-balance",
                    "proxies": members,
                    "url": DELIVERY_TEST_URL,
                    "expected-status": 204,
                    "interval": 300,
                    "timeout": 5000,
                    "strategy": "consistent-hashing",
                    "lazy": True,
                },
            ]
        )
    rule_providers: dict[str, dict[str, Any]] = {}
    rules: list[str] = []
    for item in _delivery_rule_sets():
        provider_id = "egresscope-" + hashlib.sha1(str(item.get("id") or item["url"]).encode()).hexdigest()[:12]
        rule_providers[provider_id] = {
            "type": "http",
            "url": str(item["url"]),
            "path": f"./ruleset/{provider_id}.txt",
            "interval": max(300, int(item.get("interval") or 86400)),
            "behavior": item.get("behavior") or "classical",
            "format": item.get("format") or "text",
            "proxy": DELIVERY_MAIN_POLICY,
        }
        rules.append(f"RULE-SET,{provider_id},{_delivery_policy(str(item['policy']), regions)}")
    rules.extend((f"GEOIP,CN,{DELIVERY_DIRECT_POLICY}", f"MATCH,{DELIVERY_FINAL_POLICY}"))
    payload = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "ipv6": False,
        "unified-delay": True,
        "tcp-concurrent": True,
        "profile": {"store-selected": True},
        "dns": {
            "enable": True,
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "nameserver": ["119.29.29.29", "223.5.5.5", "https://dns.alidns.com/dns-query"],
        },
        "proxies": nodes,
        "proxy-groups": proxy_groups,
        "rule-providers": rule_providers,
        "rules": rules,
    }
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)


def _surge_scalar(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace(",", "\\,")


def _surge_node_line(node: dict[str, Any]) -> str | None:
    """Render the protocols shared by mihomo and current Surge releases."""
    name = _surge_scalar(node["name"])
    proxy_type = str(node.get("type") or "").lower()
    server = _surge_scalar(node["server"])
    port = int(node["port"])
    parts = [proxy_type, server, str(port)]
    if proxy_type == "ss":
        parts.extend((f"encrypt-method={_surge_scalar(node.get('cipher', 'aes-256-gcm'))}", f"password={_surge_scalar(node.get('password', ''))}"))
    elif proxy_type in {"trojan", "anytls", "hysteria2"}:
        parts.append(f"password={_surge_scalar(node.get('password', ''))}")
    elif proxy_type == "vmess":
        parts.append(f"username={_surge_scalar(node.get('uuid', ''))}")
        if node.get("cipher"):
            parts.append(f"encrypt-method={_surge_scalar(node['cipher'])}")
    elif proxy_type in {"http", "socks5"}:
        if node.get("username"):
            parts.append(f"username={_surge_scalar(node['username'])}")
        if node.get("password"):
            parts.append(f"password={_surge_scalar(node['password'])}")
    elif proxy_type == "tuic":
        parts.append(f"token={_surge_scalar(node.get('token') or node.get('password') or '')}")
    else:
        return None
    if node.get("sni") or node.get("servername"):
        parts.append(f"sni={_surge_scalar(node.get('sni') or node.get('servername'))}")
    if "skip-cert-verify" in node:
        parts.append(f"skip-cert-verify={'true' if node['skip-cert-verify'] else 'false'}")
    if node.get("udp") and proxy_type in {"ss", "socks5"}:
        parts.append("udp-relay=true")
    if node.get("tfo"):
        parts.append("tfo=true")
    if proxy_type == "anytls":
        parts.append("reuse=true")
    return f"{name} = {', '.join(parts)}"


def _surge_delivery(name: str, nodes: list[dict[str, Any]], managed_url: str | None = None) -> str:
    rendered = [(node, _surge_node_line(node)) for node in nodes]
    supported_nodes = [node for node, line in rendered if line]
    proxy_lines = [line for _, line in rendered if line]
    if not proxy_lines:
        raise ValueError("该订阅没有 Surge 支持的节点协议")
    regions = _delivery_regions(supported_nodes)
    regional_groups = [_delivery_region_policy(region) for region, _ in regions]
    policy_choices = [DELIVERY_MAIN_POLICY, DELIVERY_DIRECT_POLICY, DELIVERY_MANUAL_POLICY, *regional_groups]
    node_names = [_surge_scalar(node["name"]) for node in supported_nodes]
    group_lines = [
        f"{DELIVERY_MAIN_POLICY} = select, {', '.join([*regional_groups, DELIVERY_MANUAL_POLICY, 'DIRECT'])}",
        f"{DELIVERY_MANUAL_POLICY} = select, {', '.join([*node_names, 'DIRECT'])}",
    ]
    group_lines.extend(f"{policy} = select, {', '.join(policy_choices)}" for policy in DELIVERY_SERVICE_POLICIES)
    group_lines.extend(
        [
            f"{DELIVERY_DIRECT_POLICY} = select, DIRECT, {DELIVERY_MAIN_POLICY}",
            f"{DELIVERY_REJECT_POLICY} = select, REJECT, {DELIVERY_DIRECT_POLICY}",
            f"{DELIVERY_CLEAN_POLICY} = select, REJECT, {DELIVERY_DIRECT_POLICY}",
            f"{DELIVERY_FINAL_POLICY} = select, {', '.join(policy_choices)}",
        ]
    )
    for region, members in regions:
        policy = _delivery_region_policy(region)
        best = f"{policy}最佳"
        sticky = f"{policy}智能"
        escaped_members = [_surge_scalar(member) for member in members]
        group_lines.extend(
            [
                f"{policy} = select, {best}, {sticky}, {DELIVERY_MANUAL_POLICY}",
                f"{best} = url-test, {', '.join(escaped_members)}, url={SURGE_DELIVERY_TEST_URL}, interval=300, tolerance=80, timeout=5",
                f"{sticky} = load-balance, {', '.join(escaped_members)}, url={SURGE_DELIVERY_TEST_URL}, interval=300, timeout=5, persistent=true",
            ]
        )
    rule_lines = [
        f"RULE-SET,{item['url']},{_delivery_policy(str(item['policy']), regions)},update-interval={max(300, int(item.get('interval') or 86400))}"
        for item in _delivery_rule_sets()
    ]
    preamble = [f"#!MANAGED-CONFIG {managed_url} interval=86400 strict=true", ""] if managed_url else []
    return "\n".join(
        [
            *preamble,
            "[General]",
            "loglevel = notify",
            "dns-server = system, 119.29.29.29, 223.5.5.5",
            "test-timeout = 5",
            "skip-proxy = 127.0.0.1, localhost, *.local, 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10",
            "tun-excluded-routes = 192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12, 100.64.0.0/10",
            "ipv6 = false",
            "",
            "[Proxy]",
            *proxy_lines,
            "",
            "[Proxy Group]",
            *group_lines,
            "",
            "[Rule]",
            *rule_lines,
            f"GEOIP,CN,{DELIVERY_DIRECT_POLICY}",
            f"FINAL,{DELIVERY_FINAL_POLICY}",
            "",
        ]
    )


def _subscription_host_key(hostname: str) -> str:
    return hostname.encode("idna").decode("ascii").casefold()


async def _resolve_subscription_target(value: str) -> tuple[str, tuple[str, ...]]:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("订阅地址必须是公开的 HTTP/HTTPS URL")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        allowed_ports = {int(item.strip()) for item in settings.subscription_allowed_ports.split(",") if item.strip()}
    except ValueError as exc:
        raise RuntimeError("EGRESSCOPE_SUBSCRIPTION_ALLOWED_PORTS contains a non-numeric port") from exc
    if port not in allowed_ports:
        raise ValueError(f"订阅地址端口 {port} 不在允许列表中")
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, port, type=0)
    except OSError as exc:
        raise ValueError("订阅域名无法解析") from exc
    resolved: set[str] = set()
    fake_ip = False
    for address in {item[4][0] for item in addresses}:
        parsed_address = ipaddress.ip_address(address.split("%", 1)[0])
        if parsed_address.is_global:
            resolved.add(str(parsed_address))
        elif any(parsed_address in network for network in MIHOMO_FAKE_IP_NETWORKS):
            fake_ip = True
        else:
            raise ValueError("订阅地址不能指向局域网、回环或保留地址")
    if fake_ip:
        resolved = set(await _validate_fake_ip_hostname(parsed.hostname))
    if not resolved:
        raise ValueError("订阅域名没有可用的公网地址")
    return value.strip(), tuple(sorted(resolved))


async def _validate_subscription_url(value: str) -> str:
    validated, _ = await _resolve_subscription_target(value)
    return validated


async def _validate_fake_ip_hostname(hostname: str) -> tuple[str, ...]:
    """Resolve a mihomo Fake-IP hostname through public DoH without weakening SSRF checks."""
    resolvers = (
        ("https://cloudflare-dns.com/dns-query", {"Accept": "application/dns-json"}),
        ("https://dns.google/resolve", {}),
    )
    async with httpx.AsyncClient(timeout=8, follow_redirects=False, headers={"User-Agent": "Egresscope/0.2"}) as client:
        for endpoint, headers in resolvers:
            resolved: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
            try:
                for record_type in ("A", "AAAA"):
                    response = await client.get(endpoint, params={"name": hostname, "type": record_type}, headers=headers)
                    response.raise_for_status()
                    payload = response.json()
                    for answer in payload.get("Answer") or []:
                        try:
                            resolved.add(ipaddress.ip_address(str(answer.get("data") or "").rstrip(".")))
                        except ValueError:
                            continue
                if not resolved:
                    continue
                if any(not address.is_global for address in resolved):
                    raise ValueError("订阅地址的真实 DNS 记录指向局域网、回环或保留地址")
                return tuple(sorted(str(address) for address in resolved))
            except ValueError:
                raise
            except (httpx.HTTPError, json.JSONDecodeError, TypeError):
                continue
    raise ValueError("订阅域名使用 Fake-IP，但公网 DNS 复核暂时失败")


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Resolve subscription hosts only to addresses validated by the application."""

    def __init__(self, pins: dict[str, tuple[str, ...]]) -> None:
        self.pins = pins
        self.backend = httpcore.AnyIOBackend()
        self._offsets: dict[str, int] = defaultdict(int)

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> httpcore.AsyncNetworkStream:
        key = _subscription_host_key(host.decode() if isinstance(host, bytes) else host)
        addresses = self.pins.get(key)
        if not addresses:
            raise OSError("subscription host was not validated")
        offset = self._offsets[key] % len(addresses)
        self._offsets[key] += 1
        return await self.backend.connect_tcp(
            addresses[offset],
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, path: str, timeout: float | None = None, socket_options: Any = None) -> httpcore.AsyncNetworkStream:
        raise OSError("unix sockets are not allowed for subscription downloads")

    async def sleep(self, seconds: float) -> None:
        await self.backend.sleep(seconds)


class _PinnedHTTPTransport(httpx.AsyncHTTPTransport):
    def __init__(self, pins: dict[str, tuple[str, ...]]) -> None:
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            max_connections=8,
            max_keepalive_connections=4,
            keepalive_expiry=5,
            network_backend=_PinnedNetworkBackend(pins),
        )


async def _download_subscription(value: str) -> tuple[bytes, dict[str, int]]:
    current = value.strip()
    pins: dict[str, tuple[str, ...]] = {}
    transport = _PinnedHTTPTransport(pins)
    timeout = httpx.Timeout(30, connect=10)
    async with httpx.AsyncClient(transport=transport, timeout=timeout, follow_redirects=False, headers={"User-Agent": "Egresscope/1.0"}) as client:
        for _ in range(6):
            current, addresses = await _resolve_subscription_target(current)
            hostname = urlparse(current).hostname
            assert hostname is not None
            pins[_subscription_host_key(hostname)] = addresses
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("订阅重定向缺少目标地址")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > SUBSCRIPTION_MAX_BYTES:
                    raise ValueError("订阅内容超过 8 MiB 限制")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > SUBSCRIPTION_MAX_BYTES:
                        raise ValueError("订阅内容超过 8 MiB 限制")
                return bytes(content), _subscription_usage(response.headers.get("subscription-userinfo"))
    raise ValueError("订阅重定向次数过多")


class SubscriptionStore:
    def _row(self, subscription_id: str) -> sqlite3.Row | None:
        with _db() as connection:
            return connection.execute(
                "SELECT subscriptions.*, users.username owner_name FROM subscriptions JOIN users ON users.id = subscriptions.owner_id WHERE subscriptions.id = ?",
                (subscription_id,),
            ).fetchone()

    @staticmethod
    def _authorize(row: sqlite3.Row | None, user: dict[str, Any]) -> sqlite3.Row:
        if row is None or (user["role"] != "admin" and int(row["owner_id"]) != int(user["id"])):
            raise KeyError("subscription")
        return row

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        usage = json.loads(row["usage_json"] or "{}")
        nodes = json.loads(row["payload_json"] or "[]")
        return {
            "id": row["id"], "ownerId": row["owner_id"], "owner": row["owner_name"], "name": row["name"],
            "maskedUrl": _masked_subscription_url(row["url"]), "interval": row["interval_seconds"], "enabled": bool(row["enabled"]),
            "gatewayEnabled": bool(row["gateway_enabled"]), "sourceFormat": row["source_format"], "nodeCount": row["node_count"],
            "nodePreview": [item.get("name") for item in nodes[:8]], "usage": usage, "fetchedAt": row["fetched_at"],
            "nextRefreshAt": row["next_refresh_at"], "lastError": row["last_error"], "updatedAt": row["updated_at"],
            "deliveryPaths": {
                "clash": f"/sub/{row['delivery_token']}/clash.yaml",
                "surge": f"/sub/{row['delivery_token']}/surge.conf",
            },
        }

    def list(self, user: dict[str, Any]) -> dict[str, Any]:
        with _db() as connection:
            if user["role"] == "admin":
                rows = connection.execute("SELECT subscriptions.*, users.username owner_name FROM subscriptions JOIN users ON users.id = subscriptions.owner_id ORDER BY gateway_enabled DESC, created_at").fetchall()
            else:
                rows = connection.execute("SELECT subscriptions.*, users.username owner_name FROM subscriptions JOIN users ON users.id = subscriptions.owner_id WHERE owner_id = ? ORDER BY created_at", (user["id"],)).fetchall()
        items = [self._public(row) for row in rows]
        return {"subscriptions": items, "summary": {"count": len(items), "nodes": sum(item["nodeCount"] for item in items), "healthy": sum(not item["lastError"] and bool(item["fetchedAt"]) for item in items), "gateway": next((item["name"] for item in items if item["gatewayEnabled"]), None)}}

    def get(self, subscription_id: str, user: dict[str, Any]) -> dict[str, Any]:
        return self._public(self._authorize(self._row(subscription_id), user))

    def create(self, user: dict[str, Any], name: str, url: str, interval: int, enabled: bool) -> str:
        subscription_id = secrets.token_hex(10)
        now = int(time.time())
        with _db() as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM subscriptions WHERE owner_id = ?", (user["id"],)).fetchone()[0])
            if count >= MAX_SUBSCRIPTIONS_PER_USER:
                raise ValueError(f"每个用户最多可创建 {MAX_SUBSCRIPTIONS_PER_USER} 个订阅")
            connection.execute(
                "INSERT INTO subscriptions(id,owner_id,name,url,interval_seconds,enabled,gateway_enabled,delivery_token,next_refresh_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (subscription_id, user["id"], name.strip(), url.strip(), interval, int(enabled), 0, secrets.token_urlsafe(24), now, now, now),
            )
        return subscription_id

    def update(self, subscription_id: str, user: dict[str, Any], updates: dict[str, Any]) -> None:
        row = self._authorize(self._row(subscription_id), user)
        mapping = {"name": "name", "url": "url", "interval": "interval_seconds", "enabled": "enabled"}
        assignments: list[str] = []
        values: list[Any] = []
        for key, column in mapping.items():
            if key not in updates:
                continue
            value = updates[key]
            if key in {"name", "url"}:
                value = value.strip()
            if key == "enabled":
                value = int(value)
            assignments.append(f"{column} = ?")
            values.append(value)
        if "url" in updates:
            assignments.extend(("next_refresh_at = ?", "last_error = NULL"))
            values.append(int(time.time()))
        if not assignments:
            return
        assignments.append("updated_at = ?")
        values.extend((int(time.time()), subscription_id))
        with _db() as connection:
            connection.execute(f"UPDATE subscriptions SET {', '.join(assignments)} WHERE id = ?", values)

    def delete(self, subscription_id: str, user: dict[str, Any]) -> bool:
        row = self._authorize(self._row(subscription_id), user)
        with _db() as connection:
            connection.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        return bool(row["gateway_enabled"])

    def rotate_token(self, subscription_id: str, user: dict[str, Any]) -> dict[str, Any]:
        self._authorize(self._row(subscription_id), user)
        with _db() as connection:
            connection.execute(
                "UPDATE subscriptions SET delivery_token = ?, updated_at = ? WHERE id = ?",
                (secrets.token_urlsafe(24), int(time.time()), subscription_id),
            )
        return self.get(subscription_id, user)

    def activate(self, subscription_id: str) -> None:
        row = self._row(subscription_id)
        if row is None:
            raise KeyError(subscription_id)
        if not row["payload_json"]:
            raise ValueError("请先成功刷新订阅，再设为网关节点源")
        with _db() as connection:
            connection.execute("UPDATE subscriptions SET gateway_enabled = 0")
            connection.execute("UPDATE subscriptions SET gateway_enabled = 1, enabled = 1, updated_at = ? WHERE id = ?", (int(time.time()), subscription_id))

    def gateway_id(self) -> str | None:
        with _db() as connection:
            row = connection.execute("SELECT id FROM subscriptions WHERE gateway_enabled = 1 LIMIT 1").fetchone()
        return str(row["id"]) if row else None

    def deactivate(self, subscription_id: str) -> None:
        with _db() as connection:
            result = connection.execute("UPDATE subscriptions SET gateway_enabled = 0, updated_at = ? WHERE id = ?", (int(time.time()), subscription_id))
        if result.rowcount != 1:
            raise KeyError(subscription_id)

    async def refresh(self, subscription_id: str, user: dict[str, Any] | None = None) -> dict[str, Any]:
        row = self._row(subscription_id)
        if user is not None:
            row = self._authorize(row, user)
        if row is None:
            raise KeyError(subscription_id)
        try:
            async with SUBSCRIPTION_REFRESH_SEMAPHORE:
                content, usage = await _download_subscription(str(row["url"]))
                source_format, nodes = _parse_subscription(content)
                now = int(time.time())
                with _db() as connection:
                    connection.execute(
                        "UPDATE subscriptions SET source_format=?,node_count=?,payload_json=?,usage_json=?,fetched_at=?,next_refresh_at=?,last_error=NULL,updated_at=? WHERE id=?",
                        (source_format, len(nodes), json.dumps(nodes, ensure_ascii=False, separators=(",", ":")), json.dumps(usage, separators=(",", ":")), now, now + int(row["interval_seconds"]), now, subscription_id),
                    )
        except Exception as exc:
            now = int(time.time())
            with _db() as connection:
                connection.execute("UPDATE subscriptions SET last_error=?,next_refresh_at=?,updated_at=? WHERE id=?", (str(exc)[:500], now + min(900, int(row["interval_seconds"])), now, subscription_id))
            raise
        refreshed = self._row(subscription_id)
        assert refreshed is not None
        return self._public(refreshed)

    def due(self) -> list[str]:
        with _db() as connection:
            rows = connection.execute("SELECT id FROM subscriptions WHERE enabled = 1 AND next_refresh_at <= ? ORDER BY next_refresh_at LIMIT 8", (int(time.time()),)).fetchall()
        return [str(row["id"]) for row in rows]

    def delivery(self, token: str, client: str, managed_url: str | None = None) -> str:
        with _db() as connection:
            row = connection.execute("SELECT name,payload_json FROM subscriptions WHERE delivery_token = ? AND enabled = 1", (token,)).fetchone()
        if not row or not row["payload_json"]:
            raise KeyError(token)
        nodes = json.loads(row["payload_json"])
        if client == "clash":
            return _clash_delivery(str(row["name"]), nodes)
        if client == "surge":
            return _surge_delivery(str(row["name"]), nodes, managed_url)
        raise KeyError(client)

    def overlay_config(self, config: dict[str, Any]) -> dict[str, Any]:
        with _db() as connection:
            row = connection.execute("SELECT payload_json,name FROM subscriptions WHERE gateway_enabled = 1 LIMIT 1").fetchone()
        if not row or not row["payload_json"]:
            return config
        return _overlay_subscription_nodes(config, json.loads(row["payload_json"]))


subscriptions = SubscriptionStore()


def _serialized_rule_operation(method: Any) -> Any:
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self.mutation_lock:
            return method(self, *args, **kwargs)

    return wrapped


class RuleWorkspace:
    """A persistent rule overlay compiled against the latest node configuration."""

    def __init__(self) -> None:
        self.path = settings.data_dir / "managed-rules.json"
        self.lock = asyncio.Lock()
        self.mutation_lock = threading.RLock()
        self.last_error: str | None = None

    def _base_config(self) -> dict[str, Any]:
        try:
            payload = yaml.safe_load(settings.config_path.read_text(encoding="utf-8")) or {}
        except PermissionError as exc:
            raise ValueError("面板只能只读访问 mihomo 配置，但当前文件权限不允许读取") from exc
        except (OSError, yaml.YAMLError) as exc:
            raise ValueError("无法读取 mihomo 基础配置") from exc
        if not isinstance(payload, dict):
            raise ValueError("mihomo 基础配置格式不正确")
        return subscriptions.overlay_config(payload)

    def _new_workspace(self) -> dict[str, Any]:
        config = self._base_config()
        try:
            defaults = json.loads(settings.default_rule_sets_path.read_text(encoding="utf-8"))
            rule_sets = defaults.get("ruleSets") or []
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("无法读取内置规则集目录") from exc
        base_rules = [str(item) for item in (config.get("rules") or [])]
        fallback = [item for item in base_rules if _parsed_rule(item)["type"] in {"GEOIP", "MATCH"}][-2:]
        if not fallback or _parsed_rule(fallback[-1])["type"] != "MATCH":
            fallback = ["MATCH,DIRECT"]
        now = int(time.time())
        return {
            "version": 2,
            "revision": 1,
            "appliedRevision": 0,
            "createdAt": now,
            "updatedAt": now,
            "ruleSets": rule_sets,
            "customRules": [],
            "fallbackRules": fallback,
        }

    def _load(self, create: bool = True) -> dict[str, Any] | None:
        if not self.path.exists():
            if not create:
                return None
            workspace = self._new_workspace()
            self._save(workspace)
            return workspace
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("规则工作区文件已损坏") from exc
        if not isinstance(payload, dict) or payload.get("version") != 2 or not isinstance(payload.get("ruleSets"), list):
            raise ValueError("规则工作区格式不正确")
        return payload

    def _save(self, workspace: dict[str, Any]) -> None:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(workspace, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    @staticmethod
    def _touch(workspace: dict[str, Any]) -> None:
        workspace["revision"] = int(workspace.get("revision") or 0) + 1
        workspace["updatedAt"] = int(time.time())

    @staticmethod
    def provider_id(rule_set_id: str) -> str:
        return "ssslab-" + hashlib.sha1(rule_set_id.encode()).hexdigest()[:12]

    def summary(self) -> dict[str, Any]:
        workspace = self._load()
        assert workspace is not None
        config = self._base_config()
        policies = [str(item.get("name")) for item in (config.get("proxy-groups") or []) if item.get("name")]
        custom = [{**rule, **_parsed_rule(str(rule.get("content") or "")), "index": index} for index, rule in enumerate(workspace.get("customRules") or [])]
        fallback = [{"content": content, **_parsed_rule(content)} for content in workspace.get("fallbackRules") or []]
        return {
            "revision": workspace.get("revision", 1),
            "appliedRevision": workspace.get("appliedRevision", 0),
            "dirty": workspace.get("revision", 1) != workspace.get("appliedRevision", 0),
            "updatedAt": workspace.get("updatedAt"),
            "lastError": self.last_error,
            "ruleSets": [{**item, "providerId": self.provider_id(str(item.get("id")))} for item in workspace.get("ruleSets") or []],
            "customRules": custom,
            "fallbackRules": fallback,
            "availablePolicies": policies,
            "counts": {
                "ruleSets": len(workspace.get("ruleSets") or []),
                "enabledRuleSets": sum(bool(item.get("enabled", True)) for item in workspace.get("ruleSets") or []),
                "customRules": len(custom),
            },
        }

    @_serialized_rule_operation
    def reset(self) -> dict[str, Any]:
        workspace = self._new_workspace()
        self._save(workspace)
        self.last_error = None
        return workspace

    @_serialized_rule_operation
    def add_rule_set(self, payload: dict[str, Any]) -> dict[str, Any]:
        workspace = self._load()
        assert workspace is not None
        rule_set = {"id": secrets.token_hex(8), **payload}
        workspace["ruleSets"].append(rule_set)
        self._touch(workspace)
        self._save(workspace)
        return rule_set

    @_serialized_rule_operation
    def update_rule_set(self, rule_set_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        workspace = self._load()
        assert workspace is not None
        rule_set = next((item for item in workspace["ruleSets"] if item.get("id") == rule_set_id), None)
        if rule_set is None:
            raise KeyError(rule_set_id)
        rule_set.update(updates)
        self._touch(workspace)
        self._save(workspace)
        return rule_set

    @_serialized_rule_operation
    def delete_rule_set(self, rule_set_id: str) -> None:
        workspace = self._load()
        assert workspace is not None
        before = len(workspace["ruleSets"])
        workspace["ruleSets"] = [item for item in workspace["ruleSets"] if item.get("id") != rule_set_id]
        if len(workspace["ruleSets"]) == before:
            raise KeyError(rule_set_id)
        self._touch(workspace)
        self._save(workspace)

    @_serialized_rule_operation
    def move_rule_set(self, rule_set_id: str, direction: str) -> int:
        workspace = self._load()
        assert workspace is not None
        index = next((i for i, item in enumerate(workspace["ruleSets"]) if item.get("id") == rule_set_id), -1)
        if index < 0:
            raise KeyError(rule_set_id)
        target = index - 1 if direction == "up" else index + 1
        target = max(0, min(target, len(workspace["ruleSets"]) - 1))
        if target != index:
            workspace["ruleSets"][index], workspace["ruleSets"][target] = workspace["ruleSets"][target], workspace["ruleSets"][index]
            self._touch(workspace)
            self._save(workspace)
        return target

    @_serialized_rule_operation
    def add_custom_rule(self, content: str, placement: str, note: str) -> dict[str, Any]:
        workspace = self._load()
        assert workspace is not None
        rule = {"id": secrets.token_hex(8), "enabled": True, "content": content.strip(), "placement": placement, "note": note.strip()}
        workspace["customRules"].append(rule)
        self._touch(workspace)
        self._save(workspace)
        return rule

    @_serialized_rule_operation
    def update_custom_rule(self, rule_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        workspace = self._load()
        assert workspace is not None
        rule = next((item for item in workspace["customRules"] if item.get("id") == rule_id), None)
        if rule is None:
            raise KeyError(rule_id)
        rule.update(updates)
        self._touch(workspace)
        self._save(workspace)
        return rule

    @_serialized_rule_operation
    def delete_custom_rule(self, rule_id: str) -> None:
        workspace = self._load()
        assert workspace is not None
        before = len(workspace["customRules"])
        workspace["customRules"] = [item for item in workspace["customRules"] if item.get("id") != rule_id]
        if len(workspace["customRules"]) == before:
            raise KeyError(rule_id)
        self._touch(workspace)
        self._save(workspace)

    @_serialized_rule_operation
    def compile(self) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        workspace = self._load()
        assert workspace is not None
        config = self._base_config()
        policies = RULE_BUILTIN_POLICIES.copy()
        policies.update(str(item.get("name")) for item in (config.get("proxy-groups") or []) if item.get("name"))
        policies.update(str(item.get("name")) for item in (config.get("proxies") or []) if item.get("name"))
        clean_policies = {_clean_name(name): name for name in policies}
        before = [item for item in workspace.get("customRules") or [] if item.get("enabled", True) and item.get("placement", "before") == "before"]
        after = [item for item in workspace.get("customRules") or [] if item.get("enabled", True) and item.get("placement") == "after"]
        providers = {key: value for key, value in (config.get("rule-providers") or {}).items() if not str(key).startswith("ssslab-")}
        enabled: list[str] = []
        enabled.extend(str(item.get("content") or "").strip() for item in before)
        download_proxy = clean_policies.get("节点选择")
        for item in workspace.get("ruleSets") or []:
            if not item.get("enabled", True):
                continue
            url = str(item.get("url") or "").strip()
            if not url.startswith(("https://", "http://")):
                raise ValueError(f"规则集 {item.get('name') or '未命名'} 的 URL 无效")
            policy = str(item.get("policy") or "").strip()
            resolved_policy = policy if policy in policies else clean_policies.get(_clean_name(policy), policy)
            provider_id = self.provider_id(str(item.get("id")))
            if item.get("format") == "mrs" and item.get("behavior") == "classical":
                raise ValueError(f"规则集 {item.get('name') or '未命名'}：MRS 不支持 classical 内容")
            provider = {
                "type": "http",
                "url": url,
                "path": f"./ruleset/{provider_id}.txt",
                "interval": max(300, int(item.get("interval") or 86400)),
                "behavior": item.get("behavior") or "classical",
                "format": item.get("format") or "text",
            }
            if download_proxy:
                provider["proxy"] = download_proxy
            providers[provider_id] = provider
            enabled.append(f"RULE-SET,{provider_id},{resolved_policy}")
        enabled.extend(str(item.get("content") or "").strip() for item in after)
        enabled.extend(str(item) for item in workspace.get("fallbackRules") or [])
        errors: list[str] = []
        for index, content in enumerate(enabled):
            parsed = _parsed_rule(content)
            if not content or parsed["type"] == "UNKNOWN" or not parsed["policy"]:
                errors.append(f"第 {index + 1} 条规则格式不完整")
            elif parsed["policy"] not in policies:
                errors.append(f"第 {index + 1} 条规则引用了不存在的策略：{parsed['policy']}")
            elif parsed["type"] == "MATCH" and index != len(enabled) - 1:
                errors.append(f"第 {index + 1} 条 MATCH 会遮蔽后续规则")
            elif parsed["type"] == "RULE-SET" and parsed["matcher"] not in providers:
                errors.append(f"第 {index + 1} 条规则引用了不存在的规则集：{parsed['matcher']}")
            if len(errors) >= 8:
                break
        if _parsed_rule(enabled[-1])["type"] != "MATCH":
            errors.append("最后一条启用规则必须是 MATCH，避免请求绕过规则链")
        if errors:
            raise ValueError("；".join(errors))
        config["rule-providers"] = providers
        config["rules"] = enabled
        return workspace, config, enabled

    async def apply(self, restoring: bool = False) -> dict[str, Any]:
        async with self.lock:
            try:
                workspace, config, enabled = await asyncio.to_thread(self.compile)
                payload = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
                await mihomo.reload_config(payload)
                workspace["appliedRevision"] = workspace.get("revision", 1)
                workspace["appliedAt"] = int(time.time())
                await asyncio.to_thread(self._save, workspace)
                self.last_error = None
                return {"ok": True, "revision": workspace["revision"], "rules": len(enabled), "restored": restoring}
            except Exception as exc:
                self.last_error = str(exc)
                raise

    async def restore_if_applied(self) -> None:
        workspace = await asyncio.to_thread(self._load, False)
        if workspace and workspace.get("appliedRevision"):
            await self.apply(restoring=True)


rule_workspace = RuleWorkspace()


def _clean_name(name: str) -> str:
    cleaned = re.sub(r"^[^A-Za-z0-9\u3400-\u9fff\[]+", "", name or "").strip()
    return cleaned or name


REGION_FLAGS = (
    (("香港", "Hong Kong", "HKG"), "🇭🇰"),
    (("台湾", "Taiwan", "TPE"), "🇹🇼"),
    (("新加坡", "狮城", "Singapore", "SGP"), "🇸🇬"),
    (("日本", "Japan", "Tokyo", "Osaka", "NRT", "KIX"), "🇯🇵"),
    (("美国", "United States", "USA", "Los Angeles", "San Jose", "LAX", "SJC"), "🇺🇸"),
    (("英国", "United Kingdom", "London", "GBR"), "🇬🇧"),
    (("韩国", "Korea", "Seoul", "ICN"), "🇰🇷"),
    (("德国", "Germany", "Frankfurt", "FRA"), "🇩🇪"),
    (("法国", "France", "Paris", "CDG"), "🇫🇷"),
    (("加拿大", "Canada", "Toronto", "YTO"), "🇨🇦"),
    (("澳大利亚", "澳洲", "Australia", "Sydney", "SYD"), "🇦🇺"),
)


def _display_node_name(name: str) -> str:
    """Keep a provider's flag, or infer one for display without changing its mihomo id."""
    raw = (name or "").strip()
    if re.search(r"[\U0001F1E6-\U0001F1FF]{2}", raw):
        return raw
    cleaned = _clean_name(raw)
    lowered = cleaned.casefold()
    for keywords, flag in REGION_FLAGS:
        if any(keyword.casefold() in lowered for keyword in keywords):
            return f"{flag} {cleaned}"
    return cleaned


def _duration(start: str | None) -> str:
    if not start:
        return "—"
    try:
        begun = datetime.fromisoformat(start.replace("Z", "+00:00"))
        seconds = max(0, int((datetime.now(timezone.utc) - begun).total_seconds()))
        return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    except ValueError:
        return "—"


def _start_timestamp(start: str | None, fallback: int) -> int:
    if not start:
        return fallback
    try:
        return int(datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return fallback


def _aliases() -> dict[str, str]:
    try:
        payload = json.loads(settings.device_aliases_path.read_text())
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


SERVICE_DOMAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("OpenAI", ("openai.com", "chatgpt.com", "oaistatic.com", "oaiusercontent.com", "chatgpt.livekit.cloud")),
    ("Telegram", ("telegram.org", "telegram.me", "t.me", "telegra.ph")),
    ("X (Twitter)", ("x.com", "twitter.com", "twimg.com", "t.co")),
    ("GitHub", ("github.com", "githubusercontent.com", "githubassets.com", "githubcopilot.com")),
    ("Microsoft", ("microsoft.com", "microsoftonline.com", "windows.com", "windowsupdate.com", "live.com", "office.com", "office365.com", "outlook.com", "azure.com")),
    ("Apple", ("apple.com", "icloud.com", "mzstatic.com", "apple-dns.net")),
    ("Google", ("google.com", "googleapis.com", "gstatic.com", "youtube.com", "ytimg.com")),
    ("Cloudflare", ("cloudflare.com", "cloudflare-dns.com", "workers.dev")),
)


def _service_for(host: str, destination_ip: str) -> tuple[str, str]:
    target = (host or destination_ip or "未知目标").strip().lower().rstrip(".")
    if not host:
        return "Direct IP", target
    for service, domains in SERVICE_DOMAINS:
        if any(target == domain or target.endswith(f".{domain}") for domain in domains):
            return service, target
    parts = target.split(".")
    label = parts[-2].replace("-", " ").title() if len(parts) >= 2 else target
    return label, target


class TrafficCollector:
    def __init__(self) -> None:
        self.online = False
        self.error: str | None = None
        self.version = "unknown"
        self.started = time.monotonic()
        self.started_at = int(time.time())
        self.connections: list[dict[str, Any]] = []
        self.devices: list[dict[str, Any]] = []
        self.chains: list[dict[str, Any]] = []
        self.timeline: deque[dict[str, Any]] = deque(maxlen=900)
        self.up_rate = 0
        self.down_rate = 0
        self.total_up = 0
        self.total_down = 0
        self._previous_connections: dict[str, tuple[int, int, float]] = {}
        self._previous_totals: tuple[int, int, float] | None = None
        self._stop = asyncio.Event()
        self._last_persist = 0.0
        self._pending_total_up = 0
        self._pending_total_down = 0
        self._pending_interval = 0.0
        self._detail_pending: dict[tuple[str, str, str, str], dict[str, int]] = {}
        self._flow_pending: dict[tuple[str, str, str], dict[str, int]] = {}

    def initialize(self) -> None:
        """Restore rate cursors and a useful chart window before polling resumes."""
        now = int(time.time())
        with _db() as connection:
            state = {row["key"]: (int(row["value"]), int(row["updated_at"])) for row in connection.execute("SELECT key,value,updated_at FROM collector_state")}
            upload_state = state.get("mihomo_upload_total")
            download_state = state.get("mihomo_download_total")
            if upload_state and download_state:
                seen_at = max(upload_state[1], download_state[1])
                self._previous_totals = (upload_state[0], download_state[0], float(seen_at))
            cursor_rows = connection.execute(
                "SELECT id,upload_bytes,download_bytes,seen_at FROM connection_cursors WHERE seen_at >= ?",
                (now - 300,),
            ).fetchall()
            self._previous_connections = {
                str(row["id"]): (int(row["upload_bytes"]), int(row["download_bytes"]), float(row["seen_at"]))
                for row in cursor_rows
            }
            history = connection.execute(
                "SELECT ts,SUM(up_bytes) up,SUM(down_bytes) down,MAX(interval_seconds) interval_seconds FROM traffic_samples WHERE ts >= ? GROUP BY ts ORDER BY ts DESC LIMIT 900",
                (now - 3600,),
            ).fetchall()
        for row in reversed(history):
            ts = int(row["ts"])
            elapsed = max(1, int(row["interval_seconds"] or 10))
            self.timeline.append({"time": _display_datetime(ts).strftime("%H:%M:%S"), "up": round(int(row["up"] or 0) / elapsed), "down": round(int(row["down"] or 0) / elapsed)})

    async def run(self) -> None:
        while not self._stop.is_set():
            before = time.monotonic()
            try:
                await self.sample()
            except Exception as exc:  # a dead core must not kill the audit service
                was_online = self.online
                self.online = False
                self.error = type(exc).__name__
                if was_online:
                    await asyncio.to_thread(
                        _record_gateway_event,
                        "error",
                        "gateway",
                        "网关连接中断",
                        "控制面暂时无法读取 mihomo 状态，系统会继续自动重试。",
                        {"error": type(exc).__name__},
                        f"gateway-offline:{int(time.time()) // 60}",
                    )
                logger.exception("traffic collector sample failed")
            elapsed = time.monotonic() - before
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(.2, settings.poll_interval - elapsed))
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    async def sample(self) -> None:
        was_online = self.online
        payload, version = await asyncio.gather(mihomo.get("/connections"), mihomo.get("/version"))
        sampled_at = time.monotonic()
        sampled_wall = time.time()
        wall_time = int(sampled_wall)
        aliases = _aliases()
        raw_connections = payload.get("connections") or []
        current: dict[str, tuple[int, int, float]] = {}
        transformed: list[dict[str, Any]] = []
        session_rows: list[tuple[Any, ...]] = []
        device_rollup: dict[str, dict[str, Any]] = defaultdict(lambda: {"active": 0, "up": 0, "down": 0, "total": 0})
        chain_rollup: dict[str, int] = defaultdict(int)

        for connection in raw_connections:
            connection_id = str(connection.get("id", ""))
            upload = int(connection.get("upload") or 0)
            download = int(connection.get("download") or 0)
            previous = self._previous_connections.get(connection_id)
            delta_time = sampled_wall - previous[2] if previous else 0
            up_rate = max(0, (upload - previous[0]) / delta_time) if previous and delta_time else 0
            down_rate = max(0, (download - previous[1]) / delta_time) if previous and delta_time else 0
            connection_up_delta = max(0, upload - previous[0]) if previous else (upload if self._previous_totals else 0)
            connection_down_delta = max(0, download - previous[1]) if previous else (download if self._previous_totals else 0)
            current[connection_id] = (upload, download, sampled_wall)
            metadata = connection.get("metadata") or {}
            source_ip = metadata.get("sourceIP") or "unknown"
            destination_ip = str(metadata.get("destinationIP") or "")
            host = str(metadata.get("host") or "")
            service, target = _service_for(host, destination_ip)
            device_name = aliases.get(source_ip, source_ip)
            raw_chain = [str(item) for item in (connection.get("chains") or [])]
            display_chain = [_clean_name(item) for item in reversed(raw_chain)]
            if not display_chain:
                display_chain = ["DIRECT"]
            exit_mode = "direct" if "DIRECT" in display_chain else "proxy"
            detail_key = (source_ip, service, target, exit_mode)
            detail = self._detail_pending.setdefault(detail_key, {"up": 0, "down": 0, "connections": 0})
            detail["up"] += connection_up_delta
            detail["down"] += connection_down_delta
            if not previous:
                detail["connections"] += 1
            rule_name = _clean_name(str(connection.get("rulePayload") or connection.get("rule") or "Match"))
            flow_key = (source_ip, rule_name, json.dumps(display_chain, ensure_ascii=False, separators=(",", ":")))
            flow_detail = self._flow_pending.setdefault(flow_key, {"up": 0, "down": 0})
            flow_detail["up"] += connection_up_delta
            flow_detail["down"] += connection_down_delta
            chain_key = display_chain[-2] if len(display_chain) > 1 else display_chain[-1]
            total = upload + download
            row = {
                "id": connection_id,
                "device": device_name,
                "sourceIP": source_ip,
                "host": host,
                "destinationIP": destination_ip,
                "destinationPort": metadata.get("destinationPort") or "",
                "network": metadata.get("network") or "tcp",
                "rule": rule_name,
                "chain": display_chain,
                "upRate": round(up_rate),
                "downRate": round(down_rate),
                "upload": upload,
                "download": download,
                "duration": _duration(connection.get("start")),
            }
            transformed.append(row)
            session_rows.append(
                (
                    connection_id,
                    source_ip,
                    host,
                    destination_ip,
                    str(metadata.get("destinationPort") or ""),
                    str(metadata.get("network") or "tcp"),
                    rule_name,
                    json.dumps(display_chain, ensure_ascii=False, separators=(",", ":")),
                    _start_timestamp(connection.get("start"), wall_time),
                    wall_time,
                    upload,
                    download,
                )
            )
            device = device_rollup[source_ip]
            device.update({"name": device_name, "ip": source_ip})
            device["active"] += 1
            device["up"] += up_rate
            device["down"] += down_rate
            device["total"] += total
            chain_rollup[chain_key] += total

        totals = (int(payload.get("uploadTotal") or 0), int(payload.get("downloadTotal") or 0), sampled_wall)
        delta_up = delta_down = 0
        sample_interval = 10
        if self._previous_totals:
            delta_time = sampled_wall - self._previous_totals[2]
            sample_interval = max(1, round(delta_time))
            delta_up = max(0, totals[0] - self._previous_totals[0])
            delta_down = max(0, totals[1] - self._previous_totals[1])
            self._pending_total_up += delta_up
            self._pending_total_down += delta_down
            self._pending_interval += max(0, delta_time)
            if delta_time:
                self.up_rate = round(delta_up / delta_time)
                self.down_rate = round(delta_down / delta_time)
        self._previous_totals = totals
        self._previous_connections = current
        self.total_up, self.total_down = totals[:2]
        self.connections = sorted(transformed, key=lambda row: row["upRate"] + row["downRate"], reverse=True)
        self.devices = sorted(device_rollup.values(), key=lambda row: row["up"] + row["down"], reverse=True)
        chain_total = sum(chain_rollup.values()) or 1
        self.chains = [
            {"name": name, "value": value, "percent": round(value / chain_total * 100, 1)}
            for name, value in sorted(chain_rollup.items(), key=lambda item: item[1], reverse=True)[:5]
        ]
        self.timeline.append({"time": _display_datetime().strftime("%H:%M:%S"), "up": self.up_rate, "down": self.down_rate})
        self.version = version.get("version", "unknown")
        self.online = True
        self.error = None
        if not was_online:
            await asyncio.to_thread(
                _record_gateway_event,
                "info",
                "gateway",
                "网关已连接",
                "mihomo 控制面和流量采集均已恢复。",
                {"version": self.version},
                f"gateway-online:{int(time.time()) // 60}",
            )

        if sampled_at - self._last_persist >= 10:
            detail_rows = [(wall_time, device, service, host, exit_mode, values["up"], values["down"], values["connections"]) for (device, service, host, exit_mode), values in self._detail_pending.items()]
            flow_rows = [(wall_time, device, rule, chain, values["up"], values["down"]) for (device, rule, chain), values in self._flow_pending.items() if values["up"] or values["down"]]
            cursor_rows = [(connection_id, values[0], values[1], wall_time) for connection_id, values in current.items()]
            await asyncio.to_thread(
                self._persist,
                wall_time,
                self._pending_total_up,
                self._pending_total_down,
                max(1, round(self._pending_interval)),
                detail_rows,
                flow_rows,
                cursor_rows,
                session_rows,
                totals[:2],
            )
            self._last_persist = sampled_at
            self._pending_total_up = 0
            self._pending_total_down = 0
            self._pending_interval = 0.0
            self._detail_pending = {}
            self._flow_pending = {}

    def _persist(
        self,
        ts: int,
        delta_up: int,
        delta_down: int,
        sample_interval: int,
        detail_rows: list[tuple[Any, ...]],
        flow_rows: list[tuple[Any, ...]],
        cursor_rows: list[tuple[Any, ...]],
        session_rows: list[tuple[Any, ...]],
        core_totals: tuple[int, int],
    ) -> None:
        grouped: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for row in flow_rows:
            try:
                chain_items = [str(item) for item in json.loads(str(row[3]))]
            except (json.JSONDecodeError, TypeError):
                chain_items = [str(row[3])]
            if "DIRECT" in chain_items:
                leaf = "DIRECT"
            elif len(chain_items) > 1:
                leaf = chain_items[-2]
            else:
                leaf = chain_items[-1] if chain_items else "UNKNOWN"
            grouped[(str(row[1]), leaf)][0] += int(row[4])
            grouped[(str(row[1]), leaf)][1] += int(row[5])

        entries = sorted(grouped.items())

        def reconcile(values: list[int], target: int) -> tuple[list[int], int]:
            raw_total = sum(values)
            if raw_total <= target:
                return values, target - raw_total
            if not raw_total:
                return [0] * len(values), target
            scaled = [value * target // raw_total for value in values]
            remainder = target - sum(scaled)
            for index in sorted(range(len(values)), key=lambda item: values[item] * target % raw_total, reverse=True)[:remainder]:
                scaled[index] += 1
            return scaled, 0

        up_values, unknown_up = reconcile([values[0] for _, values in entries], delta_up)
        down_values, unknown_down = reconcile([values[1] for _, values in entries], delta_down)
        active_by_device = {str(device["ip"]): int(device["active"]) for device in self.devices}
        rows = [
            (ts, key[0], key[1], up_values[index], down_values[index], active_by_device.get(key[0], 0), sample_interval)
            for index, (key, _) in enumerate(entries)
            if up_values[index] or down_values[index]
        ]
        if unknown_up or unknown_down:
            rows.append((ts, "unknown", "UNKNOWN", unknown_up, unknown_down, 0, sample_interval))
        cutoff = ts - settings.retention_days * 86400
        day_start = _calendar_start("day", ts)
        daily_rows = [(day_start, row[1], row[2], row[3], row[4], row[5], 1) for row in rows]
        daily_detail_rows = [(day_start, row[1], row[2], row[3], row[4], row[5], row[6], row[7]) for row in detail_rows]
        daily_flow_rows = [(day_start, row[1], row[2], row[3], row[4], row[5]) for row in flow_rows]
        class_totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        for row in rows:
            route_class = "direct" if row[2] == "DIRECT" else "unknown" if row[2] == "UNKNOWN" else "proxy"
            class_totals[(str(row[1]), route_class)][0] += int(row[3])
            class_totals[(str(row[1]), route_class)][1] += int(row[4])
        daily_class_rows = [
            (day_start, device, route_class, values[0], values[1])
            for (device, route_class), values in class_totals.items()
        ]
        with _db() as connection:
            connection.executemany("INSERT INTO traffic_samples(ts,device,chain,up_bytes,down_bytes,active,interval_seconds) VALUES(?,?,?,?,?,?,?)", rows)
            connection.executemany("INSERT INTO traffic_detail_samples(ts,device,service,host,exit_mode,up_bytes,down_bytes,connections) VALUES(?,?,?,?,?,?,?,?)", detail_rows)
            connection.executemany("INSERT INTO traffic_flow_samples VALUES(?,?,?,?,?,?)", flow_rows)
            connection.executemany(
                """
                INSERT INTO traffic_daily_rollups(day_start,device,chain,up_bytes,down_bytes,active_peak,samples)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(day_start,device,chain) DO UPDATE SET
                    up_bytes=up_bytes+excluded.up_bytes,
                    down_bytes=down_bytes+excluded.down_bytes,
                    active_peak=MAX(active_peak,excluded.active_peak),
                    samples=samples+excluded.samples
                """,
                daily_rows,
            )
            connection.executemany(
                """
                INSERT INTO traffic_detail_daily_rollups(day_start,device,service,host,exit_mode,up_bytes,down_bytes,connections)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(day_start,device,service,host,exit_mode) DO UPDATE SET
                    up_bytes=up_bytes+excluded.up_bytes,
                    down_bytes=down_bytes+excluded.down_bytes,
                    connections=connections+excluded.connections
                """,
                daily_detail_rows,
            )
            connection.executemany(
                """
                INSERT INTO traffic_flow_daily_rollups(day_start,device,rule,chain,up_bytes,down_bytes)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(day_start,device,rule,chain) DO UPDATE SET
                    up_bytes=up_bytes+excluded.up_bytes,
                    down_bytes=down_bytes+excluded.down_bytes
                """,
                daily_flow_rows,
            )
            connection.executemany(
                """
                INSERT INTO traffic_class_daily_rollups(day_start,device,route_class,up_bytes,down_bytes)
                VALUES(?,?,?,?,?)
                ON CONFLICT(day_start,device,route_class) DO UPDATE SET
                    up_bytes=up_bytes+excluded.up_bytes,
                    down_bytes=down_bytes+excluded.down_bytes
                """,
                daily_class_rows,
            )
            connection.executemany(
                """
                INSERT INTO connection_sessions(
                    id,device,host,destination_ip,destination_port,network,rule,chain,
                    started_at,last_seen_at,upload_bytes,download_bytes
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    device=excluded.device,
                    host=excluded.host,
                    destination_ip=excluded.destination_ip,
                    destination_port=excluded.destination_port,
                    network=excluded.network,
                    rule=excluded.rule,
                    chain=excluded.chain,
                    last_seen_at=excluded.last_seen_at,
                    ended_at=NULL,
                    upload_bytes=excluded.upload_bytes,
                    download_bytes=excluded.download_bytes
                """,
                session_rows,
            )
            connection.execute(
                "UPDATE connection_sessions SET ended_at = ? WHERE ended_at IS NULL AND last_seen_at < ?",
                (ts, ts),
            )
            connection.execute("DELETE FROM connection_cursors")
            connection.executemany("INSERT INTO connection_cursors(id,upload_bytes,download_bytes,seen_at) VALUES(?,?,?,?)", cursor_rows)
            connection.executemany(
                "INSERT INTO collector_state(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (("mihomo_upload_total", core_totals[0], ts), ("mihomo_download_total", core_totals[1], ts)),
            )
            connection.execute("DELETE FROM traffic_samples WHERE ts < ?", (cutoff,))
            connection.execute("DELETE FROM traffic_detail_samples WHERE ts < ?", (cutoff,))
            connection.execute("DELETE FROM traffic_flow_samples WHERE ts < ?", (cutoff,))
            connection.execute("DELETE FROM connection_sessions WHERE last_seen_at < ?", (cutoff,))
            connection.execute("DELETE FROM traffic_detail_daily_rollups WHERE day_start < ?", (day_start - 400 * 86400,))
            connection.execute("DELETE FROM traffic_flow_daily_rollups WHERE day_start < ?", (day_start - 400 * 86400,))

    def visible_connections(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = set(user.get("allowedDevices") or [])
        if user.get("role") == "admin":
            return self.connections
        return [row for row in self.connections if row["sourceIP"] in allowed]

    def visible_devices(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        allowed = set(user.get("allowedDevices") or [])
        if user.get("role") == "admin":
            return [row for row in self.devices if not _is_infrastructure_source(str(row["ip"]))]
        return [row for row in self.devices if row["ip"] in allowed and not _is_infrastructure_source(str(row["ip"]))]

    def dashboard(self, user: dict[str, Any], timeline_range: str = "live") -> dict[str, Any]:
        connections = self.visible_connections(user)
        allowed = None if user.get("role") == "admin" else set(user.get("allowedDevices") or [])

        def scoped_where(start: int, end: int | None = None) -> tuple[str, list[Any]]:
            conditions = ["ts >= ?"]
            parameters: list[Any] = [start]
            if end is not None:
                conditions.append("ts < ?")
                parameters.append(end)
            if allowed is not None:
                if not allowed:
                    conditions.append("1 = 0")
                else:
                    placeholders = ",".join("?" for _ in allowed)
                    conditions.append(f"device IN ({placeholders})")
                    parameters.extend(sorted(allowed))
            return " AND ".join(conditions), parameters

        def rollup_where(start: int, end: int | None = None) -> tuple[str, list[Any]]:
            conditions = ["day_start >= ?"]
            parameters: list[Any] = [start]
            if end is not None:
                conditions.append("day_start < ?")
                parameters.append(end)
            if allowed is not None:
                if not allowed:
                    conditions.append("1 = 0")
                else:
                    placeholders = ",".join("?" for _ in allowed)
                    conditions.append(f"device IN ({placeholders})")
                    parameters.extend(sorted(allowed))
            return " AND ".join(conditions), parameters

        now = int(time.time())
        month_start = _calendar_start("month", now)
        previous_month_start = _calendar_start("month", month_start - 1)
        month_where, month_params = rollup_where(month_start)
        previous_month_where, previous_month_params = rollup_where(previous_month_start, month_start)
        timeline_start, _, bucket_seconds, time_format = _range_window(timeline_range, now)
        timeline_where, timeline_params = scoped_where(timeline_start)
        with _db() as connection:
            current_total = connection.execute(f"SELECT COALESCE(SUM(up_bytes + down_bytes), 0) total FROM traffic_daily_rollups WHERE {month_where}", month_params).fetchone()["total"]
            previous_total = connection.execute(f"SELECT COALESCE(SUM(up_bytes + down_bytes), 0) total FROM traffic_daily_rollups WHERE {previous_month_where}", previous_month_params).fetchone()["total"]
            device_rows = connection.execute(
                f"SELECT device,SUM(up_bytes + down_bytes) total FROM traffic_daily_rollups WHERE {month_where} AND device != 'unknown' GROUP BY device ORDER BY total DESC",
                month_params,
            ).fetchall()
            exit_rows = connection.execute(
                f"SELECT chain,SUM(up_bytes + down_bytes) total FROM traffic_flow_daily_rollups WHERE {month_where} GROUP BY chain ORDER BY total DESC",
                month_params,
            ).fetchall()
            if timeline_range == "month":
                month_timeline_where, month_timeline_params = rollup_where(timeline_start)
                timeline_rows = connection.execute(
                    f"SELECT day_start bucket,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_daily_rollups WHERE {month_timeline_where} GROUP BY day_start ORDER BY day_start",
                    month_timeline_params,
                ).fetchall()
            else:
                timeline_rows = connection.execute(
                    f"SELECT (ts / ?) * ? bucket,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_samples WHERE {timeline_where} GROUP BY bucket ORDER BY bucket",
                    [bucket_seconds, bucket_seconds, *timeline_params],
                ).fetchall()

        aliases = _aliases()
        devices_by_ip = {row["ip"]: dict(row) for row in self.visible_devices(user)}
        for row in device_rows:
            ip = str(row["device"])
            if _is_infrastructure_source(ip):
                continue
            device = devices_by_ip.setdefault(ip, {"ip": ip, "name": aliases.get(ip, ip), "active": 0, "up": 0, "down": 0, "total": 0})
            device["total"] = int(row["total"] or 0)
        devices = sorted(devices_by_ip.values(), key=lambda item: (item.get("total", 0), item.get("up", 0) + item.get("down", 0)), reverse=True)

        group_names = {_clean_name(name) for name in _config_group_order()}
        chains = _exclusive_exit_usage(exit_rows, int(current_total), group_names)
        timeline = _traffic_timeline(timeline_rows, time_format)
        timeline_summary = _traffic_summary(timeline_rows)
        month_change = round((int(current_total) / int(previous_total) - 1) * 100, 1) if previous_total else 0
        uptime = int(time.monotonic() - self.started)
        return {
            "status": {"online": self.online, "version": self.version, "uptime": f"{uptime // 86400} 天 {uptime % 86400 // 3600} 小时"},
            "totals": {"active": len(connections), "upRate": round(sum(row["upRate"] for row in connections)), "downRate": round(sum(row["downRate"] for row in connections)), "month": int(current_total), "previousMonth": int(previous_total), "monthChange": month_change, "today": int(current_total), "dayChange": month_change},
            "timeline": timeline,
            "timelineRange": timeline_range,
            "timelineBucketSeconds": bucket_seconds,
            "timelineSummary": timeline_summary,
            "devices": devices,
            "chains": chains,
            "connections": connections,
        }


collector = TrafficCollector()


def _device_access_type(address: str) -> str:
    """Classify the source address without relying on a currently open connection."""
    try:
        source = ipaddress.ip_address(address)
        network = ipaddress.ip_network(settings.lan_network, strict=False)
    except ValueError:
        return "unknown"
    return "gateway" if source in network else "proxy"


def _known_devices(user: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge live sources with the retained audit inventory, respecting user scope."""
    allowed = None if user.get("role") == "admin" else set(user.get("allowedDevices") or [])
    aliases = _aliases()
    if allowed is not None and not allowed:
        return []

    conditions = ["device != 'unknown'"]
    values: list[Any] = []
    if allowed is not None:
        placeholders = ",".join("?" for _ in allowed)
        conditions.append(f"device IN ({placeholders})")
        values.extend(sorted(allowed))
    with _db() as connection:
        rows = connection.execute(
            f"""
            SELECT device, MIN(day_start) first_seen, MAX(day_start) last_seen,
                   SUM(up_bytes + down_bytes) historical_total, MAX(active_peak) max_active
            FROM traffic_daily_rollups
            WHERE {' AND '.join(conditions)}
            GROUP BY device
            ORDER BY last_seen DESC
            """,
            values,
        ).fetchall()

    live_devices = collector.visible_devices(user)
    inventory = {str(row["ip"]): dict(row) for row in live_devices}
    now = int(time.time())
    for device in inventory.values():
        device["lastSeen"] = now

    for row in rows:
        address = str(row["device"])
        if _is_infrastructure_source(address):
            continue
        device = inventory.setdefault(
            address,
            {"ip": address, "name": aliases.get(address, address), "active": 0, "up": 0, "down": 0, "total": 0},
        )
        device.update(
            {
                "firstSeen": int(row["first_seen"]),
                "lastSeen": max(int(device.get("lastSeen") or 0), int(row["last_seen"])),
                "historicalTotal": int(row["historical_total"] or 0),
                "maxActive": int(row["max_active"] or 0),
            }
        )

    configured = aliases.keys() if allowed is None else allowed
    for address in configured:
        if _is_infrastructure_source(address):
            continue
        inventory.setdefault(
            address,
            {"ip": address, "name": aliases.get(address, address), "active": 0, "up": 0, "down": 0, "total": 0, "lastSeen": None},
        )
    for address, device in inventory.items():
        device["name"] = aliases.get(address, device.get("name") or address)
        device["sourceType"] = _device_access_type(address)
    return sorted(inventory.values(), key=lambda item: (int(item.get("active") or 0) > 0, int(item.get("lastSeen") or 0)), reverse=True)


def _runtime_exit_name(raw_chain: str | list[Any] | None) -> str:
    if isinstance(raw_chain, list):
        chain = [str(item) for item in raw_chain]
    else:
        try:
            parsed = json.loads(str(raw_chain or "[]"))
            chain = [str(item) for item in parsed] if isinstance(parsed, list) else [str(raw_chain or "")]
        except (json.JSONDecodeError, TypeError):
            chain = [str(raw_chain or "")]
    cleaned = [_clean_name(item) for item in chain if item]
    if "DIRECT" in cleaned:
        return "DIRECT"
    return cleaned[-1] if cleaned else "历史未细分"


def _gateway_runtime() -> dict[str, Any]:
    aliases = _aliases()
    with _db() as connection:
        access_rows = connection.execute(
            """
            SELECT device,SUM(up_bytes) up,SUM(down_bytes) down
            FROM traffic_daily_rollups GROUP BY device
            """
        ).fetchall()
        exit_rows = connection.execute(
            """
            SELECT chain,SUM(up_bytes) up,SUM(down_bytes) down
            FROM traffic_flow_daily_rollups GROUP BY chain
            """
        ).fetchall()
        peak_access_rows = connection.execute(
            """
            SELECT device,MAX(up_bytes * 1.0 / MAX(interval_seconds,1)) up_rate,
                   MAX(down_bytes * 1.0 / MAX(interval_seconds,1)) down_rate
            FROM traffic_samples GROUP BY device
            """
        ).fetchall()
        peak_exit_rows = connection.execute(
            """
            SELECT chain,MAX(up_bytes / 10.0) up_rate,MAX(down_bytes / 10.0) down_rate
            FROM traffic_flow_samples GROUP BY chain
            """
        ).fetchall()

    access: dict[str, dict[str, Any]] = {
        "gateway": {"id": "gateway", "name": "透明网关", "up": 0, "down": 0, "currentUpRate": 0, "currentDownRate": 0, "peakUpRate": 0, "peakDownRate": 0, "devices": set()},
        "proxy": {"id": "proxy", "name": "显式代理", "up": 0, "down": 0, "currentUpRate": 0, "currentDownRate": 0, "peakUpRate": 0, "peakDownRate": 0, "devices": set()},
        "unknown": {"id": "unknown", "name": "未识别来源", "up": 0, "down": 0, "currentUpRate": 0, "currentDownRate": 0, "peakUpRate": 0, "peakDownRate": 0, "devices": set()},
    }
    for row in access_rows:
        device = str(row["device"])
        source_type = "unknown" if device == "unknown" or _is_infrastructure_source(device) else _device_access_type(device)
        target = access[source_type]
        target["up"] += int(row["up"] or 0)
        target["down"] += int(row["down"] or 0)
        if device != "unknown" and not _is_infrastructure_source(device):
            target["devices"].add(aliases.get(device, device))
    for device in collector.devices:
        address = str(device.get("ip") or "")
        source_type = "unknown" if address == "unknown" or _is_infrastructure_source(address) else _device_access_type(address)
        access[source_type]["currentUpRate"] += round(float(device.get("up") or 0))
        access[source_type]["currentDownRate"] += round(float(device.get("down") or 0))
    for row in peak_access_rows:
        source_type = _device_access_type(str(row["device"]))
        access[source_type]["peakUpRate"] = max(access[source_type]["peakUpRate"], round(float(row["up_rate"] or 0)))
        access[source_type]["peakDownRate"] = max(access[source_type]["peakDownRate"], round(float(row["down_rate"] or 0)))

    exits: dict[str, dict[str, Any]] = defaultdict(lambda: {"up": 0, "down": 0, "currentUpRate": 0, "currentDownRate": 0, "peakUpRate": 0, "peakDownRate": 0, "activeConnections": 0})
    for row in exit_rows:
        name = _runtime_exit_name(row["chain"])
        exits[name]["up"] += int(row["up"] or 0)
        exits[name]["down"] += int(row["down"] or 0)
    for connection in collector.connections:
        name = _runtime_exit_name(connection.get("chain"))
        exits[name]["currentUpRate"] += int(connection.get("upRate") or 0)
        exits[name]["currentDownRate"] += int(connection.get("downRate") or 0)
        exits[name]["activeConnections"] += 1
    for row in peak_exit_rows:
        name = _runtime_exit_name(row["chain"])
        exits[name]["peakUpRate"] = max(exits[name]["peakUpRate"], round(float(row["up_rate"] or 0)))
        exits[name]["peakDownRate"] = max(exits[name]["peakDownRate"], round(float(row["down_rate"] or 0)))

    access_items = []
    for item in access.values():
        item["devices"] = sorted(item["devices"])
        item["total"] = item["up"] + item["down"]
        if item["total"] or item["currentUpRate"] or item["currentDownRate"]:
            access_items.append(item)
    exit_items = []
    for name, item in exits.items():
        item.update({"name": name, "total": item["up"] + item["down"]})
        exit_items.append(item)
    exit_items.sort(key=lambda item: (item["total"], item["activeConnections"]), reverse=True)
    uptime = max(0, int(time.time()) - collector.started_at)
    return {
        "startedAt": collector.started_at,
        "uptimeSeconds": uptime,
        "online": collector.online,
        "version": collector.version,
        "total": sum(item["total"] for item in access_items),
        "access": access_items,
        "exits": exit_items[:100],
        "activeExits": sum(1 for item in exit_items if item["activeConnections"]),
    }


def _gateway_events(level: str, query: str, limit: int, offset: int) -> dict[str, Any]:
    conditions: list[str] = []
    parameters: list[Any] = []
    if level != "all":
        conditions.append("level = ?")
        parameters.append(level)
    if query:
        conditions.append("(title LIKE ? OR message LIKE ? OR category LIKE ?)")
        needle = f"%{query[:100]}%"
        parameters.extend((needle, needle, needle))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _db() as connection:
        count = int(connection.execute(f"SELECT COUNT(*) FROM gateway_events {where}", parameters).fetchone()[0])
        rows = connection.execute(
            f"SELECT id,level,category,title,message,detail_json,created_at FROM gateway_events {where} ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
            [*parameters, limit, offset],
        ).fetchall()
    return {
        "events": [
            {
                "id": int(row["id"]), "level": str(row["level"]), "category": str(row["category"]),
                "title": str(row["title"]), "message": str(row["message"]),
                "detail": json.loads(row["detail_json"] or "{}"), "createdAt": int(row["created_at"]),
            }
            for row in rows
        ],
        "total": count,
        "retentionDays": settings.event_retention_days,
    }


def _config_group_order() -> list[str]:
    try:
        payload = yaml.safe_load(settings.config_path.read_text()) or {}
        return [str(group.get("name")) for group in payload.get("proxy-groups", []) if group.get("name")]
    except (OSError, yaml.YAMLError):
        return []


REGIONS = ("美国", "香港", "日本", "台湾", "新加坡", "狮城", "英国")


async def strategy_payload() -> dict[str, Any]:
    payload = await mihomo.get("/proxies")
    proxy_map = payload.get("proxies") or {}
    groups = {name: data for name, data in proxy_map.items() if isinstance(data.get("all"), list)}
    config_order = _config_group_order()
    order = [name for name in config_order if name in groups] + [name for name in groups if name not in config_order]

    def latest_delay(name: str, visited: set[str] | None = None) -> int | None:
        visited = set(visited or ())
        if name in visited:
            return None
        visited.add(name)
        proxy = proxy_map.get(name) or {}
        history = proxy.get("history") or []
        measured = next((int(item["delay"]) for item in reversed(history) if item.get("delay")), None)
        if measured:
            return measured
        selected = proxy.get("now")
        if selected:
            return latest_delay(str(selected), visited)
        candidates = [latest_delay(str(item), visited) for item in (proxy.get("all") or [])]
        available = [delay for delay in candidates if delay]
        return min(available) if available else None

    def delay_level(delay: int | None, alive: bool) -> str:
        if not alive or not delay:
            return "unavailable"
        if delay < 400:
            return "good"
        if delay < 800:
            return "fair"
        return "slow"

    def display_delays(name: str, visited: set[str] | None = None) -> list[int]:
        visited = set(visited or ())
        if name in visited:
            return []
        visited.add(name)
        proxy = proxy_map.get(name) or {}
        if proxy.get("type") == "LoadBalance":
            values = [latest_delay(str(item)) for item in (proxy.get("all") or [])]
            return [value for value in values if value]
        selected = proxy.get("now")
        if selected:
            return display_delays(str(selected), visited)
        measured = latest_delay(name)
        return [measured] if measured else []

    def member_record(member_name: str, selected: str) -> dict[str, Any]:
        proxy = proxy_map.get(member_name) or {}
        alive = proxy.get("alive") is not False
        delay = latest_delay(member_name)
        return {
            "id": member_name,
            "name": _display_node_name(member_name),
            "alive": alive,
            "selected": member_name == selected,
            "delayMs": delay,
            "delay": f"{delay} ms" if delay else "待测速",
            "delayLevel": delay_level(delay, alive),
        }

    def group_record(name: str) -> dict[str, Any]:
        group = groups[name]
        group_type = str(group.get("type") or "")
        selectable = group_type == "Selector"
        mode_label = {
            "Selector": "手动选择",
            "URLTest": "自动测速",
            "LoadBalance": "自动均衡",
            "Fallback": "故障转移",
        }.get(group_type, group_type or "自动策略")
        now = str(group.get("now") or "自动均衡")
        members = [member_record(str(item), now) for item in group.get("all", [])]
        delay_values = display_delays(name)
        delay = min(delay_values) if delay_values else None
        delay_ceiling = max(delay_values) if delay_values else None
        delay_copy = f"{delay}–{delay_ceiling} ms" if delay and delay_ceiling and delay != delay_ceiling else f"{delay} ms" if delay else "待测速"
        available = sum(1 for member in members if member["alive"])
        return {"id": name, "name": _clean_name(name), "type": group_type, "typeLabel": "地区策略" if any(region in name for region in REGIONS) else "入口策略", "modeLabel": mode_label, "selectable": selectable, "now": _display_node_name(now), "nowId": now, "delayMs": delay, "delay": delay_copy, "delayLevel": delay_level(delay_ceiling, available > 0), "health": {"available": available, "total": len(members)}, "members": members, "children": []}

    top_names: list[str] = []
    for keyword in ("节点选择", "手动切换", "手动选择"):
        match = next((name for name in order if keyword in name), None)
        if match and match not in top_names:
            top_names.append(match)
    for region in REGIONS:
        parent = next((name for name in order if region in name and not any(suffix in name for suffix in ("最佳", "智能", "均衡"))), None)
        if parent and parent not in top_names:
            top_names.append(parent)
        if len(top_names) >= 7:
            break

    primary = []
    consumed = set(top_names)
    for name in top_names:
        record = group_record(name)
        if "手动" in name:
            record["typeLabel"] = "手动指定"
        region = next((item for item in REGIONS if item in name), None)
        if region:
            children = [child for child in order if child != name and region in child and any(suffix in child for suffix in ("最佳", "智能", "均衡"))]
            record["children"] = [group_record(child) for child in children]
            consumed.update(children)
        primary.append(record)
    secondary = [group_record(name) for name in order if name not in consumed and name != "GLOBAL"]
    return {"primary": primary, "secondary": secondary, "secondaryCount": len(secondary)}


def _usage_flow(device_name: str, rows: list[Any]) -> dict[str, Any]:
    """Build a Sankey from accumulated bytes, never from an average or instantaneous rate."""
    node_indexes: dict[str, int] = {}
    links: dict[tuple[int, int], int] = defaultdict(int)

    def node(name: str) -> int:
        if name not in node_indexes:
            node_indexes[name] = len(node_indexes)
        return node_indexes[name]

    for row in rows:
        try:
            chain = json.loads(str(row["chain"]))
        except (json.JSONDecodeError, TypeError):
            chain = [str(row["chain"])]
        if not isinstance(chain, list) or not chain:
            chain = ["DIRECT"]
        path = [device_name, str(row["rule"]), *[str(item) for item in chain]]
        value = int(row["up"] or 0) + int(row["down"] or 0)
        if value <= 0:
            continue
        for left, right in zip(path, path[1:]):
            links[(node(left), node(right))] += value
    if not links:
        links[(node(device_name), node("暂无流量记录"))] = 1
    nodes = [None] * len(node_indexes)
    for name, index in node_indexes.items():
        nodes[index] = {"name": name}
    return {"nodes": nodes, "links": [{"source": source, "target": target, "value": value} for (source, target), value in links.items()], "empty": not rows}


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class StrategySelectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    reconnect: bool = True


class DeviceAliasesRequest(BaseModel):
    aliases: dict[str, str] = Field(default_factory=dict)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=512)
    role: str = "viewer"
    allowedDevices: list[str] = Field(default_factory=list, max_length=256)


class UpdateUserRequest(BaseModel):
    password: str | None = Field(default=None, min_length=12, max_length=512)
    role: str | None = None
    allowedDevices: list[str] | None = Field(default=None, max_length=256)


class SubscriptionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=4096)
    interval: int = Field(default=21600, ge=900, le=2_592_000)
    enabled: bool = True


class SubscriptionUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=4096)
    interval: int | None = Field(default=None, ge=900, le=2_592_000)
    enabled: bool | None = None


class RuleSetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=2048)
    policy: str = Field(min_length=1, max_length=300)
    enabled: bool = True
    interval: int = Field(default=86400, ge=300, le=2_592_000)
    behavior: str = Field(default="classical", pattern="^(classical|domain|ipcidr)$")
    format: str = Field(default="text", pattern="^(text|yaml|mrs)$")


class RuleSetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    url: str | None = Field(default=None, min_length=8, max_length=2048)
    policy: str | None = Field(default=None, min_length=1, max_length=300)
    enabled: bool | None = None
    interval: int | None = Field(default=None, ge=300, le=2_592_000)
    behavior: str | None = Field(default=None, pattern="^(classical|domain|ipcidr)$")
    format: str | None = Field(default=None, pattern="^(text|yaml|mrs)$")


class RuleMoveRequest(BaseModel):
    direction: str = Field(pattern="^(up|down)$")


class CustomRuleRequest(BaseModel):
    content: str = Field(min_length=3, max_length=4096)
    placement: str = Field(default="before", pattern="^(before|after)$")
    note: str = Field(default="", max_length=300)


class CustomRuleUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=3, max_length=4096)
    placement: str | None = Field(default=None, pattern="^(before|after)$")
    note: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


def current_user(
    egresscope_session: str | None = Cookie(default=None),
    ssslab_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    user = auth.verify(egresscope_session or ssslab_session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录")
    return user


def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以执行此操作")
    return user


async def _subscription_refresh_loop() -> None:
    while True:
        await asyncio.sleep(60)
        for subscription_id in await asyncio.to_thread(subscriptions.due):
            try:
                item = await subscriptions.refresh(subscription_id)
                if item["gatewayEnabled"]:
                    await rule_workspace.apply()
            except Exception:
                logger.exception("scheduled subscription refresh failed", extra={"subscription_id": subscription_id})


def _mihomo_log_event(level: str, message: str) -> tuple[str, str] | None:
    lowered = message.casefold()
    meaningful = (
        "connection refused", "timeout", "timed out", "network is unreachable", "no route to host",
        "dns", "tun", "interface", "failed", "failure", "error", "fallback", "proxy changed",
    )
    normalized = "error" if level.casefold() == "error" else "warning" if level.casefold() in {"warning", "warn"} else "info"
    if normalized == "info" and not any(token in lowered for token in meaningful):
        return None
    if "connection refused" in lowered or "no route to host" in lowered or "network is unreachable" in lowered:
        title = "节点连接失败"
    elif "timeout" in lowered or "timed out" in lowered:
        title = "节点连接超时"
    elif "dns" in lowered:
        title = "DNS 状态变化"
    elif "tun" in lowered or "interface" in lowered:
        title = "网络接口状态变化"
    else:
        title = "mihomo 运行告警" if normalized != "info" else "mihomo 运行事件"
    return normalized, title


async def _mihomo_event_loop() -> None:
    parsed = urlparse(settings.controller_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = parsed.path.rstrip("/")
    endpoint = f"{scheme}://{parsed.netloc}{path}/logs?level=info"
    headers = {"Authorization": f"Bearer {settings.controller_secret}"} if settings.controller_secret else None
    while True:
        try:
            async with websockets.connect(endpoint, additional_headers=headers, open_timeout=8, close_timeout=5, ping_interval=20) as socket:
                async for raw in socket:
                    try:
                        payload = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    level = str(payload.get("type") or "info")
                    message = str(payload.get("payload") or "").strip()
                    classified = _mihomo_log_event(level, message)
                    if not message or not classified:
                        continue
                    normalized, title = classified
                    digest = hashlib.sha256(f"{normalized}:{message}".encode()).hexdigest()[:16]
                    await asyncio.to_thread(
                        _record_gateway_event,
                        normalized,
                        "mihomo",
                        title,
                        message,
                        {},
                        f"mihomo:{digest}:{int(time.time()) // 30}",
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("mihomo event stream disconnected", exc_info=True)
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.controller_secret and not settings.allow_insecure_controller:
        raise RuntimeError("MIHOMO_CONTROLLER_SECRET is required; set MIHOMO_ALLOW_INSECURE_CONTROLLER=true only for isolated development")
    auth.initialize()
    await asyncio.to_thread(collector.initialize)
    await mihomo.start()
    task = asyncio.create_task(collector.run())
    restore_task = asyncio.create_task(rule_workspace.restore_if_applied())
    subscription_task = asyncio.create_task(_subscription_refresh_loop())
    event_task = asyncio.create_task(_mihomo_event_loop())
    await asyncio.to_thread(_record_gateway_event, "info", "system", "Egresscope 已启动", "运行统计与事件采集已开始。", {"version": "0.2.0"})
    try:
        yield
    finally:
        collector.stop()
        await task
        subscription_task.cancel()
        event_task.cancel()
        if not restore_task.done():
            restore_task.cancel()
        await asyncio.gather(restore_task, subscription_task, event_task, return_exceptions=True)
        await asyncio.to_thread(_record_gateway_event, "info", "system", "Egresscope 已停止", "事件采集已安全结束。")
        await mihomo.close()


app = FastAPI(title="Egresscope API", version="0.2.0", lifespan=lifespan)


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
@app.get("/health/ready")
async def readiness(response: Response) -> dict[str, Any]:
    database_ok = True
    try:
        with _db() as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error:
        database_ok = False
    ready = collector.online and database_ok
    if not ready:
        response.status_code = 503
    return {"status": "ok" if ready else "unavailable", "mihomo": collector.online, "database": database_ok}


@app.get("/api/auth/session")
async def session(
    egresscope_session: str | None = Cookie(default=None),
    ssslab_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    return {"required": True, "user": auth.verify(egresscope_session or ssslab_session)}


@app.post("/api/auth/login")
async def login(request: Request, credentials: LoginRequest, response: Response) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{credentials.username.strip().casefold()}"
    retry_after = login_limiter.check(rate_key)
    if retry_after:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试", headers={"Retry-After": str(retry_after)})
    user = await asyncio.to_thread(auth.authenticate, credentials.username, credentials.password)
    if not user:
        login_limiter.failure(rate_key)
        await asyncio.sleep(.25)
        raise HTTPException(status_code=401, detail="用户名或密码不正确")
    login_limiter.success(rate_key)
    response.set_cookie("egresscope_session", auth.token(user), httponly=True, secure=settings.secure_cookie, samesite="strict", max_age=12 * 3600, path="/")
    return {"user": user}


@app.post("/api/auth/logout")
async def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie("egresscope_session", path="/")
    response.delete_cookie("ssslab_session", path="/")
    return {"ok": True}


@app.get("/api/users")
async def users(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    return {"users": await asyncio.to_thread(auth.list_users)}


@app.post("/api/users", status_code=201)
async def create_user(request: CreateUserRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        user = await asyncio.to_thread(auth.create_user, request.username, request.password, request.role, request.allowedDevices)
        return {"user": user}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/users/{user_id}")
async def update_user(user_id: int, request: UpdateUserRequest, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    if user_id == admin["id"] and request.role == "viewer":
        raise HTTPException(status_code=409, detail="不能降低当前登录管理员自己的权限")
    try:
        user = await asyncio.to_thread(auth.update_user, user_id, request.role, request.allowedDevices, request.password)
        return {"user": user}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/subscriptions")
async def subscription_list(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return await asyncio.to_thread(subscriptions.list, user)


@app.post("/api/subscriptions", status_code=201)
async def create_subscription(request: SubscriptionRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        url = await _validate_subscription_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        subscription_id = await asyncio.to_thread(subscriptions.create, user, request.name, url, request.interval, request.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        item = await subscriptions.refresh(subscription_id, user)
    except Exception:
        item = await asyncio.to_thread(subscriptions.get, subscription_id, user)
    return {"subscription": item}


@app.patch("/api/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: str, request: SubscriptionUpdateRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    updates = request.model_dump(exclude_none=True)
    if "url" in updates:
        try:
            updates["url"] = await _validate_subscription_url(str(updates["url"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        await asyncio.to_thread(subscriptions.update, subscription_id, user, updates)
        return {"subscription": await asyncio.to_thread(subscriptions.get, subscription_id, user)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在或无权访问") from exc


@app.delete("/api/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, bool]:
    try:
        was_gateway = await asyncio.to_thread(subscriptions.delete, subscription_id, user)
        if was_gateway:
            await rule_workspace.apply()
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在或无权访问") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="订阅已删除，但网关恢复基础节点配置失败") from exc


@app.post("/api/subscriptions/{subscription_id}/refresh")
async def refresh_subscription(subscription_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        item = await subscriptions.refresh(subscription_id, user)
        if item["gatewayEnabled"]:
            await rule_workspace.apply()
        return {"subscription": item}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在或无权访问") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="订阅源暂时无法访问") from exc


@app.post("/api/subscriptions/{subscription_id}/rotate-token")
async def rotate_subscription_token(subscription_id: str, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    try:
        item = await asyncio.to_thread(subscriptions.rotate_token, subscription_id, user)
        return {"subscription": item}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在或无权访问") from exc


@app.post("/api/subscriptions/{subscription_id}/activate")
async def activate_subscription(subscription_id: str, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    previous = await asyncio.to_thread(subscriptions.gateway_id)
    try:
        await asyncio.to_thread(subscriptions.activate, subscription_id)
        result = await rule_workspace.apply()
        await asyncio.to_thread(_record_audit, admin["id"], "activate", "subscription", subscription_id)
        return {"ok": True, "gatewaySubscription": subscription_id, "revision": result["revision"]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在") from exc
    except (ValueError, httpx.HTTPError) as exc:
        try:
            if previous and previous != subscription_id:
                await asyncio.to_thread(subscriptions.activate, previous)
            elif previous != subscription_id:
                await asyncio.to_thread(subscriptions.deactivate, subscription_id)
            await rule_workspace.apply(restoring=True)
        except Exception:
            logger.exception("failed to restore gateway subscription after activation error")
        status = 422 if isinstance(exc, ValueError) else 502
        detail = str(exc) if isinstance(exc, ValueError) else "mihomo 拒绝了订阅节点配置，原网关配置保持不变"
        raise HTTPException(status_code=status, detail=detail) from exc


@app.post("/api/subscriptions/{subscription_id}/deactivate")
async def deactivate_subscription(subscription_id: str, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    previous = await asyncio.to_thread(subscriptions.gateway_id)
    try:
        await asyncio.to_thread(subscriptions.deactivate, subscription_id)
        result = await rule_workspace.apply()
        await asyncio.to_thread(_record_audit, admin["id"], "deactivate", "subscription", subscription_id)
        return {"ok": True, "revision": result["revision"]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在") from exc
    except (ValueError, httpx.HTTPError) as exc:
        try:
            if previous:
                await asyncio.to_thread(subscriptions.activate, previous)
                await rule_workspace.apply(restoring=True)
        except Exception:
            logger.exception("failed to restore gateway subscription after deactivation error")
        status = 422 if isinstance(exc, ValueError) else 502
        detail = str(exc) if isinstance(exc, ValueError) else "网关恢复基础节点配置失败"
        raise HTTPException(status_code=status, detail=detail) from exc


@app.get("/sub/{token}/clash.yaml", response_class=PlainTextResponse)
@app.get("/sub/{token}/mihomo.yaml", response_class=PlainTextResponse, include_in_schema=False)
async def clash_subscription_delivery(token: str) -> PlainTextResponse:
    try:
        payload = await asyncio.to_thread(subscriptions.delivery, token, "clash")
        return PlainTextResponse(
            payload,
            media_type="application/yaml",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'inline; filename="egresscope-clash.yaml"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在、尚未刷新或已停用") from exc


@app.get("/sub/{token}/surge.conf", response_class=PlainTextResponse)
async def surge_subscription_delivery(token: str, request: Request) -> PlainTextResponse:
    try:
        payload = await asyncio.to_thread(subscriptions.delivery, token, "surge", str(request.url))
        return PlainTextResponse(
            payload,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'inline; filename="egresscope-surge.conf"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="订阅不存在、尚未刷新或已停用") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/dashboard")
async def dashboard(
    range: str = Query(default="live", pattern="^(live|1h|6h|24h|7d|14d|month)$"),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return collector.dashboard(user, range)


@app.get("/api/connections")
async def connections(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return {"connections": collector.visible_connections(user)}


def _connection_statistics(
    user: dict[str, Any],
    range_key: str,
    status: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    now = int(time.time())
    start = now - CONNECTION_HISTORY_RANGES[range_key]
    allowed = None if user.get("role") == "admin" else set(user.get("allowedDevices") or [])
    scope_conditions = ["last_seen_at >= ?"]
    scope_parameters: list[Any] = [start]
    if INFRASTRUCTURE_SOURCE_IPS:
        placeholders = ",".join("?" for _ in INFRASTRUCTURE_SOURCE_IPS)
        scope_conditions.append(f"device NOT IN ({placeholders})")
        scope_parameters.extend(sorted(INFRASTRUCTURE_SOURCE_IPS))
    if allowed is not None:
        if not allowed:
            scope_conditions.append("1 = 0")
        else:
            placeholders = ",".join("?" for _ in allowed)
            scope_conditions.append(f"device IN ({placeholders})")
            scope_parameters.extend(sorted(allowed))
    scope_where = " AND ".join(scope_conditions)
    status_condition = "ended_at IS NULL" if status == "active" else "ended_at IS NOT NULL" if status == "history" else "1 = 1"
    aliases = _aliases()
    with _db() as connection:
        summary = connection.execute(
            f"""
            SELECT COUNT(*) total,
                   SUM(CASE WHEN ended_at IS NULL THEN 1 ELSE 0 END) active,
                   SUM(CASE WHEN ended_at IS NOT NULL THEN 1 ELSE 0 END) history,
                   COUNT(DISTINCT device) devices,
                   COALESCE(SUM(upload_bytes + download_bytes), 0) traffic
            FROM connection_sessions WHERE {scope_where}
            """,
            scope_parameters,
        ).fetchone()
        matched = connection.execute(
            f"SELECT COUNT(*) count FROM connection_sessions WHERE {scope_where} AND {status_condition}",
            scope_parameters,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT id,device,host,destination_ip,destination_port,network,rule,chain,
                   started_at,last_seen_at,ended_at,upload_bytes,download_bytes,termination_reason
            FROM connection_sessions
            WHERE {scope_where} AND {status_condition}
            ORDER BY CASE WHEN ended_at IS NULL THEN 0 ELSE 1 END, last_seen_at DESC
            LIMIT ? OFFSET ?
            """,
            [*scope_parameters, limit, offset],
        ).fetchall()
    live = {row["id"]: row for row in collector.visible_connections(user)}
    sessions = []
    for row in rows:
        source_ip = str(row["device"])
        active_row = live.get(str(row["id"]))
        chain_value = row["chain"] or "[]"
        try:
            chain = [str(item) for item in json.loads(chain_value)]
        except (json.JSONDecodeError, TypeError):
            chain = [str(chain_value)] if chain_value else ["DIRECT"]
        started_at = int(row["started_at"] or row["last_seen_at"] or now)
        ended_at = int(row["ended_at"]) if row["ended_at"] is not None else None
        duration_seconds = max(0, (ended_at or now) - started_at)
        sessions.append(
            {
                "id": str(row["id"]),
                "device": aliases.get(source_ip, source_ip),
                "sourceIP": source_ip,
                "host": str(row["host"] or ""),
                "destinationIP": str(row["destination_ip"] or ""),
                "destinationPort": str(row["destination_port"] or ""),
                "network": str(row["network"] or "tcp"),
                "rule": str(row["rule"] or "Match"),
                "chain": chain or ["DIRECT"],
                "startedAt": started_at,
                "lastSeenAt": int(row["last_seen_at"] or started_at),
                "endedAt": ended_at,
                "status": "active" if ended_at is None else "ended",
                "upload": int(row["upload_bytes"] or 0),
                "download": int(row["download_bytes"] or 0),
                "upRate": int(active_row.get("upRate", 0)) if active_row else 0,
                "downRate": int(active_row.get("downRate", 0)) if active_row else 0,
                "durationSeconds": duration_seconds,
                "terminationReason": row["termination_reason"],
            }
        )
    return {
        "range": range_key,
        "status": status,
        "retentionDays": settings.retention_days,
        "summary": {
            "active": int(summary["active"] or 0),
            "history": int(summary["history"] or 0),
            "total": int(summary["total"] or 0),
            "devices": int(summary["devices"] or 0),
            "traffic": int(summary["traffic"] or 0),
            "matched": int(matched["count"] or 0),
        },
        "sessions": sessions,
    }


@app.get("/api/connection-statistics")
async def connection_statistics(
    range: str = Query(default="24h", pattern="^(1h|6h|24h|7d|30d)$"),
    status: str = Query(default="active", pattern="^(active|history|all)$"),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return await asyncio.to_thread(_connection_statistics, user, range, status, limit, offset)


@app.delete("/api/connections")
async def close_all_connections(admin: dict[str, Any] = Depends(admin_user)) -> dict[str, bool]:
    try:
        await mihomo.delete("/connections")
        await asyncio.to_thread(_record_audit, admin["id"], "terminate_all", "connection", None)
        return {"ok": True}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="无法终止全部连接") from exc


@app.delete("/api/connections/{connection_id}")
async def close_connection(connection_id: str, admin: dict[str, Any] = Depends(admin_user)) -> dict[str, bool]:
    try:
        await mihomo.delete(f"/connections/{quote(connection_id, safe='')}")
        with _db() as connection:
            connection.execute(
                "UPDATE connection_sessions SET ended_at = ?, termination_reason = 'admin', terminated_by = ? WHERE id = ?",
                (int(time.time()), admin["id"], connection_id),
            )
        await asyncio.to_thread(_record_audit, admin["id"], "terminate", "connection", connection_id)
        return {"ok": True}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="无法终止该连接") from exc


@app.get("/api/device-aliases")
async def device_aliases(user: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    aliases = {address: label for address, label in _aliases().items() if not _is_infrastructure_source(address)}
    if user.get("role") != "admin":
        allowed = set(user.get("allowedDevices") or [])
        aliases = {address: label for address, label in aliases.items() if address in allowed}
    return {"aliases": aliases, "devices": await asyncio.to_thread(_known_devices, user)}


@app.get("/api/gateway/runtime")
async def gateway_runtime(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    return await asyncio.to_thread(_gateway_runtime)


@app.get("/api/gateway/events")
async def gateway_events(
    level: str = Query(default="all", pattern="^(all|info|warning|error)$"),
    query: str = Query(default="", max_length=100),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    return await asyncio.to_thread(_gateway_events, level, query.strip(), limit, offset)


@app.put("/api/device-aliases")
async def update_device_aliases(request: DeviceAliasesRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    normalized: dict[str, str] = {}
    for address, alias in request.aliases.items():
        try:
            parsed = ipaddress.ip_address(address.strip())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"无效的设备 IP：{address}") from exc
        label = alias.strip()
        if not label or len(label) > 80:
            raise HTTPException(status_code=422, detail=f"设备 {address} 的名称需为 1–80 个字符")
        normalized[str(parsed)] = label
    settings.device_aliases_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = settings.device_aliases_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, settings.device_aliases_path)
    return {"aliases": normalized}


@app.get("/api/audit")
async def audit_query(
    from_ts: int = Query(default_factory=lambda: int(time.time()) - 86400),
    to_ts: int = Query(default_factory=lambda: int(time.time())),
    device: str | None = None,
    chain: str | None = None,
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if to_ts <= from_ts or to_ts - from_ts > settings.retention_days * 86400:
        raise HTTPException(status_code=422, detail=f"查询范围必须在 1 秒到 {settings.retention_days} 天之间")
    conditions = ["ts >= ?", "ts <= ?"]
    values: list[Any] = [from_ts, to_ts]
    if device:
        conditions.append("device = ?")
        values.append(device)
    if chain:
        conditions.append("chain = ?")
        values.append(chain)
    allowed = user.get("allowedDevices") or []
    if user["role"] != "admin":
        if not allowed:
            return {"timeline": [], "devices": [], "chains": []}
        conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
        values.extend(allowed)
    where = " AND ".join(conditions)
    with _db() as connection:
        timeline_rows = connection.execute(
            f"SELECT (ts / 60) * 60 minute, SUM(up_bytes) up, SUM(down_bytes) down FROM traffic_samples WHERE {where} GROUP BY minute ORDER BY minute",
            values,
        ).fetchall()
        device_rows = connection.execute(
            f"SELECT device, SUM(up_bytes) up, SUM(down_bytes) down, MAX(active) active FROM traffic_samples WHERE {where} GROUP BY device ORDER BY up + down DESC LIMIT 50",
            values,
        ).fetchall()
        chain_rows = connection.execute(
            f"SELECT chain, SUM(up_bytes) up, SUM(down_bytes) down FROM traffic_samples WHERE {where} GROUP BY chain ORDER BY up + down DESC LIMIT 50",
            values,
        ).fetchall()
    return {
        "timeline": [{"time": _display_datetime(row["minute"]).isoformat(), "up": row["up"] / 60, "down": row["down"] / 60} for row in timeline_rows],
        "devices": [dict(row) for row in device_rows if not _is_infrastructure_source(str(row["device"]))],
        "chains": [dict(row) for row in chain_rows],
    }


ANALYSIS_RANGES = {key: value[0] for key, value in DASHBOARD_TIMELINE_RANGES.items()}
SERVICE_ICONS = {"OpenAI": "openai", "Telegram": "telegram", "X (Twitter)": "x", "GitHub": "github", "Microsoft": "microsoft", "Apple": "apple", "Google": "google", "Cloudflare": "cloudflare", "Direct IP": "direct"}


@app.get("/api/traffic-analysis")
async def traffic_analysis(
    range: str = Query(default="24h"),
    device: str | None = None,
    groupBy: str = Query(default="service", pattern="^(service|target)$"),
    metric: str = Query(default="traffic", pattern="^(traffic|connections)$"),
    service: str | None = None,
    attributionPeriod: str = Query(default="day", pattern="^(hour|day|month)$"),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if range not in ANALYSIS_RANGES:
        raise HTTPException(status_code=422, detail="不支持的时间范围")
    started_at, seconds, _, _ = _range_window(range)
    use_daily = range == "month"
    if not use_daily and seconds > settings.retention_days * 86400:
        raise HTTPException(status_code=422, detail=f"当前审计数据仅保留 {settings.retention_days} 天")
    allowed = set(user.get("allowedDevices") or [])
    if user["role"] != "admin" and device and device not in allowed:
        raise HTTPException(status_code=404, detail="设备不存在或无权查看")
    time_column = "day_start" if use_daily else "ts"
    source_table = "traffic_detail_daily_rollups" if use_daily else "traffic_detail_samples"
    conditions = [f"{time_column} >= ?"]
    values: list[Any] = [started_at]
    if device:
        conditions.append("device = ?")
        values.append(device)
    elif user["role"] != "admin":
        if not allowed:
            return {"range": range, "groupBy": groupBy, "metric": metric, "totals": {"up": 0, "down": 0, "traffic": 0, "connections": 0}, "items": [], "generatedAt": int(time.time())}
        conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
        values.extend(sorted(allowed))
    where = " AND ".join(conditions)
    primary = "service" if groupBy == "service" else "host"
    with _db() as connection:
        rows = connection.execute(
            f"SELECT {primary} name, MIN(service) service, SUM(up_bytes) up, SUM(down_bytes) down, SUM(connections) connections FROM {source_table} WHERE {where} AND exit_mode != 'direct' GROUP BY {primary}",
            values,
        ).fetchall()
        detail_rows = connection.execute(
            f"SELECT service, host, SUM(up_bytes) up, SUM(down_bytes) down, SUM(connections) connections FROM {source_table} WHERE {where} AND exit_mode != 'direct' GROUP BY service, host ORDER BY up + down DESC",
            values,
        ).fetchall() if groupBy == "service" else []
        proxy_device_rows = connection.execute(
            f"SELECT DISTINCT device FROM {source_table} WHERE {where} AND exit_mode != 'direct' AND device != 'unknown'",
            values,
        ).fetchall()
        total_table = "traffic_daily_rollups" if use_daily else "traffic_samples"
        total_time = "day_start" if use_daily else "ts"
        total_conditions = [f"{total_time} >= ?"]
        total_values: list[Any] = [started_at]
        if device:
            total_conditions.append("device = ?")
            total_values.append(device)
        elif user["role"] != "admin":
            if not allowed:
                total_conditions.append("1 = 0")
            else:
                total_conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
                total_values.extend(sorted(allowed))
        total_where = " AND ".join(total_conditions)
        total_row = connection.execute(
            f"SELECT COALESCE(SUM(up_bytes),0) up,COALESCE(SUM(down_bytes),0) down FROM {total_table} WHERE {total_where}",
            total_values,
        ).fetchone()
        flow_table = "traffic_class_daily_rollups" if use_daily else "traffic_flow_samples"
        flow_time = "day_start" if use_daily else "ts"
        direct_predicate = "route_class = 'direct'" if use_daily else "instr(chain, 'DIRECT') > 0"
        direct_conditions = [f"{flow_time} >= ?", direct_predicate]
        direct_values: list[Any] = [started_at]
        if device:
            direct_conditions.append("device = ?")
            direct_values.append(device)
        elif user["role"] != "admin":
            if not allowed:
                direct_conditions.append("1 = 0")
            else:
                direct_conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
                direct_values.extend(sorted(allowed))
        direct_row = connection.execute(
            f"SELECT COALESCE(SUM(up_bytes),0) up,COALESCE(SUM(down_bytes),0) down FROM {flow_table} WHERE {' AND '.join(direct_conditions)}",
            direct_values,
        ).fetchone()
    total_up, total_down = int(total_row["up"] or 0), int(total_row["down"] or 0)
    direct_up = min(total_up, int(direct_row["up"] or 0))
    direct_down = min(total_down, int(direct_row["down"] or 0))
    proxy_up, proxy_down = max(0, total_up - direct_up), max(0, total_down - direct_down)
    total_connections = sum(int(row["connections"] or 0) for row in rows)
    raw_detail_total = sum(int(row["up"] or 0) + int(row["down"] or 0) for row in rows)
    detail_scale = (proxy_up + proxy_down) / raw_detail_total if raw_detail_total else 0
    denominator = total_connections if metric == "connections" else proxy_up + proxy_down
    details: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in detail_rows:
        details[row["service"]].append({"host": row["host"], "up": round(int(row["up"] or 0) * detail_scale), "down": round(int(row["down"] or 0) * detail_scale), "connections": int(row["connections"] or 0)})
    items = []
    for row in rows:
        up, down, connections_count = round(int(row["up"] or 0) * detail_scale), round(int(row["down"] or 0) * detail_scale), int(row["connections"] or 0)
        value = connections_count if metric == "connections" else up + down
        service_name = row["name"] if groupBy == "service" else row["service"]
        items.append({"id": row["name"], "name": row["name"], "service": service_name, "icon": SERVICE_ICONS.get(service_name, "globe"), "up": up, "down": down, "traffic": up + down, "connections": connections_count, "percent": round(value / denominator * 100, 1) if denominator else 0, "details": details.get(row["name"], [])[:12]})
    items.sort(key=lambda item: item["connections"] if metric == "connections" else item["traffic"], reverse=True)
    matching_item = next((item for item in items if service and (item["name"] == service or item["service"] == service)), None)
    selected_service = matching_item["service"] if matching_item else (items[0]["service"] if items else "")
    attribution = {"service": selected_service, "period": attributionPeriod, "buckets": [], "devices": []}
    if selected_service:
        now = int(time.time())
        if attributionPeriod == "hour":
            attr_table, attr_time, attr_start, attr_bucket = "traffic_detail_samples", "ts", now - 24 * 3600, 3600
            bucket_expr = f"({attr_time} / {attr_bucket}) * {attr_bucket}"
        elif attributionPeriod == "day":
            attr_table, attr_time, attr_start = "traffic_detail_daily_rollups", "day_start", _calendar_start("day", now - 6 * 86400)
            bucket_expr = attr_time
        else:
            attr_table, attr_time, attr_start = "traffic_detail_daily_rollups", "day_start", _calendar_start("year", now) - 32 * 86400
            bucket_expr = f"strftime('%Y-%m', {attr_time}, 'unixepoch', '+8 hours')"
        attr_conditions = [f"{attr_time} >= ?", "service = ?", "exit_mode != 'direct'"]
        attr_values: list[Any] = [attr_start, selected_service]
        if device:
            attr_conditions.append("device = ?")
            attr_values.append(device)
        elif user["role"] != "admin":
            if not allowed:
                attr_conditions.append("1 = 0")
            else:
                attr_conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
                attr_values.extend(sorted(allowed))
        with _db() as connection:
            attr_rows = connection.execute(
                f"SELECT {bucket_expr} bucket,device,SUM(up_bytes + down_bytes) total FROM {attr_table} WHERE {' AND '.join(attr_conditions)} GROUP BY bucket,device ORDER BY bucket",
                attr_values,
            ).fetchall()
        aliases = _aliases()
        bucket_map: dict[str, dict[str, Any]] = {}
        device_totals: dict[str, int] = defaultdict(int)
        for row in attr_rows:
            raw_bucket = row["bucket"]
            if attributionPeriod == "month":
                label = str(raw_bucket)
            else:
                label = _display_datetime(int(raw_bucket)).strftime("%H:%M" if attributionPeriod == "hour" else "%m-%d")
            bucket = bucket_map.setdefault(str(raw_bucket), {"time": label, "values": {}})
            amount = round(int(row["total"] or 0) * detail_scale)
            bucket["values"][str(row["device"])] = amount
            device_totals[str(row["device"])] += amount
        attributed_total = sum(device_totals.values()) or 1
        attribution = {
            "service": selected_service,
            "period": attributionPeriod,
            "buckets": list(bucket_map.values()),
            "devices": [
                {"ip": ip, "name": aliases.get(ip, ip), "traffic": amount, "percent": round(amount / attributed_total * 100, 1)}
                for ip, amount in sorted(device_totals.items(), key=lambda item: item[1], reverse=True)[:6]
                if not _is_infrastructure_source(ip)
            ],
        }
    return {
        "range": range,
        "groupBy": groupBy,
        "metric": metric,
        "totals": {
            "up": total_up,
            "down": total_down,
            "traffic": total_up + total_down,
            "connections": total_connections,
            "proxyUp": proxy_up,
            "proxyDown": proxy_down,
            "proxy": proxy_up + proxy_down,
            "directUp": direct_up,
            "directDown": direct_down,
            "direct": direct_up + direct_down,
            "proxyDevices": sum(1 for row in proxy_device_rows if not _is_infrastructure_source(str(row["device"]))),
        },
        "items": items[:50],
        "attribution": attribution,
        "generatedAt": int(time.time()),
    }


@app.get("/api/traffic-history")
async def traffic_history(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    allowed = set(user.get("allowedDevices") or [])
    conditions: list[str] = []
    values: list[Any] = []
    if user["role"] != "admin":
        if not allowed:
            return {"currentMonth": 0, "previousMonth": 0, "currentYear": 0, "previousYear": 0, "recordedTotal": 0, "months": [], "years": []}
        conditions.append(f"device IN ({','.join('?' for _ in allowed)})")
        values.extend(sorted(allowed))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with _db() as connection:
        rows = connection.execute(
            f"SELECT day_start,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_daily_rollups {where} GROUP BY day_start ORDER BY day_start",
            values,
        ).fetchall()
        direct_conditions = [*conditions, "route_class = 'direct'"]
        direct_where = f"WHERE {' AND '.join(direct_conditions)}"
        direct_rows = connection.execute(
            f"SELECT day_start,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_class_daily_rollups {direct_where} GROUP BY day_start ORDER BY day_start",
            values,
        ).fetchall()
    direct_by_day = {int(row["day_start"]): (int(row["up"] or 0), int(row["down"] or 0)) for row in direct_rows}
    month_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"up": 0, "down": 0})
    year_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"up": 0, "down": 0})
    for row in rows:
        moment = _display_datetime(int(row["day_start"]))
        month_key, year_key = moment.strftime("%Y-%m"), moment.strftime("%Y")
        direct_up, direct_down = direct_by_day.get(int(row["day_start"]), (0, 0))
        proxy_up = max(0, int(row["up"] or 0) - direct_up)
        proxy_down = max(0, int(row["down"] or 0) - direct_down)
        for totals in (month_totals[month_key], year_totals[year_key]):
            totals["up"] += proxy_up
            totals["down"] += proxy_down

    def period_rows(source: dict[str, dict[str, int]], monthly: bool) -> list[dict[str, Any]]:
        result = []
        for period in sorted(source, reverse=True):
            totals = source[period]
            result.append(
                {
                    "period": period,
                    "label": f"{period[:4]} 年 {int(period[5:])} 月" if monthly else f"{period} 年",
                    "up": totals["up"],
                    "down": totals["down"],
                    "total": totals["up"] + totals["down"],
                }
            )
        return result

    now = _display_datetime()
    current_month = now.strftime("%Y-%m")
    previous_month = _display_datetime(_calendar_start("month") - 1).strftime("%Y-%m")
    current_year = now.strftime("%Y")
    previous_year = str(int(current_year) - 1)
    months, years = period_rows(month_totals, True), period_rows(year_totals, False)
    total_for = lambda source, key: sum(source.get(key, {}).values())
    return {
        "currentMonth": total_for(month_totals, current_month),
        "previousMonth": total_for(month_totals, previous_month),
        "currentYear": total_for(year_totals, current_year),
        "previousYear": total_for(year_totals, previous_year),
        "recordedTotal": sum(item["total"] for item in years),
        "months": months,
        "years": years,
    }


@app.get("/api/devices/{device_ip}")
async def device(
    device_ip: str,
    range: str = Query(default="live", pattern="^(live|1h|6h|24h|7d|14d|month)$"),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    if _is_infrastructure_source(device_ip):
        raise HTTPException(status_code=404, detail="设备不存在或无权查看")
    visible = await asyncio.to_thread(_known_devices, user)
    selected = next((row for row in visible if row["ip"] == device_ip), None)
    if not selected:
        raise HTTPException(status_code=404, detail="设备不存在或无权查看")
    connections = collector.visible_connections(user)
    relevant = [row for row in connections if row["sourceIP"] == device_ip]
    destinations: dict[str, dict[str, Any]] = {}
    for row in relevant:
        key = row["host"] or row["destinationIP"]
        item = destinations.setdefault(key, {"host": key, "rule": row["rule"], "rate": 0, "up": 0, "down": 0, "traffic": 0, "connections": 0})
        item["rate"] += row["upRate"] + row["downRate"]
        item["up"] += int(row.get("upload") or 0)
        item["down"] += int(row.get("download") or 0)
        item["traffic"] = item["up"] + item["down"]
        item["connections"] += 1
    started_at, range_seconds, bucket_seconds, time_format = _range_window(range)
    with _db() as connection:
        if range == "month":
            history = connection.execute(
                "SELECT day_start bucket, SUM(up_bytes) up, SUM(down_bytes) down "
                "FROM traffic_daily_rollups WHERE device = ? AND day_start >= ? GROUP BY day_start ORDER BY day_start",
                (device_ip, started_at),
            ).fetchall()
            historical_destinations = connection.execute(
                "SELECT host, MIN(service) service, SUM(up_bytes) up, SUM(down_bytes) down, SUM(connections) connections "
                "FROM traffic_detail_daily_rollups WHERE device = ? AND day_start >= ? GROUP BY host ORDER BY up + down DESC LIMIT 100",
                (device_ip, started_at),
            ).fetchall()
            flow_rows = connection.execute(
                "SELECT rule,chain,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_flow_daily_rollups "
                "WHERE device = ? AND day_start >= ? GROUP BY rule,chain ORDER BY up + down DESC",
                (device_ip, started_at),
            ).fetchall()
        else:
            history = connection.execute(
                "SELECT (ts / ?) * ? bucket, SUM(up_bytes) up, SUM(down_bytes) down "
                "FROM traffic_samples WHERE device = ? AND ts >= ? GROUP BY bucket ORDER BY bucket",
                (bucket_seconds, bucket_seconds, device_ip, started_at),
            ).fetchall()
            historical_destinations = connection.execute(
                "SELECT host, MIN(service) service, SUM(up_bytes) up, SUM(down_bytes) down, SUM(connections) connections "
                "FROM traffic_detail_samples WHERE device = ? AND ts >= ? GROUP BY host ORDER BY up + down DESC LIMIT 100",
                (device_ip, started_at),
            ).fetchall()
            flow_rows = connection.execute(
                "SELECT rule,chain,SUM(up_bytes) up,SUM(down_bytes) down FROM traffic_flow_samples "
                "WHERE device = ? AND ts >= ? GROUP BY rule,chain ORDER BY up + down DESC",
                (device_ip, started_at),
            ).fetchall()
        if not flow_rows:
            fallback_table = "traffic_daily_rollups" if range == "month" else "traffic_samples"
            fallback_time = "day_start" if range == "month" else "ts"
            flow_rows = connection.execute(
                f"SELECT '历史汇总' rule,json_array(chain) chain,SUM(up_bytes) up,SUM(down_bytes) down FROM {fallback_table} "
                f"WHERE device = ? AND {fallback_time} >= ? GROUP BY chain ORDER BY up + down DESC",
                (device_ip, started_at),
            ).fetchall()
    timeline = _traffic_timeline(history, time_format)
    range_summary = _traffic_summary(history)
    sampled_seconds = max(1, min(range_seconds, (int(history[-1]["bucket"]) - int(history[0]["bucket"]) + bucket_seconds) if history else bucket_seconds))
    range_destinations = [
        {
            "host": row["host"],
            "rule": row["service"],
            "rate": round((int(row["up"] or 0) + int(row["down"] or 0)) / sampled_seconds),
            "up": int(row["up"] or 0),
            "down": int(row["down"] or 0),
            "traffic": int(row["up"] or 0) + int(row["down"] or 0),
            "connections": int(row["connections"] or 0),
        }
        for row in historical_destinations
    ]
    return {
        **selected,
        "vendor": "局域网设备",
        "range": range,
        "flow": _usage_flow(str(selected.get("name") or device_ip), flow_rows),
        "flowRange": range,
        "destinations": (sorted(destinations.values(), key=lambda item: item["rate"], reverse=True)[:8] or range_destinations) if range == "live" else range_destinations,
        "timeline": timeline,
        "timelineBucketSeconds": bucket_seconds,
        "rangeSummary": range_summary,
    }


@app.get("/api/devices/{device_ip}/sessions")
async def device_sessions(
    device_ip: str,
    range: str = Query(default="24h", pattern="^(live|1h|6h|24h|7d|14d|month)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    allowed = set(user.get("allowedDevices") or [])
    if _is_infrastructure_source(device_ip) or (user["role"] != "admin" and device_ip not in allowed):
        raise HTTPException(status_code=404, detail="设备不存在或无权查看")
    started_at, _, _, _ = _range_window(range)
    with _db() as connection:
        rows = connection.execute(
            """
            SELECT id,device,host,destination_ip,destination_port,network,rule,chain,
                   started_at,last_seen_at,ended_at,upload_bytes,download_bytes,termination_reason
            FROM connection_sessions
            WHERE device = ? AND last_seen_at >= ?
            ORDER BY last_seen_at DESC LIMIT ?
            """,
            (device_ip, started_at, limit),
        ).fetchall()
    return {
        "device": device_ip,
        "range": range,
        "sessions": [
            {
                **dict(row),
                "chain": json.loads(row["chain"] or "[]"),
                "traffic": int(row["upload_bytes"] or 0) + int(row["download_bytes"] or 0),
            }
            for row in rows
        ],
    }


@app.get("/api/strategies")
async def strategies(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        return await strategy_payload()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="mihomo 策略接口当前不可用") from exc


def _affected_connection_ids(payload: dict[str, Any], group_name: str) -> list[str]:
    return [
        str(connection["id"])
        for connection in payload.get("connections", [])
        if connection.get("id") and group_name in [str(item) for item in (connection.get("chains") or [])]
    ]


@app.put("/api/strategies/{group_name}")
async def select_strategy(group_name: str, request: StrategySelectRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以切换策略")
    started = time.monotonic()
    try:
        proxy_payload = await mihomo.get("/proxies")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="mihomo 策略接口当前不可用") from exc
    group = (proxy_payload.get("proxies") or {}).get(group_name)
    if not isinstance(group, dict):
        raise HTTPException(status_code=404, detail="策略组不存在")
    group_type = str(group.get("type") or "")
    if group_type != "Selector":
        mode = {"LoadBalance": "自动均衡", "URLTest": "自动测速", "Fallback": "故障转移"}.get(group_type, "自动")
        raise HTTPException(status_code=409, detail=f"{_clean_name(group_name)}是{mode}组，由 mihomo 自动选择节点，不能手动切换")
    members = [str(item) for item in (group.get("all") or [])]
    if request.name not in members:
        raise HTTPException(status_code=422, detail="目标节点不属于该策略组，请刷新页面后重试")
    affected_ids: list[str] = []
    snapshot_available = True
    if request.reconnect:
        try:
            affected_ids = _affected_connection_ids(await mihomo.get("/connections"), group_name)
        except httpx.HTTPError:
            snapshot_available = False
    try:
        await mihomo.select(group_name, request.name)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="策略切换失败") from exc
    closed = failed = 0
    if affected_ids:
        closed, failed = await mihomo.close_connections(affected_ids)
    await asyncio.to_thread(
        _record_gateway_event,
        "info",
        "strategy",
        "策略已切换",
        f"{_clean_name(group_name)} 现在指向 {_clean_name(request.name)}",
        {"group": group_name, "selected": request.name, "closedConnections": closed},
    )
    return {"ok": True, "group": group_name, "selected": request.name, "reconnect": request.reconnect, "affectedConnections": len(affected_ids), "closedConnections": closed, "closeFailures": failed, "snapshotAvailable": snapshot_available, "elapsedMs": round((time.monotonic() - started) * 1000)}


@app.get("/api/rules/workspace")
async def rule_workspace_summary(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(rule_workspace.summary)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/rules/reset")
async def reset_rule_workspace(_: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        await asyncio.to_thread(rule_workspace.reset)
        return await asyncio.to_thread(rule_workspace.summary)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/rules/rule-sets", status_code=201)
async def create_rule_set(request: RuleSetRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    payload = request.model_dump()
    try:
        payload["url"] = await _validate_subscription_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rule_set = await asyncio.to_thread(rule_workspace.add_rule_set, payload)
    return {"ruleSet": rule_set}


@app.patch("/api/rules/rule-sets/{rule_set_id}")
async def update_rule_set(rule_set_id: str, request: RuleSetUpdateRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        updates = request.model_dump(exclude_none=True)
        if "url" in updates:
            updates["url"] = await _validate_subscription_url(str(updates["url"]))
        rule_set = await asyncio.to_thread(rule_workspace.update_rule_set, rule_set_id, updates)
        return {"ruleSet": rule_set}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="规则集不存在") from exc


@app.delete("/api/rules/rule-sets/{rule_set_id}")
async def delete_rule_set(rule_set_id: str, _: dict[str, Any] = Depends(admin_user)) -> dict[str, bool]:
    try:
        await asyncio.to_thread(rule_workspace.delete_rule_set, rule_set_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="规则集不存在") from exc


@app.post("/api/rules/rule-sets/{rule_set_id}/move")
async def move_rule_set(rule_set_id: str, request: RuleMoveRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        index = await asyncio.to_thread(rule_workspace.move_rule_set, rule_set_id, request.direction)
        return {"ok": True, "index": index}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="规则集不存在") from exc


@app.post("/api/rules/rule-sets/{rule_set_id}/refresh")
async def refresh_rule_set(rule_set_id: str, _: dict[str, Any] = Depends(admin_user)) -> dict[str, bool]:
    try:
        await mihomo.refresh_rule_provider(rule_workspace.provider_id(rule_set_id))
        return {"ok": True}
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=409, detail="该规则集尚未应用到网关") from exc
        raise HTTPException(status_code=502, detail="规则集刷新失败") from exc


@app.post("/api/rules/custom", status_code=201)
async def create_custom_rule(request: CustomRuleRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    rule = await asyncio.to_thread(rule_workspace.add_custom_rule, request.content, request.placement, request.note)
    return {"rule": {**rule, **_parsed_rule(rule["content"])}}


@app.patch("/api/rules/custom/{rule_id}")
async def update_custom_rule(rule_id: str, request: CustomRuleUpdateRequest, _: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        rule = await asyncio.to_thread(rule_workspace.update_custom_rule, rule_id, request.model_dump(exclude_none=True))
        return {"rule": {**rule, **_parsed_rule(rule["content"])}}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="自定义规则不存在") from exc


@app.delete("/api/rules/custom/{rule_id}")
async def delete_custom_rule(rule_id: str, _: dict[str, Any] = Depends(admin_user)) -> dict[str, bool]:
    try:
        await asyncio.to_thread(rule_workspace.delete_custom_rule, rule_id)
        return {"ok": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="自定义规则不存在") from exc


@app.post("/api/rules/apply")
async def apply_rules(admin: dict[str, Any] = Depends(admin_user)) -> dict[str, Any]:
    try:
        result = await rule_workspace.apply()
        await asyncio.to_thread(_record_gateway_event, "info", "rules", "分流规则已应用", "新的规则顺序已热重载到 mihomo。", {"actorId": admin["id"]})
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="mihomo 拒绝了新规则配置，现有配置保持不变") from exc


if settings.static_dir.exists():
    assets = settings.static_dir / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str, request: Request) -> FileResponse:
        candidate = (settings.static_dir / full_path).resolve()
        if full_path and candidate.is_relative_to(settings.static_dir.resolve()) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(settings.static_dir / "index.html")
