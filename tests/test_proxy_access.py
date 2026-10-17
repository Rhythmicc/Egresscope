import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from server import main
from server.proxy_access import proxy_access, proxy_accounts, proxy_credentials, proxy_host


class ProxyAccessTests(unittest.TestCase):
    def test_mixed_and_separate_listeners_preserve_protocols_and_ipv6(self):
        config = {"bind-address": "2001:db8::12", "allow-lan": True, "mixed-port": 9999, "port": 8080, "socks-port": 1080}
        result = proxy_access(config, "192.168.1.0/24")
        self.assertEqual([item["protocol"] for item in result["listeners"]], ["HTTP / SOCKS5", "HTTP", "SOCKS5"])
        self.assertEqual(result["listeners"][0]["address"], "[2001:db8::12]:9999")

    def test_only_enabled_proxy_ports_are_listed(self):
        for port in (None, 0, -1, True, 65536, "9999"):
            with self.subTest(port=port):
                self.assertEqual(proxy_access({"mixed-port": port, "redir-port": 7892}, "invalid")["listeners"], [])

    def test_accounts_are_masked_by_default_and_colons_in_password_are_preserved(self):
        config = {"authentication": ["user:example:password", "second:", None]}
        public = proxy_accounts(config)
        self.assertEqual(public, [{"id": 0, "username": "user"}, {"id": 1, "username": "second"}])
        self.assertNotIn("password", json.dumps(public))
        self.assertEqual(proxy_accounts(config, reveal=True)[0]["password"], "example:password")
        self.assertEqual(proxy_accounts(config, reveal=True)[1]["password"], "")

    def test_controller_username_only_response_is_visible_without_password(self):
        self.assertEqual(proxy_accounts({"authentication": ["remote"]}), [{"id": 0, "username": "remote"}])

    def test_username_only_core_credentials_resolve_from_current_managed_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.yaml"
            managed = Path(directory) / "managed.yaml"
            base.write_text('authentication: ["remote:old-value"]')
            managed.write_text('authentication: ["remote:new:example-value", "unused:private-value"]')
            live = {"authentication": ["remote"]}
            accounts = proxy_credentials(live, [managed, base])
            self.assertEqual(accounts, [{"id": 0, "username": "remote", "password": "new:example-value"}])
            managed.write_text('authentication: ["remote:rotated-value"]')
            self.assertEqual(proxy_credentials(live, [managed, base])[0]["password"], "rotated-value")

    def test_configured_accounts_are_never_returned_unless_the_live_core_lists_them(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text('authentication: ["unused:private-value"]')
            self.assertEqual(proxy_credentials({}, [config]), [])
            with self.assertRaises(ValueError):
                proxy_credentials({"authentication": ["current-user"]}, [config])

    def test_wildcard_with_lan_disabled_uses_loopback(self):
        self.assertEqual(proxy_host({"bind-address": "*", "allow-lan": False}, "192.168.1.0/24"), "127.0.0.1")

    def test_lan_address_is_taken_from_the_host_route_without_sending_packets(self):
        probe = MagicMock()
        probe.__enter__.return_value = probe
        probe.getsockname.return_value = ("192.168.1.12", 20000)
        with patch("server.proxy_access.socket.socket", return_value=probe):
            self.assertEqual(proxy_host({"allow-lan": True}, "192.168.1.0/24"), "192.168.1.12")
        probe.connect.assert_called_once_with(("192.168.1.1", 9))
        probe.send.assert_not_called()

    def test_address_discovery_failure_does_not_invent_a_gateway_ip(self):
        with patch("server.proxy_access.socket.socket", side_effect=OSError("no route")):
            result = proxy_access({"allow-lan": True, "mixed-port": 9999}, "192.168.1.0/24")
        self.assertIsNone(result["listeners"][0]["address"])


class ProxyAccessApiTests(unittest.IsolatedAsyncioTestCase):
    async def fetch(self, path, user, config=None, failure=None):
        core = AsyncMock(return_value=config, side_effect=failure)
        with patch.object(main.auth, "verify", return_value=user), patch.object(main.mihomo, "get", core):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                response = await client.get(path)
        return response, core

    async def test_unauthenticated_and_viewer_requests_never_read_core_credentials(self):
        for user, status in ((None, 401), ({"id": 2, "role": "viewer", "allowedDevices": []}, 403)):
            for path in ("/api/gateway/proxy", "/api/gateway/proxy/credentials"):
                with self.subTest(user=user, path=path):
                    response, core = await self.fetch(path, user)
                    self.assertEqual(response.status_code, status)
                    core.assert_not_awaited()

    async def test_admin_summary_uses_live_config_and_never_returns_password_or_controller_secret(self):
        response, core = await self.fetch("/api/gateway/proxy", {"id": 1, "role": "admin"}, {
            "mixed-port": 9999, "bind-address": "192.168.1.12", "allow-lan": True,
            "authentication": ["example:proxy-test-secret"], "secret": "controller-test-secret",
            "skip-auth-prefixes": ["127.0.0.0/8"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["vary"], "Cookie")
        self.assertEqual(response.json()["listeners"][0]["address"], "192.168.1.12:9999")
        self.assertEqual(response.json()["skipAuthPrefixes"], ["127.0.0.0/8"])
        self.assertNotIn("proxy-test-secret", response.text)
        self.assertNotIn("controller-test-secret", response.text)
        core.assert_awaited_once_with("/configs")

    async def test_admin_reveal_is_uncached_and_reads_latest_core_credentials(self):
        for password in ("first:value", "rotated-value"):
            response, core = await self.fetch("/api/gateway/proxy/credentials", {"id": 1, "role": "admin"}, {"authentication": [f"example:{password}"]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json(), {"accounts": [{"id": 0, "username": "example", "password": password}]})
            core.assert_awaited_once_with("/configs")

    async def test_disabled_authentication_has_no_fabricated_account(self):
        response, _ = await self.fetch("/api/gateway/proxy/credentials", {"id": 1, "role": "admin"}, {})
        self.assertEqual(response.json(), {"accounts": []})

    async def test_username_only_live_core_reads_password_from_mounted_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text('authentication: ["example:mounted-test-value"]')
            with patch.object(main, "settings", replace(main.settings, config_path=path)):
                response, _ = await self.fetch("/api/gateway/proxy/credentials", {"id": 1, "role": "admin"}, {"authentication": ["example"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accounts"][0]["password"], "mounted-test-value")

    async def test_missing_current_password_fails_without_fabricating_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "settings", replace(main.settings, config_path=Path(directory)/"missing.yaml")):
                response, _ = await self.fetch("/api/gateway/proxy/credentials", {"id": 1, "role": "admin"}, {"authentication": ["example"]})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_controller_failure_is_clear_and_does_not_leak_sensitive_exception(self):
        response, _ = await self.fetch("/api/gateway/proxy/credentials", {"id": 1, "role": "admin"}, failure=httpx.ConnectError("secret-url-test"))
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("secret-url-test", response.text)
