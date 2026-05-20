"""Generate deterministic customer validation evidence plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-customer-validation-evidence-plan/v1"
KIND = "max.spec.customer_validation_evidence_plan"


def generate_customer_validation_evidence_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    hypotheses = _hypotheses(unit, spec)
    segments = _segments(unit, spec)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(unit, spec),
        "validation_hypotheses": hypotheses,
        "customer_segments": segments,
        "evidence_requests": _evidence_requests(hypotheses, segments),
        "storage_expectations": _storage_expectations(),
        "confidence_scoring": _confidence_scoring(evaluation),
        "decision_thresholds": _decision_thresholds(evaluation),
    }


def render_customer_validation_evidence_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Customer Validation Evidence Plan")
    for title, key in (("Validation Hypotheses", "validation_hypotheses"), ("Customer Segments", "customer_segments"), ("Evidence Requests", "evidence_requests"), ("Storage Expectations", "storage_expectations"), ("Confidence Scoring", "confidence_scoring"), ("Decision Thresholds", "decision_thresholds")):
        _extend(lines, title, plan.get(key) or [], lambda item: [f"- {item['id']}: {item.get('hypothesis') or item.get('request') or item.get('segment') or item.get('rule') or item.get('threshold')}"])
    return "\n".join(lines).rstrip() + "\n"


def _hypotheses(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "value_proposition")) + _values(_field(unit, "problem")) + _list(spec, "acceptance_criteria", "criteria")
    seeds = seeds or ["target customers confirm the proposed workflow solves a material problem"]
    return [{"id": f"CVE-H{index}", "hypothesis": item, "signal_needed": "customer quote or pilot observation"} for index, item in enumerate(_dedupe(seeds)[:4], start=1)]


def _segments(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "first_10_customers")) + _values(_field(unit, "specific_user")) + _values(_field(unit, "target_users")) + _list(spec, "project", "target_segments")
    seeds = seeds or ["target customer segment"]
    return [{"id": f"CVE-S{index}", "segment": item, "recruiting_owner": _first(_field(unit, "buyer"), "customer lead")} for index, item in enumerate(_dedupe(seeds)[:5], start=1)]


def _evidence_requests(hypotheses: list[dict[str, str]], segments: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for hypothesis in hypotheses:
        rows.append({"id": f"CVE-E{len(rows) + 1}", "request": f"Collect interview evidence for {hypothesis['hypothesis']}", "segment": segments[0]["segment"], "artifact": "interview note"})
    rows.append({"id": f"CVE-E{len(rows) + 1}", "request": "Collect pilot usage artifact", "segment": segments[0]["segment"], "artifact": "pilot evidence"})
    return rows


def _storage_expectations() -> list[dict[str, str]]:
    return [{"id": "CVE-ST1", "rule": "Store raw notes, consent, and synthesized evidence in the validation record"}, {"id": "CVE-ST2", "rule": "Link each artifact to a hypothesis and customer segment"}]


def _confidence_scoring(evaluation: Any | None) -> list[dict[str, Any]]:
    score = _number(_field(evaluation, "overall_score"))
    minimum = 4 if score is not None and score < 60 else 3
    return [{"id": "CVE-C1", "rule": "score each hypothesis from 1-5 using evidence quality", "minimum_confidence": minimum}]


def _decision_thresholds(evaluation: Any | None) -> list[dict[str, str]]:
    score = _number(_field(evaluation, "overall_score"))
    threshold = "average confidence >= 4 with no critical objections" if score is not None and score < 60 else "average confidence >= 3"
    return [{"id": "CVE-D1", "threshold": threshold, "decision": "continue"}, {"id": "CVE-D2", "threshold": "confidence below threshold or unresolved buyer objection", "decision": "revise"}]


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    return {"idea_id": _first(_field(unit, "id"), _nested(spec, "source", "idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled validation plan"), "domain": _first(_field(unit, "domain"), "")}


def _header(plan: dict[str, Any], label: str) -> list[str]:
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return [f"# {_text(source.get('title'))} {label}", "", f"- Schema version: {_text(plan.get('schema_version'))}", f"- Kind: {_text(plan.get('kind'))}", ""]


def _extend(lines: list[str], title: str, items: list[dict[str, Any]], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    for item in items:
        lines.extend(renderer(item))
    lines.append("")


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None) if obj is not None else None


def _nested(data: dict[str, Any], *keys: str) -> Any:
    value: Any = data
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _list(data: dict[str, Any], section: str, key: str) -> list[str]:
    return _values(_nested(data, section, key))


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value:
            compacted = _compact(item.get("name") or item.get("criterion") or item.get("segment") or item.get("description")) if isinstance(item, dict) else _compact(item)
            if compacted:
                result.append(compacted)
        return result
    compacted = _compact(value)
    return [compacted] if compacted else []


def _dedupe(values: list[str]) -> list[str]:
    result, seen = [], set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _first(*values: Any) -> str:
    return next((_compact(value) for value in values if _compact(value)), "")


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _compact(value: Any) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def _text(value: Any) -> str:
    return "" if value is None else str(value)
