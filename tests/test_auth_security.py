import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from server import main


class AuthSecurityTests(unittest.TestCase):
    def test_password_change_revokes_existing_session(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(
                main.settings,
                data_dir=Path(directory),
                device_aliases_path=Path(directory) / "devices.json",
                session_secret="session-secret-longer-than-thirty-two-characters",
                admin_password="initial-password-long-enough",
            )
            with patch.object(main, "settings", settings):
                store = main.AuthStore()
                store.initialize()
                user = store.authenticate("admin", "initial-password-long-enough")
                token = store.token(user)
                self.assertEqual(store.verify(token)["username"], "admin")
                updated = store.change_password(
                    user["id"],
                    "initial-password-long-enough",
                    "replacement-password-long-enough",
                )
                self.assertIsNone(store.verify(token))
                self.assertIsNone(store.authenticate("admin", "initial-password-long-enough"))
                self.assertEqual(store.authenticate("admin", "replacement-password-long-enough")["id"], user["id"])
                self.assertEqual(store.verify(store.token(updated))["username"], "admin")

    def test_password_change_rejects_wrong_or_reused_password(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(
                main.settings,
                data_dir=Path(directory),
                device_aliases_path=Path(directory) / "devices.json",
                session_secret="session-secret-longer-than-thirty-two-characters",
                admin_password="initial-password-long-enough",
            )
            with patch.object(main, "settings", settings):
                store = main.AuthStore()
                store.initialize()
                user = store.authenticate("admin", "initial-password-long-enough")
                token = store.token(user)
                with self.assertRaisesRegex(ValueError, "当前密码不正确"):
                    store.change_password(user["id"], "wrong-password", "replacement-password-long-enough")
                with self.assertRaisesRegex(ValueError, "不能与当前密码相同"):
                    store.change_password(user["id"], "initial-password-long-enough", "initial-password-long-enough")
                self.assertEqual(store.verify(token)["username"], "admin")

    def test_login_limiter_blocks_after_configured_failures(self):
        limiter = main.LoginRateLimiter(attempts=2, window_seconds=60)
        limiter.failure("source:user")
        self.assertEqual(limiter.check("source:user"), 0)
        limiter.failure("source:user")
        self.assertGreater(limiter.check("source:user"), 0)
        limiter.success("source:user")
        self.assertEqual(limiter.check("source:user"), 0)


if __name__ == "__main__":
    unittest.main()
