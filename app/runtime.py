from __future__ import annotations

from .schemas import AskItem, ParseResponse, PreflightResponse, RouteType


def build_ask_ledger(parsed: ParseResponse) -> list[AskItem]:
    asks: list[AskItem] = [
        AskItem(id="A1", text=parsed.main_ask, priority="high", droppable=False)
    ]
    for idx, item in enumerate(parsed.secondary_asks, start=2):
        asks.append(AskItem(id=f"A{idx}", text=item, priority="medium", droppable=False))
    return asks


def run_preflight(text: str, parsed: ParseResponse, route: RouteType) -> PreflightResponse:
    defect_flags: list[str] = []
    if not parsed.main_ask.strip():
        defect_flags.append("missing_main_ask")

    audit_hint = "response_audit"
    if route in {"compatibility", "migration", "rfc", "release"}:
        audit_hint = "system_audit"

    if parsed.misread_risk != "normal":
        defect_flags.append(f"misread_risk:{parsed.misread_risk}")

    return PreflightResponse(
        defect_flags=defect_flags,
        ask_ledger=build_ask_ledger(parsed),
        audit_hint=audit_hint,
    )
