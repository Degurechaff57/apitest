import json
import re

from apitest.areas.base import registry
from apitest.models.endpoint import Endpoint
from apitest.models.example import TestExample, TestPlan, TestPlanPhase, COVERAGE_LEVELS
from apitest.engine.fake_data import generate_fake_value


PLAN_SYSTEM_PROMPT = """You are a senior QA test planner. Given a list of test examples,
organize them into a logical execution plan.

## Rules
- Order phases by dependency: setup/auth first, then CRUD lifecycles, then cleanup
- Group examples by resource (extract from endpoint path)
- Identify shared prerequisites and group them into setup phases
- Examples that depend on others MUST come after their dependencies
- Estimate total duration based on number of examples (~10s per example)
"""


class Generator:
    """Orchestrates test areas to generate examples and plans."""

    def __init__(self, llm=None):
        self.llm = llm

    def generate_examples(self, endpoints, coverage, area_names):
        areas = registry.get_enabled(area_names)
        all_examples = []
        for area in areas:
            examples = area.generate_examples(endpoints, coverage, self.llm)
            all_examples.extend(examples)
        return all_examples

    def generate_examples_from_schema(self, endpoints: list, coverage: str) -> list[TestExample]:
        """Generate examples directly from parsed schema — no LLM, near-instant."""
        categories = COVERAGE_LEVELS.get(coverage, COVERAGE_LEVELS["happy-path"])
        examples = []
        counter = {}

        method_order = {"POST": 0, "GET": 1, "PUT": 2, "PATCH": 2, "DELETE": 3}
        endpoints = sorted(endpoints, key=lambda e: (
            method_order.get(e.method, 99), e.path))

        for ep in endpoints:
            resource_key = ep.resource.upper()
            counter.setdefault(resource_key, 0)
            success_code = 200
            for r in ep.responses:
                if 200 <= r.status_code < 300:
                    success_code = r.status_code
                    break

            base_description = ep.summary or f"{ep.method} {ep.path}"

            for cat in categories:
                counter[resource_key] += 1
                ex_id = f"TC-{resource_key}-{counter[resource_key]:03d}"

                body = {}
                for p in ep.parameters:
                    if p.location == "body":
                        body[p.name] = generate_fake_value(
                            p.name, p.schema_type,
                            enum=p.enum, minimum=p.minimum, maximum=p.maximum,
                            min_length=p.min_length, max_length=p.max_length,
                            fmt=p.format,
                        )

                cat_descriptions = {
                    "happy-path": base_description,
                    "equivalence-class": f"{base_description} — equivalence class variation",
                    "boundary-value": f"{base_description} — boundary value test",
                    "negative": f"{base_description} — negative test (invalid input)",
                    "auth-security": f"{base_description} — auth/security check",
                    "lifecycle": f"{base_description} — lifecycle step",
                }

                examples.append(TestExample(
                    id=ex_id, area="functional", category=cat,
                    endpoint=f"{ep.method} {ep.path}",
                    description=cat_descriptions.get(cat, base_description),
                    request_body=body if body else None,
                    request_headers={"Authorization": "Bearer ${TOKEN}"} if ep.has_auth else {},
                    expected_status=401 if cat == "auth-security" else
                                   400 if cat == "negative" else success_code,
                    expected_body_contains=["data"],
                ))

        return examples

    def generate_plan_from_schema(self, examples: list[TestExample], coverage: str,
                                  areas: list[str]) -> TestPlan:
        """Generate a plan deterministically — group by resource, no LLM."""
        # Group examples by resource
        groups: dict[str, list] = {}
        for ex in examples:
            resource = ex.endpoint.split(" ", 1)[1].split("/")[2] if len(
                ex.endpoint.split(" ", 1)[1].split("/")) > 2 else "root"
            groups.setdefault(resource, []).append(ex)

        phases = []
        order = 1
        for resource, exs in groups.items():
            phases.append(TestPlanPhase(
                name=resource.title(),
                order=order,
                examples=[e.id for e in exs],
                description=f"Tests for {resource} endpoints",
            ))
            order += 1

        return TestPlan(
            title="Test Plan",
            coverage=coverage,
            areas=areas,
            total_examples=len(examples),
            estimated_duration_minutes=max(1, len(examples) * 10 // 60),
            phases=phases,
        )

    def generate_examples_from_text(self, doc_text: str, coverage: str, area_names: list[str]):
        """Generate examples directly from raw API doc text (markdown, txt, etc.)."""
        areas = registry.get_enabled(area_names)
        all_examples = []
        for area in areas:
            if hasattr(area, "generate_examples_from_text"):
                examples = area.generate_examples_from_text(doc_text, coverage, self.llm)
            else:
                examples = area.generate_examples([], coverage, self.llm)
            all_examples.extend(examples)
        return all_examples

    def generate_plan(self, examples, coverage, area_names):
        examples_json = json.dumps([e.to_dict() for e in examples], indent=2)

        user_prompt = f"""Organize these test examples into a test plan.

## Examples
{examples_json}

## Output Format
Return valid JSON:
{{"plan": {{
  "title": "Test Plan: <API Name>",
  "coverage": "{coverage}",
  "areas": {json.dumps(area_names)},
  "total_examples": {len(examples)},
  "estimated_duration_minutes": <number>,
  "phases": [
    {{
      "name": "Phase name",
      "order": 1,
      "examples": ["TC-XXX-001"],
      "description": "What this phase covers",
      "depends_on_phase": null
    }}
  ]
}}}}
"""

        if self.llm is None:
            return self.generate_plan_from_schema(examples, coverage, area_names)
        response = self.llm.chat(PLAN_SYSTEM_PROMPT, user_prompt)
        return self._parse_plan(response, coverage, area_names)

    def _parse_plan(self, response, coverage, areas):
        match = re.search(r'\{[\s\S]*"plan"[\s\S]*\}', response)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(response)
        return TestPlan.from_dict(data)
