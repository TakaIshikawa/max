"""Tests for signal role annotation (problem / solution / market)."""

from __future__ import annotations

from max.analysis.roles import annotate_signals, classify_signal_role
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str = "Test signal",
    content: str = "",
    *,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    metadata: dict | None = None,
    credibility: float = 0.5,
) -> Signal:
    return Signal(
        source_type=source_type,
        source_adapter=adapter,
        title=title,
        content=content,
        url=f"https://example.com/{hash(title) % 100000}",
        credibility=credibility,
        metadata=metadata or {},
    )


# ── Deterministic adapter mapping ────────────────────────────────


def test_github_issues_classified_as_problem() -> None:
    sig = _make_signal("github_issues", source_type=SignalSourceType.FORUM)
    assert classify_signal_role(sig) == "problem"


def test_security_advisories_classified_as_problem() -> None:
    sig = _make_signal("security_advisories", source_type=SignalSourceType.SECURITY)
    assert classify_signal_role(sig) == "problem"


def test_npm_registry_classified_as_solution() -> None:
    sig = _make_signal("npm_registry", source_type=SignalSourceType.REGISTRY)
    assert classify_signal_role(sig) == "solution"


def test_pypi_registry_classified_as_solution() -> None:
    sig = _make_signal("pypi_registry", source_type=SignalSourceType.REGISTRY)
    assert classify_signal_role(sig) == "solution"


def test_github_classified_as_solution() -> None:
    sig = _make_signal("github", source_type=SignalSourceType.TRENDING)
    assert classify_signal_role(sig) == "solution"


def test_product_hunt_classified_as_market() -> None:
    sig = _make_signal("product_hunt", source_type=SignalSourceType.TRENDING)
    assert classify_signal_role(sig) == "market"


# ── Mixed adapter keyword heuristic ──────────────────────────────


def test_hackernews_problem_keywords() -> None:
    sig = _make_signal(
        "hackernews",
        title="Why does X crash every time I try to deploy?",
        content="This bug is so frustrating. The error message is unhelpful.",
    )
    assert classify_signal_role(sig) == "problem"


def test_hackernews_solution_keywords() -> None:
    sig = _make_signal(
        "hackernews",
        title="Show HN: I built a new testing framework",
        content="Introducing my open source tool for better testing.",
    )
    assert classify_signal_role(sig) == "solution"


def test_reddit_market_keywords() -> None:
    sig = _make_signal(
        "reddit",
        title="Startup raised Series A funding",
        content="The company raised $50 million at a $500 million valuation.",
    )
    assert classify_signal_role(sig) == "market"


def test_mixed_adapter_no_keywords_falls_back_to_default() -> None:
    sig = _make_signal(
        "hackernews",
        title="Interesting thoughts on software",
        content="Some general discussion about programming.",
    )
    assert classify_signal_role(sig) == "market"


# ── Metadata role_hint override ──────────────────────────────────


def test_role_hint_overrides_default_map() -> None:
    sig = _make_signal(
        "npm_registry",
        source_type=SignalSourceType.REGISTRY,
        metadata={"role_hint": "problem"},
    )
    assert classify_signal_role(sig) == "problem"


def test_role_hint_overrides_keyword_heuristic() -> None:
    sig = _make_signal(
        "hackernews",
        title="Show HN: I built something cool",
        content="Introducing a new tool",
        metadata={"role_hint": "market"},
    )
    assert classify_signal_role(sig) == "market"


def test_invalid_role_hint_ignored() -> None:
    sig = _make_signal(
        "github_issues",
        source_type=SignalSourceType.FORUM,
        metadata={"role_hint": "invalid_value"},
    )
    assert classify_signal_role(sig) == "problem"


# ── Unknown adapter fallback ─────────────────────────────────────


def test_unknown_adapter_falls_back_to_market() -> None:
    sig = _make_signal("some_new_adapter")
    assert classify_signal_role(sig) == "market"


# ── Batch annotation ─────────────────────────────────────────────


def test_annotate_signals_batch() -> None:
    signals = [
        _make_signal("github_issues", source_type=SignalSourceType.FORUM),
        _make_signal("npm_registry", source_type=SignalSourceType.REGISTRY),
        _make_signal("product_hunt", source_type=SignalSourceType.TRENDING),
    ]
    result = annotate_signals(signals)
    assert len(result) == 3
    assert result[0].signal_role == "problem"
    assert result[1].signal_role == "solution"
    assert result[2].signal_role == "market"


def test_annotate_signals_mutates_in_place() -> None:
    signals = [_make_signal("github_issues", source_type=SignalSourceType.FORUM)]
    annotate_signals(signals)
    assert signals[0].metadata["signal_role"] == "problem"


# ── Store round-trip ─────────────────────────────────────────────


def test_signal_role_store_roundtrip(store: Store) -> None:
    sig = _make_signal("github_issues", title="Test bug report", source_type=SignalSourceType.FORUM)
    annotate_signals([sig])
    store.insert_signal(sig)

    loaded = store.get_signals()
    assert len(loaded) == 1
    assert loaded[0].signal_role == "problem"


def test_get_signals_by_role(store: Store) -> None:
    signals = [
        _make_signal("github_issues", title="Bug 1", source_type=SignalSourceType.FORUM),
        _make_signal("npm_registry", title="Package 1", source_type=SignalSourceType.REGISTRY),
        _make_signal("product_hunt", title="Launch 1", source_type=SignalSourceType.TRENDING),
    ]
    annotate_signals(signals)
    for sig in signals:
        store.insert_signal(sig)

    problems = store.get_signals_by_role("problem")
    solutions = store.get_signals_by_role("solution")
    markets = store.get_signals_by_role("market")

    assert len(problems) == 1
    assert len(solutions) == 1
    assert len(markets) == 1
    assert problems[0].title == "Bug 1"
    assert solutions[0].title == "Package 1"
    assert markets[0].title == "Launch 1"
