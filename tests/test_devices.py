import unittest

from server.main import _is_infrastructure_source


class DeviceSourceTests(unittest.TestCase):
    def test_hides_configured_mihomo_and_docker_sources(self):
        for address in ("127.0.0.1", "::1", "198.18.0.1", "172.17.0.2", "172.18.0.3"):
            with self.subTest(address=address):
                self.assertTrue(_is_infrastructure_source(address))

    def test_keeps_real_gateway_and_proxy_clients(self):
        for address in ("192.168.31.42", "192.168.31.225", "10.18.18.244"):
            with self.subTest(address=address):
                self.assertFalse(_is_infrastructure_source(address))


if __name__ == "__main__":
    unittest.main()
