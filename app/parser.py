from __future__ import annotations

import re
from .schemas import ParseResponse


SPLIT_MARKERS = [
    "сначала",
    "потом",
    "затем",
    "отдельно",
    "а еще",
    "и еще",
    "также",
    "не только",
]

STYLE_MARKERS = [
    "коротко",
    "подробно",
    "пошагово",
    "по шагам",
    "детально",
]

REFERENCE_MARKERS = [
    "как справочник",
    "объясни",
    "расскажи",
    "что это",
    "в чем разница",
]

CASE_ANALYSIS_MARKERS = [
    "разбери кейс",
    "разбор кейса",
    "проанализируй",
    "сделай аудит",
    "дай план",
    "что делать",
]

TUTOR_MARKERS = [
    "научи",
    "объясни как",
    "по шагам для новичка",
    "я не разбираюсь",
]

DECISION_SUPPORT_MARKERS = [
    "что выбрать",
    "что лучше",
    "какой вариант",
    "стоит ли",
    "как правильно",
]

HIDDEN_TRAP_MARKERS = [
    "неочевид",
    "скрыт",
    "ловуш",
    "кажется прост",
    "на вид обычн",
    "реальный ответ",
    "не популярный ответ",
    "не обманчив",
]

POPULARITY_MARKERS = [
    "популярн",
    "общеизвест",
    "все говорят",
    "принято считать",
    "консенсус",
]


def _split_candidate_parts(text: str) -> list[str]:
    parts = re.split(r"\?|\n|;|\.\s+", text)
    cleaned = [p.strip(" -—\t") for p in parts if p and p.strip()]
    return cleaned or [text.strip()]


def _contains_any(lower: str, markers: list[str]) -> bool:
    return any(marker in lower for marker in markers)


def _detect_user_intent_mode(lower: str) -> str:
    scores = {
        "reference": 0,
        "case_analysis": 0,
        "tutor": 0,
        "decision_support": 0,
    }

    if _contains_any(lower, REFERENCE_MARKERS):
        scores["reference"] += 1

    if _contains_any(lower, CASE_ANALYSIS_MARKERS):
        scores["case_analysis"] += 1

    if _contains_any(lower, TUTOR_MARKERS):
        scores["tutor"] += 1

    if _contains_any(lower, DECISION_SUPPORT_MARKERS):
        scores["decision_support"] += 1

    best_mode = max(scores, key=scores.get)
    if scores[best_mode] == 0:
        return "mixed"
    return best_mode


def _detect_surface_and_alternative(text: str, lower: str) -> tuple[str, str]:
    surface = text.strip()

    if "почему" in lower:
        alt = "user may be asking for underlying mechanism, not just a direct explanation"
    elif "как" in lower:
        alt = "user may need an action plan or decision workflow, not just a description"
    elif "что" in lower:
        alt = "user may need clarification of scope or comparison, not only a definition"
    elif "можно ли" in lower or "стоит ли" in lower:
        alt = "user may be asking for recommendation under constraints, not only yes/no"
    else:
        alt = "user may have a broader analytical goal than the surface wording suggests"

    return surface, alt


def _detect_hidden_trap_screen(lower: str) -> bool:
    if _contains_any(lower, HIDDEN_TRAP_MARKERS):
        return True

    if _contains_any(lower, POPULARITY_MARKERS):
        return True

    if "правда ли" in lower:
        return True

    if "кажется" in lower or "похоже" in lower:
        return True

    return False


def _detect_misread_risk(
    lower: str,
    multi: bool,
    examples: list[str],
    policy_or_core_change: bool,
    needs_hidden_trap_screen: bool,
) -> str:
    if multi:
        return "scope_collapse"

    if needs_hidden_trap_screen:
        return "hidden_complexity"

    if examples and not policy_or_core_change:
        return "medium"

    if "совместимость" in lower and "какая" not in lower:
        return "medium"

    return "low"


def _extract_constraints(lower: str) -> list[str]:
    constraints: list[str] = []

    if "бесплатно" in lower:
        constraints.append("must be free")

    if re.search(r"\bбез\s+\S+", lower):
        constraints.append("negative constraint detected")

    return constraints


def parse_prompt(text: str) -> ParseResponse:
    text = text.strip()
    lower = text.lower()
    parts = _split_candidate_parts(text)

    secondary: list[str] = []
    examples: list[str] = []
    hypotheses: list[str] = []
    constraints: list[str] = _extract_constraints(lower)
    style: list[str] = []
    notes: list[str] = []

    for p in parts[1:]:
        if len(p) > 3:
            secondary.append(p)

    if "например" in lower or "пример" in lower:
        examples.append("user provided example detected")

    if "может" in lower or "похоже" in lower or "кажется" in lower:
        hypotheses.append("user hypothesis detected")

    if _contains_any(lower, STYLE_MARKERS):
        style.append("style preference detected")

    multi = any(m in lower for m in SPLIT_MARKERS) or len(parts) > 1
    if multi:
        notes.append("multi-part request detected")

    policy_or_core_change = any(
        token in lower
        for token in ["измени core", "измени policy", "rfc", "перепиши core", "сменить law"]
    )

    user_intent_mode = _detect_user_intent_mode(lower)
    possible_surface_interpretation, strongest_alternative_interpretation = _detect_surface_and_alternative(text, lower)
    needs_hidden_trap_screen = _detect_hidden_trap_screen(lower)

    misread_risk = _detect_misread_risk(
        lower=lower,
        multi=multi,
        examples=examples,
        policy_or_core_change=policy_or_core_change,
        needs_hidden_trap_screen=needs_hidden_trap_screen,
    )

    main_ask = parts[0] if parts else text

    return ParseResponse(
        main_ask=main_ask,
        secondary_asks=secondary,
        constraints=constraints,
        examples=examples,
        hypotheses=hypotheses,
        style_preferences=style,
        policy_or_core_change_request=policy_or_core_change,
        misread_risk=misread_risk,
        deliverable_hint=None,
        notes=notes,
        possible_surface_interpretation=possible_surface_interpretation,
        strongest_alternative_interpretation=strongest_alternative_interpretation,
        needs_hidden_trap_screen=needs_hidden_trap_screen,
        user_intent_mode=user_intent_mode,
    )
