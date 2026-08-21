import unittest

from server.main import _display_name, _display_node_name, _exclusive_exit_usage, _traffic_summary, _traffic_timeline, _usage_flow


class TrafficTimelineTests(unittest.TestCase):
    def test_timeline_keeps_consumed_bytes_instead_of_average_rate(self):
        rows = [
            {"bucket": 1_786_400_000, "up": 9_000_000, "down": 90_000_000},
            {"bucket": 1_786_403_600, "up": 4_000_000, "down": 45_000_000},
        ]
        timeline = _traffic_timeline(rows, "%H:%M")
        self.assertEqual(timeline[0]["up"], 9_000_000)
        self.assertEqual(timeline[0]["down"], 90_000_000)
        self.assertEqual(timeline[1]["down"], 45_000_000)

    def test_summary_is_period_upload_download_and_total(self):
        rows = [
            {"bucket": 1, "up": 3, "down": 7},
            {"bucket": 2, "up": 5, "down": 11},
        ]
        self.assertEqual(_traffic_summary(rows), {"up": 8, "down": 18, "traffic": 26})

    def test_device_flow_links_use_accumulated_bytes(self):
        rows = [
            {"rule": "GitHub", "chain": '["节点选择","美国","us-lax-03"]', "up": 300, "down": 700},
            {"rule": "GitHub", "chain": '["节点选择","美国","us-lax-03"]', "up": 200, "down": 800},
        ]
        flow = _usage_flow("U55C", rows)
        self.assertFalse(flow["empty"])
        self.assertTrue(flow["links"])
        self.assertTrue(all(link["value"] == 2000 for link in flow["links"]))

    def test_device_flow_is_acyclic_when_rule_and_policy_names_repeat(self):
        rows = [
            {
                "rule": "国外媒体",
                "chain": '["国外媒体","节点选择","美国","美国最佳","国外媒体"]',
                "up": 98_000_000,
                "down": 588_994,
            },
            {
                "rule": "微软服务",
                "chain": '["微软服务","节点选择","美国","美国最佳","美国节点 01"]',
                "up": 14_101,
                "down": 0,
            },
        ]
        flow = _usage_flow("ssslab-login-1", rows)

        self.assertFalse(any(link["source"] == link["target"] for link in flow["links"]))
        self.assertFalse(any(
            flow["nodes"][link["source"]]["stage"] >= flow["nodes"][link["target"]]["stage"]
            for link in flow["links"]
        ))
        self.assertEqual(sum(node["name"] == "国外媒体" for node in flow["nodes"]), 2)

    def test_exit_usage_attributes_to_region_not_policy_or_node(self):
        rows = [
            {"chain": '["节点选择","美国","美国最佳","美国圣何塞 01"]', "total": 700},
            {"chain": '["节点选择","美国","美国智能","美国圣何塞 02"]', "total": 200},
            {"chain": '["节点选择","美国","美国最佳","美国洛杉矶 03"]', "total": 50},
            {"chain": '["全球直连","DIRECT"]', "total": 100},
        ]
        result = _exclusive_exit_usage(rows, 1200)
        values = {item["name"]: item["value"] for item in result}
        # 同一地区的不同节点/策略组合并；不同地区分开。
        self.assertEqual(values, {"美国-圣何塞": 900, "美国-洛杉矶": 50, "DIRECT": 100, "历史未细分": 150})
        self.assertNotIn("节点选择", values)
        self.assertNotIn("美国最佳", values)
        self.assertNotIn("美国智能", values)
        self.assertNotIn("美国圣何塞 01", values)
        self.assertEqual(sum(values.values()), 1200)

    def test_exit_usage_aggregates_probe_chain_into_single_bucket(self):
        rows = [
            {"chain": '["🔍 出口探测","香港节点 01"]', "total": 5},
            {"chain": '["🔍 出口探测","美国节点 02"]', "total": 7},
            {"chain": '["🔍 出口探测","德国节点 03"]', "total": 9},
            {"chain": '["节点选择","美国","美国最佳","美国圣何塞 01"]', "total": 700},
        ]
        result = _exclusive_exit_usage(rows, 721)
        values = {item["name"]: item["value"] for item in result}
        self.assertEqual(values, {"美国-圣何塞": 700, "出口探测": 21})
        self.assertNotIn("香港节点 01", values)
        self.assertNotIn("美国节点 02", values)
        self.assertNotIn("德国节点 03", values)


    def test_display_names_preserve_provider_emoji_and_infer_flags_for_plain_names(self):
        self.assertEqual(_display_name("🇭🇰 香港 01"), "🇭🇰 香港 01")
        self.assertEqual(_display_name("🔥 日本 01"), "🔥 日本 01")
        self.assertEqual(_display_name("🇺🇸 洛杉矶 02 · 推荐"), "🇺🇸 洛杉矶 02 · 推荐")
        self.assertEqual(_display_node_name("🇺🇸 洛杉矶 02"), "🇺🇸 洛杉矶 02")
        self.assertEqual(_display_name("香港 01"), "🇭🇰 香港 01")
        self.assertEqual(_display_name("节点选择"), "节点选择")
        self.assertEqual(_display_name("IEPL-东京-03"), "IEPL-东京-03")


if __name__ == "__main__":
    unittest.main()
