# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dev environment
uv pip install -e ".[dev]"

# Run the CLI (during development)
python -m apitest.cli.main <command> ...

# Run full pipeline on a spec
python -m apitest.cli.main go specs/api.yaml --mode mock

# Run only project-level tests (not generated apitest_tests/)
python -m pytest tests/ -v

# Run a single project test
python -m pytest tests/test_something.py::test_name -v

# Run the CLI's own tests
python -m pytest apitest_tests/ -v
```

Requirements: Python 3.10+, Allure CLI (`brew install allure` on macOS). Set `ANTHROPIC_API_KEY` env var for the LLM provider.

## Architecture

This is an AI-powered API test automation CLI: it reads an API spec (OpenAPI YAML/JSON or markdown), uses an LLM to generate test examples, produces a test plan, executes tests against a mock or real server, and serves an Allure HTML report.

**Entry point:** `apitest/cli/main.py` — a Typer app with 8 commands: `init`, `test`, `examples`, `plan`, `run`, `go`, `report`, `cache-clear`. The `go` command runs the full end-to-end pipeline (examples → preflight → plan → run → report).

### Pipeline (the heart of the system)

```
API Doc → [parser.py] → Endpoints → [LLM/Generator] → Examples → [SchemaCorrector] → [PreflightValidator] → [Formatter] → [TestRunner] → Allure Report
```

1. **`engine/parser.py`** — Parses OpenAPI 3.x / Swagger 2.0 specs into `Endpoint` dataclass objects. For markdown docs, returns raw text for LLM processing.

2. **`engine/generator.py`** — Coordinates example generation. Two modes:
   - **LLM mode** (`--fast` not set): delegates to registered `TestArea` implementations (currently only `FunctionalArea`). For specs with >15 endpoints, splits into chunks and fans out parallel LLM calls.
   - **Schema-only mode** (`--fast`): generates examples deterministically from parsed schema with `generate_fake_value()` — no LLM, near-instant.
   - Also generates test plans — deterministic grouping by resource by default, or LLM-driven with `--llm-plan`.

3. **`engine/llm_client.py`** — Abstract `LLMClient` with three concrete implementations: `AnthropicClient`, `OpenAIClient`, `CustomClient` (OpenAI-compatible endpoint). Built-in retry with exponential backoff for transient errors (429, 5xx, rate limit, etc.). The `thinking_enabled` flag controls Anthropic extended thinking.

4. **`engine/schema_corrector.py`** — Post-LLM correction pass: cross-references LLM-generated examples against the parsed OpenAPI schema, fixing request body field names, expected status codes (matches first 2xx from spec), and auth headers.

5. **`engine/preflight.py`** — Runs every generated example against the running mock server, correcting `expected_status` from actual responses. Catches LLM hallucination errors before test execution. Independent examples run in parallel; dependent examples run sequentially.

6. **`engine/runner.py`** — Generates pytest test files (one per resource) from examples, writes a `conftest.py` with `client` and `auth_token` fixtures, then runs pytest with `--alluredir`. Cleans stale test files before each run.

7. **`engine/reporter.py`** — Runs `allure generate`, serves the HTML report via Python `http.server` in a daemon thread (no Java process leak).

### Mock server

**`engine/mock_server.py`** — Flask-based mock with in-memory SQLite. Schema-aware: it reads OpenAPI response schemas and generates realistic fake response data matching the schema structure. Supports CRUD lifecycle (POST stores in DB, GET retrieves, PUT/PATCH updates, DELETE removes). Runs in a background daemon thread on a random free port.

### Pluggable test areas

**`areas/base.py`** — `TestArea` ABC + `AreaRegistry`. Areas register themselves on import and are discovered by name. Currently only `FunctionalArea` exists.

**`areas/functional.py`** — The `FunctionalArea` implements functional testing across 6 categories (happy-path, equivalence-class, boundary-value, negative, auth-security, lifecycle) at 3 coverage levels (smoke, happy-path, full). Contains the system prompt injected into LLM calls, and handles parsing LLM JSON responses (including recovery from truncated JSON caused by max_tokens limits).

### Data models

- **`models/endpoint.py`** — `Endpoint`, `Parameter`, `RequestBody`, `Response` dataclasses. Parsed from OpenAPI specs.
- **`models/example.py`** — `TestExample`, `TestPlan`, `TestPlanPhase` dataclasses. Also defines `CATEGORIES` and `COVERAGE_LEVELS` dict.

### Configuration

**`config.py`** — Loads `.apitest.yaml` with `${ENV_VAR}` substitution. Falls back to provider-specific env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`).

### Caching

**`engine/cache.py`** — File-based cache in `.apitest_cache/` next to the spec file. Cache key is SHA-256 of (spec path, coverage, areas). Can yield ~100x speedup on re-runs.

### Output formats

**`engine/formatter.py`** — Supports JSON, YAML, Markdown, and XLSX for both examples and plans.

### Key design decisions

- The test runner generates actual `.py` files in `apitest_tests/` (gitignored) and runs pytest as a subprocess — not via pytest API. This isolates generated test code from the tool's own code.
- The preflight validator runs examples against the live mock server to correct LLM hallucinations before test execution — this is the first correctness guard.
- The schema corrector is the second guard, fixing LLM-generated field names and status codes against the parsed spec.
- The `Generator` class can work with or without an LLM instance; many methods have dual code paths for deterministic vs LLM generation.
- Chunking strategy: >15 endpoints triggers parallel chunked generation (capped at 8 concurrent calls). For markdown docs, splits on `##` section boundaries with adaptive chunk sizes based on coverage level.
