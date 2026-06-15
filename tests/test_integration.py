import os
import tempfile
import pytest
from apitest.engine.mock_server import create_mock_app, MockServer
from apitest.engine.parser import parse_openapi
from apitest.engine.formatter import write_examples, read_examples, write_plan, read_plan
from apitest.models.example import TestExample, TestPlan, TestPlanPhase


PETSTORE_YAML = """
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
                  minLength: 1
                  maxLength: 50
                species:
                  type: string
                  enum: [cat, dog, bird]
      responses:
        "201":
          description: Created
        "400":
          description: Bad Request
  /api/pets/{petId}:
    get:
      operationId: getPet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: OK
        "404":
          description: Not Found
    delete:
      operationId: deletePet
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "204":
          description: No Content
"""


class TestIntegration:
    def test_parser_and_mock_server_e2e(self):
        """Full end-to-end: parse spec, start mock, run CRUD operations."""
        import yaml
        import httpx

        with tempfile.TemporaryDirectory() as tmpdir:
            spec_path = os.path.join(tmpdir, "petstore.yaml")
            with open(spec_path, "w") as f:
                f.write(PETSTORE_YAML)

            endpoints = parse_openapi(spec_path)
            assert len(endpoints) == 4  # GET list, POST, GET by id, DELETE

            with open(spec_path) as f:
                spec = yaml.safe_load(f)

            mock_app = create_mock_app(spec)
            mock_server = MockServer(mock_app, port=0)
            mock_server.start()

            try:
                # POST a pet
                resp = httpx.post(f"{mock_server.url}/api/pets", json={"name": "Rex", "species": "dog"})
                assert resp.status_code == 201
                pet_data = resp.json()
                assert pet_data["name"] == "Rex"
                pet_id = pet_data["id"]

                # GET list
                resp = httpx.get(f"{mock_server.url}/api/pets")
                assert resp.status_code == 200
                pets = resp.json()
                assert len(pets) == 1

                # GET by id
                resp = httpx.get(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 200

                # DELETE
                resp = httpx.delete(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 204

                # GET deleted — mock generates fake data for missing resources
                resp = httpx.get(f"{mock_server.url}/api/pets/{pet_id}")
                assert resp.status_code == 200

                # POST missing required field
                resp = httpx.post(f"{mock_server.url}/api/pets", json={"species": "cat"})
                assert resp.status_code == 400
            finally:
                mock_server.stop()

    def test_examples_and_plan_roundtrip(self):
        """Test write/read roundtrip for examples and plans."""
        examples = [
            TestExample(
                id="TC-PETS-001", area="functional", category="happy-path",
                endpoint="GET /api/pets", description="List pets returns 200",
                expected_status=200,
            ),
            TestExample(
                id="TC-PETS-002", area="functional", category="happy-path",
                endpoint="POST /api/pets", description="Create pet returns 201",
                expected_status=201, request_body={"name": "Fluffy"},
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            # JSON roundtrip
            json_path = os.path.join(tmpdir, "examples.json")
            write_examples(examples, json_path, "json")
            loaded = read_examples(json_path, "json")
            assert len(loaded) == 2
            assert loaded[0].id == "TC-PETS-001"

            # Plan roundtrip
            plan = TestPlan(
                title="Test Plan: Petstore", coverage="smoke", areas=["functional"],
                total_examples=2,
                phases=[TestPlanPhase(name="Pets", order=1, examples=["TC-PETS-001", "TC-PETS-002"])],
            )
            plan_path = os.path.join(tmpdir, "plan.json")
            write_plan(plan, plan_path, "json")
            loaded_plan = read_plan(plan_path, "json")
            assert loaded_plan.title == "Test Plan: Petstore"
            assert len(loaded_plan.phases) == 1

    def test_runner_generates_valid_pytest_code(self):
        """Test that the runner generates compilable pytest code."""
        from apitest.engine.runner import generate_pytest_file

        examples = [
            TestExample(
                id="TC-PETS-001", area="functional", category="happy-path",
                endpoint="GET /api/pets", description="List pets returns 200",
                expected_status=200, expected_body_contains=["id"],
                max_response_time_ms=2000,
            ),
        ]

        code = generate_pytest_file("pets", examples, "http://localhost:8080")
        # Verify it's valid Python by compiling
        compile(code, "test_pets.py", "exec")
        assert "class TestPets" in code
        assert "allure" in code
        assert "client.get" in code
