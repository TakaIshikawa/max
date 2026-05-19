from __future__ import annotations

import csv
from io import StringIO

from max.spec.incident_postmortem_plan import (
    INCIDENT_POSTMORTEM_PLAN_CSV_COLUMNS,
    INCIDENT_POSTMORTEM_PLAN_SCHEMA_VERSION,
    generate_incident_postmortem_plan,
    render_incident_postmortem_plan_csv,
    render_incident_postmortem_plan_markdown,
)


def test_incident_postmortem_plan_shape_and_severity_defaults() -> None:
    plan = generate_incident_postmortem_plan({"source": {"idea_id": "inc-1"}, "project": {"workflow_context": "checkout"}})
    rows = list(csv.DictReader(StringIO(render_incident_postmortem_plan_csv(plan))))

    assert plan["schema_version"] == INCIDENT_POSTMORTEM_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.incident_postmortem_plan"
    assert {"incident_timeline", "customer_impact", "detection_response", "contributing_factors", "corrective_actions", "owners_deadlines", "follow_up_checks", "publication_readiness", "evidence"} <= set(plan)
    assert plan["summary"]["severity"] == "sev3"
    assert plan["summary"]["review_urgency"] == "5 business days"
    assert "## Corrective Actions" in render_incident_postmortem_plan_markdown(plan)
    assert render_incident_postmortem_plan_csv(plan).splitlines()[0] == ",".join(INCIDENT_POSTMORTEM_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "incident_timeline"


def test_incident_postmortem_plan_uses_severity_aware_urgency() -> None:
    plan = generate_incident_postmortem_plan({"incident": {"incident_id": "sev1-db", "severity": "sev1"}})

    assert plan["summary"]["review_urgency"] == "24 hours"
    assert plan["customer_impact"][0]["severity"] == "high"
