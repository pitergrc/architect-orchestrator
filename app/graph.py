from __future__ import annotations

from typing import TypedDict, NotRequired

from langgraph.graph import StateGraph, END

from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .postcheck import run_postcheck
from .llm import ask_ollama


class FlowState(TypedDict):
    text: str
    parsed: NotRequired[dict]
    route: NotRequired[dict]
    preflight: NotRequired[dict]
    draft_answer: NotRequired[str]
    postcheck: NotRequired[dict]


def node_parse(state: FlowState) -> FlowState:
    parsed = parse_prompt(state["text"])
    state["parsed"] = parsed.model_dump()
    return state


def node_route(state: FlowState) -> FlowState:
    from .schemas import ParseResponse
    parsed = ParseResponse.model_validate(state["parsed"])
    route = resolve_route(state["text"], parsed)
    state["route"] = route.model_dump()
    return state


def node_preflight(state: FlowState) -> FlowState:
    from .schemas import ParseResponse, RouteResponse
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    preflight = run_preflight(state["text"], parsed, route.route)
    state["preflight"] = preflight.model_dump()
    return state


def node_draft(state: FlowState) -> FlowState:
    route = state["route"]["route"]
    parsed = state["parsed"]
    prompt = (
        "Ты оркеструемый аналитический ассистент. "
        "Сохрани главный ask, не теряй secondary asks, не превращай пример в policy. "
        f"Route={route}. Main ask={parsed['main_ask']}. Secondary asks={parsed['secondary_asks']}."
    )
    state["draft_answer"] = ask_ollama(state["text"], system_prompt=prompt)
    return state


def node_postcheck(state: FlowState) -> FlowState:
    from .schemas import ParseResponse, RouteResponse
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    post = run_postcheck(state["text"], parsed, route.route, state.get("draft_answer", ""))
    state["postcheck"] = post.model_dump()
    return state


def build_graph():
    graph = StateGraph(FlowState)
    graph.add_node("parse", node_parse)
    graph.add_node("route", node_route)
    graph.add_node("preflight", node_preflight)
    graph.add_node("draft", node_draft)
    graph.add_node("postcheck", node_postcheck)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "route")
    graph.add_edge("route", "preflight")
    graph.add_edge("preflight", "draft")
    graph.add_edge("draft", "postcheck")
    graph.add_edge("postcheck", END)

    return graph.compile()
