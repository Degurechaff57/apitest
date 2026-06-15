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
