"""Generate deterministic vendor risk assessments for TactSpec previews."""

from __future__ import annotations

from typing import Any


VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION = "max-vendor-risk-assessment/v1"
KIND = "max.spec.vendor_risk_assessment"

_KNOWN_VENDORS = {
    "aws": ("AWS", "cloud_provider"),
    "azure": ("Azure", "cloud_provider"),
    "datadog": ("Datadog", "observability"),
    "github": ("GitHub", "developer_platform"),
    "gitlab": ("GitLab", "developer_platform"),
    "google": ("Google", "cloud_provider"),
    "hubspot": ("HubSpot", "crm"),
    "jira": ("Jira", "work_management"),
    "microsoft": ("Microsoft", "productivity_platform"),
    "openai": ("OpenAI", "ai_provider"),
    "salesforce": ("Salesforce", "crm"),
    "sentry": ("Sentry", "observability"),
    "slack": ("Slack", "messaging"),
    "stripe": ("Stripe", "payments"),
    "supabase": ("Supabase", "data_platform"),
    "teams": ("Microsoft Teams", "messaging"),
    "twilio": ("Twilio", "communications"),
    "webhook": ("Webhook provider", "integration"),
}

_DATA_TERMS = {
    "account": "account data",
    "audit": "audit logs",
    "credential": "credentials or secrets",
    "customer": "customer records",
    "email": "email addresses",
    "financial": "financial data",
    "health": "health data",
    "hipaa": "regulated health data",
    "log": "operational logs",
    "patient": "patient data",
    "payment": "payment data",
    "pii": "personal data",
    "prompt": "AI prompts and outputs",
    "secret": "credentials or secrets",
    "student": "student data",
    "token": "tokens",
}

_SENSITIVE_DATA = {
    "credentials or secrets",
    "financial data",
    "health data",
    "patient data",
    "payment data",
    "personal data",
    "regulated health data",
    "student data",
    "tokens",
}


def generate_vendor_risk_assessment(tact_spec: dict[str, Any]) -> dict[str, Any]:
    """Turn a TactSpec-like dictionary into a JSON-ready vendor risk assessment."""
    spec = tact_spec if isinstance(tact_spec, dict) else {}
    context = _context(spec)
    vendors = _vendors(context)
    risks = _risks(context, vendors)
    mitigations = _mitigations(context, vendors, risks)
    review_checklist = _review_checklist(context, vendors, risks)
    gate_decision = _gate_decision(context, vendors, risks, review_checklist)

    return {
        "schema_version": VENDOR_RISK_ASSESSMENT_SCHEMA_VERSION,
        "kind": KIND,
        "source": {
            "system": context["source"].get("system") or "max",
            "type": context["source"].get("type") or "tact_spec_preview",
            "idea_id": context["source"].get("idea_id"),
            "status": context["source"].get("status"),
            "domain": context["source"].get("domain"),
            "category": context["source"].get("category"),
            "tact_spec_schema_version": spec.get("schema_version"),
            "tact_spec_kind": spec.get("kind"),
        },
        "summary": {
            "title": context["title"],
            "workflow_context": context["workflow_context"],
            "vendor_count": len(vendors),
            "high_risk_vendor_count": sum(1 for vendor in vendors if vendor["risk_level"] == "high"),
            "risk_count": len(risks),
            "blocking_risk_count": sum(1 for risk in risks if risk["severity"] == "high"),
            "review_item_count": len(review_checklist),
            "gate_status": gate_decision["status"],
        },
        "vendors": vendors,
        "risks": risks,
        "mitigations": mitigations,
        "review_checklist": review_checklist,
        "gate_decision": gate_decision,
    }


def render_vendor_risk_assessment_markdown(assessment: dict[str, Any]) -> str:
    """Render a generated vendor risk assessment as stable markdown."""
    summary = assessment.get("summary", {})
    source = assessment.get("source", {})
    gate = assessment.get("gate_decision") or {}
    title = _text(summary.get("title")) or _text(source.get("idea_id")) or "TactSpec"

    lines = [
        f"# {title} Vendor Risk Assessment",
        "",
        f"- Schema version: {_text(assessment.get('schema_version'))}",
        f"- Source idea ID: {_text(source.get('idea_id')) or 'none'}",
        f"- Source status: {_text(source.get('status')) or 'none'}",
        f"- TactSpec schema: {_text(source.get('tact_spec_schema_version')) or 'none'}",
        f"- Workflow context: {_text(summary.get('workflow_context'))}",
        f"- Vendors: {_text(summary.get('vendor_count'))}",
        f"- High-risk vendors: {_text(summary.get('high_risk_vendor_count'))}",
        f"- Gate decision: {_text(gate.get('status'))}",
        "",
    ]

    _extend_section(lines, "Vendors", assessment.get("vendors") or [], _render_vendor)
    _extend_section(lines, "Vendor Risks", assessment.get("risks") or [], _render_risk)
    _extend_section(lines, "Mitigations", assessment.get("mitigations") or [], _render_mitigation)
    _extend_section(
        lines,
        "Review Checklist",
        assessment.get("review_checklist") or [],
        _render_checklist_item,
    )
    _extend_section(lines, "Gate Decision", [gate], _render_gate)

    return "\n".join(lines).rstrip() + "\n"


def _context(spec: dict[str, Any]) -> dict[str, Any]:
    source = _dict(spec.get("source"))
    project = _dict(spec.get("project"))
    solution = _dict(spec.get("solution"))
    execution = _dict(spec.get("execution"))
    artifacts = _dict(spec.get("artifacts"))

    privacy = _artifact(spec, artifacts, "privacy_impact_assessment")
    security = _artifact(spec, artifacts, "security_review")
    threat_model = _artifact(spec, artifacts, "threat_model")
    deployment = _artifact(spec, artifacts, "deployment_topology")
    dependencies = _artifact(spec, artifacts, "dependency_inventory")
    data_classification = _artifact(spec, artifacts, "data_classification")

    text = _haystack(spec)
    data_exchanged = _data_exchanged(text, privacy, data_classification)

    return {
        "spec": spec,
        "source": source,
        "project": project,
        "solution": solution,
        "execution": execution,
        "privacy": privacy,
        "security": security,
        "threat_model": threat_model,
        "deployment": deployment,
        "dependencies": dependencies,
        "data_classification": data_classification,
        "title": _compact(project.get("title")) or _compact(source.get("idea_id")) or "Untitled TactSpec",
        "workflow_context": _compact(project.get("workflow_context")) or "primary workflow",
        "stack": solution.get("suggested_stack"),
        "integrations": spec.get("integrations"),
        "data_exchanged": data_exchanged,
        "sensitive_data": any(item in _SENSITIVE_DATA for item in data_exchanged),
        "regulated_context": _contains_any(text, ("gdpr", "hipaa", "sox", "regulated", "patient", "payment")),
        "mentions_vendor_contract": _contains_any(
            text, ("dpa", "soc 2", "subprocessor", "sla", "baa", "vendor review")
        ),
        "mentions_residency": _contains_any(text, ("region", "residency", "cross-border", "eu", "us-only")),
        "mentions_failover": _contains_any(text, ("failover", "fallback", "queue", "retry", "circuit breaker")),
    }


def _vendors(context: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for field, name, category in _vendor_sources(context):
        records.append(
            {
                "name": name,
                "category": category,
                "source_fields": [field],
                "data_exchanged": _vendor_data(context, name, category),
                "operational_dependency": _operational_dependency(context, name, category),
                "review_requirements": _vendor_review_requirements(context, category),
                "risk_level": _vendor_risk_level(context, category),
            }
        )

    vendors = _dedupe_vendors(records)
    if vendors:
        return [
            {
                "id": f"VEND{index:02d}",
                **vendor,
                "source_fields": _dedupe_strings(vendor["source_fields"]),
                "data_exchanged": _dedupe_strings(vendor["data_exchanged"]),
                "review_requirements": _dedupe_strings(vendor["review_requirements"]),
            }
            for index, vendor in enumerate(vendors, start=1)
        ]

    return [
        {
            "id": "VEND01",
            "name": "Unspecified external vendor",
            "category": "missing_inventory",
            "source_fields": ["solution.suggested_stack", "integrations", "dependency_inventory"],
            "data_exchanged": ["unconfirmed production, customer, or operational data"],
            "operational_dependency": "No stack, integrations, or dependency inventory named the external vendor boundary.",
            "review_requirements": [
                "Complete vendor inventory with owner, purpose, data fields, contract status, and fallback plan."
            ],
            "risk_level": "high",
        }
    ]


def _vendor_sources(context: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for key, value in _dict(context["stack"]).items():
        for raw in _values(value):
            rows.append((f"solution.suggested_stack.{key}", *_classify_vendor(key, raw)))

    for key, value in _dict(context["integrations"]).items():
        for raw in _values(value):
            rows.append((f"integrations.{key}", *_classify_vendor(key, raw)))
    for raw in _list(context["integrations"]):
        rows.append(("integrations", *_classify_vendor("integration", raw)))

    for item in _list(_dict(context["dependencies"]).get("dependencies")):
        if not isinstance(item, dict):
            continue
        name = _compact(item.get("name"))
        dep_type = _compact(item.get("type")) or "dependency"
        if name:
            rows.append(("dependency_inventory.dependencies", *_classify_vendor(dep_type, name)))

    text = _haystack(
        {
            "project": context["project"],
            "solution": context["solution"],
            "execution": context["execution"],
            "privacy": context["privacy"],
            "security": context["security"],
            "threat_model": context["threat_model"],
            "deployment": context["deployment"],
        }
    )
    lowered = text.lower()
    for token, (label, category) in _KNOWN_VENDORS.items():
        if token in lowered:
            rows.append(("spec_text", label, category))

    return [row for row in rows if _compact(row[1])]


def _classify_vendor(key: str, value: Any) -> tuple[str, str]:
    raw = _compact(value) or _compact(key) or "External vendor"
    lowered = f"{key} {raw}".lower()
    for token, (label, category) in _KNOWN_VENDORS.items():
        if token in lowered:
            return label, category
    if any(term in lowered for term in ("postgres", "redis", "mysql", "mongodb", "s3", "database", "storage")):
        return raw, "data_platform"
    if any(term in lowered for term in ("auth", "oauth", "saml", "oidc", "sso")):
        return raw, "identity_provider"
    if any(term in lowered for term in ("email", "sms", "notification")):
        return raw, "communications"
    return raw, "external_service"


def _vendor_data(context: dict[str, Any], name: str, category: str) -> list[str]:
    data = list(context["data_exchanged"])
    if category in {"ai_provider", "observability"}:
        data.append("prompts, derived outputs, logs, or telemetry")
    if category in {"crm", "messaging", "communications"}:
        data.append("customer workflow metadata")
    if category in {"payments"}:
        data.append("payment data")
    if category in {"cloud_provider", "data_platform"}:
        data.append("application data, backups, logs, and configuration")
    if not data:
        data.append("workflow metadata")
    return _dedupe_strings(data)


def _operational_dependency(context: dict[str, Any], name: str, category: str) -> str:
    if category in {"cloud_provider", "data_platform"}:
        return f"{name} is on the critical path for hosting, storage, backups, or recovery."
    if category in {"identity_provider"}:
        return f"{name} can block user access and authorization decisions."
    if category in {"ai_provider", "crm", "messaging", "payments"}:
        return f"{name} can block or degrade a core workflow integration."
    if _dict(context["deployment"]):
        return f"{name} dependency should be validated against the deployment topology."
    return f"{name} dependency requires uptime, support, and fallback expectations before release."


def _vendor_review_requirements(context: dict[str, Any], category: str) -> list[str]:
    requirements = [
        "Name business owner, technical owner, purpose, environments, and launch criticality.",
        "Confirm contract status, support path, incident notification, and termination plan.",
    ]
    if context["sensitive_data"] or context["regulated_context"]:
        requirements.append("Complete privacy, security, and legal review for exchanged data.")
    if category in {"ai_provider", "payments", "identity_provider"}:
        requirements.append("Verify scopes, data retention, audit logging, and abuse controls.")
    if not context["mentions_vendor_contract"]:
        requirements.append("Record DPA, SLA, SOC 2, BAA, or equivalent evidence status.")
    if not context["mentions_failover"]:
        requirements.append("Document retry, fallback, manual workaround, and outage communication path.")
    return requirements


def _vendor_risk_level(context: dict[str, Any], category: str) -> str:
    if context["regulated_context"] and category in {"ai_provider", "payments", "crm", "data_platform", "cloud_provider"}:
        return "high"
    if context["sensitive_data"] and category in {"ai_provider", "observability", "messaging", "communications"}:
        return "high"
    if category in {"missing_inventory", "payments", "identity_provider"}:
        return "high"
    if category in {"cloud_provider", "data_platform", "crm", "ai_provider"}:
        return "medium"
    return "low"


def _risks(context: dict[str, Any], vendors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if vendors and vendors[0]["category"] == "missing_inventory":
        risks.append(
            _risk(
                "VRA-R01",
                "missing_vendor_inventory",
                "Vendor inventory is missing",
                "high",
                "The spec does not name stack vendors, integrations, or dependency inventory entries.",
                ["solution.suggested_stack", "integrations", "dependency_inventory"],
                ["Complete vendor inventory before implementation starts."],
            )
        )

    if context["sensitive_data"] or context["regulated_context"]:
        risks.append(
            _risk(
                f"VRA-R{len(risks) + 1:02d}",
                "sensitive_vendor_transfer",
                "Sensitive data may be exchanged with vendors",
                "high",
                "Detected data or domain terms require confirmation of processing purpose, retention, subprocessors, and legal basis.",
                ["privacy_impact_assessment", "data_classification", "project", "solution"],
                ["Require privacy and security signoff before using production data."],
            )
        )

    if any(vendor["risk_level"] == "high" for vendor in vendors):
        risks.append(
            _risk(
                f"VRA-R{len(risks) + 1:02d}",
                "critical_vendor_dependency",
                "High-risk vendors can block release or operations",
                "high",
                "One or more vendors handles sensitive data, identity, payment, AI, cloud, or missing-inventory responsibilities.",
                ["vendors", "dependency_inventory", "deployment_topology"],
                ["Define owner, support path, fallback, incident contact, and launch accept-or-block decision for each high-risk vendor."],
            )
        )

    if not context["mentions_vendor_contract"]:
        risks.append(
            _risk(
                f"VRA-R{len(risks) + 1:02d}",
                "contract_evidence_gap",
                "Vendor contract and assurance evidence is not explicit",
                "medium",
                "The spec does not mention DPA, SOC 2, SLA, BAA, subprocessor, or equivalent vendor assurance evidence.",
                ["project", "solution", "execution", "security_review"],
                ["Attach or reference vendor assurance evidence before launch review."],
            )
        )

    if not context["mentions_failover"]:
        risks.append(
            _risk(
                f"VRA-R{len(risks) + 1:02d}",
                "vendor_outage_gap",
                "Vendor outage behavior is unresolved",
                "medium",
                "The spec does not prove retry, fallback, queueing, manual workaround, or outage communication behavior.",
                ["deployment_topology", "dependency_inventory", "execution.risks"],
                ["Document degraded-mode behavior and customer communication triggers."],
            )
        )

    return _dedupe_risks(risks)


def _risk(
    risk_id: str,
    category: str,
    title: str,
    severity: str,
    description: str,
    evidence: list[str],
    mitigations: list[str],
) -> dict[str, Any]:
    return {
        "id": risk_id,
        "category": category,
        "title": title,
        "severity": severity,
        "description": description,
        "evidence": _dedupe_strings(evidence),
        "mitigations": mitigations,
    }


def _mitigations(
    context: dict[str, Any], vendors: list[dict[str, Any]], risks: list[dict[str, Any]]
) -> list[dict[str, str]]:
    actions = [
        ("product_owner", "Record vendor purpose, owner, launch criticality, and customer impact."),
        ("engineering_owner", "Limit vendor payloads to required fields and redact secrets from logs and telemetry."),
        ("security_owner", "Review authentication scopes, secrets handling, audit logs, and incident contacts."),
        ("operations_owner", "Define fallback, retry, rate-limit, and outage communication behavior."),
    ]
    if context["sensitive_data"] or context["regulated_context"]:
        actions.append(
            ("privacy_owner", "Confirm DPA, subprocessors, region, retention, deletion, and legal review requirements.")
        )
    if any(vendor["category"] == "ai_provider" for vendor in vendors):
        actions.append(
            ("ai_owner", "Document prompt, output, training-use, retention, evaluation, and human review controls.")
        )
    if any(risk["severity"] == "high" for risk in risks):
        actions.append(("release_owner", "Block release until all high-severity vendor risks have explicit accept-or-mitigate decisions."))
    return [
        {"id": f"VRA-M{index:02d}", "owner": owner, "action": action}
        for index, (owner, action) in enumerate(_dedupe_pairs(actions), start=1)
    ]


def _review_checklist(
    context: dict[str, Any], vendors: list[dict[str, Any]], risks: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    items = [
        _check("VRA-C01", "product_owner", "Vendor owner and purpose", "Each vendor has owner, business purpose, launch criticality, and customer impact documented."),
        _check("VRA-C02", "security_owner", "Security assurance", "Security review covers scopes, secrets, audit logs, incident contact, and assurance evidence."),
        _check("VRA-C03", "operations_owner", "Operational fallback", "Retries, degraded mode, manual workaround, and outage communication path are documented."),
    ]
    if context["sensitive_data"] or context["regulated_context"]:
        items.append(
            _check("VRA-C04", "privacy_owner", "Privacy and legal review", "Data fields, DPA or BAA status, subprocessors, retention, deletion, and region constraints are approved.")
        )
    if any(risk["severity"] == "high" for risk in risks):
        items.append(
            _check("VRA-C05", "release_owner", "Release gate signoff", "High-severity vendor risks have explicit mitigation or accepted-risk decisions.")
        )
    if vendors and vendors[0]["category"] == "missing_inventory":
        items.append(
            _check("VRA-C06", "engineering_owner", "Complete vendor inventory", "Stack, integrations, dependency inventory, and deployment topology name all external vendors.")
        )
    return items


def _check(check_id: str, owner: str, title: str, requirement: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "owner": owner,
        "title": title,
        "requirement": requirement,
        "status": "required",
    }


def _gate_decision(
    context: dict[str, Any],
    vendors: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    review_checklist: list[dict[str, Any]],
) -> dict[str, Any]:
    blocking_reasons = [
        risk["title"] for risk in risks if risk["severity"] == "high"
    ]
    if vendors and vendors[0]["category"] == "missing_inventory":
        blocking_reasons.append("External vendor boundary is not inventoried.")
    status = "blocked" if blocking_reasons else "review_required"
    if not blocking_reasons and context["mentions_vendor_contract"] and context["mentions_failover"]:
        status = "approved_with_conditions"

    return {
        "status": status,
        "blocking_reasons": _dedupe_strings(blocking_reasons),
        "required_reviews": _dedupe_strings(item["owner"] for item in review_checklist),
        "decision_rule": "blocked when vendor inventory is missing or high-severity vendor risks remain; otherwise requires owner review before release.",
    }


def _data_exchanged(
    text: str, privacy: dict[str, Any], data_classification: dict[str, Any]
) -> list[str]:
    data: list[str] = []
    lowered = text.lower()
    for token, label in _DATA_TERMS.items():
        if token in lowered:
            data.append(label)

    for item in _list(privacy.get("personal_data")):
        if isinstance(item, dict):
            data.append(_compact(item.get("label")) or _compact(item.get("id")))
    for item in _list(data_classification.get("categories")):
        if isinstance(item, dict):
            data.append(_compact(item.get("label")) or _compact(item.get("id")))
    return _dedupe_strings(item for item in data if item)


def _artifact(spec: dict[str, Any], artifacts: dict[str, Any], key: str) -> dict[str, Any]:
    return _dict(spec.get(key)) or _dict(artifacts.get(key))


def _extend_section(
    lines: list[str],
    title: str,
    items: list[Any],
    renderer,
    empty: str = "None.",
) -> None:
    lines.extend([f"## {title}", ""])
    if items:
        for item in items:
            lines.extend(renderer(item))
            lines.append("")
    else:
        lines.extend([empty, ""])


def _render_vendor(vendor: dict[str, Any]) -> list[str]:
    return [
        f"### {vendor.get('id')}: {_text(vendor.get('name'))}",
        "",
        f"- Category: {_text(vendor.get('category'))}",
        f"- Risk level: {_text(vendor.get('risk_level'))}",
        f"- Source fields: {_inline_list(vendor.get('source_fields') or [])}",
        f"- Data exchanged: {_inline_list(vendor.get('data_exchanged') or [])}",
        f"- Operational dependency: {_text(vendor.get('operational_dependency'))}",
        "- Review requirements:",
        *_bullets(vendor.get("review_requirements") or [], empty="None."),
    ]


def _render_risk(risk: dict[str, Any]) -> list[str]:
    return [
        f"### {risk.get('id')}: {_text(risk.get('title'))}",
        "",
        f"- Category: {_text(risk.get('category'))}",
        f"- Severity: {_text(risk.get('severity'))}",
        f"- Description: {_text(risk.get('description'))}",
        f"- Evidence: {_inline_list(risk.get('evidence') or [])}",
        "- Mitigations:",
        *_bullets(risk.get("mitigations") or [], empty="None."),
    ]


def _render_mitigation(mitigation: dict[str, Any]) -> list[str]:
    return [
        f"### {mitigation.get('id')}: {_text(mitigation.get('owner'))}",
        "",
        f"- Action: {_text(mitigation.get('action'))}",
    ]


def _render_checklist_item(item: dict[str, Any]) -> list[str]:
    return [
        f"### {item.get('id')}: {_text(item.get('title'))}",
        "",
        f"- Owner: {_text(item.get('owner'))}",
        f"- Status: {_text(item.get('status'))}",
        f"- Requirement: {_text(item.get('requirement'))}",
    ]


def _render_gate(gate: dict[str, Any]) -> list[str]:
    return [
        f"- Status: {_text(gate.get('status'))}",
        f"- Required reviews: {_inline_list(gate.get('required_reviews') or [])}",
        "- Blocking reasons:",
        *_bullets(gate.get("blocking_reasons") or [], empty="None."),
        f"- Decision rule: {_text(gate.get('decision_rule'))}",
    ]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _values(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    return _list(value)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return " ".join(str(value).split())


def _text(value: Any) -> str:
    return _compact(value)


def _haystack(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            parts.append(_compact(key))
            parts.append(_haystack(value[key]))
    elif isinstance(value, list | tuple | set):
        for item in value:
            parts.append(_haystack(item))
    else:
        parts.append(_compact(value))
    return " ".join(part for part in parts if part)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _dedupe_vendors(vendors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for vendor in vendors:
        key = vendor["name"].casefold()
        if key not in by_name:
            by_name[key] = vendor
            continue
        existing = by_name[key]
        existing["source_fields"].extend(vendor["source_fields"])
        existing["data_exchanged"].extend(vendor["data_exchanged"])
        existing["review_requirements"].extend(vendor["review_requirements"])
        if _risk_rank(vendor["risk_level"]) < _risk_rank(existing["risk_level"]):
            existing["risk_level"] = vendor["risk_level"]
            existing["operational_dependency"] = vendor["operational_dependency"]
    return sorted(by_name.values(), key=lambda item: (_risk_rank(item["risk_level"]), item["name"]))


def _dedupe_risks(risks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for risk in risks:
        key = risk["category"]
        if key in seen:
            continue
        seen.add(key)
        result.append(risk)
    return result


def _dedupe_strings(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _compact(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _dedupe_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for owner, action in values:
        key = (owner, action)
        if key not in seen:
            seen.add(key)
            result.append((owner, action))
    return result


def _risk_rank(level: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(level, 3)


def _inline_list(values: list[Any]) -> str:
    items = _dedupe_strings(values)
    return ", ".join(items) if items else "none"


def _bullets(values: list[Any], empty: str) -> list[str]:
    items = _dedupe_strings(values)
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]
