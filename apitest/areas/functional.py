import json
import re

from apitest.areas.base import TestArea, registry
from apitest.models.example import TestExample, CATEGORIES, COVERAGE_LEVELS


FUNCTIONAL_SYSTEM_PROMPT = """You are a senior API QA engineer specializing in functional testing.
Generate test examples and pytest code from API endpoint specifications.

## Example Output (follow this EXACT format and style)

Here is a correct example for a login endpoint:

```json
{
  "id": "TC-LOGIN-001",
  "area": "functional",
  "category": "happy-path",
  "endpoint": "POST /api/auth/login",
  "description": "Login with valid phone and code returns token",
  "preconditions": [],
  "request": {
    "headers": {"Content-Type": "application/json"},
    "body": {"phone": "13800138000", "code": "123456"}
  },
  "expected": {
    "status": 200,
    "body_contains": ["data"],
    "max_response_time_ms": 2000
  },
  "depends_on": null,
  "cleanup": ""
}
```

KEY RULES demonstrated by this example:
1. request.body uses the EXACT field names from the endpoint Parameters section
2. expected.status matches the FIRST success response code from the spec
3. body_contains lists top-level response fields (most APIs wrap in 'data')
4. Use ${TOKEN} for dynamic auth values, real data for everything else

## Test Categories
1. **happy-path**: One success case per endpoint using valid inputs
2. **equivalence-class**: Partition inputs into valid/invalid classes, test one per class
3. **boundary-value**: Test min-1, min, min+1, max-1, max, max+1 for every numeric/length constraint
4. **negative**: Missing required fields, wrong types, malformed JSON, invalid enum values
5. **auth-security**: No token, wrong role/scope for secured endpoints
6. **lifecycle**: Chain CRUD operations: Create → Read → Update → Read → Delete → Read(404)

## Coverage Matrix
- smoke: happy-path only (~1 example per endpoint)
- happy-path: happy-path + equivalence-class + negative (~3-5 per endpoint)
- full: all 6 categories (~6-10 per endpoint)

## Design Rules
- Every example MUST have a unique ID: TC-<RESOURCE>-<NNN>
- Use ${VAR} syntax for dynamic values (tokens, IDs from previous steps)
- dependencies MUST follow the Operation Dependency Graph
- Cleanup MUST leave no side effects
- Group by category first, then by endpoint
- Never multiply scenarios × verifications — total = scenarios + verifications
"""


class FunctionalArea(TestArea):
    @property
    def name(self) -> str:
        return "functional"

    def get_prompt_context(self, endpoints: list) -> str:
        parts = [
            "## Test Categories",
            "- happy-path",
            "- equivalence-class",
            "- boundary-value",
            "- negative",
            "- auth-security",
            "- lifecycle",
            "",
            "## Coverage Matrix",
            "- smoke: happy-path only (~1 example per endpoint)",
            "- happy-path: happy-path + equivalence-class + negative (~3-5 per endpoint)",
            "- full: all 6 categories (~6-10 per endpoint)",
        ]

        if endpoints:
            endpoint_list = []
            for ep in endpoints:
                params_desc = []
                for p in ep.parameters:
                    constraints = []
                    if p.enum:
                        constraints.append(f"enum={p.enum}")
                    if p.minimum is not None:
                        constraints.append(f"min={p.minimum}")
                    if p.maximum is not None:
                        constraints.append(f"max={p.maximum}")
                    if p.min_length is not None:
                        constraints.append(f"minLength={p.min_length}")
                    if p.max_length is not None:
                        constraints.append(f"maxLength={p.max_length}")
                    constraint_str = f" [{', '.join(constraints)}]" if constraints else ""
                    params_desc.append(
                        f"    {p.name} ({p.schema_type}, {'required' if p.required else 'optional'})"
                        f"{constraint_str}: {p.description}"
                    )

                endpoint_list.append(
                    f"{ep.method} {ep.path}"
                    + (f" -- {ep.summary}" if ep.summary else "")
                    + (f"\n  Auth: required" if ep.has_auth else "")
                    + (f"\n  Request body required" if ep.request_body and ep.request_body.required else "")
                    + ("\n  Parameters:\n" + "\n".join(params_desc) if params_desc else "")
                )

            parts.append("")
            parts.append("## Endpoints")
            parts.append("")
            parts.append("\n\n".join(endpoint_list))

        return "\n".join(parts)

    def generate_examples(self, endpoints, coverage, llm) -> list:
        categories = COVERAGE_LEVELS.get(coverage, COVERAGE_LEVELS["happy-path"])
        context = self.get_prompt_context(endpoints)

        user_prompt = f"""Generate test examples for the following API endpoints at coverage level: {coverage}.
Include these categories: {', '.join(categories)}.
CRITICAL: For request bodies, use the EXACT field names listed in each endpoint's "Parameters" section. Do NOT guess or substitute field names. If the spec says "phone" and "code", use "phone" and "code" — NOT "username" and "password".
CRITICAL: For expected status codes, use the FIRST success response listed in the spec. If the spec shows "200", use 200. If it shows "201", use 201. Do NOT guess.

## Endpoints
{context}

## Output Format
Return valid JSON with this structure:
{{"examples": [{{example objects}}]}}

Each example object:
{{
  "id": "TC-<RESOURCE>-<NNN>",
  "area": "functional",
  "category": "one of: {', '.join(categories)}",
  "endpoint": "METHOD /path",
  "description": "what this tests",
  "preconditions": ["list of prerequisites"],
  "request": {{"headers": {{}}, "body": {{}}}},
  "expected": {{"status": 200, "body_contains": ["field"], "schema": "SchemaName", "max_response_time_ms": 2000}},
  "depends_on": null,
  "cleanup": ""
}}
"""

        max_tok = _estimate_max_tokens(len(endpoints), coverage)
        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt, max_tokens=max_tok)
        return self._parse_examples(response)

    def generate_examples_from_text(self, doc_text: str, coverage: str, llm) -> list:
        """Generate test examples directly from raw API doc text (markdown, txt, etc.)."""
        categories = COVERAGE_LEVELS.get(coverage, COVERAGE_LEVELS["happy-path"])

        user_prompt = f"""Analyze this API documentation and generate test examples at coverage level: {coverage}.
Include these categories: {', '.join(categories)}.

## API Documentation
{doc_text}

## Output Format
Return valid JSON with this structure:
{{"examples": [{{example objects}}]}}

Each example object:
{{
  "id": "TC-<RESOURCE>-<NNN>",
  "area": "functional",
  "category": "one of: {', '.join(categories)}",
  "endpoint": "METHOD /path",
  "description": "what this tests",
  "preconditions": ["list of prerequisites"],
  "request": {{"headers": {{}}, "body": {{}}}},
  "expected": {{"status": 200, "body_contains": ["field"], "schema": "SchemaName", "max_response_time_ms": 2000}},
  "depends_on": null,
  "cleanup": ""
}}
"""

        # Estimate endpoint count from doc size: ~30 lines per endpoint
        est_endpoints = max(1, doc_text.count("\n") // 30)
        max_tok = _estimate_max_tokens(est_endpoints, coverage)
        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt, max_tokens=max_tok)
        return self._parse_examples(response)

    def generate_test_code(self, examples, llm) -> str:
        examples_json = json.dumps([e.to_dict() for e in examples], indent=2)

        user_prompt = f"""Generate pytest code for the following test examples.
Use the apitest fixtures: client (httpx.Client), auth_token (str).

Import allure: from allure import feature, story, step

## Test Examples
{examples_json}

## CRITICAL — Python Syntax Rules
- Use Python True/False/None, NEVER true/false/null (those are JSON)
- Replace template path params like {{noteId}} with real values like "1" or "test-id"
- Status codes: match exact values from the examples — 201 means 201, 400 means 400
- Assert response body fields as listed in expected.body_contains
- Use f-strings with auth_token: f"Bearer {{auth_token}}"
- Run independent tests first, then dependent ones
- Return ONLY valid Python code, no markdown wrapping, no ```python fences
"""

        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt)
        return self._extract_code(response)

    def _parse_examples(self, response: str) -> list[TestExample]:
        # Strip code fences and text preamble
        cleaned = re.sub(r'```\w*\n?', '', response)
        cleaned = cleaned.strip()

        # Find the outermost JSON object containing "examples"
        start = cleaned.find('{"examples"')
        if start == -1:
            start = cleaned.find('{\n  "examples"')
        if start == -1:
            start = cleaned.find('{\n    "examples"')
        if start == -1:
            ex_pos = cleaned.find('"examples"')
            if ex_pos >= 0:
                start = cleaned.rfind('{', 0, ex_pos)

        if start >= 0:
            depth = 0
            end = start
            for i in range(start, len(cleaned)):
                if cleaned[i] == '{':
                    depth += 1
                elif cleaned[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if depth == 0:
                # Complete JSON — extract from start to matching }
                json_str = cleaned[start:end]
            else:
                # Truncated JSON (max_tokens cutoff) — take from start to end
                json_str = cleaned[start:]
        else:
            json_str = cleaned

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Response may be truncated (max_tokens limit). Try to salvage
            # individual example objects that are complete.
            examples = self._extract_partial_examples(json_str)
            if examples:
                print(f"  Recovered {len(examples)} examples from partial JSON")
                return examples
            print(f"Warning: LLM response could not be parsed as JSON.")
            print(f"Response preview (first 500 chars): {response[:500]}")
            return []
        return [TestExample.from_dict(e) for e in data.get("examples", [])]

    @staticmethod
    def _extract_partial_examples(text: str) -> list[TestExample]:
        """Extract complete example objects from truncated JSON by repairing
        the most common truncation pattern: the last object is cut off mid-field.
        """
        arr_match = re.search(r'"examples"\s*:\s*\[', text)
        if not arr_match:
            return []
        arr_start = arr_match.end()
        body = text[arr_start:]

        examples = []
        i = 0
        while i < len(body):
            if body[i] == '{':
                depth = 0
                end = i
                for j in range(i, len(body)):
                    if body[j] == '{':
                        depth += 1
                    elif body[j] == '}':
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            break
                if depth == 0:
                    try:
                        obj = json.loads(body[i:end])
                        if "id" in obj:
                            examples.append(TestExample.from_dict(obj))
                    except json.JSONDecodeError:
                        pass
                    i = end
                    continue
                else:
                    # Last object is truncated — close open brackets/braces once
                    snippet = body[i:]
                    open_b = snippet.count('{') - snippet.count('}')
                    open_arr = snippet.count('[') - snippet.count(']')
                    in_str = (snippet.count('"') % 2) != 0
                    repaired = snippet
                    if in_str:
                        repaired += '"'
                    repaired += ']' * open_arr
                    repaired += '}' * open_b
                    try:
                        obj = json.loads(repaired)
                        if "id" in obj and isinstance(obj, dict):
                            examples.append(TestExample.from_dict(obj))
                    except json.JSONDecodeError:
                        pass
                    break
            i += 1
        return examples

    def _extract_code(self, response: str) -> str:
        match = re.search(r"```python\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        return response.strip()


def _estimate_max_tokens(num_endpoints: int, coverage: str) -> int:
    """Estimate output tokens needed based on endpoints and coverage level.

    One example is ~300 chars (~75 tokens) of JSON.
    Full coverage of 20 endpoints = 120 examples ≈ 9000+ tokens.
    """
    categories = COVERAGE_LEVELS.get(coverage, COVERAGE_LEVELS["happy-path"])
    est_examples = num_endpoints * len(categories)
    # ~80 tokens per example + 2048 overhead for JSON structure and text preamble
    return min(max(4096, est_examples * 80 + 2048), 32768)


# Self-register on import
registry.register(FunctionalArea())
