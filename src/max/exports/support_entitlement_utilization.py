"""Support entitlement utilization report export."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.support_entitlement_utilization.v1"
KIND = "max.support_entitlement_utilization"

UtilizationStatus = Literal["overage", "nearing_limit", "underused_premium", "normal"]
GroupBy = Literal["plan", "owner", "status"]


class SupportEntitlementUtilizationInput(TypedDict, total=False):
    account: str
    plan: str
    used_units: int | float
    allowance: int | float
    owner: str
    recommended_action: str
    action: str


def build_support_entitlement_utilization_report(
    records: Iterable[SupportEntitlementUtilizationInput | dict[str, Any]],
    *,
    title: str = "Support Entitlement Utilization Report",
    group_by: GroupBy = "plan",
    nearing_limit_threshold: float = 0.8,
    underused_threshold: float = 0.25,
) -> dict[str, Any]:
    entitlements = _normalize_entitlements(records, nearing_limit_threshold=nearing_limit_threshold, underused_threshold=underused_threshold)
    groups = _groups(entitlements, group_by)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Support Entitlement Utilization Report",
        "group_by": group_by,
        "summary": _summary(entitlements, groups),
        "groups": groups,
        "entitlements": entitlements,
    }


def render_support_entitlement_utilization_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Support Entitlement Utilization Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Accounts reviewed: {summary.get('account_count', 0)}",
        f"- Overages: {summary.get('overage_count', 0)}",
        f"- Nearing limits: {summary.get('nearing_limit_count', 0)}",
        f"- Underused premium entitlements: {summary.get('underused_premium_count', 0)}",
        f"- Average utilization: {summary.get('average_utilization_percent', 0)}%",
        "",
        "## Utilization Register",
        "",
    ]
    groups = report.get("groups") or []
    if groups:
        for group in groups:
            lines.extend([f"### {group['name']}", ""])
            for row in group["entitlements"]:
                lines.extend(
                    [
                        f"#### {row['account']}",
                        f"- Plan: {row['plan']}",
                        f"- Status: {row['status']}",
                        f"- Used units: {row['used_units']}",
                        f"- Allowance: {row['allowance']}",
                        f"- Utilization: {row['utilization_percent']}%",
                        f"- Owner: {row['owner']}",
                        f"- Recommended action: {row['recommended_action']}",
                        "",
                    ]
                )
    else:
        lines.append("- No support entitlement utilization records were supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_support_entitlement_utilization_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_entitlements(
    records: Iterable[SupportEntitlementUtilizationInput | dict[str, Any]],
    *,
    nearing_limit_threshold: float,
    underused_threshold: float,
) -> list[dict[str, Any]]:
    rows = []
    for raw in records:
        used_units = max(_float(raw.get("used_units")), 0.0)
        allowance = max(_float(raw.get("allowance")), 0.0)
        utilization = (used_units / allowance) if allowance else 0.0
        plan = _text(raw.get("plan") or "Unspecified plan")
        status = _status(plan=plan, utilization=utilization, allowance=allowance, nearing_limit_threshold=nearing_limit_threshold, underused_threshold=underused_threshold)
        rows.append(
            {
                "account": _text(raw.get("account") or "Unspecified account"),
                "plan": plan,
                "used_units": _number(used_units),
                "allowance": _number(allowance),
                "utilization_percent": round(utilization * 100, 1) if allowance else 0.0,
                "status": status,
                "owner": _text(raw.get("owner") or "Unassigned"),
                "recommended_action": _text(raw.get("recommended_action") or raw.get("action") or _recommended_action(status)),
            }
        )
    rows.sort(key=_entitlement_sort_key)
    return rows


def _groups(entitlements: list[dict[str, Any]], group_by: GroupBy) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in entitlements:
        grouped[row[group_by]].append(row)
    groups = [{"name": name, "account_count": len(items), "entitlements": items} for name, items in grouped.items()]
    groups.sort(key=lambda group: (_group_worst_key(group["entitlements"]), group["name"].lower()))
    return groups


def _summary(entitlements: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(entitlements),
        "group_count": len(groups),
        "overage_count": sum(1 for row in entitlements if row["status"] == "overage"),
        "nearing_limit_count": sum(1 for row in entitlements if row["status"] == "nearing_limit"),
        "underused_premium_count": sum(1 for row in entitlements if row["status"] == "underused_premium"),
        "average_utilization_percent": round(sum(row["utilization_percent"] for row in entitlements) / len(entitlements), 1) if entitlements else 0.0,
    }


_STATUS_ORDER = {"overage": 0, "nearing_limit": 1, "underused_premium": 2, "normal": 3}


def _entitlement_sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
    return (_STATUS_ORDER[row["status"]], -row["utilization_percent"], row["account"].lower())


def _group_worst_key(entitlements: list[dict[str, Any]]) -> tuple[int, float]:
    first = min(entitlements, key=_entitlement_sort_key)
    return (_STATUS_ORDER[first["status"]], -first["utilization_percent"])


def _status(
    *,
    plan: str,
    utilization: float,
    allowance: float,
    nearing_limit_threshold: float,
    underused_threshold: float,
) -> UtilizationStatus:
    if allowance and utilization > 1:
        return "overage"
    if allowance and utilization >= nearing_limit_threshold:
        return "nearing_limit"
    if _is_premium(plan) and utilization <= underused_threshold:
        return "underused_premium"
    return "normal"


def _recommended_action(status: UtilizationStatus) -> str:
    if status == "overage":
        return "Review overage charges and right-size the entitlement before renewal."
    if status == "nearing_limit":
        return "Warn account team and confirm whether additional support units are needed."
    if status == "underused_premium":
        return "Review premium plan fit and activate unused support motions."
    return "Continue monitoring support entitlement consumption."


def _is_premium(plan: str) -> bool:
    return plan.lower() in {"premium", "enterprise", "strategic", "platinum"}


def _float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _number(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
