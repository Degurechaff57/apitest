import pytest
from apitest.engine.schema_corrector import SchemaCorrector, correct_example
from apitest.models.endpoint import Endpoint, Parameter, RequestBody, Response
from apitest.models.example import TestExample


LOGIN_ENDPOINT = Endpoint(
    method="POST",
    path="/api/auth/login",
    operation_id="login",
    request_body=RequestBody(content_type="application/json", required=True),
    parameters=[
        Parameter(name="phone", location="body", schema_type="string",
                  required=True, min_length=11, max_length=11),
        Parameter(name="code", location="body", schema_type="string",
                  required=True, min_length=6, max_length=6),
    ],
    responses=[Response(status_code=200), Response(status_code=401)],
)

GET_PROFILE = Endpoint(
    method="GET", path="/api/user/profile",
    parameters=[
        Parameter(name="userId", location="query", schema_type="integer", required=False),
    ],
    responses=[Response(status_code=200), Response(status_code=404)],
    security=[{"bearerAuth": []}],
)

POST_CREATE = Endpoint(
    method="POST", path="/api/items",
    responses=[Response(status_code=201), Response(status_code=400)],
)


class TestSchemaCorrector:
    def test_corrects_login_request_body(self):
        # LLM hallucinated wrong field names
        example = TestExample(
            id="TC-LOGIN-001", area="functional", category="happy-path",
            endpoint="POST /api/auth/login",
            description="Login with valid credentials",
            request_body={"username": "testuser", "password": "test123"},
            expected_status=201,
            expected_body_contains=["token", "userId"],
        )
        corrected = correct_example(example, LOGIN_ENDPOINT)
        assert "phone" in corrected.request_body
        assert "code" in corrected.request_body
        assert "username" not in corrected.request_body
        assert "password" not in corrected.request_body
        assert corrected.expected_status == 200

    def test_corrects_status_code_for_post(self):
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="POST /api/items", description="Create item",
            expected_status=200,
        )
        corrected = correct_example(example, POST_CREATE)
        assert corrected.expected_status == 201

    def test_adds_auth_header_when_endpoint_requires_it(self):
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/user/profile", description="Get profile",
            expected_status=200,
        )
        corrected = correct_example(example, GET_PROFILE)
        assert "Authorization" in corrected.request_headers

    def test_preserves_existing_auth_header(self):
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/user/profile", description="Get profile",
            request_headers={"Authorization": "Bearer ${TOKEN}"},
            expected_status=200,
        )
        corrected = correct_example(example, GET_PROFILE)
        assert corrected.request_headers["Authorization"] == "Bearer ${TOKEN}"

    def test_does_not_add_auth_for_public_endpoint(self):
        public_ep = Endpoint(method="GET", path="/api/search", responses=[Response(status_code=200)])
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/search", description="Search", expected_status=200,
        )
        corrected = correct_example(example, public_ep)
        assert "Authorization" not in corrected.request_headers

    def test_corrector_batch_corrects_multiple_examples(self):
        corrector = SchemaCorrector()
        examples = [
            TestExample(id="TC-001", area="functional", category="happy-path",
                        endpoint="POST /api/items", description="Create", expected_status=200),
            TestExample(id="TC-002", area="functional", category="happy-path",
                        endpoint="GET /api/user/profile", description="Get", expected_status=200),
        ]
        endpoints = [POST_CREATE, GET_PROFILE]
        corrected = corrector.correct(examples, endpoints)
        assert corrected[0].expected_status == 201
        assert "Authorization" in corrected[1].request_headers

    def test_fuzzy_match_path_params(self):
        ep = Endpoint(method="GET", path="/api/notes/{noteId}", responses=[Response(status_code=200)])
        example = TestExample(
            id="TC-001", area="functional", category="happy-path",
            endpoint="GET /api/notes/${noteId}", description="Get note",
            expected_status=200,
        )
        corrected = correct_example(example, ep)
        assert corrected.expected_status == 200
