import json
import random
import re
import socket
import sqlite3
import threading
from copy import deepcopy
from pathlib import Path

from flask import Flask, request, jsonify

from apitest.engine.fake_data import generate_fake_value as _gen_fake, _next_auto_id


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
    """Create a Flask app that mocks the given OpenAPI spec with schema-aware responses."""
    app = Flask(__name__)

    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS store ("
               "resource TEXT, resource_id TEXT, data TEXT, "
               "PRIMARY KEY (resource, resource_id))")

    # Build a lookup: (method, path) -> response schema + examples
    schemas = _extract_schemas(spec)
    paths = spec.get("paths", {})

    for url_path, methods in paths.items():
        flask_path = url_path.replace("{", "<").replace("}", ">")

        for method in ["get", "post", "put", "delete", "patch"]:
            operation = methods.get(method)
            if operation is None:
                continue
            _register_route(app, method, flask_path, url_path, operation, db, schemas)

    return app


def _extract_schemas(spec: dict) -> dict:
    """Extract all named schemas from components/schemas, resolving $ref chains."""
    return spec.get("components", {}).get("schemas", {})


def _resolve_schema(schema_obj: dict, schemas: dict) -> dict:
    """Resolve $ref references in a schema object."""
    if not isinstance(schema_obj, dict):
        return {"type": "string"}
    if "$ref" in schema_obj:
        ref_name = schema_obj["$ref"].split("/")[-1]
        resolved = schemas.get(ref_name, {})
        return _resolve_schema(resolved, schemas)
    return schema_obj


def _get_response_schema(operation: dict, schemas: dict) -> dict | None:
    """Extract the JSON response schema for the first 2xx response."""
    for status_str, resp in operation.get("responses", {}).items():
        try:
            code = int(status_str)
        except ValueError:
            continue
        if 200 <= code < 300:
            content = resp.get("content", {})
            json_content = content.get("application/json", {})
            schema = json_content.get("schema", {})
            if schema:
                return _resolve_schema(schema, schemas)
    return None


def _get_request_body_schema(operation: dict, schemas: dict) -> dict | None:
    """Extract the JSON request body schema."""
    rb = operation.get("requestBody", {})
    content = rb.get("content", {})
    json_content = content.get("application/json", {})
    schema = json_content.get("schema", {})
    if schema:
        return _resolve_schema(schema, schemas)
    return None


# ---- Fake data generator adapter ----

def _generate_fake_value(prop_name: str, prop_schema: dict, schemas: dict) -> object:
    """Generate a realistic fake value for a single property based on its schema."""
    resolved = _resolve_schema(prop_schema, schemas)
    return _gen_fake(
        prop_name,
        schema_type=resolved.get("type", "string"),
        enum=resolved.get("enum"),
        minimum=resolved.get("minimum"),
        maximum=resolved.get("maximum"),
        min_length=resolved.get("minLength"),
        max_length=resolved.get("maxLength"),
        fmt=resolved.get("format", ""),
    )


def _generate_fake_data(schema: dict, schemas: dict) -> dict:
    """Generate a complete fake data object from a schema."""
    resolved = _resolve_schema(schema, schemas)

    if resolved.get("type") == "array":
        item_schema = resolved.get("items", {"type": "object", "properties": {}})
        count = random.randint(1, 3)
        return [_generate_fake_data(item_schema, schemas) for _ in range(count)]

    if resolved.get("type") == "object" or "properties" in resolved:
        props = resolved.get("properties", {})
        result = {}
        for name, prop_schema in props.items():
            result[name] = _generate_fake_value(name, prop_schema, schemas)
        # Add an id if not present
        if "id" not in result and "Id" not in str(list(props.keys())):
            pass  # Only add id for top-level objects
        return result

    return {}


def _make_response_data(operation: dict, schemas: dict, stored_data: dict | None = None,
                        is_list: bool = False) -> object:
    """Build response data matching the response schema, merging with stored data if available."""
    resp_schema = _get_response_schema(operation, schemas)
    req_schema = _get_request_body_schema(operation, schemas)

    # Use the response schema if available, otherwise fall back to request body schema
    schema = resp_schema or req_schema
    if schema is None:
        # No schema at all — return stored data or empty
        if stored_data:
            return stored_data
        return [] if is_list else {}

    # Generate the response wrapper
    resp_obj = _resolve_schema(schema, schemas)

    # Handle wrapped responses like {code, message, data: {...}}
    props = resp_obj.get("properties", {})
    if "code" in props and "data" in props:
        data_schema = props["data"]
        data_resolved = _resolve_schema(data_schema, schemas)

        if is_list:
            # Paginated list endpoint: data is an object with {total, page, list, ...}
            fake_data = _generate_fake_data(data_resolved, schemas)
            # Ensure list field has items
            data_props = data_resolved.get("properties", {})
            if "list" in data_props:
                item_schema = data_props["list"].get("items", {"type": "object", "properties": {}})
                items = [_generate_fake_data(item_schema, schemas)
                        for _ in range(random.randint(1, 3))]
                if isinstance(fake_data, dict):
                    fake_data["list"] = items
            return {
                "code": 200,
                "message": "success",
                "data": fake_data,
            }
        else:
            # Single item endpoint: data is an object
            if stored_data:
                fake = _generate_fake_data(data_resolved, schemas)
                if isinstance(fake, dict):
                    fake.update(stored_data)
                return {"code": 200, "message": "success", "data": fake}
            else:
                fake = _generate_fake_data(data_resolved, schemas)
                return {"code": 200, "message": "success", "data": fake}

    # Unwrapped response
    if stored_data:
        return stored_data
    if is_list:
        return [_generate_fake_data(schema, schemas) for _ in range(random.randint(1, 3))]
    return _generate_fake_data(schema, schemas)


# ---- Route registration ----

def _register_route(app, method, flask_path, spec_path, operation, db, schemas):
    has_path_param = "{" in spec_path

    body_required_fields = []
    rb = operation.get("requestBody", {})
    if rb:
        content = rb.get("content", {})
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {})
        if body_schema:
            body_schema = _resolve_schema(body_schema, schemas)
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
                    stored = json.loads(row["data"])
                    return jsonify(_make_response_data(operation, schemas, stored)), 200
                return jsonify({"code": 404, "message": "not found"}), 404
            else:
                rows = db.execute(
                    "SELECT data FROM store WHERE resource=?", (resource,)
                ).fetchall()
                # Determine if this is a list or single-item endpoint from the schema
                is_list = _is_list_endpoint(operation, schemas)
                if rows:
                    stored_list = [json.loads(r["data"]) for r in rows]
                    if is_list:
                        resp_schema = _get_response_schema(operation, schemas)
                        if resp_schema:
                            resp_props = _resolve_schema(resp_schema, schemas).get("properties", {})
                            if "data" in resp_props:
                                return jsonify({
                                    "code": 200, "message": "success",
                                    "data": stored_list
                                }), 200
                        return jsonify(stored_list), 200
                    else:
                        return jsonify(_make_response_data(operation, schemas, stored_list[0])), 200
                # No stored data: generate fake data from schema
                return jsonify(_make_response_data(operation, schemas, is_list=is_list)), 200

        elif method == "post":
            data = request.get_json(silent=True) or {}
            if body_required_fields:
                missing = [f for f in body_required_fields if f not in data]
                if missing:
                    return jsonify({"code": 400, "message": f"missing required fields: {missing}"}), 400
            resource_id = str(_next_auto_id())
            data["id"] = resource_id
            db.execute(
                "INSERT OR REPLACE INTO store (resource, resource_id, data) VALUES (?, ?, ?)",
                (resource, resource_id, json.dumps(data)),
            )
            db.commit()
            resp = _make_response_data(operation, schemas, data)
            success_code = _get_success_status(operation.get("responses", {}))
            return jsonify(resp), success_code

        elif method == "put":
            data = request.get_json(silent=True) or {}
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if not row:
                    return jsonify({"code": 404, "message": "not found"}), 404
                existing = json.loads(row["data"])
                existing.update(data)
                db.execute(
                    "INSERT OR REPLACE INTO store (resource, resource_id, data) VALUES (?, ?, ?)",
                    (resource, resource_id, json.dumps(existing)),
                )
                db.commit()
                resp = _make_response_data(operation, schemas, existing)
                return jsonify(resp), 200
            return jsonify({"code": 400, "message": "put requires an id"}), 400

        elif method == "delete":
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if not row:
                    return jsonify({"code": 404, "message": "not found"}), 404
                db.execute(
                    "DELETE FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                )
                db.commit()
                return "", 204
            return jsonify({"code": 400, "message": "delete requires an id"}), 400

        elif method == "patch":
            data = request.get_json(silent=True) or {}
            if has_path_param:
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if not row:
                    return jsonify({"code": 404, "message": "not found"}), 404
                existing = json.loads(row["data"])
                existing.update(data)
                db.execute(
                    "INSERT OR REPLACE INTO store (resource, resource_id, data) VALUES (?, ?, ?)",
                    (resource, resource_id, json.dumps(existing)),
                )
                db.commit()
                resp = _make_response_data(operation, schemas, existing)
                return jsonify(resp), 200
            return jsonify({"code": 400, "message": "patch requires an id"}), 400

    handler.__name__ = f"{method}_{flask_path}"
    app.add_url_rule(flask_path, f"{method}_{flask_path}", handler, methods=[method.upper()])


def _is_list_endpoint(operation: dict, schemas: dict) -> bool:
    """Heuristic: check if the response schema indicates a list/paginated endpoint."""
    resp_schema = _get_response_schema(operation, schemas)
    if resp_schema is None:
        # No schema — default to list for GET without path param
        return True
    resolved = _resolve_schema(resp_schema, schemas)
    props = resolved.get("properties", {})
    if "data" in props:
        data_schema = _resolve_schema(props["data"], schemas)
        # If data has pagination fields (total, page, list) or is an array, it's a list
        if data_schema.get("type") == "array":
            return True
        data_props = data_schema.get("properties", {})
        if "list" in data_props or "total" in data_props:
            return True
        # If data is a single object (no list/total), it's a single-item endpoint
        if data_props:
            return False
    # If the top-level type is array, it's a list
    if resolved.get("type") == "array":
        return True
    # No data wrapper at all — assume single object
    return False


def _get_success_status(responses: dict) -> int:
    for status_str in responses:
        try:
            code = int(status_str)
            if 200 <= code < 300:
                return code
        except ValueError:
            continue
    return 200


def _extract_resource(path: str) -> str:
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return parts[-1] if parts else "root"
