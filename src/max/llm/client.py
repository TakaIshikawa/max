"""Anthropic SDK wrapper — Opus for all calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from max.config import ANTHROPIC_API_KEY, MODEL

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


@dataclass
class TokenTracker:
    """Tracks token usage across LLM calls by stage label."""

    usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    by_stage: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, stage: str, input_tokens: int, output_tokens: int) -> None:
        self.usage["input"] += input_tokens
        self.usage["output"] += output_tokens
        if stage not in self.by_stage:
            self.by_stage[stage] = {"input": 0, "output": 0}
        self.by_stage[stage]["input"] += input_tokens
        self.by_stage[stage]["output"] += output_tokens

    def reset(self) -> None:
        self.usage = {"input": 0, "output": 0}
        self.by_stage.clear()

    def total(self) -> int:
        return self.usage["input"] + self.usage["output"]

    def summary(self) -> dict[str, int]:
        return {
            "total_input": self.usage["input"],
            "total_output": self.usage["output"],
            "total": self.total(),
            **{
                f"{stage}_input": counts["input"]
                for stage, counts in self.by_stage.items()
            },
            **{
                f"{stage}_output": counts["output"]
                for stage, counts in self.by_stage.items()
            },
        }


token_tracker = TokenTracker()


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or None)
    return _client


def structured_call(
    system: str,
    prompt: str,
    output_type: type[T],
    *,
    model: str = MODEL,
    max_tokens: int = 8192,
    temperature: float = 0.7,
    stage: str = "",
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

    if stage and hasattr(response, "usage"):
        token_tracker.record(
            stage,
            response.usage.input_tokens,
            response.usage.output_tokens,
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
    stage: str = "",
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

    if stage and hasattr(response, "usage"):
        token_tracker.record(
            stage,
            response.usage.input_tokens,
            response.usage.output_tokens,
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
    stage: str = "",
) -> list[T]:
    """Call Opus for each prompt sequentially and return parsed results."""
    return [
        structured_call(
            system, prompt, output_type,
            model=model, max_tokens=max_tokens, temperature=temperature,
            stage=stage,
        )
        for prompt in prompts
    ]
