from typing import Literal

from __future__ import annotations

import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException

from .schemas import (
    HealthResponse,
    PromptInput,
    ParseResponse,
    RouteRequest,
    RouteResponse,
    PreflightRequest,
    PreflightResponse,
    PostcheckRequest,
    PostcheckResponse,
    OrchestrateRequest,
    OrchestrateResponse,
    TelemetryEvent,
)
from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .postcheck import run_postcheck
from .telemetry import log_event

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
RUN_ORCHESTRATOR_ENABLED = os.getenv("RUN_ORCHESTRATOR_ENABLED", "false").lower() == "true"
RUN_ORCHESTRATOR_PUBLIC = os.getenv("RUN_ORCHESTRATOR_PUBLIC", "false").lower() == "true"

if PUBLIC_BASE_URL:
    app = FastAPI(
        title="Architect Orchestrator",
        version="0.2.0",
        servers=[{"url": PUBLIC_BASE_URL}],
    )
else:
    app = FastAPI(title="Architect Orchestrator", version="0.2.0")


@app.get("/health", response_model=HealthResponse, operation_id="healthCheck")
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse()


@app.post("/parse", response_model=ParseResponse, operation_id="parsePrompt")
def parse_endpoint(payload: PromptInput) -> ParseResponse:
    parsed = parse_prompt(payload.text)
    if parsed.misread_risk != "normal":
        deliverable_hint: str | None = None
        log_event(TelemetryEvent(event=parsed.misread_risk, payload={"text": payload.text}))
    return parsed


@app.post("/route", response_model=RouteResponse, operation_id="resolveRoute")
def route_endpoint(payload: RouteRequest) -> RouteResponse:
    route = resolve_route(payload.text, payload.parsed)
    log_event(TelemetryEvent(event="route_selected", route=route.route, payload={"reasons": route.reasons}))
    return route


class ClassifyResponse(BaseModel):
    primary_task_class: Literal["formal", "coding", "research", "planning", "diagnosis", "transformation"]
    secondary_task_class: Literal["formal", "coding", "research", "planning", "diagnosis", "transformation"] | None = None
    difficulty: Literal["low", "medium", "high", "extreme"]
    stakes: Literal["low", "medium", "high"]
    route_confidence: Literal["low", "medium", "high"]
    re_route_allowed: bool = True


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

class ConstraintsCheckResponse(BaseModel):
    hard_constraints: list[str] = []
    deployability_risk: Literal["low", "medium", "high"] = "low"
    artifact_validation_required: bool = False
    known_environment_limits: list[str] = []


@app.post("/preflight", response_model=PreflightResponse, operation_id="runPreflight")
def preflight_endpoint(payload: PreflightRequest) -> PreflightResponse:
    parsed = payload.parsed or parse_prompt(payload.text)
    route = payload.route or resolve_route(payload.text, parsed).route
    out = run_preflight(payload.text, parsed, route)
    for flag in out.defect_flags:
        log_event(TelemetryEvent(event="defect_flag", route=route, payload={"flag": flag}))
    return out


@app.post("/postcheck", response_model=PostcheckResponse, operation_id="runPostcheck")
def postcheck_endpoint(payload: PostcheckRequest) -> PostcheckResponse:
    out = run_postcheck(payload.text, payload.parsed, payload.route, payload.answer)
    for event in out.events:
        log_event(TelemetryEvent(event=event, route=payload.route, payload={"missing_asks": out.missing_asks}))
    return out
    issues: list[str] = []
    status_too_strong: bool = False
    repair_needed: bool = False
    recommended_status: Literal["final", "provisional", "partial", "blocked"] | None = None

@app.post(
    "/orchestrate",
    response_model=OrchestrateResponse,
    operation_id="runOrchestrator",
    include_in_schema=RUN_ORCHESTRATOR_PUBLIC,
)
def orchestrate_endpoint(payload: OrchestrateRequest) -> OrchestrateResponse:
    if not RUN_ORCHESTRATOR_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="runOrchestrator disabled in Render-only lite mode",
        )

    try:
        from .graph import build_graph

        graph = build_graph()
        state = graph.invoke({"text": payload.text})

        parsed = ParseResponse.model_validate(state["parsed"])
        route = RouteResponse.model_validate(state["route"])
        preflight = PreflightResponse.model_validate(state["preflight"])

        postcheck = None
        if state.get("postcheck") is not None:
            postcheck = PostcheckResponse.model_validate(state["postcheck"])

        telemetry_events = []
        if preflight.defect_flags:
            telemetry_events.extend(preflight.defect_flags)
        if postcheck and postcheck.events:
            telemetry_events.extend(postcheck.events)

        return OrchestrateResponse(
            parsed=parsed,
            route=route,
            preflight=preflight,
            draft_answer=state.get("draft_answer"),
            postcheck=postcheck,
            telemetry_events=telemetry_events,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="runOrchestrator unavailable in current deployment",
        ) from exc
