import pytest
from apitest.areas.base import TestArea, AreaRegistry


class FakeLLM:
    def chat(self, system_prompt, user_prompt, temperature=0.3):
        return '{"examples": []}'


class FakeArea(TestArea):
    @property
    def name(self) -> str:
        return "fake"

    def get_prompt_context(self, endpoints):
        return "Fake context"

    def generate_examples(self, endpoints, coverage, llm):
        return []

    def generate_test_code(self, examples, llm):
        return "# no tests"


class TestAreaRegistry:
    def test_register_and_get_area(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        area = registry.get("fake")
        assert area is not None
        assert area.name == "fake"

    def test_get_unknown_area_returns_none(self):
        registry = AreaRegistry()
        assert registry.get("nonexistent") is None

    def test_list_area_names(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        assert "fake" in registry.list_names()

    def test_get_enabled_areas(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        enabled = registry.get_enabled(["fake"])
        assert len(enabled) == 1
        assert enabled[0].name == "fake"

    def test_skip_disabled_areas(self):
        registry = AreaRegistry()
        registry.register(FakeArea())
        enabled = registry.get_enabled(["other"])
        assert len(enabled) == 0
