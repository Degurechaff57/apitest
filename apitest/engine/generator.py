import json
import re

from apitest.areas.base import registry
from apitest.models.example import TestExample, TestPlan


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

    def __init__(self, llm):
        self.llm = llm

    def generate_examples(self, endpoints, coverage, area_names):
        areas = registry.get_enabled(area_names)
        all_examples = []
        for area in areas:
            examples = area.generate_examples(endpoints, coverage, self.llm)
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

        response = self.llm.chat(PLAN_SYSTEM_PROMPT, user_prompt)
        return self._parse_plan(response, coverage, area_names)

    def _parse_plan(self, response, coverage, areas):
        match = re.search(r'\{[\s\S]*"plan"[\s\S]*\}', response)
        if match:
            data = json.loads(match.group())
        else:
            data = json.loads(response)
        return TestPlan.from_dict(data)
