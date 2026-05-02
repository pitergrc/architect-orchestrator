from __future__ import annotations

import json
from typing import TypedDict, NotRequired

from langgraph.graph import StateGraph, END

from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .llm import generate_draft
from .orchestration_core import (
    classify_task,
    plan_execution,
    check_constraints,
    enrich_preflight_response,
)
from .schemas import ParseResponse, RouteResponse, ChatBrief


class FlowState(TypedDict):
    text: str
    parsed: NotRequired[dict]
    route: NotRequired[dict]
    preflight: NotRequired[dict]
    chat_brief: NotRequired[dict]
    groq_assist: NotRequired[dict]


def node_parse(state: FlowState):
    parsed = parse_prompt(state["text"])

    if state.get("chat_brief"):
        brief = ChatBrief.model_validate(state["chat_brief"])
        if brief.main_ask:
            parsed.main_ask = brief.main_ask

    state["parsed"] = parsed.model_dump()
    return state


def node_route(state: FlowState):
    parsed = ParseResponse.model_validate(state["parsed"])
    route = resolve_route(state["text"], parsed)
    state["route"] = route.model_dump()
    return state


def node_preflight(state: FlowState):
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])

    classification = classify_task(state["text"], parsed)
    execution = plan_execution(state["text"], parsed, route, classification)
    constraints = check_constraints(parsed, classification, execution)

    base = run_preflight(state["text"], parsed, route.route)

    preflight = enrich_preflight_response(
        base=base,
        parsed=parsed,
        route=route,
        classification=classification,
        plan=execution,
        constraints=constraints,
    )

    state["preflight"] = preflight.model_dump()
    return state


def node_groq_assist(state: FlowState):
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])

    prompt = f"""
Return JSON only:

{{
 "alt_interpretations": [],
 "nonstandard_options": [],
 "risks": [],
 "overturn_conditions": []
}}

Task: {parsed.main_ask}
Route: {route.route}
"""

    result = generate_draft(state["text"], prompt)

    try:
        data = json.loads(result.text) if result.ok else {}
    except:
        data = {}

    if not isinstance(data, dict):
        data = {}

    state["groq_assist"] = {
        "alt_interpretations": data.get("alt_interpretations", []),
        "nonstandard_options": data.get("nonstandard_options", []),
        "risks": data.get("risks", []),
        "overturn_conditions": data.get("overturn_conditions", []),
    }

    return state


def build_graph():
    graph = StateGraph(FlowState)

    graph.add_node("parse", node_parse)
    graph.add_node("route", node_route)
    graph.add_node("preflight", node_preflight)
    graph.add_node("groq_assist", node_groq_assist)

    graph.set_entry_point("parse")

    graph.add_edge("parse", "route")
    graph.add_edge("route", "preflight")
    graph.add_edge("preflight", "groq_assist")
    graph.add_edge("groq_assist", END)

    return graph.compile()
