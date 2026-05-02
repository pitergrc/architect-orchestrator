from fastapi import FastAPI, HTTPException
import os

from .schemas import (
    HealthResponse,
    OrchestrateRequest,
    OrchestrateResponse,
    ExecutionReality,
    ParseResponse,
    RouteResponse,
    PreflightResponse,
    ChatBrief,
    GroqAssist,
)

from .graph import build_graph

RUN_ORCHESTRATOR_ENABLED = os.getenv("RUN_ORCHESTRATOR_ENABLED", "true").lower() == "true"
RUN_ORCHESTRATOR_PUBLIC = os.getenv("RUN_ORCHESTRATOR_PUBLIC", "true").lower() == "true"

app = FastAPI(title="Architect Orchestrator", version="1.0")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse()


@app.post(
    "/orchestrate",
    response_model=OrchestrateResponse,
    operation_id="runOrchestrator",
    include_in_schema=RUN_ORCHESTRATOR_PUBLIC,
)
def orchestrate(payload: OrchestrateRequest):
    if not RUN_ORCHESTRATOR_ENABLED:
        raise HTTPException(status_code=503, detail="disabled")

    graph = build_graph()

    state = graph.invoke({
        "text": payload.text,
        "chat_brief": payload.chat_brief.model_dump() if payload.chat_brief else None
    })

    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    preflight = PreflightResponse.model_validate(state["preflight"])

    brief = None
    if state.get("chat_brief"):
        brief = ChatBrief.model_validate(state["chat_brief"])

    groq_assist = None
    if isinstance(state.get("groq_assist"), dict):
        groq_assist = GroqAssist.model_validate(state["groq_assist"])

    return OrchestrateResponse(
        parsed=parsed,
        route=route,
        preflight=preflight,
        telemetry_events=preflight.defect_flags,
        applied_chat_brief=brief,
        execution_reality=ExecutionReality(),
        groq_assist=groq_assist,
    )
