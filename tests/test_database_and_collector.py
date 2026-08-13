import asyncio
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from server.database import LATEST_SCHEMA_VERSION, connect, migrate
from server.main import RuleWorkspace, TrafficCollector, _connection_statistics, _gateway_events, _record_gateway_event, _traffic_ledger, rule_workspace, settings, traffic_analysis


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
                self.assertIn("ai_settings", tables)
                subscription_columns = {row[1] for row in connection.execute("PRAGMA table_info(subscriptions)")}
                self.assertIn("raw_payload_json", subscription_columns)
                self.assertIn("filter_json", subscription_columns)
                indexes = {row[1] for row in connection.execute("PRAGMA index_list(connection_sessions)")}
                self.assertIn("idx_connection_sessions_seen", indexes)
                session_columns = {row[1] for row in connection.execute("PRAGMA table_info(connection_sessions)")}
                self.assertTrue({"rule_type", "rule_payload", "rule_source", "rule_source_id", "rule_label"} <= session_columns)

    def test_rule_matches_resolve_to_managed_rule_sources(self):
        workspace = RuleWorkspace()
        rule_set_id = "openai-rules"
        content = {
            "ruleSets": [{"id": rule_set_id, "name": "OpenAI", "enabled": True}],
            "customRules": [
                {
                    "id": "lan-ssh",
                    "content": "IP-CIDR,10.0.0.0/8,DIRECT,no-resolve",
                    "note": "实验室内网",
                    "enabled": True,
                }
            ],
            "fallbackRules": ["GEOIP,CN,DIRECT", "MATCH,节点选择"],
        }
        with patch.object(workspace, "_load", return_value=content):
            catalog = workspace.match_catalog()
        provider = workspace.resolve_match("RuleSet", workspace.provider_id(rule_set_id), catalog)
        custom = workspace.resolve_match("IPCIDR", "10.0.0.0/8", catalog)
        geoip = workspace.resolve_match("GeoIP", "cn", catalog)
        fallback = workspace.resolve_match("Match", "", catalog)
        unknown = workspace.resolve_match("DomainSuffix", "legacy.example", catalog)
        self.assertEqual((provider["label"], provider["source"], provider["sourceId"]), ("OpenAI", "rule-set", rule_set_id))
        self.assertEqual((custom["label"], custom["source"]), ("实验室内网", "custom"))
        self.assertEqual((geoip["label"], geoip["source"]), ("国内 IP 兜底", "fallback"))
        self.assertEqual((fallback["label"], fallback["source"]), ("最终兜底", "fallback"))
        self.assertEqual((unknown["label"], unknown["source"]), ("域名后缀 · legacy.example", "unmanaged"))

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

    def test_collector_persists_structured_rule_match_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            test_settings = replace(settings, data_dir=Path(directory))
            database = Path(directory) / "egresscope.db"
            with connect(database) as connection:
                migrate(connection)
            session = (
                "connection-1", "192.168.31.42", "chatgpt.com", "1.1.1.1", "443", "tcp",
                "OpenAI", '["节点选择","美国"]', 1_786_399_900, 1_786_400_000, 100, 900,
                "RULE-SET", "ssslab-example", "rule-set", "openai-rules", "OpenAI",
            )
            collector = TrafficCollector()
            with patch("server.main.settings", test_settings):
                collector._persist(1_786_400_000, 0, 0, 10, [], [], [], [session], (0, 0))
            with connect(database) as connection:
                row = connection.execute(
                    "SELECT rule,rule_type,rule_payload,rule_source,rule_source_id,rule_label FROM connection_sessions"
                ).fetchone()
            self.assertEqual(tuple(row), ("OpenAI", "RULE-SET", "ssslab-example", "rule-set", "openai-rules", "OpenAI"))

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
                        ("month-edge", "192.168.31.42", "month.example", "4.4.4.4", "443", "tcp", "Match", '["DIRECT"]', now - 31 * 86400, now - 31 * 86400, now - 31 * 86400, 1, 1),
                        ("expired", "192.168.31.42", "old.example", "5.5.5.5", "443", "tcp", "Match", '["DIRECT"]', now - 33 * 86400, now - 33 * 86400, now - 33 * 86400, 1, 1),
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
            self.assertIn("month-edge", remaining)
            self.assertIn("recent", remaining)

    def test_traffic_ledger_keeps_device_target_rule_and_exit_in_one_event(self):
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
                        started_at,last_seen_at,ended_at,upload_bytes,download_bytes,
                        rule_type,rule_payload,rule_source,rule_source_id,rule_label
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        ("model-download", "192.168.31.42", "huggingface.co", "1.1.1.1", "443", "tcp", "AI 模型", '["节点选择","美国最佳","us-lax-03"]', now - 600, now - 10, now - 10, 1024, 8 * 1024**3, "RuleSet", "ssslab-ai", "rule-set", "ai", "AI 模型"),
                        ("model-download-2", "192.168.31.42", "huggingface.co", "1.1.1.2", "443", "tcp", "最终兜底", '["节点选择","美国最佳","us-sjc-02"]', now - 900, now - 20, now - 20, 2048, 2 * 1024**3, "Match", "", "fallback", "fallback-0", "最终兜底"),
                        ("tiny-ntp", "192.168.31.42", "2.ntp.ubuntu.com", "185.125.190.123", "123", "udp", "最终兜底", '["节点选择","美国最佳","us-sjc-02"]', now - 120, now - 100, now - 100, 2048, 9 * 1024, "Match", "", "fallback", "fallback-0", "最终兜底"),
                        ("direct", "192.168.31.42", "mirrors.local", "192.168.31.9", "443", "tcp", "实验室内网", '["全球直连","DIRECT"]', now - 300, now - 5, now - 5, 100, 200, "DomainSuffix", "local", "custom", "lan", "实验室内网"),
                        ("other-device", "192.168.31.225", "example.com", "2.2.2.2", "443", "tcp", "最终兜底", '["节点选择","香港最佳","hk-01"]', now - 200, now - 5, now - 5, 300, 400, "Match", "", "fallback", "fallback-0", "最终兜底"),
                    ),
                )
            catalog = {
                "providers": {"ssslab-ai": {"label": "AI 模型", "source": "rule-set", "sourceId": "ai", "sourceLabel": "规则集", "detail": "规则集 #01"}},
                "custom": {},
                "fallback": {},
            }
            with patch("server.main.settings", test_settings), patch("server.main.time.time", return_value=now), patch.object(rule_workspace, "summary", return_value={"availablePolicies": ["节点选择", "美国最佳", "香港最佳", "全球直连"]}), patch.object(rule_workspace, "match_catalog", return_value=catalog):
                proxy = _traffic_ledger({"role": "viewer", "allowedDevices": ["192.168.31.42"]}, "24h", "proxy", "traffic", "", "", 100, 0)
                all_proxy = _traffic_ledger({"role": "viewer", "allowedDevices": ["192.168.31.42"]}, "24h", "proxy", "traffic", "", "", 100, 0, "device-target", "all")
                direct = _traffic_ledger({"role": "viewer", "allowedDevices": ["192.168.31.42"]}, "24h", "direct", "traffic", "", "", 100, 0, "device-target", "all")
            self.assertEqual(proxy["summary"]["events"], 3)
            self.assertEqual(proxy["summary"]["groups"], 1)
            self.assertEqual(proxy["summary"]["allGroups"], 2)
            self.assertEqual(proxy["summary"]["hiddenGroups"], 1)
            self.assertEqual(len(proxy["events"]), 1)
            self.assertEqual(len(all_proxy["events"]), 2)
            self.assertEqual(all_proxy["summary"]["hiddenGroups"], 0)
            self.assertEqual(all_proxy["events"][1]["traffic"], 11 * 1024)
            self.assertEqual(proxy["events"][0]["host"], "huggingface.co")
            self.assertEqual(proxy["events"][0]["device"], "192.168.31.42")
            self.assertEqual(proxy["events"][0]["rule"], "AI 模型")
            self.assertEqual(proxy["events"][0]["policy"], "美国最佳")
            self.assertEqual(proxy["events"][0]["node"], "us-lax-03")
            self.assertEqual(proxy["events"][0]["traffic"], 10 * 1024**3 + 3072)
            self.assertEqual(proxy["events"][0]["connectionCount"], 2)
            self.assertEqual(proxy["events"][0]["ruleVariants"], 2)
            self.assertEqual(proxy["events"][0]["pathVariants"], 2)
            with patch("server.main.settings", test_settings), patch("server.main.time.time", return_value=now), patch.object(rule_workspace, "summary", return_value={"availablePolicies": ["节点选择", "美国最佳", "香港最佳", "全球直连"]}), patch.object(rule_workspace, "match_catalog", return_value=catalog):
                details = _traffic_ledger({"role": "viewer", "allowedDevices": ["192.168.31.42"]}, "24h", "proxy", "recent", "192.168.31.42", "huggingface.co", 100, 0, "connection")
            self.assertEqual(len(details["events"]), 2)
            self.assertTrue(all(not row["grouped"] for row in details["events"]))
            self.assertEqual(direct["events"][0]["route"], "direct")

    def test_monthly_analysis_keeps_proxy_direct_and_unknown_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            database = data_dir / "egresscope.db"
            test_settings = replace(settings, data_dir=data_dir, device_aliases_path=data_dir / "devices.json")
            now = 1_786_610_000
            day_start = now - ((now + 8 * 3600) % 86400)
            with connect(database) as connection:
                migrate(connection)
                connection.execute(
                    "INSERT INTO traffic_daily_rollups VALUES(?,?,?,?,?,?,?)",
                    (day_start, "192.168.31.42", "mixed", 400, 600, 1, 1),
                )
                connection.executemany(
                    "INSERT INTO traffic_class_daily_rollups VALUES(?,?,?,?,?)",
                    (
                        (day_start, "192.168.31.42", "direct", 100, 200),
                        (day_start, "192.168.31.42", "proxy", 200, 300),
                    ),
                )
                connection.executemany(
                    "INSERT INTO traffic_detail_daily_rollups VALUES(?,?,?,?,?,?,?,?)",
                    (
                        (day_start, "192.168.31.42", "OpenAI", "chatgpt.com", "proxy", 200, 300, 2),
                        (day_start, "192.168.31.42", "Unknown", "unknown.example", "unknown", 5000, 5000, 1),
                    ),
                )
            with patch("server.main.settings", test_settings), patch("server.main.time.time", return_value=now):
                result = asyncio.run(
                    traffic_analysis(
                        range="month",
                        device=None,
                        groupBy="service",
                        metric="traffic",
                        service=None,
                        attributionPeriod="day",
                        user={"role": "admin", "allowedDevices": []},
                    )
                )
            totals = result["totals"]
            self.assertEqual(totals["traffic"], 1000)
            self.assertEqual(totals["proxy"], 500)
            self.assertEqual(totals["direct"], 300)
            self.assertEqual(totals["unknown"], 200)
            self.assertEqual(totals["proxy"] + totals["direct"] + totals["unknown"], totals["traffic"])
            self.assertEqual([(item["name"], item["traffic"]) for item in result["items"]], [("OpenAI", 500)])

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
