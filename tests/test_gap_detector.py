"""Tests for gap detection (validated unmet needs)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from max.analysis.gap_detector import Gap, detect_gaps, format_gaps_for_ideation
from max.analysis.triangulation import SignalCluster
from max.store.db import Store
from max.types.signal import Signal, SignalSourceType


def _make_signal(
    adapter: str,
    title: str,
    *,
    signal_role: str = "problem",
    credibility: float = 0.7,
    content: str = "",
) -> Signal:
    return Signal(
        source_type=SignalSourceType.FORUM,
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


# ── Gap dataclass properties ─────────────────────────────────────


def test_gap_problem_strength_empty() -> None:
    gap = Gap(topic="test", problem_signals=[], solution_signals=[])
    assert gap.problem_strength == 0.0


def test_gap_problem_strength_scales_with_diversity() -> None:
    """More diverse sources → higher problem strength."""
    signals_one = [_make_signal("hackernews", "Bug report", credibility=0.8)]
    signals_two = [
        _make_signal("hackernews", "Bug report", credibility=0.8),
        _make_signal("reddit", "Same bug", credibility=0.8),
    ]

    gap_one = Gap(topic="test", problem_signals=signals_one)
    gap_two = Gap(topic="test", problem_signals=signals_two)

    assert gap_two.problem_strength > gap_one.problem_strength


def test_gap_problem_strength_capped_at_one() -> None:
    """problem_strength should be capped at 1.0 even with very high values."""
    # Create conditions that would exceed 1.0: high credibility, many sources, many signals
    signals = [
        _make_signal(f"source_{i}", f"Problem {i}", credibility=1.0)
        for i in range(10)
    ]
    gap = Gap(topic="test", problem_signals=signals)
    assert gap.problem_strength <= 1.0


def test_gap_problem_strength_scales_with_credibility() -> None:
    """Higher average credibility → higher problem strength."""
    low_cred = [
        _make_signal("hackernews", "Bug 1", credibility=0.3),
        _make_signal("reddit", "Bug 2", credibility=0.3),
    ]
    high_cred = [
        _make_signal("hackernews", "Bug 1", credibility=0.9),
        _make_signal("reddit", "Bug 2", credibility=0.9),
    ]

    gap_low = Gap(topic="test", problem_signals=low_cred)
    gap_high = Gap(topic="test", problem_signals=high_cred)

    assert gap_high.problem_strength > gap_low.problem_strength


def test_gap_problem_strength_scales_with_signal_count() -> None:
    """More problem signals → higher problem strength (up to limit)."""
    one_signal = [_make_signal("hackernews", "Bug", credibility=0.8)]
    three_signals = [
        _make_signal("hackernews", "Bug 1", credibility=0.8),
        _make_signal("hackernews", "Bug 2", credibility=0.8),
        _make_signal("hackernews", "Bug 3", credibility=0.8),
    ]

    gap_one = Gap(topic="test", problem_signals=one_signal)
    gap_three = Gap(topic="test", problem_signals=three_signals)

    assert gap_three.problem_strength > gap_one.problem_strength


def test_gap_solution_coverage_empty() -> None:
    gap = Gap(topic="test", problem_signals=[], solution_signals=[])
    assert gap.solution_coverage == 0.0


def test_gap_solution_coverage_increases_with_solutions() -> None:
    no_sol = Gap(topic="test", problem_signals=[], solution_signals=[])
    with_sol = Gap(
        topic="test",
        problem_signals=[],
        solution_signals=[
            _make_signal("npm_registry", "Package A", signal_role="solution", credibility=0.8),
            _make_signal("pypi_registry", "Package B", signal_role="solution", credibility=0.8),
        ],
    )
    assert with_sol.solution_coverage > no_sol.solution_coverage


def test_gap_solution_coverage_capped_at_one() -> None:
    """solution_coverage should be capped at 1.0 even with many high-credibility solutions."""
    # Create conditions that would exceed 1.0: many solutions with high credibility
    solutions = [
        _make_signal(f"registry_{i}", f"Package {i}", signal_role="solution", credibility=1.0)
        for i in range(10)
    ]
    gap = Gap(topic="test", problem_signals=[], solution_signals=solutions)
    assert gap.solution_coverage <= 1.0


def test_gap_solution_coverage_scales_with_credibility() -> None:
    """Higher solution credibility → higher coverage."""
    low_cred = [
        _make_signal("npm_registry", "Package A", signal_role="solution", credibility=0.3),
        _make_signal("pypi_registry", "Package B", signal_role="solution", credibility=0.3),
    ]
    high_cred = [
        _make_signal("npm_registry", "Package A", signal_role="solution", credibility=0.9),
        _make_signal("pypi_registry", "Package B", signal_role="solution", credibility=0.9),
    ]

    gap_low = Gap(topic="test", problem_signals=[], solution_signals=low_cred)
    gap_high = Gap(topic="test", problem_signals=[], solution_signals=high_cred)

    assert gap_high.solution_coverage > gap_low.solution_coverage


def test_gap_score_computation() -> None:
    """gap_score = problem_strength * (1 - solution_coverage)."""
    gap = Gap(
        topic="test",
        problem_signals=[
            _make_signal("hackernews", "Bug 1", credibility=0.9),
            _make_signal("reddit", "Bug 2", credibility=0.9),
            _make_signal("github_issues", "Bug 3", credibility=0.9),
        ],
        solution_signals=[],  # No solutions → coverage = 0
    )
    gap.gap_score = gap.problem_strength * (1.0 - gap.solution_coverage)
    assert gap.gap_score > 0.0
    # With strong problem and no solutions, gap_score should be high
    assert gap.gap_score == gap.problem_strength


def test_gap_score_decreases_with_solutions() -> None:
    problems = [
        _make_signal("hackernews", "Testing is hard", credibility=0.8),
        _make_signal("reddit", "Testing tools are lacking", credibility=0.8),
    ]
    gap_no_sol = Gap(topic="test", problem_signals=problems, solution_signals=[])
    gap_no_sol.gap_score = gap_no_sol.problem_strength * (1.0 - gap_no_sol.solution_coverage)

    gap_with_sol = Gap(
        topic="test",
        problem_signals=problems,
        solution_signals=[
            _make_signal("npm_registry", "Test tool", signal_role="solution", credibility=0.9),
            _make_signal("pypi_registry", "Test lib", signal_role="solution", credibility=0.9),
            _make_signal("github", "Test framework", signal_role="solution", credibility=0.9),
        ],
    )
    gap_with_sol.gap_score = (
        gap_with_sol.problem_strength * (1.0 - gap_with_sol.solution_coverage)
    )

    assert gap_with_sol.gap_score < gap_no_sol.gap_score


# ── detect_gaps with store ───────────────────────────────────────


def test_detect_gaps_no_signals(store: Store) -> None:
    gaps = detect_gaps(store)
    assert gaps == []


def test_detect_gaps_no_problems(store: Store) -> None:
    """Only solution signals → no gaps."""
    signals = [
        _make_signal("npm_registry", "Package A", signal_role="solution"),
        _make_signal("pypi_registry", "Package B", signal_role="solution"),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store)
    assert gaps == []


def test_detect_gaps_problems_only(store: Store) -> None:
    """Problem signals with no solutions should produce gaps."""
    signals = [
        _make_signal("hackernews", "MCP testing is broken", credibility=0.8),
        _make_signal("reddit", "MCP testing framework needed", credibility=0.8),
        _make_signal("github_issues", "Need MCP test tools", credibility=0.8),
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0)
    assert len(gaps) > 0


def test_detect_gaps_max_gaps_limit(store: Store) -> None:
    """Should respect max_gaps parameter."""
    signals = [
        _make_signal("hackernews", f"Unique problem number {i}", credibility=0.9)
        for i in range(20)
    ]
    _seed_signals(store, signals)
    gaps = detect_gaps(store, min_gap_score=0.0, max_gaps=3)
    assert len(gaps) <= 3


def test_detect_gaps_filters_by_min_gap_score(store: Store) -> None:
    """Should only return gaps with gap_score >= min_gap_score."""
    # Create problems with varying credibility to get different gap scores
    signals = [
        _make_signal("hackernews", "High credibility problem", credibility=0.9),
        _make_signal("reddit", "High credibility problem 2", credibility=0.9),
        _make_signal("github_issues", "Low credibility problem", credibility=0.2),
    ]
    _seed_signals(store, signals)

    # With a high threshold, only high-credibility gaps should pass
    gaps = detect_gaps(store, min_gap_score=0.4)
    for gap in gaps:
        assert gap.gap_score >= 0.4


def test_detect_gaps_sorted_by_gap_score_descending(store: Store) -> None:
    """Should return gaps sorted by gap_score in descending order."""
    signals = [
        # Create multiple distinct problem clusters with varying credibility
        _make_signal("hackernews", "High priority problem A", credibility=0.95),
        _make_signal("reddit", "High priority problem A related", credibility=0.95),
        _make_signal("github_issues", "High priority problem A variant", credibility=0.95),
        _make_signal("twitter", "Medium priority problem B", credibility=0.6),
        _make_signal("forum", "Medium priority problem B related", credibility=0.6),
        _make_signal("blog", "Low priority problem C", credibility=0.3),
    ]
    _seed_signals(store, signals)

    gaps = detect_gaps(store, min_gap_score=0.0, max_gaps=10)

    if len(gaps) > 1:
        gap_scores = [g.gap_score for g in gaps]
        assert gap_scores == sorted(gap_scores, reverse=True)


@patch("max.analysis.gap_detector.triangulate")
@patch("max.analysis.gap_detector.embed_text")
@patch("max.analysis.gap_detector._cosine_similarity")
def test_detect_gaps_with_mocked_dependencies(
    mock_sim: MagicMock,
    mock_embed: MagicMock,
    mock_triangulate: MagicMock,
    store: Store,
) -> None:
    """Test detect_gaps with mocked triangulate, embed_text, and _cosine_similarity."""
    # Seed test signals
    problem1 = _make_signal("hackernews", "Testing problem", credibility=0.8)
    problem2 = _make_signal("reddit", "Testing issue", credibility=0.8)
    solution1 = _make_signal(
        "npm_registry", "Test framework", signal_role="solution", credibility=0.7
    )
    solution2 = _make_signal(
        "pypi_registry", "Test library", signal_role="solution", credibility=0.6
    )

    _seed_signals(store, [problem1, problem2, solution1, solution2])

    # Mock triangulate to return a single cluster with problem signals
    mock_cluster = SignalCluster(
        topic="Testing gaps",
        signals=[problem1, problem2],
        centroid=[1.0, 0.0, 0.0],
        source_diversity=0.67,
    )
    mock_triangulate.return_value = [mock_cluster]

    # Mock embed_text to return controlled embeddings for solutions
    # Return based on text content to handle any ordering
    def embed_side_effect(text: str) -> list[float]:
        if "Test framework" in text:
            return [0.9, 0.1, 0.0]  # similar to cluster
        else:
            return [0.1, 0.9, 0.0]  # dissimilar to cluster

    mock_embed.side_effect = embed_side_effect

    # Mock _cosine_similarity to return based on embedding similarity
    def sim_side_effect(vec1: list[float], vec2: list[float]) -> float:
        if vec2[0] > 0.5:  # Check if it's the [0.9, 0.1, 0.0] embedding
            return 0.85
        else:
            return 0.25

    mock_sim.side_effect = sim_side_effect

    gaps = detect_gaps(store, similarity_threshold=0.55, min_gap_score=0.0)

    # Verify triangulate was called with problem signals
    assert mock_triangulate.called
    call_args = mock_triangulate.call_args
    problem_signals = call_args[0][0]
    assert len(problem_signals) == 2
    assert all(s.signal_role == "problem" for s in problem_signals)

    # Verify embed_text was called for each solution signal
    assert mock_embed.call_count == 2

    # Verify _cosine_similarity was called for each solution
    assert mock_sim.call_count == 2

    # Should find one gap with one matching solution (solution1)
    assert len(gaps) == 1
    assert gaps[0].topic == "Testing gaps"
    assert len(gaps[0].problem_signals) == 2
    assert len(gaps[0].solution_signals) == 1
    assert gaps[0].solution_signals[0].title == "Test framework"


@patch("max.analysis.gap_detector.triangulate")
@patch("max.analysis.gap_detector.embed_text")
@patch("max.analysis.gap_detector._cosine_similarity")
def test_detect_gaps_semantic_similarity_matching(
    mock_sim: MagicMock,
    mock_embed: MagicMock,
    mock_triangulate: MagicMock,
    store: Store,
) -> None:
    """Test that solutions are matched to problems using semantic similarity."""
    problem = _make_signal("hackernews", "Database testing problem", credibility=0.8)
    related_solution = _make_signal(
        "npm_registry", "Database test tool", signal_role="solution", credibility=0.8
    )
    unrelated_solution = _make_signal(
        "pypi_registry", "Image processing library", signal_role="solution", credibility=0.8
    )

    _seed_signals(store, [problem, related_solution, unrelated_solution])

    # Mock triangulate
    mock_cluster = SignalCluster(
        topic="Database testing",
        signals=[problem],
        centroid=[1.0, 0.0],
        source_diversity=1.0,
    )
    mock_triangulate.return_value = [mock_cluster]

    # Mock embeddings - handle any ordering
    def embed_side_effect(text: str) -> list[float]:
        if "Database test tool" in text:
            return [0.95, 0.05]  # similar to cluster
        else:
            return [0.1, 0.9]    # dissimilar to cluster

    mock_embed.side_effect = embed_side_effect

    # Mock similarity scores - return high similarity for related embeddings
    def sim_side_effect(vec1: list[float], vec2: list[float]) -> float:
        if vec2[0] > 0.5:  # Check if it's the [0.95, 0.05] embedding (related)
            return 0.92
        else:
            return 0.15

    mock_sim.side_effect = sim_side_effect

    gaps = detect_gaps(store, similarity_threshold=0.55, min_gap_score=0.0)

    # Should match only the related solution
    assert len(gaps) == 1
    assert len(gaps[0].solution_signals) == 1
    assert gaps[0].solution_signals[0].title == "Database test tool"


# ── format_gaps_for_ideation ─────────────────────────────────────


def test_format_gaps_empty() -> None:
    assert format_gaps_for_ideation([]) is None


def test_format_gaps_output_structure() -> None:
    gaps = [
        Gap(
            topic="MCP testing gap",
            problem_signals=[
                _make_signal("hackernews", "MCP testing is hard"),
                _make_signal("reddit", "Need MCP test tools"),
            ],
            solution_signals=[],
            gap_score=0.75,
            source_diversity=0.67,
        ),
    ]
    result = format_gaps_for_ideation(gaps)
    assert result is not None
    assert "VALIDATED UNMET NEEDS" in result
    assert "MCP testing gap" in result
    assert "Gap score: 0.75" in result
    assert "hackernews" in result
    assert "Prioritize ideas" in result


def test_format_gaps_max_gaps_limit() -> None:
    gaps = [
        Gap(
            topic=f"Gap {i}",
            problem_signals=[_make_signal("hackernews", f"Problem {i}")],
            solution_signals=[],
            gap_score=0.5,
        )
        for i in range(10)
    ]
    result = format_gaps_for_ideation(gaps, max_gaps=3)
    assert result is not None
    assert "Gap 0" in result
    assert "Gap 2" in result
    # Gap 3 should not be included
    assert "4." not in result


def test_format_gaps_shows_up_to_three_problem_signals() -> None:
    """Should show maximum of 3 problem signals per gap."""
    # Create gap with 5 problem signals
    problem_signals = [
        _make_signal("hackernews", f"Problem signal {i}")
        for i in range(5)
    ]
    gap = Gap(
        topic="Test gap with many signals",
        problem_signals=problem_signals,
        solution_signals=[],
        gap_score=0.8,
    )

    result = format_gaps_for_ideation([gap])
    assert result is not None

    # Count how many problem signals are listed
    # Each problem signal is formatted as "   - [source_adapter] title"
    signal_lines = [line for line in result.split("\n") if line.strip().startswith("- [")]
    assert len(signal_lines) == 3  # Should show exactly 3, not all 5


def test_format_gaps_includes_solution_count() -> None:
    """Formatted output should include solution signal count."""
    gap = Gap(
        topic="Gap with solutions",
        problem_signals=[_make_signal("hackernews", "Problem")],
        solution_signals=[
            _make_signal("npm_registry", "Solution A", signal_role="solution"),
            _make_signal("pypi_registry", "Solution B", signal_role="solution"),
        ],
        gap_score=0.5,
    )

    result = format_gaps_for_ideation([gap])
    assert result is not None
    assert "Solution signals: 2" in result


def test_format_gaps_sorted_sources() -> None:
    """Sources should be displayed in sorted order."""
    gap = Gap(
        topic="Multi-source gap",
        problem_signals=[
            _make_signal("zforum", "Problem Z"),
            _make_signal("aforum", "Problem A"),
            _make_signal("mforum", "Problem M"),
        ],
        solution_signals=[],
        gap_score=0.7,
    )

    result = format_gaps_for_ideation([gap])
    assert result is not None

    # Extract the sources line
    lines = result.split("\n")
    sources_line = [line for line in lines if "Sources:" in line][0]

    # Sources should appear in alphabetical order
    assert sources_line.index("aforum") < sources_line.index("mforum")
    assert sources_line.index("mforum") < sources_line.index("zforum")
