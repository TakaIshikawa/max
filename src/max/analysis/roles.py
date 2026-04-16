"""Signal role classification — problem, solution, or market."""

from __future__ import annotations

from max.types.signal import Signal

# Adapters whose signals are almost always one role
DEFAULT_ROLE_MAP: dict[str, str] = {
    "github_issues": "problem",
    "security_advisories": "problem",
    "stackoverflow": "problem",
    "npm_registry": "solution",
    "pypi_registry": "solution",
    "github": "solution",
    "product_hunt": "market",
    "hackernews": "market",
    "reddit": "market",
    "arxiv": "market",
    "devto": "market",
    "pubmed": "market",
}

MIXED_ADAPTERS: set[str] = {"hackernews", "reddit", "devto"}

_PROBLEM_KEYWORDS: list[str] = [
    "bug", "broken", "crash", "fail", "error", "issue", "pain",
    "frustrat", "why does", "doesn't work", "can't", "cannot",
    "vulnerability", "exploit", "security flaw", "regression",
    "slow", "memory leak", "breaking change",
]

_SOLUTION_KEYWORDS: list[str] = [
    "show hn", "i built", "i made", "introducing", "launch",
    "released", "new library", "new tool", "open source",
    "announcing", "v1.", "v2.", "alpha", "beta",
]

_MARKET_KEYWORDS: list[str] = [
    "raised", "funding", "acquired", "ipo", "valuation",
    "million", "billion", "series a", "series b", "yc",
    "trend", "growing", "adoption", "market",
]


def classify_signal_role(signal: Signal) -> str:
    """Classify a signal's role as problem, solution, or market.

    Priority:
    1. Explicit role_hint in metadata
    2. Keyword heuristic for mixed adapters (HN, Reddit, Dev.to)
    3. Default role from DEFAULT_ROLE_MAP
    4. Fallback: "market"
    """
    hint = signal.metadata.get("role_hint")
    if hint in ("problem", "solution", "market"):
        return hint

    if signal.source_adapter in MIXED_ADAPTERS:
        text = f"{signal.title} {signal.content[:300]}".lower()
        role = _keyword_classify(text)
        if role:
            return role

    return DEFAULT_ROLE_MAP.get(signal.source_adapter, "market")


def _keyword_classify(text: str) -> str | None:
    """Score text against keyword lists. Returns highest-scoring role, or None on tie/miss."""
    scores: dict[str, int] = {"problem": 0, "solution": 0, "market": 0}
    for kw in _PROBLEM_KEYWORDS:
        if kw in text:
            scores["problem"] += 1
    for kw in _SOLUTION_KEYWORDS:
        if kw in text:
            scores["solution"] += 1
    for kw in _MARKET_KEYWORDS:
        if kw in text:
            scores["market"] += 1

    max_score = max(scores.values())
    if max_score == 0:
        return None
    winners = [role for role, score in scores.items() if score == max_score]
    return winners[0] if len(winners) == 1 else None


def annotate_signals(signals: list[Signal]) -> list[Signal]:
    """Annotate signals with role. Sets metadata['signal_role'] in-place."""
    for signal in signals:
        signal.metadata["signal_role"] = classify_signal_role(signal)
    return signals
