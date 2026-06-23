from pathlib import Path

import yaml
from apitest.models.endpoint import Endpoint, Parameter, RequestBody, Response


def detect_format(filepath: str) -> str:
    """Detect API doc format from filename or content. Returns 'openapi', 'postman', or 'markdown'."""
    name = Path(filepath).name.lower()
    ext = Path(filepath).suffix.lower()
    if "postman" in name or "collection" in name:
        return "postman"
    if ext in (".md", ".txt", ".markdown"):
        return "markdown"
    return "openapi"


def parse_text(filepath: str) -> str:
    """Read a markdown or text API document as raw content for LLM processing."""
    return Path(filepath).read_text()


def parse_openapi(filepath: str) -> list[Endpoint]:
    """Parse an OpenAPI 3.x or Swagger 2.0 spec into Endpoint list."""
    with open(filepath) as f:
        spec = yaml.safe_load(f)

    endpoints: list[Endpoint] = []
    paths = spec.get("paths", {})

    _HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head", "trace"}

    for path, methods in paths.items():
        for method in [m for m in methods if m in _HTTP_METHODS]:
            operation = methods[method]
            endpoint = _parse_operation(method.upper(), path, operation, spec)
            endpoints.append(endpoint)

    # Sort: lifecycle order (POST -> GET -> PUT -> DELETE)
    method_order = {"POST": 0, "GET": 1, "PUT": 2, "PATCH": 3, "DELETE": 4, "OPTIONS": 5, "HEAD": 6}
    endpoints.sort(key=lambda e: (e.resource, method_order.get(e.method, 99), e.path))
    return endpoints


def _parse_operation(method: str, path: str, operation: dict, spec: dict) -> Endpoint:
    parameters = _parse_parameters(operation.get("parameters", []))

    request_body = None
    if "requestBody" in operation:
        rb = operation["requestBody"]
        content = rb.get("content", {})
        json_content = content.get("application/json", {})
        schema_ref = json_content.get("schema", {}).get("$ref", "")
        request_body = RequestBody(
            content_type="application/json",
            schema_ref=schema_ref.split("/")[-1] if schema_ref else "",
            required=rb.get("required", False),
        )

    # Extract body schema properties as body-location Parameters
    if request_body and request_body.schema_ref == "":  # inline schema, not $ref
        rb = operation.get("requestBody", {})
        content = rb.get("content", {})
        json_content = content.get("application/json", {})
        body_schema = json_content.get("schema", {})
        body_props = body_schema.get("properties", {})
        body_required = body_schema.get("required", [])
        for prop_name, prop_schema in body_props.items():
            parameters.append(Parameter(
                name=prop_name,
                location="body",
                schema_type=prop_schema.get("type", "string"),
                required=prop_name in body_required,
                description=prop_schema.get("description", ""),
                enum=prop_schema.get("enum"),
                minimum=prop_schema.get("minimum"),
                maximum=prop_schema.get("maximum"),
                min_length=prop_schema.get("minLength"),
                max_length=prop_schema.get("maxLength"),
                format=prop_schema.get("format", ""),
                default=prop_schema.get("default"),
            ))

    responses = []
    for status_str, resp in operation.get("responses", {}).items():
        try:
            status_code = int(status_str)
        except ValueError:
            continue
        responses.append(Response(
            status_code=status_code,
            description=resp.get("description", ""),
        ))

    return Endpoint(
        method=method,
        path=path,
        operation_id=operation.get("operationId", ""),
        summary=operation.get("summary", ""),
        description=operation.get("description", ""),
        tags=operation.get("tags", []),
        parameters=parameters,
        request_body=request_body,
        responses=responses,
        security=operation.get("security", []),
    )


def _parse_parameters(params: list[dict]) -> list[Parameter]:
    result = []
    for p in params:
        schema = p.get("schema", {})
        result.append(Parameter(
            name=p["name"],
            location=p["in"],
            schema_type=schema.get("type", "string"),
            required=p.get("required", False),
            description=p.get("description", ""),
            enum=schema.get("enum"),
            minimum=schema.get("minimum"),
            maximum=schema.get("maximum"),
            min_length=schema.get("minLength"),
            max_length=schema.get("maxLength"),
            format=schema.get("format", ""),
            default=schema.get("default"),
        ))
    return result
