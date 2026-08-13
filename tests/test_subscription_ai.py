import tempfile
import unittest
from pathlib import Path

from server.database import connect, migrate
from server.subscription_ai import (
    AISettingsStore,
    apply_node_filter,
    inventory_for_ai,
    normalize_filter,
    parse_ai_suggestion,
)


class SubscriptionFilterTests(unittest.TestCase):
    def setUp(self):
        self.nodes = [
            {"name": "🇺🇸 美国洛杉矶 01", "type": "ss", "server": "us.example.com", "port": 443, "password": "secret"},
            {"name": "剩余流量 82 GB", "type": "ss", "server": "notice.example.com", "port": 443, "password": "secret"},
            {"name": "🇭🇰 香港 特区 01", "type": "trojan", "server": "hk.example.com", "port": 443, "password": "secret"},
        ]

    def test_filters_information_nodes_and_renames_without_exposing_credentials(self):
        config = {
            "includeRegex": "",
            "excludeRegex": "到期|官网",
            "excludeKeywords": ["剩余流量"],
            "renameRules": [{"pattern": r"\s*特区\s*", "replacement": " "}],
        }
        filtered, preview = apply_node_filter(self.nodes, config)
        self.assertEqual([item["name"] for item in filtered], ["🇺🇸 美国洛杉矶 01", "🇭🇰 香港 01"])
        self.assertEqual(preview["excluded"], 1)
        self.assertEqual(preview["renamed"], 1)
        self.assertEqual(preview["renamedPreview"], [{"from": "🇭🇰 香港 特区 01", "to": "🇭🇰 香港 01"}])
        inventory = inventory_for_ai(self.nodes)
        self.assertNotIn("server", inventory[0])
        self.assertNotIn("password", inventory[0])

    def test_rejects_a_filter_that_removes_every_node(self):
        with self.assertRaisesRegex(ValueError, "排除全部节点"):
            apply_node_filter(self.nodes, {"excludeRegex": ".*"})

    def test_rejects_expensive_nested_quantifier(self):
        with self.assertRaisesRegex(ValueError, "不安全"):
            normalize_filter({"excludeRegex": "(a+)+"})


class AISettingsStoreTests(unittest.TestCase):
    def test_api_key_is_never_returned_by_public_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "egresscope.db"

            def database():
                return connect(path)

            with connect(path) as connection:
                migrate(connection)
            store = AISettingsStore(database)
            public = store.update("deepseek", "deepseek-chat", "secret-api-key", False)
            self.assertTrue(public["apiKeyConfigured"])
            self.assertNotIn("apiKey", public)
            self.assertEqual(store.get(include_key=True)["apiKey"], "secret-api-key")

            switched = store.update("openrouter", "openai/gpt-4.1-mini", None, False)
            self.assertFalse(switched["apiKeyConfigured"])
            self.assertEqual(store.get(include_key=True)["apiKey"], "")


class AIResponseParsingTests(unittest.TestCase):
    def test_accepts_json_code_fence(self):
        suggestion = parse_ai_suggestion(
            '```json\n{"includeRegex":"","excludeKeywords":["流量"]}\n```'
        )
        self.assertEqual(suggestion["excludeKeywords"], ["流量"])

    def test_accepts_json_surrounded_by_provider_text(self):
        suggestion = parse_ai_suggestion(
            '分析完成：{"includeRegex":"美国","excludeKeywords":[]} 请确认。'
        )
        self.assertEqual(suggestion["includeRegex"], "美国")

    def test_rejects_empty_or_non_object_response(self):
        with self.assertRaisesRegex(ValueError, "没有返回"):
            parse_ai_suggestion("")
        with self.assertRaisesRegex(ValueError, "格式不正确"):
            parse_ai_suggestion("[]")


if __name__ == "__main__":
    unittest.main()
