import unittest

from server.main import _exclusive_exit_usage, _traffic_summary, _traffic_timeline, _usage_flow


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

    def test_exit_usage_counts_only_the_deepest_policy(self):
        rows = [
            {"chain": '["节点选择","美国","美国最佳","美国节点 01"]', "total": 700},
            {"chain": '["节点选择","美国","美国智能","美国节点 02"]', "total": 200},
            {"chain": '["全球直连","DIRECT"]', "total": 100},
        ]
        result = _exclusive_exit_usage(rows, 1200, {"节点选择", "美国", "美国最佳", "美国智能", "全球直连"})
        values = {item["name"]: item["value"] for item in result}
        self.assertEqual(values, {"美国最佳": 700, "美国智能": 200, "DIRECT": 100, "历史未细分": 200})
        self.assertNotIn("节点选择", values)
        self.assertEqual(sum(values.values()), 1200)


if __name__ == "__main__":
    unittest.main()
