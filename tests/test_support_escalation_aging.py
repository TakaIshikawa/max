from __future__ import annotations

import json
from unittest.mock import MagicMock

from max.exports.support_escalation_aging import build_support_escalation_aging_export, render_support_escalation_aging_csv, render_support_escalation_aging_json, render_support_escalation_aging_markdown


def _unit(unit_id: str, metadata: dict) -> MagicMock:
    unit = MagicMock()
    unit.id = unit_id
    unit.title = metadata.get("account_name", unit_id)
    unit.domain = "support"
    unit.metadata = metadata
    return unit


def test_support_escalation_aging_bands_domain_and_renderers() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = [_unit("c", {"account_name": "Critical", "oldest_ticket_age_days": 20, "sla_target_days": 5, "escalated_ticket_count": 1, "severity": "critical", "customer_segment": "enterprise"}), _unit("o", {"account_name": "Overdue", "oldest_ticket_age_days": 8, "sla_target_days": 5}), _unit("w", {"account_name": "Watch", "oldest_ticket_age_days": 4, "sla_target_days": 5, "severity": "high"}), _unit("t", {"account_name": "Track", "oldest_ticket_age_days": 1, "sla_target_days": 5})]
    report = build_support_escalation_aging_export(store, domain="support")
    assert [row["aging_band"] for row in report["escalations"]] == ["critical", "overdue", "watchlist", "on_track"]
    assert report["summary"]["oldest_escalation_age_days"] == 20
    store.get_buildable_units.assert_called_once_with(limit=1000, domain="support")
    assert render_support_escalation_aging_csv(report).splitlines()[0].startswith("idea_id,title")
    assert "# Support Escalation Aging" in render_support_escalation_aging_markdown(report)
    assert json.loads(render_support_escalation_aging_json(report))["kind"] == "max.support_escalation_aging"


def test_support_escalation_aging_empty_report() -> None:
    store = MagicMock()
    store.get_buildable_units.return_value = []
    report = build_support_escalation_aging_export(store)
    assert report["escalations"] == []
    assert "Add support ticket aging metadata" in report["recommendations"][0]
