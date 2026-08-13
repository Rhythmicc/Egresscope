import tempfile
import unittest
from pathlib import Path

from server.database import connect, migrate
from server.traffic_anomaly import (
    DEFAULT_WINDOW_SECONDS,
    TargetTrafficWindow,
    TrafficAnomalyStore,
    is_protected_target,
    target_rule,
)


class TargetTrafficWindowTests(unittest.TestCase):
    def test_aggregates_same_device_and_target_across_connections(self):
        window = TargetTrafficWindow()
        now = 10_000
        window.record(now - 20, "192.168.31.42", "cdn.example.com", 10, 20)
        window.record(now - 5, "192.168.31.42", "cdn.example.com", 30, 40)
        window.record(now - 5, "192.168.31.225", "cdn.example.com", 100, 200)
        self.assertEqual(
            window.usage("192.168.31.42", "CDN.EXAMPLE.COM.", now),
            {"upload": 40, "download": 60, "traffic": 100},
        )

    def test_prunes_samples_outside_five_minute_window(self):
        window = TargetTrafficWindow()
        now = 10_000
        window.record(now - DEFAULT_WINDOW_SECONDS - 1, "192.168.31.42", "cdn.example.com", 100, 200)
        window.record(now, "192.168.31.42", "cdn.example.com", 1, 2)
        self.assertEqual(window.usage("192.168.31.42", "cdn.example.com", now)["traffic"], 3)

    def test_global_prune_discards_inactive_target_state(self):
        window = TargetTrafficWindow()
        now = 10_000
        window.record(now - DEFAULT_WINDOW_SECONDS - 1, "192.168.31.42", "old.example.com", 100, 200)
        window.prune(now)
        self.assertEqual(window.usage("192.168.31.42", "old.example.com", now)["traffic"], 0)


class TrafficAnomalyRuleTests(unittest.TestCase):
    def test_rule_builder_only_emits_constrained_domain_or_host_rules(self):
        connection = {"host": "cdn.example.com", "destinationIP": "203.0.113.8"}
        self.assertEqual(target_rule(connection, "block"), "DOMAIN,cdn.example.com,REJECT")
        self.assertEqual(target_rule(connection, "direct"), "DOMAIN,cdn.example.com,DIRECT")
        self.assertEqual(
            target_rule({"host": "", "destinationIP": "8.8.8.8"}, "direct"),
            "IP-CIDR,8.8.8.8/32,DIRECT,no-resolve",
        )
        with self.assertRaises(ValueError):
            target_rule(connection, "arbitrary")

    def test_private_and_configured_targets_are_always_protected(self):
        self.assertTrue(is_protected_target("", "192.168.31.1", []))
        self.assertTrue(is_protected_target("api.example.internal", "8.8.8.8", ["example.internal"]))
        self.assertFalse(is_protected_target("cdn.example.com", "8.8.8.8", ["example.internal"]))


class TrafficAnomalyStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "egresscope.db"
        with connect(self.path) as connection:
            migrate(connection)

        def database():
            return connect(self.path)

        self.store = TrafficAnomalyStore(database)

    def tearDown(self):
        self.temporary.cleanup()

    def test_defaults_are_safe_and_settings_persist(self):
        initial = self.store.get_settings()
        self.assertTrue(initial["enabled"])
        self.assertFalse(initial["autonomous"])
        updated = self.store.update_settings(
            {
                "autonomous": True,
                "thresholdBytes": 2 * 1024**3,
                "actionPolicy": "ai",
                "cooldownSeconds": 1800,
                "protectedTargets": ["router.local", "example.internal"],
            }
        )
        self.assertTrue(updated["autonomous"])
        self.assertEqual(updated["thresholdBytes"], 2 * 1024**3)

    def test_reservation_deduplicates_same_device_target_window(self):
        connection = {
            "id": "connection-1",
            "device": "U55C",
            "sourceIP": "192.168.31.42",
            "host": "cdn.example.com",
            "destinationIP": "8.8.8.8",
            "upload": 10,
            "download": 20,
            "windowTraffic": 30,
            "route": "proxy",
            "rule": "最终兜底",
            "policy": "美国最佳",
            "node": "美国 01",
        }
        first = self.store.reserve(connection, 100)
        second = self.store.reserve({**connection, "id": "connection-2", "anomalyKey": "next-event"}, 100)
        self.assertIsInstance(first, int)
        self.assertIsNone(second)
        actions = self.store.list_actions(allowed_devices=None)
        self.assertEqual(actions["count"], 1)
        self.assertEqual(actions["actions"][0]["status"], "analyzing")
        self.assertEqual(actions["actions"][0]["traffic"], 30)


if __name__ == "__main__":
    unittest.main()
