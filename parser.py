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


def _split_candidate_parts(text: str) -> list[str]:
    parts = re.split(r"\?|\n|;|\.\s+", text)
    cleaned = [p.strip(" -—\t") for p in parts if p and p.strip()]
    return cleaned or [text.strip()]


def parse_prompt(text: str) -> ParseResponse:
    lower = text.lower()
    parts = _split_candidate_parts(text)

    secondary: list[str] = []
    examples: list[str] = []
    hypotheses: list[str] = []
    constraints: list[str] = []
    style: list[str] = []
    notes: list[str] = []

    for p in parts[1:]:
        if len(p) > 3:
            secondary.append(p)

    if "например" in lower or "пример" in lower:
        examples.append("user provided example detected")

    if "может" in lower or "похоже" in lower or "кажется" in lower:
        hypotheses.append("user hypothesis detected")

    if "коротко" in lower or "подробно" in lower or "по шагово" in lower or "по шагам" in lower:
        style.append("style preference detected")

    if "бесплатно" in lower:
        constraints.append("must be free")

    if "без" in lower:
        constraints.append("negative constraint detected")

    multi = any(m in lower for m in SPLIT_MARKERS) or len(parts) > 1
    if multi:
        notes.append("multi-part request detected")

    policy_or_core_change = any(
        token in lower
        for token in ["измени core", "измени policy", "rfc", "перепиши core", "сменить law"]
    )

    misread_risk = "normal"
    if multi:
        misread_risk = "scope_collapse"
    elif examples and not policy_or_core_change:
        misread_risk = "example_to_policy"
    elif "совместимость" in lower and "какая" not in lower:
        misread_risk = "abstract_compatibility"

    main_ask = parts[0] if parts else text.strip()

    return ParseResponse(
        main_ask=main_ask,
        secondary_asks=secondary,
        constraints=constraints,
        examples=examples,
        hypotheses=hypotheses,
        style_preferences=style,
        policy_or_core_change_request=policy_or_core_change,
        misread_risk=misread_risk,
        notes=notes,
    )
