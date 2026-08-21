from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


LATEST_SCHEMA_VERSION = 15


def connect(path: Path) -> sqlite3.Connection:
    """Open the appliance database with the same safety pragmas everywhere."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


@contextmanager
def transaction(path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _migration_1(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            allowed_devices TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS traffic_samples (
            ts INTEGER NOT NULL,
            device TEXT NOT NULL,
            chain TEXT NOT NULL,
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            active INTEGER NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 10
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_ts ON traffic_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_traffic_device_ts ON traffic_samples(device, ts);
        CREATE TABLE IF NOT EXISTS traffic_detail_samples (
            ts INTEGER NOT NULL,
            device TEXT NOT NULL,
            service TEXT NOT NULL,
            host TEXT NOT NULL,
            exit_mode TEXT NOT NULL DEFAULT 'unknown',
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            connections INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_detail_ts ON traffic_detail_samples(ts);
        CREATE INDEX IF NOT EXISTS idx_traffic_detail_device_ts ON traffic_detail_samples(device, ts);
        CREATE INDEX IF NOT EXISTS idx_traffic_detail_service_ts ON traffic_detail_samples(service, ts);
        CREATE TABLE IF NOT EXISTS traffic_daily_rollups (
            day_start INTEGER NOT NULL,
            device TEXT NOT NULL,
            chain TEXT NOT NULL,
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            active_peak INTEGER NOT NULL,
            samples INTEGER NOT NULL,
            PRIMARY KEY(day_start, device, chain)
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_daily_device_day ON traffic_daily_rollups(device, day_start);
        CREATE TABLE IF NOT EXISTS traffic_detail_daily_rollups (
            day_start INTEGER NOT NULL,
            device TEXT NOT NULL,
            service TEXT NOT NULL,
            host TEXT NOT NULL,
            exit_mode TEXT NOT NULL DEFAULT 'unknown',
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            connections INTEGER NOT NULL,
            PRIMARY KEY(day_start, device, service, host, exit_mode)
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_detail_daily_device_day ON traffic_detail_daily_rollups(device, day_start);
        CREATE INDEX IF NOT EXISTS idx_traffic_detail_daily_service_day ON traffic_detail_daily_rollups(service, day_start);
        CREATE TABLE IF NOT EXISTS traffic_flow_samples (
            ts INTEGER NOT NULL,
            device TEXT NOT NULL,
            rule TEXT NOT NULL,
            chain TEXT NOT NULL,
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_flow_device_ts ON traffic_flow_samples(device, ts);
        CREATE TABLE IF NOT EXISTS traffic_flow_daily_rollups (
            day_start INTEGER NOT NULL,
            device TEXT NOT NULL,
            rule TEXT NOT NULL,
            chain TEXT NOT NULL,
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            PRIMARY KEY(day_start, device, rule, chain)
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_flow_daily_device_day ON traffic_flow_daily_rollups(device, day_start);
        CREATE TABLE IF NOT EXISTS collector_state (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS connection_cursors (
            id TEXT PRIMARY KEY,
            upload_bytes INTEGER NOT NULL,
            download_bytes INTEGER NOT NULL,
            seen_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_connection_cursors_seen ON connection_cursors(seen_at);
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 21600,
            enabled INTEGER NOT NULL DEFAULT 1,
            gateway_enabled INTEGER NOT NULL DEFAULT 0,
            source_format TEXT,
            node_count INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT,
            usage_json TEXT,
            delivery_token TEXT UNIQUE NOT NULL,
            fetched_at INTEGER,
            next_refresh_at INTEGER,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_subscriptions_owner ON subscriptions(owner_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_subscriptions_refresh ON subscriptions(enabled, next_refresh_at);
        """
    )


def _migration_2(connection: sqlite3.Connection) -> None:
    if "interval_seconds" not in _columns(connection, "traffic_samples"):
        connection.execute("ALTER TABLE traffic_samples ADD COLUMN interval_seconds INTEGER NOT NULL DEFAULT 10")
    if "exit_mode" not in _columns(connection, "traffic_detail_samples"):
        connection.execute("ALTER TABLE traffic_detail_samples ADD COLUMN exit_mode TEXT NOT NULL DEFAULT 'unknown'")
    if "exit_mode" not in _columns(connection, "traffic_detail_daily_rollups"):
        connection.executescript(
            """
            ALTER TABLE traffic_detail_daily_rollups RENAME TO traffic_detail_daily_rollups_legacy;
            CREATE TABLE traffic_detail_daily_rollups (
                day_start INTEGER NOT NULL,
                device TEXT NOT NULL,
                service TEXT NOT NULL,
                host TEXT NOT NULL,
                exit_mode TEXT NOT NULL DEFAULT 'unknown',
                up_bytes INTEGER NOT NULL,
                down_bytes INTEGER NOT NULL,
                connections INTEGER NOT NULL,
                PRIMARY KEY(day_start, device, service, host, exit_mode)
            );
            INSERT INTO traffic_detail_daily_rollups(day_start,device,service,host,exit_mode,up_bytes,down_bytes,connections)
            SELECT day_start,device,service,host,'unknown',up_bytes,down_bytes,connections
            FROM traffic_detail_daily_rollups_legacy;
            DROP TABLE traffic_detail_daily_rollups_legacy;
            CREATE INDEX idx_traffic_detail_daily_device_day ON traffic_detail_daily_rollups(device, day_start);
            CREATE INDEX idx_traffic_detail_daily_service_day ON traffic_detail_daily_rollups(service, day_start);
            """
        )


def _migration_3(connection: sqlite3.Connection) -> None:
    if "session_version" not in _columns(connection, "users"):
        connection.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS traffic_class_daily_rollups (
            day_start INTEGER NOT NULL,
            device TEXT NOT NULL,
            route_class TEXT NOT NULL CHECK(route_class IN ('direct','proxy','unknown')),
            up_bytes INTEGER NOT NULL,
            down_bytes INTEGER NOT NULL,
            PRIMARY KEY(day_start, device, route_class)
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_class_device_day ON traffic_class_daily_rollups(device, day_start);
        CREATE TABLE IF NOT EXISTS connection_sessions (
            id TEXT PRIMARY KEY,
            device TEXT NOT NULL,
            host TEXT NOT NULL,
            destination_ip TEXT NOT NULL,
            destination_port TEXT NOT NULL,
            network TEXT NOT NULL,
            rule TEXT NOT NULL,
            chain TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            last_seen_at INTEGER NOT NULL,
            ended_at INTEGER,
            upload_bytes INTEGER NOT NULL,
            download_bytes INTEGER NOT NULL,
            termination_reason TEXT,
            terminated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_connection_sessions_device_seen ON connection_sessions(device, last_seen_at);
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL,
            resource_id TEXT,
            result TEXT NOT NULL,
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
        """
    )
    connection.execute(
        """
        INSERT INTO traffic_class_daily_rollups(day_start,device,route_class,up_bytes,down_bytes)
        SELECT day_start,device,
               CASE WHEN instr(chain, 'DIRECT') > 0 THEN 'direct'
                    WHEN chain = '' OR chain = 'UNKNOWN' THEN 'unknown'
                    ELSE 'proxy' END,
               SUM(up_bytes),SUM(down_bytes)
        FROM traffic_flow_daily_rollups
        GROUP BY day_start,device,
                 CASE WHEN instr(chain, 'DIRECT') > 0 THEN 'direct'
                      WHEN chain = '' OR chain = 'UNKNOWN' THEN 'unknown'
                      ELSE 'proxy' END
        ON CONFLICT(day_start,device,route_class) DO NOTHING
        """
    )


def _migration_4(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_connection_sessions_seen ON connection_sessions(last_seen_at DESC);
        CREATE INDEX IF NOT EXISTS idx_connection_sessions_status_seen ON connection_sessions(ended_at, last_seen_at DESC);
        """
    )


def _migration_5(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS gateway_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT UNIQUE,
            level TEXT NOT NULL CHECK(level IN ('info','warning','error')),
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '',
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_gateway_events_created ON gateway_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_gateway_events_level_created ON gateway_events(level, created_at DESC);
        """
    )


def _migration_6(connection: sqlite3.Connection) -> None:
    subscription_columns = _columns(connection, "subscriptions")
    if "raw_payload_json" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN raw_payload_json TEXT")
    if "filter_json" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN filter_json TEXT NOT NULL DEFAULT '{}'")
    if "filter_source" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN filter_source TEXT NOT NULL DEFAULT 'manual'")
    if "filter_updated_at" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN filter_updated_at INTEGER")
    if "ai_analysis_json" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN ai_analysis_json TEXT")
    connection.execute(
        "UPDATE subscriptions SET raw_payload_json = payload_json WHERE raw_payload_json IS NULL AND payload_json IS NOT NULL"
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS ai_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            provider TEXT NOT NULL CHECK(provider IN ('deepseek','openrouter')),
            model TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        """
    )


def _migration_7(connection: sqlite3.Connection) -> None:
    session_columns = _columns(connection, "connection_sessions")
    additions = {
        "rule_type": "TEXT NOT NULL DEFAULT ''",
        "rule_payload": "TEXT NOT NULL DEFAULT ''",
        "rule_source": "TEXT NOT NULL DEFAULT 'unknown'",
        "rule_source_id": "TEXT NOT NULL DEFAULT ''",
        "rule_label": "TEXT NOT NULL DEFAULT ''",
    }
    for column, declaration in additions.items():
        if column not in session_columns:
            connection.execute(f"ALTER TABLE connection_sessions ADD COLUMN {column} {declaration}")
    connection.execute("UPDATE connection_sessions SET rule_label = rule WHERE rule_label = ''")
    connection.execute(
        "UPDATE connection_sessions SET rule_type = 'RuleSet', rule_payload = rule "
        "WHERE rule_payload = '' AND rule LIKE 'ssslab-%'"
    )


def _migration_8(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS traffic_anomaly_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            enabled INTEGER NOT NULL DEFAULT 1,
            autonomous INTEGER NOT NULL DEFAULT 0,
            threshold_bytes INTEGER NOT NULL DEFAULT 5368709120,
            action_policy TEXT NOT NULL DEFAULT 'ai' CHECK(action_policy IN ('ai','block','direct','alert')),
            cooldown_seconds INTEGER NOT NULL DEFAULT 3600,
            protected_targets TEXT NOT NULL DEFAULT '[]',
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS traffic_anomaly_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_key TEXT NOT NULL UNIQUE,
            connection_id TEXT NOT NULL,
            device TEXT NOT NULL DEFAULT '',
            source_ip TEXT NOT NULL DEFAULT '',
            host TEXT NOT NULL DEFAULT '',
            destination_ip TEXT NOT NULL DEFAULT '',
            traffic_bytes INTEGER NOT NULL DEFAULT 0,
            route TEXT NOT NULL DEFAULT 'proxy',
            rule_name TEXT NOT NULL DEFAULT '',
            policy_name TEXT NOT NULL DEFAULT '',
            node_name TEXT NOT NULL DEFAULT '',
            decision TEXT NOT NULL CHECK(decision IN ('block','direct','alert')),
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL CHECK(status IN ('analyzing','alerted','executed','skipped','failed')),
            rule_content TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_traffic_anomaly_actions_created ON traffic_anomaly_actions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_traffic_anomaly_actions_target ON traffic_anomaly_actions(host,destination_ip,created_at DESC);
        """
    )


def _migration_9(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS github_sync_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            repo TEXT NOT NULL DEFAULT '',
            branch TEXT NOT NULL DEFAULT '',
            path TEXT NOT NULL DEFAULT '',
            token TEXT NOT NULL DEFAULT '',
            last_sync_at INTEGER,
            last_error TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL DEFAULT 0
        );
        """
    )


def _migration_10(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rotation_combos (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            subscription_ids TEXT NOT NULL DEFAULT '[]',
            strategy TEXT NOT NULL DEFAULT 'region_sticky',
            rotate_interval_seconds INTEGER NOT NULL DEFAULT 1800,
            cross_region_interval_seconds INTEGER NOT NULL DEFAULT 259200,
            enabled INTEGER NOT NULL DEFAULT 1,
            gateway_enabled INTEGER NOT NULL DEFAULT 0,
            state_json TEXT NOT NULL DEFAULT '{}',
            last_error TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rotation_combos_enabled ON rotation_combos(enabled, gateway_enabled);
        """
    )


def _migration_11(connection: sqlite3.Connection) -> None:
    combo_columns = _columns(connection, "rotation_combos")
    if "owner_id" not in combo_columns:
        connection.execute("ALTER TABLE rotation_combos ADD COLUMN owner_id INTEGER NOT NULL DEFAULT 0")
    if "delivery_token" not in combo_columns:
        connection.execute("ALTER TABLE rotation_combos ADD COLUMN delivery_token TEXT NOT NULL DEFAULT ''")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_rotation_combos_owner ON rotation_combos(owner_id)")


def _migration_12(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS node_regions (
            node_key TEXT PRIMARY KEY,
            subscription_id TEXT NOT NULL,
            node_name TEXT NOT NULL,
            country TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'name' CHECK(source IN ('name','geoip','manual')),
            probed_ip TEXT NOT NULL DEFAULT '',
            updated_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_node_regions_subscription ON node_regions(subscription_id);
        """
    )


def _migration_13(connection: sqlite3.Connection) -> None:
    combo_columns = _columns(connection, "rotation_combos")
    if "ai_assist" not in combo_columns:
        connection.execute("ALTER TABLE rotation_combos ADD COLUMN ai_assist INTEGER NOT NULL DEFAULT 0")


def _migration_14(connection: sqlite3.Connection) -> None:
    combo_columns = _columns(connection, "rotation_combos")
    if "rotation_prefs" not in combo_columns:
        # 轮换偏好：启用因素的有序优先级列表，如 ["usage_balance","region_health","region_latency"]。
        # 有序逐级生效：先按最高优先级因素排序，平局再看下一级。
        connection.execute("ALTER TABLE rotation_combos ADD COLUMN rotation_prefs TEXT NOT NULL DEFAULT '[]'")


def _migration_15(connection: sqlite3.Connection) -> None:
    subscription_columns = _columns(connection, "subscriptions")
    if "url_repeatable" not in subscription_columns:
        # 0 = 一次性链接（默认，导入后不自动轮询），1 = 可重复访问（允许自动刷新）。
        connection.execute("ALTER TABLE subscriptions ADD COLUMN url_repeatable INTEGER NOT NULL DEFAULT 0")
    if "consumed_at" not in subscription_columns:
        connection.execute("ALTER TABLE subscriptions ADD COLUMN consumed_at INTEGER")


MIGRATIONS = (_migration_1, _migration_2, _migration_3, _migration_4, _migration_5, _migration_6, _migration_7, _migration_8, _migration_9, _migration_10, _migration_11, _migration_12, _migration_13, _migration_14, _migration_15)


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL DEFAULT (unixepoch()))"
    )
    applied = {int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")}
    for version, migration in enumerate(MIGRATIONS, start=1):
        if version in applied:
            continue
        with connection:
            migration(connection)
            connection.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))
            connection.execute(f"PRAGMA user_version={version}")
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(f"database schema {version} is newer than supported {LATEST_SCHEMA_VERSION}")
