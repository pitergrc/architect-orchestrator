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
    ClassifyRequest,
    ClassifyResponse,
    ExecutionPlanRequest,
    ExecutionPlanResponse,
    ConstraintsCheckRequest,
    ConstraintsCheckResponse,
    ChatBrief,
)

from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .postcheck import run_postcheck
from .telemetry import log_event
from .orchestration_core import (
    classify_task,
    plan_execution,
    check_constraints,
    enrich_preflight_response,
    normalize_postcheck,
)

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
    parsed.deliverable_hint = parsed.deliverable_hint or "unknown"

    if parsed.misread_risk != "low":
        log_event(TelemetryEvent(event=parsed.misread_risk, payload={"text": payload.text}))

    return parsed


@app.post("/route", response_model=RouteResponse, operation_id="resolveRoute")
def route_endpoint(payload: RouteRequest) -> RouteResponse:
    route = resolve_route(payload.text, payload.parsed)
    log_event(TelemetryEvent(event="route_selected", route=route.route, payload={"reasons": route.reasons}))
    return route


@app.post("/classify", response_model=ClassifyResponse, operation_id="classifyTask")
def classify_task_endpoint(payload: ClassifyRequest) -> ClassifyResponse:
    text = payload.text
    parsed = payload.parsed or parse_prompt(text)
    return classify_task(text, parsed)


@app.post("/execution-plan", response_model=ExecutionPlanResponse, operation_id="planExecution")
def plan_execution_endpoint(payload: ExecutionPlanRequest) -> ExecutionPlanResponse:
    text = payload.text
    parsed = payload.parsed or parse_prompt(text)
    route = payload.route or resolve_route(text, parsed)

    if payload.classification is None:
        classification = classify_task(text, parsed)
    else:
        classification = payload.classification

    return plan_execution(text, parsed, route, classification)


@app.post("/constraints-check", response_model=ConstraintsCheckResponse, operation_id="checkConstraints")
def check_constraints_endpoint(payload: ConstraintsCheckRequest) -> ConstraintsCheckResponse:
    text = payload.text
    parsed = payload.parsed or parse_prompt(text)

    if payload.classification is None:
        classification = classify_task(text, parsed)
    else:
        classification = payload.classification

    if payload.execution is None:
        route = payload.route or resolve_route(text, parsed)
        execution = plan_execution(text, parsed, route, classification)
    else:
        execution = payload.execution

    return check_constraints(parsed, classification, execution)


@app.post("/preflight", response_model=PreflightResponse, operation_id="runPreflight")
def preflight_endpoint(payload: PreflightRequest) -> PreflightResponse:
    parsed = payload.parsed or parse_prompt(payload.text)
    route_obj = resolve_route(payload.text, parsed)
    route_value = payload.route or route_obj.route

    classification = classify_task(payload.text, parsed)
    plan = plan_execution(payload.text, parsed, route_obj, classification)
    constraints = check_constraints(parsed, classification, plan)

    base = run_preflight(payload.text, parsed, route_value)

    out = enrich_preflight_response(
        base=base,
        parsed=parsed,
        route=route_obj,
        classification=classification,
        plan=plan,
        constraints=constraints,
    )

    for flag in out.defect_flags:
        log_event(TelemetryEvent(event="defect_flag", route=route_value, payload={"flag": flag}))

    return out


@app.post("/postcheck", response_model=PostcheckResponse, operation_id="runPostcheck")
def postcheck_endpoint(payload: PostcheckRequest) -> PostcheckResponse:
    out = run_postcheck(payload.text, payload.parsed, payload.route, payload.answer)

    classification = classify_task(payload.text, payload.parsed)
    route_obj = resolve_route(payload.text, payload.parsed)
    plan = plan_execution(payload.text, payload.parsed, route_obj, classification)
    constraints = check_constraints(payload.parsed, classification, plan)

    out = normalize_postcheck(
        out=out,
        parsed=payload.parsed,
        classification=classification,
        plan=plan,
        constraints=constraints,
    )

    for event in out.events:
        log_event(TelemetryEvent(event=event, route=payload.route, payload={"missing_asks": out.missing_asks}))

    return out


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

        initial_state = {"text": payload.text}
        if payload.chat_brief is not None:
            initial_state["chat_brief"] = payload.chat_brief.model_dump()

        state = graph.invoke(initial_state)

        parsed = ParseResponse.model_validate(state["parsed"])
        route = RouteResponse.model_validate(state["route"])
        preflight = PreflightResponse.model_validate(state["preflight"])

        postcheck = None
        if state.get("postcheck") is not None:
            postcheck = PostcheckResponse.model_validate(state["postcheck"])

        applied_chat_brief = None
        if state.get("chat_brief") is not None:
            applied_chat_brief = ChatBrief.model_validate(state["chat_brief"])

        telemetry_events = []
        if preflight.defect_flags:
            telemetry_events.extend(preflight.defect_flags)
        if postcheck and postcheck.events:
            telemetry_events.extend(postcheck.events)
        if applied_chat_brief is not None:
            telemetry_events.append("chat_brief_used")

        return OrchestrateResponse(
            parsed=parsed,
            route=route,
            preflight=preflight,
            draft_answer=state.get("draft_answer"),
            postcheck=postcheck,
            telemetry_events=telemetry_events,
            applied_chat_brief=applied_chat_brief,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="runOrchestrator unavailable in current deployment",
        ) from exc
