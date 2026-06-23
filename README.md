# apitest

AI-powered API test automation CLI. Give it an API document, get a test suite and Allure report.

```
API Doc → [LLM] → Test Examples → Test Plan → [You Review] → Pytest + Mock → Allure Report
```

## Install

```bash
git clone <repo-url> && cd apitest
uv sync
```

Requirements: Python 3.10+, [Allure CLI](https://docs.qameta.io/allure-report/#_installing_a_commandline) (`brew install allure` on macOS).

## Quick Start

```bash
# First run: configure LLM provider (interactive arrow-key prompts)
apitest init

# Or set API key via env var (auto-detected):
export ANTHROPIC_API_KEY=your-key   # or ANTHROPIC_AUTH_TOKEN

# Test an OpenAPI spec end-to-end
apitest go specs/api.yaml --mode mock
```

## Commands

| Command | What it does |
|---|---|
| `apitest init` | Interactive setup wizard (LLM provider, API key, formats, coverage) |
| `apitest test` | Test LLM connection — verifies API key and model access |
| `apitest examples <doc>` | Parse API doc → LLM generates test examples → save to disk |
| `apitest plan` | Read examples → deterministic plan (use `--llm-plan` for LLM) |
| `apitest run` | Execute plan against mock or real server → Allure report |
| `apitest go <doc>` | All-in-one: examples → preflight → plan → run → report |
| `apitest report` | Re-serve the last Allure report |
| `apitest cache-clear <doc>` | Clear cached LLM responses for a spec |

## Key Options

| Flag | Commands | What it does |
|---|---|---|
| `--fast` | `examples`, `go` | Schema-only generation — no LLM calls, instant results |
| `--no-cache` | `examples`, `go` | Skip cache, force fresh LLM generation |
| `--thinking` / `--no-thinking` | `examples`, `plan`, `go` | Toggle LLM thinking mode. On by default for better quality; disable with `--no-thinking` if you trust the LLM or want lower token usage (~3x faster) |
| `--llm-plan` | `plan`, `go` | Use LLM for test plan generation instead of deterministic |
| `--mode mock\|real` | `run`, `go` | Mock server or real API |
| `--coverage smoke\|happy-path\|full` | `examples`, `go` | Test depth level |

## Benchmark

Tested on a 20-endpoint markdown API doc with DeepSeek V4, 3 parallel chunks, smoke coverage.

| Condition | Time | Notes |
|---|---|---|
| No thinking + cold (no cache) | **15.2s** | Default mode — LLM generates examples |
| No thinking + warm (cache hit) | **0.15s** | Instant re-run when spec unchanged |
| Thinking enabled + cold | **49.6s** | 3.3x slower than default |
| Thinking enabled + warm | **0.16s** | Cache bypasses LLM entirely |
| `--fast` (schema-only, no LLM) | <0.1s | Instant, less realistic test data |

Cache speedup: **100x** on re-runs. Thinking disabled is **3.3x faster** than enabled with minimal quality difference for structured API test generation.

## API Doc Formats

| Format | Mock mode |
|---|---|
| OpenAPI 3.x (YAML/JSON) | Supported |
| Swagger 2.0 (YAML/JSON) | Supported |
| Markdown / text | LLM-only (mock needs companion OpenAPI spec) |

## Config (`.apitest.yaml`)

```yaml
llm:
  provider: anthropic          # anthropic | openai | custom
  model: claude-sonnet-4-6
  api_key: ${ANTHROPIC_API_KEY}
  thinking_enabled: true       # on by default; set false or use --no-thinking to disable
  cache_enabled: true          # set false or use --no-cache to skip cache

api_doc: specs/openapi.yaml

examples:
  format: json                # json | yaml | md | xlsx
  dir: tests/examples
plan:
  format: md                  # md | json | yaml | xlsx
  path: test_plan.md

coverage: happy-path          # smoke | happy-path | full
execution:
  mode: mock                  # mock | real
report:
  auto_serve: true
```

## Coverage Levels

| Level | Categories | ~examples/endpoint |
|---|---|---|
| `smoke` | Happy path only | 1 |
| `happy-path` | Happy path, equivalence, negative | 3-5 |
| `full` | All 6 categories (boundary, auth, lifecycle) | 6-10 |

## How It Works

1. **LLM Parsing**: Reads your API doc and extracts endpoints, parameters, schemas
2. **Schema Correction** (OpenAPI): Cross-references LLM output against parsed schema to fix field names and status codes
3. **Preflight Validation**: Runs every generated example against the mock server, correcting `expected_status` from actual responses — eliminates LLM hallucination errors
4. **Test Plan**: Deterministic resource grouping (use `--llm-plan` for LLM-driven ordering)
5. **Mock Server**: Flask-based server with in-memory SQLite that serves schema-compliant responses
6. **Pytest + Allure**: Generates pytest files grouped by resource, runs them, produces HTML report served via Python HTTP server (no Java process leak)

## Mock Mode Specification

When `--mode mock` is used, apitest starts a Flask-based mock server that serves schema-compliant responses without needing a real backend.

### Architecture

```
Flask app (daemon thread) + in-memory SQLite
  ├── Schema parser: extracts response schemas from OpenAPI spec
  ├── Fake data generator: produces realistic values per property name/type/constraints
  └── Stateful store: remembers POST/PUT data so GET returns consistent results
```

### Supported Operations

| Method | Behavior |
|---|---|
| `GET /resource` | Returns generated list with pagination wrapper (`{code, message, data: [...]}`) |
| `GET /resource/{id}` | Returns stored item if found, otherwise generates fake item with that ID |
| `POST /resource` | Validates required body fields, stores item, returns success response with generated ID |
| `PUT /resource/{id}` | Updates stored item (404 if not found), returns merged result |
| `PATCH /resource/{id}` | Partial update of stored item (404 if not found) |
| `DELETE /resource/{id}` | Removes item from store, returns 204 (idempotent — succeeds even if absent) |

### Schema Resolution

1. Response schema is extracted from the first 2xx response in the OpenAPI operation
2. `$ref` chains are resolved against `components/schemas`
3. For wrapped responses (`{code, message, data}`), the `data` sub-schema is used for payload generation
4. For list endpoints, the `data.list` items schema generates array elements

### Fake Data Generation Rules

- Property **names** drive values: `email` → `user@example.com`, `phone` → `138...`, `price` → random float, `id` → auto-increment integer
- Schema **types and constraints** are respected: `enum`, `min`/`max`, `minLength`/`maxLength`, `format` (email, date-time, uri, uuid)
- Boolean names starting with `is`/`has`/`allow`/`show` default to `true`
- Tags/arrays return 1-3 random samples from a curated Chinese + English list

### Limitations

- Request body validation only checks `required` fields at the top level — nested required fields are not validated
- No authentication enforcement — the mock server accepts any `Authorization` header
- No business logic — relationships between resources (e.g., "user must exist before creating a post") are not enforced
- Schema-less responses (operations with no 2xx response schema) fall back to empty `{}` or `[]`

## Example Output

```
$ apitest go demo/specs/xiaohongshu-openapi.yaml --mode mock --coverage smoke

==================================================
Step 1/3: Generating test examples
==================================================
Parsed 17 endpoints
Calling deepseek-v4-pro[1m] to generate examples (coverage: smoke)...
  Splitting 17 endpoints into 2 chunks (2 parallel LLM calls)...
  Preflight validating against mock server at http://127.0.0.1:51234...
  Preflight: corrected 3 expected status codes (0 skipped/17 total)
Generated 17 examples -> tests/examples/examples.json

==================================================
Step 2/3: Generating test plan
==================================================
Plan written -> test_plan.md
  Phases: 4, Total: 17 examples

==================================================
Step 3/3: Running tests
==================================================
Running 17 tests (mock mode)...
Allure report: http://127.0.0.1:51235 (auto-closes when CLI exits)

17 passed in 0.20s — All tests passed!
```

## Tech Stack

Python · Typer · Questionary · httpx · Pytest · Allure · Flask · Anthropic SDK · OpenAI SDK · PyYAML
