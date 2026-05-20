"""Generate deterministic pilot success review plans."""

from __future__ import annotations

from typing import Any


SCHEMA_VERSION = "max-pilot-success-review-plan/v1"
KIND = "max.spec.pilot_success_review_plan"


def generate_pilot_success_review_plan(unit: Any, evaluation: Any | None = None, tact_spec_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = tact_spec_preview if isinstance(tact_spec_preview, dict) else {}
    source = _source(unit, spec)
    score = _number(_field(evaluation, "overall_score"))
    recommendation = _compact(_field(evaluation, "recommendation")) or "not_evaluated"
    goals = _pilot_goals(unit, spec)
    metrics = _success_metrics(unit, evaluation, spec)
    criteria = _decision_criteria(score, recommendation, _values(_field(evaluation, "weaknesses")))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": source,
        "summary": {"title": source["title"], "pilot_goal_count": len(goals), "metric_count": len(metrics), "recommendation": recommendation, "evaluation_score": score},
        "pilot_goals": goals,
        "success_metrics": metrics,
        "review_agenda": _review_agenda(unit, spec),
        "evidence_requests": _evidence_requests(unit, evaluation, spec),
        "decision_criteria": criteria,
        "next_step_recommendations": _next_steps(criteria),
    }


def render_pilot_success_review_plan_markdown(plan: dict[str, Any]) -> str:
    lines = _header(plan, "Pilot Success Review Plan")
    _extend(lines, "Pilot Goals", plan.get("pilot_goals") or [], lambda item: [f"- {item['id']}: {item['goal']} owner={item['owner']}"])
    _extend(lines, "Success Metrics", plan.get("success_metrics") or [], lambda item: [f"- {item['id']}: {item['metric']} target={item['target']}"])
    _extend(lines, "Review Agenda", plan.get("review_agenda") or [], lambda item: [f"- {item['id']}: {item['topic']} ({item['duration_minutes']}m)"])
    _extend(lines, "Evidence Requests", plan.get("evidence_requests") or [], lambda item: [f"- {item['id']}: {item['evidence']} source={item['source']}"])
    _extend(lines, "Decision Criteria", plan.get("decision_criteria") or [], lambda item: [f"- {item['id']}: {item['decision']} condition={item['condition']}"])
    return "\n".join(lines).rstrip() + "\n"


def _pilot_goals(unit: Any, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "value_proposition")) + _values(_field(unit, "validation_plan")) + _list(spec, "execution", "mvp_scope")
    seeds = seeds or ["Validate customer value in the pilot workflow"]
    return [{"id": f"PSR-G{index}", "goal": item, "owner": _first(_field(unit, "buyer"), "pilot sponsor")} for index, item in enumerate(_dedupe(seeds)[:4], start=1)]


def _success_metrics(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = _list(spec, "execution", "success_metrics") or _list(spec, "acceptance_criteria", "criteria")
    if not metrics:
        metrics = ["Pilot users complete the primary workflow", "Sponsor confirms expansion value"]
    score = _number(_field(evaluation, "overall_score"))
    target = "meets pilot target" if score is None or score >= 70 else "requires mitigation plan before expansion"
    return [{"id": f"PSR-M{index}", "metric": item, "target": target, "evidence": "pilot review packet"} for index, item in enumerate(_dedupe(metrics)[:5], start=1)]


def _review_agenda(unit: Any, spec: dict[str, Any]) -> list[dict[str, Any]]:
    topics = ["Pilot goals recap", "Metric and evidence review", "Customer objections", "Expansion decision", "Next-step owners"]
    return [{"id": f"PSR-A{index}", "topic": topic, "duration_minutes": 10 if index < 5 else 5, "owner": _first(_field(unit, "specific_user"), "pilot lead")} for index, topic in enumerate(topics, start=1)]


def _evidence_requests(unit: Any, evaluation: Any | None, spec: dict[str, Any]) -> list[dict[str, str]]:
    seeds = _values(_field(unit, "evidence_rationale")) + _list(spec, "evidence", "rationale") + _values(_field(evaluation, "strengths"))[:2]
    seeds = seeds or ["Usage notes, stakeholder quotes, and unresolved pilot risks"]
    return [{"id": f"PSR-E{index}", "evidence": item, "source": _first(_field(unit, "specific_user"), "pilot customer"), "required": "true"} for index, item in enumerate(_dedupe(seeds)[:5], start=1)]


def _decision_criteria(score: float | None, recommendation: str, weaknesses: list[str]) -> list[dict[str, str]]:
    threshold = "overall score >= 70" if score is not None else "customer sponsor confirms value"
    result = [
        {"id": "PSR-D1", "decision": "expand", "condition": f"{threshold} and no unresolved blocker", "recommendation_context": recommendation},
        {"id": "PSR-D2", "decision": "extend_pilot", "condition": "metrics are mixed or evidence is incomplete", "recommendation_context": recommendation},
        {"id": "PSR-D3", "decision": "stop", "condition": "customer value is unproven or sponsor rejects rollout", "recommendation_context": recommendation},
    ]
    if score is not None and score < 60 or recommendation in {"no", "strong_no"} or weaknesses:
        result[0]["condition"] = "all weaknesses have named mitigations and sponsor explicitly accepts residual risk"
    return result


def _next_steps(criteria: list[dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": f"PSR-N{index}", "trigger": item["decision"], "action": f"Prepare {item['decision']} follow-up plan"} for index, item in enumerate(criteria, start=1)]


def _header(plan: dict[str, Any], label: str) -> list[str]:
    summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}
    return [f"# {_text(summary.get('title')) or 'Pilot'} {label}", "", f"- Schema version: {_text(plan.get('schema_version'))}", f"- Kind: {_text(plan.get('kind'))}", f"- Source idea ID: {_text(source.get('idea_id'))}", ""]


def _extend(lines: list[str], title: str, items: list[dict[str, Any]], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    for item in items:
        lines.extend(renderer(item))
    lines.append("")


def _source(unit: Any, spec: dict[str, Any]) -> dict[str, str]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"idea_id": _first(_field(unit, "id"), source.get("idea_id"), "unknown"), "title": _first(_field(unit, "title"), _nested(spec, "project", "title"), "Untitled pilot"), "domain": _first(_field(unit, "domain"), source.get("domain"), "")}


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
            compacted = _compact(item.get("name") or item.get("criterion") or item.get("description") or item.get("metric")) if isinstance(item, dict) else _compact(item)
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
