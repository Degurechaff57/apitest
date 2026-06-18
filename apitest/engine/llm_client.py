import random
import time
from abc import ABC, abstractmethod


def _is_retryable(exception: Exception) -> bool:
    """Check if an error is transient and worth retrying."""
    msg = str(exception).lower()
    # HTTP status codes in error message
    retryable_codes = ["429", "500", "502", "503", "504"]
    for code in retryable_codes:
        if code in msg:
            return True
    # Common transient patterns
    retryable_keywords = ["rate limit", "too many requests", "server error",
                          "service unavailable", "timeout", "connection reset",
                          "internal server error", "overloaded"]
    for kw in retryable_keywords:
        if kw in msg:
            return True
    return False


class LLMClient(ABC):
    """Abstract LLM client. Use LLMClient.create() to get the right implementation."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None,
                 thinking_enabled: bool = True):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.thinking_enabled = thinking_enabled

    @abstractmethod
    def _send(self, system_prompt: str, user_prompt: str, temperature: float = 0.3,
              max_tokens: int = 8192) -> str:
        """Raw chat implementation — each provider overrides this."""

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3,
             retries: int = 3, max_tokens: int = 8192) -> str:
        """Send a chat completion with retry on transient errors."""
        last_error = None
        for attempt in range(retries):
            try:
                return self._send(system_prompt, user_prompt, temperature, max_tokens)
            except Exception as e:
                last_error = e
                if attempt < retries - 1 and _is_retryable(e):
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    print(f"  Retry {attempt + 1}/{retries} in {delay:.1f}s ({e})")
                    time.sleep(delay)
                    continue
                raise
        raise last_error  # pragma: no cover — only reached if all retries fail

    def ping(self) -> tuple[bool, str]:
        """Send a minimal request to verify the API key works. Returns (ok, message)."""
        try:
            response = self.chat(
                "You are a connection tester. Always reply with exactly: ok",
                "reply with just the word ok, nothing else",
                temperature=0.0,
                retries=1,  # no retries for ping — fail fast
            )
            if response.strip():
                return True, "Connection successful"
            return False, "Empty response from API"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def create(provider: str, model: str, api_key: str, base_url: str | None = None,
               thinking_enabled: bool = True) -> "LLMClient":
        if provider == "openai":
            return OpenAIClient(model, api_key, thinking_enabled=thinking_enabled)
        elif provider == "anthropic":
            return AnthropicClient(model, api_key, base_url, thinking_enabled=thinking_enabled)
        elif provider == "custom":
            return CustomClient(model, api_key, base_url, thinking_enabled=thinking_enabled)
        else:
            raise ValueError(f"Unknown provider: {provider}")


class OpenAIClient(LLMClient):
    def _send(self, system_prompt: str, user_prompt: str, temperature: float = 0.3,
              max_tokens: int = 8192) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, timeout=120.0, max_retries=0)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(LLMClient):
    def _send(self, system_prompt: str, user_prompt: str, temperature: float = 0.3,
              max_tokens: int = 8192) -> str:
        from anthropic import Anthropic

        client_kwargs = {"timeout": 120.0, "max_retries": 0}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        if self.api_key:
            if self.api_key.startswith("sk-"):
                client_kwargs["auth_token"] = self.api_key
            else:
                client_kwargs["api_key"] = self.api_key

        client = Anthropic(**client_kwargs)
        create_kwargs: dict = {
            "max_tokens": max_tokens,
            "model": self.model,
            "system": [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": temperature,
        }

        # Respect thinking_enabled flag (default: enabled for standard models)
        if not self.thinking_enabled:
            create_kwargs["thinking"] = {"type": "disabled"}

        response = client.messages.create(**create_kwargs)
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return "".join(text_parts)


class CustomClient(LLMClient):
    """OpenAI-compatible endpoint (e.g., self-hosted, proxies)."""
    def _send(self, system_prompt: str, user_prompt: str, temperature: float = 0.3,
              max_tokens: int = 8192) -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=120.0, max_retries=0)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
