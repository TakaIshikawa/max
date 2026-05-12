"""JSON API renderer for disaster recovery plans."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "max.api.disaster_recovery.v1"


def disaster_recovery_plan_to_json(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Render a generated disaster recovery plan as an API JSON structure."""
    summary = dict(plan.get("summary") or {})
    procedures = list(plan.get("procedures") or plan.get("recovery_procedures") or [])
    contacts = list(plan.get("contacts") or plan.get("contact_matrix") or [])
    escalation_paths = list(plan.get("escalation_paths") or plan.get("escalations") or [])
    scenarios = list(plan.get("scenarios") or [])

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.api.disaster_recovery",
        "summary": summary,
        "objectives": {
            "rpo": summary.get("recovery_point_objective") or plan.get("rpo"),
            "rto": summary.get("recovery_time_objective") or plan.get("rto"),
        },
        "procedures": procedures,
        "contacts": contacts,
        "escalation_paths": escalation_paths,
        "scenarios": scenarios,
        "metadata": {
            "source_schema_version": plan.get("schema_version"),
            "source_kind": plan.get("kind"),
            "procedure_count": len(procedures),
            "contact_count": len(contacts),
            "escalation_path_count": len(escalation_paths),
            "scenario_count": len(scenarios),
        },
    }
