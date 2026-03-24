"""Anthropic SDK wrapper — Opus for all calls."""

from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

from max.config import ANTHROPIC_API_KEY, MODEL

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def structured_call(
    system: str,
    prompt: str,
    output_type: type[T],
    *,
    model: str = MODEL,
    max_tokens: int = 8192,
    temperature: float = 0.7,
) -> T:
    """Call Opus and parse the response into a Pydantic model.

    Uses tool_use to enforce structured JSON output matching the schema.
    """
    client = get_client()
    schema = output_type.model_json_schema()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[
            {
                "name": "structured_output",
                "description": f"Return the result as a {output_type.__name__}",
                "input_schema": schema,
            }
        ],
        tool_choice={"type": "tool", "name": "structured_output"},
    )

    for block in response.content:
        if block.type == "tool_use":
            return output_type.model_validate(block.input)

    raise ValueError(f"No tool_use block in response: {response.content}")


def text_call(
    system: str,
    prompt: str,
    *,
    model: str = MODEL,
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> str:
    """Call Opus and return plain text response."""
    client = get_client()

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.content[0].text


def batch_structured_call(
    system: str,
    prompts: list[str],
    output_type: type[T],
    *,
    model: str = MODEL,
    max_tokens: int = 8192,
    temperature: float = 0.7,
) -> list[T]:
    """Call Opus for each prompt sequentially and return parsed results."""
    return [
        structured_call(
            system, prompt, output_type,
            model=model, max_tokens=max_tokens, temperature=temperature,
        )
        for prompt in prompts
    ]
