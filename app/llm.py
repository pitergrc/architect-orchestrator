from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TIMEOUT = float(os.getenv("GROQ_TIMEOUT", "120"))
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))


@dataclass
class DraftResult:
    ok: bool
    text: str
    provider: str = "groq"
    model: str = GROQ_MODEL
    error_type: str | None = None
    error_message: str | None = None


def _build_client() -> OpenAI:
    return OpenAI(
        api_key=GROQ_API_KEY,
        base_url=GROQ_BASE_URL,
        timeout=GROQ_TIMEOUT,
    )


def generate_draft(user_text: str, system_prompt: str | None = None) -> DraftResult:
    if not GROQ_API_KEY:
        return DraftResult(
            ok=False,
            text="",
            error_type="missing_groq_api_key",
            error_message="GROQ_API_KEY is not set",
        )

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

    client = _build_client()

    try:
        response = client.responses.create(
            model=GROQ_MODEL,
            input=input_parts,
            temperature=GROQ_TEMPERATURE,
            tool_choice="none",
        )
    except Exception as exc:
        return DraftResult(
            ok=False,
            text="",
            error_type="groq_request_failed",
            error_message=str(exc),
        )

    output_text = (getattr(response, "output_text", "") or "").strip()

    if not output_text:
        return DraftResult(
            ok=False,
            text="",
            error_type="empty_model_output",
            error_message="Groq Responses API returned empty output_text",
        )

    return DraftResult(
        ok=True,
        text=output_text,
        provider="groq",
        model=GROQ_MODEL,
    )


def ask_ollama(user_text: str, system_prompt: str | None = None) -> str:
    """
    Legacy wrapper kept for backward compatibility.
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
