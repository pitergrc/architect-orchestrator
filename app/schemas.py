from typing import Any, Literal
from pydantic import BaseModel, Field


RouteType = Literal["ordinary", "compatibility", "migration", "rfc", "release"]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "architect-orchestrator"


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
    possible_surface_interpretation: str = ""
    strongest_alternative_interpretation: str = ""
    needs_hidden_trap_screen: bool = False
    user_intent_mode: Literal["reference", "case_analysis", "tutor", "decision_support", "mixed"] = "mixed"


class RouteResponse(BaseModel):
    route: RouteType
    reasons: list[str] = Field(default_factory=list)
    orchestration_required: bool = True
    screening_required: bool = True
    default_depth_floor: Literal["standard", "deep"] = "standard"
    can_use_light_internal_path: bool = False


class PreflightResponse(BaseModel):
    runtime_mode: str = "FULL_CORE"
    loaded_core: bool = True
    no_duplicate_law: bool = True
    prompt_parse_active: bool = True
    ask_ledger_active: bool = True
    prompt_coverage_required: bool = True
    audit_scope_resolver_active: bool = True
    defect_flags: list[str] = Field(default_factory=list)
    ask_ledger: list[Any] = Field(default_factory=list)
    audit_hint: Literal["response_audit", "system_audit"] = "response_audit"
    task_profile: dict | None = None
    execution_flags: dict | None = None
    constraints_flags: dict | None = None
    deliverable_contract: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class ChatBrief(BaseModel):
    main_ask: str | None = None
    secondary_asks: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    strongest_alternative_interpretation: str | None = None
    candidate_hypotheses: list[str] = Field(default_factory=list)
    overturn_conditions: list[str] = Field(default_factory=list)
    desired_output_shape: list[str] = Field(default_factory=list)


class ExecutionReality(BaseModel):
    action_selected: bool = True
    response_received: bool = True
    draft_safe: bool = True
    notes: list[str] = Field(default_factory=list)


class GroqAssist(BaseModel):
    alt_interpretations: list[str] = Field(default_factory=list)
    nonstandard_options: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    overturn_conditions: list[str] = Field(default_factory=list)


class OrchestrateRequest(BaseModel):
    text: str
    use_llm: bool = True
    chat_brief: ChatBrief | None = None


class OrchestrateResponse(BaseModel):
    parsed: ParseResponse
    route: RouteResponse
    preflight: PreflightResponse
    telemetry_events: list[str] = Field(default_factory=list)
    applied_chat_brief: ChatBrief | None = None
    execution_reality: ExecutionReality | None = None
    groq_assist: GroqAssist | None = None
       
