import json
import subprocess
import sys
import webbrowser
from pathlib import Path


def check_allure_installed() -> bool:
    try:
        subprocess.run(["allure", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class Reporter:
    """Generate and serve Allure reports from test results."""

    def __init__(self, auto_serve: bool = True, results_dir: str = "allure-results"):
        self.auto_serve = auto_serve
        self.results_dir = results_dir
        self.report_dir = "allure-report"

    def serve(self) -> None:
        if not check_allure_installed():
            self._print_install_instructions()
            return

        results_path = Path(self.results_dir)
        if not results_path.exists() or not list(results_path.glob("*.json")):
            print(f"No Allure results found in {self.results_dir}/")
            return

        subprocess.run(
            ["allure", "generate", self.results_dir, "-o", self.report_dir, "--clean"],
            check=False,
        )

        if self.auto_serve:
            report_index = Path(self.report_dir) / "index.html"
            if report_index.exists():
                webbrowser.open(f"file://{report_index.absolute()}")
                print(f"Allure report opened: {report_index}")
            else:
                print("Report generation failed. Check allure-results for raw data.")

    def _print_install_instructions(self) -> None:
        print("Allure CLI not found. Install it to generate HTML reports:")
        if sys.platform == "darwin":
            print("  brew install allure")
        elif sys.platform == "linux":
            print("  sudo apt install allure")
        else:
            print("  Download from: https://github.com/allure-framework/allure2/releases")
        print()
        print(f"Raw Allure results available in {self.results_dir}/")
        self._print_summary()

    def _print_summary(self) -> None:
        results_path = Path(self.results_dir)
        if not results_path.exists():
            return
        passed, failed = 0, 0
        for f in results_path.glob("*-result.json"):
            try:
                data = json.loads(f.read_text())
                status = data.get("status", "unknown")
                if status == "passed":
                    passed += 1
                elif status in ("failed", "broken"):
                    failed += 1
            except (json.JSONDecodeError, KeyError):
                pass
        print(f"Results: {passed} passed, {failed} failed")
