"""Generate deterministic certificate renewal plans for TactSpec previews."""

from __future__ import annotations

from typing import Any, Mapping

from max.spec._launch_governance import CSV_COLUMNS, base_context, item, render_csv, render_markdown, summary

CERTIFICATE_RENEWAL_PLAN_SCHEMA_VERSION = "max-certificate-renewal-plan/v1"
KIND = "max.certificate_renewal_plan"
CERTIFICATE_RENEWAL_PLAN_CSV_COLUMNS = CSV_COLUMNS
SECTIONS = ("certificate_inventory", "expiry_risk", "renewal_steps", "validation_checks", "rollback", "communications", "evidence")


def generate_certificate_renewal_plan(tact_spec: dict[str, Any]) -> dict[str, Any]:
    context = base_context(tact_spec)
    cert = _mapping(context["spec"].get("certificate") or context["spec"].get("certificate_renewal"))
    service = _text(cert.get("service")) or context["workflow"]
    common_name = _text(cert.get("common_name")) or f"{service} certificate"
    owner = _text(cert.get("owner")) or "platform_owner"
    expires_in_days = _number(cert.get("expires_in_days"))
    risk = "critical" if expires_in_days is not None and expires_in_days <= 14 else "high" if expires_in_days is not None and expires_in_days <= 30 else "medium"

    return {
        "schema_version": CERTIFICATE_RENEWAL_PLAN_SCHEMA_VERSION,
        "kind": KIND,
        "source": context["source"],
        "summary": summary(context, service=service, expiry_risk=risk),
        "certificate_inventory": [
            item("CRT1", "certificate_record", f"Renew {common_name} for {service}.", owner, evidence=["certificate.common_name", "certificate.service"])
        ],
        "expiry_risk": [
            item("EXP1", "expiry_timeline", f"Certificate expires in {_days_label(expires_in_days)}.", owner, severity=risk, action="Escalate immediately for critical expiry risk." if risk == "critical" else "Schedule renewal before expiry window.", evidence=["certificate.expires_in_days"])
        ],
        "renewal_steps": [
            item("REN1", "request_certificate", "Generate CSR or provider request using approved SANs and key policy.", "engineering_owner", evidence=["solution.technical_approach"]),
            item("REN2", "deploy_certificate", "Deploy renewed certificate through the standard release path with versioned secrets.", "release_owner", evidence=["execution.validation_plan"]),
        ],
        "validation_checks": [
            item("VAL1", "tls_validation", "Validate chain, SAN coverage, expiry, OCSP/stapling behavior, and client connectivity.", "qa_owner", action="Block completion on failed TLS checks.", evidence=["execution.validation_plan"])
        ],
        "rollback": [
            item("RB1", "restore_previous_cert", "Keep previous certificate and secret version available until renewed certificate is validated.", "engineering_owner", severity="high", evidence=["execution.risks"])
        ],
        "communications": [
            item("COM1", "stakeholder_notice", f"Notify service owner, on-call, and support about {service} certificate renewal timing.", "release_manager", evidence=["project.support_context"])
        ],
        "evidence": [
            item("EV1", "renewal_evidence", "Attach inventory, approval, deployment log, TLS validation output, monitoring snapshot, and rollback readiness.", "release_manager", action="Required for closure.", evidence=["evidence.references"])
        ],
        "evidence_references": context["evidence_references"],
    }


def render_certificate_renewal_plan_markdown(plan: dict[str, Any]) -> str:
    return render_markdown(plan, "Certificate Renewal Plan", SECTIONS)


def render_certificate_renewal_plan_csv(plan: dict[str, Any]) -> str:
    return render_csv(plan, SECTIONS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _number(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _days_label(value: int | None) -> str:
    return f"{value} days" if value is not None else "an unknown number of days"
