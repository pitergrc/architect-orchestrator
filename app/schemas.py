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
    deliverable_hint: str | None = None
    notes: list[str] = Field(default_factory=list)

    # v2 additions — keep defaults for backward compatibility
    possible_surface_interpretation: str = ""
    strongest_alternative_interpretation: str = ""
    needs_hidden_trap_screen: bool = False
    user_intent_mode: Literal["reference", "case_analysis", "tutor", "decision_support", "mixed"] = "mixed"


class RouteRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None


class RouteResponse(BaseModel):
    route: RouteType
    reasons: list[str] = Field(default_factory=list)

    # v2 additions — safe defaults
    orchestration_required: bool = True
    screening_required: bool = True
    default_depth_floor: Literal["standard", "deep"] = "standard"
    can_use_light_internal_path: bool = False


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

    task_profile: dict | None = None
    execution_flags: dict | None = None
    constraints_flags: dict | None = None
    deliverable_contract: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class ClassifyResponse(BaseModel):
    primary_task_class: Literal["formal", "coding", "research", "planning", "diagnosis", "transformation"]
    secondary_task_class: Literal["formal", "coding", "research", "planning", "diagnosis", "transformation"] | None = None
    difficulty: Literal["low", "medium", "high", "extreme"]
    stakes: Literal["low", "medium", "high"]
    route_confidence: Literal["low", "medium", "high"]
    re_route_allowed: bool = True

    # v2 additions — safe defaults
    hidden_trap_risk: Literal["low", "medium", "high"] = "low"
    popularity_bias_risk: Literal["low", "medium", "high"] = "low"
    evidence_debt: Literal["low", "medium", "high"] = "low"
    freshness_need: Literal["low", "medium", "high"] = "low"
    tool_need_likelihood: Literal["low", "medium", "high"] = "low"
    deceptive_simple_risk: Literal["low", "medium", "high"] = "low"


class ExecutionPlanResponse(BaseModel):
    execution_mode: Literal["fast", "standard", "deep", "hybrid", "artifact_first"]
    tool_mandatory: bool = False
    verifier_required: bool = True
    critic_required: bool = False
    carryover_required: bool = False
    constraints_check_required: bool = True
    deployability_check_required: bool = False
    max_passes: int = 2
    max_repair_cycles: int = 1
    deliverable_contract: Literal["answer", "plan", "spec", "memo", "patch", "report", "artifact"]

    # v2 additions — safe defaults
    hidden_trap_screen_required: bool = False
    popularity_check_required: bool = False
    freshness_check_required: bool = False
    minimum_status_ceiling_without_tools: Literal["final", "provisional", "partial", "blocked"] = "final"
    recommended_tools: list[str] = Field(default_factory=list)
    reason_tools_matter: list[str] = Field(default_factory=list)


class ConstraintsCheckResponse(BaseModel):
    hard_constraints: list[str] = Field(default_factory=list)
    deployability_risk: Literal["low", "medium", "high"] = "low"
    artifact_validation_required: bool = False
    known_environment_limits: list[str] = Field(default_factory=list)

    # v2 additions — safe defaults
    orchestration_limits: list[str] = Field(default_factory=list)
    status_ceiling: Literal["final", "provisional", "partial", "blocked"] = "final"

class ClassifyRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None


class ExecutionPlanRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None
    route: RouteResponse | None = None
    classification: ClassifyResponse | None = None


class ConstraintsCheckRequest(BaseModel):
    text: str
    parsed: ParseResponse | None = None
    route: RouteResponse | None = None
    classification: ClassifyResponse | None = None
    execution: ExecutionPlanResponse | None = None


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
    issues: list[str] = Field(default_factory=list)
    status_too_strong: bool = False
    repair_needed: bool = False
    recommended_status: Literal["final", "provisional", "partial", "blocked"] | None = None


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
