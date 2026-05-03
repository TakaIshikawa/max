"""Competitive landscape reports for persisted design briefs."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from typing import Any

from max.analysis.idea_similarity import find_similar_ideas
from max.analysis.portfolio_overlap import find_portfolio_overlap_clusters
from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.competitive_landscape.v1"

CSV_COLUMNS: tuple[str, ...] = (
    "schema_version",
    "design_brief_id",
    "design_brief_title",
    "status",
    "row_type",
    "item_id",
    "item_name",
    "saturation_level",
    "saturation_score",
    "source_idea_ids",
    "competitor_count",
    "prior_art_record_count",
    "similar_idea_count",
    "portfolio_overlap_cluster_count",
    "evaluation_count",
    "overlap_score",
    "evidence_ids",
    "counts",
    "rationale_summary",
    "suggested_response",
    "details",
)


def build_design_brief_competitive_landscape(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a deterministic competitive landscape report from stored Max data."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_ids = [idea["id"] for idea in source_ideas]
    prior_art = _prior_art_records(store, source_ids)
    evaluations = _evaluation_records(store, source_ids)
    similarity = _similarity_records(store, source_ideas)
    portfolio_overlap = _portfolio_overlap_records(store, set(source_ids))

    status = "ready" if prior_art else "insufficient_data"
    clusters = _competitor_clusters(prior_art, source_ideas)
    differentiation_angles = _differentiation_angles(
        design_brief,
        source_ideas,
        clusters,
        evaluations,
        similarity,
        portfolio_overlap,
    )
    saturation = _saturation_level(clusters, evaluations, similarity, portfolio_overlap)

    return {
        "schema_version": SCHEMA_VERSION,
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
            "source_idea_ids": source_ids or list(design_brief.get("source_idea_ids") or []),
        },
        "status": status,
        "summary": {
            "source_idea_count": len(source_ids),
            "prior_art_record_count": len(prior_art),
            "competitor_cluster_count": len(clusters),
            "similar_idea_count": len(similarity),
            "portfolio_overlap_cluster_count": len(portfolio_overlap),
            "saturation_level": saturation["level"],
            "insufficient_data_reasons": [] if prior_art else [
                "No stored prior-art records are linked to the design brief source ideas."
            ],
        },
        "saturation": saturation,
        "competitor_clusters": clusters,
        "differentiation_angles": differentiation_angles,
        "recommended_positioning": _recommended_positioning(
            design_brief,
            saturation,
            differentiation_angles,
            clusters,
        ),
        "signals": {
            "prior_art": prior_art,
            "similar_ideas": similarity,
            "portfolio_overlap": portfolio_overlap,
            "evaluations": evaluations,
        },
        "source_ideas": source_ideas,
    }


def render_design_brief_competitive_landscape(report: dict[str, Any], fmt: str = "json") -> str:
    """Render a competitive landscape report for MCP consumers."""
    if fmt == "json":
        return json.dumps(report, indent=2) + "\n"
    if fmt == "csv":
        return render_design_brief_competitive_landscape_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported competitive landscape format: {fmt}")

    brief = report["design_brief"]
    lines = [
        f"# Competitive Landscape: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Status: `{report['status']}`",
        f"Saturation: `{report['saturation']['level']}`",
        "",
        "## Recommended Positioning",
        "",
        report["recommended_positioning"],
        "",
    ]
    for cluster in report["competitor_clusters"]:
        lines.extend(
            [
                f"## {cluster['name']}",
                "",
                cluster["positioning_summary"],
                "",
                f"- Competitors: {cluster['competitor_count']}",
                f"- Source ideas: {', '.join(cluster['source_idea_ids'])}",
                f"- Suggested response: {cluster['suggested_response']}",
                "",
            ]
        )
    if not report["competitor_clusters"]:
        lines.extend(["## Data Gap", "", "; ".join(report["summary"]["insufficient_data_reasons"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def render_design_brief_competitive_landscape_csv(report: dict[str, Any]) -> str:
    """Render competitive landscape rows as deterministic CSV text."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, str]]:
    summary = report.get("summary") or {}
    saturation = report.get("saturation") or {}
    clusters = list(report.get("competitor_clusters") or [])
    angles = list(report.get("differentiation_angles") or [])
    signal_counts = _signal_counts(report)
    rows = [
        _csv_row(
            report,
            row_type="summary",
            item_id="summary",
            item_name="Competitive landscape summary",
            saturation_level=summary.get("saturation_level") or saturation.get("level"),
            prior_art_record_count=summary.get("prior_art_record_count"),
            competitor_count=summary.get("competitor_cluster_count"),
            similar_idea_count=summary.get("similar_idea_count"),
            portfolio_overlap_cluster_count=summary.get("portfolio_overlap_cluster_count"),
            evaluation_count=signal_counts["evaluation_count"],
            source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
            counts=signal_counts,
            rationale_summary="; ".join(_string_list(summary.get("insufficient_data_reasons"))),
            suggested_response=report.get("recommended_positioning"),
        ),
        _csv_row(
            report,
            row_type="saturation",
            item_id="saturation",
            item_name="Saturation signal",
            saturation_level=saturation.get("level"),
            saturation_score=saturation.get("score"),
            source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
            counts=signal_counts,
            rationale_summary=saturation.get("level"),
            suggested_response=report.get("recommended_positioning"),
            details={"drivers": saturation.get("drivers")},
        ),
    ]

    if not clusters:
        rows.append(
            _csv_row(
                report,
                row_type="data_gap",
                item_id="data-gap",
                item_name="Prior-art data gap",
                saturation_level=saturation.get("level"),
                source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
                counts=signal_counts,
                rationale_summary="; ".join(_string_list(summary.get("insufficient_data_reasons"))),
                suggested_response=report.get("recommended_positioning"),
            )
        )

    for cluster in clusters:
        top_competitors = list(cluster.get("top_competitors") or [])
        rows.append(
            _csv_row(
                report,
                row_type="competitor_cluster",
                item_id=cluster.get("id"),
                item_name=cluster.get("name"),
                saturation_level=saturation.get("level"),
                saturation_score=saturation.get("score"),
                source_idea_ids=cluster.get("source_idea_ids"),
                competitor_count=cluster.get("competitor_count"),
                overlap_score=cluster.get("overlap_score"),
                evidence_ids=[record.get("id") for record in top_competitors],
                counts={
                    "competitor_count": cluster.get("competitor_count"),
                    "source_idea_count": len(_string_list(cluster.get("source_idea_ids"))),
                    "top_competitor_count": len(top_competitors),
                },
                rationale_summary=cluster.get("positioning_summary"),
                suggested_response=cluster.get("suggested_response"),
                details={
                    "source": cluster.get("source"),
                    "shared_terms": cluster.get("shared_terms"),
                    "top_competitor_ids": [record.get("id") for record in top_competitors],
                    "top_competitor_titles": [record.get("title") for record in top_competitors],
                },
            )
        )

    for angle in angles:
        rows.append(
            _csv_row(
                report,
                row_type="differentiation_angle",
                item_id=angle.get("id"),
                item_name=angle.get("title"),
                saturation_level=saturation.get("level"),
                source_idea_ids=angle.get("source_idea_ids"),
                evidence_ids=angle.get("evidence"),
                counts={"evidence_count": len(_string_list(angle.get("evidence")))},
                rationale_summary=angle.get("rationale"),
                suggested_response=report.get("recommended_positioning"),
            )
        )

    rows.append(
        _csv_row(
            report,
            row_type="recommended_positioning",
            item_id="recommended-positioning",
            item_name="Recommended positioning",
            saturation_level=saturation.get("level"),
            saturation_score=saturation.get("score"),
            source_idea_ids=(report.get("design_brief") or {}).get("source_idea_ids"),
            counts=signal_counts,
            rationale_summary=report.get("recommended_positioning"),
            suggested_response=report.get("recommended_positioning"),
        )
    )
    return rows


def _csv_row(report: dict[str, Any], **values: Any) -> dict[str, str]:
    brief = report.get("design_brief") or {}
    row = {
        "schema_version": report.get("schema_version"),
        "design_brief_id": brief.get("id"),
        "design_brief_title": brief.get("title"),
        "status": report.get("status"),
        "row_type": "",
        "item_id": "",
        "item_name": "",
        "saturation_level": "",
        "saturation_score": "",
        "source_idea_ids": "",
        "competitor_count": "",
        "prior_art_record_count": "",
        "similar_idea_count": "",
        "portfolio_overlap_cluster_count": "",
        "evaluation_count": "",
        "overlap_score": "",
        "evidence_ids": "",
        "counts": "",
        "rationale_summary": "",
        "suggested_response": "",
        "details": "",
    }
    row.update(values)
    return {column: _csv_cell(row.get(column)) for column in CSV_COLUMNS}


def _signal_counts(report: dict[str, Any]) -> dict[str, int]:
    summary = report.get("summary") or {}
    signals = report.get("signals") or {}
    return {
        "source_idea_count": int(summary.get("source_idea_count") or 0),
        "prior_art_record_count": int(summary.get("prior_art_record_count") or 0),
        "competitor_cluster_count": int(summary.get("competitor_cluster_count") or 0),
        "similar_idea_count": int(summary.get("similar_idea_count") or 0),
        "portfolio_overlap_cluster_count": int(summary.get("portfolio_overlap_cluster_count") or 0),
        "evaluation_count": len(signals.get("evaluations") or []),
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple | set):
        return _stable_json(list(value))
    if isinstance(value, dict):
        return _stable_json(
            {key: item for key, item in value.items() if item not in (None, "", [])}
        )
    return str(value)


def _stable_json(value: Any) -> str:
    return json.dumps(_stable_value(value), sort_keys=True, separators=(",", ":"))


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _stable_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple | set):
        return sorted(
            (_stable_value(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return value


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    relationship_by_id: dict[str, dict[str, Any]] = {}
    for source in design_brief.get("sources", []):
        relationship_by_id.setdefault(source["idea_id"], source)

    ordered_ids = list(
        dict.fromkeys(
            [
                design_brief.get("lead_idea_id"),
                *design_brief.get("source_idea_ids", []),
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
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _prior_art_records(store: Store, source_ids: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea_id in source_ids:
        for match in store.get_prior_art_matches(idea_id):
            records.append(
                {
                    "id": match["id"],
                    "source_idea_id": idea_id,
                    "source": match["source"],
                    "title": match["title"],
                    "url": match["url"],
                    "description": match.get("description", ""),
                    "relevance_score": round(float(match.get("relevance_score") or 0.0), 3),
                    "match_signals": match.get("match_signals", {}),
                    "search_query": match.get("search_query", ""),
                    "created_at": match.get("created_at", ""),
                }
            )
    records.sort(key=lambda item: (-item["relevance_score"], item["source"], item["title"], item["id"]))
    return records


def _evaluation_records(store: Store, source_ids: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea_id in source_ids:
        evaluation = store.get_evaluation(idea_id)
        if not evaluation:
            continue
        records.append(
            {
                "source_idea_id": idea_id,
                "competitive_density_score": evaluation.competitive_density.value,
                "competitive_density_confidence": evaluation.competitive_density.confidence,
                "competitive_density_reasoning": evaluation.competitive_density.reasoning,
                "overall_score": evaluation.overall_score,
                "strengths": evaluation.strengths,
                "weaknesses": evaluation.weaknesses,
                "recommendation": evaluation.recommendation,
            }
        )
    return records


def _similarity_records(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records_by_id: dict[str, dict[str, Any]] = {}
    source_ids = {idea["id"] for idea in source_ideas}
    for idea in source_ideas:
        try:
            results = find_similar_ideas(store, idea_id=idea["id"], threshold=0.18, limit=5)
        except (LookupError, ValueError):
            continue
        for result in results:
            if result.idea_id in source_ids:
                continue
            existing = records_by_id.get(result.idea_id)
            record = {
                "idea_id": result.idea_id,
                "title": result.title,
                "problem_summary": result.problem_summary,
                "similarity_score": round(result.similarity_score, 3),
                "source_idea_ids": [idea["id"]],
                "overlapping_evidence_ids": result.overlapping_evidence_ids,
                "overlapping_insight_ids": result.overlapping_insight_ids,
            }
            if existing is None:
                records_by_id[result.idea_id] = record
            else:
                existing["similarity_score"] = max(existing["similarity_score"], record["similarity_score"])
                existing["source_idea_ids"] = sorted(set(existing["source_idea_ids"]) | {idea["id"]})
                existing["overlapping_evidence_ids"] = sorted(
                    set(existing["overlapping_evidence_ids"]) | set(record["overlapping_evidence_ids"])
                )
                existing["overlapping_insight_ids"] = sorted(
                    set(existing["overlapping_insight_ids"]) | set(record["overlapping_insight_ids"])
                )
    records = list(records_by_id.values())
    records.sort(key=lambda item: (-item["similarity_score"], item["idea_id"]))
    return records[:10]


def _portfolio_overlap_records(store: Store, source_ids: set[str]) -> list[dict[str, Any]]:
    clusters = find_portfolio_overlap_clusters(store, limit=20, min_overlap_score=0.25)
    records: list[dict[str, Any]] = []
    for cluster in clusters:
        if not source_ids & set(cluster.idea_ids):
            continue
        records.append(
            {
                "cluster_id": cluster.cluster_id,
                "idea_ids": cluster.idea_ids,
                "representative_idea_ids": cluster.representative_idea_ids,
                "overlap_score": cluster.overlap_score,
                "suggested_action": cluster.suggested_action,
                "overlap_reasons": [
                    {
                        "type": reason.type,
                        "description": reason.description,
                        "score": reason.score,
                        "shared_terms": reason.shared_terms,
                        "shared_ids": reason.shared_ids,
                    }
                    for reason in cluster.overlap_reasons
                ],
            }
        )
    return records


def _competitor_clusters(
    prior_art: list[dict[str, Any]],
    source_ideas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ideas_by_id = {idea["id"]: idea for idea in source_ideas}
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in prior_art:
        buckets[_cluster_key(record)].append(record)

    clusters: list[dict[str, Any]] = []
    for index, (key, records) in enumerate(
        sorted(
            buckets.items(),
            key=lambda item: (-max(record["relevance_score"] for record in item[1]), item[0]),
        ),
        1,
    ):
        source_ids = sorted({record["source_idea_id"] for record in records})
        top = sorted(records, key=lambda item: (-item["relevance_score"], item["title"]))[:5]
        shared_terms = _shared_terms(records, [ideas_by_id[item] for item in source_ids if item in ideas_by_id])
        avg_score = sum(record["relevance_score"] for record in records) / len(records)
        clusters.append(
            {
                "id": f"competitor-cluster-{index}",
                "name": _cluster_name(key, top),
                "source": key,
                "competitor_count": len(records),
                "source_idea_ids": source_ids,
                "top_competitors": top,
                "overlap_score": round(avg_score, 3),
                "shared_terms": shared_terms,
                "positioning_summary": _positioning_summary(key, shared_terms, top),
                "suggested_response": _cluster_response(avg_score, len(records)),
            }
        )
    return clusters


def _differentiation_angles(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    similarity: list[dict[str, Any]],
    portfolio_overlap: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    angles: list[dict[str, Any]] = []
    source_ids = [idea["id"] for idea in source_ideas]
    if design_brief.get("specific_user") or design_brief.get("buyer"):
        angles.append(
            _angle(
                "specific-user-focus",
                "Specific user and buyer focus",
                _compact(
                    f"Anchor positioning on {design_brief.get('specific_user') or 'the target user'} "
                    f"and {design_brief.get('buyer') or 'the buyer'}."
                ),
                source_ids,
                ["design_brief.specific_user", "design_brief.buyer"],
            )
        )
    if design_brief.get("workflow_context"):
        angles.append(
            _angle(
                "workflow-integration",
                "Workflow integration",
                f"Lead with the persisted workflow context: {design_brief['workflow_context']}",
                source_ids,
                ["design_brief.workflow_context"],
            )
        )
    for scope in _string_list(design_brief.get("mvp_scope"))[:2]:
        angles.append(
            _angle(
                f"mvp-{_slug(scope)}",
                f"MVP wedge: {_short_title(scope)}",
                f"Use {scope} as a concrete wedge against broad incumbent tools.",
                source_ids,
                ["design_brief.mvp_scope"],
            )
        )

    weak_density = [record for record in evaluations if record["competitive_density_score"] < 6.0]
    if weak_density:
        angles.append(
            _angle(
                "competitive-density-mitigation",
                "Competitive-density mitigation",
                "Treat competition as a validation risk and require sharper proof of unmet workflow pain.",
                [record["source_idea_id"] for record in weak_density],
                ["evaluation.competitive_density"],
            )
        )
    if similarity or portfolio_overlap:
        angles.append(
            _angle(
                "portfolio-separation",
                "Portfolio separation",
                "Differentiate from nearby stored Max ideas by naming a narrower persona, trigger, and first milestone.",
                sorted({idea_id for record in similarity for idea_id in record["source_idea_ids"]} | set(source_ids)),
                ["similarity", "portfolio_overlap"],
            )
        )
    if clusters:
        angles.append(
            _angle(
                "competitor-gap",
                "Prior-art gap",
                "Position around gaps not covered by the strongest stored prior-art matches.",
                sorted({idea_id for cluster in clusters for idea_id in cluster["source_idea_ids"]}),
                ["prior_art_matches"],
            )
        )

    return _dedupe_angles(angles)[:6]


def _saturation_level(
    clusters: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    similarity: list[dict[str, Any]],
    portfolio_overlap: list[dict[str, Any]],
) -> dict[str, Any]:
    prior_art_score = min(sum(cluster["competitor_count"] for cluster in clusters) / 8.0, 1.0)
    relevance_score = max((cluster["overlap_score"] for cluster in clusters), default=0.0)
    density_scores = [record["competitive_density_score"] for record in evaluations]
    evaluation_pressure = 1.0 - (sum(density_scores) / len(density_scores) / 10.0) if density_scores else 0.0
    similarity_pressure = max((record["similarity_score"] for record in similarity), default=0.0)
    portfolio_pressure = max((record["overlap_score"] for record in portfolio_overlap), default=0.0)
    score = round(
        min(
            1.0,
            prior_art_score * 0.34
            + relevance_score * 0.28
            + evaluation_pressure * 0.18
            + similarity_pressure * 0.10
            + portfolio_pressure * 0.10,
        ),
        3,
    )
    if not clusters:
        level = "unknown"
    elif score >= 0.72:
        level = "high"
    elif score >= 0.42:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "score": score,
        "drivers": {
            "prior_art_density": round(prior_art_score, 3),
            "prior_art_relevance": round(relevance_score, 3),
            "evaluation_pressure": round(evaluation_pressure, 3),
            "similarity_pressure": round(similarity_pressure, 3),
            "portfolio_pressure": round(portfolio_pressure, 3),
        },
    }


def _recommended_positioning(
    design_brief: dict[str, Any],
    saturation: dict[str, Any],
    angles: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
) -> str:
    if not clusters:
        return (
            "Insufficient stored prior-art data to recommend a competitor-aware position. "
            "Run and persist prior-art checks for the design brief source ideas before handoff."
        )
    lead_angle = angles[0]["title"].lower() if angles else "workflow specificity"
    if saturation["level"] == "high":
        posture = "Enter with a narrow wedge"
    elif saturation["level"] == "medium":
        posture = "Position as a focused alternative"
    else:
        posture = "Position around category creation"
    return _compact(
        f"{posture} for {design_brief.get('specific_user') or 'the target user'}, "
        f"using {lead_angle} and the first MVP milestone as the proof point."
    )


def _cluster_key(record: dict[str, Any]) -> str:
    source = str(record.get("source") or "unknown").lower()
    if source in {"github", "npm", "pypi", "product_hunt"}:
        return source
    return "other"


def _cluster_name(key: str, top: list[dict[str, Any]]) -> str:
    labels = {
        "github": "Open-source repository competitors",
        "npm": "JavaScript package competitors",
        "pypi": "Python package competitors",
        "product_hunt": "Product competitors",
        "other": "Stored prior-art competitors",
    }
    if key in labels:
        return labels[key]
    return _short_title(top[0]["title"]) if top else "Stored prior-art competitors"


def _shared_terms(records: list[dict[str, Any]], ideas: list[dict[str, Any]]) -> list[str]:
    competitor_counts = _token_counts(
        " ".join(
            f"{record.get('title', '')} {record.get('description', '')} {record.get('search_query', '')}"
            for record in records
        )
    )
    idea_counts = _token_counts(
        " ".join(
            f"{idea.get('title', '')} {idea.get('problem', '')} {idea.get('solution', '')} "
            f"{idea.get('workflow_context', '')}"
            for idea in ideas
        )
    )
    shared = set(competitor_counts) & set(idea_counts)
    return sorted(shared, key=lambda token: (-(competitor_counts[token] + idea_counts[token]), token))[:12]


def _positioning_summary(key: str, shared_terms: list[str], top: list[dict[str, Any]]) -> str:
    competitor = top[0]["title"] if top else "stored competitors"
    if shared_terms:
        return f"{competitor} overlaps on {', '.join(shared_terms[:5])}."
    return f"{competitor} is the strongest stored {key} prior-art match."


def _cluster_response(avg_score: float, count: int) -> str:
    if avg_score >= 0.82 or count >= 4:
        return "Differentiate sharply before build commitment."
    if avg_score >= 0.65 or count >= 2:
        return "Name a focused wedge and validate switching pain."
    return "Monitor as weak prior art while validating the workflow."


def _angle(
    angle_id: str,
    title: str,
    rationale: str,
    source_idea_ids: list[str],
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "id": angle_id,
        "title": title,
        "rationale": _compact(rationale),
        "source_idea_ids": sorted(dict.fromkeys(source_idea_ids)),
        "evidence": evidence,
    }


def _dedupe_angles(angles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for angle in angles:
        deduped.setdefault(angle["id"], angle)
    return list(deduped.values())


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _token_counts(text: str) -> Counter[str]:
    return Counter(
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    )


def _short_title(text: str, *, max_chars: int = 56) -> str:
    compact = _compact(text)
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _slug(text: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", text.lower()))[:36].strip("-")
    return slug or "scope"


def _compact(text: str) -> str:
    return " ".join(str(text).split())


_STOPWORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "that",
    "the",
    "this",
    "with",
    "without",
    "users",
    "user",
    "teams",
    "team",
    "tool",
    "tools",
    "api",
    "app",
    "service",
    "platform",
}
