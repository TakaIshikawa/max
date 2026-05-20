from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.security_review_evidence_aging import (
    build_security_review_evidence_aging_export,
    render_security_review_evidence_aging_json,
    render_security_review_evidence_aging_markdown,
)


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = unit_id
    unit.metadata = metadata
    return unit


def _store(units: list[MagicMock]) -> MagicMock:
    store = MagicMock()
    store.get_buildable_units.return_value = units
    return store


def test_evidence_statuses_sorting_and_invalid_dates() -> None:
    report = build_security_review_evidence_aging_export(
        _store(
            [
                _unit("current", {"account": "Zenith", "evidence_submitted_at": "2026-05-01", "evidence_due_at": "2026-06-01"}),
                _unit("stale", {"account": "Beta", "evidence_submitted_at": "2026-01-01", "stale_evidence": True}),
                _unit("pending", {"account": "Delta", "evidence_requests": ["SOC2"], "evidence_due_at": "bad-date"}),
                _unit("overdue", {"account": "Acme", "evidence_requests": ["DPA"], "evidence_due_at": "2026-01-01", "blockers": ["Legal"]}),
            ]
        )
    )

    assert [row["idea_id"] for row in report["evidence_rows"]] == ["overdue", "stale", "pending", "current"]
    assert report["summary"]["status_counts"] == {"overdue": 1, "stale": 1, "pending": 1, "current": 1}
    assert report["overdue_items"][0]["blockers"] == ["Legal"]
    assert report["evidence_rows"][2]["evidence_due_at"] is None


def test_domain_forwarding_renderers_and_empty_state() -> None:
    store = _store([])
    report = build_security_review_evidence_aging_export(store, domain="health")

    store.get_buildable_units.assert_called_once_with(limit=1000, domain="health")
    assert json.loads(render_security_review_evidence_aging_json(report)) == report
    assert "No security review evidence records found" in render_security_review_evidence_aging_markdown(report)
