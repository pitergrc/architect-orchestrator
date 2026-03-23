from __future__ import annotations

from .schemas import ParseResponse, RouteResponse


def resolve_route(text: str, parsed: ParseResponse | None = None) -> RouteResponse:
    lower = text.lower()
    reasons: list[str] = []

    if any(k in lower for k in ["release", "repack", "release-critical", "блокер", "not ready", "lock"]):
        reasons.append("release/repack language detected")
        return RouteResponse(route="release", reasons=reasons)

    if any(k in lower for k in ["rfc", "измени core", "измени policy", "сменить law", "governance", "testsuite"]):
        reasons.append("rfc/law-adjacent language detected")
        return RouteResponse(route="rfc", reasons=reasons)

    if any(k in lower for k in ["migration", "перенос", "миграц", "rebuild поверх"]):
        reasons.append("migration language detected")
        return RouteResponse(route="migration", reasons=reasons)

    if any(k in lower for k in ["совместим", "compatibility", "audit", "cross-file", "manifest", "instruction", "template"]):
        reasons.append("compatibility language detected")
        return RouteResponse(route="compatibility", reasons=reasons)

    reasons.append("default ordinary route")
    return RouteResponse(route="ordinary", reasons=reasons)
