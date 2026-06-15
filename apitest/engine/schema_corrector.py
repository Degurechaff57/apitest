import re
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample
from apitest.engine.fake_data import generate_fake_value


def correct_example(example: TestExample, endpoint: Endpoint) -> TestExample:
    # 1. Fix expected status from spec
    success_code = _get_success_code(endpoint)
    if example.category in ("happy-path",) and example.expected_status != success_code:
        example.expected_status = success_code

    # 2. Generate valid request body from schema params
    body_params = [p for p in endpoint.parameters if p.location == "body"]
    if body_params and endpoint.method in ("POST", "PUT", "PATCH"):
        body = {}
        for p in body_params:
            body[p.name] = generate_fake_value(
                p.name, p.schema_type,
                enum=p.enum, minimum=p.minimum, maximum=p.maximum,
                min_length=p.min_length, max_length=p.max_length,
                fmt=p.format,
            )
        if body:
            example.request_body = body

    # 3. Add auth header if endpoint requires it
    if endpoint.has_auth and "Authorization" not in example.request_headers:
        example.request_headers["Authorization"] = "Bearer ${TOKEN}"

    # 4. Ensure body assertions have sensible defaults
    if not example.expected_body_contains:
        example.expected_body_contains = ["data"]

    return example


def _get_success_code(endpoint: Endpoint) -> int:
    for resp in endpoint.responses:
        if 200 <= resp.status_code < 300:
            return resp.status_code
    return 200 if endpoint.method != "POST" else 201


class SchemaCorrector:
    def correct(self, examples: list[TestExample], endpoints: list[Endpoint]) -> list[TestExample]:
        lookup: dict[str, Endpoint] = {}
        for ep in endpoints:
            lookup[f"{ep.method} {ep.path}"] = ep

        for ex in examples:
            ep = lookup.get(ex.endpoint)
            if ep is None:
                ep = self._fuzzy_match(ex.endpoint, lookup)
            if ep is not None:
                correct_example(ex, ep)

        return examples

    def _fuzzy_match(self, example_endpoint: str, lookup: dict[str, Endpoint]) -> Endpoint | None:
        try:
            ex_method, ex_path = example_endpoint.split(" ", 1)
        except ValueError:
            return None
        ex_parts = ex_path.split("/")
        for key, ep in lookup.items():
            ep_method, ep_path = key.split(" ", 1)
            if ep_method != ex_method:
                continue
            ep_parts = ep_path.split("/")
            if len(ep_parts) != len(ex_parts):
                continue
            match = True
            for sp, epp in zip(ep_parts, ex_parts):
                if sp.startswith("{"):
                    continue
                if sp != epp:
                    match = False
                    break
            if match:
                return ep
        return None
