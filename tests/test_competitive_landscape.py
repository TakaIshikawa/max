"""Tests for competitive landscape exports."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.competitive_landscape import (
    KIND,
    SCHEMA_VERSION,
    _classify_position,
    _extract_competitors,
    _identify_market_gaps,
    build_competitive_landscape,
    render_competitive_landscape_json,
    render_competitive_landscape_markdown,
)
from max.types.signal import Signal, SignalSourceType


def _make_unit(
    *,
    unit_id: str = "bu-001",
    title: str = "Observability Copilot",
    domain: str = "devtools",
    evidence_signals: list[str] | None = None,
    quality_score: float = 0.72,
    novelty_score: float = 0.45,
    metadata: dict | None = None,
) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = title
    unit.domain = domain
    unit.category = "application"
    unit.problem = "Teams cannot explain production incidents quickly."
    unit.solution = "AI incident analysis over logs, traces, and deploy history."
    unit.value_proposition = "Cuts mean time to resolution with cited root-cause evidence."
    unit.specific_user = "SRE teams"
    unit.workflow_context = "Incident response"
    unit.why_now = "LLM context windows can now cover telemetry bundles."
    unit.quality_score = quality_score
    unit.novelty_score = novelty_score
    unit.evidence_signals = evidence_signals or ["sig-1"]
    unit.metadata = metadata or {}
    return unit


def _make_signal(
    *,
    signal_id: str = "sig-1",
    title: str = "Datadog competitor momentum",
    content: str = "Competitors include Datadog, New Relic, and Honeycomb for incident workflows.",
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        id=signal_id,
        source_type=SignalSourceType.MARKET,
        source_adapter="test_adapter",
        title=title,
        content=content,
        url=f"https://example.com/{signal_id}",
        tags=["observability"],
        metadata=metadata or {},
    )


def _mock_store(
    units: list[MagicMock] | None = None,
    signals: list[Signal] | None = None,
) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units or []
    store.get_signals.return_value = signals or []
    store.get_signal.side_effect = lambda signal_id: {
        signal.id: signal for signal in (signals or [])
    }.get(signal_id)
    return store


def test_build_competitive_landscape_schema_structure_and_domain_filter() -> None:
    unit = _make_unit(metadata={"differentiators": ["cited incident timeline"]})
    signal = _make_signal()
    store = _mock_store([unit], [signal])

    report = build_competitive_landscape(store, domain="devtools")

    assert report["schema_version"] == SCHEMA_VERSION
    assert report["kind"] == KIND
    assert "generated_at" in report
    assert report["source"]["entity_type"] == "competitive_landscape"
    assert report["source"]["domain_filter"] == "devtools"
    assert len(report["landscape_entries"]) == 1
    entry = report["landscape_entries"][0]
    assert entry["idea_id"] == "bu-001"
    assert entry["title"] == "Observability Copilot"
    assert {competitor["name"] for competitor in entry["competitors"]} >= {"Datadog", "New Relic"}
    assert "cited incident timeline" in entry["differentiators"]
    assert entry["market_position"] in {"leader", "challenger", "niche", "emerging"}
    assert entry["threat_level"] in {"low", "medium", "high"}
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="devtools")


def test_extract_competitors_from_signal_content_and_metadata() -> None:
    signals = [
        _make_signal(
            content="Alternatives like Linear and Jira are common in planning workflows.",
            metadata={
                "competitors": [
                    {"name": "Asana", "url": "https://asana.com"},
                    "Monday.com",
                ],
            },
        )
    ]

    competitors = _extract_competitors(signals)
    by_name = {competitor["name"]: competitor for competitor in competitors}

    assert {"Linear", "Jira", "Asana", "Monday.com"}.issubset(by_name)
    assert by_name["Asana"]["url"] == "https://asana.com"
    assert by_name["Linear"]["relationship"] == "adjacent"
    assert all("overlap_score" in competitor for competitor in competitors)


def test_position_classification_logic() -> None:
    high_overlap = [
        {"name": "Datadog", "relationship": "direct competitor", "overlap_score": 0.82},
        {"name": "New Relic", "relationship": "direct competitor", "overlap_score": 0.75},
    ]
    niche_unit = _make_unit(novelty_score=0.8)

    assert _classify_position(_make_unit(), []) == "emerging"
    assert _classify_position(_make_unit(), high_overlap) == "challenger"
    assert _classify_position(niche_unit, [high_overlap[0]]) == "niche"


def test_market_gap_identification_finds_underserved_segments() -> None:
    entries = [
        {
            "title": "Security Copilot",
            "competitors": [],
            "market_position": "emerging",
            "threat_level": "low",
        },
        {
            "title": "Security Review Bot",
            "competitors": [{"name": "SecureCo"}],
            "market_position": "niche",
            "threat_level": "low",
        },
        {
            "title": "CRM Assistant",
            "competitors": [{"name": "Salesforce"}],
            "market_position": "challenger",
            "threat_level": "high",
        },
    ]

    gaps = _identify_market_gaps(entries)

    assert gaps[0]["segment"] == "security"
    assert gaps[0]["gap_type"] == "underserved"
    assert gaps[0]["opportunity_count"] == 1


def test_markdown_rendering_includes_positioning_matrix() -> None:
    report = build_competitive_landscape(
        _mock_store([_make_unit()], [_make_signal()]),
    )

    markdown = render_competitive_landscape_markdown(report)

    assert "# Competitive Landscape" in markdown
    assert "## Positioning Matrix" in markdown
    assert "| Idea | Market Position | Threat Level | Competitors | Differentiators |" in markdown
    assert "Observability Copilot" in markdown
    assert "Datadog" in markdown
    assert markdown.endswith("\n")


def test_empty_store_handling_and_json_renderer() -> None:
    report = build_competitive_landscape(_mock_store())
    rendered = render_competitive_landscape_json(report)

    assert report["landscape_entries"] == []
    assert report["market_gaps"] == []
    assert report["positioning_summary"]["entry_count"] == 0
    assert json.loads(rendered)["schema_version"] == SCHEMA_VERSION
    assert "No buildable units available" in render_competitive_landscape_markdown(report)


def test_units_with_no_competitor_signals_are_emerging_low_threat() -> None:
    unit = _make_unit(evidence_signals=["sig-quiet"])
    signal = _make_signal(
        signal_id="sig-quiet",
        title="Pain point research",
        content="Teams struggle with incident handoffs and need better summaries.",
    )

    report = build_competitive_landscape(_mock_store([unit], [signal]))
    entry = report["landscape_entries"][0]

    assert entry["competitors"] == []
    assert entry["market_position"] == "emerging"
    assert entry["threat_level"] == "low"
    assert report["market_gaps"][0]["gap_type"] == "underserved"
