"""Portfolio theme saturation report for persisted design work."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from max.store.db import Store


SCHEMA_VERSION = "max.portfolio_theme_saturation.v1"
KIND = "max.portfolio_theme_saturation"
DEFAULT_LIMIT = 10_000
DEFAULT_RECENT_VALIDATION_DAYS = 90
DEFAULT_CROWDED_COUNT = 3
DEFAULT_THIN_EVIDENCE_COUNT = 2


def build_portfolio_theme_saturation_report(
    store: Store,
    *,
    domain: str | Iterable[str] | None = None,
    min_count: int = 1,
    limit: int = DEFAULT_LIMIT,
    crowded_count: int = DEFAULT_CROWDED_COUNT,
    thin_evidence_count: int = DEFAULT_THIN_EVIDENCE_COUNT,
    recent_validation_days: int = DEFAULT_RECENT_VALIDATION_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready theme saturation report from persisted portfolio records."""

    if min_count < 1:
        raise ValueError("min_count must be at least 1")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    domains = _filter_values(domain)
    if domains and len(domains) == 1:
        domain_filter = next(iter(domains))
        units = store.get_buildable_units(limit=limit, domain=domain_filter)
        briefs = store.get_design_briefs(limit=limit, domain=domain_filter)
        experiments = store.query_validation_experiments(domain=domain_filter)
    else:
        units = store.get_buildable_units(limit=limit)
        briefs = store.get_design_briefs(limit=limit)
        experiments = store.query_validation_experiments()

    return build_portfolio_theme_saturation_from_records(
        buildable_units=units,
        design_briefs=briefs,
        validation_experiments=experiments,
        domain=domains,
        min_count=min_count,
        crowded_count=crowded_count,
        thin_evidence_count=thin_evidence_count,
        recent_validation_days=recent_validation_days,
        generated_at=generated_at,
    )


def build_portfolio_theme_saturation_from_records(
    *,
    buildable_units: Iterable[Any],
    design_briefs: Iterable[Mapping[str, Any]],
    validation_experiments: Iterable[Mapping[str, Any]] = (),
    domain: set[str] | str | Iterable[str] | None = None,
    min_count: int = 1,
    crowded_count: int = DEFAULT_CROWDED_COUNT,
    thin_evidence_count: int = DEFAULT_THIN_EVIDENCE_COUNT,
    recent_validation_days: int = DEFAULT_RECENT_VALIDATION_DAYS,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a theme saturation report from already-loaded portfolio records."""

    if min_count < 1:
        raise ValueError("min_count must be at least 1")

    generated = generated_at or datetime.now(UTC).isoformat()
    generated_dt = _parse_datetime(generated) or datetime.now(UTC)
    recent_cutoff = generated_dt - timedelta(days=max(recent_validation_days, 0))
    domain_filter = _filter_values(domain)

    records = [
        record
        for record in (
            [_unit_record(unit) for unit in buildable_units]
            + [_brief_record(brief) for brief in design_briefs]
        )
        if _matches_filter(record["domain"], domain_filter)
    ]
    validation_by_idea = _validation_by_idea(validation_experiments, recent_cutoff=recent_cutoff)
    total_records = len(records)

    buckets = _theme_buckets(
        records,
        validation_by_idea=validation_by_idea,
        total_records=total_records,
        min_count=min_count,
        crowded_count=crowded_count,
        thin_evidence_count=thin_evidence_count,
    )

    flags = _flags(buckets)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "generated_at": generated,
        "filters": {
            "domain": sorted(domain_filter) if domain_filter else None,
            "min_count": min_count,
        },
        "summary": {
            "total_items": total_records,
            "buildable_unit_count": sum(1 for record in records if record["source_type"] == "buildable_unit"),
            "design_brief_count": sum(1 for record in records if record["source_type"] == "design_brief"),
            "theme_bucket_count": len(buckets),
            "crowded_theme_count": len(flags["crowded"]),
            "thinly_evidenced_theme_count": len(flags["thinly_evidenced"]),
            "missing_recent_validation_count": len(flags["missing_recent_validation"]),
        },
        "theme_buckets": buckets,
        "saturation_flags": flags,
        "recommendations": _recommendations(buckets, total_records, min_count),
    }


def _theme_buckets(
    records: list[dict[str, Any]],
    *,
    validation_by_idea: dict[str, str],
    total_records: int,
    min_count: int,
    crowded_count: int,
    thin_evidence_count: int,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault((record["domain"], record["theme"]), []).append(record)

    buckets: list[dict[str, Any]] = []
    for (domain, theme), members in grouped.items():
        if len(members) < min_count:
            continue
        evidence_ids = _dedupe(
            evidence_id
            for member in members
            for evidence_id in member["evidence_ids"]
        )
        source_idea_ids = _dedupe(
            source_id
            for member in members
            for source_id in member["source_idea_ids"]
        )
        recent_validation_ids = _dedupe(
            idea_id for idea_id in source_idea_ids if idea_id in validation_by_idea
        )
        readiness_counts = Counter(member["readiness_band"] for member in members)
        category_counts = Counter(member["category"] for member in members)
        source_type_counts = Counter(member["source_type"] for member in members)
        source_idea_count = len(source_idea_ids)
        evidence_count = len(evidence_ids)
        item_count = len(members)
        portfolio_share = round(item_count / total_records, 3) if total_records else 0.0
        evidence_concentration = round(evidence_count / max(item_count, 1), 3)
        saturation_score = _saturation_score(
            item_count=item_count,
            portfolio_share=portfolio_share,
            evidence_count=evidence_count,
            source_idea_count=source_idea_count,
            recent_validation_count=len(recent_validation_ids),
            readiness_counts=readiness_counts,
            crowded_count=crowded_count,
        )
        flags = _bucket_flags(
            item_count=item_count,
            evidence_count=evidence_count,
            recent_validation_count=len(recent_validation_ids),
            crowded_count=crowded_count,
            thin_evidence_count=thin_evidence_count,
        )
        bucket_id = _bucket_id(domain, theme)
        buckets.append(
            {
                "id": bucket_id,
                "domain": domain,
                "theme": theme,
                "categories": _counter_rows(category_counts, "category"),
                "readiness_bands": _counter_rows(readiness_counts, "readiness_band"),
                "source_idea_count": source_idea_count,
                "source_idea_ids": source_idea_ids,
                "item_count": item_count,
                "buildable_unit_count": source_type_counts.get("buildable_unit", 0),
                "design_brief_count": source_type_counts.get("design_brief", 0),
                "evidence_count": evidence_count,
                "evidence_concentration": evidence_concentration,
                "recent_validation_count": len(recent_validation_ids),
                "recent_validation_idea_ids": recent_validation_ids,
                "saturation_score": saturation_score,
                "flags": flags,
                "representative_items": _representative_items(members),
            }
        )

    return sorted(
        buckets,
        key=lambda bucket: (
            -bucket["saturation_score"],
            -bucket["evidence_concentration"],
            -bucket["item_count"],
            bucket["domain"],
            bucket["theme"],
        ),
    )


def _unit_record(unit: Any) -> dict[str, Any]:
    unit_id = _clean(_get(unit, "id") or _get(unit, "buildable_unit_id") or _get(unit, "idea_id"))
    category = _clean(_get(unit, "category")) or "uncategorized"
    source_idea_ids = _dedupe([unit_id, *_list(_get(unit, "source_idea_ids"))])
    evidence_ids = _dedupe(
        [
            *_list(_get(unit, "evidence_signals")),
            *_list(_get(unit, "inspiring_insights")),
            *_list(_get(unit, "source_idea_ids")),
        ]
    )
    readiness_score = _unit_readiness_score(unit)
    return {
        "id": unit_id,
        "title": _clean(_get(unit, "title")) or unit_id,
        "source_type": "buildable_unit",
        "domain": _clean(_get(unit, "domain")) or "unspecified",
        "theme": _theme_value(_get(unit, "theme") or category),
        "category": category,
        "readiness_score": readiness_score,
        "readiness_band": _readiness_band(readiness_score),
        "source_idea_ids": source_idea_ids,
        "evidence_ids": evidence_ids,
        "created_at": _clean(_get(unit, "created_at")),
        "updated_at": _clean(_get(unit, "updated_at")),
    }


def _brief_record(brief: Mapping[str, Any]) -> dict[str, Any]:
    source_idea_ids = _dedupe(_list(brief.get("source_idea_ids")))
    evidence_ids = _dedupe(
        [
            *source_idea_ids,
            *[
                _clean(source.get("idea_id"))
                for source in _list(brief.get("sources"))
                if isinstance(source, Mapping)
            ],
        ]
    )
    readiness_score = _float(brief.get("readiness_score"))
    return {
        "id": _clean(brief.get("id")),
        "title": _clean(brief.get("title")),
        "source_type": "design_brief",
        "domain": _clean(brief.get("domain")) or "unspecified",
        "theme": _theme_value(brief.get("theme")),
        "category": "design_brief",
        "readiness_score": readiness_score,
        "readiness_band": _readiness_band(readiness_score),
        "source_idea_ids": source_idea_ids,
        "evidence_ids": evidence_ids,
        "created_at": _clean(brief.get("created_at")),
        "updated_at": _clean(brief.get("updated_at")),
    }


def _saturation_score(
    *,
    item_count: int,
    portfolio_share: float,
    evidence_count: int,
    source_idea_count: int,
    recent_validation_count: int,
    readiness_counts: Counter[str],
    crowded_count: int,
) -> float:
    crowding = min(item_count / max(crowded_count, 1), 1.0) * 0.42
    share = min(portfolio_share, 1.0) * 0.28
    readiness = (
        (readiness_counts.get("high", 0) * 1.0 + readiness_counts.get("medium", 0) * 0.55)
        / max(item_count, 1)
    ) * 0.14
    source_pressure = min(source_idea_count / max(item_count * 2, 1), 1.0) * 0.08
    evidence_pressure = min(evidence_count / max(item_count * 3, 1), 1.0) * 0.05
    validation_gap = 0.03 if recent_validation_count == 0 else 0.0
    return round(min(crowding + share + readiness + source_pressure + evidence_pressure + validation_gap, 1.0), 3)


def _bucket_flags(
    *,
    item_count: int,
    evidence_count: int,
    recent_validation_count: int,
    crowded_count: int,
    thin_evidence_count: int,
) -> list[str]:
    flags: list[str] = []
    if item_count >= crowded_count:
        flags.append("crowded")
    if evidence_count < thin_evidence_count:
        flags.append("thinly_evidenced")
    if recent_validation_count == 0:
        flags.append("missing_recent_validation")
    return flags


def _flags(buckets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result = {"crowded": [], "thinly_evidenced": [], "missing_recent_validation": []}
    for bucket in buckets:
        for flag in result:
            if flag in bucket["flags"]:
                result[flag].append(
                    {
                        "theme_bucket_id": bucket["id"],
                        "domain": bucket["domain"],
                        "theme": bucket["theme"],
                        "saturation_score": bucket["saturation_score"],
                        "item_count": bucket["item_count"],
                    }
                )
    return result


def _recommendations(
    buckets: list[dict[str, Any]],
    total_records: int,
    min_count: int,
) -> list[dict[str, str]]:
    if total_records == 0:
        return [
            {
                "priority": "high",
                "action": "Generate or import design briefs and buildable units before assessing theme saturation.",
                "rationale": "No persisted portfolio items matched the selected filters.",
            }
        ]
    if not buckets:
        return [
            {
                "priority": "high",
                "action": f"Lower min_count below {min_count} or add more portfolio items before making saturation decisions.",
                "rationale": "The matching portfolio is too sparse to form reportable theme buckets.",
            },
            {
                "priority": "medium",
                "action": "Prioritize first validation evidence for the newest themes rather than generating more adjacent ideas.",
                "rationale": "Sparse portfolios need evidence breadth before saturation scoring becomes useful.",
            },
        ]

    recommendations: list[dict[str, str]] = []
    crowded = [bucket for bucket in buckets if "crowded" in bucket["flags"]]
    thin = [bucket for bucket in buckets if "thinly_evidenced" in bucket["flags"]]
    missing_validation = [
        bucket for bucket in buckets if "missing_recent_validation" in bucket["flags"]
    ]
    underrepresented = [
        bucket
        for bucket in sorted(buckets, key=lambda item: (item["item_count"], item["theme"]))
        if bucket["item_count"] == 1 and "thinly_evidenced" not in bucket["flags"]
    ]

    if crowded:
        top = crowded[0]
        recommendations.append(
            {
                "priority": "high",
                "action": f"Pause new ideas in {top['domain']} / {top['theme']} and consolidate or differentiate the existing bucket.",
                "rationale": f"{top['item_count']} persisted items produce the highest saturation score ({top['saturation_score']}).",
            }
        )
    if thin:
        top = thin[0]
        recommendations.append(
            {
                "priority": "high",
                "action": f"Add source evidence before advancing {top['domain']} / {top['theme']}.",
                "rationale": f"The bucket has {top['evidence_count']} distinct evidence item(s).",
            }
        )
    if missing_validation:
        top = missing_validation[0]
        recommendations.append(
            {
                "priority": "medium",
                "action": f"Run or attach a recent validation experiment for {top['domain']} / {top['theme']}.",
                "rationale": "No source idea in the bucket has recent completed validation evidence.",
            }
        )
    if underrepresented:
        top = underrepresented[0]
        recommendations.append(
            {
                "priority": "medium",
                "action": f"Consider one focused expansion in underrepresented theme {top['domain']} / {top['theme']}.",
                "rationale": "The bucket has evidence but only one persisted item.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "priority": "low",
                "action": "Keep generation balanced and revisit saturation after the next validation cycle.",
                "rationale": "No crowded, thinly evidenced, or stale-validation theme flags were detected.",
            }
        )
    return recommendations


def _validation_by_idea(
    experiments: Iterable[Mapping[str, Any]],
    *,
    recent_cutoff: datetime,
) -> dict[str, str]:
    recent: dict[str, str] = {}
    for experiment in experiments:
        status = _clean(experiment.get("status"))
        if status != "completed":
            continue
        idea_id = _clean(experiment.get("idea_id"))
        if not idea_id:
            continue
        timestamp = _parse_datetime(
            experiment.get("completed_at")
            or experiment.get("updated_at")
            or experiment.get("created_at")
        )
        if timestamp is None or timestamp < recent_cutoff:
            continue
        recent[idea_id] = _clean(experiment.get("id"))
    return recent


def _unit_readiness_score(unit: Any) -> float:
    quality = _float(_get(unit, "quality_score"))
    usefulness = _float(_get(unit, "usefulness_score"))
    novelty = _float(_get(unit, "novelty_score"))
    score = max(quality, usefulness, novelty) * 10.0
    status = _clean(_get(unit, "status"))
    if status == "published":
        score = max(score, 85.0)
    elif status == "approved":
        score = max(score, 75.0)
    elif status == "evaluated":
        score = max(score, 55.0)
    elif status == "rejected":
        score = min(score, 35.0)
    return round(min(max(score, 0.0), 100.0), 1)


def _readiness_band(score: float) -> str:
    if score >= 70.0:
        return "high"
    if score >= 40.0:
        return "medium"
    return "low"


def _representative_items(members: list[dict[str, Any]]) -> list[dict[str, str]]:
    ranked = sorted(
        members,
        key=lambda member: (
            -member["readiness_score"],
            member["source_type"],
            member["id"],
        ),
    )
    return [
        {
            "id": member["id"],
            "title": member["title"],
            "source_type": member["source_type"],
            "readiness_band": member["readiness_band"],
        }
        for member in ranked[:5]
    ]


def _counter_rows(counts: Counter[str], key: str) -> list[dict[str, Any]]:
    return [
        {key: value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _theme_value(value: Any) -> str:
    return _clean(value).lower().replace(" ", "-") or "uncategorized"


def _bucket_id(domain: str, theme: str) -> str:
    return f"{domain}:{theme}".lower().replace(" ", "-")


def _matches_filter(value: str, allowed: set[str] | None) -> bool:
    return allowed is None or value in allowed


def _filter_values(value: str | Iterable[str] | set[str] | None) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = _clean(value)
        return {cleaned} if cleaned else None
    values = {_clean(item) for item in value}
    values.discard("")
    return values or None


def _dedupe(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _get(item: Any, key: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(key)
    return getattr(item, key, None)


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple | set):
        return list(value)
    return [value]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _parse_datetime(value: Any) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
