"""Customer success risk trend export report."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any, Iterable, Literal, TypedDict

SCHEMA_VERSION = "max.customer_success_risk_trend.v1"
KIND = "max.customer_success_risk_trend"

RiskMovement = Literal["worsened", "improved", "unchanged", "new"]

_STATUS_SCORE = {
    "critical": 90.0,
    "high": 75.0,
    "at risk": 75.0,
    "medium": 50.0,
    "watch": 50.0,
    "low": 20.0,
    "healthy": 10.0,
}
_STATUS_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "healthy": 4, "unknown": 5}


class CustomerSuccessRiskSnapshotInput(TypedDict, total=False):
    account: str
    account_id: str
    name: str
    observed_at: str
    date: str
    risk_score: float
    score: float
    status: str
    risk_level: str
    driver: str
    reason: str
    drivers: list[str]
    evidence: list[str]


def build_customer_success_risk_trend_report(
    snapshots: Iterable[CustomerSuccessRiskSnapshotInput | dict[str, Any]],
    *,
    title: str = "Customer Success Risk Trend Report",
) -> dict[str, Any]:
    rows = _normalize_snapshots(snapshots)
    by_account: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_account[row["account"]].append(row)

    latest_accounts = [_latest_account_row(account, account_rows) for account, account_rows in by_account.items()]
    latest_accounts.sort(key=lambda row: (_STATUS_ORDER.get(row["status"], 99), -row["risk_score"], row["account"].lower()))

    top_worsening = [row for row in latest_accounts if row["risk_delta"] > 0]
    top_worsening.sort(key=lambda row: (-row["risk_delta"], -row["risk_score"], row["account"].lower()))

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "title": _text(title) or "Customer Success Risk Trend Report",
        "summary": _summary(rows, latest_accounts),
        "latest_accounts": latest_accounts,
        "movement_counts": _movement_counts(latest_accounts),
        "top_worsening_accounts": top_worsening[:5],
        "top_risk_drivers": _top_risk_drivers(rows),
        "snapshots": rows,
    }


def render_customer_success_risk_trend_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"# {report.get('title') or 'Customer Success Risk Trend Report'}",
        "",
        f"Schema: `{report.get('schema_version', SCHEMA_VERSION)}`",
        "",
        "## Summary",
        "",
        f"- Accounts: {summary.get('account_count', 0)}",
        f"- Snapshots: {summary.get('snapshot_count', 0)}",
        f"- Average latest risk score: {summary.get('average_latest_risk_score', 0.0)}",
        f"- Worsening accounts: {summary.get('worsening_account_count', 0)}",
        f"- High risk accounts: {summary.get('high_risk_account_count', 0)}",
        "",
        "## Latest Account Risk",
        "",
    ]
    if report.get("latest_accounts"):
        lines.extend(["| Account | Observed | Status | Score | Movement | Drivers |", "|---------|----------|--------|-------|----------|---------|"])
        for row in report["latest_accounts"]:
            lines.append(
                f"| {_md(row['account'])} | {_md(row['observed_at'] or 'Unspecified')} | {row['status']} | "
                f"{row['risk_score']} | {row['movement']} ({row['risk_delta']:+.1f}) | {_md(', '.join(row['drivers']) or 'None')} |"
            )
    else:
        lines.append("- No customer success risk snapshots were supplied.")

    lines.extend(["", "## Worsening Accounts", ""])
    if report.get("top_worsening_accounts"):
        for row in report["top_worsening_accounts"]:
            lines.append(f"- {row['account']}: +{row['risk_delta']:.1f} to {row['risk_score']} ({', '.join(row['drivers']) or 'no driver supplied'})")
    else:
        lines.append("- No accounts worsened in the supplied snapshots.")

    lines.extend(["", "## Dominant Risk Drivers", ""])
    for row in report.get("top_risk_drivers") or []:
        lines.append(f"- {row['driver']}: {row['count']}")
    if not report.get("top_risk_drivers"):
        lines.append("- No risk drivers supplied.")
    return "\n".join(lines).rstrip() + "\n"


def render_customer_success_risk_trend_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, default=str) + "\n"


def _normalize_snapshots(snapshots: Iterable[CustomerSuccessRiskSnapshotInput | dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for index, raw in enumerate(snapshots):
        status = _status(raw.get("status") or raw.get("risk_level"))
        score = _score(raw.get("risk_score", raw.get("score")), status=status)
        rows.append(
            {
                "account": _text(raw.get("account") or raw.get("account_id") or raw.get("name") or "Unknown account"),
                "observed_at": _text(raw.get("observed_at") or raw.get("date")),
                "risk_score": score,
                "status": status,
                "drivers": _items(raw.get("drivers") or raw.get("driver") or raw.get("reason")),
                "evidence": _items(raw.get("evidence")),
                "_input_order": index,
            }
        )
    rows.sort(key=lambda row: (row["account"].lower(), row["observed_at"] or "9999-12-31", row["_input_order"]))
    for row in rows:
        row.pop("_input_order", None)
    return rows


def _latest_account_row(account: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (row["observed_at"] or "9999-12-31", row["risk_score"], row["status"]))
    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) > 1 else None
    previous_score = previous["risk_score"] if previous else None
    delta = round(latest["risk_score"] - previous_score, 1) if previous_score is not None else 0.0
    return {
        "account": account,
        "observed_at": latest["observed_at"],
        "risk_score": latest["risk_score"],
        "status": latest["status"],
        "previous_risk_score": previous_score,
        "risk_delta": delta,
        "movement": _movement(delta, previous),
        "drivers": latest["drivers"],
        "snapshot_count": len(rows),
    }


def _summary(rows: list[dict[str, Any]], latest_accounts: list[dict[str, Any]]) -> dict[str, Any]:
    latest_count = len(latest_accounts)
    return {
        "account_count": latest_count,
        "snapshot_count": len(rows),
        "average_latest_risk_score": round(sum(row["risk_score"] for row in latest_accounts) / latest_count, 1) if latest_count else 0.0,
        "high_risk_account_count": sum(1 for row in latest_accounts if row["status"] in {"critical", "high"} or row["risk_score"] >= 70),
        "worsening_account_count": sum(1 for row in latest_accounts if row["movement"] == "worsened"),
        "improved_account_count": sum(1 for row in latest_accounts if row["movement"] == "improved"),
    }


def _movement_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {movement: sum(1 for row in rows if row["movement"] == movement) for movement in ("worsened", "improved", "unchanged", "new")}


def _top_risk_drivers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(driver for row in rows for driver in row["drivers"])
    return [{"driver": driver, "count": count} for driver, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[:5]]


def _movement(delta: float, previous: dict[str, Any] | None) -> RiskMovement:
    if previous is None:
        return "new"
    if delta > 0:
        return "worsened"
    if delta < 0:
        return "improved"
    return "unchanged"


def _score(value: Any, *, status: str) -> float:
    try:
        score = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        score = _STATUS_SCORE.get(status, 0.0)
    return round(min(max(score, 0.0), 100.0), 1)


def _status(value: Any) -> str:
    text = _text(value).lower().replace("_", " ")
    if text in _STATUS_SCORE:
        return "high" if text == "at risk" else text
    if text in {"red", "severe"}:
        return "critical"
    if text in {"yellow", "moderate"}:
        return "medium"
    if text in {"green", "ok"}:
        return "healthy"
    return "unknown"


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return sorted({part.strip() for part in value.replace(";", ",").split(",") if part.strip()})
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)})
    return [_text(value)] if _text(value) else []


def _text(value: Any) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|")
