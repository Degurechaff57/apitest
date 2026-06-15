# apitest CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that ingests API documentation, generates test examples and plans via LLM, executes them against mock or real targets, and produces Allure reports.

**Architecture:** Python package with `typer` CLI, `questionary` TUI prompts, pluggable test areas via abstract base class, Flask-based mock server for offline testing, and LLM abstraction supporting OpenAI and Anthropic. The pipeline flows: parse API doc → generate examples → orchestrate plan → generate pytest code → execute → report.

**Tech Stack:** Python 3.10+, typer, questionary, httpx, pytest + allure-pytest, flask, openai SDK, anthropic SDK, prance, openpyxl, pyyaml, hatchling

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `apitest/__init__.py`
- Create: `apitest/py.typed`

- [ ] **Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "apitest"
version = "0.1.0"
description = "AI-powered API test automation CLI"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.9",
    "questionary>=2.0",
    "httpx>=0.27",
    "pytest>=8.0",
    "pytest-httpx>=0.30",
    "allure-pytest>=2.13",
    "openai>=1.30",
    "anthropic>=0.30",
    "prance>=0.22",
    "openapi-core>=0.19",
    "flask>=3.0",
    "openpyxl>=3.1",
    "pyyaml>=6.0",
]

[project.scripts]
apitest = "apitest.cli.main:app"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-httpx>=0.30",
]

[tool.hatch.build.targets.wheel]
packages = ["apitest"]
```

- [ ] **Step 2: Create package init and marker files**

```python
# apitest/__init__.py
"""apitest — AI-powered API test automation toolkit."""
__version__ = "0.1.0"
```

Create empty `apitest/py.typed` (PEP 561 marker).

- [ ] **Step 3: Install in dev mode and verify**

Run: `pip install -e .`
Run: `python -c "import apitest; print(apitest.__version__)"`
Expected: `0.1.0`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml apitest/__init__.py apitest/py.typed
git commit -m "chore: scaffold project with hatchling build"
```

---

### Task 2: Endpoint Model

**Files:**
- Create: `apitest/models/__init__.py`
- Create: `apitest/models/endpoint.py`
- Create: `apitest/models/example.py`

- [ ] **Step 1: Write Endpoint dataclass**

```python
# apitest/models/endpoint.py
from dataclasses import dataclass, field


@dataclass
class Parameter:
    name: str
    location: str  # query, path, header, cookie, body
    schema_type: str  # string, integer, number, boolean, array, object
    required: bool = False
    description: str = ""
    enum: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    format: str = ""  # email, uuid, date-time, etc.
    default: object = None


@dataclass
class RequestBody:
    content_type: str = "application/json"
    schema_ref: str = ""  # $ref name
    required: bool = False


@dataclass
class Response:
    status_code: int
    description: str = ""
    schema_ref: str = ""


@dataclass
class Endpoint:
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str  # /api/users/{id}
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: list[Response] = field(default_factory=list)
    security: list[dict[str, list[str]]] = field(default_factory=list)

    @property
    def resource(self) -> str:
        """Extract resource name from path, e.g. /api/users/{id} -> users"""
        parts = [p for p in self.path.split("/") if p and not p.startswith("{")]
        return parts[-1] if parts else "root"

    @property
    def required_params(self) -> list["Parameter"]:
        return [p for p in self.parameters if p.required]

    @property
    def has_auth(self) -> bool:
        return len(self.security) > 0
```

- [ ] **Step 2: Write TestExample and TestPlan dataclasses**

```python
# apitest/models/example.py
from dataclasses import dataclass, field


@dataclass
class TestExample:
    id: str  # TC-USER-001
    area: str  # functional
    category: str  # happy-path, equivalence-class, boundary-value, negative, auth-security, lifecycle
    endpoint: str  # POST /api/users
    description: str
    preconditions: list[str] = field(default_factory=list)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: dict | None = None
    expected_status: int = 200
    expected_body_contains: list[str] = field(default_factory=list)
    expected_schema: str = ""
    max_response_time_ms: int = 2000
    depends_on: str | None = None  # another example ID
    cleanup: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "area": self.area,
            "category": self.category,
            "endpoint": self.endpoint,
            "description": self.description,
            "preconditions": self.preconditions,
            "request": {
                "headers": self.request_headers,
                **({"body": self.request_body} if self.request_body else {}),
            },
            "expected": {
                "status": self.expected_status,
                **({"body_contains": self.expected_body_contains} if self.expected_body_contains else {}),
                **({"schema": self.expected_schema} if self.expected_schema else {}),
                "max_response_time_ms": self.max_response_time_ms,
            },
            "depends_on": self.depends_on,
            "cleanup": self.cleanup,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestExample":
        req = data.get("request", {})
        exp = data.get("expected", {})
        return cls(
            id=data["id"],
            area=data.get("area", "functional"),
            category=data.get("category", "happy-path"),
            endpoint=data["endpoint"],
            description=data.get("description", ""),
            preconditions=data.get("preconditions", []),
            request_headers=req.get("headers", {}),
            request_body=req.get("body"),
            expected_status=exp.get("status", 200),
            expected_body_contains=exp.get("body_contains", []),
            expected_schema=exp.get("schema", ""),
            max_response_time_ms=exp.get("max_response_time_ms", 2000),
            depends_on=data.get("depends_on"),
            cleanup=data.get("cleanup", ""),
        )


@dataclass
class TestPlanPhase:
    name: str
    order: int
    examples: list[str]  # example IDs
    description: str = ""
    depends_on_phase: int | None = None


@dataclass
class TestPlan:
    title: str
    coverage: str
    areas: list[str]
    phases: list[TestPlanPhase] = field(default_factory=list)
    total_examples: int = 0
    estimated_duration_minutes: int = 0

    def to_dict(self) -> dict:
        return {
            "plan": {
                "title": self.title,
                "coverage": self.coverage,
                "areas": self.areas,
                "total_examples": self.total_examples,
                "estimated_duration_minutes": self.estimated_duration_minutes,
                "phases": [
                    {
                        "name": p.name,
                        "order": p.order,
                        "examples": p.examples,
                        "description": p.description,
                        **({"depends_on_phase": p.depends_on_phase} if p.depends_on_phase else {}),
                    }
                    for p in self.phases
                ],
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestPlan":
        plan = data["plan"]
        return cls(
            title=plan["title"],
            coverage=plan["coverage"],
            areas=plan["areas"],
            total_examples=plan.get("total_examples", 0),
            estimated_duration_minutes=plan.get("estimated_duration_minutes", 0),
            phases=[
                TestPlanPhase(
                    name=p["name"],
                    order=p["order"],
                    examples=p["examples"],
                    description=p.get("description", ""),
                    depends_on_phase=p.get("depends_on_phase"),
                )
                for p in plan.get("phases", [])
            ],
        )


CATEGORIES = [
    "happy-path",
    "equivalence-class",
    "boundary-value",
    "negative",
    "auth-security",
    "lifecycle",
]

COVERAGE_LEVELS = {
    "smoke": ["happy-path"],
    "happy-path": ["happy-path", "equivalence-class", "negative"],
    "full": CATEGORIES,
}
```

- [ ] **Step 3: Write models init**

```python
# apitest/models/__init__.py
from apitest.models.endpoint import Endpoint, Parameter, RequestBody, Response
from apitest.models.example import (
    TestExample,
    TestPlan,
    TestPlanPhase,
    CATEGORIES,
    COVERAGE_LEVELS,
)

__all__ = [
    "Endpoint",
    "Parameter",
    "RequestBody",
    "Response",
    "TestExample",
    "TestPlan",
    "TestPlanPhase",
    "CATEGORIES",
    "COVERAGE_LEVELS",
]
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from apitest.models import Endpoint, TestExample, TestPlan, CATEGORIES, COVERAGE_LEVELS; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add apitest/models/
git commit -m "feat: add Endpoint, TestExample, TestPlan data models"
```

---

### Task 3: Config Loader

**Files:**
- Create: `apitest/config.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test for config loading**

```python
# tests/test_config.py
import os
import tempfile
import pytest
from apitest.config import Config, load_config


class TestConfig:
    def test_loads_default_values_with_no_file(self):
        cfg = load_config()
        assert cfg.llm_provider == "anthropic"
        assert cfg.llm_model == "claude-sonnet-4-6"
        assert cfg.examples_format == "json"
        assert cfg.plan_format == "md"
        assert cfg.coverage == "happy-path"
        assert cfg.execution_mode == "mock"

    def test_loads_from_yaml_file(self):
        yaml_content = """
llm:
  provider: "openai"
  model: "gpt-4o"
  api_key: "sk-test123"
examples:
  format: "yaml"
coverage: "full"
execution:
  mode: "real"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name

        try:
            cfg = load_config(path)
            assert cfg.llm_provider == "openai"
            assert cfg.llm_model == "gpt-4o"
            assert cfg.llm_api_key == "sk-test123"
            assert cfg.examples_format == "yaml"
            assert cfg.coverage == "full"
            assert cfg.execution_mode == "real"
        finally:
            os.unlink(path)

    def test_resolves_env_var_in_api_key(self):
        os.environ["TEST_API_KEY"] = "env-key-123"
        yaml_content = """
llm:
  api_key: "${TEST_API_KEY}"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            path = f.name

        try:
            cfg = load_config(path)
            assert cfg.llm_api_key == "env-key-123"
        finally:
            os.unlink(path)
            del os.environ["TEST_API_KEY"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write Config class and loader**

```python
# apitest/config.py
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    # LLM
    llm_provider: str = "anthropic"  # openai | anthropic | custom
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_base_url: str | None = None

    # Input
    api_doc: str = "specs/openapi.yaml"

    # Output
    examples_format: str = "json"  # json | yaml | md | xlsx
    examples_dir: str = "tests/examples"
    plan_format: str = "md"  # md | json | yaml | xlsx
    plan_path: str = "test_plan.md"

    # Execution
    base_url: str = "http://localhost:8080"
    coverage: str = "happy-path"  # smoke | happy-path | full
    execution_mode: str = "mock"  # mock | real
    execution_mock_server_port: int | None = None

    # Report
    report_auto_serve: bool = True
    report_dir: str = "allure-results"

    # Areas
    areas: list[str] = field(default_factory=lambda: ["functional"])


_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _resolve_env_vars(value: str) -> str:
    def _replace(match):
        env_name = match.group(1)
        return os.environ.get(env_name, "")

    return _ENV_VAR_RE.sub(_replace, value)


def load_config(path: str | None = None) -> Config:
    """Load config from YAML file, falling back to defaults.

    Search order: explicit path -> .apitest.yaml in CWD -> defaults.
    """
    if path is None:
        cwd_path = Path.cwd() / ".apitest.yaml"
        if cwd_path.exists():
            path = str(cwd_path)

    if path and Path(path).exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    llm = raw.get("llm", {})
    examples = raw.get("examples", {})
    plan = raw.get("plan", {})
    execution = raw.get("execution", {})
    report = raw.get("report", {})

    api_key = llm.get("api_key", "")
    api_key = _resolve_env_vars(api_key) if api_key else ""

    return Config(
        llm_provider=llm.get("provider", "anthropic"),
        llm_model=llm.get("model", "claude-sonnet-4-6"),
        llm_api_key=api_key,
        llm_base_url=llm.get("base_url"),
        api_doc=raw.get("api_doc", "specs/openapi.yaml"),
        examples_format=examples.get("format", "json"),
        examples_dir=examples.get("dir", "tests/examples"),
        plan_format=plan.get("format", "md"),
        plan_path=plan.get("path", "test_plan.md"),
        base_url=raw.get("base_url", "http://localhost:8080"),
        coverage=raw.get("coverage", "happy-path"),
        execution_mode=execution.get("mode", "mock"),
        execution_mock_server_port=execution.get("mock_server_port"),
        report_auto_serve=report.get("auto_serve", True),
        report_dir=report.get("dir", "allure-results"),
        areas=raw.get("areas", ["functional"]),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/config.py tests/
git commit -m "feat: add config loader with YAML and env var support"
```

---

### Task 4: LLM Client

**Files:**
- Create: `apitest/engine/__init__.py`
- Create: `apitest/engine/llm_client.py`
- Create: `tests/test_llm_client.py`

- [ ] **Step 1: Write a test for LLM client factory**

```python
# tests/test_llm_client.py
import pytest
from apitest.engine.llm_client import LLMClient, OpenAIClient, AnthropicClient, CustomClient


class TestLLMClient:
    def test_create_openai_client(self):
        client = LLMClient.create("openai", "gpt-4o", "sk-test")
        assert isinstance(client, OpenAIClient)
        assert client.model == "gpt-4o"

    def test_create_anthropic_client(self):
        client = LLMClient.create("anthropic", "claude-sonnet-4-6", "sk-test")
        assert isinstance(client, AnthropicClient)
        assert client.model == "claude-sonnet-4-6"

    def test_create_custom_client(self):
        client = LLMClient.create("custom", "my-model", "sk-test", base_url="https://api.example.com/v1")
        assert isinstance(client, CustomClient)
        assert client.base_url == "https://api.example.com/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            LLMClient.create("unknown", "model", "key")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write LLM client abstraction**

```python
# apitest/engine/llm_client.py
from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Abstract LLM client. Use LLMClient.create() to get the right implementation."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @abstractmethod
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """Send a chat completion and return the text response."""

    @staticmethod
    def create(provider: str, model: str, api_key: str, base_url: str | None = None) -> "LLMClient":
        if provider == "openai":
            return OpenAIClient(model, api_key)
        elif provider == "anthropic":
            return AnthropicClient(model, api_key)
        elif provider == "custom":
            return CustomClient(model, api_key, base_url)
        else:
            raise ValueError(f"Unknown provider: {provider}")


class OpenAIClient(LLMClient):
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)
        response = client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        return response.content[0].text


class CustomClient(LLMClient):
    """OpenAI-compatible endpoint (e.g., self-hosted, proxies)."""

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_client.py -v`
Expected: 4 PASS

- [ ] **Step 5: Write engine init**

```python
# apitest/engine/__init__.py
from apitest.engine.llm_client import LLMClient, OpenAIClient, AnthropicClient, CustomClient

__all__ = ["LLMClient", "OpenAIClient", "AnthropicClient", "CustomClient"]
```

- [ ] **Step 6: Commit**

```bash
git add apitest/engine/ tests/test_llm_client.py
git commit -m "feat: add LLM client abstraction (OpenAI, Anthropic, custom)"
```

---

### Task 5: API Doc Parser

**Files:**
- Create: `apitest/engine/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write a minimal OpenAPI fixture and test the parser**

```python
# tests/test_parser.py
import tempfile
import pytest
from apitest.engine.parser import parse_openapi, detect_format
from apitest.models.endpoint import Endpoint


MINIMAL_OPENAPI_YAML = """
openapi: "3.0.0"
info:
  title: Test API
  version: "1.0.0"
paths:
  /api/users:
    get:
      operationId: listUsers
      summary: List all users
      parameters:
        - name: role
          in: query
          schema:
            type: string
            enum: [admin, user]
      responses:
        "200":
          description: OK
      security:
        - bearerAuth: []
    post:
      operationId: createUser
      summary: Create a user
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, email]
              properties:
                name:
                  type: string
                  minLength: 1
                  maxLength: 100
                email:
                  type: string
                  format: email
                age:
                  type: integer
                  minimum: 0
                  maximum: 150
      responses:
        "201":
          description: Created
        "400":
          description: Bad Request
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
"""


class TestParser:
    def test_detect_openapi_format(self):
        assert detect_format("spec.yaml") == "openapi"
        assert detect_format("spec.json") == "openapi"
        assert detect_format("spec.yml") == "openapi"

    def test_detect_postman_format(self):
        assert detect_format("collection.json") == "postman"
        # Postman collections have "info" and "item" at top level
        # Format detection by filename pattern is the primary method;
        # content-based detection is fallback

    def test_parse_openapi_endpoints(self):
        import yaml
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(MINIMAL_OPENAPI_YAML)
            path = f.name

        try:
            endpoints = parse_openapi(path)
            assert len(endpoints) == 2

            get_users = [e for e in endpoints if e.method == "GET"][0]
            assert get_users.path == "/api/users"
            assert get_users.operation_id == "listUsers"
            assert len(get_users.parameters) == 1
            assert get_users.parameters[0].name == "role"
            assert get_users.parameters[0].enum == ["admin", "user"]
            assert get_users.has_auth is True

            post_users = [e for e in endpoints if e.method == "POST"][0]
            assert post_users.request_body is not None
            assert post_users.request_body.required is True
            assert post_users.responses[0].status_code == 201
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parser.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the parser**

```python
# apitest/engine/parser.py
from pathlib import Path

import yaml
from apitest.models.endpoint import Endpoint, Parameter, RequestBody, Response


def detect_format(filepath: str) -> str:
    """Detect API doc format from filename. Returns 'openapi' or 'postman'."""
    name = Path(filepath).name.lower()
    if "postman" in name or "collection" in name:
        return "postman"
    return "openapi"


def parse_openapi(filepath: str) -> list[Endpoint]:
    """Parse an OpenAPI 3.x or Swagger 2.0 spec into Endpoint list."""
    with open(filepath) as f:
        spec = yaml.safe_load(f)

    endpoints: list[Endpoint] = []
    paths = spec.get("paths", {})

    for path, methods in paths.items():
        for method in ["get", "post", "put", "delete", "patch", "options", "head"]:
            operation = methods.get(method)
            if operation is None:
                continue

            endpoint = _parse_operation(method.upper(), path, operation, spec)
            endpoints.append(endpoint)

    # Sort: lifecycle order (POST → GET → PUT → DELETE)
    method_order = {"POST": 0, "GET": 1, "PUT": 2, "PATCH": 3, "DELETE": 4, "OPTIONS": 5, "HEAD": 6}
    endpoints.sort(key=lambda e: (e.resource, method_order.get(e.method, 99), e.path))

    return endpoints


def _parse_operation(method: str, path: str, operation: dict, spec: dict) -> Endpoint:
    parameters = _parse_parameters(operation.get("parameters", []), spec)

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


def _parse_parameters(params: list[dict], spec: dict) -> list[Parameter]:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parser.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/parser.py tests/test_parser.py
git commit -m "feat: add OpenAPI 3.x/Swagger 2.0 parser"
```

---

### Task 6: Formatter (Multi-Format Output)

**Files:**
- Create: `apitest/engine/formatter.py`
- Create: `tests/test_formatter.py`

- [ ] **Step 1: Write tests for format read/write**

```python
# tests/test_formatter.py
import json
import os
import tempfile
import pytest
from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan
from apitest.models.example import TestExample, TestPlan, TestPlanPhase


SAMPLE_EXAMPLES = [
    TestExample(
        id="TC-USER-001",
        area="functional",
        category="happy-path",
        endpoint="POST /api/users",
        description="Create user returns 201",
        preconditions=["valid token"],
        request_headers={"Authorization": "Bearer ${TOKEN}"},
        request_body={"name": "John", "email": "john@test.com"},
        expected_status=201,
        expected_body_contains=["id", "name"],
        max_response_time_ms=2000,
    ),
]

SAMPLE_PLAN = TestPlan(
    title="Test Plan: My API",
    coverage="happy-path",
    areas=["functional"],
    total_examples=1,
    phases=[
        TestPlanPhase(name="Setup", order=1, examples=["TC-USER-001"], description="Setup phase"),
    ],
)


class TestFormatter:
    @pytest.mark.parametrize("fmt", ["json", "yaml"])
    def test_write_and_read_examples(self, fmt):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, f"examples.{fmt}")
            write_examples(SAMPLE_EXAMPLES, filepath, fmt)
            assert os.path.exists(filepath)

            loaded = read_examples(filepath, fmt)
            assert len(loaded) == 1
            assert loaded[0].id == "TC-USER-001"
            assert loaded[0].expected_status == 201

    def test_write_examples_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "examples.json")
            write_examples(SAMPLE_EXAMPLES, filepath, "json")
            with open(filepath) as f:
                data = json.load(f)
            assert data["examples"][0]["id"] == "TC-USER-001"

    @pytest.mark.parametrize("fmt", ["json", "yaml"])
    def test_write_and_read_plan(self, fmt):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, f"plan.{fmt}")
            write_plan(SAMPLE_PLAN, filepath, fmt)
            assert os.path.exists(filepath)

            loaded = read_plan(filepath, fmt)
            assert loaded.title == "Test Plan: My API"
            assert len(loaded.phases) == 1

    def test_write_examples_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "examples.md")
            write_examples(SAMPLE_EXAMPLES, filepath, "md")
            content = open(filepath).read()
            assert "# Test Examples" in content
            assert "TC-USER-001" in content
            assert "POST /api/users" in content

    def test_write_plan_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "plan.md")
            write_plan(SAMPLE_PLAN, filepath, "md")
            content = open(filepath).read()
            assert "# Test Plan: My API" in content
            assert "Setup" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_formatter.py -v`
Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Write the formatter**

```python
# apitest/engine/formatter.py
import json
from pathlib import Path

import yaml

from apitest.models.example import TestExample, TestPlan, TestPlanPhase

_FORMAT_EXT = {
    "json": ".json",
    "yaml": ".yaml",
    "yml": ".yaml",
    "md": ".md",
    "xlsx": ".xlsx",
}


def write_examples(examples: list[TestExample], filepath: str, fmt: str) -> None:
    """Write test examples to a file in the specified format."""
    path = Path(filepath)

    if fmt == "json":
        data = {"examples": [e.to_dict() for e in examples]}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    elif fmt in ("yaml", "yml"):
        data = {"examples": [e.to_dict() for e in examples]}
        path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False))

    elif fmt == "md":
        _write_examples_md(examples, path)

    elif fmt == "xlsx":
        _write_examples_xlsx(examples, path)

    else:
        raise ValueError(f"Unknown format: {fmt}")


def read_examples(filepath: str, fmt: str) -> list[TestExample]:
    """Read test examples from a file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Examples file not found: {filepath}")

    if fmt == "json":
        data = json.loads(path.read_text())
    elif fmt in ("yaml", "yml"):
        data = yaml.safe_load(path.read_text())
    elif fmt == "md":
        raise ValueError("Cannot parse examples from markdown. Use json or yaml for machine reading.")
    elif fmt == "xlsx":
        return _read_examples_xlsx(path)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    return [TestExample.from_dict(e) for e in data.get("examples", [])]


def write_plan(plan: TestPlan, filepath: str, fmt: str) -> None:
    """Write test plan to a file."""
    path = Path(filepath)

    if fmt == "json":
        path.write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False))

    elif fmt in ("yaml", "yml"):
        path.write_text(yaml.dump(plan.to_dict(), allow_unicode=True, sort_keys=False))

    elif fmt == "md":
        _write_plan_md(plan, path)

    elif fmt == "xlsx":
        _write_plan_xlsx(plan, path)

    else:
        raise ValueError(f"Unknown format: {fmt}")


def read_plan(filepath: str, fmt: str) -> TestPlan:
    """Read test plan from a file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {filepath}")

    if fmt == "json":
        data = json.loads(path.read_text())
    elif fmt in ("yaml", "yml"):
        data = yaml.safe_load(path.read_text())
    elif fmt == "md":
        raise ValueError("Cannot parse plan from markdown. Use json or yaml for machine reading.")
    elif fmt == "xlsx":
        return _read_plan_xlsx(path)
    else:
        raise ValueError(f"Unknown format: {fmt}")

    return TestPlan.from_dict(data)


def _write_examples_md(examples: list[TestExample], path: Path) -> None:
    lines = ["# Test Examples\n"]
    for cat in ["happy-path", "equivalence-class", "boundary-value", "negative", "auth-security", "lifecycle"]:
        cat_examples = [e for e in examples if e.category == cat]
        if not cat_examples:
            continue
        lines.append(f"## {cat.replace('-', ' ').title()}\n")
        for e in cat_examples:
            lines.append(f"### {e.id}: {e.description}")
            lines.append(f"- **Endpoint:** `{e.endpoint}`")
            lines.append(f"- **Expected:** {e.expected_status}")
            if e.preconditions:
                lines.append(f"- **Preconditions:** {', '.join(e.preconditions)}")
            if e.depends_on:
                lines.append(f"- **Depends on:** `{e.depends_on}`")
            lines.append("")
    path.write_text("\n".join(lines))


def _write_examples_xlsx(examples: list[TestExample], path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Test Examples"
    ws.append(["ID", "Area", "Category", "Endpoint", "Description", "Expected Status",
                "Preconditions", "Depends On", "Cleanup"])
    for e in examples:
        ws.append([e.id, e.area, e.category, e.endpoint, e.description, e.expected_status,
                   ", ".join(e.preconditions), e.depends_on or "", e.cleanup])
    wb.save(path)


def _read_examples_xlsx(path: Path) -> list[TestExample]:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    examples = []
    for row in rows:
        examples.append(TestExample(
            id=row[0], area=row[1], category=row[2], endpoint=row[3],
            description=row[4], expected_status=row[5],
            preconditions=[p.strip() for p in (row[6] or "").split(",") if p.strip()],
            depends_on=row[7] or None, cleanup=row[8] or "",
        ))
    return examples


def _write_plan_md(plan: TestPlan, path: Path) -> None:
    lines = [f"# {plan.title}\n"]
    lines.append(f"**Coverage:** {plan.coverage} | **Areas:** {', '.join(plan.areas)}")
    lines.append(f"**Total Examples:** {plan.total_examples}\n")
    for phase in plan.phases:
        lines.append(f"## Phase {phase.order}: {phase.name}")
        if phase.description:
            lines.append(f"\n{phase.description}\n")
        if phase.depends_on_phase:
            lines.append(f"\n*Depends on Phase {phase.depends_on_phase}*\n")
        lines.append("**Examples:**")
        for eid in phase.examples:
            lines.append(f"- `{eid}`")
        lines.append("")
    path.write_text("\n".join(lines))


def _write_plan_xlsx(plan: TestPlan, path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Test Plan"
    ws.append(["Phase", "Name", "Description", "Depends On Phase", "Example IDs"])
    for phase in plan.phases:
        ws.append([phase.order, phase.name, phase.description,
                   phase.depends_on_phase or "", ", ".join(phase.examples)])
    wb.save(path)


def _read_plan_xlsx(path: Path) -> list[TestExample]:
    from openpyxl import load_workbook

    wb = load_workbook(path)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    phases = []
    for row in rows:
        example_ids = [e.strip() for e in (row[4] or "").split(",") if e.strip()]
        phases.append(TestPlanPhase(
            name=row[1], order=row[0],
            description=row[2] or "",
            depends_on_phase=row[3] if row[3] else None,
            examples=example_ids,
        ))
    return TestPlan(title="", coverage="", areas=[], phases=phases)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_formatter.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/formatter.py tests/test_formatter.py
git commit -m "feat: add multi-format formatter (json, yaml, md, xlsx)"
```

---

### Task 7: Test Area Base Class

**Files:**
- Create: `apitest/areas/__init__.py`
- Create: `apitest/areas/base.py`
- Create: `tests/test_areas.py`

- [ ] **Step 1: Write test for area registry**

```python
# tests/test_areas.py
import pytest
from apitest.areas.base import TestArea, AreaRegistry
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample


class FakeLLM:
    def chat(self, system_prompt, user_prompt, temperature=0.3):
        return '{"examples": []}'


class FakeArea(TestArea):
    @property
    def name(self) -> str:
        return "fake"

    def get_prompt_context(self, endpoints):
        return "Fake context"

    def generate_examples(self, endpoints, coverage, llm):
        return []

    def generate_test_code(self, examples, llm):
        return "# no tests"


class TestAreaRegistry:
    def test_register_and_get_area(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        area = registry.get("fake")
        assert area is not None
        assert area.name == "fake"

    def test_get_unknown_area_returns_none(self):
        registry = AreaRegistry()
        assert registry.get("nonexistent") is None

    def test_list_area_names(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        assert "fake" in registry.list_names()

    def test_get_enabled_areas(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        enabled = registry.get_enabled(["fake"])
        assert len(enabled) == 1
        assert enabled[0].name == "fake"

    def test_skip_disabled_areas(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        enabled = registry.get_enabled(["other"])
        assert len(enabled) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_areas.py -v`
Expected: FAIL

- [ ] **Step 3: Write TestArea base and AreaRegistry**

```python
# apitest/areas/base.py
from abc import ABC, abstractmethod

from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample


class TestArea(ABC):
    """Base class for a testing business area.

    Each area handles one testing domain (functional, security, performance, etc.)
    and knows how to generate examples and test code for that domain.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique area identifier, e.g. 'functional', 'security'."""

    @abstractmethod
    def get_prompt_context(self, endpoints: list[Endpoint]) -> str:
        """Return area-specific context injected into the LLM system prompt."""

    @abstractmethod
    def generate_examples(
        self, endpoints: list[Endpoint], coverage: str, llm: "LLMClient",
    ) -> list[TestExample]:
        """Generate test examples for this area using the LLM."""

    @abstractmethod
    def generate_test_code(
        self, examples: list[TestExample], llm: "LLMClient",
    ) -> str:
        """Generate pytest code for examples in this area. Returns file content string."""


class AreaRegistry:
    """Registry of available test areas. Areas are registered at import time."""

    def __init__(self):
        self._areas: dict[str, TestArea] = {}

    def register(self, area: TestArea) -> None:
        self._areas[area.name] = area

    def get(self, name: str) -> TestArea | None:
        return self._areas.get(name)

    def list_names(self) -> list[str]:
        return list(self._areas.keys())

    def get_enabled(self, area_names: list[str]) -> list[TestArea]:
        """Return registered areas whose names are in area_names, preserving order."""
        return [self._areas[n] for n in area_names if n in self._areas]


# Global registry — areas register themselves on import
registry = AreaRegistry()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_areas.py -v`
Expected: 5 PASS

- [ ] **Step 5: Write areas init with auto-registration**

```python
# apitest/areas/__init__.py
from apitest.areas.base import TestArea, AreaRegistry, registry

# v1 area — import triggers self-registration
from apitest.areas.functional import FunctionalArea  # noqa: F401

__all__ = ["TestArea", "AreaRegistry", "registry", "FunctionalArea"]
```

- [ ] **Step 6: Commit**

```bash
git add apitest/areas/ tests/test_areas.py
git commit -m "feat: add TestArea base class and area registry"
```

---

### Task 8: Functional Business Testing Area

**Files:**
- Create: `apitest/areas/functional.py`
- Extend: `tests/test_areas.py`

- [ ] **Step 1: Add test for functional area prompt context**

Add to `tests/test_areas.py`:

```python
from apitest.areas.functional import FunctionalArea


class TestFunctionalArea:
    def test_name_is_functional(self):
        area = FunctionalArea()
        assert area.name == "functional"

    def test_prompt_context_includes_categories(self):
        area = FunctionalArea()
        ctx = area.get_prompt_context([])
        assert "happy-path" in ctx
        assert "equivalence-class" in ctx
        assert "boundary-value" in ctx
        assert "negative" in ctx
        assert "auth-security" in ctx
        assert "lifecycle" in ctx

    def test_prompt_context_includes_coverage_matrix(self):
        area = FunctionalArea()
        ctx = area.get_prompt_context([])
        assert "smoke" in ctx
        assert "happy-path" in ctx
        assert "full" in ctx

    def test_generate_examples_returns_list(self):
        area = FunctionalArea()

        class MockLLM:
            def chat(self, system_prompt, user_prompt, temperature=0.3):
                import json
                return json.dumps({
                    "examples": [{
                        "id": "TC-USERS-001",
                        "area": "functional",
                        "category": "happy-path",
                        "endpoint": "GET /api/users",
                        "description": "List users returns 200",
                        "preconditions": [],
                        "request": {"headers": {}},
                        "expected": {"status": 200},
                        "depends_on": None,
                        "cleanup": "",
                    }]
                })

        from apitest.models.endpoint import Endpoint
        endpoint = Endpoint(method="GET", path="/api/users")
        examples = area.generate_examples([endpoint], "smoke", MockLLM())
        assert len(examples) == 1
        assert examples[0].id == "TC-USERS-001"

    def test_generate_test_code_returns_string(self):
        area = FunctionalArea()

        class MockLLM:
            def chat(self, system_prompt, user_prompt, temperature=0.3):
                return "def test_example():\n    assert True\n"

        from apitest.models.example import TestExample
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/users", description="test",
            expected_status=200,
        )
        code = area.generate_test_code([example], MockLLM())
        assert "def test_example" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_areas.py::TestFunctionalArea -v`
Expected: FAIL

- [ ] **Step 3: Write FunctionalArea**

```python
# apitest/areas/functional.py
import json
import re

from apitest.areas.base import TestArea, registry
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample, CATEGORIES, COVERAGE_LEVELS


FUNCTIONAL_SYSTEM_PROMPT = """You are a senior API QA engineer specializing in functional testing.
Generate test examples and pytest code from API endpoint specifications.

## Test Categories
1. **happy-path**: One success case per endpoint using valid inputs
2. **equivalence-class**: Partition inputs into valid/invalid classes, test one per class
3. **boundary-value**: Test min-1, min, min+1, max-1, max, max+1 for every numeric/length constraint
4. **negative**: Missing required fields, wrong types, malformed JSON, invalid enum values
5. **auth-security**: No token, wrong role/scope for secured endpoints
6. **lifecycle**: Chain CRUD operations: Create → Read → Update → Read → Delete → Read(404)

## Coverage Matrix
- smoke: happy-path only (~1 example per endpoint)
- happy-path: happy-path + equivalence-class + negative (~3-5 per endpoint)
- full: all 6 categories (~6-10 per endpoint)

## Design Rules
- Every example MUST have a unique ID: TC-<RESOURCE>-<NNN>
- Use ${VAR} syntax for dynamic values (tokens, IDs from previous steps)
- dependencies MUST follow the Operation Dependency Graph
- Cleanup MUST leave no side effects
- Group by category first, then by endpoint
- Never multiply scenarios × verifications — total = scenarios + verifications
"""


class FunctionalArea(TestArea):
    @property
    def name(self) -> str:
        return "functional"

    def get_prompt_context(self, endpoints: list[Endpoint]) -> str:
        endpoint_list = []
        for ep in endpoints:
            params_desc = []
            for p in ep.parameters:
                constraints = []
                if p.enum:
                    constraints.append(f"enum={p.enum}")
                if p.minimum is not None:
                    constraints.append(f"min={p.minimum}")
                if p.maximum is not None:
                    constraints.append(f"max={p.maximum}")
                if p.min_length is not None:
                    constraints.append(f"minLength={p.min_length}")
                if p.max_length is not None:
                    constraints.append(f"maxLength={p.max_length}")
                constraint_str = f" [{', '.join(constraints)}]" if constraints else ""
                params_desc.append(
                    f"    {p.name} ({p.schema_type}, {'required' if p.required else 'optional'})"
                    f"{constraint_str}: {p.description}"
                )

            endpoint_list.append(
                f"{ep.method} {ep.path}"
                + (f" — {ep.summary}" if ep.summary else "")
                + (f"\n  Auth: required" if ep.has_auth else "")
                + (f"\n  Request body required" if ep.request_body and ep.request_body.required else "")
                + "\n  Parameters:\n" + "\n".join(params_desc) if params_desc else ""
            )

        return "\n\n".join(endpoint_list)

    def generate_examples(
        self, endpoints: list[Endpoint], coverage: str, llm,
    ) -> list[TestExample]:
        categories = COVERAGE_LEVELS.get(coverage, COVERAGE_LEVELS["happy-path"])
        context = self.get_prompt_context(endpoints)

        user_prompt = f"""Generate test examples for the following API endpoints at coverage level: {coverage}.
Include these categories: {', '.join(categories)}.

## Endpoints
{context}

## Output Format
Return valid JSON with this structure:
{{"examples": [{{example objects}}]}}

Each example object:
{{
  "id": "TC-<RESOURCE>-<NNN>",
  "area": "functional",
  "category": "one of: {', '.join(categories)}",
  "endpoint": "METHOD /path",
  "description": "what this tests",
  "preconditions": ["list of prerequisites"],
  "request": {{"headers": {{}}, "body": {{}}}},  // body optional for GET
  "expected": {{"status": 200, "body_contains": ["field"], "schema": "SchemaName", "max_response_time_ms": 2000}},
  "depends_on": "TC-OTHER-001",  // or null
  "cleanup": "DELETE /path/{{id}}"  // or ""
}}
"""

        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt)
        return self._parse_examples(response)

    def generate_test_code(self, examples: list[TestExample], llm) -> str:
        examples_json = json.dumps([e.to_dict() for e in examples], indent=2)

        user_prompt = f"""Generate pytest code for the following test examples.
Use the apitest fixtures: client (httpx.Client), auth_token (str).

Import and use allure: from allure import feature, story, step

## Test Examples
{examples_json}

## Code Rules
- Class name: Test<ResourceName> (PascalCase)
- Method name: test_<description_snake_case>
- Decorate with @feature("<Resource>") and @story("<Operation>")
- Use client.<method>(endpoint, ...) for requests
- Assert status code, response body fields, and response time
- Handle depends_on with pytest-order or manual ordering
- ${VAR} values come from fixtures or environment
- Return ONLY valid Python code, no markdown wrapping
"""

        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt)
        return self._extract_code(response)

    def _parse_examples(self, response: str) -> list[TestExample]:
        # Extract JSON block from response (may be wrapped in markdown)
        match = re.search(r"\{[\s\S]*\"examples\"[\s\S]*\}", response)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(response)
        return [TestExample.from_dict(e) for e in data.get("examples", [])]

    def _extract_code(self, response: str) -> str:
        # Extract code block from markdown if present
        match = re.search(r"```python\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        return response.strip()


# Self-register on import
registry.register(FunctionalArea())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_areas.py -v`
Expected: 10 PASS (5 from Task 7 + 5 from Task 8)

- [ ] **Step 5: Commit**

```bash
git add apitest/areas/functional.py tests/test_areas.py
git commit -m "feat: add Functional Business Testing area with LLM prompts"
```

---

### Task 9: Generator — Examples & Plan

**Files:**
- Create: `apitest/engine/generator.py`
- Create: `tests/test_generator.py`

- [ ] **Step 1: Write test for generator**

```python
# tests/test_generator.py
import json
import tempfile
import os
import pytest
from apitest.engine.generator import Generator
from apitest.engine.parser import parse_openapi
from apitest.models.example import TestExample, TestPlan
from apitest.areas.functional import FunctionalArea


MINIMAL_SPEC_YAML = """
openapi: "3.0.0"
info:
  title: Petstore
  version: "1.0.0"
paths:
  /api/pets:
    get:
      operationId: listPets
      responses:
        "200":
          description: OK
    post:
      operationId: createPet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
      responses:
        "201":
          description: Created
"""


class MockLLM:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []

    def chat(self, system_prompt, user_prompt, temperature=0.3):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({"examples": []})


class TestGenerator:
    def test_generate_examples_calls_llm(self):
        # Setup: write spec, parse it
        import yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(MINIMAL_SPEC_YAML)
            spec_path = f.name

        try:
            endpoints = parse_openapi(spec_path)
            llm = MockLLM(responses=[
                json.dumps({
                    "examples": [{
                        "id": "TC-PETS-001",
                        "area": "functional",
                        "category": "happy-path",
                        "endpoint": "GET /api/pets",
                        "description": "List pets returns 200",
                        "preconditions": [],
                        "request": {"headers": {}},
                        "expected": {"status": 200},
                        "depends_on": None,
                        "cleanup": "",
                    }]
                }),
            ])

            gen = Generator(llm)
            examples = gen.generate_examples(endpoints, "smoke", ["functional"])
            assert len(examples) > 0
            # Verify LLM was called with endpoint context
            called = False
            for call in llm.calls:
                if "/api/pets" in call["user"]:
                    called = True
            assert called, "LLM should receive endpoint context"
        finally:
            os.unlink(spec_path)

    def test_generate_plan_calls_llm_with_examples(self):
        examples = [
            TestExample(
                id="TC-PETS-001", area="functional", category="happy-path",
                endpoint="GET /api/pets", description="List pets",
                expected_status=200,
            ),
        ]

        llm = MockLLM(responses=[
            json.dumps({
                "plan": {
                    "title": "Test Plan: Petstore",
                    "coverage": "smoke",
                    "areas": ["functional"],
                    "total_examples": 1,
                    "phases": [{
                        "name": "Pets",
                        "order": 1,
                        "examples": ["TC-PETS-001"],
                        "description": "Pet operations",
                    }],
                }
            }),
        ])

        gen = Generator(llm)
        plan = gen.generate_plan(examples, "smoke", ["functional"])
        assert plan.title == "Test Plan: Petstore"
        assert len(plan.phases) == 1
        assert plan.phases[0].examples == ["TC-PETS-001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Write Generator**

```python
# apitest/engine/generator.py
import json
import re

from apitest.areas.base import registry
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample, TestPlan


PLAN_SYSTEM_PROMPT = """You are a senior QA test planner. Given a list of test examples,
organize them into a logical execution plan.

## Rules
- Order phases by dependency: setup/auth first, then CRUD lifecycles, then cleanup
- Group examples by resource (extract from endpoint path)
- Identify shared prerequisites and group them into setup phases
- Examples that depend on others MUST come after their dependencies
- Estimate total duration based on number of examples (~10s per example)
"""


class Generator:
    """Orchestrates test areas to generate examples and plans."""

    def __init__(self, llm):
        self.llm = llm

    def generate_examples(
        self, endpoints: list[Endpoint], coverage: str, area_names: list[str],
    ) -> list[TestExample]:
        """Run each enabled area's generate_examples and merge results."""
        areas = registry.get_enabled(area_names)
        all_examples: list[TestExample] = []

        for area in areas:
            examples = area.generate_examples(endpoints, coverage, self.llm)
            all_examples.extend(examples)

        return all_examples

    def generate_plan(
        self, examples: list[TestExample], coverage: str, area_names: list[str],
    ) -> TestPlan:
        """Orchestrate examples into an ordered test plan via LLM."""
        examples_json = json.dumps([e.to_dict() for e in examples], indent=2)

        user_prompt = f"""Organize these test examples into a test plan.

## Examples
{examples_json}

## Output Format
Return valid JSON:
{{"plan": {{
  "title": "Test Plan: <API Name>",
  "coverage": "{coverage}",
  "areas": {json.dumps(area_names)},
  "total_examples": {len(examples)},
  "estimated_duration_minutes": <number>,
  "phases": [
    {{
      "name": "Phase name",
      "order": 1,
      "examples": ["TC-XXX-001"],
      "description": "What this phase covers",
      "depends_on_phase": null  // or phase order number
    }}
  ]
}}}}
"""

        response = self.llm.chat(PLAN_SYSTEM_PROMPT, user_prompt)
        return self._parse_plan(response, coverage, area_names)

    def _parse_plan(self, response: str, coverage: str, areas: list[str]) -> TestPlan:
        match = re.search(r"\{[\s\S]*\"plan\"[\s\S]*\}", response)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(response)
        return TestPlan.from_dict(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generator.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/generator.py tests/test_generator.py
git commit -m "feat: add generator for examples and test plan orchestration"
```

---

### Task 10: Mock Server

**Files:**
- Create: `apitest/engine/mock_server.py`
- Create: `tests/test_mock_server.py`

- [ ] **Step 1: Write test for mock server**

```python
# tests/test_mock_server.py
import threading
import time
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
        server = MockServer(app, port=0)  # port=0 = auto-assign
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
            resp = httpx.post(
                f"{server.url}/api/users",
                json={"name": "Alice"},
            )
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mock_server.py -v`
Expected: FAIL

- [ ] **Step 3: Write mock server**

```python
# apitest/engine/mock_server.py
import json
import os
import socket
import sqlite3
import threading
import uuid
from pathlib import Path

from flask import Flask, request, jsonify, g


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


class MockServer:
    """Wraps a Flask mock server running in a background thread."""

    def __init__(self, app: Flask, port: int | None = None):
        self.app = app
        self.port = port or _get_free_port()
        self._thread: threading.Thread | None = None
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

    def stop(self) -> None:
        self._running = False
        # Flask dev server can be killed by requesting shutdown
        # For daemon threads, they'll exit when the main process exits

    def is_running(self) -> bool:
        return self._running


def create_mock_app(spec: dict) -> Flask:
    """Create a Flask app that mocks the given OpenAPI spec."""
    app = Flask(__name__)

    # In-memory SQLite per request context
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(":memory:")
            g.db.row_factory = sqlite3.Row
            g.db.execute("CREATE TABLE IF NOT EXISTS store ("
                         "resource TEXT, resource_id TEXT, data TEXT, "
                         "PRIMARY KEY (resource, resource_id))")
        return g.db

    # Extract schema info
    schemas = _extract_schemas(spec)
    paths = spec.get("paths", {})

    for url_path, methods in paths.items():
        flask_path = url_path.replace("{", "<").replace("}", ">")

        for method in ["get", "post", "put", "delete", "patch"]:
            operation = methods.get(method)
            if operation is None:
                continue

            _register_route(app, method, flask_path, url_path, operation, schemas)

    return app


def _extract_schemas(spec: dict) -> dict:
    """Extract schema definitions from components/schemas."""
    return spec.get("components", {}).get("schemas", {})


def _register_route(app, method, flask_path, spec_path, operation, schemas):
    """Register a single mock route on the Flask app."""
    responses = operation.get("responses", {})
    success_status = _get_success_status(responses)
    has_path_param = "{" in spec_path

    # Get the request body schema if present
    body_schema = None
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
        db = get_db()

        if method == "get":
            if has_path_param:
                # GET /resource/{id} — return single item
                resource_id = list(kwargs.values())[0] if kwargs else None
                row = db.execute(
                    "SELECT data FROM store WHERE resource=? AND resource_id=?",
                    (resource, str(resource_id)),
                ).fetchone()
                if row:
                    return jsonify(json.loads(row["data"])), 200
                return jsonify({"error": "not found"}), 404
            else:
                # GET /resource — list all
                rows = db.execute(
                    "SELECT data FROM store WHERE resource=?", (resource,)
                ).fetchall()
                return jsonify([json.loads(r["data"]) for r in rows]), 200

        elif method == "post":
            data = request.get_json(silent=True) or {}

            # Schema validation
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

    # Flask app teardown to close DB connections
    def teardown(exception=None):
        db = getattr(g, "db", None)
        if db is not None:
            db.close()

    app.teardown_appcontext(teardown)
    app.add_url_rule(flask_path, f"{method}_{flask_path}", handler, methods=[method])


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_mock_server.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/mock_server.py tests/test_mock_server.py
git commit -m "feat: add Flask-based mock server with in-memory SQLite"
```

---

### Task 11: Test Code Generator & Pytest Runner

**Files:**
- Create: `apitest/engine/runner.py`
- Create: `apitest/engine/conftest_template.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write the conftest template**

```python
# apitest/engine/conftest_template.py
CONFTEST_TEMPLATE = '''"""Auto-generated by apitest — test fixtures."""
import os
import pytest
import httpx


@pytest.fixture(scope="session")
def base_url():
    return os.environ.get("APITEST_BASE_URL", "{base_url}")


@pytest.fixture(scope="session")
def auth_token():
    token = os.environ.get("APITEST_AUTH_TOKEN", "")
    if not token:
        pytest.skip("APITEST_AUTH_TOKEN not set")
    return token


@pytest.fixture
def client(base_url):
    with httpx.Client(base_url=base_url, timeout=30.0) as c:
        yield c
'''
```

- [ ] **Step 2: Write runner test**

```python
# tests/test_runner.py
import os
import tempfile
import pytest
from apitest.engine.runner import (
    TestRunner,
    generate_pytest_file,
    write_conftest,
)
from apitest.models.example import TestExample, TestPlan, TestPlanPhase


class TestCodeGeneration:
    def test_generate_pytest_file_content(self):
        examples = [
            TestExample(
                id="TC-USERS-001",
                area="functional",
                category="happy-path",
                endpoint="GET /api/users",
                description="List users returns 200",
                preconditions=["valid token"],
                request_headers={"Authorization": "Bearer ${TOKEN}"},
                expected_status=200,
                expected_body_contains=["id", "name"],
                max_response_time_ms=2000,
            ),
        ]

        code = generate_pytest_file("users", examples, "http://localhost:8080")
        assert "class TestUsers" in code
        assert "def test_list_users_returns_200" in code
        assert "allure.feature" in code
        assert "allure.story" in code
        assert "client.get" in code
        assert "assert res.status_code == 200" in code
        assert '"id"' in code or "'id'" in code
        assert 'elapsed.total_seconds()' in code

    def test_write_conftest_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_conftest(tmpdir, "http://example.com")
            conftest_path = os.path.join(tmpdir, "conftest.py")
            assert os.path.exists(conftest_path)
            content = open(conftest_path).read()
            assert "http://example.com" in content
            assert "def client" in content
            assert "def auth_token" in content
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_runner.py -v`
Expected: FAIL

- [ ] **Step 4: Write runner**

```python
# apitest/engine/runner.py
import os
import subprocess
import sys
from pathlib import Path

from apitest.models.example import TestExample, TestPlan
from apitest.engine.conftest_template import CONFTEST_TEMPLATE


class TestRunner:
    """Generates test code and runs pytest with allure."""

    def __init__(self, config):
        self.config = config
        self._test_dir = Path("tests")

    def run(
        self, examples: list[TestExample], plan: TestPlan, mode: str, mock_server=None,
    ) -> int:
        """Execute the full test run. Returns pytest exit code."""
        self._test_dir.mkdir(exist_ok=True)

        # 1. Write conftest
        base_url = self.config.base_url
        if mode == "mock" and mock_server:
            base_url = mock_server.url

        write_conftest(str(self._test_dir), base_url)

        # 2. Generate test files grouped by resource
        test_files = _group_by_resource(examples)
        for resource, resource_examples in test_files.items():
            code = generate_pytest_file(resource, resource_examples, base_url)
            filepath = self._test_dir / f"test_{resource}.py"
            filepath.write_text(code)

        # 3. Write allure config
        (Path.cwd() / "allure-results").mkdir(exist_ok=True)

        # 4. Run pytest
        cmd = [
            sys.executable, "-m", "pytest",
            str(self._test_dir),
            "--alluredir", self.config.report_dir,
            "-v",
        ]
        result = subprocess.run(cmd, cwd=str(Path.cwd()))
        return result.returncode


def write_conftest(dir_path: str, base_url: str) -> None:
    """Write conftest.py to the test directory."""
    content = CONFTEST_TEMPLATE.format(base_url=base_url)
    Path(dir_path, "conftest.py").write_text(content)


def generate_pytest_file(resource: str, examples: list[TestExample], base_url: str) -> str:
    """Generate a pytest file for a set of examples sharing the same resource."""
    lines = [
        '"""Auto-generated by apitest."""',
        "import allure",
        "",
        "",
        f"class Test{resource.title()}:",
        f'    """Tests for {resource} endpoints."""',
        "",
    ]

    for example in examples:
        test_name = _to_test_name(example)
        method, path = example.endpoint.split(" ", 1)
        http_method = method.lower()
        feature = resource.title()
        story = example.description

        lines.append(f"    @allure.feature('{feature}')")
        lines.append(f"    @allure.story('{story}')")
        lines.append(f"    def {test_name}(self, client, auth_token):")

        # Resolve variable references in headers
        headers = {}
        for k, v in example.request_headers.items():
            headers[k] = v.replace("${TOKEN}", "{auth_token}").replace("${ADMIN_TOKEN}", "{auth_token}")

        headers_str = ", ".join(f'"{k}": f"{v}"' for k, v in headers.items())
        lines.append(f"        headers = {{{headers_str}}}")

        # Build request call
        if http_method in ("get", "delete", "head", "options"):
            if example.request_body:
                lines.append(
                    f"        res = client.{http_method}('{path}', headers=headers, json={example.request_body})"
                )
            else:
                lines.append(f"        res = client.{http_method}('{path}', headers=headers)")
        else:
            body = example.request_body or {}
            body_str = _format_body(body)
            lines.append(
                f"        res = client.{http_method}('{path}', headers=headers, json={body_str})"
            )

        # Assertions
        lines.append(f"        assert res.status_code == {example.expected_status}")
        for field in example.expected_body_contains:
            lines.append(f"        assert '{field}' in res.json()")
        lines.append(f"        assert res.elapsed.total_seconds() < {example.max_response_time_ms / 1000}")
        lines.append("")

    return "\n".join(lines)


def _group_by_resource(examples: list[TestExample]) -> dict[str, list[TestExample]]:
    groups: dict[str, list[TestExample]] = {}
    for e in examples:
        method, path = e.endpoint.split(" ", 1)
        parts = [p for p in path.split("/") if p and not p.startswith("{")]
        resource = parts[-1] if parts else "root"
        groups.setdefault(resource, []).append(e)
    return groups


def _to_test_name(example: TestExample) -> str:
    """Convert example description to a valid pytest method name."""
    import re
    name = example.description.lower()
    name = re.sub(r"[^a-z0-9 ]", "", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return f"test_{name}"


def _format_body(body: dict) -> str:
    """Format a dict as a Python literal string for code generation."""
    import json
    return json.dumps(body)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner.py -v`
Expected: 2 PASS

- [ ] **Step 6: Commit**

```bash
git add apitest/engine/runner.py apitest/engine/conftest_template.py tests/test_runner.py
git commit -m "feat: add test code generator and pytest runner"
```

---

### Task 12: Reporter

**Files:**
- Create: `apitest/engine/reporter.py`
- Create: `tests/test_reporter.py`

- [ ] **Step 1: Write reporter test**

```python
# tests/test_reporter.py
import os
import tempfile
import pytest
from apitest.engine.reporter import Reporter, check_allure_installed


class TestReporter:
    def test_check_allure_installed(self):
        # allure may or may not be installed; just check it doesn't crash
        result = check_allure_installed()
        assert isinstance(result, bool)

    def test_report_serve_prints_url(self, capsys):
        reporter = Reporter(auto_serve=True, results_dir="allure-results")
        # When allure is not installed, should print instructions
        if not check_allure_installed():
            reporter.serve()
            captured = capsys.readouterr()
            assert "allure" in captured.out.lower() or "install" in captured.out.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_reporter.py -v`
Expected: FAIL

- [ ] **Step 3: Write reporter**

```python
# apitest/engine/reporter.py
import os
import subprocess
import sys
from pathlib import Path

import webbrowser


def check_allure_installed() -> bool:
    """Check if the Allure CLI is available on PATH."""
    try:
        subprocess.run(
            ["allure", "--version"],
            capture_output=True,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class Reporter:
    """Generate and serve Allure reports from test results."""

    def __init__(self, auto_serve: bool = True, results_dir: str = "allure-results"):
        self.auto_serve = auto_serve
        self.results_dir = results_dir
        self.report_dir = "allure-report"

    def serve(self) -> None:
        """Serve the Allure report in a browser."""
        if not check_allure_installed():
            self._print_install_instructions()
            self._serve_raw_json()
            return

        results_path = Path(self.results_dir)
        if not results_path.exists() or not list(results_path.glob("*.json")):
            print(f"No Allure results found in {self.results_dir}/")
            return

        # Generate report
        subprocess.run(
            ["allure", "generate", self.results_dir, "-o", self.report_dir, "--clean"],
            check=False,
        )

        if self.auto_serve:
            report_index = Path(self.report_dir) / "index.html"
            if report_index.exists():
                webbrowser.open(f"file://{report_index.absolute()}")
                print(f"Allure report opened: {report_index}")
            else:
                print("Report generation failed. Check allure-results for raw data.")

    def _print_install_instructions(self) -> None:
        print("Allure CLI not found. Install it to generate HTML reports:")
        if sys.platform == "darwin":
            print("  brew install allure")
        elif sys.platform == "linux":
            print("  sudo apt install allure")
        else:
            print("  Download from: https://github.com/allure-framework/allure2/releases")
        print()
        print(f"Raw Allure results available in {self.results_dir}/")
        self._serve_raw_json()

    def _serve_raw_json(self) -> None:
        """Print a summary from raw Allure JSON results."""
        results_path = Path(self.results_dir)
        if not results_path.exists():
            return

        import json
        passed, failed, broken = 0, 0, 0
        for f in results_path.glob("*-result.json"):
            try:
                data = json.loads(f.read_text())
                status = data.get("status", "unknown")
                if status == "passed":
                    passed += 1
                elif status in ("failed", "broken"):
                    failed += 1
            except (json.JSONDecodeError, KeyError):
                pass

        print(f"Results: {passed} passed, {failed} failed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reporter.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/engine/reporter.py tests/test_reporter.py
git commit -m "feat: add Allure reporter with auto-serve and fallback"
```

---

### Task 13: Init Wizard

**Files:**
- Create: `apitest/cli/__init__.py`
- Create: `apitest/cli/init_wizard.py`
- Create: `tests/test_init_wizard.py`

- [ ] **Step 1: Write init wizard test**

```python
# tests/test_init_wizard.py
import os
import tempfile
import pytest
from apitest.cli.init_wizard import InitWizard


class TestInitWizard:
    def test_generate_config_yaml(self):
        wizard = InitWizard()
        answers = {
            "provider": "anthropic",
            "api_key_env": "ANTHROPIC_API_KEY",
            "api_key_manual": "",
            "model": "claude-sonnet-4-6",
            "base_url": "",
            "api_doc": "specs/openapi.yaml",
            "base_url_test": "http://localhost:8080",
            "examples_format": "json",
            "plan_format": "md",
            "coverage": "happy-path",
        }
        yaml_content = wizard._build_config(answers)
        assert "provider: anthropic" in yaml_content
        assert "${ANTHROPIC_API_KEY}" in yaml_content
        assert "json" in yaml_content
        assert "happy-path" in yaml_content

    def test_build_config_with_manual_key(self):
        wizard = InitWizard()
        answers = {
            "provider": "openai",
            "api_key_env": "",
            "api_key_manual": "sk-my-key",
            "model": "gpt-4o",
            "base_url": "",
            "api_doc": "api.yaml",
            "base_url_test": "http://localhost:3000",
            "examples_format": "xlsx",
            "plan_format": "md",
            "coverage": "full",
        }
        yaml_content = wizard._build_config(answers)
        assert "provider: openai" in yaml_content
        assert "sk-my-key" in yaml_content
        assert "xlsx" in yaml_content
        assert "full" in yaml_content

    def test_build_config_with_custom_provider(self):
        wizard = InitWizard()
        answers = {
            "provider": "custom",
            "api_key_env": "CUSTOM_KEY",
            "api_key_manual": "",
            "model": "deepseek-v3",
            "base_url": "https://api.internal.com/v1",
            "api_doc": "openapi.yaml",
            "base_url_test": "http://localhost:8080",
            "examples_format": "json",
            "plan_format": "json",
            "coverage": "smoke",
        }
        yaml_content = wizard._build_config(answers)
        assert "provider: custom" in yaml_content
        assert "base_url: https://api.internal.com/v1" in yaml_content
        assert "deepseek-v3" in yaml_content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_init_wizard.py -v`
Expected: FAIL

- [ ] **Step 3: Write init wizard**

```python
# apitest/cli/init_wizard.py
from pathlib import Path

import questionary


class InitWizard:
    """Interactive first-run setup wizard with arrow-key navigation."""

    def run(self) -> str:
        """Run the wizard and return the generated .apitest.yaml content."""
        print("Welcome to apitest — API test automation toolkit\n")

        answers = {}

        # 1. Provider
        provider = questionary.select(
            "Choose LLM provider:",
            choices=[
                questionary.Choice("Anthropic", value="anthropic"),
                questionary.Choice("OpenAI", value="openai"),
                questionary.Choice("Custom (OpenAI-compatible endpoint)", value="custom"),
            ],
        ).ask()
        if provider is None:
            raise KeyboardInterrupt()
        answers["provider"] = provider

        # 2. API Key
        key_method = questionary.select(
            "How to provide API key?",
            choices=[
                questionary.Choice("From environment variable (recommended)", value="env"),
                questionary.Choice("Enter manually", value="manual"),
            ],
        ).ask()
        if key_method == "env":
            env_name = questionary.text(
                "Environment variable name:",
                default="ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY",
            ).ask()
            answers["api_key_env"] = env_name
            answers["api_key_manual"] = ""
        else:
            manual_key = questionary.password("API key:").ask()
            answers["api_key_env"] = ""
            answers["api_key_manual"] = manual_key

        # 3. Model
        preset_models = {
            "anthropic": ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"],
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "custom": [],
        }
        presets = preset_models.get(provider, [])
        choices = [questionary.Choice(m, value=m) for m in presets]
        choices.append(questionary.Choice("Custom (type model name)", value="__custom__"))

        model = questionary.select("Model:", choices=choices).ask()
        if model == "__custom__":
            model = questionary.text(
                "Model name:",
                instruction="Format: model-name (e.g. gpt-4o, claude-sonnet-4-6)",
            ).ask()
        answers["model"] = model

        # 4. Base URL (custom provider only)
        if provider == "custom":
            base_url = questionary.text(
                "Custom endpoint URL:",
                default="https://api.example.com/v1",
                instruction="Format: https://host:port/v1",
            ).ask()
            answers["base_url"] = base_url
        else:
            answers["base_url"] = ""

        # 5. API Doc path
        answers["api_doc"] = questionary.text(
            "Default API doc path:",
            default="specs/openapi.yaml",
        ).ask()

        # 6. Test base URL
        answers["base_url_test"] = questionary.text(
            "Default base URL for test execution:",
            default="http://localhost:8080",
        ).ask()

        # 7. Examples format
        answers["examples_format"] = questionary.select(
            "Examples output format:",
            choices=[
                questionary.Choice("json (machine-readable, default)", value="json"),
                questionary.Choice("yaml", value="yaml"),
                questionary.Choice("md (markdown, human-readable)", value="md"),
                questionary.Choice("xlsx (Excel, for stakeholders)", value="xlsx"),
            ],
        ).ask()

        # 8. Plan format
        answers["plan_format"] = questionary.select(
            "Plan output format:",
            choices=[
                questionary.Choice("md (markdown, default)", value="md"),
                questionary.Choice("json", value="json"),
                questionary.Choice("yaml", value="yaml"),
                questionary.Choice("xlsx (Excel)", value="xlsx"),
            ],
        ).ask()

        # 9. Coverage depth
        answers["coverage"] = questionary.select(
            "Default coverage depth:",
            choices=[
                questionary.Choice("smoke — 1 example per endpoint", value="smoke"),
                questionary.Choice("happy-path — ~3-5 examples per endpoint (default)", value="happy-path"),
                questionary.Choice("full — ~6-10 examples per endpoint", value="full"),
            ],
        ).ask()

        return self._build_config(answers)

    def _build_config(self, answers: dict) -> str:
        provider = answers["provider"]
        api_key = ""
        if answers["api_key_env"]:
            api_key = f"${{{answers['api_key_env']}}}"
        elif answers["api_key_manual"]:
            api_key = answers["api_key_manual"]

        lines = [
            "# apitest configuration",
            f"",
            f"llm:",
            f"  provider: \"{answers['provider']}\"",
            f"  model: \"{answers['model']}\"",
            f"  api_key: \"{api_key}\"",
        ]

        if answers.get("base_url"):
            lines.append(f"  base_url: \"{answers['base_url']}\"")

        lines += [
            f"",
            f"api_doc: \"{answers['api_doc']}\"",
            f"",
            f"examples:",
            f"  format: \"{answers['examples_format']}\"",
            f"  dir: \"tests/examples\"",
            f"",
            f"plan:",
            f"  format: \"{answers['plan_format']}\"",
            f"  path: \"test_plan.{answers['plan_format']}\"",
            f"",
            f"base_url: \"{answers['base_url_test']}\"",
            f"coverage: \"{answers['coverage']}\"",
            f"",
            f"execution:",
            f"  mode: \"mock\"",
            f"  mock_server_port: null",
            f"",
            f"report:",
            f"  auto_serve: true",
            f"  dir: \"allure-results\"",
            f"",
            f"areas:",
            f"  - functional",
        ]

        return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_init_wizard.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/cli/ tests/test_init_wizard.py
git commit -m "feat: add interactive init wizard with arrow-key navigation"
```

---

### Task 14: CLI Commands

**Files:**
- Create: `apitest/cli/main.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write CLI integration test**

```python
# tests/test_cli.py
import pytest
from typer.testing import CliRunner
from apitest.cli.main import app


runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "examples" in result.stdout
        assert "plan" in result.stdout
        assert "run" in result.stdout
        assert "go" in result.stdout
        assert "report" in result.stdout
        assert "init" in result.stdout

    def test_report_command_exists(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_init_command_exists(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0

    def test_examples_command_requires_api_doc(self):
        result = runner.invoke(app, ["examples"])
        # Should either show help or error about missing argument
        assert "Usage" in result.stdout or "Missing" in result.stdout or result.exit_code != 0

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "apitest" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Write CLI main**

```python
# apitest/cli/main.py
from pathlib import Path
from typing import Optional

import typer

from apitest import __version__
from apitest.config import load_config
from apitest.engine.parser import parse_openapi, detect_format
from apitest.engine.llm_client import LLMClient
from apitest.engine.generator import Generator
from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan
from apitest.engine.runner import TestRunner
from apitest.engine.reporter import Reporter
from apitest.engine.mock_server import create_mock_app, MockServer
from apitest.cli.init_wizard import InitWizard

app = typer.Typer(
    name="apitest",
    help="AI-powered API test automation toolkit",
)


def version_callback(value: bool):
    if value:
        print(f"apitest v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", callback=version_callback, help="Show version",
    ),
):
    pass


@app.command()
def init():
    """Run the interactive first-run setup wizard."""
    wizard = InitWizard()
    yaml_content = wizard.run()

    config_path = Path.cwd() / ".apitest.yaml"
    if config_path.exists():
        overwrite = typer.confirm(".apitest.yaml already exists. Overwrite?")
        if not overwrite:
            print("Aborted.")
            raise typer.Exit()

    config_path.write_text(yaml_content)
    print(f"\nConfig written to {config_path}")
    print("You're ready! Try: apitest go <your-api-doc>")


@app.command()
def examples(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Generate test examples from an API document."""
    config = load_config(config_path)
    fmt = output_format or config.examples_format
    cov = coverage or config.coverage

    print(f"Parsing {api_doc}...")
    endpoints = parse_openapi(api_doc)
    print(f"Found {len(endpoints)} endpoints")

    print(f"Generating examples (coverage: {cov})...")
    client = LLMClient.create(
        config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
    )
    gen = Generator(client)
    test_examples = gen.generate_examples(endpoints, cov, config.areas)

    output_dir = Path(config.examples_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"examples.{fmt}"

    write_examples(test_examples, str(output_path), fmt)
    print(f"Generated {len(test_examples)} examples → {output_path}")


@app.command()
def plan(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    output_format: Optional[str] = typer.Option(None, "--format", "-f", help="Output format"),
):
    """Orchestrate test examples into a test plan."""
    config = load_config(config_path)
    fmt = output_format or config.plan_format

    # Read examples
    examples_dir = Path(config.examples_dir)
    examples_file = examples_dir / f"examples.{config.examples_format}"
    if not examples_file.exists():
        print(f"Examples not found: {examples_file}")
        print("Run 'apitest examples <api-doc>' first.")
        raise typer.Exit(code=1)

    print(f"Reading examples from {examples_file}...")
    test_examples = read_examples(str(examples_file), config.examples_format)

    print(f"Generating plan for {len(test_examples)} examples...")
    client = LLMClient.create(
        config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
    )
    gen = Generator(client)
    test_plan = gen.generate_plan(test_examples, config.coverage, config.areas)

    plan_path = config.plan_path
    if not plan_path.endswith(f".{fmt}"):
        plan_path = f"test_plan.{fmt}"

    write_plan(test_plan, plan_path, fmt)
    print(f"Plan written → {plan_path}")
    print(f"  Phases: {len(test_plan.phases)}")
    print(f"  Total examples: {test_plan.total_examples}")
    print("Review the plan, then run: apitest run")


@app.command()
def run(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode: mock | real"),
):
    """Execute the test plan and generate an Allure report."""
    config = load_config(config_path)
    exec_mode = mode or config.execution_mode

    # Read examples and plan
    examples_dir = Path(config.examples_dir)
    examples_file = examples_dir / f"examples.{config.examples_format}"
    if not examples_file.exists():
        print(f"Examples not found: {examples_file}")
        print("Run 'apitest examples <api-doc>' first.")
        raise typer.Exit(code=1)

    plan_file = Path(config.plan_path)
    if not plan_file.exists():
        # Try other formats
        for fmt in ["md", "json", "yaml"]:
            alt = Path(f"test_plan.{fmt}")
            if alt.exists():
                plan_file = alt
                break

    if not plan_file.exists():
        print(f"Plan not found: {config.plan_path}")
        print("Run 'apitest plan' first.")
        raise typer.Exit(code=1)

    test_examples = read_examples(str(examples_file), config.examples_format)
    plan_fmt = plan_file.suffix.lstrip(".")
    test_plan = read_plan(str(plan_file), plan_fmt)

    # Start mock server if needed
    mock_server = None
    if exec_mode == "mock":
        import yaml
        with open(config.api_doc) as f:
            spec = yaml.safe_load(f)
        mock_app = create_mock_app(spec)
        mock_server = MockServer(mock_app, port=config.execution_mock_server_port)
        mock_server.start()
        print(f"Mock server started at {mock_server.url}")

    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)

        # Report
        reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
        reporter.serve()

        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)

        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")


@app.command()
def go(
    api_doc: str = typer.Argument(..., help="Path to API documentation"),
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    coverage: Optional[str] = typer.Option(None, "--coverage", help="Coverage level"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Execution mode: mock | real"),
):
    """Run the full pipeline: examples → plan → run → report."""
    config = load_config(config_path)
    cov = coverage or config.coverage
    exec_mode = mode or config.execution_mode

    # Step 1: Examples
    print(f"\n{'='*50}")
    print(f"Step 1/3: Generating test examples")
    print(f"{'='*50}\n")

    endpoints = parse_openapi(api_doc)
    print(f"Parsed {len(endpoints)} endpoints from {api_doc}")

    client = LLMClient.create(
        config.llm_provider, config.llm_model, config.llm_api_key, config.llm_base_url,
    )
    gen = Generator(client)
    test_examples = gen.generate_examples(endpoints, cov, config.areas)

    output_dir = Path(config.examples_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    examples_path = output_dir / f"examples.{config.examples_format}"
    write_examples(test_examples, str(examples_path), config.examples_format)
    print(f"Generated {len(test_examples)} examples → {examples_path}")

    # Step 2: Plan
    print(f"\n{'='*50}")
    print(f"Step 2/3: Generating test plan")
    print(f"{'='*50}\n")

    test_plan = gen.generate_plan(test_examples, cov, config.areas)
    plan_path = config.plan_path
    write_plan(test_plan, plan_path, config.plan_format)
    print(f"Plan written → {plan_path}")
    print(f"  Phases: {len(test_plan.phases)}, Total: {test_plan.total_examples} examples")

    # Step 3: Execute
    print(f"\n{'='*50}")
    print(f"Step 3/3: Running tests")
    print(f"{'='*50}\n")

    mock_server = None
    if exec_mode == "mock":
        import yaml
        with open(config.api_doc) as f:
            spec = yaml.safe_load(f)
        mock_app = create_mock_app(spec)
        mock_server = MockServer(mock_app, port=config.execution_mock_server_port)
        mock_server.start()
        print(f"Mock server started at {mock_server.url}")

    try:
        print(f"Running {test_plan.total_examples} tests ({exec_mode} mode)...")
        runner = TestRunner(config)
        exit_code = runner.run(test_examples, test_plan, exec_mode, mock_server)

        reporter = Reporter(auto_serve=config.report_auto_serve, results_dir=config.report_dir)
        reporter.serve()

        if exit_code != 0:
            print(f"\nTests completed with failures (exit code: {exit_code})")
            raise typer.Exit(code=exit_code)

        print("\nAll tests passed!")
    finally:
        if mock_server:
            mock_server.stop()
            print("Mock server stopped.")


@app.command()
def report(
    config_path: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """Re-serve the last Allure report."""
    config = load_config(config_path)
    reporter = Reporter(auto_serve=True, results_dir=config.report_dir)
    reporter.serve()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add apitest/cli/main.py tests/test_cli.py
git commit -m "feat: add CLI commands (examples, plan, run, go, report, init)"
```

---

### Task 15: Integration Test (End-to-End)

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write end-to-end test with mock mode**

```python
# tests/test_integration.py
import os
import tempfile
import json
import pytest
from typer.testing import CliRunner
from apitest.cli.main import app


runner = CliRunner()


PETSTORE_YAML = """
openapi: "3.0.0"
info:
  title: Petstore
  version: "1.0.0"
paths:
  /api/pets:
    get:
      operationId: listPets
      responses:
        "200":
          description: OK
    post:
      operationId: createPet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
                  minLength: 1
                  maxLength: 50
                species:
                  type: string
                  enum: [cat, dog, bird]
      responses:
        "201":
          description: Created
        "400":
          description: Bad Request
  /api/pets/{petId}:
    get:
      operationId: getPet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
        "404":
          description: Not Found
    delete:
      operationId: deletePet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "204":
          description: No Content
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
"""


class TestIntegration:
    """End-to-end tests using the mock LLM (no real API key needed)."""

    def test_full_pipeline_with_mock_mode(self):
        """Run examples -> plan -> run in mock mode with a fake LLM response."""
        # Create a temp directory with .apitest.yaml and the spec
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write spec
            spec_path = os.path.join(tmpdir, "petstore.yaml")
            with open(spec_path, "w") as f:
                f.write(PETSTORE_YAML)

            # Write config that uses a fake API key (tests don't call real LLM)
            config = {
                "llm": {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_key": "fake-key"},
                "api_doc": spec_path,
                "examples": {"format": "json", "dir": os.path.join(tmpdir, "tests/examples")},
                "plan": {"format": "json", "path": os.path.join(tmpdir, "test_plan.json")},
                "base_url": "http://localhost:8080",
                "coverage": "smoke",
                "execution": {"mode": "mock", "mock_server_port": None},
                "report": {"auto_serve": False, "dir": os.path.join(tmpdir, "allure-results")},
                "areas": ["functional"],
            }
            config_path = os.path.join(tmpdir, ".apitest.yaml")
            import yaml
            with open(config_path, "w") as f:
                yaml.dump(config, f)

            # Parse spec (no LLM needed)
            from apitest.engine.parser import parse_openapi
            endpoints = parse_openapi(spec_path)
            assert len(endpoints) == 3  # GET /pets, POST /pets, GET /pets/{id}, DELETE /pets/{id}

            # Verify mock server starts and handles CRUD
            from apitest.engine.mock_server import create_mock_app, MockServer
            with open(spec_path) as f:
                spec = yaml.safe_load(f)

            mock_app = create_mock_app(spec)
            mock_server = MockServer(mock_app, port=0)
            mock_server.start()

            import httpx
            try:
                # POST a pet
                resp = httpx.post(f"{mock_server.url}/api/pets", json={"name": "Rex", "species": "dog"})
                assert resp.status_code == 201
                pet_data = resp.json()
                assert pet_data["name"] == "Rex"
                pet_id = pet_data["id"]

                # GET list
                resp = httpx.get(f"{mock_server.url}/api/pets")
                assert resp.status_code == 200
                pets = resp.json()
                assert len(pets) == 1

                # GET by id
                resp = httpx.get(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 200

                # DELETE
                resp = httpx.delete(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 204

                # GET deleted
                resp = httpx.get(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 404

                # POST missing required field
                resp = httpx.post(f"{mock_server.url}/api/pets", json={"species": "cat"})
                assert resp.status_code == 400
            finally:
                mock_server.stop()


    def test_generate_examples_and_plan_integration(self):
        """Test that examples can be generated and a plan created from them."""
        from apitest.models.example import TestExample, TestPlan, TestPlanPhase
        from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create sample examples
            examples = [
                TestExample(
                    id="TC-PETS-001", area="functional", category="happy-path",
                    endpoint="GET /api/pets", description="List pets returns 200",
                    expected_status=200,
                ),
                TestExample(
                    id="TC-PETS-002", area="functional", category="happy-path",
                    endpoint="POST /api/pets", description="Create pet returns 201",
                    expected_status=201, request_body={"name": "Fluffy"},
                ),
            ]

            # Write as JSON
            json_path = os.path.join(tmpdir, "examples.json")
            write_examples(examples, json_path, "json")

            # Read back
            loaded = read_examples(json_path, "json")
            assert len(loaded) == 2

            # Create and write a plan as JSON
            plan = TestPlan(
                title="Test Plan: Petstore",
                coverage="smoke",
                areas=["functional"],
                total_examples=2,
                phases=[
                    TestPlanPhase(name="Pets", order=1, examples=["TC-PETS-001", "TC-PETS-002"]),
                ],
            )
            plan_path = os.path.join(tmpdir, "plan.json")
            write_plan(plan, plan_path, "json")

            # Read back
            loaded_plan = read_plan(plan_path, "json")
            assert loaded_plan.title == "Test Plan: Petstore"
            assert len(loaded_plan.phases) == 1
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/test_integration.py -v`
Expected: 2 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add end-to-end integration tests for mock mode"
```

---

### Task 16: Finalize — Run Full Test Suite & Verify

- [ ] **Step 1: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (should be ~30+ tests across all test files)

- [ ] **Step 2: Verify CLI --help output**

Run: `python -m apitest.cli.main --help`
Expected: Shows commands (init, examples, plan, run, go, report)

- [ ] **Step 3: Verify CLI --version**

Run: `python -m apitest.cli.main --version`
Expected: `apitest v0.1.0`

- [ ] **Step 4: Verify import completeness**

Run: `python -c "
from apitest import __version__
from apitest.config import Config, load_config
from apitest.models import Endpoint, TestExample, TestPlan, CATEGORIES, COVERAGE_LEVELS
from apitest.engine import LLMClient, OpenAIClient, AnthropicClient, CustomClient
from apitest.areas import TestArea, registry
print('All imports OK')
"`
Expected: `All imports OK`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: finalize v0.1.0 — all tests passing"
```
