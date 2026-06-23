from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
import threading
import webbrowser
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


def _notify(title: str, message: str) -> None:
    """Send a desktop notification. Best-effort — failures are silent."""
    try:
        if platform.system() == "Darwin":
            # macOS: escape double quotes in message for osascript
            safe_title = title.replace('"', "'")
            safe_msg = message.replace('"', "'")
            subprocess.run([
                "osascript", "-e",
                f'display notification "{safe_msg}" with title "{safe_title}"',
            ], capture_output=True, timeout=3)
        elif platform.system() == "Linux":
            subprocess.run(
                ["notify-send", title, message],
                capture_output=True, timeout=3,
            )
        elif platform.system() == "Windows":
            # Windows toast notification via PowerShell
            subprocess.run([
                "powershell", "-Command",
                f'[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications]'
                f'; echo "notification suppressed"',
            ], capture_output=True, timeout=3)
    except Exception:
        pass  # notification is best-effort, never block the pipeline


class Reporter:
    """Generate and serve Allure reports from test results."""

    def __init__(self, auto_serve: bool = True, results_dir: str = "allure-results"):
        self.auto_serve = auto_serve
        self.results_dir = results_dir
        self.report_dir = "allure-report"
        self._server: http.server.HTTPServer | None = None
        self._port: int | None = None

    def serve(self, notify: bool = True) -> str | None:
        """Generate and serve the Allure report. Returns the report URL if served.

        Set ``notify=True`` to fire a desktop notification and auto-open the browser.
        """
        if not check_allure_installed():
            self._print_install_instructions()
            return None

        results_path = Path(self.results_dir)
        if not results_path.exists() or not list(results_path.glob("*.json")):
            print(f"No Allure results found in {self.results_dir}/")
            return None

        subprocess.run(
            ["allure", "generate", self.results_dir, "-o", self.report_dir, "--clean"],
            check=False,
        )

        report_index = Path(self.report_dir) / "index.html"
        if not report_index.exists():
            print("Report generation failed. Check allure-results for raw data.")
            return None

        url = None
        if self.auto_serve:
            url = self._serve_http()

        if notify:
            # Summarize results for notification
            passed, failed = self._count_results()
            if failed:
                _notify("apitest", f"Tests complete: {passed} passed, {failed} failed")
            else:
                _notify("apitest", f"All {passed} tests passed")

            if url:
                print(f"Opening report in browser: {url}")
                webbrowser.open(url)

        return url

    def _serve_http(self) -> str:
        """Serve allure-report/ via Python HTTP server in a daemon thread.

        No Java process — server dies with the CLI process. Socket is properly
        released on interpreter exit via daemon thread + SO_REUSEADDR.
        """
        import http.server
        import os

        report_dir = Path(self.report_dir).resolve()
        self._port = _get_free_port()

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(report_dir), **kwargs)

            def log_message(self, fmt, *args):
                pass  # suppress access logs

        self._server = http.server.HTTPServer(("127.0.0.1", self._port), Handler)
        # Allow immediate port reuse when the process exits
        self._server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        url = f"http://127.0.0.1:{self._port}"
        print(f"Allure report: {url} (auto-closes when CLI exits)")
        return url

    def stop(self) -> None:
        """Explicitly shut down the HTTP server. Safe to call multiple times."""
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None
            self._port = None

    def __del__(self) -> None:
        """Last-resort cleanup. The daemon thread approach means this is rarely
        needed, but it guards against edge cases where the Reporter is garbage-
        collected before process exit."""
        self.stop()

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

    def _count_results(self) -> tuple[int, int]:
        """Count passed/failed from Allure result files."""
        results_path = Path(self.results_dir)
        passed, failed = 0, 0
        if not results_path.exists():
            return passed, failed
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
        return passed, failed

    def _print_summary(self) -> None:
        passed, failed = self._count_results()
        print(f"Results: {passed} passed, {failed} failed")
