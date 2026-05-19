from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports import build_security_review_intake_packet_export
from max.exports.security_review_intake_packet import (
    render_security_review_intake_packet_json,
    render_security_review_intake_packet_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("title", unit_id)
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_security_packet_normalizes_scalars_lists_and_evidence() -> None:
    report = build_security_review_intake_packet_export(_store([
        _unit("complete", {"frameworks": "SOC 2, ISO 27001", "controls": ["SSO", "audit logs"], "data_classes": "PII", "subprocessors": {"hosting": "AWS"}, "deployment_model": "SaaS", "evidence_urls": "https://evidence/a", "owner": "Implementation"}),
        _unit("open", {"owner": "SE", "open_questions": ["Need DPA status"]}),
    ]))

    assert report["packet_rows"][0]["idea_id"] == "open"
    assert "Which security controls apply?" in report["packet_rows"][0]["unanswered_questions"]
    complete = report["packet_rows"][1]
    assert complete["compliance_frameworks"] == ["SOC 2", "ISO 27001"]
    assert complete["subprocessors"] == ["hosting: AWS"]
    assert report["evidence_inventory"] == [{"evidence_url": "https://evidence/a", "idea_count": 1}]
    assert report["summary"]["open_question_count"] >= 1


def test_security_packet_renderers_include_required_sections_for_empty_store() -> None:
    report = build_security_review_intake_packet_export(_store([]), domain="enterprise")

    assert json.loads(render_security_review_intake_packet_json(report))["packet_rows"] == []
    markdown = render_security_review_intake_packet_markdown(report)
    assert "## Evidence" in markdown
    assert "## Unanswered Questions" in markdown
    assert "## Implementation/Security Ownership" in markdown
    assert "No security review intake metadata" in markdown
