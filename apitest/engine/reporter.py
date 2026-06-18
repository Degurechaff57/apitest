import json
import socket
import subprocess
import sys
import threading
from pathlib import Path


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


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
        self._server = None

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
                self._serve_http()
            else:
                print("Report generation failed. Check allure-results for raw data.")

    def _serve_http(self) -> None:
        """Serve allure-report/ via Python HTTP server in a daemon thread.
        No Java process left behind — server dies with the CLI process."""
        import http.server
        import os

        report_dir = Path(self.report_dir).resolve()
        port = _get_free_port()

        # Change to report dir so SimpleHTTPRequestHandler serves it
        original_dir = os.getcwd()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(report_dir), **kwargs)

            def log_message(self, fmt, *args):
                pass  # suppress access logs

        self._server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        print(f"Allure report: http://127.0.0.1:{port} (auto-closes when CLI exits)")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None

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
