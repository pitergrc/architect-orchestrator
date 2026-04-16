from __future__ import annotations

from .schemas import PostcheckResponse, ParseResponse, RouteType


SYSTEM_ROUTES = {"compatibility", "migration", "rfc", "release"}


def _contains_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)


def _has_reasoning_signal(lower_answer: str) -> bool:
    markers = [
        "потому",
        "зависит",
        "однако",
        "но",
        "с другой стороны",
        "если",
        "при этом",
        "альтернатив",
        "не всегда",
        "может",
        "риск",
        "огранич",
    ]
    return _contains_any(lower_answer, markers)


def _has_uncertainty_or_scope_signal(lower_answer: str) -> bool:
    markers = [
        "зависит",
        "если",
        "при условии",
        "не всегда",
        "возмож",
        "непол",
        "огранич",
        "точный ответ зависит",
        "нужно проверить",
        "нельзя уверенно",
    ]
    return _contains_any(lower_answer, markers)


def _has_system_audit_signal(lower_answer: str) -> bool:
    markers = [
        "system audit",
        "системн",
        "архитектур",
        "runtime",
        "оркестратор",
        "модул",
        "контракт",
        "схем",
        "конфликт",
        "валидац",
    ]
    return _contains_any(lower_answer, markers)


def _mentions_alternative_or_distinction(lower_answer: str) -> bool:
    markers = [
        "альтернатив",
        "другая интерпретац",
        "другая трактов",
        "поверхност",
        "на первый взгляд",
        "популярн",
        "лучше подтвержден",
        "best-supported",
        "consensus",
    ]
    return _contains_any(lower_answer, markers)


def run_postcheck(text: str, parsed: ParseResponse, route: RouteType, answer: str) -> PostcheckResponse:
    lower_answer = answer.lower()
    events: list[str] = []
    missing_asks: list[str] = []
    notes: list[str] = []
    issues: list[str] = []

    # 1) Ask coverage
    if parsed.main_ask and parsed.main_ask.lower()[:20] not in lower_answer:
        notes.append("main ask not echoed directly; manual review recommended")

    for ask in parsed.secondary_asks:
        first = ask.lower()[:18]
        if first and first not in lower_answer:
            missing_asks.append(ask)

    if missing_asks:
        events.append("lost_ask")
        issues.append("secondary asks not visibly covered")

    # 2) Hidden-trap awareness
    if parsed.needs_hidden_trap_screen:
        if not _has_reasoning_signal(lower_answer):
            events.append("hidden_trap_missed")
            issues.append("answer may be too direct for a hidden-trap-prone task")

        if not _mentions_alternative_or_distinction(lower_answer):
            notes.append("hidden-trap task without explicit alternative/distinction wording")

    # 3) Over-strong answers
    status_too_strong = False
    repair_needed = False
    recommended_status: str | None = "final"

    if parsed.needs_hidden_trap_screen and not _has_uncertainty_or_scope_signal(lower_answer):
        status_too_strong = True
        repair_needed = True
        recommended_status = "provisional"
        issues.append("answer may be too final for a hidden-complexity task")

    # 4) System route checks
    if route in SYSTEM_ROUTES:
        if not _has_system_audit_signal(lower_answer):
            events.append("system_audit_framing_missing")
            issues.append("system-level route without explicit system or architecture framing")
            if recommended_status == "final":
                recommended_status = "provisional"

    # 5) User-intent-sensitive checks
    if parsed.user_intent_mode in {"case_analysis", "decision_support"}:
        if not _has_reasoning_signal(lower_answer):
            notes.append("case-analysis or decision-support response may be too shallow")

    # 6) If there are real issues, ok should be false
    ok = len(events) == 0 and not status_too_strong

    return PostcheckResponse(
        ok=ok,
        events=events,
        missing_asks=missing_asks,
        notes=notes,
        issues=issues,
        status_too_strong=status_too_strong,
        repair_needed=repair_needed,
        recommended_status=recommended_status,
    )
