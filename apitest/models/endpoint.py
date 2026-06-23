from dataclasses import dataclass, field


@dataclass
class Parameter:
    name: str
    location: str  # query, path, header, cookie, body
    schema_type: str  # string, integer, number, boolean, array, object
    required: bool = False
    description: str = ""
    enum: list[str] | None = None
    minimum: float | None = None
    maximum: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    format: str = ""  # email, uuid, date-time, etc.
    default: object = None


@dataclass
class RequestBody:
    content_type: str = "application/json"
    schema_ref: str = ""  # $ref name
    required: bool = False


@dataclass
class Response:
    status_code: int
    description: str = ""
    schema_ref: str = ""


@dataclass
class Endpoint:
    method: str  # GET, POST, PUT, DELETE, PATCH
    path: str  # /api/users/{id}
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[Parameter] = field(default_factory=list)
    request_body: RequestBody | None = None
    responses: list[Response] = field(default_factory=list)
    security: list[dict[str, list[str]]] = field(default_factory=list)

    @property
    def resource(self) -> str:
        """Extract resource name from path, e.g. /api/users/{id} -> users"""
        parts = [p for p in self.path.split("/") if p and not p.startswith("{")]
        return parts[-1] if parts else "root"

    @property
    def required_params(self) -> list["Parameter"]:
        return [p for p in self.parameters if p.required]

    @property
    def has_auth(self) -> bool:
        return any(req for req in self.security if req)
