import tempfile
import unittest
from pathlib import Path

from server.kernel import (
    KernelManager,
    asset_name,
    binary_name,
    checksum_name,
    detect_arch,
    normalize_version,
    version_key,
)


class KernelNamingTests(unittest.TestCase):
    def test_arch_detection(self):
        self.assertEqual(detect_arch("x86_64"), "amd64")
        self.assertEqual(detect_arch("amd64"), "amd64")
        self.assertEqual(detect_arch("aarch64"), "arm64")
        self.assertEqual(detect_arch("armv7l"), "armv7")

    def test_asset_and_binary_names(self):
        self.assertEqual(asset_name("amd64", "v1.19.29"), "mihomo-linux-amd64-v1.19.29.gz")
        self.assertEqual(asset_name("arm64", "1.20.0"), "mihomo-linux-arm64-v1.20.0.gz")
        self.assertEqual(binary_name("v1.19.29"), "mihomo-v1.19.29")
        self.assertEqual(checksum_name("v1.19.29"), "sha256-v1.19.29.txt")

    def test_version_normalization_and_compare(self):
        with self.assertRaises(ValueError):
            normalize_version("latest")
        self.assertEqual(normalize_version("1.19.29"), "v1.19.29")
        self.assertLess(version_key("v1.19.29"), version_key("v1.20.0"))
        self.assertEqual(version_key("v1.19.29"), version_key("1.19.29"))


class KernelManagerTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self._dir.name)
        self.manager = KernelManager(self.bin_dir)

    def tearDown(self):
        self._dir.cleanup()

    def test_stage_apply_status_and_rollback(self):
        (self.bin_dir / "mihomo-v1.19.29").write_bytes(b"old-binary")
        (self.bin_dir / "mihomo-v1.20.0").write_bytes(b"new-binary")
        self.assertEqual(self.manager.staged()[0]["version"], "v1.19.29")
        self.manager.apply("v1.20.0")
        self.assertEqual(self.manager.current_version(), "v1.20.0")
        status = self.manager.status(running_version="v1.19.29")
        self.assertTrue(status["pendingRestart"], "暂存版本与运行版本不一致时应提示重启")
        # 回滚到上一暂存版本。
        result = self.manager.rollback()
        self.assertEqual(result["version"], "v1.19.29")
        self.assertEqual(self.manager.current_version(), "v1.19.29")

    def test_apply_requires_staged_binary(self):
        with self.assertRaises(ValueError):
            self.manager.apply("v9.9.9")

    def test_checksum_parse(self):
        content = "abc123" * 11 + "\n" + "d" * 64 + "  mihomo-linux-amd64-v1.20.0.gz\n"
        self.assertEqual(self.manager._parse_checksum(content, "mihomo-linux-amd64-v1.20.0.gz"), "d" * 64)


if __name__ == "__main__":
    unittest.main()
