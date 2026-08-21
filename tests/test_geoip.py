import unittest
from unittest.mock import patch

from server.geoip import COUNTRY_CODES, COUNTRY_FLAGS, GeoIPResolver, normalize_country


class GeoIPResolverTests(unittest.TestCase):
    def test_offline_preferred_when_mmdb_present(self):
        resolver = GeoIPResolver()
        resolver._reader = {
            "1.2.3.4": {
                "country": {"iso_code": "US"},
                "city": {"names": {"en": "Seattle"}},
            }
        }
        self.assertEqual(resolver.resolve("1.2.3.4"), {"country": "美国", "city": "Seattle"})

    def test_private_address_rejected_before_any_lookup(self):
        resolver = GeoIPResolver()
        resolver._resolve_offline = lambda ip: (_ for _ in ()).throw(AssertionError("should not be called"))
        resolver._resolve_online = lambda ip: (_ for _ in ()).throw(AssertionError("should not be called"))
        self.assertIsNone(resolver.resolve("192.168.1.1"))
        self.assertIsNone(resolver.resolve("10.0.0.1"))
        self.assertIsNone(resolver.resolve("127.0.0.1"))

    @patch("server.geoip.httpx.get")
    def test_online_fallback_parses_ipapi(self, mock_get):
        resolver = GeoIPResolver(online_service="https://example.test/{ip}")
        mock_get.return_value = type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: {"country_name": "United States", "city": "Los Angeles"}})()
        result = resolver.resolve("8.8.8.8")
        self.assertEqual(result, {"country": "美国", "city": "Los Angeles"})

    @patch("server.geoip.httpx.get")
    def test_online_iso_code_normalized_to_chinese(self, mock_get):
        resolver = GeoIPResolver(online_service="https://example.test/{ip}")
        mock_get.return_value = type("Resp", (), {"raise_for_status": lambda self: None, "json": lambda self: {"country_code": "JP", "city": "Tokyo"}})()
        self.assertEqual(resolver.resolve("8.8.8.8"), {"country": "日本", "city": "Tokyo"})

    def test_country_codes_cover_common_regions(self):
        self.assertEqual(COUNTRY_CODES["US"], "美国")
        self.assertEqual(COUNTRY_CODES["JP"], "日本")
        self.assertEqual(COUNTRY_CODES["HK"], "香港")

    def test_normalize_country_maps_iso_english_and_chinese(self):
        self.assertEqual(normalize_country("US"), "美国")
        self.assertEqual(normalize_country("United States"), "美国")
        self.assertEqual(normalize_country("Hong Kong"), "香港")
        self.assertEqual(normalize_country("美国"), "美国")
        self.assertEqual(normalize_country(""), "")

    def test_country_flags_derive_from_iso(self):
        self.assertEqual(COUNTRY_FLAGS["美国"], "🇺🇸")
        self.assertEqual(COUNTRY_FLAGS["日本"], "🇯🇵")
        self.assertEqual(COUNTRY_FLAGS["香港"], "🇭🇰")
        self.assertEqual(COUNTRY_FLAGS["台湾"], "🇨🇳")


if __name__ == "__main__":
    unittest.main()
