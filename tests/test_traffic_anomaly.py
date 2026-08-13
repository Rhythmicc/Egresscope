import tempfile
import unittest
from pathlib import Path

from server.database import connect, migrate
from server.traffic_anomaly import (
    TrafficAnomalyStore,
    is_protected_target,
    target_rule,
)


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

    def test_reservation_deduplicates_one_connection_threshold_event(self):
        connection = {
            "id": "connection-1",
            "device": "U55C",
            "sourceIP": "192.168.31.42",
            "host": "cdn.example.com",
            "destinationIP": "8.8.8.8",
            "upload": 10,
            "download": 20,
            "route": "proxy",
            "rule": "最终兜底",
            "policy": "美国最佳",
            "node": "美国 01",
        }
        first = self.store.reserve(connection, 100)
        second = self.store.reserve(connection, 100)
        self.assertIsInstance(first, int)
        self.assertIsNone(second)
        actions = self.store.list_actions(allowed_devices=None)
        self.assertEqual(actions["count"], 1)
        self.assertEqual(actions["actions"][0]["status"], "analyzing")


if __name__ == "__main__":
    unittest.main()
