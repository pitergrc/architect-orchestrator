from __future__ import annotations

from typing import TypedDict, NotRequired

from langgraph.graph import StateGraph, END

from .parser import parse_prompt
from .router import resolve_route
from .runtime import run_preflight
from .postcheck import run_postcheck
from .llm import generate_draft
from .orchestration_core import (
    classify_task,
    plan_execution,
    check_constraints,
    enrich_preflight_response,
    normalize_postcheck,
)
from .schemas import (
    ParseResponse,
    RouteResponse,
    PreflightResponse,
    PostcheckResponse,
    ClassifyResponse,
    ExecutionPlanResponse,
    ConstraintsCheckResponse,
)


SYSTEM_ROUTES = {"compatibility", "migration", "rfc", "release"}


class FlowState(TypedDict):
    text: str
    parsed: NotRequired[dict]
    route: NotRequired[dict]
    classification: NotRequired[dict]
    execution: NotRequired[dict]
    constraints: NotRequired[dict]
    preflight: NotRequired[dict]
    draft_answer: NotRequired[str]
    draft_failure: NotRequired[dict]
    postcheck: NotRequired[dict]


def _join_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return "; ".join(items)


def _build_draft_system_prompt(
    text: str,
    parsed: ParseResponse,
    route: RouteResponse,
    preflight: PreflightResponse,
) -> str:
    execution_flags = preflight.execution_flags or {}
    constraints_flags = preflight.constraints_flags or {}
    risk_flags = preflight.risk_flags or []

    lines: list[str] = [
        "Ты high-reliability аналитический ассистент.",
        "Твоя задача — помочь честно и полезно, а не дать просто самый гладкий ответ.",
        "Сохрани главный ask и не теряй secondary asks.",
        "Не выдавай популярный, удобный или поверхностный ответ за лучший подтвержденный.",
        "Не скрывай значимые unknowns, если они влияют на вывод.",
        "",
        f"Route: {route.route}",
        f"Main ask: {parsed.main_ask}",
        f"Secondary asks: {_join_or_none(parsed.secondary_asks)}",
        f"Constraints: {_join_or_none(parsed.constraints)}",
        f"User intent mode: {parsed.user_intent_mode}",
        f"Possible surface interpretation: {parsed.possible_surface_interpretation}",
        f"Strongest alternative interpretation: {parsed.strongest_alternative_interpretation}",
        f"Risk flags: {_join_or_none(risk_flags)}",
        "",
        "Обязательные правила ответа:",
        "- не теряй asks пользователя;",
        "- не закрывай задачу слишком рано;",
        "- если есть скрытая сложность, отрази её явно;",
        "- если есть сильная альтернатива, не игнорируй её;",
        "- если уверенность ограничена, покажи это честно;",
    ]

    if route.route in SYSTEM_ROUTES:
        lines.extend([
            "",
            "Так как route системный, отвечай в режиме архитектурного / системного аудита.",
            "Используй формулировки уровня architecture, runtime, constraints, modules, execution, validation.",
        ])

    if execution_flags.get("hidden_trap_screen_required"):
        lines.extend([
            "",
            "Перед выводом проверь, не является ли задача deceptively simple.",
            "Если поверхностная трактовка слабее альтернативной — скажи это прямо.",
            "Не ограничивайся первым очевидным ответом.",
        ])

    if execution_flags.get("popularity_check_required"):
        lines.extend([
            "",
            "Отделяй популярный ответ от лучше подтвержденного ответа.",
            "Если популярный ответ слабее подтвержденного, скажи это прямо.",
        ])

    if execution_flags.get("freshness_check_required"):
        lines.extend([
            "",
            "Если задача зависит от актуальности, не притворяйся, что текущие факты уже проверены.",
            "Если без внешней проверки честный final невозможен — скажи это.",
        ])

    if execution_flags.get("tool_mandatory"):
        lines.extend([
            "",
            "Для этой задачи внешняя проверка materially important.",
            "Без неё не выдавай unjustified final.",
            "Если нужно, дай provisional answer и укажи, что именно нужно проверить.",
        ])

    if parsed.user_intent_mode == "case_analysis":
        lines.extend([
            "",
            "Так как это case analysis, желательно дать:",
            "- краткое понимание проблемы",
            "- варианты",
            "- trade-offs",
            "- рабочий вывод",
            "- риски",
        ])

    if parsed.user_intent_mode == "decision_support":
        lines.extend([
            "",
            "Так как это decision support, желательно дать:",
            "- варианты",
            "- плюсы/минусы",
            "- что может перевернуть решение",
            "- лучший текущий выбор",
        ])

    if parsed.user_intent_mode == "tutor":
        lines.extend([
            "",
            "Так как пользователь просит помощь как новичок, объясняй ясно и по шагам.",
        ])

    if constraints_flags.get("status_ceiling") in {"provisional", "partial", "blocked"}:
        lines.extend([
            "",
            f"Важное ограничение: honest status ceiling is {constraints_flags.get('status_ceiling')}.",
            "Не делай вид, что ответ final, если условия этого не позволяют.",
        ])

    lines.extend([
        "",
        "Пиши на языке пользователя.",
        "Отвечай по существу.",
    ])

    return "\n".join(lines)


def node_parse(state: FlowState) -> FlowState:
    parsed = parse_prompt(state["text"])
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


def node_draft(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    preflight = PreflightResponse.model_validate(state["preflight"])

    prompt = _build_draft_system_prompt(
        text=state["text"],
        parsed=parsed,
        route=route,
        preflight=preflight,
    )

    draft = generate_draft(state["text"], system_prompt=prompt)

    if draft.ok:
        state["draft_answer"] = draft.text
        state["draft_failure"] = {
            "ok": True,
            "provider": draft.provider,
            "model": draft.model,
        }
        return state

    state["draft_answer"] = ""
    state["draft_failure"] = {
        "ok": False,
        "provider": draft.provider,
        "model": draft.model,
        "error_type": draft.error_type,
        "error_message": draft.error_message,
    }
    return state


def node_postcheck(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    classification = ClassifyResponse.model_validate(state["classification"])
    execution = ExecutionPlanResponse.model_validate(state["execution"])
    constraints = ConstraintsCheckResponse.model_validate(state["constraints"])

    draft_failure = state.get("draft_failure") or {}

    if not draft_failure.get("ok", True):
        post = PostcheckResponse(
            ok=False,
            events=["llm_backend_unavailable"],
            missing_asks=[],
            notes=[
                f"draft generation failed: {draft_failure.get('error_type', 'unknown_error')}",
                draft_failure.get("error_message", "no error details available"),
            ],
            issues=["draft_generation_failed"],
            status_too_strong=False,
            repair_needed=False,
            recommended_status="blocked",
        )
        state["postcheck"] = post.model_dump()
        return state

    route = RouteResponse.model_validate(state["route"])

    post = run_postcheck(state["text"], parsed, route.route, state.get("draft_answer", ""))
    post = normalize_postcheck(
        out=post,
        parsed=parsed,
        classification=classification,
        plan=execution,
        constraints=constraints,
    )

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
