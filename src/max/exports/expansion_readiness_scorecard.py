"""Expansion readiness scorecard export for account growth planning."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store

SCHEMA_VERSION = "max.expansion_readiness_scorecard.v1"
KIND = "max.expansion_readiness_scorecard"

_BAND_ORDER = {"ready": 0, "watch": 1, "blocked": 2}


def build_expansion_readiness_scorecard_export(store: Store, domain: str | None = None) -> dict[str, Any]:
    accounts = [_account_row(unit) for unit in store.get_buildable_units(limit=1000, domain=domain)]
    accounts.sort(key=lambda row: (_BAND_ORDER[row["score_band"]], -row["readiness_score"], row["account_name"], row["idea_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"project": "max", "entity_type": "expansion_readiness_scorecard", "domain_filter": domain},
        "summary": _summary(accounts),
        "accounts": accounts,
    }


def render_expansion_readiness_scorecard_markdown(report: dict[str, Any]) -> str:
    lines = ["# Expansion Readiness Scorecard", "", f"Schema: `{report['schema_version']}`", f"Generated: {report['generated_at']}", "", "## Accounts", ""]
    if report.get("accounts"):
        lines.extend(["| Account | Score | Band | Positive Signals | Blockers | Next Action |", "|---------|-------|------|------------------|----------|-------------|"])
        for row in report["accounts"]:
            lines.append(f"| {_md(row['account_name'])} | {row['readiness_score']:.0f} | {row['score_band']} | {_md(', '.join(row['positive_signals']) or 'None')} | {_md(', '.join(row['expansion_blockers']) or 'None')} | {_md(row['recommended_next_action'])} |")
    else:
        lines.append("- No accounts available for expansion scoring.")
    return "\n".join(lines).rstrip() + "\n"


def render_expansion_readiness_scorecard_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str)


def _account_row(unit: Any) -> dict[str, Any]:
    metadata = _metadata(unit)
    positives: list[str] = []
    blockers: list[str] = []
    score = 50.0
    for key, label in (("usage", "Strong usage"), ("adoption", "Healthy adoption"), ("stakeholders", "Engaged stakeholders"), ("integrations", "Integration depth"), ("renewal", "Renewal confidence")):
        value = _text(_first(metadata, key, f"{key}_signal"))
        delta = _signal_score(value)
        score += delta
        if delta > 0:
            positives.append(label)
        elif delta < 0:
            blockers.append(f"Weak {label.lower()}")
    support = _text(_first(metadata, "support_load", "open_escalations", "tickets")).lower()
    if any(word in support for word in ("high", "escalation", "many", "blocked")):
        score -= 25
        blockers.append("High support load")
    elif any(word in support for word in ("low", "none", "healthy")):
        score += 10
        positives.append("Low support load")
    score = round(max(0.0, min(100.0, score)), 1)
    band = "ready" if score >= 75 and not blockers else "watch" if score >= 45 else "blocked"
    return {
        "idea_id": str(getattr(unit, "id", "")),
        "account_name": _text(_first(metadata, "account", "account_name", "customer")) or str(getattr(unit, "title", "Untitled")),
        "readiness_score": score,
        "score_band": band,
        "expansion_blockers": blockers,
        "positive_signals": positives,
        "recommended_next_action": _next_action(band, blockers),
    }


def _summary(accounts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "account_count": len(accounts),
        "average_readiness_score": round(sum(row["readiness_score"] for row in accounts) / len(accounts), 1) if accounts else 0.0,
        "band_counts": {band: sum(1 for row in accounts if row["score_band"] == band) for band in ("ready", "watch", "blocked")},
    }


def _next_action(band: str, blockers: list[str]) -> str:
    if band == "ready":
        return "Prepare expansion discovery and executive outreach."
    if blockers:
        return f"Resolve {blockers[0].lower()} before expansion outreach."
    return "Collect more readiness evidence before committing expansion motion."


def _signal_score(value: str) -> float:
    text = value.lower()
    if not text:
        return 0.0
    if any(word in text for word in ("high", "strong", "healthy", "yes", "ready", "growing")):
        return 10.0
    if any(word in text for word in ("low", "weak", "risk", "blocked", "no", "declining")):
        return -12.0
    return 3.0


def _metadata(unit: Any) -> dict[str, Any]:
    return getattr(unit, "metadata", None) if isinstance(getattr(unit, "metadata", None), dict) else {}


def _first(metadata: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metadata:
            return metadata[key]
    return None


def _text(value: Any) -> str:
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
