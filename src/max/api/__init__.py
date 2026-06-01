"""API endpoint renderers for external integrations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from max.api.budget_usage import budget_usage_to_json
from max.api.budget_burn_rate_status import budget_burn_rate_status_to_json
from max.api.disaster_recovery import disaster_recovery_plan_to_json
from max.api.adapter_rate_limit_exhaustion_status import adapter_rate_limit_exhaustion_status_to_json
from max.api.adapter_circuit_breaker_recovery_status import adapter_circuit_breaker_recovery_status_to_json
from max.api.adapter_health_rollup_status import adapter_health_rollup_status_to_json
from max.api.buildable_unit_graduation_criteria_status import buildable_unit_graduation_criteria_status_to_json
from max.api.buildable_unit_stack_policy_status import buildable_unit_stack_policy_status_to_json
from max.api.domain_profile_schema_drift_status import domain_profile_schema_drift_status_to_json
from max.api.embedding_cache_hit_rate_status import embedding_cache_hit_rate_status_to_json
from max.api.signal_ingestion_error_spike_status import signal_ingestion_error_spike_status_to_json
from max.api.llm_cost_projection_status import llm_cost_projection_status_to_json
from max.api.spec_evidence_freshness_status import spec_evidence_freshness_status_to_json
from max.api.runtime_artifact_retention_status import runtime_artifact_retention_status_to_json
from max.api.runtime_artifact_purge_status import runtime_artifact_purge_status_to_json
from max.api.signal_annotation_coverage_status import signal_annotation_coverage_status_to_json
from max.api.insight_evidence_chain_gap_status import insight_evidence_chain_gap_status_to_json
from max.api.buildable_unit_spec_blocker_status import buildable_unit_spec_blocker_status_to_json
from max.api.publisher_destination_quota_status import publisher_destination_quota_status_to_json
from max.api.profile_source_mix_shift_status import profile_source_mix_shift_status_to_json
from max.api.embedding_reindex_queue_status import embedding_reindex_queue_status_to_json
from max.api.embedding_index_fragmentation_status import embedding_index_fragmentation_status_to_json
from max.api.embedding_similarity_threshold_status import embedding_similarity_threshold_status_to_json
from max.api.evaluation_dimension_coverage_status import evaluation_dimension_coverage_status_to_json
from max.api.evaluation_recommendation_distribution_status import evaluation_recommendation_distribution_status_to_json
from max.api.evaluation_rubric_version_status import evaluation_rubric_version_status_to_json
from max.api.feedback_weight_drift_status import feedback_weight_drift_status_to_json
from max.api.feedback_ingestion_backlog_status import feedback_ingestion_backlog_status_to_json
from max.api.feedback_outcome_freshness_status import feedback_outcome_freshness_status_to_json
from max.api.insight_deduplication_collision_status import insight_deduplication_collision_status_to_json
from max.api.insight_staleness_distribution_status import insight_staleness_distribution_status_to_json
from max.api.insight_to_unit_conversion_status import insight_to_unit_conversion_status_to_json
from max.api.ideation_mode_quota_status import ideation_mode_quota_status_to_json
from max.api.evaluation_dataset_staleness_status import evaluation_dataset_staleness_status_to_json
from max.api.evaluation_score_outlier_status import evaluation_score_outlier_status_to_json
from max.api.feedback_label_quality_status import feedback_label_quality_status_to_json
from max.api.idea_novelty_decay_status import idea_novelty_decay_status_to_json
from max.api.inference_queue_saturation_status import inference_queue_saturation_status_to_json
from max.api.llm_prompt_cache_health_status import llm_prompt_cache_health_status_to_json
from max.api.llm_context_truncation_status import llm_context_truncation_status_to_json
from max.api.llm_prompt_drift_status import llm_prompt_drift_status_to_json
from max.api.llm_provider_failover_status import llm_provider_failover_status_to_json
from max.api.llm_retry_storm_status import llm_retry_storm_status_to_json
from max.api.model_usage_anomaly_status import model_usage_anomaly_status_to_json
from max.api.incremental_synthesis_checkpoint_status import incremental_synthesis_checkpoint_status_to_json
from max.api.pii_detection_backlog_status import pii_detection_backlog_status_to_json
from max.api.pipeline_budget_guardrail_trip_status import pipeline_budget_guardrail_trip_status_to_json
from max.api.pipeline_run_sla_status import pipeline_run_sla_status_to_json
from max.api.profile_evaluation_weight_drift_status import profile_evaluation_weight_drift_status_to_json
from max.api.profile_run_parameter_drift_status import profile_run_parameter_drift_status_to_json
from max.api.profile_source_budget_status import profile_source_budget_status_to_json
from max.api.profile_constraint_coverage_status import profile_constraint_coverage_status_to_json
from max.api.profile_constraint_violation_status import profile_constraint_violation_status_to_json
from max.api.profile_deprecation_sunset_status import profile_deprecation_sunset_status_to_json
from max.api.prompt_template_version_drift_status import prompt_template_version_drift_status_to_json
from max.api.prompt_redaction_coverage_status import prompt_redaction_coverage_status_to_json
from max.api.publication_webhook_delivery_status import publication_webhook_delivery_status_to_json
from max.api.publication_destination_rate_limit_status import publication_destination_rate_limit_status_to_json
from max.api.publication_approval_delegation_status import publication_approval_delegation_status_to_json
from max.api.publisher_destination_failover_status import publisher_destination_failover_status_to_json
from max.api.publication_payload_size_status import publication_payload_size_status_to_json
from max.api.publisher_retry_policy_status import publisher_retry_policy_status_to_json
from max.api.retrospective_learning_health_status import retrospective_learning_health_status_to_json
from max.api.retention_policy_exception_status import retention_policy_exception_status_to_json
from max.api.run_artifact_freshness_status import run_artifact_freshness_status_to_json
from max.api.run_step_retry_status import run_step_retry_status_to_json
from max.api.signal_deduplication_cluster_status import signal_deduplication_cluster_status_to_json
from max.api.signal_freshness_regression_status import signal_freshness_regression_status_to_json
from max.api.signal_payload_redaction_status import signal_payload_redaction_status_to_json
from max.api.source_adapter_error_budget_status import source_adapter_error_budget_status_to_json
from max.api.source_adapter_backoff_debt_status import source_adapter_backoff_debt_status_to_json
from max.api.source_adapter_stale_credential_status import source_adapter_stale_credential_status_to_json
from max.api.source_adapter_throttle_window_status import source_adapter_throttle_window_status_to_json
from max.api.source_sampling_bias_status import source_sampling_bias_status_to_json
from max.api.source_payload_size_status import source_payload_size_status_to_json
from max.api.source_ingestion_error_taxonomy_status import source_ingestion_error_taxonomy_status_to_json
from max.api.source_priority_rebalance_status import source_priority_rebalance_status_to_json
from max.api.source_terms_compliance_status import source_terms_compliance_status_to_json
from max.api.source_adapter_output_contract_status import source_adapter_output_contract_status_to_json
from max.api.spec_generation_failure_taxonomy_status import spec_generation_failure_taxonomy_status_to_json
from max.api.spec_generation_queue_depth_status import spec_generation_queue_depth_status_to_json
from max.api.spec_publication_readiness_status import spec_publication_readiness_status_to_json
from max.api.spec_evidence_citation_quality_status import spec_evidence_citation_quality_status_to_json
from max.api.spec_publication_queue_health_status import spec_publication_queue_health_status_to_json
from max.api.spec_publication_audit_trail_status import spec_publication_audit_trail_status_to_json
from max.api.spec_trace_completeness_status import spec_trace_completeness_status_to_json
from max.api.spec_traceability_gap_status import spec_traceability_gap_status_to_json
from max.api.synthesis_batch_backlog_status import synthesis_batch_backlog_status_to_json
from max.api.synthesis_incremental_watermark_status import synthesis_incremental_watermark_status_to_json
from max.api.tact_daemon_connectivity_status import tact_daemon_connectivity_status_to_json
from max.api.tact_daemon_publication_health_status import tact_daemon_publication_health_status_to_json
from max.api.tact_spec_export_readiness_status import tact_spec_export_readiness_status_to_json
from max.api.tact_spec_template_migration_status import tact_spec_template_migration_status_to_json


def design_brief_go_to_market_to_json(strategy: Mapping[str, Any]) -> dict[str, Any]:
    """Render design brief go-to-market data as an API JSON structure."""
    channels = list(strategy.get("distribution_channels") or strategy.get("channels") or [])
    timeline = list(strategy.get("launch_timeline") or strategy.get("timeline") or [])
    metrics = {
        "segment_count": _summary_value(strategy, "segment_count", "market_segments"),
        "channel_count": _summary_value(strategy, "channel_count", "distribution_channels"),
        "messaging_count": _summary_value(strategy, "messaging_count", "key_messaging"),
        "timeline_milestone_count": len(timeline),
    }
    return {
        "schema_version": "max.api.design_brief_go_to_market.v1",
        "kind": "max.api.design_brief_go_to_market",
        "strategy": {
            "summary": dict(strategy.get("summary") or {}),
            "market_segments": list(strategy.get("market_segments") or []),
            "positioning": list(strategy.get("positioning_statements") or []),
            "messaging": list(strategy.get("key_messaging") or []),
        },
        "channels": channels,
        "timeline": timeline,
        "metrics": metrics,
        "metadata": _metadata(strategy),
    }


def portfolio_stage_distribution_to_json(report: Mapping[str, Any]) -> dict[str, Any]:
    """Render portfolio stage distribution data as an API JSON structure."""
    stage_counts = {
        "by_status": list(report.get("by_status") or []),
        "by_recommendation": list(report.get("by_recommendation") or []),
        "by_profile": list(report.get("by_profile") or []),
        "by_domain": list(report.get("by_domain") or []),
        "by_evidence_strength": list(report.get("by_evidence_strength") or []),
    }
    return {
        "schema_version": "max.api.portfolio_stage_distribution.v1",
        "kind": "max.api.portfolio_stage_distribution",
        "summary": dict(report.get("summary") or {}),
        "stage_counts": stage_counts,
        "percentages": _percentages(stage_counts),
        "groups": list(report.get("groups") or []),
        "bottlenecks": list(report.get("bottlenecks") or []),
        "recommendations": list(report.get("recommendations") or []),
        "metadata": _metadata(report, extra={"filters": dict(report.get("filters") or {})}),
    }


def design_brief_technical_risks_to_json(report: Mapping[str, Any]) -> dict[str, Any]:
    """Render design brief technical risks data as an API JSON structure."""
    risks = list(report.get("technical_risks") or report.get("risks") or [])
    return {
        "schema_version": "max.api.design_brief_technical_risks.v1",
        "kind": "max.api.design_brief_technical_risks",
        "summary": dict(report.get("summary") or {}),
        "risk_categories": _group_risks(risks, "category"),
        "severity_levels": _group_risks(risks, "severity"),
        "mitigation_strategies": [
            {
                "risk_id": risk.get("id"),
                "strategy": risk.get("mitigation_strategy") or risk.get("mitigation"),
                "owner": risk.get("owner"),
            }
            for risk in risks
        ],
        "impact_assessments": [
            {
                "risk_id": risk.get("id"),
                "severity": risk.get("severity"),
                "likelihood": risk.get("likelihood"),
                "description": risk.get("description"),
            }
            for risk in risks
        ],
        "risks": risks,
        "metadata": _metadata(report),
    }


def _summary_value(report: Mapping[str, Any], key: str, fallback_list_key: str) -> int:
    summary = report.get("summary")
    if isinstance(summary, Mapping) and isinstance(summary.get(key), int):
        return int(summary[key])
    value = report.get(fallback_list_key)
    return len(value) if isinstance(value, list) else 0


def _metadata(
    payload: Mapping[str, Any],
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = payload.get("source") if isinstance(payload.get("source"), Mapping) else {}
    design_brief = (
        payload.get("design_brief") if isinstance(payload.get("design_brief"), Mapping) else {}
    )
    metadata = {
        "source_schema_version": payload.get("schema_version"),
        "source_kind": payload.get("kind"),
        "source": dict(source),
        "design_brief": dict(design_brief),
    }
    if extra:
        metadata.update(dict(extra))
    return metadata


def _percentages(stage_counts: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, dict[str, float]]:
    percentages: dict[str, dict[str, float]] = {}
    for dimension, rows in stage_counts.items():
        percentages[dimension] = {
            str(_row_value(row, dimension)): float(row.get("percentage") or 0.0)
            for row in rows
        }
    return percentages


def _row_value(row: Mapping[str, Any], dimension: str) -> Any:
    key = dimension.removeprefix("by_")
    return row.get(key) or row.get("value") or "unspecified"


def _group_risks(risks: list[Any], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for risk in risks:
        if not isinstance(risk, Mapping):
            continue
        grouped.setdefault(str(risk.get(key) or "unspecified"), []).append(risk)
    return [
        {
            key: value,
            "count": len(items),
            "risk_ids": [item.get("id") for item in items],
        }
        for value, items in sorted(grouped.items())
    ]


__all__ = [
    "design_brief_go_to_market_to_json",
    "budget_usage_to_json",
    "budget_burn_rate_status_to_json",
    "adapter_rate_limit_exhaustion_status_to_json",
    "adapter_circuit_breaker_recovery_status_to_json",
    "adapter_health_rollup_status_to_json",
    "buildable_unit_graduation_criteria_status_to_json",
    "buildable_unit_stack_policy_status_to_json",
    "domain_profile_schema_drift_status_to_json",
    "embedding_cache_hit_rate_status_to_json",
    "signal_ingestion_error_spike_status_to_json",
    "llm_cost_projection_status_to_json",
    "spec_evidence_freshness_status_to_json",
    "runtime_artifact_retention_status_to_json",
    "runtime_artifact_purge_status_to_json",
    "signal_annotation_coverage_status_to_json",
    "insight_evidence_chain_gap_status_to_json",
    "buildable_unit_spec_blocker_status_to_json",
    "publisher_destination_quota_status_to_json",
    "profile_source_mix_shift_status_to_json",
    "embedding_reindex_queue_status_to_json",
    "embedding_index_fragmentation_status_to_json",
    "portfolio_stage_distribution_to_json",
    "design_brief_technical_risks_to_json",
    "disaster_recovery_plan_to_json",
    "embedding_similarity_threshold_status_to_json",
    "evaluation_dimension_coverage_status_to_json",
    "evaluation_recommendation_distribution_status_to_json",
    "evaluation_rubric_version_status_to_json",
    "evaluation_dataset_staleness_status_to_json",
    "evaluation_score_outlier_status_to_json",
    "feedback_weight_drift_status_to_json",
    "feedback_ingestion_backlog_status_to_json",
    "feedback_outcome_freshness_status_to_json",
    "feedback_label_quality_status_to_json",
    "idea_novelty_decay_status_to_json",
    "insight_staleness_distribution_status_to_json",
    "insight_to_unit_conversion_status_to_json",
    "ideation_mode_quota_status_to_json",
    "inference_queue_saturation_status_to_json",
    "llm_prompt_cache_health_status_to_json",
    "llm_context_truncation_status_to_json",
    "llm_prompt_drift_status_to_json",
    "llm_provider_failover_status_to_json",
    "llm_retry_storm_status_to_json",
    "model_usage_anomaly_status_to_json",
    "incremental_synthesis_checkpoint_status_to_json",
    "pii_detection_backlog_status_to_json",
    "pipeline_budget_guardrail_trip_status_to_json",
    "pipeline_run_sla_status_to_json",
    "profile_evaluation_weight_drift_status_to_json",
    "profile_run_parameter_drift_status_to_json",
    "profile_source_budget_status_to_json",
    "profile_constraint_coverage_status_to_json",
    "profile_constraint_violation_status_to_json",
    "profile_deprecation_sunset_status_to_json",
    "prompt_template_version_drift_status_to_json",
    "insight_deduplication_collision_status_to_json",
    "prompt_redaction_coverage_status_to_json",
    "publication_webhook_delivery_status_to_json",
    "publication_destination_rate_limit_status_to_json",
    "publication_approval_delegation_status_to_json",
    "publisher_destination_failover_status_to_json",
    "publication_payload_size_status_to_json",
    "publisher_retry_policy_status_to_json",
    "retrospective_learning_health_status_to_json",
    "retention_policy_exception_status_to_json",
    "run_artifact_freshness_status_to_json",
    "run_step_retry_status_to_json",
    "signal_deduplication_cluster_status_to_json",
    "signal_freshness_regression_status_to_json",
    "signal_payload_redaction_status_to_json",
    "source_adapter_error_budget_status_to_json",
    "source_adapter_backoff_debt_status_to_json",
    "source_adapter_stale_credential_status_to_json",
    "source_adapter_throttle_window_status_to_json",
    "source_sampling_bias_status_to_json",
    "source_payload_size_status_to_json",
    "source_ingestion_error_taxonomy_status_to_json",
    "source_priority_rebalance_status_to_json",
    "source_terms_compliance_status_to_json",
    "source_adapter_output_contract_status_to_json",
    "spec_generation_failure_taxonomy_status_to_json",
    "spec_generation_queue_depth_status_to_json",
    "spec_publication_readiness_status_to_json",
    "spec_evidence_citation_quality_status_to_json",
    "spec_publication_queue_health_status_to_json",
    "spec_publication_audit_trail_status_to_json",
    "spec_trace_completeness_status_to_json",
    "spec_traceability_gap_status_to_json",
    "synthesis_batch_backlog_status_to_json",
    "synthesis_incremental_watermark_status_to_json",
    "tact_daemon_connectivity_status_to_json",
    "tact_daemon_publication_health_status_to_json",
    "tact_spec_export_readiness_status_to_json",
    "tact_spec_template_migration_status_to_json",
]
