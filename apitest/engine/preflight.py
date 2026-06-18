import concurrent.futures
import re

import httpx

from apitest.models.example import TestExample


def _resolve_path(path: str) -> str:
    return re.sub(r'\$\{(\w+)\}|\{(\w+)\}', r'1', path)


def _build_request(example: TestExample) -> dict:
    """Build httpx request params from a TestExample, matching runner.py logic."""
    method, raw_path = example.endpoint.split(" ", 1)
    http_method = method.lower()
    path = _resolve_path(raw_path)

    headers = {}
    for k, v in example.request_headers.items():
        headers[k] = re.sub(r'\$\{\w+\}', 'mock-token', v)
    if http_method in ("post", "put", "patch") and example.request_body:
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

    body = None
    body_is_raw = False
    if isinstance(example.request_body, dict):
        body = {}
        for k, v in example.request_body.items():
            body[k] = re.sub(r'\$\{\w+\}', 'test_value', v) if isinstance(v, str) else v
    elif isinstance(example.request_body, str):
        # Raw string body (malformed JSON negative test)
        body = example.request_body
        body_is_raw = True

    return {
        "method": http_method,
        "path": path,
        "headers": headers,
        "body": body,
        "body_is_raw": body_is_raw,
    }


class PreflightValidator:
    """Runs examples against a live server and corrects expected_status from reality."""

    def __init__(self, base_url: str, max_workers: int = 5):
        self.base_url = base_url.rstrip("/")
        self.max_workers = max_workers

    def validate(self, examples: list[TestExample]) -> list[TestExample]:
        """Run all examples against the server, correcting expected_status."""
        independent = [e for e in examples if not e.depends_on]
        dependent = [e for e in examples if e.depends_on]

        corrected = 0
        skipped = 0

        with httpx.Client(base_url=self.base_url, timeout=10.0) as client:
            # Run independent examples in parallel
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.max_workers, max(1, len(independent)))
            ) as executor:
                futures = {executor.submit(self._check, client, e): e for e in independent}
                for future in concurrent.futures.as_completed(futures):
                    ex = futures[future]
                    try:
                        if future.result():
                            corrected += 1
                    except Exception:
                        skipped += 1

            # Run dependent examples sequentially
            for ex in dependent:
                try:
                    if self._check(client, ex):
                        corrected += 1
                except Exception:
                    skipped += 1

        if corrected:
            print(f"  Preflight: corrected {corrected} expected status codes "
                  f"({skipped} skipped/{len(examples)} total)")
        return examples

    def _check(self, client: httpx.Client, example: TestExample) -> bool:
        """Send one example's request and correct expected_status if needed."""
        try:
            req = _build_request(example)
        except Exception:
            return False

        method = req["method"]
        path = req["path"]
        headers = req["headers"]
        body = req["body"]
        body_is_raw = req.get("body_is_raw", False)

        try:
            if method in ("get", "head", "options"):
                res = client.request(method.upper(), path, headers=headers)
            elif method == "delete":
                if body:
                    kwargs = {"headers": headers}
                    if body_is_raw:
                        kwargs["content"] = body
                    else:
                        kwargs["json"] = body
                    res = client.request("DELETE", path, **kwargs)
                else:
                    res = client.request("DELETE", path, headers=headers)
            else:
                if body:
                    kwargs = {"headers": headers}
                    if body_is_raw:
                        kwargs["content"] = body
                    else:
                        kwargs["json"] = body
                    res = client.request(method.upper(), path, **kwargs)
                else:
                    res = client.request(method.upper(), path, headers=headers)
        except Exception:
            return False

        actual_status = res.status_code
        # Retry 500s — mock server can flake under concurrent load
        if actual_status == 500:
            try:
                if method in ("get", "head", "options"):
                    res2 = client.request(method.upper(), path, headers=headers)
                elif body:
                    kwargs = {"headers": headers}
                    if body_is_raw:
                        kwargs["content"] = body
                    else:
                        kwargs["json"] = body
                    res2 = client.request(method.upper(), path, **kwargs)
                else:
                    res2 = client.request(method.upper(), path, headers=headers)
                if res2.status_code != 500:
                    actual_status = res2.status_code
            except Exception:
                pass
        # Never let a 500 override expected_status — 500 is always a server bug
        if actual_status == 500:
            return False

        if example.expected_status != actual_status:
            example.expected_status = actual_status
            if actual_status >= 400:
                example.expected_body_contains = []
            return True
        return False
