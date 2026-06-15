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
            return AnthropicClient(model, api_key, base_url)
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

        client_kwargs = {}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        if self.api_key:
            # sk-* tokens use bearer auth, others use x-api-key
            if self.api_key.startswith("sk-"):
                client_kwargs["auth_token"] = self.api_key
            else:
                client_kwargs["api_key"] = self.api_key

        client = Anthropic(**client_kwargs)
        response = client.messages.create(
            max_tokens=8192,
            model=self.model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        # Collect text from TextBlock content (skip ThinkingBlock from DeepSeek)
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "".join(text_parts)


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
