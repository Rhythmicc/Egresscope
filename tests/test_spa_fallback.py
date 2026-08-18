import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from server.main import _spa_fallback


class SpaFallbackTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.static = Path(self.directory.name)
        (self.static / "index.html").write_text("app shell", encoding="utf-8")
        (self.static / "assets").mkdir()
        (self.static / "assets" / "app.js").write_text("app js", encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_unknown_api_path_is_404_not_the_app_shell(self):
        for path in ("api", "api/nope", "api/users/extra"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPException) as caught:
                    _spa_fallback(path, self.static)
                self.assertEqual(caught.exception.status_code, 404)

    def test_serves_existing_static_asset(self):
        response = _spa_fallback("assets/app.js", self.static)
        self.assertTrue(str(response.path).endswith("assets/app.js"))

    def test_falls_back_to_index_html_for_unknown_app_route(self):
        response = _spa_fallback("flow/step-two", self.static)
        self.assertTrue(str(response.path).endswith("index.html"))

    def test_path_traversal_cannot_escape_static_dir(self):
        response = _spa_fallback("../etc/passwd", self.static)
        self.assertTrue(str(response.path).endswith("index.html"))


if __name__ == "__main__":
    unittest.main()
