"""Signal source coverage drift report for expected versus observed source mix."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import StringIO
from typing import Any


SCHEMA_VERSION = "max.signal_source_coverage_drift.v1"
KIND = "max.signal_source_coverage_drift"
CSV_COLUMNS = (
    "profile",
    "domain",
    "source",
    "expected_share",
    "observed_share",
    "absolute_drift",
    "observed_count",
    "severity_band",
)
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "healthy": 2}


@dataclass(frozen=True)
class ExpectedSourceCoverage:
    profile: str
    source: str
    expected_share: float
    domain: str = ""


@dataclass(frozen=True)
class ObservedSignalSourceCount:
    profile: str
    source: str
    observed_count: int
    domain: str = ""


@dataclass(frozen=True)
class SourceCoverageDriftRow:
    profile: str
    domain: str
    source: str
    expected_share: float
    observed_share: float
    absolute_drift: float
    observed_count: int
    severity_band: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "domain": self.domain,
            "source": self.source,
            "expected_share": self.expected_share,
            "observed_share": self.observed_share,
            "absolute_drift": self.absolute_drift,
            "observed_count": self.observed_count,
            "severity_band": self.severity_band,
        }


def build_signal_source_coverage_drift_report(
    expected_coverage: Iterable[ExpectedSourceCoverage | Mapping[str, Any]],
    observed_signals: Iterable[ObservedSignalSourceCount | Mapping[str, Any]],
    *,
    warning_drift_threshold: float = 0.15,
    critical_drift_threshold: float = 0.30,
) -> dict[str, Any]:
    """Compare expected source shares against observed signal counts by profile/domain."""
    if warning_drift_threshold < 0:
        raise ValueError("warning_drift_threshold must be non-negative")
    if critical_drift_threshold < warning_drift_threshold:
        raise ValueError("critical_drift_threshold must be greater than or equal to warning_drift_threshold")

    expected = [_normalize_expected(item) for item in expected_coverage]
    observed = [_normalize_observed(item) for item in observed_signals]
    expected_by_key = {(item.profile, item.domain, item.source): item for item in expected}
    observed_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    group_totals: dict[tuple[str, str], int] = defaultdict(int)
    for item in observed:
        key = (item.profile, item.domain, item.source)
        observed_counts[key] += item.observed_count
        group_totals[(item.profile, item.domain)] += item.observed_count

    all_keys = set(expected_by_key) | set(observed_counts)
    rows = [
        _row_for_key(
            key,
            expected_by_key.get(key),
            observed_counts.get(key, 0),
            group_totals.get((key[0], key[1]), 0),
            warning_drift_threshold,
            critical_drift_threshold,
        )
        for key in all_keys
    ]
    rows.sort(key=_row_sort_key)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "filters": {
            "warning_drift_threshold": warning_drift_threshold,
            "critical_drift_threshold": critical_drift_threshold,
        },
        "summary": {
            "coverage_row_count": len(rows),
            "critical_count": sum(1 for row in rows if row.severity_band == "critical"),
            "warning_count": sum(1 for row in rows if row.severity_band == "warning"),
            "healthy_count": sum(1 for row in rows if row.severity_band == "healthy"),
            "zero_observed_expected_count": sum(1 for row in rows if row.expected_share > 0 and row.observed_count == 0),
        },
        "rows": [row.as_dict() for row in rows],
    }


def render_signal_source_coverage_drift_report(report: Mapping[str, Any], *, fmt: str = "json") -> str:
    """Render signal source coverage drift as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported signal source coverage drift report format: {fmt}")

    summary = _mapping(report.get("summary"))
    lines = [
        "# Signal Source Coverage Drift",
        "",
        f"Schema: `{report.get('schema_version')}`",
        f"Rows: {summary.get('coverage_row_count', 0)}",
        f"Critical: {summary.get('critical_count', 0)}",
        f"Warning: {summary.get('warning_count', 0)}",
        f"Zero observed expected sources: {summary.get('zero_observed_expected_count', 0)}",
        "",
        "## Coverage Drift",
        "",
        "| Profile | Domain | Source | Expected Share | Observed Share | Drift | Observed Count | Severity |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    rows = _sorted_row_maps(report.get("rows"))
    if rows:
        for row in rows:
            lines.append(
                "| `{}` | `{}` | `{}` | {:.3f} | {:.3f} | {:.3f} | {} | {} |".format(
                    row.get("profile") or "",
                    row.get("domain") or "",
                    row.get("source") or "",
                    float(row.get("expected_share") or 0.0),
                    float(row.get("observed_share") or 0.0),
                    float(row.get("absolute_drift") or 0.0),
                    row.get("observed_count", 0),
                    row.get("severity_band") or "",
                )
            )
    else:
        lines.append("| none | none | none | 0.000 | 0.000 | 0.000 | 0 | healthy |")
    return "\n".join(lines).rstrip() + "\n"


def _render_csv(report: Mapping[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _sorted_row_maps(report.get("rows")):
        writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})
    return output.getvalue()


def _row_for_key(
    key: tuple[str, str, str],
    expected: ExpectedSourceCoverage | None,
    observed_count: int,
    group_total: int,
    warning_drift_threshold: float,
    critical_drift_threshold: float,
) -> SourceCoverageDriftRow:
    profile, domain, source = key
    expected_share = round(expected.expected_share if expected is not None else 0.0, 4)
    observed_share = round(observed_count / group_total, 4) if group_total else 0.0
    drift = round(abs(expected_share - observed_share), 4)
    if drift >= critical_drift_threshold or (expected_share > 0 and observed_count == 0):
        severity = "critical"
    elif drift >= warning_drift_threshold:
        severity = "warning"
    else:
        severity = "healthy"
    return SourceCoverageDriftRow(
        profile=profile,
        domain=domain,
        source=source,
        expected_share=expected_share,
        observed_share=observed_share,
        absolute_drift=drift,
        observed_count=observed_count,
        severity_band=severity,
    )


def _normalize_expected(item: ExpectedSourceCoverage | Mapping[str, Any]) -> ExpectedSourceCoverage:
    if isinstance(item, ExpectedSourceCoverage):
        row = item
    else:
        row = ExpectedSourceCoverage(
            profile=str(item.get("profile") or "unspecified"),
            domain=str(item.get("domain") or ""),
            source=str(item.get("source") or item.get("source_adapter") or "unknown"),
            expected_share=_bounded_share(item.get("expected_share", item.get("share", 0.0))),
        )
    return ExpectedSourceCoverage(
        profile=row.profile or "unspecified",
        domain=row.domain or "",
        source=row.source or "unknown",
        expected_share=_bounded_share(row.expected_share),
    )


def _normalize_observed(item: ObservedSignalSourceCount | Mapping[str, Any]) -> ObservedSignalSourceCount:
    if isinstance(item, ObservedSignalSourceCount):
        row = item
    else:
        row = ObservedSignalSourceCount(
            profile=str(item.get("profile") or "unspecified"),
            domain=str(item.get("domain") or ""),
            source=str(item.get("source") or item.get("source_adapter") or "unknown"),
            observed_count=_nonnegative_int(item.get("observed_count", item.get("signal_count", 1))),
        )
    return ObservedSignalSourceCount(
        profile=row.profile or "unspecified",
        domain=row.domain or "",
        source=row.source or "unknown",
        observed_count=_nonnegative_int(row.observed_count),
    )


def _row_sort_key(row: SourceCoverageDriftRow) -> tuple[int, float, str, str, str]:
    zero_expected_source = row.expected_share > 0 and row.observed_count == 0
    return (_SEVERITY_ORDER[row.severity_band], 0 if zero_expected_source else 1, -row.absolute_drift, row.profile, row.domain, row.source)


def _sorted_row_maps(value: Any) -> list[Mapping[str, Any]]:
    rows = _list_of_maps(value)
    return sorted(
        rows,
        key=lambda row: (
            _SEVERITY_ORDER.get(str(row.get("severity_band")), len(_SEVERITY_ORDER)),
            0 if _float(row.get("expected_share")) > 0 and _int(row.get("observed_count")) == 0 else 1,
            -_float(row.get("absolute_drift")),
            str(row.get("profile") or ""),
            str(row.get("domain") or ""),
            str(row.get("source") or ""),
        ),
    )


def _bounded_share(value: Any) -> float:
    try:
        return round(min(1.0, max(0.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_maps(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []
