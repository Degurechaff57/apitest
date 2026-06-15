import os
import tempfile
import pytest
from apitest.config import Config, load_config


class TestConfig:
    def test_loads_default_values_with_no_file(self):
        # Save and clear env vars that override defaults
        saved = {}
        for var in ("ANTHROPIC_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                     "ANTHROPIC_BASE_URL", "OPENAI_API_KEY"):
            saved[var] = os.environ.pop(var, None)

        try:
            cfg = load_config()
            assert cfg.llm_provider == "anthropic"
            assert cfg.llm_model == "claude-sonnet-4-6"
            assert cfg.examples_format == "json"
            assert cfg.plan_format == "md"
            assert cfg.coverage == "happy-path"
            assert cfg.execution_mode == "mock"
        finally:
            for var, val in saved.items():
                if val is not None:
                    os.environ[var] = val

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
