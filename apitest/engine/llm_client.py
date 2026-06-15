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
