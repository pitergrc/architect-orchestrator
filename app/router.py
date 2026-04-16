from __future__ import annotations

from .schemas import ParseResponse, RouteResponse


def _needs_deep_floor(parsed: ParseResponse | None, lower: str) -> bool:
    if parsed is not None:
        if parsed.needs_hidden_trap_screen:
            return True

        if parsed.misread_risk in ["scope_collapse", "hidden_complexity"]:
            return True

        if parsed.user_intent_mode in ["case_analysis", "decision_support"]:
            return True

        if len(parsed.secondary_asks) > 0:
            return True

    if any(k in lower for k in ["сейчас", "актуаль", "последние", "обновления"]):
        return True

    if any(k in lower for k in ["неочевид", "скрыт", "ловуш", "реальный ответ", "не популярный"]):
        return True

    return False


def resolve_route(text: str, parsed: ParseResponse | None = None) -> RouteResponse:
    lower = text.lower()
    reasons: list[str] = []

    orchestration_required = True
    screening_required = True
    default_depth_floor = "standard"
    can_use_light_internal_path = False

    if _needs_deep_floor(parsed, lower):
        default_depth_floor = "deep"
        reasons.append("deep floor triggered by hidden complexity, multipart, or user intent")

    if any(k in lower for k in ["release", "repack", "release-critical", "блокер", "not ready", "lock"]):
        reasons.append("release/repack language detected")
        return RouteResponse(
            route="release",
            reasons=reasons,
            orchestration_required=orchestration_required,
            screening_required=screening_required,
            default_depth_floor=default_depth_floor,
            can_use_light_internal_path=can_use_light_internal_path,
        )

    if any(k in lower for k in ["rfc", "измени core", "измени policy", "сменить law", "governance", "testsuite"]):
        reasons.append("rfc/law-adjacent language detected")
        return RouteResponse(
            route="rfc",
            reasons=reasons,
            orchestration_required=orchestration_required,
            screening_required=screening_required,
            default_depth_floor=default_depth_floor,
            can_use_light_internal_path=can_use_light_internal_path,
        )

    if any(k in lower for k in ["migration", "перенос", "миграц", "rebuild поверх"]):
        reasons.append("migration language detected")
        return RouteResponse(
            route="migration",
            reasons=reasons,
            orchestration_required=orchestration_required,
            screening_required=screening_required,
            default_depth_floor=default_depth_floor,
            can_use_light_internal_path=can_use_light_internal_path,
        )

    if any(k in lower for k in ["совместим", "compatibility", "audit", "cross-file", "manifest", "instruction", "template"]):
        reasons.append("compatibility language detected")
        return RouteResponse(
            route="compatibility",
            reasons=reasons,
            orchestration_required=orchestration_required,
            screening_required=screening_required,
            default_depth_floor=default_depth_floor,
            can_use_light_internal_path=can_use_light_internal_path,
        )

    reasons.append("default ordinary route")
    return RouteResponse(
        route="ordinary",
        reasons=reasons,
        orchestration_required=orchestration_required,
        screening_required=screening_required,
        default_depth_floor=default_depth_floor,
        can_use_light_internal_path=can_use_light_internal_path,
    )
