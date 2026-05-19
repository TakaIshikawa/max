"""Generate deterministic API deprecation plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

API_DEPRECATION_PLAN_SCHEMA_VERSION = "max-api-deprecation-plan/v1"
KIND = "max.api_deprecation_plan"
API_DEPRECATION_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("deprecated_endpoints", "known_consumers", "replacement_guidance", "notice_timeline", "compatibility_window", "monitoring", "extension_criteria", "evidence")


def generate_api_deprecation_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    api = _mapping(context["spec"].get("api_deprecation") or context["spec"].get("api"))
    endpoints = _list(api.get("endpoints")) or [_text(api.get("endpoint")) or "/legacy"]
    consumers = _list(api.get("known_consumers"))
    notice_days = _number(api.get("notice_days")) or 90
    escalated = not consumers or notice_days < 60
    window = _text(api.get("compatibility_window")) or f"{notice_days}-day compatibility window"

    return {
        "schema_version": API_DEPRECATION_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, endpoint_count=len(endpoints), escalation_required=escalated),
        "deprecated_endpoints": [
            item("API1", "endpoint_inventory", f"Deprecate endpoints: {', '.join(endpoints)}.", "api_owner", severity="high" if escalated else "medium", evidence=["api_deprecation.endpoints"])
        ],
        "known_consumers": [
            item("CON1", "consumer_inventory", f"Known consumers: {', '.join(consumers) if consumers else 'unknown consumers'}." , "customer_success_owner", severity="critical" if not consumers else "medium", action="Escalate unknown consumers before notice is sent." if not consumers else "Confirm migration contacts for each consumer.", evidence=["api_deprecation.known_consumers"])
        ],
        "replacement_guidance": [
            item("REP1", "replacement_path", f"Move consumers to {_text(api.get('replacement')) or 'the supported replacement API'} with examples and contract tests.", "api_owner", evidence=["solution.technical_approach"])
        ],
        "notice_timeline": [
            item("NOT1", "notice_schedule", f"Send deprecation notice {notice_days} days before removal with reminders at 30, 14, and 7 days.", "product_owner", severity="high" if notice_days < 60 else "medium", action="Short notice requires escalation." if notice_days < 60 else "Track acknowledgements.", evidence=["api_deprecation.notice_days"])
        ],
        "compatibility_window": [
            item("CMP1", "parallel_support", f"Maintain compatibility for {window}.", "engineering_owner", action="Do not remove until migration and monitoring gates pass.", evidence=["api_deprecation.compatibility_window"])
        ],
        "monitoring": [
            item("MON1", "legacy_usage", "Monitor legacy traffic, error rate, auth failures, and unmigrated consumer IDs.", "on_call_owner", timing="daily during notice", evidence=["execution.validation_plan"])
        ],
        "extension_criteria": [
            item("EXT1", "rollback_or_extension", "Extend the window for critical consumer blockers, unknown high-volume traffic, or replacement instability.", "api_owner", severity="high", evidence=["execution.risks"])
        ],
        "evidence": [
            item("EV1", "deprecation_evidence", "Attach endpoint inventory, consumer notice log, replacement docs, usage dashboards, and extension decisions.", "release_manager", action="Required for removal approval.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_api_deprecation_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "API Deprecation Plan", SECTIONS)


def render_api_deprecation_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _text(value)
    return [text] if text else []


def _number(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
