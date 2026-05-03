"""Deterministic support playbooks for persisted design briefs."""

from __future__ import annotations

import csv
import json
import re
from io import StringIO
from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.support_playbook.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "design_brief_id",
    "design_brief_title",
    "design_status",
    "readiness_score",
    "section",
    "item_id",
    "item_title",
    "name",
    "owner",
    "team",
    "severity",
    "priority",
    "trigger",
    "response",
    "detail",
    "source_idea_ids",
)


def build_design_brief_support_playbook(store: Store, brief_id: str) -> dict[str, Any] | None:
    """Build an operational support playbook from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    lead_idea = next((idea for idea in source_ideas if idea.get("role") == "lead"), None)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _support_context(design_brief, source_ideas, lead_idea)
    risks = _dedupe_strings(
        [*_string_list(design_brief.get("risks")), *_source_risks(source_ideas)]
    )
    scenarios = _support_scenarios(design_brief, context, risks, source_idea_ids)
    escalation = _escalation_criteria(design_brief, context, risks, source_idea_ids)
    monitoring = _monitoring_signals(design_brief, context, risks, scenarios, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "max.design_brief.support_playbook",
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
            "readiness_score": design_brief.get("readiness_score", 0.0),
            "design_status": design_brief.get("design_status", ""),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "support_goal": f"Prepare support handoff for {design_brief['title']}.",
            "target_user": context["target_user"],
            "buyer": context["buyer"],
            "workflow_context": context["workflow_context"],
            "primary_scope": context["primary_scope"],
            "primary_risk": risks[0] if risks else "No explicit risk captured.",
            "fallbacks_used": context["fallbacks_used"],
            "scenario_count": len(scenarios),
            "elevated_escalation_count": len(
                [item for item in escalation if item["severity"] == "elevated"]
            ),
            "monitoring_signal_count": len(monitoring),
        },
        "onboarding_checks": _onboarding_checks(design_brief, context, risks, source_idea_ids),
        "support_scenarios": scenarios,
        "troubleshooting_flows": _troubleshooting_flows(context, scenarios, source_idea_ids),
        "escalation_criteria": escalation,
        "response_snippets": _response_snippets(design_brief, context, scenarios, source_idea_ids),
        "monitoring_signals": monitoring,
        "source_ideas": source_ideas,
    }


def render_design_brief_support_playbook(playbook: dict[str, Any], fmt: str = "markdown") -> str:
    """Render the support playbook as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(playbook, indent=2) + "\n"
    if fmt == "csv":
        return _render_csv(playbook)
    if fmt != "markdown":
        raise ValueError(f"Unsupported support playbook format: {fmt}")

    brief = playbook["design_brief"]
    summary = playbook["summary"]
    lines = [
        f"# Support Playbook: {brief['title']}",
        "",
        f"Schema: `{playbook['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Status: {brief.get('design_status') or 'unknown'}",
        f"Readiness: {float(brief.get('readiness_score') or 0.0):.1f}/100",
        f"Source ideas: {', '.join(brief.get('source_idea_ids') or []) or 'design brief'}",
        "",
        "## Support Context",
        "",
        f"- Goal: {summary['support_goal']}",
        f"- Target user: {summary['target_user']}",
        f"- Buyer: {summary['buyer']}",
        f"- Workflow: {summary['workflow_context']}",
        f"- Primary scope: {summary['primary_scope']}",
        f"- Primary risk: {summary['primary_risk']}",
        f"- Fallbacks used: {', '.join(summary['fallbacks_used']) or 'none'}",
        "",
        "## Onboarding Checks",
        "",
    ]
    for check in playbook["onboarding_checks"]:
        lines.extend(
            [
                f"### {check['id']}: {check['check']}",
                "",
                f"- Owner: {check['owner']}",
                f"- Pass signal: {check['pass_signal']}",
                f"- Failure action: {check['failure_action']}",
                "",
            ]
        )

    lines.extend(["## Support Scenarios", ""])
    for scenario in playbook["support_scenarios"]:
        lines.extend(
            [
                f"### {scenario['id']}: {scenario['name']}",
                "",
                f"- Trigger: {scenario['trigger']}",
                f"- Likely cause: {scenario['likely_cause']}",
                f"- First response: {scenario['first_response']}",
                f"- Resolution target: {scenario['resolution_target']}",
                "",
            ]
        )

    lines.extend(["## Troubleshooting Flows", ""])
    for flow in playbook["troubleshooting_flows"]:
        lines.extend(
            [
                f"### {flow['scenario_id']}",
                "",
                *[f"{index}. {step}" for index, step in enumerate(flow["steps"], start=1)],
                f"- Stop when: {flow['stop_condition']}",
                "",
            ]
        )

    lines.extend(["## Escalation Criteria", ""])
    for item in playbook["escalation_criteria"]:
        lines.extend(
            [
                f"### {item['severity'].title()}: {item['name']}",
                "",
                f"- Escalate when: {item['escalate_when']}",
                f"- Owner: {item['owner']}",
                f"- Path: {item['path']}",
                f"- SLA: {item['sla']}",
                "",
            ]
        )

    lines.extend(["## Response Snippets", ""])
    for snippet in playbook["response_snippets"]:
        lines.extend(
            [
                f"### {snippet['name']}",
                "",
                f"- Channel: {snippet['channel']}",
                "",
                snippet["body"],
                "",
            ]
        )

    lines.extend(["## Monitoring Signals", ""])
    for signal in playbook["monitoring_signals"]:
        lines.extend(
            [
                f"- **{signal['signal']}**: {signal['threshold']}",
                f"  Owner: {signal['owner']}; action: {signal['action']}",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _render_csv(playbook: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(playbook):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(playbook: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for item in playbook.get("onboarding_checks") or []:
        rows.append(
            _csv_row(
                playbook,
                section="readiness_gaps",
                item_id=item.get("id"),
                item_title=item.get("check"),
                name=item.get("check"),
                owner=item.get("owner"),
                priority="readiness",
                trigger=item.get("pass_signal"),
                response=item.get("failure_action"),
                detail={"pass_signal": item.get("pass_signal")},
                source_idea_ids=item.get("source_idea_ids") or [],
            )
        )

    for item in playbook.get("support_scenarios") or []:
        rows.append(
            _csv_row(
                playbook,
                section="support_scenarios",
                item_id=item.get("id"),
                item_title=item.get("name"),
                name=item.get("name"),
                trigger=item.get("trigger"),
                response=item.get("first_response"),
                detail={
                    "likely_cause": item.get("likely_cause"),
                    "resolution_target": item.get("resolution_target"),
                },
                source_idea_ids=item.get("source_idea_ids") or [],
            )
        )

    for item in playbook.get("troubleshooting_flows") or []:
        scenario_id = item.get("scenario_id")
        for index, step in enumerate(item.get("steps") or [], start=1):
            rows.append(
                _csv_row(
                    playbook,
                    section="troubleshooting_steps",
                    item_id=f"{scenario_id}-TS{index}" if scenario_id else f"TS{index}",
                    item_title=f"Troubleshooting step {index}",
                    name=f"Troubleshooting flow for {scenario_id or 'scenario'}",
                    priority=index,
                    trigger=item.get("stop_condition"),
                    response=step,
                    detail={
                        "scenario_id": scenario_id,
                        "step_number": index,
                        "stop_condition": item.get("stop_condition"),
                    },
                    source_idea_ids=item.get("source_idea_ids") or [],
                )
            )

    for item in playbook.get("escalation_criteria") or []:
        rows.append(
            _csv_row(
                playbook,
                section="escalation_paths",
                item_id=item.get("id"),
                item_title=item.get("name"),
                name=item.get("name"),
                owner=item.get("owner"),
                severity=item.get("severity"),
                trigger=item.get("escalate_when"),
                response=item.get("path"),
                detail={
                    "sla": item.get("sla"),
                },
                source_idea_ids=item.get("source_idea_ids") or [],
            )
        )

    for item in playbook.get("response_snippets") or []:
        rows.append(
            _csv_row(
                playbook,
                section="macros_templates",
                item_id=item.get("id"),
                item_title=item.get("name"),
                name=item.get("name"),
                trigger=item.get("channel"),
                response=item.get("body"),
                detail={"channel": item.get("channel")},
                source_idea_ids=item.get("source_idea_ids") or [],
            )
        )

    for item in playbook.get("monitoring_signals") or []:
        rows.append(
            _csv_row(
                playbook,
                section="metrics",
                item_id=item.get("id"),
                item_title=item.get("signal"),
                name=item.get("signal"),
                owner=item.get("owner"),
                trigger=item.get("threshold"),
                response=item.get("action"),
                detail={"threshold": item.get("threshold")},
                source_idea_ids=item.get("source_idea_ids") or [],
            )
        )

    for index, item in enumerate(playbook.get("next_actions") or [], start=1):
        if isinstance(item, dict):
            item_id = item.get("id") or f"NA{index}"
            title = (
                item.get("title")
                or item.get("name")
                or item.get("action")
                or f"Next action {index}"
            )
            response = item.get("action") or item.get("response") or item.get("detail") or title
            detail = {
                key: value
                for key, value in sorted(item.items())
                if key
                not in {
                    "id",
                    "title",
                    "name",
                    "action",
                    "response",
                    "detail",
                    "owner",
                    "team",
                    "severity",
                    "priority",
                    "trigger",
                    "source_idea_ids",
                }
            }
            source_ids = item.get("source_idea_ids")
        else:
            item_id = f"NA{index}"
            title = f"Next action {index}"
            response = item
            detail = {}
            source_ids = None
        rows.append(
            _csv_row(
                playbook,
                section="next_actions",
                item_id=item_id,
                item_title=title,
                name=title,
                owner=item.get("owner") if isinstance(item, dict) else None,
                team=item.get("team") if isinstance(item, dict) else None,
                severity=item.get("severity") if isinstance(item, dict) else None,
                priority=item.get("priority") if isinstance(item, dict) else None,
                trigger=item.get("trigger") if isinstance(item, dict) else None,
                response=response,
                detail=detail,
                source_idea_ids=source_ids
                or (playbook.get("design_brief") or {}).get("source_idea_ids"),
            )
        )

    return rows


def _csv_row(playbook: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = playbook.get("design_brief") or {}
    row = {
        "schema_version": playbook.get("schema_version"),
        "kind": playbook.get("kind"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "design_status": brief.get("design_status"),
        "readiness_score": brief.get("readiness_score"),
        **values,
    }
    return {column: _csv_text(row.get(column)) for column in CSV_COLUMNS}


def _csv_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, set):
        value = sorted(value, key=str)
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in sorted(value, key=str)]
    return value


def _support_context(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    lead_idea: dict[str, Any] | None,
) -> dict[str, Any]:
    fallbacks: list[str] = []
    title = str(design_brief["title"])
    target_user = _first_with_label(
        fallbacks,
        "specific_user",
        (design_brief.get("specific_user"), "design_brief.specific_user"),
        (lead_idea and lead_idea.get("specific_user"), "lead_idea.specific_user"),
        (_field_values(source_ideas, "specific_user"), "source_ideas.specific_user"),
        (f"{title} user", "explicit_fallback"),
    )
    buyer = _first_with_label(
        fallbacks,
        "buyer",
        (design_brief.get("buyer"), "design_brief.buyer"),
        (lead_idea and lead_idea.get("buyer"), "lead_idea.buyer"),
        (_field_values(source_ideas, "buyer"), "source_ideas.buyer"),
        ("support sponsor", "explicit_fallback"),
    )
    workflow = _first_with_label(
        fallbacks,
        "workflow_context",
        (design_brief.get("workflow_context"), "design_brief.workflow_context"),
        (lead_idea and lead_idea.get("workflow_context"), "lead_idea.workflow_context"),
        (_field_values(source_ideas, "workflow_context"), "source_ideas.workflow_context"),
        (f"{title} support workflow", "explicit_fallback"),
    )
    scope_items = _string_list(design_brief.get("mvp_scope"))
    primary_scope = scope_items[0] if scope_items else f"first usable {title} workflow"
    if not scope_items:
        fallbacks.append("mvp_scope")
    validation_plan = _first_text(
        design_brief.get("validation_plan"),
        lead_idea and lead_idea.get("validation_plan"),
        f"Validate support readiness for {workflow}.",
    )
    current_workaround = _first_text(
        lead_idea and lead_idea.get("current_workaround"),
        "the current manual process",
    )
    value = _first_text(
        design_brief.get("merged_product_concept"),
        lead_idea and lead_idea.get("value_proposition"),
        f"Support {target_user} through {workflow}.",
    )
    return {
        "target_user": target_user,
        "buyer": buyer,
        "workflow_context": workflow,
        "primary_scope": primary_scope,
        "validation_plan": validation_plan,
        "current_workaround": current_workaround,
        "value_proposition": value,
        "fallbacks_used": fallbacks,
    }


def _onboarding_checks(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    validation = context["validation_plan"]
    risk = risks[0] if risks else "unknown operational risk"
    return [
        {
            "id": "OC1",
            "check": f"Confirm {context['target_user']} can enter {context['workflow_context']}.",
            "owner": "Support owner",
            "pass_signal": "Customer can name the trigger, input, and expected output before first use.",
            "failure_action": "Schedule guided setup and record the missing workflow precondition.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "OC2",
            "check": f"Verify MVP scope is understood: {context['primary_scope']}.",
            "owner": "Product lead",
            "pass_signal": "Customer and sponsor agree which requests are in scope for the first release.",
            "failure_action": "Send scope clarification before enabling the customer.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "OC3",
            "check": "Capture validation baseline and success criteria.",
            "owner": "Research lead",
            "pass_signal": f"Baseline notes map to the validation plan: {validation}",
            "failure_action": "Pause rollout until a measurable before-and-after signal is defined.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "OC4",
            "check": f"Assign owner for support risk: {risk}",
            "owner": "Risk owner",
            "pass_signal": "Risk owner, mitigation, and escalation route are visible before customer exposure.",
            "failure_action": "Block onboarding for affected customers until ownership is explicit.",
            "source_idea_ids": source_ids,
        },
    ]


def _support_scenarios(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    title = design_brief["title"]
    scope = context["primary_scope"]
    workflow = context["workflow_context"]
    scenarios = [
        {
            "id": "SS1",
            "name": f"First-run confusion in {workflow}",
            "trigger": f"{context['target_user']} cannot complete the first {scope} attempt.",
            "likely_cause": "Setup expectations, workflow prerequisites, or success criteria were not clear.",
            "first_response": "Acknowledge the blocker, confirm the intended workflow step, and offer guided recovery.",
            "resolution_target": "Customer reaches first value or receives a documented workaround within one business day.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "SS2",
            "name": "Scope mismatch or missing capability",
            "trigger": f"Customer asks {title} to handle work outside {scope}.",
            "likely_cause": "The MVP boundary is not visible enough during onboarding or support handoff.",
            "first_response": "Clarify current scope, capture the request, and explain whether it affects validation.",
            "resolution_target": "Request is tagged as in-scope defect, future enhancement, or validation blocker.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "SS3",
            "name": "Validation evidence is incomplete",
            "trigger": "Support interaction resolves the ticket but does not record the learning signal.",
            "likely_cause": f"The support path is disconnected from the validation plan: {context['validation_plan']}",
            "first_response": "Attach the support case to the expected validation signal before closing it.",
            "resolution_target": "Every resolved pilot issue includes outcome, severity, and next evidence action.",
            "source_idea_ids": source_ids,
        },
    ]
    risk = risks[0] if risks else ""
    if risk:
        scenarios.append(
            {
                "id": "SS4",
                "name": "Risk-sensitive support blocker",
                "trigger": f"Customer reports concern related to: {risk}",
                "likely_cause": "A known design brief risk surfaced during support or onboarding.",
                "first_response": "Treat as a risk event, preserve details, and route to the named risk owner.",
                "resolution_target": "Risk owner confirms mitigation, workaround, or stop decision before expansion.",
                "source_idea_ids": source_ids,
            }
        )
    return scenarios


def _troubleshooting_flows(
    context: dict[str, Any],
    scenarios: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    for scenario in scenarios:
        steps = [
            f"Confirm the customer role, workflow step, and expected outcome for {context['workflow_context']}.",
            "Classify the issue as setup, scope, defect, evidence gap, or risk event.",
            f"Compare the request against MVP scope: {context['primary_scope']}.",
            "Record severity, customer impact, current workaround, and validation signal.",
            "Close with a documented resolution, owner, or escalation path.",
        ]
        if scenario["id"] == "SS4":
            steps.insert(2, "Preserve risk evidence and avoid expanding access until the risk owner reviews it.")
        flows.append(
            {
                "scenario_id": scenario["id"],
                "steps": steps,
                "stop_condition": "The customer has a next step and the playbook has captured the learning signal.",
                "source_idea_ids": source_ids,
            }
        )
    return flows


def _escalation_criteria(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    criteria = [
        {
            "id": "EC1",
            "name": "Workflow blocked",
            "severity": "standard",
            "escalate_when": f"{context['target_user']} cannot complete {context['workflow_context']} after guided recovery.",
            "owner": "Support owner",
            "path": "Support owner -> Product lead",
            "sla": "Review within one business day.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "EC2",
            "name": "Validation signal at risk",
            "severity": "standard",
            "escalate_when": f"Support cases prevent the team from executing the validation plan: {context['validation_plan']}",
            "owner": "Research lead",
            "path": "Research lead -> Product lead",
            "sla": "Review before the next pilot touchpoint.",
            "source_idea_ids": source_ids,
        },
    ]
    high_risk = _is_high_risk(design_brief, risks)
    if high_risk:
        risk = risks[0] if risks else "Readiness score is below support threshold."
        criteria.append(
            {
                "id": "EC3",
                "name": "Elevated risk path",
                "severity": "elevated",
                "escalate_when": f"Customer impact touches the high-risk condition: {risk}",
                "owner": "Risk owner",
                "path": "Support owner -> Risk owner -> Engineering lead -> Product sponsor",
                "sla": "Same business day review; pause expansion until disposition is recorded.",
                "source_idea_ids": source_ids,
            }
        )
    return criteria


def _response_snippets(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    scenarios: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    title = design_brief["title"]
    scenario = scenarios[0]
    return [
        {
            "id": "RS1",
            "name": "First response acknowledgement",
            "channel": "email_or_chat",
            "body": (
                f"Thanks for flagging this in {title}. I am going to trace the {context['workflow_context']} "
                f"step with you and confirm whether it is setup, scope, or product behavior. "
                "I will send the next action and owner after we classify it."
            ),
            "source_idea_ids": source_ids,
        },
        {
            "id": "RS2",
            "name": "Scope clarification",
            "channel": "email_or_chat",
            "body": (
                f"For this release, the supported scope is {context['primary_scope']}. "
                f"I captured your request against {context['workflow_context']} and will confirm whether it is "
                "a supported path, a workaround, or a candidate for the next milestone."
            ),
            "source_idea_ids": source_ids,
        },
        {
            "id": "RS3",
            "name": "Resolution and learning capture",
            "channel": "email",
            "body": (
                f"We resolved the issue as: {scenario['resolution_target']} "
                f"I also recorded how this affects the validation plan for {title}, so the product team can "
                "decide whether to continue, revise, or escalate."
            ),
            "source_idea_ids": source_ids,
        },
    ]


def _monitoring_signals(
    design_brief: dict[str, Any],
    context: dict[str, Any],
    risks: list[str],
    scenarios: list[dict[str, Any]],
    source_ids: list[str],
) -> list[dict[str, Any]]:
    signals = [
        {
            "id": "MS1",
            "signal": "First-run support rate",
            "threshold": f"More than 20% of {context['target_user']} contacts need help completing {context['workflow_context']}.",
            "owner": "Support owner",
            "action": "Review onboarding checks and update the setup path before adding customers.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "MS2",
            "signal": "Scope-mismatch tickets",
            "threshold": f"Three or more tickets ask for behavior outside {context['primary_scope']}.",
            "owner": "Product lead",
            "action": "Revisit MVP scope, roadmap language, and response snippets.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "MS3",
            "signal": "Evidence capture coverage",
            "threshold": "Any closed pilot support case lacks severity, outcome, or validation signal.",
            "owner": "Research lead",
            "action": "Reopen the case for learning capture before weekly pilot review.",
            "source_idea_ids": source_ids,
        },
        {
            "id": "MS4",
            "signal": "Scenario mix",
            "threshold": f"One scenario accounts for more than half of {len(scenarios)} tracked scenario types.",
            "owner": "Support owner",
            "action": "Add a focused troubleshooting flow or product fix for the dominant scenario.",
            "source_idea_ids": source_ids,
        },
    ]
    if _is_high_risk(design_brief, risks):
        signals.append(
            {
                "id": "MS5",
                "signal": "Elevated escalation volume",
                "threshold": "Any elevated escalation remains unresolved at the end of the business day.",
                "owner": "Risk owner",
                "action": "Pause expansion and publish risk disposition before the next customer exposure.",
                "source_idea_ids": source_ids,
            }
        )
    return signals


def _is_high_risk(design_brief: dict[str, Any], risks: list[str]) -> bool:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    risk_text = " ".join(risks).lower()
    high_risk_terms = ("security", "privacy", "compliance", "legal", "data", "unsafe", "blocker")
    return readiness < 60 or any(term in risk_text for term in high_risk_terms)


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    ideas: list[dict[str, Any]] = []
    seen: set[str] = set()
    sources = list(design_brief.get("sources", []))
    if not sources:
        lead_id = design_brief.get("lead_idea_id")
        if lead_id:
            sources.append({"idea_id": lead_id, "role": "lead", "rank": 0})
        for rank, idea_id in enumerate(design_brief.get("source_idea_ids", []), start=1):
            if idea_id != lead_id:
                sources.append({"idea_id": idea_id, "role": "supporting", "rank": rank})

    for source in sources:
        idea_id = str(source["idea_id"])
        if idea_id in seen:
            continue
        seen.add(idea_id)
        unit = store.get_buildable_unit(idea_id)
        if not unit:
            ideas.append(
                {
                    "id": idea_id,
                    "role": source.get("role", "source"),
                    "rank": source.get("rank", 0),
                    "missing": True,
                }
            )
            continue
        data = unit.model_dump(mode="json")
        data["role"] = source.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        data["rank"] = source.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _first_with_label(fallbacks: list[str], field: str, *candidates: tuple[Any, str]) -> str:
    for value, label in candidates:
        if isinstance(value, list):
            text = _first_text(*value)
        else:
            text = _first_text(value)
        if text:
            if label == "explicit_fallback":
                fallbacks.append(field)
            return text
    return ""


def _field_values(source_ideas: list[dict[str, Any]], field: str) -> list[str]:
    return [str(idea.get(field) or "") for idea in source_ideas if not idea.get("missing")]


def _source_risks(source_ideas: list[dict[str, Any]]) -> list[str]:
    risks: list[str] = []
    for idea in source_ideas:
        if not idea.get("missing"):
            risks.extend(_string_list(idea.get("domain_risks")))
    return risks


def _first_text(*values: Any) -> str:
    for value in values:
        text = _compact(value)
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_compact(value)] if _compact(value) else []
    if isinstance(value, list):
        return [_compact(item) for item in value if _compact(item)]
    return [_compact(value)] if _compact(value) else []


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = _compact(value)
        key = re.sub(r"\s+", " ", text.lower())
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _compact(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())
