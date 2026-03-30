"""Tests for gap detection — gap identification, categorization, and gap-to-idea mapping.

Complements test_gap_detector.py with deeper coverage of:
- Gap identification across the signal landscape (multi-adapter diversity)
- Gap categorization and scoring edge cases
- Gap-to-idea mapping (format_gaps_for_ideation detail)
"""

from __future__ import annotations

from max.analysis.gap_detector import Gap, detect_gaps, format_gaps_for_ideation
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str,
    *,
    signal_role: str = "problem",
    credibility: float = 0.7,
    content: str = "",
    source_type: SignalSourceType = SignalSourceType.FORUM,
) -> Signal:
    return Signal(
        source_type=source_type,
        source_adapter=adapter,
        title=title,
        content=content or title,
        url=f"https://example.com/{hash(title) % 100000}",
        credibility=credibility,
        metadata={"signal_role": signal_role},
    )


def _seed_signals(store: Store, signals: list[Signal]) -> None:
    for sig in signals:
        store.insert_signal(sig)


# ── Gap identification in the signal landscape ───────────────────


def test_gap_landscape_multi_adapter_problems_score_higher() -> None:
    """Problems confirmed across multiple adapters should have higher gap scores."""
    single_source = Gap(
        topic="single-source issue",
        problem_signals=[
            _make_signal("hackernews", "Problem A", credibility=0.8),
            _make_signal("hackernews", "Problem A again", credibility=0.8),
        ],
    )
    single_source.gap_score = single_source.problem_strength * (
        1.0 - single_source.solution_coverage
    )

    multi_source = Gap(
        topic="multi-source issue",
        problem_signals=[
            _make_signal("hackernews", "Problem B", credibility=0.8),
            _make_signal("reddit", "Problem B too", credibility=0.8),
        ],
    )
    multi_source.gap_score = multi_source.problem_strength * (
        1.0 - multi_source.solution_coverage
    )

    assert multi_source.gap_score > single_source.gap_score


def test_gap_landscape_low_credibility_reduces_strength() -> None:
    """Low-credibility signals produce weaker problem strength."""
    high_cred = Gap(
        topic="high-cred",
        problem_signals=[
            _make_signal("hackernews", "High cred problem", credibility=0.9),
            _make_signal("reddit", "High cred problem too", credibility=0.9),
        ],
    )
    low_cred = Gap(
        topic="low-cred",
        problem_signals=[
            _make_signal("hackernews", "Low cred problem", credibility=0.2),
            _make_signal("reddit", "Low cred problem too", credibility=0.2),
        ],
    )

    assert high_cred.problem_strength > low_cred.problem_strength


def test_gap_problem_strength_capped_at_one() -> None:
    """problem_strength should never exceed 1.0 regardless of input."""
    gap = Gap(
        topic="saturated",
        problem_signals=[
            _make_signal(f"adapter_{i}", f"Problem {i}", credibility=1.0)
            for i in range(10)
        ],
    )
    assert gap.problem_strength <= 1.0


def test_gap_solution_coverage_capped_at_one() -> None:
    """solution_coverage should never exceed 1.0 regardless of input."""
    gap = Gap(
        topic="saturated",
        solution_signals=[
            _make_signal(f"adapter_{i}", f"Solution {i}", signal_role="solution", credibility=1.0)
            for i in range(10)
        ],
    )
    assert gap.solution_coverage <= 1.0


def test_gap_single_low_credibility_signal() -> None:
    """A single low-credibility signal should produce very low problem_strength."""
    gap = Gap(
        topic="weak",
        problem_signals=[
            _make_signal("hackernews", "Meh problem", credibility=0.1),
        ],
    )
    # size_factor min(1/2, 1.0)=0.5, diversity 1/3=0.333, cred 0.1
    # strength = min(1.0, 0.1 * 0.333 * 0.5) ≈ 0.017
    assert gap.problem_strength < 0.1


def test_gap_problem_strength_size_factor() -> None:
    """Problem strength should increase when going from 1 to 2+ signals."""
    one_signal = Gap(
        topic="one",
        problem_signals=[_make_signal("hackernews", "Problem", credibility=0.8)],
    )
    two_signals = Gap(
        topic="two",
        problem_signals=[
            _make_signal("hackernews", "Problem A", credibility=0.8),
            _make_signal("hackernews", "Problem B", credibility=0.8),
        ],
    )
    # Same adapter, same credibility — difference is size_factor: min(1/2)=0.5 vs min(2/2)=1.0
    assert two_signals.problem_strength > one_signal.problem_strength


# ── Gap categorization (scoring edge cases) ──────────────────────


def test_gap_full_solution_coverage_yields_zero_score() -> None:
    """If solutions fully cover the problem, gap_score should be near zero."""
    gap = Gap(
        topic="well-solved",
        problem_signals=[
            _make_signal("hackernews", "A known problem", credibility=0.5),
        ],
        solution_signals=[
            _make_signal("npm_registry", "Solution A", signal_role="solution", credibility=1.0),
            _make_signal("pypi_registry", "Solution B", signal_role="solution", credibility=1.0),
            _make_signal("github", "Solution C", signal_role="solution", credibility=1.0),
        ],
    )
    gap.gap_score = gap.problem_strength * (1.0 - gap.solution_coverage)
    # solution_coverage = min(1.0, 1.0 * 3/3) = 1.0 → gap_score = 0
    assert gap.gap_score == 0.0


def test_gap_partial_solution_coverage() -> None:
    """Partial solutions should reduce but not eliminate the gap score."""
    problems = [
        _make_signal("hackernews", "Auth is hard", credibility=0.8),
        _make_signal("reddit", "Auth really is hard", credibility=0.8),
        _make_signal("github_issues", "Auth bugs everywhere", credibility=0.8),
    ]

    no_sol = Gap(topic="auth-gap", problem_signals=problems, solution_signals=[])
    no_sol.gap_score = no_sol.problem_strength * (1.0 - no_sol.solution_coverage)

    partial_sol = Gap(
        topic="auth-gap",
        problem_signals=problems,
        solution_signals=[
            _make_signal("npm_registry", "Auth lib", signal_role="solution", credibility=0.5),
        ],
    )
    partial_sol.gap_score = partial_sol.problem_strength * (1.0 - partial_sol.solution_coverage)

    assert 0 < partial_sol.gap_score < no_sol.gap_score


def test_detect_gaps_min_gap_score_filters(store: Store) -> None:
    """Gaps below min_gap_score should be excluded."""
    # Seed weak problem signals that produce a low gap score
    signals = [
        _make_signal("hackernews", "Minor annoyance in tooling", credibility=0.3),
    ]
    _seed_signals(store, signals)

    gaps_lenient = detect_gaps(store, min_gap_score=0.0)
    gaps_strict = detect_gaps(store, min_gap_score=0.9)

    assert len(gaps_strict) <= len(gaps_lenient)


def test_detect_gaps_sorts_by_score_descending(store: Store) -> None:
    """Returned gaps should be sorted by gap_score descending."""
    signals = [
        # Cluster 1: strong problem
        _make_signal("hackernews", "Critical auth vulnerability everywhere", credibility=0.9),
        _make_signal("reddit", "Auth vulnerability critical discussion", credibility=0.9),
        _make_signal("github_issues", "Auth vulnerability fix needed urgently", credibility=0.9),
        # Cluster 2: weaker problem
        _make_signal("hackernews", "Minor UI glitch in dark mode theme", credibility=0.3),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0)

    if len(gaps) >= 2:
        for i in range(len(gaps) - 1):
            assert gaps[i].gap_score >= gaps[i + 1].gap_score


def test_detect_gaps_with_mixed_roles(store: Store) -> None:
    """Market signals should be ignored — only problem and solution matter."""
    signals = [
        _make_signal("hackernews", "API rate limiting is painful", signal_role="problem", credibility=0.8),
        _make_signal("reddit", "API rate limiting frustrations", signal_role="problem", credibility=0.8),
        _make_signal("product_hunt", "New startup raised funding", signal_role="market", credibility=0.9),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0)

    # Market signals should not appear in any gap's problem or solution lists
    for gap in gaps:
        for sig in gap.problem_signals + gap.solution_signals:
            assert sig.signal_role != "market"


def test_detect_gaps_solutions_reduce_gap_score(store: Store) -> None:
    """Adding matching solution signals should reduce gap scores."""
    problem_title = "Database migration tooling is broken and unreliable"
    problems = [
        _make_signal("hackernews", problem_title, credibility=0.8),
        _make_signal("reddit", "Database migration tooling really broken", credibility=0.8),
    ]

    _seed_signals(store, problems)
    gaps_without_sol = detect_gaps(store, min_gap_score=0.0)

    # Add solutions with related content
    solutions = [
        _make_signal(
            "npm_registry",
            "Database migration tool released",
            signal_role="solution",
            credibility=0.9,
            content="A comprehensive database migration tooling solution",
        ),
        _make_signal(
            "pypi_registry",
            "DB migration framework launched",
            signal_role="solution",
            credibility=0.9,
            content="Python database migration tooling framework",
        ),
    ]
    for sol in solutions:
        store.insert_signal(sol)

    gaps_with_sol = detect_gaps(store, min_gap_score=0.0)

    # The max gap score should decrease when solutions are added
    max_without = max((g.gap_score for g in gaps_without_sol), default=0)
    max_with = max((g.gap_score for g in gaps_with_sol), default=0)
    assert max_with <= max_without


# ── Gap-to-idea mapping (format_gaps_for_ideation) ───────────────


def test_format_gaps_includes_all_gap_fields() -> None:
    """Output should contain topic, score, sources, signal counts, and sample titles."""
    gap = Gap(
        topic="Observability gap in serverless",
        problem_signals=[
            _make_signal("hackernews", "Serverless monitoring is blind"),
            _make_signal("reddit", "Lambda observability lacking"),
            _make_signal("github_issues", "Missing serverless metrics"),
        ],
        solution_signals=[
            _make_signal("npm_registry", "Basic logger", signal_role="solution"),
        ],
        gap_score=0.65,
        source_diversity=1.0,
    )
    result = format_gaps_for_ideation([gap])
    assert result is not None
    assert "Observability gap in serverless" in result
    assert "Gap score: 0.65" in result
    assert "Problem signals: 3" in result
    assert "Solution signals: 1" in result
    assert "hackernews" in result
    assert "reddit" in result
    assert "github_issues" in result


def test_format_gaps_sample_titles_limited_to_three() -> None:
    """Only the first 3 problem signal titles should appear in the output."""
    gap = Gap(
        topic="Testing gap",
        problem_signals=[
            _make_signal("hackernews", f"Signal title {i}")
            for i in range(6)
        ],
        solution_signals=[],
        gap_score=0.5,
    )
    result = format_gaps_for_ideation([gap])
    assert result is not None
    assert "Signal title 0" in result
    assert "Signal title 2" in result
    # 4th signal should not be listed (only first 3 shown)
    assert "Signal title 3" not in result


def test_format_gaps_multiple_gaps_numbered() -> None:
    """Multiple gaps should be numbered sequentially."""
    gaps = [
        Gap(
            topic=f"Gap topic {i}",
            problem_signals=[_make_signal("hackernews", f"Problem {i}")],
            solution_signals=[],
            gap_score=0.5 + i * 0.1,
        )
        for i in range(3)
    ]
    result = format_gaps_for_ideation(gaps)
    assert result is not None
    assert "1. Gap topic 0" in result
    assert "2. Gap topic 1" in result
    assert "3. Gap topic 2" in result


def test_format_gaps_prioritize_instruction() -> None:
    """Output should contain the ideation prioritization instruction."""
    gap = Gap(
        topic="Test gap",
        problem_signals=[_make_signal("hackernews", "Test problem")],
        solution_signals=[],
        gap_score=0.5,
    )
    result = format_gaps_for_ideation([gap])
    assert result is not None
    assert "highest-value opportunities" in result


def test_format_gaps_sources_deduplicated_and_sorted() -> None:
    """Sources in the output should be deduplicated and sorted."""
    gap = Gap(
        topic="Dedup sources",
        problem_signals=[
            _make_signal("reddit", "Problem A"),
            _make_signal("hackernews", "Problem B"),
            _make_signal("reddit", "Problem C"),  # Duplicate adapter
        ],
        solution_signals=[],
        gap_score=0.5,
    )
    result = format_gaps_for_ideation([gap])
    assert result is not None
    # Sources line should contain sorted, deduplicated adapters
    assert "Sources: hackernews, reddit" in result
