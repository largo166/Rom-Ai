import unittest
from collections import defaultdict

from fastapi.testclient import TestClient

from app.config import settings
import app.routes.health as health_routes
from main import app


class RouteRegistrationTest(unittest.TestCase):
    def test_method_and_path_pairs_are_unique(self):
        routes = defaultdict(list)
        for route in app.routes:
            for method in getattr(route, "methods", None) or []:
                if method not in {"HEAD", "OPTIONS"}:
                    routes[(method, route.path)].append(route.endpoint.__name__)

        duplicates = {key: endpoints for key, endpoints in routes.items() if len(endpoints) > 1}

        self.assertEqual(duplicates, {}, f"duplicate routes shadow handlers: {duplicates}")


class CorsTest(unittest.TestCase):
    def test_projects_api_allows_vite_fallback_port(self):
        client = TestClient(app)

        response = client.options(
            "/api/projects",
            headers={
                "Origin": "http://127.0.0.1:5176",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://127.0.0.1:5176")


class SettingsRouteTest(unittest.TestCase):
    def test_tencent_meeting_token_can_be_saved_without_echoing_secret(self):
        client = TestClient(app)
        original_token = settings.tencent_meeting_token
        original_write_env_value = health_routes.write_env_value
        writes = []
        try:
            settings.tencent_meeting_token = ""
            health_routes.write_env_value = lambda key, value: writes.append((key, value))

            response = client.post("/api/settings/tencent-meeting", json={"token": "token-for-test"})

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["tencent_meeting_configured"])
            self.assertNotIn("token-for-test", response.text)
            self.assertEqual(settings.tencent_meeting_token, "token-for-test")
            self.assertEqual(writes, [("TENCENT_MEETING_TOKEN", "token-for-test")])
        finally:
            settings.tencent_meeting_token = original_token
            health_routes.write_env_value = original_write_env_value


if __name__ == "__main__":
    unittest.main()
