from __future__ import annotations

import csv
from io import StringIO

from max.spec.certificate_renewal_plan import (
    CERTIFICATE_RENEWAL_PLAN_CSV_COLUMNS,
    CERTIFICATE_RENEWAL_PLAN_SCHEMA_VERSION,
    generate_certificate_renewal_plan,
    render_certificate_renewal_plan_csv,
    render_certificate_renewal_plan_markdown,
)


def test_certificate_renewal_plan_shape_and_defaults() -> None:
    plan = generate_certificate_renewal_plan({"source": {"idea_id": "cert-default"}, "project": {"workflow_context": "api gateway"}})
    rows = list(csv.DictReader(StringIO(render_certificate_renewal_plan_csv(plan))))

    assert plan["schema_version"] == CERTIFICATE_RENEWAL_PLAN_SCHEMA_VERSION
    assert plan["kind"] == "max.certificate_renewal_plan"
    assert {"certificate_inventory", "expiry_risk", "renewal_steps", "validation_checks", "rollback", "communications", "evidence"} <= set(plan)
    assert plan["summary"]["service"] == "api gateway"
    assert plan["summary"]["expiry_risk"] == "medium"
    assert "## Validation Checks" in render_certificate_renewal_plan_markdown(plan)
    assert render_certificate_renewal_plan_csv(plan).splitlines()[0] == ",".join(CERTIFICATE_RENEWAL_PLAN_CSV_COLUMNS)
    assert rows[0]["section"] == "certificate_inventory"


def test_certificate_renewal_plan_marks_critical_expiry() -> None:
    plan = generate_certificate_renewal_plan({"certificate": {"service": "edge", "common_name": "edge.example.com", "expires_in_days": 7}})

    assert plan["summary"]["expiry_risk"] == "critical"
    assert plan["expiry_risk"][0]["severity"] == "critical"
    assert "Escalate immediately" in plan["expiry_risk"][0]["action"]
