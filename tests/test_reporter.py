import pytest
from apitest.engine.reporter import Reporter, check_allure_installed


class TestReporter:
    def test_check_allure_installed(self):
        result = check_allure_installed()
        assert isinstance(result, bool)

    def test_report_prints_instructions_when_allure_missing(self, capsys):
        reporter = Reporter(auto_serve=True, results_dir="allure-results")
        if not check_allure_installed():
            reporter.serve()
            captured = capsys.readouterr()
            assert "allure" in captured.out.lower() or "install" in captured.out.lower()
