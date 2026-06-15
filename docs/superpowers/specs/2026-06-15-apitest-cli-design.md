# apitest — API Test Automation CLI Design Spec

## Overview

A CLI tool that assists QA engineers through the API testing lifecycle: requirements analysis (API doc ingestion) → test example generation → test plan orchestration → plan execution → Allure report delivery. The tool uses LLMs (OpenAI/Anthropic) for intelligent analysis and generation.

## Lifecycle & Commands

```
API Doc → apitest examples → apitest plan → [User Review] → apitest run → Allure Report
                              \                                      /
                               apitest go (all-in-one)
```

| Command | Stage | Description |
|---|---|---|
| `apitest init` | Setup | Interactive first-run wizard, writes `.apitest.yaml` |
| `apitest examples <api-doc>` | Generate | Parse API doc → LLM generates test examples → write to disk |
| `apitest plan` | Orchestrate | Read examples → LLM arranges into ordered plan → write to disk |
| `apitest run` | Execute | Read plan + examples → generate pytest code → run → collect Allure results |
| `apitest go <api-doc>` | Pipeline | examples → plan → run in sequence |
| `apitest report` | Report | Re-serve last Allure report in browser |

## Config File: `.apitest.yaml`

```yaml
# LLM provider
llm:
  provider: "anthropic"           # openai | anthropic | custom
  model: "claude-sonnet-4-6"
  api_key: "${ANTHROPIC_API_KEY}" # env var reference or plain string
  base_url: null                  # only for custom provider

# Input
api_doc: "specs/openapi.yaml"

# Output
examples:
  format: "json"                  # json | yaml | md | xlsx
  dir: "tests/examples"
plan:
  format: "md"                    # md | json | yaml | xlsx
  path: "test_plan.md"

# Execution
base_url: "http://localhost:8080"
coverage: "happy-path"            # smoke | happy-path | full
execution:
  mode: "mock"                    # mock | real
  mock_server_port: null          # auto-assigned if omitted

# Report
report:
  auto_serve: true
  dir: "allure-results"

# Test areas (v1: functional only, others for future)
areas:
  - functional
```

## Init Flow (First-Run Wizard)

Interactive terminal UI using arrow-key navigation (`↑↓`), Enter to select, with custom free-text input support.

**Interaction pattern:**
- Preset options: arrow keys navigate, Enter selects
- "Custom" option at bottom of each list: switches to free-text input with format reference displayed above the input line
- Light validation on custom input (URL format, non-empty); re-prompt with hint on failure

**Question sequence:**
1. **Provider** — OpenAI / Anthropic / Custom
2. **API Key** — From env var (type name) / Enter manually (masked input)
3. **Model** — Provider-specific preset list / Custom (type name, format: `model-name`)
4. **Base URL** (custom provider only) — text input (format: `https://host:port/v1`)
5. **API Doc path** — text input (default: `specs/openapi.yaml`)
6. **Test base URL** — text input (default: `http://localhost:8080`)
7. **Examples format** — json (default) / yaml / md / xlsx
8. **Plan format** — md (default) / json / yaml / xlsx
9. **Coverage depth** — smoke / happy-path (default) / full

**TUI library:** `python-inquirer` or `questionary`

## Architecture

### Package Structure

```
apitest/
├── __init__.py
├── py.typed
├── config.py              # .apitest.yaml loader, env var resolution
├── cli/
│   ├── __init__.py
│   ├── main.py            # Typer CLI entry point, command routing
│   └── init_wizard.py     # Interactive first-run setup (questionary)
├── areas/
│   ├── __init__.py
│   ├── base.py            # TestArea abstract base class
│   └── functional.py      # v1: Functional Business Testing area
├── engine/
│   ├── __init__.py
│   ├── parser.py          # OpenAPI/Swagger/Postman → list[Endpoint]
│   ├── llm_client.py      # OpenAI/Anthropic/custom HTTP abstraction
│   ├── generator.py       # Orchestrates areas → examples + plan
│   ├── runner.py          # pytest + allure-pytest invocation
│   ├── reporter.py        # Allure serve/generate
│   └── formatter.py       # JSON/YAML/MD/XLSX read/write
└── models/
    ├── __init__.py
    ├── endpoint.py        # Endpoint dataclass (method, path, params, schema, auth)
    └── example.py         # TestExample dataclass
```

### Dependency Graph

```
config.py  ←── cli/, engine/, areas/

cli/
  main.py ──→ init_wizard.py
  main.py ──→ engine/parser.py, engine/generator.py, engine/runner.py, engine/reporter.py

engine/
  parser.py   ──→ models/endpoint.py
  generator.py ──→ areas/base.py, engine/llm_client.py, engine/formatter.py, models/example.py
  runner.py   ──→ models/example.py, engine/formatter.py
  reporter.py ──→ (shells out to allure)

areas/
  base.py     ──→ models/endpoint.py, models/example.py, engine/llm_client.py
  functional.py ──→ base.py
```

### Test Area Plugin Protocol

Each testing business area is a class implementing `TestArea`:

```python
class TestArea(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_prompt_context(self, endpoints: list[Endpoint]) -> str:
        """Area-specific context injected into the LLM system prompt."""

    @abstractmethod
    def generate_examples(
        self, endpoints: list[Endpoint], coverage: str, llm: LLMClient
    ) -> list[TestExample]:
        """Generate test examples for this area."""

    @abstractmethod
    def generate_test_code(
        self, examples: list[TestExample], llm: LLMClient
    ) -> str:
        """Generate pytest code for examples. Returns file content."""
```

**v1 area:** `FunctionalBusinessTesting` — the default and only enabled area.
**v2+ areas:** `DataConsistency`, `PerformanceStability`, `Security`, `IdempotencyReliability`, `IntegrationContract`, `VersionCompatibility`, `Observability`

Areas are discovered via a registry in `areas/__init__.py`. The generator iterates over enabled areas, calling each area's `generate_examples()` and merging results. In v1, only one area runs; the architecture supports parallel execution when multiple areas are enabled.

## Test Example Schema

Each generated example follows this JSON structure:

```json
{
  "id": "TC-USER-001",
  "area": "functional",
  "category": "happy-path",
  "endpoint": "POST /api/users",
  "description": "Create user with valid data returns 201",
  "preconditions": ["valid admin JWT token"],
  "request": {
    "headers": {"Authorization": "Bearer ${ADMIN_TOKEN}", "Content-Type": "application/json"},
    "body": {"name": "John Doe", "email": "john@example.com", "age": 30}
  },
  "expected": {
    "status": 201,
    "body_contains": ["id", "name", "email"],
    "schema": "UserResponse",
    "max_response_time_ms": 2000
  },
  "depends_on": null,
  "cleanup": "DELETE /api/users/{id}"
}
```

**Design rules:**
- `id` — unique, pattern `TC-<RESOURCE>-<NNN>`
- `area` — source test area name
- `category` — one of: `happy-path`, `equivalence-class`, `boundary-value`, `negative`, `auth-security`, `lifecycle`
- `${VAR}` syntax for dynamic values (tokens, IDs from previous steps)
- `depends_on` — references another example ID for chaining (ODG-driven)
- `cleanup` — free-text description of cleanup action

## Generation Strategy

### Phase 1: Analyze
LLM parses the API doc and produces structured analysis:
- Endpoint inventory (method, path, parameters, request/response schemas)
- Operation Dependency Graph (ODG) — which endpoints feed into others
- Schema constraints per parameter (type, min/max, minLength/maxLength, enum, required, format)
- Detected security schemes (bearer, apiKey, oauth2, basic)

### Phase 2: Generate Examples (6 Dimensions)

| # | Dimension | Rule | Method |
|---|---|---|---|
| 1 | Happy Path | Every endpoint ≥1 success case | First valid value per param from schema |
| 2 | Equivalence Class | Partition valid/invalid, one per class | Infer from type + constraints + enums |
| 3 | Boundary Values | min±1, max±1 for every numeric/length constraint | Extract min/max/minLength/maxLength |
| 4 | Negative Tests | Missing required, wrong type, malformed JSON, invalid enum | For each required field: omit; for typed: wrong type |
| 5 | Auth & Security | No token, expired token, wrong role/scope | Per detected security scheme |
| 6 | Resource Lifecycle | CRUD chains: Create→Read→Update→Read→Delete→Read(404) | ODG topological traversal |

**Coverage matrix:**

| Level | 1 | 2 | 3 | 4 | 5 | 6 | ~examples/endpoint |
|---|---|---|---|---|---|---|---|
| `smoke` | ✓ | — | — | — | — | — | ~1 |
| `happy-path` | ✓ | ✓ | — | ✓ | — | — | ~3-5 |
| `full` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~6-10 |

**Key principles (from Chinese QA practice):**
- **Unified structure** — every example follows the same JSON schema, no ad-hoc formats
- **Layered, not multiplied** — total examples = scenario count + verification count (not scenarios × verifications)
- **Dependency-driven preconditions** — use real API calls (not direct DB inserts) to set up test data
- **Category before endpoint** — group by `category` first, then by endpoint, to make coverage gaps visible

### Phase 3: Orchestrate Plan
LLM reads all generated examples and produces a test plan:
- Order by dependency (ODG topological sort)
- Group by resource/module
- Prioritize by risk and coverage breadth
- Identify shared fixtures and setup sequences
- Plan includes: execution order, estimated duration, prerequisite data, cleanup order

## Test Plan Schema

```json
{
  "plan": {
    "title": "Test Plan: Petstore API",
    "created": "2026-06-15T10:00:00Z",
    "coverage": "happy-path",
    "areas": ["functional"],
    "total_examples": 42,
    "estimated_duration_minutes": 15,
    "phases": [
      {
        "name": "Setup & Authentication",
        "order": 1,
        "examples": ["TC-AUTH-001"],
        "description": "Obtain tokens and verify auth endpoints"
      },
      {
        "name": "User CRUD Lifecycle",
        "order": 2,
        "examples": ["TC-USER-001", "TC-USER-002", ...],
        "depends_on_phase": 1
      }
    ]
  }
}
```

## Test Execution

The executor generates pytest files from the plan + examples, using a lightweight framework:

```python
# Generated test — example output
class TestUsers:
    endpoint = "/api/users"

    @allure.feature("Users")
    @allure.story("Create user")
    def test_create_user_returns_201(self, client, auth_token):
        res = client.post(
            self.endpoint,
            json={"name": "John Doe", "email": "john@example.com", "age": 30},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert res.status_code == 201
        assert "id" in res.json()
        assert res.elapsed.total_seconds() < 2.0
```

- `client` — fixture wrapping `httpx.Client` with base_url from config
- `auth_token` — fixture resolving `${ADMIN_TOKEN}` from env or pre-step output
- `@allure.*` decorators — auto-generated from area, category, and endpoint
- Cleanup via pytest fixture teardown based on example's `cleanup` field

The executor invokes: `pytest tests/ --alluredir=allure-results/`

### Execution Modes

Tests run in one of two modes, configured via `.apitest.yaml` or `--mode` flag.
The generated test code is identical in both modes — only the target changes.

#### Mock Mode (default)

For first-time users, offline development, and shift-left testing before the real API exists.

```
apitest run --mode mock
```

1. CLI parses the API doc and generates a **Flask-based mock server** from the spec
2. Mock server starts on `localhost:<port>` (auto-assigned or configured)
3. `base_url` is overridden to point at the mock server
4. Tests run against the mock, Allure results collected
5. Mock server is stopped

**Mock server behavior:**
- Routes generated from OpenAPI paths and methods
- Response bodies generated from schema examples (or auto-generated from types)
- **In-memory SQLite store** for stateful CRUD — POST writes, GET reads, DELETE removes
- Schema validation on request bodies (returns 400 for mismatches)
- Auth simulation: accepts any well-formed Bearer token, returns mock JWT
- Realistic error responses: 404 for missing resources, 409 for duplicates

**Limitations:** No real DB verification, no real auth integration, no external service dependencies.

#### Real Mode

For testing against live APIs with real infrastructure.

```
apitest run --mode real
```

1. Tests run against the configured `base_url`
2. Auth tokens come from environment variables (as configured)
3. Cleanup actually matters — proper setup/teardown required
4. Optional DB connection for data consistency verification (v1.5+)

**Config:**
```yaml
execution:
  mode: "mock"               # mock | real
  mock_server_port: null     # auto-assigned if omitted
  db:                        # real mode only (v1.5+)
    type: "postgresql"
    url: "${DATABASE_URL}"
```

#### Mode Comparison

| Aspect | Mock | Real |
|---|---|---|
| Target | Local Flask server | Live API at base_url |
| Auth | Accepts any well-formed token | Real token from env vars |
| DB | In-memory SQLite | Optional DB connection (v1.5+) |
| Side effects | Ephemeral, lost on stop | Persistent, needs cleanup |
| Use case | First try, CI, shift-left | Actual API testing, integration |
| Generated tests | Same | Same |

## Report

Allure CLI (Java-based) is required for HTML report generation. If not installed, the CLI prints
installation instructions (`brew install allure` on macOS, `apt install allure` on Debian/Ubuntu)
and falls back to serving raw JSON results.

After execution:
1. Run `allure generate allure-results/ -o allure-report/` to produce the static HTML report
2. If `auto_serve: true`, run `allure open allure-report/` to open it in the default browser
3. If Allure CLI not installed, output raw Allure JSON results and print install instructions

## Input Formats Supported

| Format | Parse Method |
|---|---|
| OpenAPI 3.x (JSON/YAML) | `openapi-core` or custom parser |
| Swagger 2.0 (JSON/YAML) | Same parser, version-detect |
| Postman Collection v2.1 | Custom parser (JSON structure) |

## Non-Goals for v1

- CI/CD integration (interactive-only)
- Non-functional test areas (Data Consistency, Performance, Security, etc. — architecture supports them, implementation deferred)
- Test data factories / synthetic data generation beyond what LLM infers from schemas
- Real-time test monitoring / streaming
- Export to non-Allure report formats

## Tech Stack

| Component | Choice |
|---|---|
| CLI framework | `typer` |
| TUI prompts | `questionary` |
| HTTP client (runtime) | `httpx` |
| Test runner | `pytest` + `pytest-httpx` |
| Report | `allure-pytest` + Allure CLI |
| LLM clients | `openai` + `anthropic` SDKs |
| OpenAPI parsing | `openapi-core` + `prance` |
| Mock server | `flask` + in-memory SQLite |
| Excel output | `openpyxl` |
| YAML output | `pyyaml` |
| Package management | `hatchling` or `poetry` |
| Minimum Python | 3.10 |
