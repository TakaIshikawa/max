"""Deterministic pricing strategy reports for persisted design briefs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from io import StringIO
from typing import Any, Iterable

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.pricing_strategy.v1"
CSV_COLUMNS: tuple[str, ...] = (
    "section",
    "item_id",
    "name",
    "package",
    "monthly_min_usd",
    "monthly_max_usd",
    "detail",
    "rationale",
    "source",
)


def build_design_brief_pricing_strategy(
    store: Store,
    brief_id: str,
) -> dict[str, Any] | None:
    """Build a deterministic pricing strategy from stored design brief lineage."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    evidence = _evidence_references(store, source_ideas)
    evaluations = _evaluation_records(store, source_ideas)
    market_signals = _market_signal_counts(evidence)
    competitive_hints = _competitive_hints(store, source_ideas)
    value_metric = _value_metric(design_brief, source_ideas)
    price_bands = _price_bands(design_brief, market_signals, evaluations, competitive_hints)
    packages = _packages(design_brief, source_ideas, price_bands, value_metric)
    confidence = _confidence(design_brief, evidence, evaluations, competitive_hints)
    validation_questions = _validation_questions(design_brief, value_metric, price_bands)
    objections = _objections(design_brief, market_signals, competitive_hints)

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
            "readiness_score": float(design_brief.get("readiness_score") or 0.0),
            "design_status": design_brief.get("design_status", ""),
            "buyer": _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer"),
            "specific_user": _first_text(
                design_brief.get("specific_user"),
                _field_values(source_ideas, "specific_user"),
                "target user",
            ),
            "workflow_context": _first_text(
                design_brief.get("workflow_context"),
                _field_values(source_ideas, "workflow_context"),
                "target workflow",
            ),
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": [idea["id"] for idea in source_ideas]
            or list(design_brief.get("source_idea_ids") or []),
        },
        "market_signals": market_signals,
        "competitive_landscape_hints": competitive_hints,
        "packages": packages,
        "price_bands": price_bands,
        "value_metric": value_metric,
        "free_trial_usage_limits": _free_trial_usage_limits(value_metric, confidence),
        "objections": objections,
        "validation_questions": validation_questions,
        "key_assumptions": _key_assumptions(design_brief, value_metric, price_bands, objections),
        "risks": _pricing_risks(design_brief, market_signals, competitive_hints),
        "recommended_experiments": _recommended_experiments(validation_questions),
        "confidence": confidence,
        "evidence_references": evidence,
        "source_ideas": source_ideas,
    }


def render_design_brief_pricing_strategy(report: dict[str, Any], fmt: str = "json") -> str:
    """Render a pricing strategy as JSON, Markdown, or CSV."""
    if fmt == "json":
        return json.dumps(report, indent=2, sort_keys=True) + "\n"
    if fmt == "csv":
        return _render_csv(report)
    if fmt != "markdown":
        raise ValueError(f"Unsupported pricing strategy format: {fmt}")

    brief = report["design_brief"]
    confidence = report["confidence"]
    lines = [
        f"# Pricing Strategy: {brief['title']}",
        "",
        f"Schema: `{report['schema_version']}`",
        f"Design brief: `{brief['id']}`",
        f"Buyer: {brief['buyer']}",
        f"User: {brief['specific_user']}",
        f"Confidence: {confidence['level']} ({confidence['score']:.2f})",
        "",
        "## Recommended Packaging",
        "",
    ]
    for package in report["packages"]:
        lines.extend(
            [
                f"### {package['name']}",
                "",
                f"- **Target customer**: {package['target_customer']}",
                f"- **Price band**: {package['price_band_label']}",
                f"- **Value anchor**: {package['value_anchor']}",
                f"- **Included limits**: {package['included_limits']}",
                f"- **Upgrade trigger**: {package['upgrade_trigger']}",
                "",
            ]
        )

    lines.extend(["## Initial Price Bands", ""])
    for band in report["price_bands"]:
        lines.extend(
            [
                f"- **{band['package']}**: ${band['monthly_min_usd']}-${band['monthly_max_usd']}/month",
                f"  - Rationale: {band['rationale']}",
            ]
        )

    metric = report["value_metric"]
    lines.extend(
        [
            "",
            "## Value Metric",
            "",
            f"- **Metric**: {metric['metric']}",
            f"- **Unit**: {metric['unit']}",
            f"- **Rationale**: {metric['rationale']}",
            f"- **Expansion trigger**: {metric['expansion_trigger']}",
            "",
            "## Free Trial And Usage Limits",
            "",
        ]
    )
    for limit in report["free_trial_usage_limits"]:
        lines.append(f"- {limit}")

    lines.extend(["", "## Buyer Objections", ""])
    for objection in report["objections"]:
        lines.append(f"- **{objection['theme']}**: {objection['response']}")

    lines.extend(["", "## Validation Questions", ""])
    lines.extend(f"- {question}" for question in report["validation_questions"])

    lines.extend(["", "## Evidence References", ""])
    if report["evidence_references"]:
        for reference in report["evidence_references"]:
            line = f"- `{reference['id']}` [{reference['source_type']}] {reference['title']}"
            if reference.get("url"):
                line += f" - {reference['url']}"
            lines.append(line)
    else:
        lines.append("- No stored evidence references are linked to the brief lineage.")
    return "\n".join(lines).rstrip() + "\n"


def pricing_strategy_filename(design_brief: dict[str, Any], *, fmt: str = "markdown") -> str:
    extension = {"csv": "csv", "json": "json"}.get(fmt, "md")
    return f"{_filename_part(str(design_brief['id']))}-pricing-strategy.{extension}"


def _render_csv(report: dict[str, Any]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in _csv_rows(report):
        writer.writerow(row)
    return output.getvalue()


def _csv_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    band_by_package = {
        str(band.get("package") or ""): band for band in report.get("price_bands", []) if band
    }
    for index, package in enumerate(report.get("packages") or [], start=1):
        name = str(package.get("name") or "")
        band = band_by_package.get(name, {})
        rows.append(
            _csv_row(
                section="tier",
                item_id=f"tier-{index}",
                name=name,
                package=name,
                monthly_min_usd=band.get("monthly_min_usd", ""),
                monthly_max_usd=band.get("monthly_max_usd", ""),
                detail=_csv_join(
                    [
                        package.get("target_customer"),
                        package.get("included_limits"),
                        package.get("upgrade_trigger"),
                    ]
                ),
                rationale=_csv_join([package.get("value_anchor"), band.get("rationale")]),
                source="packages",
            )
        )

    for index, assumption in enumerate(report.get("key_assumptions") or [], start=1):
        rows.append(
            _csv_row(
                section="assumption",
                item_id=str(assumption.get("id") or f"assumption-{index}"),
                name=str(assumption.get("name") or assumption.get("theme") or ""),
                detail=str(assumption.get("assumption") or assumption.get("detail") or ""),
                rationale=str(assumption.get("rationale") or ""),
                source=str(assumption.get("source") or "key_assumptions"),
            )
        )

    for index, risk in enumerate(report.get("risks") or [], start=1):
        rows.append(
            _csv_row(
                section="risk",
                item_id=str(risk.get("id") or f"risk-{index}"),
                name=str(risk.get("risk") or risk.get("theme") or ""),
                detail=str(risk.get("mitigation") or risk.get("detail") or ""),
                rationale=str(risk.get("rationale") or ""),
                source=str(risk.get("source") or "risks"),
            )
        )

    for index, experiment in enumerate(report.get("recommended_experiments") or [], start=1):
        rows.append(
            _csv_row(
                section="experiment",
                item_id=str(experiment.get("id") or f"experiment-{index}"),
                name=str(experiment.get("name") or experiment.get("question") or ""),
                detail=str(experiment.get("experiment") or experiment.get("detail") or ""),
                rationale=str(experiment.get("success_metric") or experiment.get("rationale") or ""),
                source=str(experiment.get("source") or "recommended_experiments"),
            )
        )
    return rows


def _csv_row(**values: Any) -> dict[str, Any]:
    return {column: values.get(column, "") for column in CSV_COLUMNS}


def _csv_join(values: Iterable[Any], *, separator: str = "; ") -> str:
    return separator.join(clean for value in values if (clean := _clean(value)))


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
        data["rank"] = relationship.get("rank", 0 if data["role"] == "lead" else None)
        ideas.append(data)
    return ideas


def _evidence_references(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signal_ids: set[str] = set()
    insight_ids: set[str] = set()
    for idea in source_ideas:
        signal_ids.update(_string_list(idea.get("evidence_signals")))
        insight_ids.update(_string_list(idea.get("inspiring_insights")))

    for insight_id in sorted(insight_ids):
        insight = store.get_insight(insight_id)
        if insight:
            signal_ids.update(_string_list(getattr(insight, "evidence", [])))

    references: list[dict[str, Any]] = []
    for signal_id in sorted(signal_ids):
        signal = store.get_signal(signal_id)
        if not signal:
            continue
        references.append(
            {
                "id": signal.id,
                "source_type": _source_type(signal),
                "source_adapter": str(getattr(signal, "source_adapter", "") or "unknown"),
                "title": signal.title,
                "url": signal.url,
                "credibility": round(float(signal.credibility or 0.0), 2),
                "tags": list(signal.tags),
                "signal_role": str(getattr(signal, "signal_role", "") or ""),
            }
        )
    references.sort(key=lambda item: item["id"])
    return references


def _evaluation_records(store: Store, source_ideas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idea in source_ideas:
        idea_id = str(idea.get("id") or "")
        if not idea_id:
            continue
        evaluation = store.get_evaluation(idea_id)
        if not evaluation:
            continue
        records.append(
            {
                "source_idea_id": idea_id,
                "overall_score": round(float(evaluation.overall_score), 2),
                "addressable_scale": round(float(evaluation.addressable_scale.value), 2),
                "pain_severity": round(float(evaluation.pain_severity.value), 2),
                "competitive_density": round(float(evaluation.competitive_density.value), 2),
                "recommendation": evaluation.recommendation,
            }
        )
    records.sort(key=lambda item: item["source_idea_id"])
    return records


def _market_signal_counts(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    by_type = Counter(reference["source_type"] for reference in evidence)
    by_role = Counter(reference.get("signal_role") or "unknown" for reference in evidence)
    return {
        "total": len(evidence),
        "survey": by_type.get("survey", 0),
        "funding": by_type.get("funding", 0),
        "forum": by_type.get("forum", 0),
        "security": by_type.get("security", 0),
        "by_source_type": dict(sorted(by_type.items())),
        "by_signal_role": dict(sorted(by_role.items())),
    }


def _competitive_hints(store: Store, source_ideas: list[dict[str, Any]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for idea in source_ideas:
        idea_id = str(idea.get("id") or "")
        if not idea_id:
            continue
        for match in store.get_prior_art_matches(idea_id):
            matches.append(
                {
                    "source_idea_id": idea_id,
                    "source": match.get("source", ""),
                    "title": match.get("title", ""),
                    "url": match.get("url", ""),
                    "relevance_score": round(float(match.get("relevance_score") or 0.0), 2),
                }
            )
    matches.sort(key=lambda item: (-item["relevance_score"], item["source"], item["title"]))
    density = "unknown"
    if len(matches) >= 4:
        density = "high"
    elif matches:
        density = "moderate"
    return {
        "prior_art_count": len(matches),
        "density": density,
        "top_references": matches[:5],
    }


def _value_metric(design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]) -> dict[str, str]:
    text = " ".join(
        [
            str(design_brief.get("merged_product_concept") or ""),
            str(design_brief.get("workflow_context") or ""),
            " ".join(_string_list(design_brief.get("mvp_scope"))),
            " ".join(str(idea.get("solution") or "") for idea in source_ideas),
        ]
    ).lower()
    if any(term in text for term in ("api", "ci", "release", "deployment", "workflow", "run")):
        return {
            "metric": "completed workflow runs",
            "unit": "run",
            "rationale": "The brief frames value around repeated workflow execution and review throughput.",
            "expansion_trigger": "Move customers to higher packages as monthly workflow runs or retained history grows.",
        }
    if any(term in text for term in ("seat", "team", "collaboration", "reviewer", "operator")):
        return {
            "metric": "active team seats",
            "unit": "seat",
            "rationale": "The brief points to a team workflow where value expands with active participants.",
            "expansion_trigger": "Move customers to higher packages as additional users join the buying workflow.",
        }
    return {
        "metric": "active accounts",
        "unit": "account",
        "rationale": "The persisted brief does not provide a more specific metered usage signal.",
        "expansion_trigger": "Move customers to higher packages when account volume, integrations, or reporting needs grow.",
    }


def _price_bands(
    design_brief: dict[str, Any],
    market_signals: dict[str, Any],
    evaluations: list[dict[str, Any]],
    competitive_hints: dict[str, Any],
) -> list[dict[str, Any]]:
    readiness = float(design_brief.get("readiness_score") or 0.0)
    avg_eval = _average(item["overall_score"] for item in evaluations) or readiness
    signal_boost = 1 if market_signals["funding"] or market_signals["survey"] else 0
    density_penalty = -1 if competitive_hints["density"] == "high" else 0
    tier = max(0, min(2, int((readiness + avg_eval) >= 150) + signal_boost + density_penalty))
    bands = [
        [(29, 79), (149, 399), (799, 1999)],
        [(49, 99), (249, 599), (1200, 3000)],
        [(99, 199), (499, 999), (2500, 6000)],
    ][tier]
    packages = ("Starter", "Team", "Business")
    rationales = (
        "Low-friction entry package for first proof-of-value pilots.",
        "Default paid package for the named buyer and recurring workflow.",
        "Expansion package for cross-team usage, governance, and reporting.",
    )
    return [
        {
            "package": package,
            "monthly_min_usd": low,
            "monthly_max_usd": high,
            "rationale": rationale,
        }
        for package, (low, high), rationale in zip(packages, bands, rationales, strict=True)
    ]


def _packages(
    design_brief: dict[str, Any],
    source_ideas: list[dict[str, Any]],
    price_bands: list[dict[str, Any]],
    value_metric: dict[str, str],
) -> list[dict[str, Any]]:
    buyer = _first_text(design_brief.get("buyer"), _field_values(source_ideas, "buyer"), "target buyer")
    user = _first_text(design_brief.get("specific_user"), _field_values(source_ideas, "specific_user"), "target user")
    scope = _string_list(design_brief.get("mvp_scope")) or ["Core workflow", "Baseline reporting"]
    return [
        {
            "name": "Starter",
            "target_customer": f"One {user} team validating the workflow",
            "price_band_label": _band_label(price_bands[0]),
            "value_anchor": scope[0],
            "included_limits": f"Up to 100 {value_metric['unit']}s/month and 30 days of history",
            "upgrade_trigger": f"More than 100 {value_metric['unit']}s/month or additional teams",
        },
        {
            "name": "Team",
            "target_customer": f"{buyer} rolling the workflow into a recurring team process",
            "price_band_label": _band_label(price_bands[1]),
            "value_anchor": scope[min(1, len(scope) - 1)],
            "included_limits": f"Up to 1,000 {value_metric['unit']}s/month, integrations, and shared reporting",
            "upgrade_trigger": "Cross-functional reporting, audit needs, or more than one buying team",
        },
        {
            "name": "Business",
            "target_customer": f"{buyer} standardizing the workflow across multiple teams",
            "price_band_label": _band_label(price_bands[2]),
            "value_anchor": "Governance, priority support, and executive reporting",
            "included_limits": f"Up to 10,000 {value_metric['unit']}s/month with negotiated overages",
            "upgrade_trigger": "Security review, procurement requirements, or multi-team rollout",
        },
    ]


def _free_trial_usage_limits(value_metric: dict[str, str], confidence: dict[str, Any]) -> list[str]:
    base = 25 if confidence["level"] == "low" else 50
    return [
        "14-day trial with no credit card for discovery-led pilots.",
        f"Limit trial usage to {base} {value_metric['unit']}s and one shared workspace.",
        "Require sales or founder approval before extending trials beyond one additional cycle.",
    ]


def _objections(
    design_brief: dict[str, Any],
    market_signals: dict[str, Any],
    competitive_hints: dict[str, Any],
) -> list[dict[str, str]]:
    objections = [
        {
            "theme": "Budget ownership",
            "response": (
                f"Anchor pricing to the named buyer ({design_brief.get('buyer') or 'target buyer'}) and validate "
                "whether the workflow maps to an existing budget line."
            ),
        },
        {
            "theme": "Proof of value",
            "response": "Use the trial to measure saved time, avoided risk, or conversion before annual commitments.",
        },
    ]
    if market_signals["funding"] == 0:
        objections.append(
            {
                "theme": "Willingness to pay",
                "response": "No funding or budget signal is linked yet, so test paid pilot conversion before discounting.",
            }
        )
    if competitive_hints["prior_art_count"]:
        objections.append(
            {
                "theme": "Competitive alternatives",
                "response": "Differentiate on the brief-specific workflow and report outcome, not generic feature parity.",
            }
        )
    return objections


def _validation_questions(
    design_brief: dict[str, Any],
    value_metric: dict[str, str],
    price_bands: list[dict[str, Any]],
) -> list[str]:
    team_band = price_bands[1]
    return [
        f"Will {design_brief.get('buyer') or 'the buyer'} pay ${team_band['monthly_min_usd']}-${team_band['monthly_max_usd']}/month for the Team package after a pilot?",
        f"Does {value_metric['metric']} match how customers perceive value and forecast usage?",
        "Which trial limit creates urgency without blocking a fair proof of value?",
        "What procurement, security, or stakeholder review is required before the Business package can close?",
        "Which customer segment shows the least price sensitivity during discovery calls?",
    ]


def _key_assumptions(
    design_brief: dict[str, Any],
    value_metric: dict[str, str],
    price_bands: list[dict[str, Any]],
    objections: list[dict[str, str]],
) -> list[dict[str, str]]:
    team_band = price_bands[1] if len(price_bands) > 1 else {}
    assumptions = [
        {
            "id": "assumption-value-metric",
            "name": "Value metric fit",
            "assumption": f"Customers will accept {value_metric['metric']} as the primary expansion metric.",
            "rationale": value_metric["rationale"],
            "source": "value_metric",
        },
        {
            "id": "assumption-team-band",
            "name": "Team package willingness to pay",
            "assumption": (
                f"{design_brief.get('buyer') or 'The buyer'} will consider "
                f"${team_band.get('monthly_min_usd', '')}-${team_band.get('monthly_max_usd', '')}/month "
                "after a credible pilot."
            ),
            "rationale": str(team_band.get("rationale") or ""),
            "source": "price_bands",
        },
    ]
    for index, objection in enumerate(objections[:2], start=1):
        assumptions.append(
            {
                "id": f"assumption-objection-{index}",
                "name": objection["theme"],
                "assumption": objection["response"],
                "rationale": "Buyer objection handling depends on this assumption being true in discovery.",
                "source": "objections",
            }
        )
    return assumptions


def _pricing_risks(
    design_brief: dict[str, Any],
    market_signals: dict[str, Any],
    competitive_hints: dict[str, Any],
) -> list[dict[str, str]]:
    risks = [
        {
            "id": f"risk-{index}",
            "risk": risk,
            "mitigation": "Validate this risk during paid pilot discovery before locking package terms.",
            "rationale": "Persisted design brief risk.",
            "source": "design_brief.risks",
        }
        for index, risk in enumerate(_string_list(design_brief.get("risks")), start=1)
    ]
    if market_signals.get("funding", 0) == 0:
        risks.append(
            {
                "id": "risk-budget-signal",
                "risk": "No linked funding or explicit budget evidence.",
                "mitigation": "Ask buyers to name the budget owner and pilot approval threshold.",
                "rationale": "Pricing confidence is lower without budget evidence.",
                "source": "market_signals",
            }
        )
    if competitive_hints.get("density") == "high":
        risks.append(
            {
                "id": "risk-competitive-density",
                "risk": "High competitive density may compress willingness to pay.",
                "mitigation": "Anchor packaging around brief-specific workflow outcomes and proof points.",
                "rationale": "Multiple alternatives increase substitution pressure.",
                "source": "competitive_landscape_hints",
            }
        )
    return risks


def _recommended_experiments(validation_questions: list[str]) -> list[dict[str, str]]:
    return [
        {
            "id": f"experiment-{index}",
            "name": "Validate pricing question",
            "question": question,
            "experiment": "Run structured buyer discovery or paid pilot follow-up against this question.",
            "success_metric": "Decision-quality evidence captured from at least three qualified buyers.",
            "source": "validation_questions",
        }
        for index, question in enumerate(validation_questions, start=1)
    ]


def _confidence(
    design_brief: dict[str, Any],
    evidence: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    competitive_hints: dict[str, Any],
) -> dict[str, Any]:
    readiness = min(max(float(design_brief.get("readiness_score") or 0.0) / 100.0, 0.0), 1.0)
    evidence_score = min(len(evidence) / 6.0, 1.0)
    evaluation_score = min((_average(item["overall_score"] for item in evaluations) or 0.0) / 100.0, 1.0)
    competitive_score = 0.7 if competitive_hints["prior_art_count"] else 0.35
    buyer_score = 1.0 if design_brief.get("buyer") and design_brief.get("specific_user") else 0.45
    score = round(
        readiness * 0.25
        + evidence_score * 0.25
        + evaluation_score * 0.25
        + competitive_score * 0.10
        + buyer_score * 0.15,
        2,
    )
    return {
        "score": score,
        "level": "high" if score >= 0.75 else "medium" if score >= 0.45 else "low",
        "drivers": [
            f"readiness={readiness:.2f}",
            f"evidence_references={len(evidence)}",
            f"evaluations={len(evaluations)}",
            f"prior_art={competitive_hints['prior_art_count']}",
        ],
    }


def _field_values(items: list[dict[str, Any]], field: str) -> list[str]:
    return [_clean(item.get(field)) for item in items if _clean(item.get(field))]


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, list | tuple):
            found = _first_text(*value)
            if found:
                return found
            continue
        clean = _clean(value)
        if clean:
            return clean
    return ""


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _source_type(signal: Any) -> str:
    source_type = getattr(signal, "source_type", "")
    if hasattr(source_type, "value"):
        return str(source_type.value).lower()
    return str(source_type or "").lower()


def _average(values: Iterable[float]) -> float | None:
    values = list(values)
    if not values:
        return None
    return sum(values) / len(values)


def _band_label(band: dict[str, Any]) -> str:
    return f"${band['monthly_min_usd']}-${band['monthly_max_usd']}/month"


def _filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_")
