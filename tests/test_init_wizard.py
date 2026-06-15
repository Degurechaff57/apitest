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
