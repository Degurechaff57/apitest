import pytest
import httpx
from apitest.engine.mock_server import MockServer, create_mock_app


MINIMAL_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Test", "version": "1.0"},
    "paths": {
        "/api/users": {
            "get": {
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                "responses": {"201": {"description": "Created"}},
            },
        },
        "/api/users/{userId}": {
            "get": {
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "OK"}},
            },
            "delete": {
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}},
                ],
                "responses": {"204": {"description": "No Content"}},
            },
        },
    },
}


class TestMockServer:
    def test_server_starts_and_stops(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        assert server.url.startswith("http://")
        server.stop()
        assert not server.is_running()

    def test_get_endpoint_returns_200(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        try:
            resp = httpx.get(f"{server.url}/api/users")
            assert resp.status_code == 200
        finally:
            server.stop()

    def test_post_and_get_resource(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        try:
            resp = httpx.post(f"{server.url}/api/users", json={"name": "Alice"})
            assert resp.status_code == 201
            data = resp.json()
            assert "id" in data
            user_id = data["id"]
            resp = httpx.get(f"{server.url}/api/users/{user_id}")
            assert resp.status_code == 200
            assert resp.json()["name"] == "Alice"
        finally:
            server.stop()

    def test_get_nonexistent_returns_404(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        try:
            resp = httpx.get(f"{server.url}/api/users/nonexistent")
            assert resp.status_code == 404
        finally:
            server.stop()

    def test_delete_resource(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        try:
            resp = httpx.post(f"{server.url}/api/users", json={"name": "Bob"})
            user_id = resp.json()["id"]
            resp = httpx.delete(f"{server.url}/api/users/{user_id}")
            assert resp.status_code == 204
            resp = httpx.get(f"{server.url}/api/users/{user_id}")
            assert resp.status_code == 404
        finally:
            server.stop()

    def test_post_missing_required_field_returns_400(self):
        app = create_mock_app(MINIMAL_OPENAPI)
        server = MockServer(app, port=0)
        server.start()
        try:
            resp = httpx.post(f"{server.url}/api/users", json={"wrong_field": "x"})
            assert resp.status_code == 400
        finally:
            server.stop()
