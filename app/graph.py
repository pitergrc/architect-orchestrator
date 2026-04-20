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
    ChatBrief,
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
    repair_count: NotRequired[int]
    chat_brief: NotRequired[dict]


def _join_or_none(items: list[str]) -> str:
    if not items:
        return "none"
    return "; ".join(items)


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


def _append_chat_brief_lines(lines: list[str], brief: ChatBrief | None) -> None:
    if brief is None:
        return

    lines.extend([
        "",
        "Upstream chat-side brief from stronger model:",
        f"- Chat-brief main ask: {brief.main_ask or 'none'}",
        f"- Chat-brief secondary asks: {_join_or_none(brief.secondary_asks)}",
        f"- Chat-brief constraints: {_join_or_none(brief.constraints)}",
        f"- Chat-brief strongest alternative: {brief.strongest_alternative_interpretation or 'none'}",
        f"- Chat-brief candidate hypotheses: {_join_or_none(brief.candidate_hypotheses)}",
        f"- Chat-brief overturn conditions: {_join_or_none(brief.overturn_conditions)}",
        f"- Chat-brief desired output shape: {_join_or_none(brief.desired_output_shape)}",
        "",
        "Используй этот brief как high-value prior analysis от более сильной chat-side модели.",
        "Но не воспринимай его как абсолютную истину: сверяй его с задачей и не следуй ему слепо.",
    ])


def _build_draft_system_prompt(
    text: str,
    parsed: ParseResponse,
    route: RouteResponse,
    preflight: PreflightResponse,
    brief: ChatBrief | None = None,
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
    ]

    _append_chat_brief_lines(lines, brief)

    lines.extend([
        "",
        "Обязательные правила ответа:",
        "- не теряй asks пользователя;",
        "- не закрывай задачу слишком рано;",
        "- если есть скрытая сложность, отрази её явно;",
        "- если есть сильная альтернатива, не игнорируй её;",
        "- если уверенность ограничена, покажи это честно;",
    ])

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

    if brief is not None and brief.desired_output_shape:
        lines.extend([
            "",
            "Предпочтительная форма ответа от chat-side модели:",
            *[f"- {item}" for item in brief.desired_output_shape],
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


def _build_repair_system_prompt(
    parsed: ParseResponse,
    route: RouteResponse,
    preflight: PreflightResponse,
    repair_count: int,
    brief: ChatBrief | None = None,
) -> str:
    execution_flags = preflight.execution_flags or {}
    constraints_flags = preflight.constraints_flags or {}
    risk_flags = preflight.risk_flags or []

    lines: list[str] = [
        "Ты high-reliability аналитический ассистент.",
        "Ты не пишешь ответ с нуля: ты исправляешь предыдущий draft после verifier/postcheck.",
        "Сохрани полезные части draft, но исправь load-bearing defects.",
        "Не теряй главный ask и secondary asks.",
        "Не исправляй только стиль, если проблема содержательная.",
        "",
        f"Route: {route.route}",
        f"Main ask: {parsed.main_ask}",
        f"Secondary asks: {_join_or_none(parsed.secondary_asks)}",
        f"Constraints: {_join_or_none(parsed.constraints)}",
        f"User intent mode: {parsed.user_intent_mode}",
        f"Possible surface interpretation: {parsed.possible_surface_interpretation}",
        f"Strongest alternative interpretation: {parsed.strongest_alternative_interpretation}",
        f"Risk flags: {_join_or_none(risk_flags)}",
        f"Current repair attempt: {repair_count + 1}",
    ]

    _append_chat_brief_lines(lines, brief)

    lines.extend([
        "",
        "Требования к исправлению:",
        "- исправь пропущенные asks, если они потерялись;",
        "- если скрытая сложность не отражена, отрази её явно;",
        "- если есть сильная альтернатива, не игнорируй её;",
        "- если tools required, не притворяйся, что верификация уже была сделана;",
        "- если честный final невозможен, явно держи более слабый статус;",
        "- верни только улучшенный ответ пользователю, без служебных комментариев про repair loop.",
    ])

    if execution_flags.get("tool_mandatory"):
        lines.extend([
            "",
            "Важно: tool use is mandatory for an honest final.",
            "Если tools не были реально исполнены, не закрывай ответ как final.",
        ])

    if constraints_flags.get("status_ceiling") in {"provisional", "partial", "blocked"}:
        lines.extend([
            "",
            f"Важно: current honest status ceiling is {constraints_flags.get('status_ceiling')}.",
            "Нельзя поднимать статус выше этого потолка.",
        ])

    return "\n".join(lines)


def _build_repair_user_text(
    original_text: str,
    previous_draft: str,
    postcheck: PostcheckResponse,
) -> str:
    parts = [
        "ORIGINAL USER REQUEST:",
        original_text.strip(),
        "",
        "PREVIOUS DRAFT:",
        (previous_draft or "").strip() or "[empty]",
        "",
        "POSTCHECK EVENTS:",
        _join_or_none(postcheck.events),
        "",
        "POSTCHECK ISSUES:",
        _join_or_none(postcheck.issues),
        "",
        "POSTCHECK NOTES:",
        _join_or_none(postcheck.notes),
        "",
        "MISSING ASKS:",
        _join_or_none(postcheck.missing_asks),
        "",
        f"RECOMMENDED STATUS: {postcheck.recommended_status or 'unknown'}",
        "",
        "Перепиши draft так, чтобы устранить load-bearing defects, но не выдумывай, что tools уже были использованы, если этого не было.",
    ]
    return "\n".join(parts)


def _route_after_postcheck(state: FlowState) -> str:
    post = PostcheckResponse.model_validate(state["postcheck"])
    execution = ExecutionPlanResponse.model_validate(state["execution"])
    repair_count = state.get("repair_count", 0)

    if post.repair_needed and repair_count < execution.max_repair_cycles:
        return "repair"

    return "end"


def node_parse(state: FlowState) -> FlowState:
    parsed = parse_prompt(state["text"])

    raw_brief = state.get("chat_brief")
    if raw_brief is not None:
        brief = ChatBrief.model_validate(raw_brief)
        parsed = _merge_chat_brief_into_parsed(parsed, brief)
        state["chat_brief"] = brief.model_dump()

    state["parsed"] = parsed.model_dump()
    state.setdefault("repair_count", 0)
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

    brief = None
    if state.get("chat_brief") is not None:
        brief = ChatBrief.model_validate(state["chat_brief"])

    prompt = _build_draft_system_prompt(
        text=state["text"],
        parsed=parsed,
        route=route,
        preflight=preflight,
        brief=brief,
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


def node_repair(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    preflight = PreflightResponse.model_validate(state["preflight"])
    postcheck = PostcheckResponse.model_validate(state["postcheck"])

    brief = None
    if state.get("chat_brief") is not None:
        brief = ChatBrief.model_validate(state["chat_brief"])

    repair_count = state.get("repair_count", 0)

    repair_system_prompt = _build_repair_system_prompt(
        parsed=parsed,
        route=route,
        preflight=preflight,
        repair_count=repair_count,
        brief=brief,
    )

    repair_user_text = _build_repair_user_text(
        original_text=state["text"],
        previous_draft=state.get("draft_answer", ""),
        postcheck=postcheck,
    )

    repaired = generate_draft(repair_user_text, system_prompt=repair_system_prompt)
    state["repair_count"] = repair_count + 1

    if repaired.ok:
        state["draft_answer"] = repaired.text
        state["draft_failure"] = {
            "ok": True,
            "provider": repaired.provider,
            "model": repaired.model,
            "repair_attempt": state["repair_count"],
        }
        return state

    state["draft_failure"] = {
        "ok": False,
        "provider": repaired.provider,
        "model": repaired.model,
        "error_type": repaired.error_type,
        "error_message": repaired.error_message,
        "repair_attempt": state["repair_count"],
    }
    return state


def node_postcheck(state: FlowState) -> FlowState:
    parsed = ParseResponse.model_validate(state["parsed"])
    route = RouteResponse.model_validate(state["route"])
    classification = ClassifyResponse.model_validate(state["classification"])
    execution = ExecutionPlanResponse.model_validate(state["execution"])
    constraints = ConstraintsCheckResponse.model_validate(state["constraints"])

    draft_failure = state.get("draft_failure") or {}
    repair_count = state.get("repair_count", 0)
    best_available_draft = (state.get("draft_answer") or "").strip()

    if not draft_failure.get("ok", True):
        if best_available_draft:
            post = run_postcheck(state["text"], parsed, route.route, best_available_draft)
            post = normalize_postcheck(
                out=post,
                parsed=parsed,
                classification=classification,
                plan=execution,
                constraints=constraints,
            )
            post.ok = False
            post.repair_needed = False
            if post.recommended_status == "final":
                post.recommended_status = "provisional"
            if "repair_generation_failed" not in post.issues:
                post.issues.append("repair_generation_failed")
            post.notes.append(
                f"repair pass failed after {repair_count} attempt(s); returning best available previous draft"
            )
            post.notes.append(
                f"repair failure details: {draft_failure.get('error_type', 'unknown_error')} / "
                f"{draft_failure.get('error_message', 'no error details available')}"
            )
            state["postcheck"] = post.model_dump()
            return state

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

    post = run_postcheck(state["text"], parsed, route.route, state.get("draft_answer", ""))
    post = normalize_postcheck(
        out=post,
        parsed=parsed,
        classification=classification,
        plan=execution,
        constraints=constraints,
    )

    if post.repair_needed and repair_count >= execution.max_repair_cycles:
        post.repair_needed = False
        post.ok = False
        if post.recommended_status == "final":
            post.recommended_status = "provisional"
        if "repair_budget_exhausted" not in post.issues:
            post.issues.append("repair_budget_exhausted")
        post.notes.append(
            f"repair budget exhausted after {repair_count} attempt(s); returning best available downgraded result"
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
    graph.add_node("repair", node_repair)

    graph.set_entry_point("parse")
    graph.add_edge("parse", "route")
    graph.add_edge("route", "preflight")
    graph.add_edge("preflight", "draft")
    graph.add_edge("draft", "postcheck")

    graph.add_conditional_edges(
        "postcheck",
        _route_after_postcheck,
        {
            "repair": "repair",
            "end": END,
        },
    )

    graph.add_edge("repair", "postcheck")

    return graph.compile()
