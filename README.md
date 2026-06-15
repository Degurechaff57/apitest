# apitest

AI-powered API test automation CLI. Give it an API document, get a test suite and Allure report.

```
API Doc → [LLM] → Test Examples → Test Plan → [You Review] → Pytest + Mock → Allure Report
```

## Install

```bash
git clone <repo-url> && cd apitest
uv pip install -e .
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
| `apitest examples <doc>` | Parse API doc → LLM generates test examples → save to disk |
| `apitest plan` | Read examples → LLM orchestrates into ordered test plan |
| `apitest run` | Execute plan against mock or real server → Allure report |
| `apitest go <doc>` | All-in-one: examples → plan → run → report |
| `apitest report` | Re-serve the last Allure report |

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
2. **Schema Correction**: Cross-references LLM output against parsed schema to fix field names and status codes
3. **Test Plan**: LLM organizes examples into phases ordered by endpoint dependencies
4. **Mock Server**: Flask-based server with in-memory SQLite that serves schema-compliant responses
5. **Pytest + Allure**: Generates pytest files grouped by resource, runs them, produces Allure report

## Example Output

```
$ apitest go demo/specs/xiaohongshu-openapi.yaml --mode mock

==================================================
Step 1/3: Generating test examples
==================================================
Parsed 17 endpoints
Corrected examples against API spec
Generated 17 examples -> tests/examples/examples.json

==================================================
Step 2/3: Generating test plan
==================================================
Plan written -> test_plan.md
  Phases: 8, Total: 17 examples

==================================================
Step 3/3: Running tests
==================================================
Mock server started at http://127.0.0.1:51234
Running 17 tests (mock mode)...
17 passed in 0.20s

All tests passed!
```

## Tech Stack

Python · Typer · Questionary · httpx · Pytest · Allure · Flask · Anthropic SDK · OpenAI SDK · PyYAML
