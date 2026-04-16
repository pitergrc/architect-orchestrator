from __future__ import annotations

from .schemas import AskItem, ParseResponse, PreflightResponse, RouteType


def build_ask_ledger(parsed: ParseResponse) -> list[AskItem]:
    asks: list[AskItem] = [
        AskItem(id="A1", text=parsed.main_ask, priority="high", droppable=False)
    ]

    for idx, item in enumerate(parsed.secondary_asks, start=2):
        asks.append(
            AskItem(
                id=f"A{idx}",
                text=item,
                priority="medium",
                droppable=False,
            )
        )

    return asks


def _detect_depth_floor(parsed: ParseResponse) -> str:
    if parsed.needs_hidden_trap_screen:
        return "deep"

    if parsed.misread_risk in {"scope_collapse", "hidden_complexity"}:
        return "deep"

    if parsed.user_intent_mode in {"case_analysis", "decision_support"}:
        return "deep"

    if parsed.secondary_asks:
        return "deep"

    return "standard"


def _build_risk_flags(parsed: ParseResponse) -> list[str]:
    risk_flags: list[str] = []

    if parsed.misread_risk not in {"low"}:
        risk_flags.append(f"misread_risk:{parsed.misread_risk}")

    if parsed.needs_hidden_trap_screen:
        risk_flags.append("hidden_trap_screen_required")

    if parsed.user_intent_mode in {"case_analysis", "decision_support"}:
        risk_flags.append(f"user_intent_mode:{parsed.user_intent_mode}")

    if parsed.policy_or_core_change_request:
        risk_flags.append("policy_or_core_change_request")

    if parsed.secondary_asks:
        risk_flags.append("multi_ask_structure")

    return risk_flags


def _build_task_profile(parsed: ParseResponse, route: RouteType) -> dict:
    return {
        "route": route,
        "main_ask_present": bool(parsed.main_ask.strip()),
        "secondary_ask_count": len(parsed.secondary_asks),
        "user_intent_mode": parsed.user_intent_mode,
        "needs_hidden_trap_screen": parsed.needs_hidden_trap_screen,
        "possible_surface_interpretation": parsed.possible_surface_interpretation,
        "strongest_alternative_interpretation": parsed.strongest_alternative_interpretation,
    }


def _build_execution_flags(parsed: ParseResponse, route: RouteType) -> dict:
    depth_floor = _detect_depth_floor(parsed)

    system_audit = route in {"compatibility", "migration", "rfc", "release"}

    return {
        "orchestration_required": True,
        "screening_required": True,
        "default_depth_floor": depth_floor,
        "can_use_light_internal_path": False,
        "verifier_default_on": True,
        "critic_candidate": depth_floor == "deep",
        "system_audit_mode": system_audit,
    }


def _build_constraints_flags(parsed: ParseResponse) -> dict:
    return {
        "constraints_present": bool(parsed.constraints),
        "raw_constraints": parsed.constraints,
        "deliverable_hint_present": parsed.deliverable_hint is not None,
    }


def run_preflight(text: str, parsed: ParseResponse, route: RouteType) -> PreflightResponse:
    defect_flags: list[str] = []

    if not parsed.main_ask.strip():
        defect_flags.append("missing_main_ask")

    if parsed.misread_risk in {"scope_collapse", "hidden_complexity"}:
        defect_flags.append(f"misread_risk:{parsed.misread_risk}")

    if parsed.needs_hidden_trap_screen:
        defect_flags.append("hidden_trap_screen_required")

    audit_hint = "response_audit"
    if route in {"compatibility", "migration", "rfc", "release"}:
        audit_hint = "system_audit"

    risk_flags = _build_risk_flags(parsed)
    task_profile = _build_task_profile(parsed, route)
    execution_flags = _build_execution_flags(parsed, route)
    constraints_flags = _build_constraints_flags(parsed)

    deliverable_contract = parsed.deliverable_hint or "answer"

    return PreflightResponse(
        defect_flags=defect_flags,
        ask_ledger=build_ask_ledger(parsed),
        audit_hint=audit_hint,
        task_profile=task_profile,
        execution_flags=execution_flags,
        constraints_flags=constraints_flags,
        deliverable_contract=deliverable_contract,
        risk_flags=risk_flags,
    )
