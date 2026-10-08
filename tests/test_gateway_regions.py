import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from server import main
from server.main import _overlay_subscription_nodes, _proxy_available


class GatewayRegionalInventoryTests(unittest.TestCase):
    def test_missing_country_keeps_policy_topology_and_blocks_only_that_exit(self):
        config = {
            "proxies": [{"name": "Old US"}, {"name": "Old UK"}],
            "proxy-groups": [
                {"name": "Entry", "type": "select", "proxies": ["美国", "英国"]},
                {"name": "美国", "type": "select", "proxies": ["美国最佳"]},
                {"name": "英国", "type": "select", "proxies": ["英国最佳", "英国均衡"]},
                {"name": "美国最佳", "type": "url-test", "proxies": ["Old US"]},
                {"name": "英国最佳", "type": "url-test", "proxies": ["Old UK"]},
                {"name": "英国均衡", "type": "load-balance", "proxies": ["Old UK"]},
            ],
            "rules": ["DOMAIN-SUFFIX,example.com,英国", "MATCH,Entry"],
        }
        original = deepcopy(config)
        result = _overlay_subscription_nodes(config, [{"name": "🇺🇸 New US"}])
        self.assertEqual(result["rules"], original["rules"])
        self.assertEqual([(g["name"], g["type"]) for g in result["proxy-groups"]], [(g["name"], g["type"]) for g in original["proxy-groups"]])
        groups = {g["name"]: g["proxies"] for g in result["proxy-groups"]}
        self.assertEqual(groups["美国最佳"], ["🇺🇸 New US"])
        self.assertEqual(groups["英国"], ["英国最佳", "英国均衡"])
        self.assertEqual(groups["英国最佳"], ["REJECT"])
        self.assertEqual(groups["英国均衡"], ["REJECT"])
        self.assertNotIn("Old UK", str(groups))

    def test_missing_country_preserves_explicit_existing_fallback(self):
        config = {"proxies": [{"name": "Old UK"}], "proxy-groups": [{"name": "英国", "type": "select", "proxies": ["Old UK", "OtherPolicy"]}]}
        result = _overlay_subscription_nodes(config, [{"name": "🇺🇸 New US"}])
        self.assertEqual(result["proxy-groups"][0]["proxies"], ["OtherPolicy"])

    def test_node_group_name_collision_still_fails_before_inventory_replacement(self):
        config = {"proxies": [{"name": "old"}], "proxy-groups": [{"name": "Entry", "type": "select", "proxies": ["old"]}]}
        with self.assertRaisesRegex(ValueError, "冲突"):
            _overlay_subscription_nodes(config, [{"name": "Entry"}])
        self.assertEqual(config["proxies"], [{"name": "old"}])

    def test_empty_subscription_cannot_replace_gateway_inventory(self):
        config = {"proxies": [{"name": "old"}]}
        with self.assertRaisesRegex(ValueError, "没有可用节点"):
            _overlay_subscription_nodes(config, [])
        self.assertEqual(config["proxies"], [{"name": "old"}])

    def test_rejected_region_is_not_reported_as_healthy(self):
        proxies = {
            "英国": {"type": "Selector", "all": ["英国最佳", "英国均衡"]},
            "英国最佳": {"type": "URLTest", "all": ["REJECT"]},
            "英国均衡": {"type": "LoadBalance", "all": ["REJECT"]},
            "REJECT": {"type": "Reject", "alive": True},
            "美国最佳": {"type": "URLTest", "all": ["US-A"]},
            "US-A": {"type": "SS", "alive": True},
            "loop": {"type": "Selector", "all": ["loop"]},
        }
        self.assertFalse(_proxy_available(proxies, "英国"))
        self.assertFalse(_proxy_available(proxies, "REJECT"))
        self.assertFalse(_proxy_available(proxies, "loop"))
        self.assertTrue(_proxy_available(proxies, "美国最佳"))


class GatewayRegionalHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_strategy_payload_marks_rejected_region_and_member_unavailable(self):
        proxies = {
            "英国": {"type": "Selector", "all": ["英国最佳"], "now": "英国最佳"},
            "英国最佳": {"type": "URLTest", "all": ["REJECT"], "now": "REJECT"},
            "REJECT": {"type": "Reject", "alive": True},
        }
        with patch.object(main.mihomo, "get", AsyncMock(return_value={"proxies": proxies})), patch.object(main, "_config_group_order", return_value=list(proxies)):
            payload = await main.strategy_payload()
        region = next(group for group in payload["primary"] if group["id"] == "英国")
        self.assertEqual(region["health"], {"available": 0, "total": 1})
        self.assertFalse(region["members"][0]["alive"])
        automatic = region["children"][0]
        self.assertFalse(automatic["selectable"])
        self.assertEqual(automatic["health"], {"available": 0, "total": 1})
        rejected = automatic["members"][0]
        self.assertEqual(rejected["id"], "REJECT")
        self.assertEqual(rejected["name"], "无可用节点（REJECT）")
        self.assertEqual(rejected["delay"], "不可用")
        self.assertFalse(rejected["alive"])
