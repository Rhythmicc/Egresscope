import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from server.database import LATEST_SCHEMA_VERSION, connect, migrate
from server.main import TrafficCollector, _connection_statistics, _gateway_events, _record_gateway_event, settings


class DatabaseMigrationTests(unittest.TestCase):
    def test_migrates_fresh_database_and_enables_foreign_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "egresscope.db"
            with connect(database) as connection:
                migrate(connection)
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], LATEST_SCHEMA_VERSION)
                self.assertEqual(connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertIn("traffic_class_daily_rollups", tables)
                self.assertIn("connection_sessions", tables)
                self.assertIn("gateway_events", tables)
                indexes = {row[1] for row in connection.execute("PRAGMA index_list(connection_sessions)")}
                self.assertIn("idx_connection_sessions_seen", indexes)

    def test_collector_flush_preserves_gateway_byte_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            test_settings = replace(settings, data_dir=Path(directory))
            database = Path(directory) / "egresscope.db"
            with connect(database) as connection:
                migrate(connection)
            collector = TrafficCollector()
            collector.devices = [{"ip": "192.168.31.42", "active": 1, "up": 0, "down": 0}]
            flow_rows = [
                (1_786_400_000, "192.168.31.42", "GitHub", '["节点选择","美国最佳","node-a"]', 800, 1900)
            ]
            with patch("server.main.settings", test_settings):
                collector._persist(1_786_400_000, 1000, 2000, 10, [], flow_rows, [], [], (1000, 2000))
            with sqlite3.connect(database) as connection:
                total = connection.execute("SELECT SUM(up_bytes),SUM(down_bytes) FROM traffic_samples").fetchone()
                classes = dict(connection.execute("SELECT route_class,up_bytes+down_bytes FROM traffic_class_daily_rollups"))
            self.assertEqual(total, (1000, 2000))
            self.assertEqual(classes["proxy"], 2700)
            self.assertEqual(classes["unknown"], 300)

    def test_connection_statistics_keeps_history_for_thirty_days_and_scopes_viewers(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            database = data_dir / "egresscope.db"
            test_settings = replace(
                settings,
                data_dir=data_dir,
                device_aliases_path=data_dir / "devices.json",
                retention_days=30,
            )
            now = 1_786_400_000
            with connect(database) as connection:
                migrate(connection)
                connection.executemany(
                    """
                    INSERT INTO connection_sessions(
                        id,device,host,destination_ip,destination_port,network,rule,chain,
                        started_at,last_seen_at,ended_at,upload_bytes,download_bytes
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ("active", "192.168.31.42", "github.com", "1.1.1.1", "443", "tcp", "GitHub", '["节点选择","美国最佳"]', now - 60, now, None, 100, 900),
                        ("recent", "192.168.31.42", "openai.com", "2.2.2.2", "443", "tcp", "OpenAI", '["节点选择","美国最佳"]', now - 3600, now - 1800, now - 1800, 200, 800),
                        ("other", "192.168.31.225", "example.com", "3.3.3.3", "80", "tcp", "DIRECT", '["DIRECT"]', now - 3600, now - 1800, now - 1800, 50, 50),
                        ("expired", "192.168.31.42", "old.example", "4.4.4.4", "443", "tcp", "Match", '["DIRECT"]', now - 31 * 86400, now - 31 * 86400, now - 31 * 86400, 1, 1),
                    ),
                )
            collector = TrafficCollector()
            with patch("server.main.settings", test_settings), patch("server.main.time.time", return_value=now):
                result = _connection_statistics({"role": "viewer", "allowedDevices": ["192.168.31.42"]}, "30d", "all", 100, 0)
                collector._persist(now, 0, 0, 10, [], [], [], [], (0, 0))
            self.assertEqual([row["id"] for row in result["sessions"]], ["active", "recent"])
            self.assertEqual(result["summary"], {"active": 1, "history": 1, "total": 2, "devices": 1, "traffic": 2000, "matched": 2})
            with connect(database) as connection:
                remaining = {row[0] for row in connection.execute("SELECT id FROM connection_sessions")}
            self.assertNotIn("expired", remaining)
            self.assertIn("recent", remaining)

    def test_gateway_events_are_persistent_filterable_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            database = data_dir / "egresscope.db"
            test_settings = replace(settings, data_dir=data_dir, event_retention_days=90)
            with connect(database) as connection:
                migrate(connection)
            with patch("server.main.settings", test_settings), patch("server.main.time.time", return_value=1_786_400_000):
                _record_gateway_event("error", "mihomo", "节点连接失败", "connection refused", event_key="same-event")
                _record_gateway_event("error", "mihomo", "节点连接失败", "connection refused", event_key="same-event")
                _record_gateway_event("info", "strategy", "策略已切换", "美国最佳 现在指向 node-a")
                result = _gateway_events("error", "refused", 100, 0)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["events"][0]["title"], "节点连接失败")
            self.assertEqual(result["retentionDays"], 90)


if __name__ == "__main__":
    unittest.main()
