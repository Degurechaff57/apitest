import tempfile
import os
import pytest
from apitest.engine.parser import parse_openapi, detect_format


MINIMAL_OPENAPI_YAML = """
openapi: "3.0.0"
info:
  title: Test API
  version: "1.0.0"
paths:
  /api/users:
    get:
      operationId: listUsers
      summary: List all users
      parameters:
        - name: role
          in: query
          schema:
            type: string
            enum: [admin, user]
      responses:
        "200":
          description: OK
      security:
        - bearerAuth: []
    post:
      operationId: createUser
      summary: Create a user
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name, email]
              properties:
                name:
                  type: string
                  minLength: 1
                  maxLength: 100
                email:
                  type: string
                  format: email
                age:
                  type: integer
                  minimum: 0
                  maximum: 150
      responses:
        "201":
          description: Created
        "400":
          description: Bad Request
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
"""


class TestParser:
    def test_detect_openapi_format(self):
        assert detect_format("spec.yaml") == "openapi"
        assert detect_format("spec.json") == "openapi"
        assert detect_format("spec.yml") == "openapi"

    def test_parse_openapi_endpoints(self):
        import yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(MINIMAL_OPENAPI_YAML)
            path = f.name

        try:
            endpoints = parse_openapi(path)
            assert len(endpoints) == 2

            get_users = [e for e in endpoints if e.method == "GET"][0]
            assert get_users.path == "/api/users"
            assert get_users.operation_id == "listUsers"
            assert len(get_users.parameters) == 1
            assert get_users.parameters[0].name == "role"
            assert get_users.parameters[0].enum == ["admin", "user"]
            assert get_users.has_auth is True

            post_users = [e for e in endpoints if e.method == "POST"][0]
            assert post_users.request_body is not None
            assert post_users.request_body.required is True
            assert post_users.responses[0].status_code == 201
        finally:
            os.unlink(path)
