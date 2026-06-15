import pytest
from apitest.engine.fake_data import generate_fake_value


class TestFakeData:
    def test_generates_phone_from_property_name(self):
        val = generate_fake_value("phone", "string")
        assert val.startswith("138")
        assert len(val) == 11

    def test_generates_email_from_format(self):
        val = generate_fake_value("email", "string", fmt="email")
        assert "@" in val
        assert ".com" in val

    def test_generates_integer_in_range(self):
        val = generate_fake_value("age", "integer", minimum=0, maximum=150)
        assert isinstance(val, int)
        assert 0 <= val <= 150

    def test_generates_enum_value(self):
        val = generate_fake_value("role", "string", enum=["admin", "user", "guest"])
        assert val in ["admin", "user", "guest"]

    def test_generates_boolean(self):
        val = generate_fake_value("active", "boolean")
        assert isinstance(val, bool)

    def test_generates_code_from_name(self):
        val = generate_fake_value("code", "string")
        assert val == "123456"
