from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


RouteType = Literal["ordinary", "compatibility", "migration", "rfc", "release"]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "architect-orchestrator"


class PromptInput(BaseModel):
    text: str = Field(..., description="Raw user message")
    prior_route: str | None = None
    prior_mode: str | None = None


class ParseResponse(BaseModel):
    main_ask: str
    secondary_asks: list[str]
    constraints: list[str]
    examples: list[str]
    hypotheses: list[str]
    style_preferences: list[str]
    policy_or_core_change_request: bool
    misread_risk: str
    notes: list[str] = Field(default_factory=list)


class RouteRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None


class RouteResponse(BaseModel):
    route: RouteType
    reasons: list[str] = Field(default_factory=list)


class AskItem(BaseModel):
    id: str
    text: str
    priority: Literal["high", "medium", "low"] = "medium"
    droppable: bool = False


class PreflightRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None
    route: RouteType | None = None


class PreflightResponse(BaseModel):
    runtime_mode: str = "FULL_CORE"
    loaded_core: bool = True
    no_duplicate_law: bool = True
    prompt_parse_active: bool = True
    ask_ledger_active: bool = True
    prompt_coverage_required: bool = True
    audit_scope_resolver_active: bool = True
    defect_flags: list[str] = Field(default_factory=list)
    ask_ledger: list[AskItem] = Field(default_factory=list)
    audit_hint: Literal["response_audit", "system_audit"] = "response_audit"


class PostcheckRequest(BaseModel):
    text: str
    parsed: ParseResponse
    route: RouteType
    answer: str


class PostcheckResponse(BaseModel):
    ok: bool
    events: list[str] = Field(default_factory=list)
    missing_asks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class OrchestrateRequest(BaseModel):
    text: str
    use_llm: bool = True


class OrchestrateResponse(BaseModel):
    parsed: ParseResponse
    route: RouteResponse
    preflight: PreflightResponse
    draft_answer: str | None = None
    postcheck: PostcheckResponse | None = None
    telemetry_events: list[str] = Field(default_factory=list)


class TelemetryEvent(BaseModel):
    event: str
    route: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
