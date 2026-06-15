import pytest
from typer.testing import CliRunner
from apitest.cli.main import app


runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "examples" in result.stdout
        assert "plan" in result.stdout
        assert "run" in result.stdout
        assert "go" in result.stdout
        assert "report" in result.stdout
        assert "init" in result.stdout

    def test_report_command_exists(self):
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_init_command_exists(self):
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0

    def test_examples_command_requires_api_doc(self):
        result = runner.invoke(app, ["examples"])
        assert "Usage" in result.stdout or "Missing" in result.stdout or result.exit_code != 0

    def test_version(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "apitest" in result.stdout
