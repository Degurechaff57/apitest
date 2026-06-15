# Schema-Based Test Data Generation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LLM-hallucinated request bodies and assertions with schema-derived test data, so generated tests pass against the mock server regardless of which LLM model is used.

**Architecture:** Extract the existing fake data generator from `mock_server.py` into a shared `apitest/engine/fake_data.py` module. Build a `SchemaCorrector` that walks each LLM-generated example, looks up the matching parsed Endpoint, and overwrites request bodies, path params, expected status codes, and response assertions from the schema. The LLM continues to decide test strategy (which endpoints, categories, coverage), but all test DATA comes from the schema.

**Tech Stack:** Python 3.10+, dataclasses, pyyaml (already in deps)

---

## File Structure

```
apitest/engine/
  fake_data.py          # NEW — shared fake data generator (extracted from mock_server.py)
  mock_server.py        # MODIFY — import from fake_data.py, delete duplicated code
  schema_corrector.py   # NEW — corrects LLM examples against parsed Endpoints
  runner.py             # MODIFY — use corrected example data directly
apitest/cli/
  main.py               # MODIFY — call SchemaCorrector in examples/go commands
tests/
  test_fake_data.py      # NEW — unit tests for fake data generator
  test_schema_corrector.py # NEW — unit tests for schema corrector
```

**File responsibilities:**
- `fake_data.py` — pure function: takes property name + Parameter/type info → returns valid test value. No OpenAPI spec dependency.
- `schema_corrector.py` — takes list[TestExample] + list[Endpoint] → returns corrected list[TestExample]. Uses fake_data.py.
- `mock_server.py` — delegates `_generate_fake_value` to `fake_data.py`.

---

### Task 1: Extract Fake Data Generator to Shared Module

**Files:**
- Create: `apitest/engine/fake_data.py`
- Modify: `apitest/engine/mock_server.py` — delete `_generate_fake_value` and related helpers, import from fake_data
- Create: `tests/test_fake_data.py`

The fake data generator already works well in `mock_server.py`. We extract it into a standalone module so both the mock server and the schema corrector use the same logic.

- [ ] **Step 1: Write test for fake data generator**

```python
# tests/test_fake_data.py
import pytest
from apitest.engine.fake_data import generate_fake_value


class TestFakeData:
    def test_generates_phone_from_property_name(self):
        val = generate_fake_value("phone", "string")
        assert val.startswith("138")
        assert len(val) == 11

    def test_generates_email_from_format(self):
        val = generate_fake_value("email", "string", fmt="email")
        assert "@" in val
        assert ".com" in val

    def test_generates_integer_in_range(self):
        val = generate_fake_value("age", "integer", minimum=0, maximum=150)
        assert isinstance(val, int)
        assert 0 <= val <= 150

    def test_generates_enum_value(self):
        val = generate_fake_value("role", "string", enum=["admin", "user", "guest"])
        assert val in ["admin", "user", "guest"]

    def test_generates_boolean(self):
        val = generate_fake_value("active", "boolean")
        assert isinstance(val, bool)

    def test_generates_code_from_name(self):
        val = generate_fake_value("code", "string")
        assert val == "123456"

    def test_generates_nickname(self):
        val = generate_fake_value("nickname", "string")
        assert isinstance(val, str)
        assert len(val) > 0

    def test_generates_from_parameter_object(self):
        from apitest.models.endpoint import Parameter
        p = Parameter(name="targetUserId", location="body", schema_type="integer", required=True, minimum=1)
        val = generate_fake_value(p.name, p.schema_type, enum=p.enum,
                                  minimum=p.minimum, maximum=p.maximum,
                                  min_length=p.min_length, max_length=p.max_length,
                                  fmt=p.format)
        assert isinstance(val, int)
        assert val >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fake_data.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Create fake_data.py**

The existing `_generate_fake_value` in mock_server.py needs to be adapted: the mock server version takes `(prop_name, prop_schema_dict, schemas_dict)` — schema dicts from raw YAML. The shared version takes flat parameters (type, enum, min, max, format) that work with both raw dicts AND our Endpoint model objects.

```python
# apitest/engine/fake_data.py
import random

_SAMPLE_NAMES = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace",
                 "Henry", "Iris", "Jack", "Kate", "Leo", "Mia", "Noah", "Olivia"]
_SAMPLE_TAGS = ["摄影", "旅行", "探店", "美食", "露营", "装备", "穿搭", "美妆",
                "读书", "运动", "音乐", "电影", "科技", "生活", "萌宠"]
_SAMPLE_TITLES = ["周末露营装备推荐", "探店藏在巷子里的咖啡馆", "夏日护肤好物分享",
                  "城市周边一日游攻略", "新入手的相机测评", "在家也能做的美味甜点"]
_SAMPLE_CONTENTS = ["最近入手的露营装备分享...", "这家店环境很好，推荐给大家",
                    "用了两周后的真实感受，值得入手", "详细攻略，建议收藏"]
_next_id = 1001


def _next_auto_id() -> int:
    global _next_id
    _next_id += 1
    return _next_id


def generate_fake_value(
    prop_name: str,
    schema_type: str = "string",
    *,
    enum: list | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    fmt: str = "",
) -> object:
    """Generate a realistic fake value for a single property.

    Uses the property name, type, constraints, and format to produce
    a value that looks realistic and satisfies schema constraints.

    Args:
        prop_name: The property/field name (e.g. 'phone', 'email', 'age')
        schema_type: JSON schema type (string, integer, number, boolean, array, object)
        enum: Allowed enum values
        minimum: Minimum numeric value
        maximum: Maximum numeric value
        min_length: Minimum string length
        max_length: Maximum string length
        fmt: Format hint (email, uri, date-time, uuid, etc.)
    """
    if enum:
        return random.choice(enum)

    if schema_type == "integer" or schema_type == "number":
        lo = int(minimum) if minimum is not None else 0
        hi = int(maximum) if maximum is not None else 99999
        return random.randint(lo, min(hi, 99999))

    if schema_type == "boolean":
        return random.choice([True, False])

    # String type — use name/format heuristics
    name_lower = prop_name.lower()

    if fmt == "email" or "email" in name_lower:
        return f"user{_next_auto_id()}@example.com"
    if fmt == "uri" or fmt == "url" or "avatar" in name_lower or "cover" in name_lower or "image" in name_lower:
        return f"https://cdn.example.com/{prop_name}/{_next_auto_id()}.jpg"
    if fmt == "date-time" or "time" in name_lower:
        return "2025-06-15 14:30:00"
    if fmt == "date" or "date" in name_lower:
        return "2025-06-15"
    if fmt == "uuid":
        return str(_next_auto_id())
    if "phone" in name_lower:
        return f"138{random.randint(10000000, 99999999)}"
    if "token" in name_lower:
        return f"eyJ{random.randint(100000, 999999)}.{random.randint(100000, 999999)}"
    if "name" in name_lower or "nickname" in name_lower:
        return random.choice(_SAMPLE_NAMES)
    if "title" in name_lower:
        return random.choice(_SAMPLE_TITLES)
    if "content" in name_lower or "bio" in name_lower or "description" in name_lower:
        return random.choice(_SAMPLE_CONTENTS)
    if "tag" in name_lower:
        return random.sample(_SAMPLE_TAGS, min(3, len(_SAMPLE_TAGS)))
    if "code" in name_lower:
        return "123456"
    if "message" in name_lower:
        return "操作成功"
    if "gender" in name_lower:
        return random.choice([0, 1, 2])
    if "count" in name_lower or "total" in name_lower:
        return random.randint(100, 20000)
    if "price" in name_lower:
        return round(random.uniform(9.9, 999.0), 2)
    if "id" in name_lower and name_lower != "id":
        return _next_auto_id()
    if "id" == name_lower:
        return _next_auto_id()
    if "page" in name_lower:
        return 1
    if "size" in name_lower:
        return 20
    if "visibility" in name_lower:
        return "public"
    if name_lower.startswith("has") or name_lower.startswith("is") or name_lower.startswith("allow") or name_lower.startswith("show"):
        return True

    return f"sample-{prop_name}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_fake_data.py -v`
Expected: 8 PASS

- [ ] **Step 5: Update mock_server.py to use shared module**

Delete the `_generate_fake_value` function and `_next_auto_id`, `_SAMPLE_*` constants from `mock_server.py`. Replace with:

```python
from apitest.engine.fake_data import generate_fake_value as _generate_fake_value, _next_auto_id
```

The function signatures differ slightly — the mock server passes `(prop_name, prop_schema_dict, schemas_dict)`. We need a thin adapter in mock_server.py:

```python
def _generate_fake_value_adapter(prop_name: str, prop_schema: dict, schemas: dict) -> object:
    """Adapter: converts mock_server's (name, schema_dict, schemas) to flat args."""
    resolved = _resolve_schema(prop_schema, schemas)
    return generate_fake_value(
        prop_name,
        schema_type=resolved.get("type", "string"),
        enum=resolved.get("enum"),
        minimum=resolved.get("minimum"),
        maximum=resolved.get("maximum"),
        min_length=resolved.get("minLength"),
        max_length=resolved.get("maxLength"),
        fmt=resolved.get("format", ""),
    )
```

Then replace calls from `_generate_fake_value(name, schema, schemas)` to `_generate_fake_value_adapter(name, schema, schemas)`.

- [ ] **Step 6: Run full test suite to verify no regressions**

Run: `python3 -m pytest tests/ -q`
Expected: All existing tests still pass (49+)

- [ ] **Step 7: Commit**

```bash
git add apitest/engine/fake_data.py apitest/engine/mock_server.py tests/test_fake_data.py
git commit -m "refactor: extract fake data generator to shared module"
```

---

### Task 2: Build Schema Corrector

**Files:**
- Create: `apitest/engine/schema_corrector.py`
- Create: `tests/test_schema_corrector.py`

The corrector takes LLM-generated examples and overwrites request bodies, expected status codes, and response assertions using the parsed Endpoint schemas.

- [ ] **Step 1: Write test for schema corrector**

```python
# tests/test_schema_corrector.py
import pytest
from apitest.engine.schema_corrector import SchemaCorrector, correct_example
from apitest.models.endpoint import Endpoint, Parameter, RequestBody, Response
from apitest.models.example import TestExample


LOGIN_ENDPOINT = Endpoint(
    method="POST",
    path="/api/auth/login",
    operation_id="login",
    summary="用户登录",
    request_body=RequestBody(
        content_type="application/json",
        schema_ref="",
        required=True,
    ),
    parameters=[
        Parameter(name="phone", location="body", schema_type="string",
                  required=True, min_length=11, max_length=11),
        Parameter(name="code", location="body", schema_type="string",
                  required=True, min_length=6, max_length=6),
    ],
    responses=[Response(status_code=200), Response(status_code=401)],
)

GET_PROFILE = Endpoint(
    method="GET",
    path="/api/user/profile",
    operation_id="getUserProfile",
    parameters=[
        Parameter(name="userId", location="query", schema_type="integer", required=False),
    ],
    responses=[Response(status_code=200), Response(status_code=404)],
    security=[{"bearerAuth": []}],
)


class TestSchemaCorrector:
    def test_corrects_login_request_body(self):
        # LLM hallucinated wrong field names
        example = TestExample(
            id="TC-LOGIN-001", area="functional", category="happy-path",
            endpoint="POST /api/auth/login",
            description="Login with valid credentials",
            request_body={"username": "testuser", "password": "test123"},
            expected_status=201,  # wrong
            expected_body_contains=["token", "userId"],
        )
        corrected = correct_example(example, LOGIN_ENDPOINT)
        # Request body should now use schema field names
        assert "phone" in corrected.request_body
        assert "code" in corrected.request_body
        assert "username" not in corrected.request_body
        assert "password" not in corrected.request_body
        # Status code should match spec
        assert corrected.expected_status == 200
        # Assertions unchanged (LLM ones are reasonable)
        assert "token" in corrected.expected_body_contains

    def test_corrects_status_code_for_post(self):
        create_ep = Endpoint(
            method="POST", path="/api/items",
            responses=[Response(status_code=201), Response(status_code=400)],
        )
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="POST /api/items", description="Create item",
            expected_status=200,  # wrong — spec says 201
        )
        corrected = correct_example(example, create_ep)
        assert corrected.expected_status == 201

    def test_adds_auth_header_when_endpoint_requires_it(self):
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/user/profile", description="Get profile",
            expected_status=200,
        )
        corrected = correct_example(example, GET_PROFILE)
        assert "Authorization" in corrected.request_headers
        assert "${TOKEN}" in corrected.request_headers["Authorization"]

    def test_preserves_existing_auth_header(self):
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/user/profile", description="Get profile",
            request_headers={"Authorization": "Bearer ${TOKEN}"},
            expected_status=200,
        )
        corrected = correct_example(example, GET_PROFILE)
        assert corrected.request_headers["Authorization"] == "Bearer ${TOKEN}"

    def test_does_not_add_auth_for_public_endpoint(self):
        public_ep = Endpoint(
            method="GET", path="/api/search",
            responses=[Response(status_code=200)],
        )
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/search", description="Search",
            expected_status=200,
        )
        corrected = correct_example(example, public_ep)
        assert "Authorization" not in corrected.request_headers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_schema_corrector.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write schema_corrector.py**

```python
# apitest/engine/schema_corrector.py
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample
from apitest.engine.fake_data import generate_fake_value


def correct_example(example: TestExample, endpoint: Endpoint) -> TestExample:
    """Correct a single test example against its endpoint schema.

    Fixes:
    1. Request body — generates from schema, replacing hallucinated fields
    2. Expected status — uses the spec's success status code
    3. Auth headers — adds Authorization header if endpoint requires it
    4. Expected body assertions — keeps LLM suggestions, adds 'data' for wrapped responses
    """
    # 1. Fix expected status from spec
    success_code = _get_success_code(endpoint)
    if example.category == "happy-path" or example.expected_status != success_code:
        example.expected_status = success_code

    # 2. Generate valid request body from schema
    params = endpoint.parameters
    body_params = [p for p in params if p.location == "body"]
    if body_params and endpoint.method in ("POST", "PUT", "PATCH"):
        body = {}
        for p in body_params:
            body[p.name] = generate_fake_value(
                p.name, p.schema_type,
                enum=p.enum,
                minimum=p.minimum, maximum=p.maximum,
                min_length=p.min_length, max_length=p.max_length,
                fmt=p.format,
            )
        # Include required params even if not in body_params (from request_body schema)
        if body:
            example.request_body = body
    elif endpoint.method == "POST" and endpoint.request_body and not body_params:
        # POST with request body but params parsed from elsewhere
        # Keep LLM body if endpoint has a request_body definition but no parsed body params
        pass

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
    """Corrects a batch of LLM-generated examples against parsed endpoint schemas."""

    def correct(self, examples: list[TestExample], endpoints: list[Endpoint]) -> list[TestExample]:
        # Build endpoint lookup: "METHOD /path" -> Endpoint
        lookup: dict[str, Endpoint] = {}
        for ep in endpoints:
            lookup[f"{ep.method} {ep.path}"] = ep

        for ex in examples:
            ep = lookup.get(ex.endpoint)
            if ep is None:
                # Fuzzy match: normalize path params
                ep = self._fuzzy_match(ex.endpoint, lookup)

            if ep is not None:
                correct_example(ex, ep)

        return examples

    def _fuzzy_match(self, example_endpoint: str, lookup: dict[str, Endpoint]) -> Endpoint | None:
        ex_method, ex_path = example_endpoint.split(" ", 1)
        ex_parts = ex_path.split("/")

        for key, ep in lookup.items():
            ep_method, ep_path = key.split(" ", 1)
            if ep_method != ex_method:
                continue
            ep_parts = ep_path.split("/")
            if len(ep_parts) != len(ex_parts):
                continue
            match = True
            for sp, ep in zip(ep_parts, ex_parts):
                if sp.startswith("{"):
                    continue
                if sp != ep:
                    match = False
                    break
            if match:
                return ep
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_schema_corrector.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/schema_corrector.py tests/test_schema_corrector.py
git commit -m "feat: add schema corrector for LLM-generated examples"
```

---

### Task 3: Integrate Corrector into CLI Pipeline

**Files:**
- Modify: `apitest/cli/main.py` — replace `_correct_examples_against_endpoints` with SchemaCorrector
- Modify: `apitest/cli/main.py` — update `go` command to also correct examples

The CLI already has `_correct_examples_against_endpoints` in `main.py` — replace it with the new SchemaCorrector. Also apply correction in the `go` command.

- [ ] **Step 1: Replace old correction function**

In `apitest/cli/main.py`, replace the `_correct_examples_against_endpoints` function and `_paths_match` with:

```python
from apitest.engine.schema_corrector import SchemaCorrector


def _correct_examples_against_endpoints(examples, endpoints):
    """Fix request bodies, status codes, and headers based on parsed API spec."""
    corrector = SchemaCorrector()
    return corrector.correct(examples, endpoints)
```

Delete the old `_correct_examples_against_endpoints`, `_paths_match`, and `_get_schema_top_fields` functions.

- [ ] **Step 2: Add correction to go command**

The `go` command already generates examples via `gen.generate_examples(endpoints, cov, config.areas)` and stores them. After that line, add correction:

In the `go` command, find the section after example generation (where `test_examples` is assigned) and add:

```python
    # Schema correction (go command, after example generation)
    if doc_format != "markdown":
        test_examples = _correct_examples_against_endpoints(test_examples, endpoints)
```

The `examples` command already has this correction call. Verify it reads correctly.

- [ ] **Step 3: Run existing tests**

Run: `python3 -m pytest tests/ -q`
Expected: All existing tests pass

- [ ] **Step 4: Run full pipeline**

Run: `python3 -m apitest.cli.main go demo/specs/xiaohongshu-openapi.yaml --coverage smoke --mode mock 2>&1 | grep -E "PASSED|FAILED|passed|failed" | tail -20`

Expected: More tests pass than before (8/17). Target: 12+/17 passing.

- [ ] **Step 5: Commit**

```bash
git add apitest/cli/main.py
git commit -m "feat: integrate SchemaCorrector into CLI pipeline"
```

---

### Task 4: Update Runner for Schema-Aware Code Generation

**Files:**
- Modify: `apitest/engine/runner.py`

The runner already generates code from TestExample objects. After Task 3, the examples have corrected request bodies and status codes. But there are still LLM artifacts in the descriptions and test names. Clean up the runner to produce robust code.

- [ ] **Step 1: Add Content-Type header automatically for POST/PUT**

In `generate_pytest_file`, after the headers section, automatically add `Content-Type: application/json` for methods with a request body:

```python
        # Auto-add Content-Type for requests with body
        if http_method in ("post", "put", "patch") and body:
            if "Content-Type" not in headers:
                headers["Content-Type"] = "application/json"
```

- [ ] **Step 2: Fix DELETE with body to send as JSON content**

Change the DELETE handler to use `json=` (httpx actually does support it in newer versions, but to be safe):

```python
        elif http_method == "delete":
            if body:
                body_str = _py_repr(body)
                lines.append(f"        res = client.request('DELETE', '{path}', headers=headers, json={body_str})")
            else:
                lines.append(f"        res = client.{http_method}('{path}', headers=headers)")
```

- [ ] **Step 3: Run tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add apitest/engine/runner.py
git commit -m "fix: auto-add Content-Type header, fix DELETE with body"
```

---

### Task 5: Integration Verification

**Files:**
- Create/modify: no new files — verification only

- [ ] **Step 1: Run full unit test suite**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass (49+)

- [ ] **Step 2: Run full pipeline against demo spec**

```bash
rm -f apitest_tests/test_*.py
python3 -m apitest.cli.main go demo/specs/xiaohongshu-openapi.yaml --coverage smoke --mode mock
```

Expected: 12+/17 tests pass. The remaining failures should be limited to:
- Path parameter resolution (`{noteId}` → real ID) — known limitation
- Nested schema objects that the fake data generator doesn't handle

- [ ] **Step 3: Verify generated examples are schema-correct**

Run: `python3 -c "
import json
with open('tests/examples/examples.json') as f:
    data = json.load(f)
for ex in data['examples'][:3]:
    print(f'{ex[\"id\"]}: {ex[\"endpoint\"]}')
    print(f'  status={ex[\"expected\"][\"status\"]}')
    if ex.get('request', {}).get('body'):
        print(f'  body keys: {list(ex[\"request\"][\"body\"].keys())}')
    if ex.get('request', {}).get('headers'):
        print(f'  headers: {list(ex[\"request\"][\"headers\"].keys())}')
"`

Expected: Login example has `phone`, `code` in body (not `username`, `password`). Auth-protected endpoints have `Authorization` header. Status codes match spec.

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "chore: finalize schema-based test data generation"
```

---

### Task 6: Path Parameter Resolution (Bonus — if needed for 100% pass rate)

**Files:**
- Modify: `apitest/engine/schema_corrector.py`
- Modify: `apitest/engine/runner.py`

If tests with path parameters (`/api/notes/{noteId}/like`, `/api/notes/{noteId}/comments`) still fail after Task 5, implement proper path parameter resolution.

- [ ] **Step 1: In correct_example, resolve path parameters**

Add to `correct_example` in `schema_corrector.py`:

```python
    # Resolve path parameters in endpoint
    import re
    path_params = re.findall(r'\{(\w+)\}', endpoint.path)
    for param_name in path_params:
        param = next((p for p in endpoint.parameters if p.name == param_name and p.location == "path"), None)
        if param:
            value = generate_fake_value(
                param.name, param.schema_type,
                enum=param.enum, minimum=param.minimum, maximum=param.maximum,
                fmt=param.format,
            )
            example.endpoint = example.endpoint.replace(f"{{{param_name}}}", str(value))
```

- [ ] **Step 2: Run tests and verify**

Run: `python3 -m pytest tests/ -q`
Run full pipeline.
Expected: 15+/17 tests pass.

- [ ] **Step 3: Commit**

```bash
git add apitest/engine/schema_corrector.py
git commit -m "feat: resolve path parameters in corrected examples"
```
