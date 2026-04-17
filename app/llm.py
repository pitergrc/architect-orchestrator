from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


OPENAI_MODEL = (
    os.getenv("OPENAI_MODEL")
    or os.getenv("OPENAI_MODE")   # backward compatibility for old env typo
    or "gpt-5.4"
)
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "120"))


@dataclass
class DraftResult:
    ok: bool
    text: str
    provider: str = "openai"
    model: str = OPENAI_MODEL
    error_type: str | None = None
    error_message: str | None = None


client = OpenAI(timeout=OPENAI_TIMEOUT)


def generate_draft(user_text: str, system_prompt: str | None = None) -> DraftResult:
    input_parts = []

    if system_prompt:
        input_parts.append(
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            }
        )

    input_parts.append(
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_text}],
        }
    )

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=input_parts,
        )
    except Exception as exc:
        return DraftResult(
            ok=False,
            text="",
            error_type="openai_request_failed",
            error_message=str(exc),
        )

    output_text = (getattr(response, "output_text", "") or "").strip()

    if not output_text:
        return DraftResult(
            ok=False,
            text="",
            error_type="empty_model_output",
            error_message="OpenAI Responses API returned empty output_text",
        )

    return DraftResult(
        ok=True,
        text=output_text,
    )


def ask_ollama(user_text: str, system_prompt: str | None = None) -> str:
    """
    Backward-compatible legacy wrapper.
    Keep this only so old callers do not break immediately.
    New code should use generate_draft().
    """
    result = generate_draft(user_text=user_text, system_prompt=system_prompt)

    if result.ok:
        return result.text

    return (
        "LLM backend unavailable. "
        f"type={result.error_type}; "
        f"message={result.error_message or 'unknown error'}"
    )
