import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import yaml

from server.main import (
    _clash_delivery,
    _validate_subscription_url,
    _masked_subscription_url,
    _overlay_subscription_nodes,
    _parse_subscription,
    _subscription_usage,
    _surge_delivery,
    _surge_scalar,
)


class SubscriptionParsingTests(unittest.TestCase):
    def test_parses_surge_anytls_without_direct_entry(self):
        source = b"""
[Proxy]
DIRECT = direct
US-A = anytls, us.example.com, 443, password=secret, sni=edge.example.com, skip-cert-verify=false, udp-relay=true
HK-A = trojan, hk.example.com, 8443, password=secret, sni=hk.example.com
[Proxy Group]
ignored = select,US-A
"""
        source_format, nodes = _parse_subscription(source)
        self.assertEqual(source_format, "surge")
        self.assertEqual([item["name"] for item in nodes], ["US-A", "HK-A"])
        self.assertTrue(nodes[0]["udp"])
        self.assertFalse(nodes[0]["skip-cert-verify"])

    def test_parses_mihomo_yaml(self):
        source = b"""
proxies:
  - name: Tokyo
    type: ss
    server: jp.example.com
    port: 443
    cipher: aes-128-gcm
    password: secret
"""
        source_format, nodes = _parse_subscription(source)
        self.assertEqual(source_format, "mihomo")
        self.assertEqual(nodes[0]["name"], "Tokyo")

    def test_rejects_oversized_or_control_character_node_identity(self):
        oversized = yaml.safe_dump({"proxies": [{"name": "a" * 257, "type": "ss", "server": "example.com", "port": 443}]}, allow_unicode=True).encode()
        with self.assertRaisesRegex(ValueError, "节点名称最多"):
            _parse_subscription(oversized)
        controlled = yaml.safe_dump({"proxies": [{"name": "safe\nFINAL,DIRECT", "type": "ss", "server": "example.com", "port": 443}]}, allow_unicode=True).encode()
        with self.assertRaisesRegex(ValueError, "控制字符"):
            _parse_subscription(controlled)

    def test_replaces_node_inventory_without_changing_group_topology(self):
        config = {
            "proxies": [
                {"name": "Old US", "type": "ss", "server": "old-us", "port": 1},
                {"name": "Old HK", "type": "ss", "server": "old-hk", "port": 2},
            ],
            "proxy-groups": [
                {"name": "Manual", "type": "select", "proxies": ["DIRECT", "Old US", "Old HK"]},
                {"name": "美国最佳", "type": "url-test", "proxies": ["Old US"]},
                {"name": "香港最佳", "type": "url-test", "proxies": ["Old HK"]},
            ],
        }
        nodes = [
            {"name": "🇺🇸 New US", "type": "ss", "server": "new-us", "port": 3},
            {"name": "🇭🇰 New HK", "type": "ss", "server": "new-hk", "port": 4},
        ]
        result = _overlay_subscription_nodes(config, nodes)
        self.assertEqual(result["proxy-groups"][0]["proxies"], ["DIRECT", "🇺🇸 New US", "🇭🇰 New HK"])
        self.assertEqual(result["proxy-groups"][1]["proxies"], ["🇺🇸 New US"])
        self.assertEqual(result["proxy-groups"][2]["proxies"], ["🇭🇰 New HK"])

    def test_masks_secret_url_and_parses_usage(self):
        self.assertEqual(_masked_subscription_url("https://example.com/sub?token=secret"), "https://example.com/••••")
        self.assertEqual(_subscription_usage("upload=1; download=2; total=3; expire=4"), {"upload": 1, "download": 2, "total": 3, "expire": 4})

    def test_generates_complete_clash_profile(self):
        nodes = [
            {"name": "🇺🇸 US A", "type": "anytls", "server": "us.example.com", "port": 443, "password": "secret", "sni": "edge.example.com"},
            {"name": "🇭🇰 HK A", "type": "trojan", "server": "hk.example.com", "port": 443, "password": "secret"},
        ]
        profile = yaml.safe_load(_clash_delivery("Example", nodes))
        self.assertEqual(profile["mixed-port"], 7890)
        self.assertTrue(profile["unified-delay"])
        self.assertEqual(profile["rules"][-1], "MATCH,🐟 漏网之鱼")
        group_names = [group["name"] for group in profile["proxy-groups"]]
        self.assertIn("💬 Ai平台", group_names)
        self.assertIn("🇺🇸 美国最佳", group_names)
        best = next(group for group in profile["proxy-groups"] if group["name"] == "🇺🇸 美国最佳")
        self.assertEqual(best["expected-status"], 204)
        self.assertEqual(best["url"], "https://www.gstatic.com/generate_204")
        self.assertGreaterEqual(len(profile["rule-providers"]), 30)
        self.assertTrue(any(rule.endswith(",🇺🇸 美国") for rule in profile["rules"]))
        self.assertNotIn("http-listen", profile)

    def test_generates_complete_surge_profile(self):
        nodes = [{"name": "🇺🇸 US A", "type": "anytls", "server": "us.example.com", "port": 443, "password": "secret", "sni": "edge.example.com", "skip-cert-verify": False}]
        profile = _surge_delivery("Example", nodes, "https://proxy.example/sub/token/surge.conf")
        self.assertTrue(profile.startswith("#!MANAGED-CONFIG https://proxy.example/sub/token/surge.conf interval=86400 strict=true"))
        self.assertIn("[General]", profile)
        self.assertIn("[Proxy]", profile)
        self.assertIn("🇺🇸 US A = anytls, us.example.com, 443, password=secret", profile)
        self.assertIn("🇺🇸 美国智能 = load-balance", profile)
        self.assertIn("💬 Ai平台 = select", profile)
        self.assertIn("RULE-SET,https://", profile)
        self.assertIn("url=http://www.gstatic.com/generate_204", profile)
        self.assertIn("persistent=true", profile)
        self.assertIn("tun-excluded-routes", profile)
        self.assertNotIn("proxy-test-url", profile)
        self.assertNotIn("internet-test-url", profile)
        self.assertNotIn("http-listen", profile)
        self.assertNotIn("[Script]", profile)
        self.assertNotIn("[Host]", profile)
        self.assertTrue(profile.rstrip().endswith("FINAL,🐟 漏网之鱼"))

    def test_surge_scalar_never_emits_line_or_control_characters(self):
        self.assertEqual(_surge_scalar("node,\r\n\t\x00end"), r"node\,\r\n\t\x00end")
        profile = _surge_delivery(
            "Example",
            [{"name": "Safe\nFINAL,DIRECT", "type": "ss", "server": "example.com", "port": 443, "cipher": "aes-128-gcm", "password": "secret\n[Host]"}],
        )
        self.assertNotIn("\nFINAL,DIRECT", profile)
        self.assertNotIn("\n[Host]\n", profile)

    def test_delivery_rules_fall_back_when_region_is_missing(self):
        nodes = [{"name": "🇺🇸 US A", "type": "ss", "server": "us.example.com", "port": 443, "cipher": "aes-128-gcm", "password": "secret"}]
        clash = yaml.safe_load(_clash_delivery("Example", nodes))
        self.assertNotIn("🇯🇵 日本", [group["name"] for group in clash["proxy-groups"]])
        self.assertFalse(any(rule.endswith(",🇯🇵 日本") for rule in clash["rules"]))
        surge = _surge_delivery("Example", nodes)
        self.assertNotIn(",🇯🇵 日本,update-interval=", surge)


class SubscriptionUrlValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rechecks_mihomo_fake_ip_with_public_dns(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=[(2, 1, 6, "", ("198.18.0.53", 443))])):
            with patch("server.main._validate_fake_ip_hostname", AsyncMock(return_value=("93.184.216.34",))) as recheck:
                self.assertEqual(await _validate_subscription_url("https://example.com/sub"), "https://example.com/sub")
                recheck.assert_awaited_once_with("example.com")

    async def test_still_rejects_real_private_address(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=[(2, 1, 6, "", ("192.168.1.10", 443))])):
            with self.assertRaisesRegex(ValueError, "局域网"):
                await _validate_subscription_url("https://example.com/sub")


if __name__ == "__main__":
    unittest.main()
