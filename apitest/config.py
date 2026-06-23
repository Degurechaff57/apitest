import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    # LLM
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_thinking_enabled: bool = True
    llm_cache_enabled: bool = True

    # Input
    api_doc: str = "specs/openapi.yaml"

    # Output
    examples_format: str = "json"
    examples_dir: str = "tests/examples"
    plan_format: str = "md"
    plan_path: str = "test_plan.md"

    # Execution
    base_url: str = "http://localhost:8080"
    coverage: str = "happy-path"
    execution_mode: str = "mock"
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


_DEFAULT_ENV_VARS = {
    "anthropic": ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
    "openai": ["OPENAI_API_KEY"],
}


def load_config(path: str | None = None) -> Config:
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
    api_key = _resolve_env_vars(api_key)
    provider = llm.get("provider", "anthropic")

    # Fallback: check provider-specific env vars if no key from config
    if not api_key:
        for env_var in _DEFAULT_ENV_VARS.get(provider, []):
            api_key = os.environ.get(env_var, "")
            if api_key:
                break

    # Fallback: check provider-specific base URL from env
    base_url = llm.get("base_url")
    if not base_url and provider == "anthropic":
        base_url = os.environ.get("ANTHROPIC_BASE_URL")

    model = llm.get("model", "")
    if not model and provider == "anthropic":
        model = os.environ.get("ANTHROPIC_MODEL", "")

    return Config(
        llm_provider=provider,
        llm_model=model or "claude-sonnet-4-6",
        llm_api_key=api_key,
        llm_base_url=base_url,
        llm_thinking_enabled=llm.get("thinking_enabled", False),
        llm_cache_enabled=llm.get("cache_enabled", True),
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
