from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, ContextManager

from .config import Settings


DatabaseFactory = Callable[[], ContextManager[sqlite3.Connection]]
DatabaseHook = Callable[[sqlite3.Connection], None]


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
    """User and session repository with all infrastructure supplied explicitly."""

    def __init__(
        self,
        settings_provider: Callable[[], Settings],
        database: DatabaseFactory,
        migrate: DatabaseHook,
        backfill_rollups: DatabaseHook,
    ) -> None:
        self._settings_provider = settings_provider
        self._database = database
        self._migrate = migrate
        self._backfill_rollups = backfill_rollups
        self.session_secret = settings_provider().session_secret

    def initialize(self) -> None:
        settings = self._settings_provider()
        self.session_secret = settings.session_secret
        if len(self.session_secret) < 32:
            raise RuntimeError("EGRESSCOPE_SESSION_SECRET is required and must contain at least 32 characters")
        with self._database() as connection:
            self._migrate(connection)
            database_path = Path(connection.execute("PRAGMA database_list").fetchone()[2])
            os.chmod(database_path, 0o600)
            self._backfill_rollups(connection)
            count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            if count == 0:
                if not settings.admin_password:
                    raise RuntimeError("EGRESSCOPE_ADMIN_PASSWORD is required for the initial administrator")
                connection.execute(
                    "INSERT INTO users(username,password_hash,role,allowed_devices,created_at) VALUES(?,?,?,?,?)",
                    (settings.admin_username, _password_hash(settings.admin_password), "admin", "[]", int(time.time())),
                )

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self._database() as connection:
            row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not _password_matches(password, row["password_hash"]):
            return None
        return self.public_user(row)

    def list_users(self) -> list[dict[str, Any]]:
        with self._database() as connection:
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
            with self._database() as connection:
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
        with self._database() as connection:
            result = connection.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", values)
            if result.rowcount != 1:
                raise ValueError("用户不存在")
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self.public_user(row)

    def change_password(self, user_id: int, current_password: str, new_password: str) -> dict[str, Any]:
        if len(new_password) < 12:
            raise ValueError("新密码至少需要 12 个字符")
        with self._database() as connection:
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None or not _password_matches(current_password, row["password_hash"]):
                raise ValueError("当前密码不正确")
            if _password_matches(new_password, row["password_hash"]):
                raise ValueError("新密码不能与当前密码相同")
            connection.execute(
                "UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?",
                (_password_hash(new_password), user_id),
            )
            updated = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self.public_user(updated)

    @staticmethod
    def public_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "allowedDevices": json.loads(row["allowed_devices"] or "[]"),
        }

    def token(self, user: dict[str, Any]) -> str:
        with self._database() as connection:
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
            with self._database() as connection:
                row = connection.execute("SELECT * FROM users WHERE id = ?", (payload["sub"],)).fetchone()
            if not row or int(payload.get("ver", 0)) != int(row["session_version"]):
                return None
            return self.public_user(row)
        except (ValueError, KeyError, json.JSONDecodeError):
            return None


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
