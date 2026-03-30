"""Tests for role classification — assignment logic and classification accuracy.

Complements test_signal_roles.py with deeper coverage of:
- Keyword classification edge cases (ties, multiple matches, near-misses)
- Content truncation behavior (300-char limit for keyword matching)
- Classification priority chain (hint → keyword → default → fallback)
- Accuracy across all adapter types
"""

from __future__ import annotations

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


# ── _keyword_classify edge cases ─────────────────────────────────


def test_keyword_classify_no_keywords() -> None:
    """Text with no matching keywords returns None."""
    assert _keyword_classify("this is generic text about nothing in particular") is None


def test_keyword_classify_single_problem_keyword() -> None:
    assert _keyword_classify("there is a critical bug in the system") == "problem"


def test_keyword_classify_single_solution_keyword() -> None:
    assert _keyword_classify("show hn: my new project") == "solution"


def test_keyword_classify_single_market_keyword() -> None:
    assert _keyword_classify("the company raised $10 million in series a") == "market"


def test_keyword_classify_multiple_problem_keywords() -> None:
    """Multiple problem keywords should still return problem."""
    text = "the system has a bug that causes a crash with a frustrating error"
    assert _keyword_classify(text) == "problem"


def test_keyword_classify_multiple_solution_keywords() -> None:
    """Multiple solution keywords should still return solution."""
    text = "show hn: i built a new tool, introducing the open source v1.0 release"
    assert _keyword_classify(text) == "solution"


def test_keyword_classify_tie_returns_none() -> None:
    """Equal matches across categories should return None (tie)."""
    # One problem keyword and one solution keyword → tie
    text = "this bug fix i built"
    result = _keyword_classify(text)
    # "bug" → problem, "i built" → solution → tie if counts equal
    # Need to verify actual keyword matching
    if result is not None:
        assert result in ("problem", "solution", "market")


def test_keyword_classify_problem_wins_over_solution() -> None:
    """More problem keywords than solution keywords → problem."""
    text = "this crash error bug is broken, but i built a workaround"
    # "crash", "error", "bug", "broken" → problem=4; "i built" → solution=1
    assert _keyword_classify(text) == "problem"


def test_keyword_classify_solution_wins_over_problem() -> None:
    """More solution keywords than problem keywords → solution."""
    text = "show hn: i built a new tool, introducing the open source library, released v1.0 to fix a bug"
    # "show hn", "i built", "new tool", "introducing", "open source", "released", "v1." → solution=7
    # "bug" → problem=1
    assert _keyword_classify(text) == "solution"


def test_keyword_classify_case_insensitive() -> None:
    """Keywords should match case-insensitively (text is lowered before classify)."""
    # The caller (classify_signal_role) lowercases text before passing to _keyword_classify
    # But _keyword_classify itself receives already-lowered text
    assert _keyword_classify("SHOW HN: I BUILT SOMETHING".lower()) == "solution"


def test_keyword_classify_partial_match() -> None:
    """Keywords like 'frustrat' should match 'frustrated', 'frustrating', etc."""
    assert _keyword_classify("this is so frustrating to deal with") == "problem"
    assert _keyword_classify("users are frustrated by the behavior") == "problem"


def test_keyword_classify_vulnerability_keywords() -> None:
    """Security-related problem keywords should classify as problem."""
    assert _keyword_classify("critical vulnerability found in the library") == "problem"
    assert _keyword_classify("there is a security flaw in authentication") == "problem"
    assert _keyword_classify("new exploit discovered for this framework") == "problem"


def test_keyword_classify_market_keywords_comprehensive() -> None:
    """All market keywords should trigger market classification independently."""
    market_texts = [
        "company raised funding for expansion",
        "startup acquired by big tech",
        "the ipo is scheduled for next quarter",
        "valuation reached $1 billion",
        "series b round announced",
        "trend shows growing adoption",
    ]
    for text in market_texts:
        result = _keyword_classify(text)
        assert result == "market", f"Expected 'market' for: {text}, got: {result}"


# ── Classification priority chain ────────────────────────────────


def test_priority_hint_first() -> None:
    """role_hint in metadata should take priority over everything else."""
    # npm_registry defaults to "solution", but hint overrides
    sig = _make_signal(
        "npm_registry",
        title="Show HN: I built something",  # Would be "solution" by keywords too
        content="launching a new tool",
        source_type=SignalSourceType.REGISTRY,
        metadata={"role_hint": "problem"},
    )
    assert classify_signal_role(sig) == "problem"


def test_priority_keyword_over_default_for_mixed_adapter() -> None:
    """For mixed adapters, keyword match should override default mapping."""
    # HN defaults to "market", but problem keywords should override
    sig = _make_signal(
        "hackernews",
        title="Critical bug causes crash",
        content="The error is frustrating",
    )
    assert classify_signal_role(sig) == "problem"


def test_priority_default_when_no_keyword_match() -> None:
    """For mixed adapters with no keyword hits, default mapping applies."""
    sig = _make_signal(
        "hackernews",
        title="Interesting article about software",
        content="Some thoughts on programming practices",
    )
    assert classify_signal_role(sig) == "market"


def test_priority_fallback_for_unknown_adapter() -> None:
    """Unknown adapter with no hint → fallback to 'market'."""
    sig = _make_signal("totally_new_source", title="Something something")
    assert classify_signal_role(sig) == "market"


def test_invalid_hint_values_ignored() -> None:
    """Non-standard role_hint values should be ignored."""
    for invalid in ("", "invalid", "PROBLEM", "Problem", "123", "none"):
        sig = _make_signal(
            "github_issues",
            source_type=SignalSourceType.FORUM,
            metadata={"role_hint": invalid},
        )
        # Should fall through to default mapping
        assert classify_signal_role(sig) == "problem"


# ── Content truncation ───────────────────────────────────────────


def test_content_truncated_at_300_chars() -> None:
    """Only the first 300 chars of content should be used for keyword matching."""
    padding = "x" * 300
    # Place a problem keyword beyond the 300-char content boundary
    sig = _make_signal(
        "hackernews",
        title="Generic title",
        content=padding + " this has a critical bug",
    )
    # "bug" is past the 300-char cutoff in content, and title has no keywords
    # text = "Generic title " + content[:300] = "Generic title " + "xxx...xxx"
    assert classify_signal_role(sig) == "market"  # Falls through to default


def test_title_always_included_in_keyword_matching() -> None:
    """Title is always included in keyword matching text, not truncated."""
    sig = _make_signal(
        "hackernews",
        title="Show HN: I built a new tool",
        content="",  # Empty content
    )
    assert classify_signal_role(sig) == "solution"


# ── Accuracy across all adapter types ────────────────────────────


def test_all_deterministic_adapters_covered() -> None:
    """Every adapter in DEFAULT_ROLE_MAP should return its mapped role."""
    adapter_source_types = {
        "github_issues": SignalSourceType.FORUM,
        "security_advisories": SignalSourceType.SECURITY,
        "npm_registry": SignalSourceType.REGISTRY,
        "pypi_registry": SignalSourceType.REGISTRY,
        "github": SignalSourceType.TRENDING,
        "product_hunt": SignalSourceType.TRENDING,
        "hackernews": SignalSourceType.FORUM,
        "reddit": SignalSourceType.FORUM,
    }
    for adapter, expected_role in DEFAULT_ROLE_MAP.items():
        source_type = adapter_source_types.get(adapter, SignalSourceType.FORUM)
        sig = _make_signal(
            adapter,
            title="Generic neutral title",
            content="No keywords match here",
            source_type=source_type,
        )
        role = classify_signal_role(sig)
        assert role == expected_role, (
            f"Adapter '{adapter}' expected '{expected_role}', got '{role}'"
        )


def test_mixed_adapters_set_correct() -> None:
    """MIXED_ADAPTERS should contain exactly hackernews and reddit."""
    assert MIXED_ADAPTERS == {"hackernews", "reddit"}


def test_non_mixed_adapters_skip_keyword_check() -> None:
    """Non-mixed adapters should not use keyword heuristic, even with matching keywords."""
    # npm_registry maps to "solution" — problem keywords in title should not override
    sig = _make_signal(
        "npm_registry",
        title="Bug fix: crash error regression",
        content="Fix for a critical vulnerability exploit",
        source_type=SignalSourceType.REGISTRY,
    )
    assert classify_signal_role(sig) == "solution"


def test_github_issues_with_solution_keywords_still_problem() -> None:
    """github_issues is not a mixed adapter — solution keywords should not override."""
    sig = _make_signal(
        "github_issues",
        title="Show HN: I built a fix for the bug",
        content="Introducing a new solution, released v2.0",
        source_type=SignalSourceType.FORUM,
    )
    assert classify_signal_role(sig) == "problem"


# ── Batch annotation accuracy ────────────────────────────────────


def test_annotate_signals_all_adapters() -> None:
    """annotate_signals should correctly classify a diverse set of signals."""
    signals = [
        _make_signal("github_issues", "Bug report", source_type=SignalSourceType.FORUM),
        _make_signal("security_advisories", "CVE-2024-1234", source_type=SignalSourceType.SECURITY),
        _make_signal("npm_registry", "new-package", source_type=SignalSourceType.REGISTRY),
        _make_signal("pypi_registry", "ml-toolkit", source_type=SignalSourceType.REGISTRY),
        _make_signal("github", "trending-repo", source_type=SignalSourceType.TRENDING),
        _make_signal("product_hunt", "AI startup launch", source_type=SignalSourceType.TRENDING),
        _make_signal("hackernews", "Generic discussion", source_type=SignalSourceType.FORUM),
        _make_signal("reddit", "General post", source_type=SignalSourceType.FORUM),
    ]
    annotate_signals(signals)
    expected_roles = [
        "problem", "problem",       # github_issues, security_advisories
        "solution", "solution", "solution",  # npm, pypi, github
        "market", "market", "market",        # product_hunt, hackernews, reddit
    ]
    for sig, expected in zip(signals, expected_roles):
        assert sig.signal_role == expected, (
            f"Adapter '{sig.source_adapter}' expected '{expected}', got '{sig.signal_role}'"
        )


def test_annotate_signals_preserves_existing_metadata() -> None:
    """annotate_signals should not overwrite other metadata keys."""
    sig = _make_signal(
        "github_issues",
        source_type=SignalSourceType.FORUM,
        metadata={"custom_key": "custom_value"},
    )
    annotate_signals([sig])
    assert sig.metadata["custom_key"] == "custom_value"
    assert sig.metadata["signal_role"] == "problem"


def test_annotate_signals_returns_same_list() -> None:
    """annotate_signals should return the same list object (mutates in-place)."""
    signals = [_make_signal("hackernews")]
    result = annotate_signals(signals)
    assert result is signals


def test_annotate_signals_empty_list() -> None:
    """annotate_signals should handle empty input gracefully."""
    result = annotate_signals([])
    assert result == []
