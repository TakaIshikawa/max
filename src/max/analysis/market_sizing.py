"""Deterministic market-sizing reports for persisted design briefs."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from io import StringIO
from pathlib import Path
from typing import Any, Iterable

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.market_sizing.v1"

SIGNAL_BUCKETS = ("survey", "funding", "security", "forum")

CSV_COLUMNS: tuple[str, ...] = (
    "row_type",
    "design_brief_id",
    "design_brief_title",
    "segment_name",
    "buyer",
    "user",
    "source_idea_ids",
    "estimate_scope",
    "estimate_value",
    "assumption",
    "evidence",
    "confidence_level",
    "confidence_score",
    "evidence_strength",
    "risk",
    "next_step",
    "survey_signals",
    "funding_signals",
    "security_signals",
    "forum_signals",
    "total_signals",
)


def build_market_sizing_report(
    store: Store,
    design_brief: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic market-sizing report from persisted brief lineage."""
    source_ideas = _source_ideas(store, design_brief)
    evidence = _collect_evidence(store, source_ideas)
    evaluations = _collect_evaluations(store, source_ideas)
    profile_context = _profile_context(str(design_brief.get("domain") or ""))
    signal_counts = _signal_counts(evidence["signals"].values())
    segments = _segments(design_brief, source_ideas, evidence, evaluations)
    gaps = _gaps(design_brief, source_ideas, signal_counts, evaluations, profile_context)
    confidence = _confidence(design_brief, signal_counts, evaluations, profile_context, gaps)

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "project": "max",
            "entity_type": "design_brief",
            "id": design_brief["id"],
        },
        "design_brief": {
            "id": design_brief["id"],
            "title": design_brief["title"],
            "domain": design_brief.get("domain", ""),
            "theme": design_brief.get("theme", ""),
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": list(design_brief.get("source_idea_ids") or []),
        },
        "market_hypotheses": _market_hypotheses(design_brief, source_ideas, profile_context),
        "segments": segments,
        "signal_counts": signal_counts,
        "evaluation_summary": _evaluation_summary(evaluations),
        "profile_context": profile_context,
        "confidence": confidence,
        "gaps": gaps,
        "recommendations": _recommendations(segments, signal_counts, gaps),
    }


def render_market_sizing_report(report: dict[str, Any], *, fmt: str = "markdown") -> str:
    """Render a market-sizing report as Markdown, JSON, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported market sizing format: {fmt}")

    brief = report["design_brief"]
    counts = report["signal_counts"]
    lines = [
        f"# Market Sizing: {brief['title']}",
        "",
        f"- **Design brief**: `{brief['id']}`",
        f"- **Domain**: {brief.get('domain') or 'general'}",
        f"- **Theme**: {brief.get('theme') or 'implementation-candidate'}",
        f"- **Confidence**: {report['confidence']['level']} ({report['confidence']['score']:.2f})",
        "",
        "## Signal Counts",
        "",
        (
            f"- Survey: {counts['survey']} | Funding: {counts['funding']} | "
            f"Security: {counts['security']} | Forum: {counts['forum']} | "
            f"Total: {counts['total']}"
        ),
        "",
        "## Market Hypotheses",
        "",
    ]
    lines.extend(f"- {item}" for item in report["market_hypotheses"])
    lines.extend(["", "## Segments", ""])
    for segment in report["segments"]:
        lines.extend(
            [
                f"### {segment['name']}",
                "",
                f"- **Buyer**: {segment['buyer']}",
                f"- **User**: {segment['user']}",
                f"- **Evidence strength**: {segment['evidence_strength']}",
                f"- **Confidence**: {segment['confidence']:.2f}",
                (
                    f"- **Signals**: survey={segment['signal_counts']['survey']}, "
                    f"funding={segment['signal_counts']['funding']}, "
                    f"security={segment['signal_counts']['security']}, "
                    f"forum={segment['signal_counts']['forum']}"
                ),
                f"- **Source ideas**: {', '.join(segment['source_idea_ids']) or '-'}",
                "",
            ]
        )
    lines.extend(["## Gaps", ""])
    lines.extend(f"- {gap}" for gap in report["gaps"])
    lines.extend(["", "## Recommended Next Validation Data", ""])
    lines.extend(f"- {item}" for item in report["recommendations"])
    return "\n".join(lines) + "\n"


def write_market_sizing_report(path: Path, report: dict[str, Any], *, fmt: str = "markdown") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_market_sizing_report(report, fmt=fmt), encoding="utf-8")


def market_sizing_filename(design_brief: dict[str, Any], *, fmt: str) -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    brief_id = _filename_part(str(design_brief["id"]))
    title = _filename_part(str(design_brief.get("title") or ""))
    title_part = f"-{title}" if title else ""
    return f"{brief_id}{title_part}-market-sizing.{extension}"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    brief = report.get("design_brief") or {}
    segments = sorted(
        report.get("segments") or [],
        key=lambda segment: (
            str(segment.get("name") or ""),
            str(segment.get("buyer") or ""),
            str(segment.get("user") or ""),
        ),
    )
    if not brief or not segments:
        return []

    rows: list[dict[str, str]] = []
    assumptions = _string_list(report.get("market_hypotheses"))
    recommendations = _string_list(report.get("recommendations"))
    risks = [gap for gap in _string_list(report.get("gaps")) if not gap.startswith("No major")]
    confidence = report.get("confidence") or {}

    for segment in segments:
        segment_risks = [
            gap for gap in _string_list(segment.get("gaps")) if not gap.startswith("No major")
        ]
        row_context = {
            "design_brief_id": brief.get("id"),
            "design_brief_title": brief.get("title"),
            "segment_name": segment.get("name"),
            "buyer": segment.get("buyer"),
            "user": segment.get("user"),
            "source_idea_ids": _csv_join(segment.get("source_idea_ids")),
            "evidence": _evidence_summary(segment),
            "confidence_level": confidence.get("level"),
            "confidence_score": segment.get("confidence"),
            "evidence_strength": segment.get("evidence_strength"),
            **_signal_count_columns(segment.get("signal_counts") or {}),
        }
        for scope, estimate in _segment_estimates(segment):
            rows.append(
                _csv_row(
                    **row_context,
                    row_type="estimate",
                    estimate_scope=scope,
                    estimate_value=estimate,
                    assumption=_csv_join(assumptions),
                    risk=_csv_join([*risks, *segment_risks]),
                    next_step=_csv_join(recommendations),
                )
            )
        for assumption in assumptions:
            rows.append(_csv_row(**row_context, row_type="assumption", assumption=assumption))
        for risk in [*risks, *segment_risks]:
            rows.append(_csv_row(**row_context, row_type="risk", risk=risk))
        for next_step in recommendations:
            rows.append(_csv_row(**row_context, row_type="next_step", next_step=next_step))
    return rows


def _segment_estimates(segment: dict[str, Any]) -> list[tuple[str, str]]:
    buyer = _clean(segment.get("buyer")) or "target buyer"
    user = _clean(segment.get("user")) or "target user"
    strength = _clean(segment.get("evidence_strength")) or "unknown"
    confidence = _clean(segment.get("confidence")) or "0"
    return [
        ("TAM", f"All {buyer} teams with recurring {user} workflow pain; evidence strength={strength}."),
        ("SAM", f"Reachable {buyer} segment represented by linked source ideas and evidence signals."),
        ("SOM", f"Near-term pilotable share requiring validation; segment confidence={confidence}."),
    ]


def _evidence_summary(segment: dict[str, Any]) -> str:
    counts = segment.get("signal_counts") or {}
    adapters = counts.get("by_source_adapter") or {}
    source_types = counts.get("by_source_type") or {}
    parts = [
        f"survey={counts.get('survey', 0)}",
        f"funding={counts.get('funding', 0)}",
        f"security={counts.get('security', 0)}",
        f"forum={counts.get('forum', 0)}",
        f"total={counts.get('total', 0)}",
    ]
    if adapters:
        parts.append(
            "adapters="
            + "; ".join(f"{key}:{adapters[key]}" for key in sorted(adapters))
        )
    if source_types:
        parts.append(
            "source_types="
            + "; ".join(f"{key}:{source_types[key]}" for key in sorted(source_types))
        )
    return " | ".join(parts)


def _signal_count_columns(counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "survey_signals": counts.get("survey", 0),
        "funding_signals": counts.get("funding", 0),
        "security_signals": counts.get("security", 0),
        "forum_signals": counts.get("forum", 0),
        "total_signals": counts.get("total", 0),
    }


def _csv_row(**values: Any) -> dict[str, str]:
    return {column: _csv_text(values.get(column)) for column in CSV_COLUMNS}


def _csv_join(values: Any, *, separator: str = "; ") -> str:
    return separator.join(text for value in _string_list(values) if (text := _csv_text(value)))


def _csv_text(value: Any) -> str:
    return "" if value is None else str(value)


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id = {
        source["idea_id"]: source
        for source in design_brief.get("sources", [])
        if source.get("idea_id")
    }
    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *list(design_brief.get("source_idea_ids") or []),
                *relationship_by_id.keys(),
            ]
        )
    )

    ideas: list[dict[str, Any]] = []
    for idea_id in ordered_ids:
        if not idea_id:
            continue
        unit = store.get_buildable_unit(str(idea_id))
        if not unit:
            continue
        data = unit.model_dump(mode="json")
        relationship = relationship_by_id.get(str(idea_id), {})
        data["role"] = relationship.get("role") or (
            "lead" if idea_id == design_brief.get("lead_idea_id") else "source"
        )
        ideas.append(data)
    return ideas


def _collect_evidence(store: Store, source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    signal_ids: set[str] = set()
    insight_ids: set[str] = set()
    for idea in source_ideas:
        signal_ids.update(_string_list(idea.get("evidence_signals")))
        insight_ids.update(_string_list(idea.get("inspiring_insights")))

    insights: dict[str, Any] = {}
    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if not insight:
            continue
        insights[insight_id] = insight
        signal_ids.update(_string_list(getattr(insight, "evidence", [])))

    signals: dict[str, Any] = {}
    for signal_id in sorted(signal_ids):
        signal = store.get_signal(signal_id)
        if signal:
            signals[signal_id] = signal
    return {"signals": signals, "insights": insights}


def _collect_evaluations(store: Store, source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    evaluations = {}
    for idea in source_ideas:
        idea_id = idea.get("id")
        if not idea_id:
            continue
        evaluation = store.get_evaluation(str(idea_id))
        if evaluation:
            evaluations[str(idea_id)] = evaluation
    return evaluations


def _profile_context(domain: str) -> dict[str, Any]:
    if not domain:
        return {"domain": "", "profile_name": None, "categories": [], "target_user_types": []}
    try:
        from max.profiles.loader import list_profiles, load_profile

        for profile_name in sorted(list_profiles()):
            profile = load_profile(profile_name)
            if profile.domain.name == domain or profile_name == domain:
                return {
                    "domain": profile.domain.name,
                    "profile_name": profile.name,
                    "description": profile.domain.description,
                    "categories": sorted(profile.domain.categories),
                    "target_user_types": sorted(profile.domain.target_user_types),
                }
    except Exception:
        pass
    return {"domain": domain, "profile_name": None, "categories": [], "target_user_types": []}


def _signal_counts(signals: Iterable[Any]) -> dict[str, Any]:
    by_type: Counter[str] = Counter()
    by_adapter: Counter[str] = Counter()
    by_role: Counter[str] = Counter()

    for signal in signals:
        source_type = _source_type(signal)
        by_type[source_type] += 1
        by_adapter[str(getattr(signal, "source_adapter", "") or "unknown")] += 1
        role = str(getattr(signal, "signal_role", "") or "").lower()
        if role:
            by_role[role] += 1

    bucket_counts = {bucket: 0 for bucket in SIGNAL_BUCKETS}
    for source_type, count in by_type.items():
        if source_type in bucket_counts:
            bucket_counts[source_type] += count
        elif source_type in {"article", "roadmap", "failure_data", "trending", "registry"}:
            continue
    return {
        **bucket_counts,
        "total": sum(by_type.values()),
        "by_source_type": dict(sorted(by_type.items())),
        "by_source_adapter": dict(sorted(by_adapter.items())),
        "by_signal_role": dict(sorted(by_role.items())),
    }


def _segments(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    evidence: dict[str, Any],
    evaluations: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    primary_key = (
        _clean(design_brief.get("buyer")) or "Unknown buyer",
        _clean(design_brief.get("specific_user")) or "Unknown user",
    )
    for idea in source_ideas:
        key = (
            _clean(idea.get("buyer")) or primary_key[0],
            _clean(idea.get("specific_user")) or primary_key[1],
        )
        grouped[key].append(idea)
    if not grouped:
        grouped[primary_key] = []

    segments = []
    for (buyer, user), ideas in sorted(grouped.items(), key=lambda item: item[0]):
        signal_ids = _segment_signal_ids(ideas, evidence)
        signals = [evidence["signals"][signal_id] for signal_id in signal_ids if signal_id in evidence["signals"]]
        counts = _signal_counts(signals)
        idea_ids = sorted(str(idea["id"]) for idea in ideas if idea.get("id"))
        avg_eval = _average(
            float(evaluations[idea_id].overall_score)
            for idea_id in idea_ids
            if idea_id in evaluations
        )
        strength = _evidence_strength(counts["total"], len(counts["by_source_adapter"]), avg_eval)
        confidence = _segment_confidence(counts["total"], len(counts["by_source_adapter"]), avg_eval)
        segment_gaps = []
        if buyer == "Unknown buyer":
            segment_gaps.append("Buyer is not specified for this segment.")
        if user == "Unknown user":
            segment_gaps.append("Specific user is not specified for this segment.")
        if counts["survey"] == 0:
            segment_gaps.append("No survey evidence is linked to this segment.")
        if counts["funding"] == 0:
            segment_gaps.append("No funding evidence is linked to this segment.")
        segments.append(
            {
                "name": _segment_name(buyer, user),
                "buyer": buyer,
                "user": user,
                "source_idea_ids": idea_ids,
                "signal_counts": counts,
                "evaluation_score": avg_eval,
                "evidence_strength": strength,
                "confidence": confidence,
                "gaps": segment_gaps,
            }
        )
    return segments


def _segment_signal_ids(ideas: list[dict[str, Any]], evidence: dict[str, Any]) -> list[str]:
    ids: set[str] = set()
    for idea in ideas:
        ids.update(_string_list(idea.get("evidence_signals")))
        for insight_id in _string_list(idea.get("inspiring_insights")):
            insight = evidence["insights"].get(insight_id)
            if insight:
                ids.update(_string_list(getattr(insight, "evidence", [])))
    return sorted(ids)


def _market_hypotheses(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    profile_context: dict[str, Any],
) -> list[str]:
    buyer = _clean(design_brief.get("buyer")) or _first_non_empty(idea.get("buyer") for idea in source_ideas) or "target buyer"
    user = (
        _clean(design_brief.get("specific_user"))
        or _first_non_empty(idea.get("specific_user") for idea in source_ideas)
        or "target user"
    )
    workflow = (
        _clean(design_brief.get("workflow_context"))
        or _first_non_empty(idea.get("workflow_context") for idea in source_ideas)
        or "target workflow"
    )
    domain = profile_context.get("domain") or design_brief.get("domain") or "the target domain"
    hypotheses = [
        f"{buyer} will sponsor validation if {user} has recurring pain in {workflow}.",
        f"The initial reachable market is the {domain} segment already represented by the persisted source ideas.",
    ]
    if design_brief.get("why_this_now"):
        hypotheses.append(f"Market timing depends on this urgency holding true: {design_brief['why_this_now']}")
    return hypotheses


def _evaluation_summary(evaluations: dict[str, Any]) -> dict[str, Any]:
    scores = [float(evaluation.overall_score) for evaluation in evaluations.values()]
    recommendations = Counter(str(evaluation.recommendation) for evaluation in evaluations.values())
    return {
        "evaluated_source_ideas": len(scores),
        "average_overall_score": _round_or_none(_average(scores)),
        "recommendations": dict(sorted(recommendations.items())),
    }


def _gaps(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    signal_counts: dict[str, Any],
    evaluations: dict[str, Any],
    profile_context: dict[str, Any],
) -> list[str]:
    gaps = []
    if not source_ideas:
        gaps.append("No persisted source ideas could be loaded for this brief.")
    if not _clean(design_brief.get("buyer")):
        gaps.append("Design brief does not name a buyer.")
    if not _clean(design_brief.get("specific_user")):
        gaps.append("Design brief does not name a specific user.")
    if signal_counts["survey"] == 0:
        gaps.append("No quantified survey evidence is linked to the brief lineage.")
    if signal_counts["funding"] == 0:
        gaps.append("No funding signal is linked to the brief lineage.")
    if signal_counts["forum"] == 0:
        gaps.append("No forum demand signal is linked to the brief lineage.")
    if len(evaluations) < len(source_ideas):
        gaps.append("At least one source idea has no persisted evaluation.")
    if not profile_context.get("profile_name"):
        gaps.append("No matching profile context was found for the brief domain.")
    return gaps or ["No major market-sizing data gaps detected."]


def _recommendations(
    segments: list[dict[str, Any]],
    signal_counts: dict[str, Any],
    gaps: list[str],
) -> list[str]:
    recs = []
    weakest = [segment for segment in segments if segment["evidence_strength"] == "weak"]
    if weakest:
        names = ", ".join(segment["name"] for segment in weakest[:3])
        recs.append(f"Collect direct discovery evidence for weak segment(s): {names}.")
    if signal_counts["survey"] == 0:
        recs.append("Add survey or benchmark data that quantifies frequency, spend, or adoption intent.")
    if signal_counts["funding"] == 0:
        recs.append("Add funding, purchasing, or budget-owner evidence to test willingness to pay.")
    if signal_counts["security"] > 0:
        recs.append("Validate whether security evidence creates budget urgency or only implementation risk.")
    if any("buyer" in gap.lower() for gap in gaps):
        recs.append("Interview budget owners separately from users and record approval criteria.")
    recs.append("Run a segment-tagged smoke test so conversion can be compared by buyer and user profile.")
    return list(dict.fromkeys(recs))


def _confidence(
    design_brief: dict[str, Any],
    signal_counts: dict[str, Any],
    evaluations: dict[str, Any],
    profile_context: dict[str, Any],
    gaps: list[str],
) -> dict[str, Any]:
    readiness = min(max(float(design_brief.get("readiness_score") or 0.0) / 100.0, 0.0), 1.0)
    evidence_score = min(signal_counts["total"] / 8.0, 1.0)
    quantified_score = min(
        (signal_counts["survey"] + signal_counts["funding"] + signal_counts["forum"]) / 4.0,
        1.0,
    )
    evaluation_score = (
        min((_average(float(e.overall_score) for e in evaluations.values()) or 0.0) / 100.0, 1.0)
        if evaluations
        else 0.0
    )
    profile_score = 1.0 if profile_context.get("profile_name") else 0.4
    gap_penalty = min(max(len([gap for gap in gaps if not gap.startswith("No major")]) * 0.05, 0.0), 0.25)
    score = max(
        0.0,
        min(
            1.0,
            readiness * 0.25
            + evidence_score * 0.20
            + quantified_score * 0.20
            + evaluation_score * 0.25
            + profile_score * 0.10
            - gap_penalty,
        ),
    )
    return {
        "score": round(score, 2),
        "level": "high" if score >= 0.75 else "medium" if score >= 0.45 else "low",
        "drivers": [
            f"readiness={readiness:.2f}",
            f"evidence_signals={signal_counts['total']}",
            f"evaluations={len(evaluations)}",
            f"profile_context={'yes' if profile_context.get('profile_name') else 'no'}",
        ],
    }


def _evidence_strength(signal_count: int, adapter_count: int, evaluation_score: float | None) -> str:
    if signal_count >= 5 and adapter_count >= 3 and (evaluation_score or 0.0) >= 70.0:
        return "strong"
    if signal_count >= 2 and adapter_count >= 2:
        return "moderate"
    return "weak"


def _segment_confidence(signal_count: int, adapter_count: int, evaluation_score: float | None) -> float:
    score = min(signal_count / 6.0, 1.0) * 0.45 + min(adapter_count / 3.0, 1.0) * 0.25
    score += min((evaluation_score or 0.0) / 100.0, 1.0) * 0.30
    return round(score, 2)


def _source_type(signal: Any) -> str:
    source_type = getattr(signal, "source_type", "")
    if hasattr(source_type, "value"):
        return str(source_type.value).lower()
    return str(source_type or "").lower()


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(values: Iterable[Any]) -> str:
    for value in values:
        clean = _clean(value)
        if clean:
            return clean
    return ""


def _average(values: Iterable[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _segment_name(buyer: str, user: str) -> str:
    if buyer == user:
        return buyer
    return f"{buyer} / {user}"
