from __future__ import annotations

from typing import TypedDict, NotRequired

from langgraph.graph import StateGraph, END

from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .orchestration_core import (
    classify_task,
    plan_execution,
    check_constraints,
    enrich_preflight_response,
)
from .schemas import (
    ParseResponse,
    RouteResponse,
    ChatBrief,
)


class FlowState(TypedDict):
    text: str
    parsed: NotRequired[dict]
    route: NotRequired[dict]
    classification: NotRequired[dict]
    execution: NotRequired[dict]
    constraints: NotRequired[dict]
    preflight: NotRequired[dict]
    chat_brief: NotRequired[dict]


def _dedup_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue

        key = cleaned.lower()
        if key in seen:
            continue

        seen.add(key)
        out.append(cleaned)

    return out


def _merge_chat_brief_into_parsed(parsed: ParseResponse, brief: ChatBrief) -> ParseResponse:
    merged = parsed.model_copy(deep=True)

    if brief.main_ask and brief.main_ask.strip():
        merged.main_ask = brief.main_ask.strip()
        merged.possible_surface_interpretation = brief.main_ask.strip()

    merged.secondary_asks = _dedup_keep_order([
        *brief.secondary_asks,
        *merged.secondary_asks,
    ])

    merged.constraints = _dedup_keep_order([
        *brief.constraints,
        *merged.constraints,
    ])

    merged.hypotheses = _dedup_keep_order([
        *brief.candidate_hypotheses,
        *merged.hypotheses,
    ])

    if brief.strongest_alternative_interpretation and brief.strongest_alternative_interpretation.strip():
        merged.strongest_alternative_interpretation = brief.strongest_alternative_interpretation.strip()

    notes = list(merged.notes)
    notes.append("chat_brief_applied")

    if brief.candidate_hypotheses:
        notes.append("chat_brief_candidate_hypotheses_supplied")

    if brief.overturn_conditions:
        notes.append("chat_brief_overturn_conditions_supplied")

    if brief.desired_output_shape:
        notes.append("chat_brief_output_shape_supplied")

    merged.notes = _dedup_keep_order(notes)
    return merged


def node_parse(state: FlowState) -> FlowState:
    parsed = parse_prompt(state["text"])

    raw_brief = state.get("chat_brief")
    if raw_brief is not None:
        brief = ChatBrief.model_validate(raw_brief)
        parsed = _merge_chat_brief_into_parsed(parsed, brief)
        state["chat_brief"] = brief.model_dump()

    state["parsed"] = parsed.model_dump()
    return state


def node_route(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = resolve_route(state["text"], parsed)
    state["route"] = route.model_dump()
    return state


def node_preflight(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])

    classification = classify_task(state["text"], parsed)
    execution = plan_execution(state["text"], parsed, route, classification)
    constraints = check_constraints(parsed, classification, execution)

    base_preflight = run_preflight(state["text"], parsed, route.route)
    preflight = enrich_preflight_response(
        base=base_preflight,
        parsed=parsed,
        route=route,
        classification=classification,
        plan=execution,
        constraints=constraints,
    )

    state["classification"] = classification.model_dump()
    state["execution"] = execution.model_dump()
    state["constraints"] = constraints.model_dump()
    state["preflight"] = preflight.model_dump()
    return state


def build_graph():
    graph = StateGraph(FlowState)

    graph.add_node("parse", node_parse)
    graph.add_node("route", node_route)
    graph.add_node("preflight", node_preflight)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "route")
    graph.add_edge("route", "preflight")
    graph.add_edge("preflight", END)

    return graph.compile()
