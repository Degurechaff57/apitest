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


from apitest.areas.functional import FunctionalArea


class TestFunctionalArea:
    def test_name_is_functional(self):
        area = FunctionalArea()
        assert area.name == "functional"

    def test_prompt_context_includes_categories(self):
        area = FunctionalArea()
        ctx = area.get_prompt_context([])
        assert "happy-path" in ctx
        assert "equivalence-class" in ctx
        assert "boundary-value" in ctx
        assert "negative" in ctx
        assert "auth-security" in ctx
        assert "lifecycle" in ctx

    def test_prompt_context_includes_coverage_matrix(self):
        area = FunctionalArea()
        ctx = area.get_prompt_context([])
        assert "smoke" in ctx
        assert "happy-path" in ctx
        assert "full" in ctx

    def test_generate_examples_returns_list(self):
        area = FunctionalArea()

        class MockLLM:
            def chat(self, system_prompt, user_prompt, temperature=0.3):
                import json
                return json.dumps({
                    "examples": [{
                        "id": "TC-USERS-001",
                        "area": "functional",
                        "category": "happy-path",
                        "endpoint": "GET /api/users",
                        "description": "List users returns 200",
                        "preconditions": [],
                        "request": {"headers": {}},
                        "expected": {"status": 200},
                        "depends_on": None,
                        "cleanup": "",
                    }]
                })

        from apitest.models.endpoint import Endpoint
        endpoint = Endpoint(method="GET", path="/api/users")
        examples = area.generate_examples([endpoint], "smoke", MockLLM())
        assert len(examples) == 1
        assert examples[0].id == "TC-USERS-001"

    def test_generate_test_code_returns_string(self):
        area = FunctionalArea()

        class MockLLM:
            def chat(self, system_prompt, user_prompt, temperature=0.3):
                return "def test_example():\n    assert True\n"

        from apitest.models.example import TestExample
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/users", description="test",
            expected_status=200,
        )
        code = area.generate_test_code([example], MockLLM())
        assert "def test_example" in code
