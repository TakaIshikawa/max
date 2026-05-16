"""Generate deterministic security incident tabletop exercise plans."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.spec.security_incident_tabletop_plan.v1"
KIND = "max.spec.security_incident_tabletop_plan"


def generate_security_incident_tabletop_plan(incident_context: dict[str, Any]) -> dict[str, Any]:
    """Return a stable tabletop exercise plan for a security incident scenario."""
    ctx = _context(incident_context)
    elevated = ctx["customer_impacting"] or ctx["regulated"] or ctx["severity"] in {"sev1", "critical"}
    notification_target = "within 24 hours" if elevated else "after incident commander approval"

    evidence = [
        "incident timeline with timestamps and decision owners",
        "alert payloads, affected account list, and containment notes",
        "communications drafts and approval history",
    ]
    if elevated:
        evidence.extend(
            [
                "customer notification decision record and legal approval",
                "forensic preservation checklist for regulated evidence",
            ]
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "scenario": {
            "name": ctx["scenario_name"],
            "setup": ctx["setup"],
            "severity": ctx["severity"],
            "customer_impacting": ctx["customer_impacting"],
            "regulated_context": ctx["regulated"],
        },
        "participants": ctx["participants"],
        "roles": [
            {"role": "incident_commander", "owner": ctx["incident_commander"]},
            {"role": "security_lead", "owner": ctx["security_lead"]},
            {"role": "communications_lead", "owner": ctx["communications_lead"]},
            {"role": "legal_privacy_reviewer", "owner": ctx["legal_owner"], "required": elevated},
        ],
        "inject_timeline": [
            {"minute": 0, "inject": "Initial alert fires and triage channel opens."},
            {"minute": 15, "inject": "New signal suggests potential data access by an unauthorized actor."},
            {"minute": 30, "inject": "Customer-facing symptoms or stakeholder questions begin."},
            {"minute": 45, "inject": "Containment option creates availability or evidence tradeoff."},
            {"minute": 60, "inject": "Decision needed on notifications and executive update."},
        ],
        "decision_points": [
            "Classify severity and declare incident ownership.",
            "Choose containment action and preservation approach.",
            "Decide whether customer, regulator, or executive notification is required.",
            "Approve recovery criteria before closing the exercise.",
        ],
        "communications": {
            "channels": ctx["channels"],
            "customer_notification_target": notification_target,
            "executive_update": "every 30 minutes during exercise" if elevated else "at exercise close",
        },
        "evidence_collection": evidence,
        "success_criteria": [
            "Severity and owners are assigned within 10 minutes.",
            "Containment decision includes evidence preservation impact.",
            "Communications are drafted with clear audience, timing, and approval owner.",
            "Follow-up actions have owners and due dates before the tabletop closes.",
        ],
        "follow_up_actions": [
            {"action": "Publish exercise notes and gaps.", "owner": ctx["incident_commander"], "due": "2 business days"},
            {"action": "Update runbook and contact matrix.", "owner": ctx["security_lead"], "due": "5 business days"},
            {"action": "Track remediation actions to closure.", "owner": ctx["risk_owner"], "due": "next security review"},
        ],
    }


def _context(value: dict[str, Any]) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    scenario = _text(raw.get("scenario") or raw.get("scenario_name")) or "Suspected credential compromise"
    severity = (_text(raw.get("severity")) or "sev2").lower()
    regulations = _list(raw.get("regulations"))
    text = " ".join([scenario, _text(raw.get("setup")), *regulations]).lower()
    regulated = bool(raw.get("regulated")) or any(
        term in text for term in ("gdpr", "hipaa", "pci", "sox", "regulated", "privacy")
    )
    customer_impacting = bool(raw.get("customer_impacting")) or any(
        term in text for term in ("customer", "data exposure", "breach", "personal data")
    )
    return {
        "scenario_name": scenario,
        "setup": _text(raw.get("setup"))
        or "Security monitoring identifies suspicious activity requiring coordinated response.",
        "severity": severity,
        "regulated": regulated,
        "customer_impacting": customer_impacting,
        "participants": _list(raw.get("participants"))
        or ["incident commander", "security lead", "engineering lead", "communications lead"],
        "channels": _list(raw.get("channels")) or ["incident bridge", "security Slack channel", "status draft"],
        "incident_commander": _text(raw.get("incident_commander")) or "Incident Commander",
        "security_lead": _text(raw.get("security_lead")) or "Security Lead",
        "communications_lead": _text(raw.get("communications_lead")) or "Communications Lead",
        "legal_owner": _text(raw.get("legal_owner")) or "Legal/Privacy Owner",
        "risk_owner": _text(raw.get("risk_owner")) or "Risk Owner",
    }


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return []


def _text(value: Any) -> str:
    return " ".join(str(value).split()) if value not in (None, "") else ""
