from __future__ import annotations

import os

from openai import OpenAI


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "120"))

client = OpenAI(timeout=OPENAI_TIMEOUT)


def ask_ollama(user_text: str, system_prompt: str | None = None) -> str:
    """
    Backward-compatible function name.
    We keep the old name so graph.py does not need to change again.
    Internally this now uses OpenAI Responses API instead of Ollama.
    """

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
        return (
            "LLM backend unavailable. "
            "OpenAI request failed, so a reliable draft answer could not be generated. "
            f"Error: {exc}"
        )

    output_text = getattr(response, "output_text", "") or ""
    output_text = output_text.strip()

    if not output_text:
        return (
            "LLM backend returned an empty response. "
            "A reliable draft answer could not be generated."
        )

    return output_text
