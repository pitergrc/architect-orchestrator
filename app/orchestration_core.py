from __future__ import annotations

from .schemas import (
    ParseResponse,
    RouteResponse,
    ClassifyResponse,
    ExecutionPlanResponse,
    ConstraintsCheckResponse,
    PreflightResponse,
    PostcheckResponse,
)


def _detect_primary_task_class(text: str, parsed: ParseResponse) -> str:
    lower = text.lower()

    if any(k in lower for k in ["ошибка", "баг", "debug", "python", "код", "stacktrace", "traceback"]):
        return "coding"

    if any(k in lower for k in ["докажи", "вычисли", "реши", "формула", "уравнение", "процент", "вероятность"]):
        return "formal"

    if any(k in lower for k in ["симптом", "диагноз", "не работает", "почему не работает", "причина сбоя"]):
        return "diagnosis"

    if any(k in lower for k in ["перепиши", "сократи", "перефразируй", "переведи", "transform", "rewrite"]):
        return "transformation"

    if parsed.user_intent_mode in {"case_analysis", "decision_support"}:
        return "planning"

    return "research"


def _detect_secondary_task_class(text: str, primary: str) -> str | None:
    lower = text.lower()

    if primary == "research" and any(k in lower for k in ["что делать", "дай план", "пошагово", "стратег", "рекомендац"]):
        return "planning"

    if primary == "planning" and any(k in lower for k in ["исследуй", "сравни", "найди данные", "проверь"]):
        return "research"

    if primary == "coding" and any(k in lower for k in ["почему", "корень проблемы", "диагноз"]):
        return "diagnosis"

    return None


def _detect_difficulty(parsed: ParseResponse, primary: str) -> str:
    if parsed.misread_risk in {"scope_collapse", "hidden_complexity"}:
        return "high"

    if parsed.needs_hidden_trap_screen:
        return "high"

    if len(parsed.secondary_asks) >= 2:
        return "high"

    if primary in {"coding", "formal", "diagnosis"}:
        return "medium"

    return "medium"


def _detect_stakes(text: str, parsed: ParseResponse) -> str:
    lower = text.lower()

    if any(k in lower for k in ["здоров", "медицин", "финанс", "деньги", "юрид", "закон", "безопасн"]):
        return "high"

    if parsed.user_intent_mode in {"decision_support"}:
        return "high"

    return "medium"


def _detect_popularity_bias_risk(text: str) -> str:
    lower = text.lower()

    if any(k in lower for k in ["все говорят", "общеизвест", "принято считать", "популярн", "консенсус"]):
        return "high"

    if "правда ли" in lower:
        return "medium"

    return "low"


def _detect_freshness_need(text: str) -> str:
    lower = text.lower()

    if any(k in lower for k in ["сейчас", "на данный момент", "последние", "актуаль", "сегодня", "обновления", "новости"]):
        return "high"

    if any(k in lower for k in ["версия", "цена", "ceo", "руководитель", "должность", "релиз"]):
        return "medium"

    return "low"


def _detect_tool_need_likelihood(text: str, parsed: ParseResponse, freshness_need: str) -> str:
    lower = text.lower()

    if freshness_need in {"medium", "high"}:
        return "high"

    if any(k in lower for k in ["pdf", "файл", "документ", "таблица", "excel", "csv", "json"]):
        return "high"

    if any(k in lower for k in ["посчитай", "вычисли", "%", "процент", "сравни числа", "статистик"]):
        return "high"

    if parsed.needs_hidden_trap_screen:
        return "medium"

    return "low"


def classify_task(text: str, parsed: ParseResponse) -> ClassifyResponse:
    primary = _detect_primary_task_class(text, parsed)
    secondary = _detect_secondary_task_class(text, primary)
    difficulty = _detect_difficulty(parsed, primary)
    stakes = _detect_stakes(text, parsed)
    popularity_bias_risk = _detect_popularity_bias_risk(text)
    freshness_need = _detect_freshness_need(text)
    tool_need_likelihood = _detect_tool_need_likelihood(text, parsed, freshness_need)

    if parsed.needs_hidden_trap_screen or parsed.misread_risk == "hidden_complexity":
        hidden_trap_risk = "high"
    elif parsed.misread_risk == "scope_collapse":
        hidden_trap_risk = "medium"
    else:
        hidden_trap_risk = "low"

    if primary == "research" or freshness_need in {"medium", "high"}:
        evidence_debt = "medium"
    else:
        evidence_debt = "low"

    if hidden_trap_risk == "high" and popularity_bias_risk == "high":
        evidence_debt = "high"

    deceptive_simple_risk = "high" if parsed.needs_hidden_trap_screen else "low"

    route_confidence = "medium"
    if primary in {"coding", "formal", "diagnosis"}:
        route_confidence = "high"

    return ClassifyResponse(
        primary_task_class=primary,
        secondary_task_class=secondary,
        difficulty=difficulty,
        stakes=stakes,
        route_confidence=route_confidence,
        re_route_allowed=True,
        hidden_trap_risk=hidden_trap_risk,
        popularity_bias_risk=popularity_bias_risk,
        evidence_debt=evidence_debt,
        freshness_need=freshness_need,
        tool_need_likelihood=tool_need_likelihood,
        deceptive_simple_risk=deceptive_simple_risk,
    )


def plan_execution(
    text: str,
    parsed: ParseResponse,
    route: RouteResponse,
    classification: ClassifyResponse,
) -> ExecutionPlanResponse:
    recommended_tools: list[str] = []
    reason_tools_matter: list[str] = []

    tool_mandatory = False
    freshness_check_required = False
    popularity_check_required = classification.popularity_bias_risk in {"medium", "high"}
    hidden_trap_screen_required = (
        classification.hidden_trap_risk in {"medium", "high"}
        or classification.deceptive_simple_risk in {"medium", "high"}
    )

    if classification.freshness_need in {"medium", "high"}:
        freshness_check_required = True
        tool_mandatory = True
        recommended_tools.append("web")
        reason_tools_matter.append("freshness matters")

    lower = text.lower()

    if classification.tool_need_likelihood == "high":
        if any(k in lower for k in ["pdf", "файл", "документ", "таблица", "excel", "csv", "json"]):
            recommended_tools.append("file_inspection")
            reason_tools_matter.append("document or file inspection matters")

        if any(k in lower for k in ["посчитай", "вычисли", "%", "процент", "статистик", "формула"]):
            recommended_tools.append("calculator_or_code")
            reason_tools_matter.append("exact calculation matters")

    if classification.evidence_debt == "high" and "web" not in recommended_tools:
        recommended_tools.append("web")
        reason_tools_matter.append("support quality matters")
        tool_mandatory = True

    execution_mode = "standard"
    if route.default_depth_floor == "deep":
        execution_mode = "deep"

    if (
        classification.stakes == "high"
        or classification.hidden_trap_risk == "high"
        or classification.popularity_bias_risk == "high"
    ):
        execution_mode = "deep"

    critic_required = False
    if (
        classification.stakes == "high"
        or classification.hidden_trap_risk == "high"
        or classification.popularity_bias_risk == "high"
    ):
        critic_required = True

    verifier_required = classification.difficulty != "low"

    deliverable_contract = parsed.deliverable_hint or "answer"
    if deliverable_contract not in {"answer", "plan", "spec", "memo", "patch", "report", "artifact"}:
        deliverable_contract = "answer"

    deployability_check_required = deliverable_contract in {"spec", "patch", "artifact"}

    minimum_status_ceiling_without_tools = "final"
    if tool_mandatory:
        minimum_status_ceiling_without_tools = "provisional"

    max_passes = 2
    max_repair_cycles = 1

    if execution_mode == "deep":
        max_passes = 3

    if classification.stakes == "high":
        max_repair_cycles = 2

    dedup_tools: list[str] = []
    for tool in recommended_tools:
        if tool not in dedup_tools:
            dedup_tools.append(tool)

    dedup_reasons: list[str] = []
    for reason in reason_tools_matter:
        if reason not in dedup_reasons:
            dedup_reasons.append(reason)

    return ExecutionPlanResponse(
        execution_mode=execution_mode,
        tool_mandatory=tool_mandatory,
        verifier_required=verifier_required,
        critic_required=critic_required,
        carryover_required=False,
        constraints_check_required=True,
        deployability_check_required=deployability_check_required,
        max_passes=max_passes,
        max_repair_cycles=max_repair_cycles,
        deliverable_contract=deliverable_contract,
        hidden_trap_screen_required=hidden_trap_screen_required,
        popularity_check_required=popularity_check_required,
        freshness_check_required=freshness_check_required,
        minimum_status_ceiling_without_tools=minimum_status_ceiling_without_tools,
        recommended_tools=dedup_tools,
        reason_tools_matter=dedup_reasons,
    )


def check_constraints(
    parsed: ParseResponse,
    classification: ClassifyResponse,
    plan: ExecutionPlanResponse,
) -> ConstraintsCheckResponse:
    deployability_risk = "low"
    artifact_validation_required = False

    if plan.deliverable_contract in {"spec", "patch", "artifact"}:
        deployability_risk = "medium"
        artifact_validation_required = True

    status_ceiling = "final"
    orchestration_limits: list[str] = []

    if plan.tool_mandatory:
        status_ceiling = "provisional"
        orchestration_limits.append("final_requires_tools")

    if classification.evidence_debt == "high" and not plan.tool_mandatory:
        status_ceiling = "provisional"

    return ConstraintsCheckResponse(
        hard_constraints=parsed.constraints,
        deployability_risk=deployability_risk,
        artifact_validation_required=artifact_validation_required,
        known_environment_limits=[],
        orchestration_limits=orchestration_limits,
        status_ceiling=status_ceiling,
    )


def enrich_preflight_response(
    base: PreflightResponse,
    parsed: ParseResponse,
    route: RouteResponse,
    classification: ClassifyResponse,
    plan: ExecutionPlanResponse,
    constraints: ConstraintsCheckResponse,
) -> PreflightResponse:
    out = base.model_copy(deep=True)

    out.task_profile = {
        "primary_task_class": classification.primary_task_class,
        "secondary_task_class": classification.secondary_task_class,
        "difficulty": classification.difficulty,
        "stakes": classification.stakes,
        "user_intent_mode": parsed.user_intent_mode,
        "hidden_trap_risk": classification.hidden_trap_risk,
        "popularity_bias_risk": classification.popularity_bias_risk,
        "evidence_debt": classification.evidence_debt,
        "freshness_need": classification.freshness_need,
        "tool_need_likelihood": classification.tool_need_likelihood,
        "route": route.route,
        "possible_surface_interpretation": parsed.possible_surface_interpretation,
        "strongest_alternative_interpretation": parsed.strongest_alternative_interpretation,
    }

    out.execution_flags = {
        "execution_mode": plan.execution_mode,
        "tool_mandatory": plan.tool_mandatory,
        "verifier_required": plan.verifier_required,
        "critic_required": plan.critic_required,
        "carryover_required": plan.carryover_required,
        "hidden_trap_screen_required": plan.hidden_trap_screen_required,
        "popularity_check_required": plan.popularity_check_required,
        "freshness_check_required": plan.freshness_check_required,
        "recommended_tools": plan.recommended_tools,
        "reason_tools_matter": plan.reason_tools_matter,
        "minimum_status_ceiling_without_tools": plan.minimum_status_ceiling_without_tools,
    }

    out.constraints_flags = {
        "constraints_check_required": plan.constraints_check_required,
        "deployability_check_required": plan.deployability_check_required,
        "deployability_risk": constraints.deployability_risk,
        "artifact_validation_required": constraints.artifact_validation_required,
        "status_ceiling": constraints.status_ceiling,
        "hard_constraints": constraints.hard_constraints,
        "known_environment_limits": constraints.known_environment_limits,
        "orchestration_limits": constraints.orchestration_limits,
    }

    out.deliverable_contract = plan.deliverable_contract

    out.risk_flags = [
        f"hidden_trap_risk:{classification.hidden_trap_risk}",
        f"popularity_bias_risk:{classification.popularity_bias_risk}",
        f"evidence_debt:{classification.evidence_debt}",
        f"freshness_need:{classification.freshness_need}",
        f"tool_need_likelihood:{classification.tool_need_likelihood}",
    ]

    return out


def normalize_postcheck(
    out: PostcheckResponse,
    parsed: ParseResponse,
    classification: ClassifyResponse,
    plan: ExecutionPlanResponse,
    constraints: ConstraintsCheckResponse | None = None,
) -> PostcheckResponse:
    normalized = out.model_copy(deep=True)

    if normalized.recommended_status is None:
        normalized.recommended_status = "final"

    if parsed.needs_hidden_trap_screen and normalized.recommended_status == "final":
        normalized.status_too_strong = True
        normalized.repair_needed = True
        normalized.recommended_status = "provisional"
        if "hidden_trap_screen_was_required" not in normalized.issues:
            normalized.issues.append("hidden_trap_screen_was_required")
        if "hidden_trap_missed" not in normalized.events:
            normalized.events.append("hidden_trap_missed")

    if plan.tool_mandatory and normalized.recommended_status == "final":
        normalized.status_too_strong = True
        normalized.repair_needed = True
        normalized.recommended_status = "provisional"
        if "tool_required_for_honest_final" not in normalized.issues:
            normalized.issues.append("tool_required_for_honest_final")
        if "tool_needed_but_skipped" not in normalized.events:
            normalized.events.append("tool_needed_but_skipped")

    if constraints is not None:
        status_ceiling = constraints.status_ceiling
        if status_ceiling in {"provisional", "partial", "blocked"} and normalized.recommended_status == "final":
            normalized.status_too_strong = True
            normalized.repair_needed = True
            normalized.recommended_status = status_ceiling
            if "status_ceiling_enforced" not in normalized.issues:
                normalized.issues.append("status_ceiling_enforced")

    if classification.popularity_bias_risk == "high" and normalized.recommended_status == "final":
        normalized.recommended_status = "provisional"
        if "popularity_support_distinction_needed" not in normalized.issues:
            normalized.issues.append("popularity_support_distinction_needed")

    if normalized.status_too_strong:
        normalized.ok = False

    return normalized
