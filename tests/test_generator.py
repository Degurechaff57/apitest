import json
import tempfile
import os
import pytest
from apitest.engine.generator import Generator
from apitest.engine.parser import parse_openapi
from apitest.models.example import TestExample


MINIMAL_SPEC_YAML = """
openapi: "3.0.0"
info:
  title: Petstore
  version: "1.0.0"
paths:
  /api/pets:
    get:
      operationId: listPets
      responses:
        "200":
          description: OK
    post:
      operationId: createPet
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
      responses:
        "201":
          description: Created
"""


class MockLLM:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.calls = []

    def chat(self, system_prompt, user_prompt, temperature=0.3):
        self.calls.append({"system": system_prompt, "user": user_prompt})
        if self.responses:
            return self.responses.pop(0)
        return json.dumps({"examples": []})


class TestGenerator:
    def test_generate_examples_calls_llm(self):
        import yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(MINIMAL_SPEC_YAML)
            spec_path = f.name

        try:
            endpoints = parse_openapi(spec_path)
            llm = MockLLM(responses=[
                json.dumps({
                    "examples": [{
                        "id": "TC-PETS-001",
                        "area": "functional",
                        "category": "happy-path",
                        "endpoint": "GET /api/pets",
                        "description": "List pets returns 200",
                        "preconditions": [],
                        "request": {"headers": {}},
                        "expected": {"status": 200},
                        "depends_on": None,
                        "cleanup": "",
                    }]
                }),
            ])

            gen = Generator(llm)
            examples = gen.generate_examples(endpoints, "smoke", ["functional"])
            assert len(examples) > 0
            called = False
            for call in llm.calls:
                if "/api/pets" in call["user"]:
                    called = True
            assert called, "LLM should receive endpoint context"
        finally:
            os.unlink(spec_path)

    def test_generate_plan_calls_llm_with_examples(self):
        examples = [
            TestExample(
                id="TC-PETS-001", area="functional", category="happy-path",
                endpoint="GET /api/pets", description="List pets",
                expected_status=200,
            ),
        ]

        llm = MockLLM(responses=[
            json.dumps({
                "plan": {
                    "title": "Test Plan: Petstore",
                    "coverage": "smoke",
                    "areas": ["functional"],
                    "total_examples": 1,
                    "phases": [{
                        "name": "Pets",
                        "order": 1,
                        "examples": ["TC-PETS-001"],
                        "description": "Pet operations",
                    }],
                }
            }),
        ])

        gen = Generator(llm)
        plan = gen.generate_plan(examples, "smoke", ["functional"], use_llm=True)
        assert plan.title == "Test Plan: Petstore"
        assert len(plan.phases) == 1
        assert plan.phases[0].examples == ["TC-PETS-001"]
