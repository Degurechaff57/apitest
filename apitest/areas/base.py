from abc import ABC, abstractmethod


class TestArea(ABC):
    """Base class for a testing business area.

    Each area handles one testing domain (functional, security, performance, etc.)
    and knows how to generate examples and test code for that domain.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique area identifier, e.g. 'functional', 'security'."""

    @abstractmethod
    def get_prompt_context(self, endpoints: list) -> str:
        """Return area-specific context injected into the LLM system prompt."""

    @abstractmethod
    def generate_examples(self, endpoints: list, coverage: str, llm) -> list:
        """Generate test examples for this area using the LLM."""

    @abstractmethod
    def generate_test_code(self, examples: list, llm) -> str:
        """Generate pytest code for examples in this area. Returns file content string."""


class AreaRegistry:
    """Registry of available test areas. Areas are registered at import time."""

    def __init__(self):
        self._areas: dict[str, TestArea] = {}

    def register(self, area: TestArea) -> None:
        self._areas[area.name] = area

    def get(self, name: str) -> TestArea | None:
        return self._areas.get(name)

    def list_names(self) -> list[str]:
        return list(self._areas.keys())

    def get_enabled(self, area_names: list[str]) -> list[TestArea]:
        """Return registered areas whose names are in area_names, preserving order."""
        return [self._areas[n] for n in area_names if n in self._areas]


# Global registry — areas register themselves on import
registry = AreaRegistry()
