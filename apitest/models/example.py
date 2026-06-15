from dataclasses import dataclass, field


@dataclass
class TestExample:
    id: str  # TC-USER-001
    area: str  # functional
    category: str  # happy-path, equivalence-class, boundary-value, negative, auth-security, lifecycle
    endpoint: str  # POST /api/users
    description: str
    preconditions: list[str] = field(default_factory=list)
    request_headers: dict[str, str] = field(default_factory=dict)
    request_body: dict | None = None
    expected_status: int = 200
    expected_body_contains: list[str] = field(default_factory=list)
    expected_schema: str = ""
    max_response_time_ms: int = 2000
    depends_on: str | None = None  # another example ID
    cleanup: str = ""

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "area": self.area,
            "category": self.category,
            "endpoint": self.endpoint,
            "description": self.description,
            "preconditions": self.preconditions,
            "request": {"headers": self.request_headers},
            "expected": {
                "status": self.expected_status,
                "max_response_time_ms": self.max_response_time_ms,
            },
            "depends_on": self.depends_on,
            "cleanup": self.cleanup,
        }
        if self.request_body is not None:
            result["request"]["body"] = self.request_body
        if self.expected_body_contains:
            result["expected"]["body_contains"] = self.expected_body_contains
        if self.expected_schema:
            result["expected"]["schema"] = self.expected_schema
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TestExample":
        req = data.get("request", {})
        exp = data.get("expected", {})
        return cls(
            id=data["id"],
            area=data.get("area", "functional"),
            category=data.get("category", "happy-path"),
            endpoint=data["endpoint"],
            description=data.get("description", ""),
            preconditions=data.get("preconditions", []),
            request_headers=req.get("headers", {}),
            request_body=req.get("body"),
            expected_status=exp.get("status", 200),
            expected_body_contains=exp.get("body_contains", []),
            expected_schema=exp.get("schema", ""),
            max_response_time_ms=exp.get("max_response_time_ms", 2000),
            depends_on=data.get("depends_on"),
            cleanup=data.get("cleanup", ""),
        )


@dataclass
class TestPlanPhase:
    name: str
    order: int
    examples: list[str]  # example IDs
    description: str = ""
    depends_on_phase: int | None = None


@dataclass
class TestPlan:
    title: str
    coverage: str
    areas: list[str]
    phases: list[TestPlanPhase] = field(default_factory=list)
    total_examples: int = 0
    estimated_duration_minutes: int = 0

    def to_dict(self) -> dict:
        phases_data = []
        for p in self.phases:
            phase_dict = {
                "name": p.name,
                "order": p.order,
                "examples": p.examples,
                "description": p.description,
            }
            if p.depends_on_phase is not None:
                phase_dict["depends_on_phase"] = p.depends_on_phase
            phases_data.append(phase_dict)
        return {
            "plan": {
                "title": self.title,
                "coverage": self.coverage,
                "areas": self.areas,
                "total_examples": self.total_examples,
                "estimated_duration_minutes": self.estimated_duration_minutes,
                "phases": phases_data,
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TestPlan":
        plan = data["plan"]
        return cls(
            title=plan["title"],
            coverage=plan["coverage"],
            areas=plan["areas"],
            total_examples=plan.get("total_examples", 0),
            estimated_duration_minutes=plan.get("estimated_duration_minutes", 0),
            phases=[
                TestPlanPhase(
                    name=p["name"],
                    order=p["order"],
                    examples=p["examples"],
                    description=p.get("description", ""),
                    depends_on_phase=p.get("depends_on_phase"),
                )
                for p in plan.get("phases", [])
            ],
        )


CATEGORIES = [
    "happy-path",
    "equivalence-class",
    "boundary-value",
    "negative",
    "auth-security",
    "lifecycle",
]

COVERAGE_LEVELS = {
    "smoke": ["happy-path"],
    "happy-path": ["happy-path", "equivalence-class", "negative"],
    "full": CATEGORIES,
}
