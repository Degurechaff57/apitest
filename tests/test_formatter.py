import json
import os
import tempfile
import pytest
from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan
from apitest.models.example import TestExample, TestPlan, TestPlanPhase


SAMPLE_EXAMPLES = [
    TestExample(
        id="TC-USER-001",
        area="functional",
        category="happy-path",
        endpoint="POST /api/users",
        description="Create user returns 201",
        preconditions=["valid token"],
        request_headers={"Authorization": "Bearer ${TOKEN}"},
        request_body={"name": "John", "email": "john@test.com"},
        expected_status=201,
        expected_body_contains=["id", "name"],
        max_response_time_ms=2000,
    ),
]

SAMPLE_PLAN = TestPlan(
    title="Test Plan: My API",
    coverage="happy-path",
    areas=["functional"],
    total_examples=1,
    phases=[
        TestPlanPhase(name="Setup", order=1, examples=["TC-USER-001"], description="Setup phase"),
    ],
)


class TestFormatter:
    @pytest.mark.parametrize("fmt", ["json", "yaml"])
    def test_write_and_read_examples(self, fmt):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, f"examples.{fmt}")
            write_examples(SAMPLE_EXAMPLES, filepath, fmt)
            assert os.path.exists(filepath)

            loaded = read_examples(filepath, fmt)
            assert len(loaded) == 1
            assert loaded[0].id == "TC-USER-001"
            assert loaded[0].expected_status == 201

    def test_write_examples_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "examples.json")
            write_examples(SAMPLE_EXAMPLES, filepath, "json")
            with open(filepath) as f:
                data = json.load(f)
            assert data["examples"][0]["id"] == "TC-USER-001"

    @pytest.mark.parametrize("fmt", ["json", "yaml"])
    def test_write_and_read_plan(self, fmt):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, f"plan.{fmt}")
            write_plan(SAMPLE_PLAN, filepath, fmt)
            assert os.path.exists(filepath)

            loaded = read_plan(filepath, fmt)
            assert loaded.title == "Test Plan: My API"
            assert len(loaded.phases) == 1

    def test_write_examples_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "examples.md")
            write_examples(SAMPLE_EXAMPLES, filepath, "md")
            content = open(filepath).read()
            assert "# Test Examples" in content
            assert "TC-USER-001" in content
            assert "POST /api/users" in content

    def test_write_plan_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "plan.md")
            write_plan(SAMPLE_PLAN, filepath, "md")
            content = open(filepath).read()
            assert "# Test Plan: My API" in content
            assert "Setup" in content
