"""Generate deterministic release rollback drill plans."""

from __future__ import annotations

from typing import Any

from max.spec._planning_common import compact, markdown_header, number, string_list, text


SCHEMA_VERSION = "max-release-rollback-drill-plan/v1"
KIND = "max.release_rollback_drill_plan"


def generate_release_rollback_drill_plan(spec_like: Any) -> dict[str, Any]:
    """Return drill scope, triggers, roles, probes, timing targets, and follow-ups."""
    spec = spec_like if isinstance(spec_like, dict) else {}
    scope = _drill_scope(spec)
    triggers = _trigger_matrix(spec)
    participants = _participant_roles(spec)
    probes = _validation_probes(spec)
    timing = _timing_targets(spec)
    comms = _communication_checkpoints(spec)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "source": _source(spec),
        "summary": {
            "title": _title(spec),
            "component_count": len(scope),
            "critical_trigger_count": sum(1 for item in triggers if item["classification"] == "critical"),
            "participant_count": len(participants),
            "probe_count": len(probes),
            "timing_target_count": len(timing),
            "checkpoint_count": len(comms),
        },
        "drill_scope": scope,
        "trigger_matrix": triggers,
        "participant_roles": participants,
        "validation_probes": probes,
        "timing_targets": timing,
        "communication_checkpoints": comms,
        "follow_up_actions": _follow_up_actions(spec, triggers, probes),
    }


def render_release_rollback_drill_plan_markdown(plan: dict[str, Any]) -> str:
    """Render a rollback drill plan as deterministic Markdown."""
    lines = markdown_header(plan, "Release Rollback Drill Plan")
    _extend(lines, "Drill Agenda", plan.get("drill_scope") or [], _render_scope)
    _extend(lines, "Rollback Decision Points", plan.get("trigger_matrix") or [], _render_trigger)
    _extend(lines, "Participant Roles", plan.get("participant_roles") or [], _render_participant)
    _extend(lines, "Validation Checklist", plan.get("validation_probes") or [], _render_probe)
    _extend(lines, "Timing Targets", plan.get("timing_targets") or [], _render_timing)
    _extend(lines, "Communication Checkpoints", plan.get("communication_checkpoints") or [], _render_checkpoint)
    _extend(lines, "Retrospective", plan.get("follow_up_actions") or [], _render_follow_up)
    return "\n".join(lines).rstrip() + "\n"


def _drill_scope(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("release_components") or spec.get("components"), "component")
    if not rows:
        rows = [{"component": "release artifact"}]
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"SCP{len(result) + 1}",
                "component": row["component"],
                "release": _first(row.get("release"), row.get("version"), spec.get("release"), "current release"),
                "rollback_method": _first(row.get("rollback_method"), row.get("method"), "restore previous stable version"),
                "owner": _first(row.get("owner"), "release_owner"),
                "scope_note": _first(row.get("scope_note"), row.get("description"), "Exercise rollback readiness for this component."),
            }
        )
    return sorted(result, key=lambda item: item["component"].casefold())


def _trigger_matrix(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("rollback_triggers") or spec.get("triggers"), "trigger")
    result: list[dict[str, Any]] = []
    for row in rows:
        classification = _trigger_classification(row)
        result.append(
            {
                "id": f"TRG{len(result) + 1}",
                "trigger": row["trigger"],
                "classification": classification,
                "signal": _first(row.get("signal"), row.get("metric"), row["trigger"]),
                "threshold": _first(row.get("threshold"), row.get("condition"), "operator-confirmed rollback condition"),
                "decision_owner": _first(row.get("decision_owner"), row.get("owner"), "incident_commander"),
                "decision": _decision_for(classification),
            }
        )
    if not result:
        result.append(
            {
                "id": "TRG1",
                "trigger": "customer-impacting regression",
                "classification": "critical",
                "signal": "error rate and customer support reports",
                "threshold": "confirmed release regression",
                "decision_owner": "incident_commander",
                "decision": _decision_for("critical"),
            }
        )
    result = sorted(result, key=lambda item: (_class_rank(item["classification"]), item["trigger"].casefold()))
    for index, item in enumerate(result, start=1):
        item["id"] = f"TRG{index}"
    return result


def _participant_roles(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("drill_participants") or spec.get("participants"), "name")
    result: list[dict[str, Any]] = []
    for row in rows:
        role = _role(row)
        result.append(
            {
                "id": f"PAR{len(result) + 1}",
                "name": row["name"],
                "role": role,
                "group": _role_group(role),
                "responsibility": _first(row.get("responsibility"), row.get("duty"), _default_responsibility(role)),
                "contact": _first(row.get("contact"), "not provided"),
            }
        )
    if not result:
        result.append(
            {
                "id": "PAR1",
                "name": "release owner",
                "role": "release_lead",
                "group": "command",
                "responsibility": _default_responsibility("release_lead"),
                "contact": "not provided",
            }
        )
    result = sorted(result, key=lambda item: (item["group"], item["role"], item["name"].casefold()))
    for index, item in enumerate(result, start=1):
        item["id"] = f"PAR{index}"
    return result


def _validation_probes(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("validation_probes") or spec.get("probes"), "probe")
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"VAL{len(result) + 1}",
                "probe": row["probe"],
                "target": _first(row.get("target"), row.get("component"), "release surface"),
                "expected_result": _first(row.get("expected_result"), row.get("success"), "returns to pre-release baseline"),
                "owner": _first(row.get("owner"), "quality_owner"),
                "required": bool(row.get("required", True)),
            }
        )
    return sorted(result, key=lambda item: (not item["required"], item["probe"].casefold()))


def _timing_targets(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("timing_targets") or spec.get("timing"), "name")
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"TIM{len(result) + 1}",
                "name": row["name"],
                "target_minutes": number(_first(row.get("target_minutes"), row.get("minutes"))),
                "owner": _first(row.get("owner"), "release_owner"),
                "measurement": _first(row.get("measurement"), "wall-clock drill timing"),
            }
        )
    if not result:
        result = [
            {"id": "TIM1", "name": "detect rollback trigger", "target_minutes": 5.0, "owner": "release_owner", "measurement": "alert to decision"},
            {"id": "TIM2", "name": "complete rollback", "target_minutes": 15.0, "owner": "release_owner", "measurement": "decision to stable validation"},
        ]
    return sorted(result, key=lambda item: ((item["target_minutes"] if item["target_minutes"] is not None else 999999), item["name"].casefold()))


def _communication_checkpoints(spec: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _records(spec.get("communication_checkpoints") or spec.get("checkpoints"), "checkpoint")
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"COM{len(result) + 1}",
                "checkpoint": row["checkpoint"],
                "channel": _first(row.get("channel"), "incident channel"),
                "audience": _first(row.get("audience"), "release stakeholders"),
                "timing": _first(row.get("timing"), "during drill"),
                "owner": _first(row.get("owner"), "communications_owner"),
            }
        )
    return sorted(result, key=lambda item: (item["timing"], item["checkpoint"].casefold()))


def _follow_up_actions(spec: dict[str, Any], triggers: list[dict[str, Any]], probes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = _records(spec.get("follow_up_actions") or spec.get("followups"), "action")
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": f"FUP{len(result) + 1}",
                "action": row["action"],
                "owner": _first(row.get("owner"), "release_owner"),
                "due": _first(row.get("due"), row.get("timing"), "next retrospective"),
            }
        )
    if not result:
        if any(item["classification"] == "critical" for item in triggers):
            result.append({"id": "FUP1", "action": "Document rollback decision gaps and update trigger thresholds.", "owner": "release_owner", "due": "next retrospective"})
        if probes:
            result.append({"id": f"FUP{len(result) + 1}", "action": "Review failed or slow validation probes.", "owner": "quality_owner", "due": "next retrospective"})
    return result


def _records(value: Any, default_key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        record = dict(item) if isinstance(item, dict) else {default_key: item}
        key = compact(record.get(default_key) or record.get("name") or record.get("component") or record.get("trigger") or record.get("probe") or record.get("checkpoint") or record.get("action"))
        if key:
            record[default_key] = key
            if default_key != "name" and not compact(record.get("name")):
                record["name"] = key
            result.append(record)
    return result


def _trigger_classification(row: dict[str, Any]) -> str:
    explicit = compact(row.get("classification") or row.get("severity")).lower()
    if explicit in {"critical", "warning", "informational"}:
        return explicit
    threshold = " ".join(string_list([row.get("trigger"), row.get("threshold"), row.get("condition")])).lower()
    value = number(row.get("value"))
    if value is not None and value >= 1:
        return "critical"
    if any(term in threshold for term in ("sev1", "critical", "outage", "data loss", "5xx", "error budget", "payment failure")):
        return "critical"
    if any(term in threshold for term in ("latency", "degraded", "warning", "sev2")):
        return "warning"
    return "informational"


def _role(row: dict[str, Any]) -> str:
    return compact(row.get("role") or row.get("function") or "observer").lower().replace(" ", "_")


def _role_group(role: str) -> str:
    if role in {"incident_commander", "release_lead", "rollback_owner"}:
        return "command"
    if role in {"engineer", "sre", "quality_owner", "qa"}:
        return "execution"
    if role in {"communications", "customer_success", "support"}:
        return "communications"
    return "observer"


def _default_responsibility(role: str) -> str:
    return {
        "incident_commander": "Own rollback decision and drill control.",
        "release_lead": "Coordinate release context and rollback execution.",
        "rollback_owner": "Execute rollback steps and report status.",
        "sre": "Watch operational telemetry and validate stability.",
        "qa": "Run validation probes and record results.",
        "communications": "Send checkpoint updates to stakeholders.",
    }.get(role, "Observe the drill and capture follow-up notes.")


def _decision_for(classification: str) -> str:
    if classification == "critical":
        return "rollback immediately unless incident commander records an explicit hold."
    if classification == "warning":
        return "pause rollout and prepare rollback while validating customer impact."
    return "monitor during drill and capture retrospective notes."


def _source(spec: dict[str, Any]) -> dict[str, str]:
    source = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    return {"idea_id": compact(source.get("idea_id")) or compact(spec.get("id"))}


def _title(spec: dict[str, Any]) -> str:
    project = spec.get("project") if isinstance(spec.get("project"), dict) else {}
    return _first(project.get("title"), spec.get("title"), "Release Rollback Drill")


def _class_rank(value: str) -> int:
    return {"critical": 0, "warning": 1, "informational": 2}.get(value, 3)


def _extend(lines: list[str], title: str, items: list[Any], renderer: Any) -> None:
    lines.extend([f"## {title}", ""])
    if not items:
        lines.extend(["None.", ""])
        return
    for item in items:
        lines.extend(renderer(item))
        lines.append("")


def _render_scope(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['component']}", "", f"- Release: {item['release']}", f"- Rollback method: {item['rollback_method']}", f"- Owner: {item['owner']}", f"- Scope note: {item['scope_note']}"]


def _render_trigger(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['trigger']}", "", f"- Classification: {item['classification']}", f"- Signal: {item['signal']}", f"- Threshold: {item['threshold']}", f"- Decision owner: {item['decision_owner']}", f"- Decision: {item['decision']}"]


def _render_participant(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Role: {item['role']}", f"- Group: {item['group']}", f"- Responsibility: {item['responsibility']}", f"- Contact: {item['contact']}"]


def _render_probe(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['probe']}", "", f"- Target: {item['target']}", f"- Expected result: {item['expected_result']}", f"- Owner: {item['owner']}", f"- Required: {text(item['required'])}"]


def _render_timing(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['name']}", "", f"- Target minutes: {text(item.get('target_minutes')) or 'unknown'}", f"- Owner: {item['owner']}", f"- Measurement: {item['measurement']}"]


def _render_checkpoint(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}: {item['checkpoint']}", "", f"- Channel: {item['channel']}", f"- Audience: {item['audience']}", f"- Timing: {item['timing']}", f"- Owner: {item['owner']}"]


def _render_follow_up(item: dict[str, Any]) -> list[str]:
    return [f"### {item['id']}", "", f"- Action: {item['action']}", f"- Owner: {item['owner']}", f"- Due: {item['due']}"]


def _first(*values: Any) -> Any:
    for value in values:
        if compact(value):
            return value
    return ""
