"""Trial conversion readiness scorecard export."""

from __future__ import annotations

import json
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.trial_conversion_readiness_scorecard.v1"
KIND = "max.trial_conversion_readiness_scorecard"

ReadinessBand = Literal["ready", "watch", "blocked"]


class TrialConversionReadinessInput(TypedDict, total=False):
    account_id: str
    account: str
    account_name: str
    activation: int | float | str
    activation_score: int | float | str
    usage_depth: int | float | str
    usage_score: int | float | str
    stakeholder_engagement: int | float | str
    stakeholder_score: int | float | str
    blockers: str | list[str]
    unresolved_blockers: str | list[str]
    owner: str
    trial_end_date: str
    next_action: str


def build_trial_conversion_readiness_scorecard(
    records: Iterable[TrialConversionReadinessInput | dict[str, Any]],
    *,
    title: str = "Trial Conversion Readiness Scorecard",
) -> dict[str, Any]:
    accounts = _normalize_accounts(records)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Trial Conversion Readiness Scorecard",
        "summary": _summary(accounts),
        "accounts": accounts,
        "recommendations": _recommendations(accounts),
    }


def render_trial_conversion_readiness_scorecard_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Trial Conversion Readiness Scorecard'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Trial accounts: {summary.get('account_count', 0)}",
        f"- Average readiness score: {summary.get('average_readiness_score', 0.0)}",
        f"- Ready trials: {summary.get('band_counts', {}).get('ready', 0)}",
        f"- Watch trials: {summary.get('band_counts', {}).get('watch', 0)}",
        f"- Blocked trials: {summary.get('band_counts', {}).get('blocked', 0)}",
        "",
        "## Account Scorecard",
        "",
    ]
    accounts = report.get("accounts") or []
    if accounts:
        lines.extend([
            "| Account | Score | Band | Activation | Usage Depth | Stakeholders | Blockers | Owner | Trial End | Next Action |",
            "|---------|-------|------|------------|-------------|--------------|----------|-------|-----------|-------------|",
        ])
        for row in accounts:
            lines.append(
                f"| {_md(row['account_name'])} | {row['readiness_score']} | {row['readiness_band']} | "
                f"{row['activation_score']} | {row['usage_depth_score']} | {row['stakeholder_engagement_score']} | "
                f"{_md(', '.join(row['blockers']) or 'None')} | {_md(row['owner'])} | "
                f"{_md(row['trial_end_date'] or 'Unknown')} | {_md(row['next_action'])} |"
            )
    else:
        lines.append("- No trial accounts supplied for readiness scoring.")
    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in report.get("recommendations", []))
    return "\n".join(lines).rstrip() + "\n"


def render_trial_conversion_readiness_scorecard_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_accounts(records: Iterable[TrialConversionReadinessInput | dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in records:
        account_id = _text(raw.get("account_id") or raw.get("account") or raw.get("account_name") or "Unknown trial")
        blockers = _items(_first(raw, "unresolved_blockers", "blockers"))
        row = {
            "account_id": account_id,
            "account_name": _text(raw.get("account_name") or raw.get("account") or account_id),
            "activation_score": _score(_first(raw, "activation_score", "activation"), default=40),
            "usage_depth_score": _score(_first(raw, "usage_score", "usage_depth"), default=40),
            "stakeholder_engagement_score": _score(_first(raw, "stakeholder_score", "stakeholder_engagement"), default=40),
            "blockers": blockers,
            "owner": _text(raw.get("owner") or "Unassigned"),
            "trial_end_date": _text(raw.get("trial_end_date")),
            "explicit_next_action": _text(raw.get("next_action")),
        }
        existing = merged.get(account_id.lower())
        if existing is None:
            merged[account_id.lower()] = row
            continue
        existing["account_name"] = min(existing["account_name"], row["account_name"])
        existing["activation_score"] = max(existing["activation_score"], row["activation_score"])
        existing["usage_depth_score"] = max(existing["usage_depth_score"], row["usage_depth_score"])
        existing["stakeholder_engagement_score"] = max(existing["stakeholder_engagement_score"], row["stakeholder_engagement_score"])
        existing["blockers"] = sorted(set(existing["blockers"]) | set(row["blockers"]))
        existing["owner"] = _prefer_assigned(existing["owner"], row["owner"])
        existing["trial_end_date"] = min(filter(None, [existing["trial_end_date"], row["trial_end_date"]]), default="")
        existing["explicit_next_action"] = existing["explicit_next_action"] or row["explicit_next_action"]
    accounts = [_finalize(row) for row in merged.values()]
    accounts.sort(key=lambda row: (row["readiness_score"], -len(row["blockers"]), row["trial_end_date"] or "9999-12-31", row["account_name"].lower()))
    return accounts


def _finalize(row: dict[str, Any]) -> dict[str, Any]:
    blocker_penalty = min(35, len(row["blockers"]) * 12)
    score = round(max(0, min(100, row["activation_score"] * 0.35 + row["usage_depth_score"] * 0.30 + row["stakeholder_engagement_score"] * 0.25 + 10 - blocker_penalty)))
    band: ReadinessBand = "ready" if score >= 75 and not row["blockers"] else "watch" if score >= 50 else "blocked"
    return {
        "account_id": row["account_id"],
        "account_name": row["account_name"],
        "readiness_score": score,
        "readiness_band": band,
        "activation_score": row["activation_score"],
        "usage_depth_score": row["usage_depth_score"],
        "stakeholder_engagement_score": row["stakeholder_engagement_score"],
        "blockers": row["blockers"],
        "owner": row["owner"],
        "trial_end_date": row["trial_end_date"],
        "next_action": row["explicit_next_action"] or _next_action(band, row),
    }


def _summary(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(accounts),
        "average_readiness_score": round(sum(row["readiness_score"] for row in accounts) / len(accounts), 1) if accounts else 0.0,
        "band_counts": {band: sum(1 for row in accounts if row["readiness_band"] == band) for band in ("ready", "watch", "blocked")},
        "unresolved_blocker_count": sum(len(row["blockers"]) for row in accounts),
    }


def _recommendations(accounts: list[dict[str, Any]]) -> list[str]:
    if not accounts:
        return ["Capture trial activation, usage depth, stakeholder engagement, unresolved blockers, owner, and trial end date."]
    recommendations = []
    if any(row["readiness_band"] == "blocked" for row in accounts):
        recommendations.append("Prioritize blocked trials with named owner follow-up before the trial end date.")
    if any(row["activation_score"] < 50 for row in accounts):
        recommendations.append("Run guided activation outreach for accounts below 50 activation readiness.")
    if any(row["stakeholder_engagement_score"] < 50 for row in accounts):
        recommendations.append("Schedule business sponsor touchpoints for trials with weak stakeholder engagement.")
    return recommendations or ["Prepare ready trials for conversion plan review."]


def _next_action(band: ReadinessBand, row: dict[str, Any]) -> str:
    if row["blockers"]:
        return f"Resolve {row['blockers'][0]} before conversion ask."
    if row["activation_score"] < 50:
        return "Run activation checklist with the trial team."
    if row["usage_depth_score"] < 50:
        return "Expand usage into the committed trial workflow."
    if row["stakeholder_engagement_score"] < 50:
        return "Secure executive or business owner engagement."
    if band == "ready":
        return "Confirm pricing, procurement path, and close plan."
    return "Refresh readiness evidence and assign a dated conversion step."


def _score(value: Any, *, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = float(str(value).rstrip("%"))
        return round(max(0, min(100, number)))
    except ValueError:
        text = _text(value).lower()
        if any(word in text for word in ("high", "strong", "deep", "complete", "ready", "engaged")):
            return 85
        if any(word in text for word in ("medium", "moderate", "partial", "some", "active")):
            return 60
        if any(word in text for word in ("low", "weak", "shallow", "blocked", "none", "poor")):
            return 25
        return default


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return sorted({part.strip() for part in value.replace(";", ",").split(",") if part.strip() and part.strip().lower() != "none"})
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item) and _text(item).lower() != "none"})
    return [_text(value)] if _text(value) else []


def _prefer_assigned(left: str, right: str) -> str:
    if left == "Unassigned":
        return right
    if right == "Unassigned":
        return left
    return min(left, right)


def _first(record: TrialConversionReadinessInput | dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return None


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
