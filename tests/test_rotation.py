import unittest

from server.rotation import (
    choose_rotation,
    city_of,
    normalize_city,
    pool_profiles,
    regions_for,
)


def country_of(name: str) -> str | None:
    lowered = name.casefold()
    for country, hints in (("美国", ("美国", "united states", "los angeles", "san jose", "seattle", "🇺🇸")),
                           ("日本", ("日本", "japan", "tokyo", "osaka", "🇯🇵")),
                           ("香港", ("香港", "hong kong", "🇭🇰"))):
        if any(hint.casefold() in lowered for hint in hints):
            return country
    return None


def region_of(name: str) -> str | None:
    return city_of(name) or "默认"


class CityDetectionTests(unittest.TestCase):
    def test_detects_chinese_city_tokens(self):
        self.assertEqual(city_of("🇺🇸 洛杉矶 01"), "洛杉矶")
        self.assertEqual(city_of("美国-圣何塞-02"), "圣何塞")
        self.assertEqual(city_of("日本 东京 03"), "东京")

    def test_detects_iata_codes_at_word_boundaries(self):
        self.assertEqual(city_of("US LAX-01"), "洛杉矶")
        self.assertEqual(city_of("🇺🇸 SEA-02"), "西雅图")
        self.assertEqual(city_of("日本 NRT 01"), "东京")

    def test_never_confuses_common_words_with_city_codes(self):
        self.assertNotEqual(city_of("research-01"), "西雅图")
        self.assertNotEqual(city_of("history-cdn"), "伊斯坦布尔")

    def test_normalize_city_maps_english_to_chinese_key(self):
        self.assertEqual(normalize_city("Los Angeles"), "洛杉矶")
        self.assertEqual(normalize_city("seattle"), "西雅图")
        self.assertEqual(normalize_city("洛杉矶"), "洛杉矶")
        self.assertEqual(normalize_city("Osaka"), "大阪")

    def test_normalize_city_covers_common_datacenter_exits(self):
        self.assertEqual(normalize_city("Berlin"), "柏林")
        self.assertEqual(normalize_city("Ashburn"), "阿什本")
        self.assertEqual(normalize_city("San Jose"), "圣何塞")
        self.assertEqual(normalize_city("City of London"), "伦敦")
        self.assertEqual(city_of("美国 阿什本 01"), "阿什本")
        self.assertEqual(city_of("🇩🇪 Berlin-02"), "柏林")


class RotationSelectionTests(unittest.TestCase):
    def setUp(self):
        # 单一国家（美国）的节点池，跨三个地区。
        self.pool = pool_profiles([
            "🇺🇸 洛杉矶 01", "🇺🇸 洛杉矶 02", "🇺🇸 圣何塞 01", "🇺🇸 西雅图 01",
        ], country_of, region_of)

    def test_stays_in_same_region_when_healthy_and_rotation_due(self):
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(self.pool, current, {"🇺🇸 洛杉矶 01": {"alive": True}, "🇺🇸 洛杉矶 02": {"alive": True}}, rotate_due=True, cross_due=False)
        self.assertEqual(result["node"], "🇺🇸 洛杉矶 02")
        self.assertEqual(result["region"], "洛杉矶")
        self.assertFalse(result["crossed"])

    def test_does_not_rotate_when_not_due(self):
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(self.pool, current, {}, rotate_due=False, cross_due=False)
        self.assertEqual(result["node"], "🇺🇸 洛杉矶 01")

    def test_prefers_different_provider_within_region(self):
        pool = [
            {"name": "🇺🇸 A 美国-圣何塞-1", "provider": "A", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 A 美国-圣何塞-2", "provider": "A", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 B 美国-圣何塞-1", "provider": "B", "country": "美国", "region": "圣何塞"},
        ]
        current = {"country": "美国", "region": "圣何塞", "node": "🇺🇸 A 美国-圣何塞-1"}
        result = choose_rotation(pool, current, {}, rotate_due=True, cross_due=False)
        self.assertEqual(result["node"], "🇺🇸 B 美国-圣何塞-1")
        self.assertEqual(result["reason"], "同地区切换至其他提供商")
        self.assertFalse(result["crossed"])

    def test_falls_back_to_same_provider_when_no_alternative(self):
        pool = [
            {"name": "🇺🇸 A 美国-圣何塞-1", "provider": "A", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 A 美国-圣何塞-2", "provider": "A", "country": "美国", "region": "圣何塞"},
        ]
        current = {"country": "美国", "region": "圣何塞", "node": "🇺🇸 A 美国-圣何塞-1"}
        result = choose_rotation(pool, current, {}, rotate_due=True, cross_due=False)
        self.assertEqual(result["node"], "🇺🇸 A 美国-圣何塞-2")
        self.assertEqual(result["reason"], "同地区健康节点轮换")

    def test_usage_balance_prefers_least_used_provider(self):
        pool = [
            {"name": "🇺🇸 A 美国-圣何塞-1", "provider": "A", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 B 美国-圣何塞-1", "provider": "B", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 B 美国-圣何塞-2", "provider": "B", "country": "美国", "region": "圣何塞"},
        ]
        current = {"country": "美国", "region": "圣何塞", "node": "🇺🇸 A 美国-圣何塞-1"}
        # A 已用很多、B 未用 → 用量均衡应选 B（即便字母序 A 在前）。
        result = choose_rotation(pool, current, {}, rotate_due=True, cross_due=False,
                                 prefs=["usage_balance"], usage={"A": 5000, "B": 0})
        self.assertEqual(result["node"], "🇺🇸 B 美国-圣何塞-1")

    def test_cross_region_uses_factor_priority(self):
        pool = [
            {"name": "🇺🇸 A 美国-圣何塞-1", "provider": "A", "country": "美国", "region": "圣何塞"},
            {"name": "🇺🇸 B 美国-洛杉矶-1", "provider": "B", "country": "美国", "region": "洛杉矶"},
            {"name": "🇺🇸 C 美国-西雅图-1", "provider": "C", "country": "美国", "region": "西雅图"},
        ]
        current = {"country": "美国", "region": "圣何塞", "node": "🇺🇸 A 美国-圣何塞-1"}
        health = {
            "🇺🇸 A 美国-圣何塞-1": {"alive": True},
            "🇺🇸 B 美国-洛杉矶-1": {"alive": True, "delay": 300},
            "🇺🇸 C 美国-西雅图-1": {"alive": True, "delay": 50},
        }
        # 因素顺序：地区延迟优先 → 选延迟更低的西雅图。
        result = choose_rotation(pool, current, health, rotate_due=False, cross_due=True,
                                 prefs=["region_latency"])
        self.assertEqual(result["region"], "西雅图")

    def test_unhealthy_node_switches_within_region(self):
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(
            self.pool, current,
            {"🇺🇸 洛杉矶 01": {"alive": False}, "🇺🇸 洛杉矶 02": {"alive": True}},
            rotate_due=False, cross_due=False,
        )
        self.assertEqual(result["node"], "🇺🇸 洛杉矶 02")
        self.assertFalse(result["crossed"])

    def test_crosses_region_when_region_has_no_healthy_nodes(self):
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(
            self.pool, current,
            {"🇺🇸 洛杉矶 01": {"alive": False}, "🇺🇸 洛杉矶 02": {"alive": False},
             "🇺🇸 圣何塞 01": {"alive": True}},
            rotate_due=False, cross_due=False,
        )
        # 健康地区为圣何塞（存活）与西雅图（未上报默认存活），因素全平局取字母序最优。
        self.assertEqual(result["region"], "圣何塞")
        self.assertTrue(result["crossed"])

    def test_crosses_region_when_due(self):
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(self.pool, current, {"🇺🇸 洛杉矶 01": {"alive": True}}, rotate_due=False, cross_due=True)
        self.assertEqual(result["region"], "圣何塞")
        self.assertTrue(result["crossed"])

    def test_never_crosses_country(self):
        # 即使美国无健康节点，也不切到其它国家。
        mixed = pool_profiles(["🇺🇸 洛杉矶 01", "🇯🇵 东京 01"], country_of, region_of)
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(mixed, current, {"🇺🇸 洛杉矶 01": {"alive": False}}, rotate_due=False, cross_due=True)
        self.assertEqual(result["country"], "美国")

    def test_cross_region_stays_in_country_even_when_other_country_healthy(self):
        # 跨地区 = 换同国家的不同地区；即使其它国家有健康节点也不切走。
        pool = pool_profiles(["🇺🇸 洛杉矶 01", "🇺🇸 圣何塞 01", "🇯🇵 东京 01"], country_of, region_of)
        current = {"country": "美国", "region": "洛杉矶", "node": "🇺🇸 洛杉矶 01"}
        result = choose_rotation(
            pool, current,
            {"🇺🇸 洛杉矶 01": {"alive": False}, "🇺🇸 圣何塞 01": {"alive": True}, "🇯🇵 东京 01": {"alive": True}},
            rotate_due=False, cross_due=True,
        )
        self.assertEqual(result["country"], "美国")
        self.assertEqual(result["region"], "圣何塞")
        self.assertTrue(result["crossed"])
        self.assertNotEqual(result["node"], "🇯🇵 东京 01")

    def test_regions_grouped_per_country(self):
        self.assertEqual(regions_for(self.pool, "美国"), ["圣何塞", "洛杉矶", "西雅图"])


if __name__ == "__main__":
    unittest.main()
