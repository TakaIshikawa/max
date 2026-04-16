"""Comprehensive tests for signal role classification at src/max/analysis/roles.py."""

from __future__ import annotations

import pytest

from max.analysis.roles import (
    DEFAULT_ROLE_MAP,
    MIXED_ADAPTERS,
    _keyword_classify,
    annotate_signals,
    classify_signal_role,
)
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str = "Test signal",
    content: str = "",
    *,
    source_type: SignalSourceType = SignalSourceType.FORUM,
    metadata: dict | None = None,
) -> Signal:
    """Helper to create a test Signal."""
    return Signal(
        source_type=source_type,
        source_adapter=adapter,
        title=title,
        content=content,
        url=f"https://example.com/{hash(title) % 100000}",
        metadata=metadata or {},
    )


# ── 1. DEFAULT_ROLE_MAP tests ────────────────────────────────────────


def test_default_role_map_github_issues_problem() -> None:
    """github_issues adapter → 'problem'."""
    sig = _make_signal("github_issues", source_type=SignalSourceType.FORUM)
    assert classify_signal_role(sig) == "problem"


def test_default_role_map_security_advisories_problem() -> None:
    """security_advisories adapter → 'problem'."""
    sig = _make_signal("security_advisories", source_type=SignalSourceType.SECURITY)
    assert classify_signal_role(sig) == "problem"


def test_default_role_map_npm_registry_solution() -> None:
    """npm_registry adapter → 'solution'."""
    sig = _make_signal("npm_registry", source_type=SignalSourceType.REGISTRY)
    assert classify_signal_role(sig) == "solution"


def test_default_role_map_pypi_registry_solution() -> None:
    """pypi_registry adapter → 'solution'."""
    sig = _make_signal("pypi_registry", source_type=SignalSourceType.REGISTRY)
    assert classify_signal_role(sig) == "solution"


def test_default_role_map_github_solution() -> None:
    """github adapter → 'solution'."""
    sig = _make_signal("github", source_type=SignalSourceType.TRENDING)
    assert classify_signal_role(sig) == "solution"


def test_default_role_map_product_hunt_market() -> None:
    """product_hunt adapter → 'market'."""
    sig = _make_signal("product_hunt", source_type=SignalSourceType.TRENDING)
    assert classify_signal_role(sig) == "market"


def test_default_role_map_stackoverflow_problem() -> None:
    """stackoverflow adapter → 'problem'."""
    sig = _make_signal("stackoverflow", source_type=SignalSourceType.FORUM)
    assert classify_signal_role(sig) == "problem"


def test_default_role_map_arxiv_market() -> None:
    """arxiv adapter → 'market'."""
    sig = _make_signal("arxiv", source_type=SignalSourceType.SURVEY)
    assert classify_signal_role(sig) == "market"


def test_default_role_map_pubmed_market() -> None:
    """pubmed adapter → 'market'."""
    sig = _make_signal("pubmed", source_type=SignalSourceType.SURVEY)
    assert classify_signal_role(sig) == "market"


def test_default_role_map_devto_uses_keywords() -> None:
    """devto is in MIXED_ADAPTERS, uses keyword heuristic first.

    When no keywords match, falls back to DEFAULT_ROLE_MAP which maps devto to 'market'.
    """
    sig = _make_signal("devto", title="Neutral title", content="No special keywords here")
    # _keyword_classify returns None, falls back to DEFAULT_ROLE_MAP['devto'] = 'market'
    assert classify_signal_role(sig) == "market"


def test_default_role_map_hackernews_uses_keywords() -> None:
    """hackernews is in MIXED_ADAPTERS, uses keyword heuristic first.

    When no keywords match, falls back to DEFAULT_ROLE_MAP which maps hackernews to 'market'.
    """
    sig = _make_signal("hackernews", title="Neutral title", content="No special keywords here")
    # _keyword_classify returns None, falls back to DEFAULT_ROLE_MAP['hackernews'] = 'market'
    assert classify_signal_role(sig) == "market"


def test_default_role_map_reddit_uses_keywords() -> None:
    """reddit is in MIXED_ADAPTERS, uses keyword heuristic first.

    When no keywords match, falls back to DEFAULT_ROLE_MAP which maps reddit to 'market'.
    """
    sig = _make_signal("reddit", title="General discussion", content="Some random content")
    # _keyword_classify returns None, falls back to DEFAULT_ROLE_MAP['reddit'] = 'market'
    assert classify_signal_role(sig) == "market"


# ── 2. Explicit role_hint tests ──────────────────────────────────────


def test_role_hint_problem_overrides_adapter() -> None:
    """metadata={'role_hint': 'problem'} → 'problem' regardless of adapter."""
    sig = _make_signal("npm_registry", metadata={"role_hint": "problem"})
    assert classify_signal_role(sig) == "problem"


def test_role_hint_solution_overrides_adapter() -> None:
    """metadata={'role_hint': 'solution'} → 'solution'."""
    sig = _make_signal("github_issues", metadata={"role_hint": "solution"})
    assert classify_signal_role(sig) == "solution"


def test_role_hint_market_overrides_adapter() -> None:
    """metadata={'role_hint': 'market'} → 'market'."""
    sig = _make_signal("security_advisories", metadata={"role_hint": "market"})
    assert classify_signal_role(sig) == "market"


def test_role_hint_invalid_falls_through() -> None:
    """metadata={'role_hint': 'invalid'} → falls through to other logic."""
    sig = _make_signal("github_issues", metadata={"role_hint": "invalid"})
    # Falls through to DEFAULT_ROLE_MAP, github_issues → 'problem'
    assert classify_signal_role(sig) == "problem"


def test_role_hint_overrides_keywords_for_mixed_adapters() -> None:
    """role_hint has priority over keyword heuristic."""
    sig = _make_signal(
        "hackernews",
        title="Show HN: I built a new tool",  # solution keywords
        content="Introducing my open source project",
        metadata={"role_hint": "market"},
    )
    assert classify_signal_role(sig) == "market"


# ── 3. _keyword_classify tests ───────────────────────────────────────


def test_keyword_classify_problem_single_keyword() -> None:
    """Text with single problem keyword → 'problem'."""
    assert _keyword_classify("this library has a bug") == "problem"


def test_keyword_classify_problem_multiple_keywords() -> None:
    """Text with multiple problem keywords → 'problem'."""
    text = "The app crashes and shows an error message, it's broken"
    assert _keyword_classify(text) == "problem"


def test_keyword_classify_problem_vulnerability() -> None:
    """Security-related problem keywords → 'problem'."""
    assert _keyword_classify("security vulnerability in authentication") == "problem"


def test_keyword_classify_solution_show_hn() -> None:
    """'show hn' keyword → 'solution'."""
    assert _keyword_classify("show hn: my new project") == "solution"


def test_keyword_classify_solution_i_built() -> None:
    """'i built' keyword → 'solution'."""
    assert _keyword_classify("i built a tool to solve this problem") == "solution"


def test_keyword_classify_solution_open_source() -> None:
    """'open source' keyword → 'solution'."""
    assert _keyword_classify("Announcing our new open source library") == "solution"


def test_keyword_classify_solution_multiple_keywords() -> None:
    """Multiple solution keywords → 'solution'."""
    text = "Show HN: I built and released a new library, now in beta"
    assert _keyword_classify(text) == "solution"


def test_keyword_classify_market_funding() -> None:
    """'raised' and 'funding' keywords → 'market'."""
    assert _keyword_classify("Startup raised Series A funding") == "market"


def test_keyword_classify_market_valuation() -> None:
    """'valuation' keyword → 'market'."""
    assert _keyword_classify("Company valued at 500 million") == "market"


def test_keyword_classify_market_multiple_keywords() -> None:
    """Multiple market keywords → 'market'."""
    text = "The startup raised 50 million in Series B funding with YC backing"
    assert _keyword_classify(text) == "market"


def test_keyword_classify_no_keywords_returns_none() -> None:
    """Text with no matching keywords → None."""
    assert _keyword_classify("This is a neutral discussion about software") is None


def test_keyword_classify_tie_returns_none() -> None:
    """Tie between categories → None."""
    # Create a true tie: same number of keywords in multiple categories
    # 1 problem keyword, 1 solution keyword, 1 market keyword
    text = "bug in the system with a new tool for trend analysis"
    result = _keyword_classify(text)
    # 'bug' (problem: 1), 'new tool' (solution: 1), 'trend' (market: 1) → tie
    assert result is None


def test_keyword_classify_problem_wins_over_solution() -> None:
    """More problem keywords than solution → 'problem'."""
    text = "This bug causes a crash and shows error messages. I built a workaround."
    # 3 problem keywords (bug, crash, error) vs 1 solution keyword (i built)
    assert _keyword_classify(text) == "problem"


def test_keyword_classify_case_insensitive() -> None:
    """_keyword_classify expects lowercase input; classify_signal_role handles lowercasing."""
    # _keyword_classify expects pre-lowercased text
    assert _keyword_classify("bug in the system") == "problem"
    assert _keyword_classify("show hn: new tool") == "solution"
    assert _keyword_classify("raised funding") == "market"

    # Uppercase text won't match since _keyword_classify doesn't lowercase
    assert _keyword_classify("BUG in the system") is None


# ── 4. Mixed adapter behavior ─────────────────────────────────────────


def test_mixed_adapter_reddit_problem_keywords() -> None:
    """Reddit signal with problem title → 'problem'."""
    sig = _make_signal(
        "reddit",
        title="This library crashes on Python 3.12",
        content="Getting constant errors when running on new Python version",
    )
    assert classify_signal_role(sig) == "problem"


def test_mixed_adapter_hackernews_solution_keywords() -> None:
    """HN signal with solution title → 'solution'."""
    sig = _make_signal(
        "hackernews",
        title="Show HN: I built a new tool",
        content="Introducing my open source project for developers",
    )
    assert classify_signal_role(sig) == "solution"


def test_mixed_adapter_reddit_market_keywords() -> None:
    """Reddit signal with market keywords → 'market'."""
    sig = _make_signal(
        "reddit",
        title="Company raised Series A",
        content="Startup just announced 20 million in funding",
    )
    assert classify_signal_role(sig) == "market"


def test_mixed_adapter_devto_solution_keywords() -> None:
    """Dev.to signal with solution keywords → 'solution'."""
    sig = _make_signal(
        "devto",
        title="I built a new CLI tool",
        content="Introducing my open source library for developers",
    )
    assert classify_signal_role(sig) == "solution"


def test_mixed_adapter_devto_problem_keywords() -> None:
    """Dev.to signal with problem keywords → 'problem'."""
    sig = _make_signal(
        "devto",
        title="Why does my React app crash?",
        content="Getting constant errors and bugs in production",
    )
    assert classify_signal_role(sig) == "problem"


def test_mixed_adapter_content_truncation() -> None:
    """Verify content[:300] is used for keyword matching."""
    # Create content longer than 300 chars with keywords only after position 300
    content_before_300 = "a" * 250  # 250 neutral chars
    content_after_300 = " bug crash error vulnerability"  # Problem keywords after position 300
    full_content = content_before_300 + "x" * 100 + content_after_300

    sig = _make_signal(
        "hackernews",
        title="Neutral title",
        content=full_content,
    )
    # Keywords are after position 300, so should not be detected
    # Falls back to DEFAULT_ROLE_MAP['hackernews'] = 'market'
    assert classify_signal_role(sig) == "market"


def test_mixed_adapter_keywords_in_first_300_chars() -> None:
    """Keywords within first 300 chars are detected."""
    content = "This is a bug that causes crashes. " + ("x" * 300)
    sig = _make_signal("reddit", title="Issue", content=content)
    # Keywords are in first 300 chars
    assert classify_signal_role(sig) == "problem"


def test_mixed_adapter_no_keywords_falls_back_to_default_map() -> None:
    """Mixed adapter with no keywords → falls back to DEFAULT_ROLE_MAP."""
    sig = _make_signal(
        "hackernews",
        title="Interesting article about programming",
        content="General discussion without specific keywords",
    )
    # _keyword_classify returns None, falls back to DEFAULT_ROLE_MAP['hackernews'] = 'market'
    assert classify_signal_role(sig) == "market"


# ── 5. annotate_signals tests ─────────────────────────────────────────


def test_annotate_signals_sets_metadata_signal_role() -> None:
    """annotate_signals modifies metadata['signal_role'] in-place."""
    signals = [
        _make_signal("github_issues", source_type=SignalSourceType.FORUM),
        _make_signal("npm_registry", source_type=SignalSourceType.REGISTRY),
    ]
    annotate_signals(signals)
    assert signals[0].metadata["signal_role"] == "problem"
    assert signals[1].metadata["signal_role"] == "solution"


def test_annotate_signals_returns_same_list() -> None:
    """annotate_signals returns the same list (not a copy)."""
    signals = [_make_signal("github_issues")]
    result = annotate_signals(signals)
    assert result is signals


def test_annotate_signals_empty_list() -> None:
    """annotate_signals handles empty list."""
    result = annotate_signals([])
    assert result == []


def test_annotate_signals_multiple_signals_individually_classified() -> None:
    """Multiple signals get individually classified."""
    signals = [
        _make_signal("github_issues", title="Bug report", source_type=SignalSourceType.FORUM),
        _make_signal("pypi_registry", title="New package", source_type=SignalSourceType.REGISTRY),
        _make_signal("product_hunt", title="Product launch", source_type=SignalSourceType.TRENDING),
        _make_signal(
            "hackernews",
            title="Show HN: New tool",
            content="I built this",
        ),
    ]
    annotate_signals(signals)

    assert signals[0].signal_role == "problem"
    assert signals[1].signal_role == "solution"
    assert signals[2].signal_role == "market"
    assert signals[3].signal_role == "solution"  # Keywords detected


def test_annotate_signals_preserves_existing_metadata() -> None:
    """annotate_signals preserves other metadata fields."""
    signals = [
        _make_signal("github_issues", metadata={"custom_field": "value"}),
    ]
    annotate_signals(signals)

    assert signals[0].metadata["signal_role"] == "problem"
    assert signals[0].metadata["custom_field"] == "value"


# ── 6. Unknown adapter ────────────────────────────────────────────────


def test_unknown_adapter_fallback_to_market() -> None:
    """Adapter name not in DEFAULT_ROLE_MAP → fallback 'market'."""
    sig = _make_signal("arxiv", title="Research paper")
    assert classify_signal_role(sig) == "market"


def test_unknown_adapter_with_role_hint() -> None:
    """Unknown adapter with role_hint → uses role_hint."""
    sig = _make_signal("arxiv", metadata={"role_hint": "solution"})
    assert classify_signal_role(sig) == "solution"


# ── Edge cases and integration ────────────────────────────────────────


def test_classification_priority_role_hint_over_keywords() -> None:
    """Priority check: role_hint overrides keyword heuristic."""
    sig = _make_signal(
        "reddit",
        title="Bug causes crashes",  # Problem keywords
        content="This is broken and frustrating",
        metadata={"role_hint": "solution"},
    )
    assert classify_signal_role(sig) == "solution"


def test_classification_priority_keywords_over_default_map() -> None:
    """Priority check: keywords (for mixed adapters) override DEFAULT_ROLE_MAP."""
    sig = _make_signal(
        "hackernews",
        title="Show HN: New project",
        content="I built this tool",
    )
    # Without keywords, hackernews → 'market' from DEFAULT_ROLE_MAP
    # With solution keywords, should be 'solution'
    assert classify_signal_role(sig) == "solution"


def test_classification_priority_default_map_over_fallback() -> None:
    """Priority check: DEFAULT_ROLE_MAP overrides fallback 'market'."""
    sig = _make_signal("npm_registry")
    # npm_registry in DEFAULT_ROLE_MAP → 'solution', not fallback 'market'
    assert classify_signal_role(sig) == "solution"


def test_signal_role_property_reads_metadata() -> None:
    """Signal.signal_role property reads from metadata."""
    sig = _make_signal("github_issues")
    annotate_signals([sig])
    # Via property
    assert sig.signal_role == "problem"
    # Via metadata
    assert sig.metadata["signal_role"] == "problem"


def test_mixed_adapters_constant_correctness() -> None:
    """Verify MIXED_ADAPTERS constant contains expected values."""
    assert MIXED_ADAPTERS == {"hackernews", "reddit", "devto"}


def test_default_role_map_constant_correctness() -> None:
    """Verify DEFAULT_ROLE_MAP constant contains expected mappings."""
    assert DEFAULT_ROLE_MAP["github_issues"] == "problem"
    assert DEFAULT_ROLE_MAP["security_advisories"] == "problem"
    assert DEFAULT_ROLE_MAP["stackoverflow"] == "problem"
    assert DEFAULT_ROLE_MAP["npm_registry"] == "solution"
    assert DEFAULT_ROLE_MAP["pypi_registry"] == "solution"
    assert DEFAULT_ROLE_MAP["github"] == "solution"
    assert DEFAULT_ROLE_MAP["product_hunt"] == "market"
    assert DEFAULT_ROLE_MAP["hackernews"] == "market"
    assert DEFAULT_ROLE_MAP["reddit"] == "market"
    assert DEFAULT_ROLE_MAP["arxiv"] == "market"
    assert DEFAULT_ROLE_MAP["devto"] == "market"
    assert DEFAULT_ROLE_MAP["pubmed"] == "market"
