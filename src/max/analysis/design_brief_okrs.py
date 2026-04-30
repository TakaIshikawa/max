"""Deterministic OKR export for design brief payloads."""

from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = "max.design_brief.okrs.v1"

_HIGH_RISK_KEYWORDS = (
    "compliance",
    "credential",
    "external",
    "hipaa",
    "legal",
    "oauth",
    "pii",
    "privacy",
    "regulated",
    "security",
)


def build_design_brief_okrs(design_brief: dict[str, Any]) -> dict[str, Any]:
    """Build measurable execution OKRs from a dict-like design brief payload."""
    risks = _risk_records(design_brief)
    validation_experiments = _validation_experiments(design_brief)
    roadmap_items = _roadmap_items(design_brief)
    evaluation_scores = _evaluation_scores(design_brief)
    confidence = _confidence(design_brief, evaluation_scores, validation_experiments, risks)
    risk_summary = _risk_summary(design_brief, risks)
    objectives = _objectives(
        design_brief,
        confidence=confidence,
        risk_summary=risk_summary,
        validation_experiments=validation_experiments,
        roadmap_items=roadmap_items,
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
            "generated_at": design_brief.get("updated_at") or design_brief.get("created_at"),
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
        },
        "summary": {
            "objective_count": len(objectives),
            "key_result_count": sum(len(objective["key_results"]) for objective in objectives),
            "confidence_level": confidence["level"],
            "risk_level": risk_summary["level"],
            "validation_required": _needs_validation(confidence, risk_summary, design_brief),
        },
        "confidence": confidence,
        "risk_summary": risk_summary,
        "evaluation_scores": evaluation_scores,
        "validation_experiments": validation_experiments,
        "roadmap_items": roadmap_items,
        "objectives": objectives,
    }


def render_design_brief_okrs_markdown(report: dict[str, Any]) -> str:
    """Render a design brief OKR report as stable Markdown."""
    brief = report["design_brief"]
    lines = [
        f"# OKRs: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Confidence: `{report['confidence']['level']}`",
        f"Risk: `{report['risk_summary']['level']}`",
        "",
        "## Summary",
        "",
        f"- Objectives: {report['summary']['objective_count']}",
        f"- Key results: {report['summary']['key_result_count']}",
        f"- Validation required: {_yes_no(report['summary']['validation_required'])}",
        "",
        "## Objectives",
        "",
    ]
    for objective in report["objectives"]:
        lines.extend(
            [
                f"### {objective['id']}: {objective['objective']}",
                "",
                f"- Owner hint: {objective['owner_hint']}",
                f"- Confidence: `{objective['confidence']}`",
                f"- Risk: `{objective['risk_level']}`",
                "- Key results:",
            ]
        )
        for key_result in objective["key_results"]:
            lines.append(
                f"  - **{key_result['id']}**: {key_result['metric']} "
                f"Target: {key_result['target']}. Evidence: {key_result['evidence_source']}."
            )
        lines.append("")

    lines.extend(["## Risk Annotations", ""])
    for risk in report["risk_summary"]["top_risks"]:
        lines.append(f"- **{risk['id']}** (`{risk['severity']}`): {risk['title']}")
    if not report["risk_summary"]["top_risks"]:
        lines.append("- No explicit risks were provided.")

    return "\n".join(lines).rstrip() + "\n"


def _objectives(
    design_brief: dict[str, Any],
    *,
    confidence: dict[str, Any],
    risk_summary: dict[str, Any],
    validation_experiments: list[dict[str, Any]],
    roadmap_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    objectives = [
        _objective(
            "O1",
            f"Validate demand for {design_brief['title']}",
            _owner_hint(design_brief, default="Product lead"),
            confidence["level"],
            risk_summary["level"],
            _demand_key_results(design_brief, validation_experiments, confidence, risk_summary),
        ),
        _objective(
            "O2",
            "Deliver the first measurable MVP workflow",
            _owner_for_scope(_first(_string_list(design_brief.get("mvp_scope"))) or ""),
            confidence["level"],
            _delivery_risk(risk_summary),
            _delivery_key_results(design_brief, roadmap_items),
        ),
        _objective(
            "O3",
            "Create evidence-backed launch readiness",
            "Product operations lead",
            confidence["level"],
            risk_summary["level"],
            _readiness_key_results(design_brief, confidence, risk_summary),
        ),
    ]
    if _needs_validation(confidence, risk_summary, design_brief):
        objectives.append(
            _objective(
                "O4",
                "Reduce the riskiest assumptions before scaling build effort",
                "Research lead",
                confidence["level"],
                "high" if risk_summary["level"] == "high" else "medium",
                _validation_key_results(design_brief, validation_experiments, risk_summary),
            )
        )
    return objectives


def _demand_key_results(
    design_brief: dict[str, Any],
    validation_experiments: list[dict[str, Any]],
    confidence: dict[str, Any],
    risk_summary: dict[str, Any],
) -> list[dict[str, str]]:
    user = _clean(design_brief.get("specific_user")) or "target users"
    buyer = _clean(design_brief.get("buyer")) or "the buyer"
    krs = [
        _kr("KR1", f"Interview at least 5 {user}", "5 completed interviews", "Customer discovery notes"),
        _kr("KR2", f"Confirm {buyer} owns the budget or approval path", "3 qualified buyer confirmations", "Buyer validation log"),
    ]
    if confidence["level"] != "high" or risk_summary["level"] in {"medium", "high"}:
        krs.append(
            _kr(
                "KR3",
                "Run a validation experiment with explicit proceed or stop criteria",
                _experiment_target(validation_experiments),
                "Validation experiment results",
            )
        )
    else:
        krs.append(
            _kr("KR3", "Convert validated demand into a committed pilot cohort", "2 pilot teams committed", "Pilot pipeline")
        )
    return krs


def _delivery_key_results(design_brief: dict[str, Any], roadmap_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    scope = _string_list(design_brief.get("mvp_scope"))
    milestones = _string_list(design_brief.get("first_milestones"))
    first_scope = _first(scope) or "core product workflow"
    first_milestone = _first(milestones) or _first_title(roadmap_items) or "first MVP milestone"
    return [
        _kr("KR1", f"Ship {first_scope} in a testable MVP slice", "1 working end-to-end slice", "Demo build and test run"),
        _kr("KR2", f"Complete {first_milestone}", "Acceptance criteria met", "Roadmap or milestone tracker"),
        _kr("KR3", "Keep unresolved implementation blockers visible", "0 blocking issues without owner and next action", "Delivery risk log"),
    ]


def _readiness_key_results(
    design_brief: dict[str, Any],
    confidence: dict[str, Any],
    risk_summary: dict[str, Any],
) -> list[dict[str, str]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    target = min(95.0, max(80.0, readiness + 5.0))
    krs = [
        _kr("KR1", "Raise design brief readiness with fresh evidence", f"Readiness score >= {target:.1f}", "Design brief review"),
        _kr("KR2", "Document owners for product, engineering, and validation decisions", "3 owner roles named", "Execution handoff"),
    ]
    if risk_summary["level"] == "low" and confidence["level"] == "high":
        krs.append(_kr("KR3", "Prepare launch or beta decision package", "Decision package accepted", "Launch review"))
    else:
        krs.append(_kr("KR3", "Close the highest-priority risk before launch or beta expansion", "Top risk mitigated or accepted", "Risk register"))
    return krs


def _validation_key_results(
    design_brief: dict[str, Any],
    validation_experiments: list[dict[str, Any]],
    risk_summary: dict[str, Any],
) -> list[dict[str, str]]:
    top_risk = _first(risk_summary["top_risks"])
    risk_title = top_risk["title"] if top_risk else "weakest assumption"
    plan = _clean(design_brief.get("validation_plan")) or _first_title(validation_experiments) or "a focused validation plan"
    return [
        _kr("KR1", f"Execute {plan}", _experiment_target(validation_experiments), "Validation plan"),
        _kr("KR2", f"Resolve or mitigate {risk_title}", "Mitigation accepted by named owner", "Risk register"),
        _kr("KR3", "Prevent weak evidence from entering delivery scope", "0 roadmap items without evidence or validation action", "Roadmap review"),
    ]


def _confidence(
    design_brief: dict[str, Any],
    evaluation_scores: list[dict[str, Any]],
    validation_experiments: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    readiness = min(max(float(design_brief.get("readiness_score") or 0.0) / 100.0, 0.0), 1.0)
    evaluation = _average(item["score"] for item in evaluation_scores) / 100.0 if evaluation_scores else 0.0
    evidence = 0.0
    if _clean(design_brief.get("validation_plan")):
        evidence += 0.35
    if validation_experiments:
        evidence += min(len(validation_experiments) / 4.0, 1.0) * 0.35
    if design_brief.get("buyer") and design_brief.get("specific_user"):
        evidence += 0.30
    risk_penalty = min(len([risk for risk in risks if risk["severity"] == "high"]) * 0.08, 0.24)
    score = round(max(0.0, min(1.0, readiness * 0.45 + evaluation * 0.25 + evidence * 0.30 - risk_penalty)), 2)
    return {
        "score": score,
        "level": "high" if score >= 0.74 else "medium" if score >= 0.45 else "low",
        "drivers": [
            f"readiness={float(design_brief.get('readiness_score') or 0.0):.1f}",
            f"evaluations={len(evaluation_scores)}",
            f"validation_experiments={len(validation_experiments)}",
            f"high_risks={sum(1 for risk in risks if risk['severity'] == 'high')}",
        ],
    }


def _risk_summary(design_brief: dict[str, Any], risks: list[dict[str, Any]]) -> dict[str, Any]:
    high_count = sum(1 for risk in risks if risk["severity"] == "high")
    medium_count = sum(1 for risk in risks if risk["severity"] == "medium")
    weak_evidence = not _clean(design_brief.get("validation_plan"))
    level = "high" if high_count or _has_high_risk_text(design_brief) else "medium" if medium_count or weak_evidence else "low"
    return {
        "level": level,
        "high_risk_count": high_count,
        "medium_risk_count": medium_count,
        "weak_evidence": weak_evidence,
        "top_risks": risks[:3],
    }


def _risk_records(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, risk in enumerate(_string_list(design_brief.get("risks")), start=1):
        records.append(
            {
                "id": f"R{index}",
                "title": _short_title(risk),
                "description": risk,
                "severity": "high",
                "source": "design_brief.risks",
            }
        )

    register = design_brief.get("risk_register")
    for risk in _list_from_artifact(register, "risks"):
        if not isinstance(risk, dict):
            continue
        title = _clean(risk.get("title")) or _short_title(_clean(risk.get("description")))
        if not title:
            continue
        records.append(
            {
                "id": f"R{len(records) + 1}",
                "title": title,
                "description": _clean(risk.get("description")) or title,
                "severity": _severity(risk.get("severity") or risk.get("risk_level")),
                "source": "risk_register",
            }
        )
    return _dedupe_records(records, "title")


def _validation_experiments(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    experiments = []
    for source_key in ("validation_experiments", "experiments"):
        for item in _list_value(design_brief.get(source_key)):
            experiments.append(_experiment_record(item, source_key))
    validation_artifact = design_brief.get("validation_plan_artifact") or design_brief.get("validation_plan_report")
    for item in _list_from_artifact(validation_artifact, "experiments"):
        experiments.append(_experiment_record(item, "validation_plan"))
    return _dedupe_records([item for item in experiments if item["title"]], "title")


def _roadmap_items(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for item in _list_value(design_brief.get("roadmap_items")):
        items.append(_roadmap_record(item, "roadmap_items"))
    roadmap = design_brief.get("roadmap")
    for item in _list_from_artifact(roadmap, "items"):
        items.append(_roadmap_record(item, "roadmap"))
    for phase in _list_from_artifact(roadmap, "phases"):
        if isinstance(phase, dict):
            for item in _list_value(phase.get("items")):
                items.append(_roadmap_record(item, "roadmap.phases"))
    return _dedupe_records([item for item in items if item["title"]], "title")


def _evaluation_scores(design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for source_key in ("evaluation_scores", "evaluations"):
        for item in _list_value(design_brief.get(source_key)):
            if isinstance(item, dict):
                value = item.get("overall_score") or item.get("score") or item.get("value")
                if value is None:
                    continue
                scores.append(
                    {
                        "id": _clean(item.get("id") or item.get("idea_id") or item.get("unit_id")) or f"E{len(scores) + 1}",
                        "score": round(float(value), 2),
                        "recommendation": _clean(item.get("recommendation")),
                    }
                )
            elif item is not None:
                scores.append({"id": f"E{len(scores) + 1}", "score": round(float(item), 2), "recommendation": ""})
    return scores


def _objective(
    item_id: str,
    objective: str,
    owner_hint: str,
    confidence: str,
    risk_level: str,
    key_results: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "objective": objective,
        "owner_hint": owner_hint,
        "confidence": confidence,
        "risk_level": risk_level,
        "key_results": key_results,
    }


def _kr(item_id: str, metric: str, target: str, evidence_source: str) -> dict[str, str]:
    return {
        "id": item_id,
        "metric": metric,
        "target": target,
        "evidence_source": evidence_source,
    }


def _needs_validation(confidence: dict[str, Any], risk_summary: dict[str, Any], design_brief: dict[str, Any]) -> bool:
    return (
        confidence["level"] != "high"
        or risk_summary["level"] in {"medium", "high"}
        or not _clean(design_brief.get("validation_plan"))
    )


def _owner_hint(design_brief: dict[str, Any], *, default: str) -> str:
    buyer = _clean(design_brief.get("buyer"))
    if buyer:
        return f"Product lead with {buyer}"
    return default


def _owner_for_scope(scope: str) -> str:
    lowered = scope.lower()
    if any(keyword in lowered for keyword in ("api", "cli", "integration", "github", "data")):
        return "Engineering lead"
    if any(keyword in lowered for keyword in ("research", "validation", "interview")):
        return "Research lead"
    return "Product engineer"


def _delivery_risk(risk_summary: dict[str, Any]) -> str:
    return "medium" if risk_summary["level"] == "high" else risk_summary["level"]


def _experiment_target(validation_experiments: list[dict[str, Any]]) -> str:
    first = _first(validation_experiments)
    if first and first.get("success_metric"):
        return str(first["success_metric"])
    if validation_experiments:
        return "1 experiment reaches its success threshold"
    return "1 completed validation run with documented threshold"


def _experiment_record(item: Any, source: str) -> dict[str, Any]:
    if isinstance(item, dict):
        title = _clean(item.get("title") or item.get("name") or item.get("experiment"))
        return {
            "title": title,
            "success_metric": _clean(item.get("success_metric") or item.get("target") or item.get("exit_criteria")),
            "source": source,
        }
    return {"title": _clean(item), "success_metric": "", "source": source}


def _roadmap_record(item: Any, source: str) -> dict[str, Any]:
    if isinstance(item, dict):
        title = _clean(item.get("title") or item.get("name"))
        return {
            "title": title,
            "phase": _clean(item.get("phase")),
            "owner_role": _clean(item.get("owner_role") or item.get("owner_hint")),
            "exit_criteria": _clean(item.get("exit_criteria")),
            "source": source,
        }
    return {"title": _clean(item), "phase": "", "owner_role": "", "exit_criteria": "", "source": source}


def _list_from_artifact(artifact: Any, key: str) -> list[Any]:
    if isinstance(artifact, dict):
        return _list_value(artifact.get(key))
    return []


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [_clean(item) for item in _list_value(value) if _clean(item)]


def _dedupe_records(records: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        marker = _clean(record.get(key)).lower()
        if not marker or marker in seen:
            continue
        seen.add(marker)
        if record.get("id", "").startswith("R"):
            record = {**record, "id": f"R{len(deduped) + 1}"}
        deduped.append(record)
    return deduped


def _severity(value: Any) -> str:
    severity = _clean(value).lower()
    return severity if severity in {"low", "medium", "high"} else "medium"


def _average(values: Any) -> float:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else 0.0


def _first(items: list[Any]) -> Any:
    return items[0] if items else None


def _first_title(items: list[dict[str, Any]]) -> str:
    first = _first(items)
    return _clean(first.get("title")) if isinstance(first, dict) else ""


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _short_title(text: str) -> str:
    cleaned = _clean(text)
    if not cleaned:
        return "Unspecified risk"
    sentence = re.split(r"[.;:]", cleaned, maxsplit=1)[0]
    words = sentence.split()
    return " ".join(words[:8])


def _has_high_risk_text(design_brief: dict[str, Any]) -> bool:
    text = " ".join(
        [
            _clean(design_brief.get("validation_plan")),
            *(_string_list(design_brief.get("risks"))),
            _clean(design_brief.get("merged_product_concept")),
        ]
    ).lower()
    return any(keyword in text for keyword in _HIGH_RISK_KEYWORDS)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
