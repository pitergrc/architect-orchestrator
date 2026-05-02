from __future__ import annotations

import json
import re
from typing import Any, TypedDict, NotRequired

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
    groq_assist: NotRequired[dict]


def _dedup_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for item in items:
        if not isinstance(item, str):
            continue

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


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()

    if not text:
        return {}

    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced_match:
        try:
            data = json.loads(fenced_match.group(1))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    object_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if object_match:
        try:
            data = json.loads(object_match.group(0))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    return {}


def _safe_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])

    if not isinstance(value, list):
        return []

    out: list[str] = []
    for item in value:
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                out.append(cleaned)

    return _dedup_keep_order(out)


def _build_groq_assist_prompt(parsed: ParseResponse, route: RouteResponse, preflight: dict) -> str:
    risk_flags = preflight.get("risk_flags", []) or []
    execution_flags = preflight.get("execution_flags", {}) or {}
    constraints_flags = preflight.get("constraints_flags", {}) or {}

    return f"""
Ты внутренний аналитический assist-слой оркестратора.

Ты НЕ пишешь финальный ответ пользователю.
Ты НЕ определяешь execution reality.
Ты НЕ решаешь, был ли action вызван.
Ты НЕ определяешь final status.
Ты НЕ подменяешь ChatGPT.

Твоя задача — усилить анализ:
- альтернативные трактовки
- нестандартные варианты
- риски
- условия, которые могут перевернуть вывод

Верни только JSON-объект без markdown и без текста вокруг:

{{
  "alt_interpretations": [],
  "nonstandard_options": [],
  "risks": [],
  "overturn_conditions": [],
  "notes": []
}}

Жёсткие запреты:
- не пиши “I cannot send HTTP request”
- не пиши “I can’t call tools”
- не утверждай, что action недоступен
- не путай endpoint path и operationId
- не делай финальный ответ

Контекст:
Main ask: {parsed.main_ask}
Secondary asks: {parsed.secondary_asks}
Constraints: {parsed.constraints}
Route: {route.route}
Route reasons: {route.reasons}
User intent mode: {parsed.user_intent_mode}
Surface interpretation: {parsed.possible_surface_interpretation}
Strongest alternative interpretation: {parsed.strongest_alternative_interpretation}
Risk flags: {risk_flags}
Execution flags: {execution_flags}
Constraints flags: {constraints_flags}
"""


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


def node_groq_assist(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    preflight = state.get("preflight", {})

    prompt = _build_groq_assist_prompt(
        parsed=parsed,
        route=route,
        preflight=preflight,
    )

    result = generate_draft(
        user_text=state["text"],
        system_prompt=prompt,
    )

    if not result.ok:
        state["groq_assist"] = {
            "alt_interpretations": [],
            "nonstandard_options": [],
            "risks": [],
            "overturn_conditions": [],
            "notes": [
                "groq_assist_unavailable",
                f"error_type:{result.error_type or 'unknown'}",
                f"error_message:{result.error_message or 'none'}",
            ],
        }
        return state

    data = _extract_json_object(result.text)

    state["groq_assist"] = {
        "alt_interpretations": _safe_list(data, "alt_interpretations"),
        "nonstandard_options": _safe_list(data, "nonstandard_options"),
        "risks": _safe_list(data, "risks"),
        "overturn_conditions": _safe_list(data, "overturn_conditions"),
        "notes": _dedup_keep_order([
            *_safe_list(data, "notes"),
            f"provider:{result.provider}",
            f"model:{result.model}",
        ]),
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


