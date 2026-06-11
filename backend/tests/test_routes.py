import unittest
from collections import defaultdict

from fastapi.testclient import TestClient

from main import app


class RouteRegistrationTest(unittest.TestCase):
    def test_method_and_path_pairs_are_unique(self):
        routes = defaultdict(list)
        for route in app.routes:
            for method in route.methods or []:
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


if __name__ == "__main__":
    unittest.main()
