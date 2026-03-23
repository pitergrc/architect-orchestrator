from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

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
from .graph import build_graph

app = FastAPI(title="Architect Orchestrator", version="0.1.0")
graph = build_graph()


@app.get("/health", response_model=HealthResponse, operation_id="healthCheck")
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/parse", response_model=ParseResponse, operation_id="parsePrompt")
def parse_endpoint(payload: PromptInput) -> ParseResponse:
    parsed = parse_prompt(payload.text)
    if parsed.misread_risk != "normal":
        log_event(TelemetryEvent(event=parsed.misread_risk, payload={"text": payload.text}))
    return parsed


@app.post("/route", response_model=RouteResponse, operation_id="resolveRoute")
def route_endpoint(payload: RouteRequest) -> RouteResponse:
    route = resolve_route(payload.text, payload.parsed)
    log_event(TelemetryEvent(event="route_selected", route=route.route, payload={"reasons": route.reasons}))
    return route


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


@app.post("/orchestrate", response_model=OrchestrateResponse, operation_id="runOrchestrator")
def orchestrate_endpoint(payload: OrchestrateRequest) -> OrchestrateResponse:
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
