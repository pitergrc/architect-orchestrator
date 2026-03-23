from __future__ import annotations

from .schemas import PostcheckResponse, ParseResponse, RouteType


def run_postcheck(text: str, parsed: ParseResponse, route: RouteType, answer: str) -> PostcheckResponse:
    lower_answer = answer.lower()
    events: list[str] = []
    missing_asks: list[str] = []
    notes: list[str] = []

    if parsed.main_ask and parsed.main_ask.lower()[:20] not in lower_answer:
        notes.append("main ask not echoed directly; manual review recommended")

    for ask in parsed.secondary_asks:
        first = ask.lower()[:18]
        if first and first not in lower_answer:
            missing_asks.append(ask)

    if missing_asks:
        events.append("lost_ask")

    if parsed.misread_risk == "example_to_policy" and "policy" in lower_answer:
        events.append("example_to_policy")

    if route in {"compatibility", "migration", "rfc", "release"}:
        if "system audit" not in lower_answer.lower() and "system audit" not in answer:
            notes.append("system-level route without explicit audit wording")

    ok = len(events) == 0
    return PostcheckResponse(ok=ok, events=events, missing_asks=missing_asks, notes=notes)
