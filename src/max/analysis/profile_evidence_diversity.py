"""Profile evidence diversity analysis."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from max.profiles.schema import PipelineProfile

SCHEMA_VERSION = "max.profile.evidence_diversity.v1"
KIND = "max.profile.evidence_diversity"

DEFAULT_SOURCE_CONCENTRATION_THRESHOLD = 0.60
DEFAULT_CATEGORY_CONCENTRATION_THRESHOLD = 0.70
DEFAULT_REPEATED_TERM_THRESHOLD = 2

_TERM_PARAM_KEYS = (
    "categories",
    "filter_keywords",
    "keywords",
    "queries",
    "query_terms",
    "search_terms",
    "subreddits",
    "tags",
    "topics",
    "watchlist_terms",
)

PROFILE_EVIDENCE_DIVERSITY_CSV_COLUMNS = (
    "schema_version",
    "kind",
    "generated_at",
    "profile",
    "domain",
    "section",
    "item",
    "source",
    "source_count",
    "source_share",
    "category",
    "category_count",
    "category_share",
    "term",
    "term_count",
    "term_sources",
    "warning_type",
    "warning_severity",
    "warning_value",
    "warning_count",
    "warning_share",
    "warning_threshold",
    "warning_message",
    "recommendation",
)


def build_profile_evidence_diversity_report(
    profile: PipelineProfile,
    signals: Sequence[Any],
    *,
    source_concentration_threshold: float = DEFAULT_SOURCE_CONCENTRATION_THRESHOLD,
    category_concentration_threshold: float = DEFAULT_CATEGORY_CONCENTRATION_THRESHOLD,
    repeated_term_threshold: int = DEFAULT_REPEATED_TERM_THRESHOLD,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Measure whether recent profile evidence is concentrated in narrow inputs."""

    if source_concentration_threshold <= 0 or source_concentration_threshold > 1:
        raise ValueError("source_concentration_threshold must be greater than 0 and at most 1")
    if category_concentration_threshold <= 0 or category_concentration_threshold > 1:
        raise ValueError("category_concentration_threshold must be greater than 0 and at most 1")
    if repeated_term_threshold < 1:
        raise ValueError("repeated_term_threshold must be at least 1")

    generated_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    evidence = list(signals)
    total_signals = len(evidence)
    enabled_sources = [source for source in profile.sources if source.enabled]
    enabled_adapters = _dedupe(source.adapter for source in enabled_sources)

    source_counts = Counter(_source_adapter(signal) for signal in evidence)
    category_counts = Counter(_category(signal, profile) for signal in evidence)
    repeated_terms = _repeated_terms(
        profile,
        evidence,
        repeated_term_threshold=repeated_term_threshold,
    )
    source_rows = _share_rows(source_counts, total_signals, key_name="source")
    category_rows = _share_rows(category_counts, total_signals, key_name="category")
    source_concentration = source_rows[0] if source_rows else None
    category_concentration = category_rows[0] if category_rows else None
    warnings = _warnings(
        total_signals=total_signals,
        source_rows=source_rows,
        category_rows=category_rows,
        repeated_terms=repeated_terms,
        source_concentration_threshold=source_concentration_threshold,
        category_concentration_threshold=category_concentration_threshold,
    )
    underused_sources = _underused_sources(enabled_adapters, source_counts, total_signals)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated_at,
        "profile": {
            "name": profile.name,
            "domain": profile.domain.name,
        },
        "thresholds": {
            "source_concentration": source_concentration_threshold,
            "category_concentration": category_concentration_threshold,
            "repeated_term_count": repeated_term_threshold,
        },
        "summary": {
            "total_signals": total_signals,
            "unique_source_count": len(source_counts),
            "unique_category_count": len(category_counts),
            "top_source_share": source_concentration["share"] if source_concentration else 0.0,
            "top_category_share": (
                category_concentration["share"] if category_concentration else 0.0
            ),
            "warning_count": len(warnings),
        },
        "total_signals": total_signals,
        "unique_source_count": len(source_counts),
        "source_concentration": source_concentration,
        "category_concentration": category_concentration,
        "source_diversity": source_rows,
        "category_diversity": category_rows,
        "repeated_query_topic_terms": repeated_terms,
        "concentration_warnings": warnings,
        "recommended_source_mix_adjustments": _recommended_adjustments(
            warnings,
            underused_sources=underused_sources,
            enabled_adapters=enabled_adapters,
        ),
        "underused_sources": underused_sources,
    }


def build_profile_evidence_diversity(
    profile: PipelineProfile,
    signals: Sequence[Any],
    *,
    source_concentration_threshold: float = DEFAULT_SOURCE_CONCENTRATION_THRESHOLD,
    category_concentration_threshold: float = DEFAULT_CATEGORY_CONCENTRATION_THRESHOLD,
    repeated_term_threshold: int = DEFAULT_REPEATED_TERM_THRESHOLD,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compatibility alias for building a profile evidence diversity report."""

    return build_profile_evidence_diversity_report(
        profile,
        signals,
        source_concentration_threshold=source_concentration_threshold,
        category_concentration_threshold=category_concentration_threshold,
        repeated_term_threshold=repeated_term_threshold,
        now=now,
    )


def render_profile_evidence_diversity_report(
    report: Mapping[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Render a profile evidence diversity report as Markdown, JSON, or CSV."""

    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return render_profile_evidence_diversity_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported profile evidence diversity report format: {fmt}")
    return render_profile_evidence_diversity_markdown(report)


def render_profile_evidence_diversity(
    report: Mapping[str, Any],
    *,
    fmt: str = "markdown",
) -> str:
    """Compatibility alias for rendering a profile evidence diversity report."""

    return render_profile_evidence_diversity_report(report, fmt=fmt)


def render_profile_evidence_diversity_markdown(report: Mapping[str, Any]) -> str:
    """Render a deterministic Markdown profile evidence diversity report."""

    profile = report["profile"]
    summary = report["summary"]
    lines = [
        f"# Profile Evidence Diversity: {profile['name']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Kind: `{report['kind']}`",
        f"Generated at: {report['generated_at']}",
        f"Domain: `{profile['domain']}`",
        "",
        "## Summary",
        "",
        f"- Total signals: {summary['total_signals']}",
        f"- Unique sources: {summary['unique_source_count']}",
        f"- Unique categories: {summary['unique_category_count']}",
        f"- Top source share: {_format_share(summary['top_source_share'])}",
        f"- Top category share: {_format_share(summary['top_category_share'])}",
        f"- Concentration warnings: {summary['warning_count']}",
        "",
        "## Source Diversity",
        "",
    ]
    _append_share_table(lines, report.get("source_diversity") or [], "Source", "source")

    lines.extend(["", "## Category Diversity", ""])
    _append_share_table(lines, report.get("category_diversity") or [], "Category", "category")

    lines.extend(["", "## Repeated Query/Topic Terms", ""])
    repeated_terms = report.get("repeated_query_topic_terms") or []
    if repeated_terms:
        lines.append("| Term | Count | Sources |")
        lines.append("| --- | ---: | --- |")
        for row in repeated_terms:
            lines.append(
                f"| {_escape_cell(row['term'])} | {row['count']} | "
                f"{_inline_code(row.get('sources') or [])} |"
            )
    else:
        lines.append("No repeated configured query or topic terms were found.")

    lines.extend(["", "## Concentration Warnings", ""])
    warnings = report.get("concentration_warnings") or []
    if warnings:
        lines.append("| Severity | Type | Detail | Recommendation |")
        lines.append("| --- | --- | --- | --- |")
        for warning in warnings:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _escape_cell(warning["severity"]),
                        _escape_cell(warning["type"]),
                        _escape_cell(warning["message"]),
                        _escape_cell(warning["recommendation"]),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No concentration warnings.")

    lines.extend(["", "## Actionable Evidence Gaps", ""])
    _append_actionable_gap_table(lines, report)

    lines.extend(["", "## Recommended Source Mix Adjustments", ""])
    adjustments = report.get("recommended_source_mix_adjustments") or []
    if adjustments:
        lines.extend(f"- {adjustment}" for adjustment in adjustments)
    else:
        lines.append("- Keep the current source mix and monitor concentration after the next run.")

    return "\n".join(lines).rstrip() + "\n"


def render_profile_evidence_diversity_csv(report: Mapping[str, Any]) -> str:
    """Render a deterministic CSV profile evidence diversity report."""

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=PROFILE_EVIDENCE_DIVERSITY_CSV_COLUMNS,
        lineterminator="\n",
    )
    writer.writeheader()
    for row in _profile_evidence_diversity_csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _profile_evidence_diversity_csv_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary = report["summary"]
    rows.append(
        _csv_row(
            report,
            section="profile",
            item="summary",
            source_count=summary["unique_source_count"],
            category_count=summary["unique_category_count"],
            warning_count=summary["warning_count"],
            source_share=summary["top_source_share"],
            category_share=summary["top_category_share"],
        )
    )

    source_rows = report.get("source_diversity") or []
    if source_rows:
        for source_row in source_rows:
            rows.append(
                _csv_row(
                    report,
                    section="source_mix",
                    item=source_row["source"],
                    source=source_row["source"],
                    source_count=source_row["count"],
                    source_share=source_row["share"],
                )
            )
    else:
        rows.append(
            _csv_row(
                report,
                section="source_mix",
                item="none",
                recommendation="No source evidence is available.",
            )
        )

    category_rows = report.get("category_diversity") or []
    if category_rows:
        for category_row in category_rows:
            rows.append(
                _csv_row(
                    report,
                    section="category_coverage",
                    item=category_row["category"],
                    category=category_row["category"],
                    category_count=category_row["count"],
                    category_share=category_row["share"],
                )
            )
    else:
        rows.append(
            _csv_row(
                report,
                section="category_coverage",
                item="none",
                recommendation="No category evidence is available.",
            )
        )

    repeated_terms = report.get("repeated_query_topic_terms") or []
    if repeated_terms:
        for term_row in repeated_terms:
            rows.append(
                _csv_row(
                    report,
                    section="repeated_term_coverage",
                    item=term_row["term"],
                    term=term_row["term"],
                    term_count=term_row["count"],
                    term_sources=", ".join(term_row.get("sources") or []),
                )
            )
    else:
        rows.append(
            _csv_row(
                report,
                section="repeated_term_coverage",
                item="none",
                recommendation="No repeated configured query or topic terms were found.",
            )
        )

    for warning in report.get("concentration_warnings") or []:
        rows.append(
            _csv_row(
                report,
                section="warning",
                item=warning["type"],
                warning_type=warning["type"],
                warning_severity=warning["severity"],
                warning_value=warning["value"],
                warning_count=warning.get("count", ""),
                warning_share=warning.get("share", ""),
                warning_threshold=warning.get("threshold", ""),
                warning_message=warning["message"],
                recommendation=warning["recommendation"],
            )
        )

    for source_row in report.get("underused_sources") or []:
        rows.append(
            _csv_row(
                report,
                section="underused_source",
                item=source_row["source"],
                source=source_row["source"],
                source_count=source_row["count"],
                source_share=source_row["share"],
                recommendation=source_row["recommendation"],
            )
        )

    adjustments = report.get("recommended_source_mix_adjustments") or []
    if adjustments:
        for index, adjustment in enumerate(adjustments, start=1):
            rows.append(
                _csv_row(
                    report,
                    section="recommendation",
                    item=str(index),
                    recommendation=adjustment,
                )
            )
    else:
        rows.append(
            _csv_row(
                report,
                section="recommendation",
                item="1",
                recommendation="Keep the current source mix and monitor concentration after the next run.",
            )
        )

    return rows


def _csv_row(report: Mapping[str, Any], **values: Any) -> dict[str, Any]:
    profile = report["profile"]
    row = {column: "" for column in PROFILE_EVIDENCE_DIVERSITY_CSV_COLUMNS}
    row.update(
        {
            "schema_version": report["schema_version"],
            "kind": report["kind"],
            "generated_at": report["generated_at"],
            "profile": profile["name"],
            "domain": profile["domain"],
        }
    )
    row.update(values)
    return row


def _source_adapter(signal: Any) -> str:
    return _clean(_value(signal, "source_adapter")) or "unspecified"


def _category(signal: Any, profile: PipelineProfile) -> str:
    metadata = _value(signal, "metadata")
    if isinstance(metadata, Mapping):
        for key in ("category", "domain_category", "topic"):
            value = _clean(metadata.get(key))
            if value:
                return value

    tags = [_clean(tag) for tag in _list_value(_value(signal, "tags"))]
    profile_categories = {category.casefold(): category for category in profile.domain.categories}
    for tag in tags:
        if tag.casefold() in profile_categories:
            return profile_categories[tag.casefold()]
    source_type = _value(signal, "source_type")
    if hasattr(source_type, "value"):
        source_type = source_type.value
    return _clean(source_type) or "uncategorized"


def _repeated_terms(
    profile: PipelineProfile,
    signals: list[Any],
    *,
    repeated_term_threshold: int,
) -> list[dict[str, Any]]:
    terms = _profile_terms(profile)
    counts: Counter[str] = Counter()
    sources_by_term: dict[str, set[str]] = {term.casefold(): set() for term in terms}
    labels_by_key = {term.casefold(): term for term in terms}

    for signal in signals:
        haystack = _signal_text(signal)
        source = _source_adapter(signal)
        for term in terms:
            key = term.casefold()
            if _contains_term(haystack, term):
                counts[key] += 1
                sources_by_term[key].add(source)

    rows = [
        {
            "term": labels_by_key[key],
            "count": count,
            "sources": sorted(sources_by_term[key]),
        }
        for key, count in counts.items()
        if count >= repeated_term_threshold
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["term"].casefold()))


def _profile_terms(profile: PipelineProfile) -> list[str]:
    terms: list[str] = []
    terms.extend(profile.domain.categories)
    terms.extend(profile.domain.workflows)
    terms.extend(profile.domain.target_segments)
    for source in profile.sources:
        if not source.enabled:
            continue
        terms.extend(source.watchlist)
        params = source.normalized_params
        for key in _TERM_PARAM_KEYS:
            terms.extend(_list_value(params.get(key)))
    return _dedupe(term.strip() for term in terms if term and term.strip())


def _warnings(
    *,
    total_signals: int,
    source_rows: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
    repeated_terms: list[dict[str, Any]],
    source_concentration_threshold: float,
    category_concentration_threshold: float,
) -> list[dict[str, Any]]:
    if total_signals == 0:
        return [
            {
                "type": "no_evidence",
                "severity": "high",
                "value": "none",
                "share": 0.0,
                "threshold": 0.0,
                "message": "No recent evidence signals were provided for this profile.",
                "recommendation": (
                    "Run enabled sources or import recent signals before generating ideas "
                    "from this profile."
                ),
            }
        ]

    warnings: list[dict[str, Any]] = []
    warnings.extend(
        _share_warnings(
            rows=source_rows,
            value_key="source",
            warning_type="source_concentration",
            threshold=source_concentration_threshold,
            recommendation=(
                "Add independent evidence from underused enabled sources "
                "before promoting more ideas."
            ),
        )
    )
    warnings.extend(
        _share_warnings(
            rows=category_rows,
            value_key="category",
            warning_type="category_concentration",
            threshold=category_concentration_threshold,
            recommendation=(
                "Broaden collection into adjacent categories or retune profile category queries."
            ),
        )
    )
    for row in repeated_terms:
        warnings.append(
            {
                "type": "repeated_term",
                "severity": "medium" if row["count"] < total_signals else "high",
                "value": row["term"],
                "count": row["count"],
                "share": _share(row["count"], total_signals),
                "threshold": None,
                "message": (
                    f"Configured term '{row['term']}' appears in {row['count']} recent signals."
                ),
                "recommendation": (
                    "Add variant queries and adjacent topics so one term does not dominate "
                    "profile evidence."
                ),
            }
        )
    return sorted(
        warnings,
        key=lambda warning: (
            _severity_order(warning["severity"]),
            warning["type"],
            -float(warning.get("share") or 0.0),
            str(warning.get("value") or ""),
        ),
    )


def _share_warnings(
    *,
    rows: list[dict[str, Any]],
    value_key: str,
    warning_type: str,
    threshold: float,
    recommendation: str,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for row in rows:
        share = float(row["share"])
        if share <= threshold:
            continue
        severity = "high" if share >= 0.8 else "medium"
        warnings.append(
            {
                "type": warning_type,
                "severity": severity,
                "value": row[value_key],
                "count": row["count"],
                "share": share,
                "threshold": threshold,
                "message": (
                    f"{_format_share(share)} of recent evidence comes from "
                    f"{value_key} '{row[value_key]}'."
                ),
                "recommendation": recommendation,
            }
        )
    return warnings


def _recommended_adjustments(
    warnings: list[dict[str, Any]],
    *,
    underused_sources: list[dict[str, Any]],
    enabled_adapters: list[str],
) -> list[str]:
    if any(warning["type"] == "no_evidence" for warning in warnings):
        if enabled_adapters:
            return [
                "Collect fresh evidence from enabled sources: "
                + ", ".join(f"`{adapter}`" for adapter in enabled_adapters)
                + "."
            ]
        return [
            "Configure and enable at least two independent evidence sources for this profile."
        ]

    adjustments: list[str] = []
    if underused_sources:
        adapters = ", ".join(f"`{row['source']}`" for row in underused_sources[:5])
        adjustments.append(f"Increase collection from underused enabled sources: {adapters}.")
    if any(warning["type"] == "category_concentration" for warning in warnings):
        adjustments.append(
            "Add query terms for less represented profile categories before the next run."
        )
    if any(warning["type"] == "repeated_term" for warning in warnings):
        adjustments.append(
            "Rotate repeated query/topic terms with synonyms, adjacent workflows, "
            "and negated filters."
        )
    if not adjustments and enabled_adapters:
        adjustments.append(
            "Keep the current source mix and compare diversity after the next profile run."
        )
    return adjustments


def _underused_sources(
    enabled_adapters: list[str],
    source_counts: Counter[str],
    total_signals: int,
) -> list[dict[str, Any]]:
    if not enabled_adapters:
        return []
    expected_share = 1 / len(enabled_adapters)
    rows: list[dict[str, Any]] = []
    for adapter in enabled_adapters:
        count = source_counts.get(adapter, 0)
        share = _share(count, total_signals)
        if count == 0 or share < round(expected_share * 0.5, 4):
            rows.append(
                {
                    "source": adapter,
                    "count": count,
                    "share": share,
                    "recommendation": f"Retune or allocate more fetch budget to `{adapter}`.",
                }
            )
    return sorted(rows, key=lambda row: (row["count"], row["source"]))


def _share_rows(counts: Counter[str], total: int, *, key_name: str) -> list[dict[str, Any]]:
    return [
        {
            key_name: value,
            "count": count,
            "share": _share(count, total),
        }
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _signal_text(signal: Any) -> str:
    parts = [
        _value(signal, "title"),
        _value(signal, "content"),
        " ".join(_list_value(_value(signal, "tags"))),
    ]
    metadata = _value(signal, "metadata")
    if isinstance(metadata, Mapping):
        parts.extend(str(value) for value in metadata.values() if isinstance(value, str))
    return "\n".join(_clean(part) for part in parts if _clean(part)).casefold()


def _contains_term(haystack: str, term: str) -> bool:
    cleaned = _clean(term).casefold()
    if not cleaned:
        return False
    return re.search(rf"(?<!\w){re.escape(cleaned)}(?!\w)", haystack) is not None


def _value(row: Any, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _list_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return []


def _share(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 4)


def _format_share(value: Any) -> str:
    return f"{float(value) * 100:.1f}%"


def _severity_order(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)


def _inline_code(values: Sequence[Any]) -> str:
    if not values:
        return "None"
    return ", ".join(f"`{_escape_cell(str(value))}`" for value in values)


def _append_share_table(
    lines: list[str],
    rows: Sequence[Mapping[str, Any]],
    label: str,
    key: str,
) -> None:
    if not rows:
        lines.append(f"No {label.lower()} evidence is available.")
        return
    lines.append(f"| {label} | Count | Share |")
    lines.append("| --- | ---: | ---: |")
    for row in rows:
        lines.append(
            f"| {_escape_cell(row[key])} | {row['count']} | {_format_share(row['share'])} |"
        )


def _append_actionable_gap_table(lines: list[str], report: Mapping[str, Any]) -> None:
    warnings = report.get("concentration_warnings") or []
    underused_sources = report.get("underused_sources") or []
    if not warnings and not underused_sources:
        lines.append("- No actionable evidence gaps.")
        return

    lines.append("| Gap | Severity | Evidence | Action |")
    lines.append("| --- | --- | --- | --- |")
    for warning in warnings:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(warning["type"]),
                    _escape_cell(warning["severity"]),
                    _escape_cell(warning["message"]),
                    _escape_cell(warning["recommendation"]),
                ]
            )
            + " |"
        )
    for source in underused_sources:
        evidence = (
            f"`{source['source']}` has {source['count']} signal(s) "
            f"({_format_share(source['share'])})."
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    "underused_source",
                    "medium",
                    _escape_cell(evidence),
                    _escape_cell(source["recommendation"]),
                ]
            )
            + " |"
        )


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(values: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped
