import unittest

from server.main import GitHubSyncStore


class GitHubSyncValidationTests(unittest.TestCase):
    def test_target_validation_accepts_standard_repository_branch_and_path(self):
        self.assertEqual(
            GitHubSyncStore._validated_target(
                "Rhythmicc/ACL4SSR",
                "feature/custom-rules",
                "Clash/egresscope-custom-rules.json",
            ),
            ("Rhythmicc/ACL4SSR", "feature/custom-rules", "Clash/egresscope-custom-rules.json"),
        )

    def test_target_validation_rejects_path_traversal_and_invalid_repository(self):
        with self.assertRaisesRegex(ValueError, "owner/repository"):
            GitHubSyncStore._validated_target("owner/repo/extra", "main", "rules.json")
        with self.assertRaisesRegex(ValueError, "文件路径无效"):
            GitHubSyncStore._validated_target("owner/repo", "main", "../rules.json")

    def test_empty_remote_rule_set_is_a_valid_snapshot(self):
        self.assertEqual(
            GitHubSyncStore._rules_from_payload(
                {"version": 1, "kind": "egresscope-custom-rules", "customRules": []}
            ),
            [],
        )

    def test_duplicate_or_invalid_remote_ids_are_regenerated(self):
        rules = GitHubSyncStore._rules_from_payload(
            {
                "version": 1,
                "kind": "egresscope-custom-rules",
                "customRules": [
                    {"id": "same", "content": "DOMAIN,one.example,DIRECT", "enabled": False},
                    {"id": "same", "content": "DOMAIN,two.example,DIRECT", "enabled": "false"},
                ],
            }
        )
        self.assertEqual(rules[0]["id"], "same")
        self.assertNotEqual(rules[1]["id"], "same")
        self.assertFalse(rules[0]["enabled"])
        self.assertTrue(rules[1]["enabled"])

    def test_remote_rule_content_limit_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "内容长度无效"):
            GitHubSyncStore._rules_from_payload(
                {
                    "version": 1,
                    "kind": "egresscope-custom-rules",
                    "customRules": [{"id": "rule", "content": "x" * 4097}],
                }
            )


if __name__ == "__main__":
    unittest.main()
