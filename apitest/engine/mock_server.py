import json
import socket
import sqlite3
import threading
import uuid

from flask import Flask, request, jsonify


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class MockServer:
    """Wraps a Flask mock server running in a background thread."""

    def __init__(self, app: Flask, port: int | None = None):
        self.app = app
        self.port = port or _get_free_port()
        self._thread = None
        self._running = False

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(
            target=self.app.run,
            kwargs={"host": "127.0.0.1", "port": self.port, "debug": False, "use_reloader": False},
            daemon=True,
        )
        self._thread.start()
        import time
        time.sleep(0.1)

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running


def create_mock_app(spec: dict) -> Flask:
    """Create a Flask app that mocks the given OpenAPI spec."""
    app = Flask(__name__)

    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS store ("
               "resource TEXT, resource_id TEXT, data TEXT, "
               "PRIMARY KEY (resource, resource_id))")

    paths = spec.get("paths", {})

    for url_path, methods in paths.items():
        flask_path = url_path.replace("{", "<").replace("}", ">")

        for method in ["get", "post", "put", "delete", "patch"]:
            operation = methods.get(method)
            if operation is None:
                continue
            _register_route(app, method, flask_path, url_path, operation, db)

    return app


def _register_route(app, method, flask_path, spec_path, operation, db):
    has_path_param = "{" in spec_path

    body_required_fields = []
    rb = operation.get("requestBody", {})
    if rb:
        content = rb.get("content", {})
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {})
        if body_schema:
            body_required_fields = body_schema.get("required", [])

    resource = _extract_resource(spec_path)

    def handler(**kwargs):
        if method == "get":
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if row:
                    return jsonify(json.loads(row["data"])), 200
                return jsonify({"error": "not found"}), 404
            else:
                rows = db.execute(
                    "SELECT data FROM store WHERE resource=?", (resource,)
                ).fetchall()
                return jsonify([json.loads(r["data"]) for r in rows]), 200

        elif method == "post":
            data = request.get_json(silent=True) or {}
            if body_required_fields:
                missing = [f for f in body_required_fields if f not in data]
                if missing:
                    return jsonify({"error": f"missing required fields: {missing}"}), 400
            resource_id = data.get("id") or str(uuid.uuid4())[:8]
            data["id"] = resource_id
            db.execute(
                "INSERT OR REPLACE INTO store (resource, resource_id, data) VALUES (?, ?, ?)",
                (resource, resource_id, json.dumps(data)),
            )
            db.commit()
            return jsonify(data), 201

        elif method == "put":
            data = request.get_json(silent=True) or {}
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if not row:
                    return jsonify({"error": "not found"}), 404
                existing = json.loads(row["data"])
                existing.update(data)
                existing["id"] = resource_id
                db.execute(
                    "INSERT OR REPLACE INTO store (resource, resource_id, data) VALUES (?, ?, ?)",
                    (resource, resource_id, json.dumps(existing)),
                )
                db.commit()
                return jsonify(existing), 200
            return jsonify({"error": "put requires an id"}), 400

        elif method == "delete":
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                db.execute(
                    "DELETE FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                )
                db.commit()
                return "", 204
            return jsonify({"error": "delete requires an id"}), 400

    handler.__name__ = f"{method}_{flask_path}"
    app.add_url_rule(flask_path, f"{method}_{flask_path}", handler, methods=[method.upper()])


def _extract_resource(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return parts[-1] if parts else "root"
