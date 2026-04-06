"""Anthropic SDK wrapper — Opus for all calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from max.config import ANTHROPIC_API_KEY, MODEL

T = TypeVar("T", bound=BaseModel)

_client: anthropic.Anthropic | None = None


# Approximate pricing per 1K tokens in USD (as of Jan 2025)
# Update these values when Anthropic changes pricing
MODEL_PRICING = {
    "claude-opus-4-6": {"input_per_1k": 0.015, "output_per_1k": 0.075},
    "claude-sonnet-4-5-20250929": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-sonnet-3-5-20241022": {"input_per_1k": 0.003, "output_per_1k": 0.015},
    "claude-haiku-4-5-20251001": {"input_per_1k": 0.001, "output_per_1k": 0.005},
}


class BudgetExceededError(Exception):
    """Raised when token or cost budget is exceeded during a pipeline run."""
    pass


@dataclass
class TokenTracker:
    """Tracks token usage and cost across LLM calls by stage label."""

    usage: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    by_stage: dict[str, dict[str, int]] = field(default_factory=dict)
    model: str = MODEL

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

    def estimated_cost_usd(self) -> float:
        """Calculate estimated cost in USD based on current usage."""
        pricing = MODEL_PRICING.get(self.model)
        if not pricing:
            # Fallback to Opus pricing if model not found
            pricing = MODEL_PRICING["claude-opus-4-6"]

        input_cost = (self.usage["input"] / 1000) * pricing["input_per_1k"]
        output_cost = (self.usage["output"] / 1000) * pricing["output_per_1k"]
        return input_cost + output_cost

    def cost_by_stage(self) -> dict[str, float]:
        """Calculate cost breakdown by stage."""
        pricing = MODEL_PRICING.get(self.model)
        if not pricing:
            pricing = MODEL_PRICING["claude-opus-4-6"]

        costs = {}
        for stage, counts in self.by_stage.items():
            input_cost = (counts["input"] / 1000) * pricing["input_per_1k"]
            output_cost = (counts["output"] / 1000) * pricing["output_per_1k"]
            costs[stage] = input_cost + output_cost
        return costs

    def budget_remaining(self, budget: float) -> float:
        """Return remaining budget in USD. Negative if over budget."""
        if budget <= 0:
            return float("inf")
        return budget - self.estimated_cost_usd()

    def is_over_budget(self, budget: float) -> bool:
        """Check if current cost exceeds the budget."""
        if budget <= 0:
            return False
        return self.estimated_cost_usd() > budget

    def summary(self) -> dict:
        return {
            "total_input": self.usage["input"],
            "total_output": self.usage["output"],
            "total": self.total(),
            "estimated_cost_usd": self.estimated_cost_usd(),
            "cost_by_stage": self.cost_by_stage(),
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
    Raises BudgetExceededError if token or cost budget is exceeded.
    """
    from max.config import MAX_COST_BUDGET, MAX_TOKEN_BUDGET

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

        # Check budget after recording tokens
        if MAX_TOKEN_BUDGET > 0 and token_tracker.total() > MAX_TOKEN_BUDGET:
            raise BudgetExceededError(
                f"Token budget exceeded: {token_tracker.total()} > {MAX_TOKEN_BUDGET}"
            )
        if token_tracker.is_over_budget(MAX_COST_BUDGET):
            cost = token_tracker.estimated_cost_usd()
            raise BudgetExceededError(
                f"Cost budget exceeded: ${cost:.4f} > ${MAX_COST_BUDGET:.4f}"
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
    """Call Opus and return plain text response.

    Raises BudgetExceededError if token or cost budget is exceeded.
    """
    from max.config import MAX_COST_BUDGET, MAX_TOKEN_BUDGET

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

        # Check budget after recording tokens
        if MAX_TOKEN_BUDGET > 0 and token_tracker.total() > MAX_TOKEN_BUDGET:
            raise BudgetExceededError(
                f"Token budget exceeded: {token_tracker.total()} > {MAX_TOKEN_BUDGET}"
            )
        if token_tracker.is_over_budget(MAX_COST_BUDGET):
            cost = token_tracker.estimated_cost_usd()
            raise BudgetExceededError(
                f"Cost budget exceeded: ${cost:.4f} > ${MAX_COST_BUDGET:.4f}"
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
