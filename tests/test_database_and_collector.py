import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from server.database import LATEST_SCHEMA_VERSION, connect, migrate
from server.main import TrafficCollector, settings


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


if __name__ == "__main__":
    unittest.main()
