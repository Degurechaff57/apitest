import os
import tempfile
import pytest
from apitest.engine.runner import (
    generate_pytest_file,
    write_conftest,
)
from apitest.models.example import TestExample


class TestCodeGeneration:
    def test_generate_pytest_file_content(self):
        examples = [
            TestExample(
                id="TC-USERS-001",
                area="functional",
                category="happy-path",
                endpoint="GET /api/users",
                description="List users returns 200",
                preconditions=["valid token"],
                request_headers={"Authorization": "Bearer ${TOKEN}"},
                expected_status=200,
                expected_body_contains=["id", "name"],
                max_response_time_ms=2000,
            ),
        ]

        code = generate_pytest_file("users", examples, "http://localhost:8080")
        assert "class TestUsers" in code
        assert "def test_tc_users_001" in code
        assert "allure.feature" in code
        assert "allure.story" in code
        assert "client.get" in code
        assert "assert res.status_code == 200" in code
        assert "elapsed.total_seconds()" in code

    def test_write_conftest_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            write_conftest(tmpdir, "http://example.com")
            conftest_path = os.path.join(tmpdir, "conftest.py")
            assert os.path.exists(conftest_path)
            content = open(conftest_path).read()
            assert "http://example.com" in content
            assert "def client" in content
            assert "def auth_token" in content
