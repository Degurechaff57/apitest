import json
import re

from apitest.areas.base import TestArea, registry
from apitest.models.example import TestExample, CATEGORIES, COVERAGE_LEVELS


FUNCTIONAL_SYSTEM_PROMPT = """You are a senior API QA engineer specializing in functional testing.
Generate test examples and pytest code from API endpoint specifications.

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

        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt)
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

        response = llm.chat(FUNCTIONAL_SYSTEM_PROMPT, user_prompt)
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
        match = re.search(r'\{[\s\S]*"examples"[\s\S]*\}', response)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(response)
        return [TestExample.from_dict(e) for e in data.get("examples", [])]

    def _extract_code(self, response: str) -> str:
        match = re.search(r"```python\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\n([\s\S]*?)```", response)
        if match:
            return match.group(1).strip()
        return response.strip()


# Self-register on import
registry.register(FunctionalArea())
