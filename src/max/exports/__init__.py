"""Export modules for competitive intelligence and market analysis."""

from max.exports.budget_overrun_root_cause_report import (
    build_budget_overrun_root_cause_report,
    render_budget_overrun_root_cause_report_json,
    render_budget_overrun_root_cause_report_markdown,
)
from max.exports.idea_review_cycle_time_report import (
    build_idea_review_cycle_time_report,
    render_idea_review_cycle_time_report_json,
    render_idea_review_cycle_time_report_markdown,
)
from max.exports.insight_evidence_staleness_report import (
    build_insight_evidence_staleness_report,
    render_insight_evidence_staleness_report_json,
    render_insight_evidence_staleness_report_markdown,
)
from max.exports.insight_confidence_decay_report import (
    build_insight_confidence_decay_report_export,
    render_insight_confidence_decay_report_json,
    render_insight_confidence_decay_report_markdown,
)
from max.exports.buildable_unit_stack_diversity_report import (
    build_buildable_unit_stack_diversity_report_export,
    render_buildable_unit_stack_diversity_report_json,
    render_buildable_unit_stack_diversity_report_markdown,
)
from max.exports.idea_aging_sla_report import (
    build_idea_aging_sla_report_export,
    render_idea_aging_sla_report_json,
    render_idea_aging_sla_report_markdown,
)
from max.exports.profile_coverage_drift_report import (
    build_profile_coverage_drift_report,
    render_profile_coverage_drift_report_json,
    render_profile_coverage_drift_report_markdown,
)
from max.exports.publisher_retry_backlog_report import (
    build_publisher_retry_backlog_report,
    render_publisher_retry_backlog_report_json,
    render_publisher_retry_backlog_report_markdown,
)
from max.exports.publisher_webhook_latency_report import (
    generate_publisher_webhook_latency_report,
    render_publisher_webhook_latency_report_json,
    render_publisher_webhook_latency_report_markdown,
)
from max.exports.signal_source_noise_report import (
    build_signal_source_noise_report,
    render_signal_source_noise_report_json,
    render_signal_source_noise_report_markdown,
)
from max.exports.source_api_deprecation_report import (
    build_source_api_deprecation_report,
    render_source_api_deprecation_report_json,
    render_source_api_deprecation_report_markdown,
)
from max.exports.synthesis_batch_backlog import (
    generate_synthesis_batch_backlog_report,
    render_synthesis_batch_backlog_json,
)
from max.exports.eval_goldens_coverage_gap_report import generate_eval_goldens_coverage_gap_report
from max.exports.embedding_dimension_mismatch_report import generate_embedding_dimension_mismatch_report
from max.exports.profile_weight_conflict_report import generate_profile_weight_conflict_report
from max.exports.domain_profile_constraint_violation_report import generate_domain_profile_constraint_violation_report
from max.exports.insight_contradiction_report import (
    generate_insight_contradiction_report,
    render_insight_contradiction_report_json,
    render_insight_contradiction_report_markdown,
)
from max.exports.spec_template_coverage_report import (
    generate_spec_template_coverage_report,
    render_spec_template_coverage_report_json,
    render_spec_template_coverage_report_markdown,
)
from max.exports.feedback_reviewer_agreement_report import (
    generate_feedback_reviewer_agreement_report,
    render_feedback_reviewer_agreement_report_json,
    render_feedback_reviewer_agreement_report_markdown,
)
from max.exports.llm_prompt_version_adoption_report import (
    generate_llm_prompt_version_adoption_report,
    render_llm_prompt_version_adoption_report_json,
    render_llm_prompt_version_adoption_report_markdown,
)
from max.exports.security_advisory_signal_impact_report import (
    generate_security_advisory_signal_impact_report,
    render_security_advisory_signal_impact_report_json,
    render_security_advisory_signal_impact_report_markdown,
)
from max.exports.source_adapter_error_budget_breach_report import (
    generate_source_adapter_error_budget_breach_report,
    render_source_adapter_error_budget_breach_report_json,
    render_source_adapter_error_budget_breach_report_markdown,
)
from max.exports.ideation_prompt_yield_variance_report import (
    generate_ideation_prompt_yield_variance_report,
    render_ideation_prompt_yield_variance_report_json,
    render_ideation_prompt_yield_variance_report_markdown,
)
from max.exports.spec_generation_failure_taxonomy_report import (
    generate_spec_generation_failure_taxonomy_report,
    render_spec_generation_failure_taxonomy_report_json,
    render_spec_generation_failure_taxonomy_report_markdown,
)
from max.exports.budget_reservation_utilization_report import (
    generate_budget_reservation_utilization_report,
    render_budget_reservation_utilization_report_json,
    render_budget_reservation_utilization_report_markdown,
)
from max.exports.evidence_chain_orphan_report import (
    generate_evidence_chain_orphan_report,
    render_evidence_chain_orphan_report_json,
    render_evidence_chain_orphan_report_markdown,
)
from max.exports.signal_ingestion_lag_report import generate_signal_ingestion_lag_report
from max.exports.runtime_artifact_retention_report import generate_runtime_artifact_retention_report
from max.exports.synthesis_prompt_failure_report import generate_synthesis_prompt_failure_report
from max.exports.idea_duplicate_cluster_report import generate_idea_duplicate_cluster_report
from max.exports.llm_token_budget_leak_report import generate_llm_token_budget_leak_report
from max.exports.insight_evidence_source_concentration_report import generate_insight_evidence_source_concentration_report
from max.exports.buildable_unit_dependency_freshness_report import generate_buildable_unit_dependency_freshness_report
from max.exports.buildable_unit_scope_creep_report import generate_buildable_unit_scope_creep_report
from max.exports.feedback_reviewer_throughput_forecast_report import generate_feedback_reviewer_throughput_forecast_report
from max.exports.insight_gap_detection_precision_report import generate_insight_gap_detection_precision_report
from max.exports.llm_provider_failover_drill_report import generate_llm_provider_failover_drill_report
from max.exports.publication_destination_cost_spike_report import generate_publication_destination_cost_spike_report
from max.exports.profile_cadence_adherence_report import (
    generate_profile_cadence_adherence_report,
    render_profile_cadence_adherence_report_json,
    render_profile_cadence_adherence_report_markdown,
)
from max.exports.profile_source_contract_coverage_report import (
    generate_profile_source_contract_coverage_report,
    render_profile_source_contract_coverage_report_json,
    render_profile_source_contract_coverage_report_markdown,
)
from max.exports.source_adapter_retry_jitter_report import (
    generate_source_adapter_retry_jitter_report,
    render_source_adapter_retry_jitter_report_json,
    render_source_adapter_retry_jitter_report_markdown,
)
from max.exports.spec_publication_rollback_readiness_report import generate_spec_publication_rollback_readiness_report
from max.exports.spec_generation_token_waste_report import (
    build_spec_generation_token_waste_report,
    render_spec_generation_token_waste_report_json,
    render_spec_generation_token_waste_report_markdown,
)
from max.exports.ideation_mode_conversion_funnel_report import generate_ideation_mode_conversion_funnel_report
from max.exports.retrospective_feedback_outcome_skew_report import generate_retrospective_feedback_outcome_skew_report
from max.exports.feedback_recency_decay_report import generate_feedback_recency_decay_report
from max.exports.idea_stack_concentration_report import generate_idea_stack_concentration_report
from max.exports.insight_evidence_trace_depth_report import generate_insight_evidence_trace_depth_report
from max.exports.insight_novelty_collision_report import generate_insight_novelty_collision_report
from max.exports.llm_cost_anomaly_report import generate_llm_cost_anomaly_report
from max.exports.profile_source_mix_drift_report import generate_profile_source_mix_drift_report
from max.exports.publication_target_failure_cluster_report import generate_publication_target_failure_cluster_report
from max.exports.signal_annotation_gap_report import generate_signal_annotation_gap_report
from max.exports.source_credential_scope_report import generate_source_credential_scope_report
from max.exports.spec_evidence_trace_gap_report import generate_spec_evidence_trace_gap_report
from max.exports.compliance_evidence_packet import (
    build_compliance_evidence_packet,
    render_compliance_evidence_packet_csv,
    render_compliance_evidence_packet_json,
    render_compliance_evidence_packet_markdown,
)
from max.exports.compliance_questionnaire_gap import (
    build_compliance_questionnaire_gap_export,
    render_compliance_questionnaire_gap_json,
    render_compliance_questionnaire_gap_markdown,
)
from max.exports.customer_success_qbr import (
    build_customer_success_qbr_export,
    render_customer_success_qbr_csv,
    render_customer_success_qbr_json,
    render_customer_success_qbr_markdown,
)
from max.exports.customer_value_realization import (
    export_customer_value_realization,
    render_customer_value_realization_json,
)
from max.exports.customer_reference_readiness import (
    build_customer_reference_readiness_export,
    render_customer_reference_readiness_json,
    render_customer_reference_readiness_markdown,
)
from max.exports.customer_escalation_risk_report import (
    build_customer_escalation_risk_report_export,
    render_customer_escalation_risk_report_json,
    render_customer_escalation_risk_report_markdown,
)
from max.exports.customer_churn_save_playbook import (
    build_customer_churn_save_playbook_export,
    render_customer_churn_save_playbook_json,
    render_customer_churn_save_playbook_markdown,
)
from max.exports.customer_adoption_risk_index import (
    build_customer_adoption_risk_index_export,
    render_customer_adoption_risk_index_json,
    render_customer_adoption_risk_index_markdown,
)
from max.exports.customer_journey_friction_report import (
    build_customer_journey_friction_report_export,
    render_customer_journey_friction_report_json,
    render_customer_journey_friction_report_markdown,
)
from max.exports.expansion_readiness_scorecard import (
    build_expansion_readiness_scorecard_export,
    render_expansion_readiness_scorecard_json,
    render_expansion_readiness_scorecard_markdown,
)
from max.exports.enterprise_security_questionnaire import (
    build_enterprise_security_questionnaire_export,
    render_enterprise_security_questionnaire_json,
    render_enterprise_security_questionnaire_markdown,
)
from max.exports.enterprise_pilot_success_scorecard import (
    build_enterprise_pilot_success_scorecard_export,
    render_enterprise_pilot_success_scorecard_json,
    render_enterprise_pilot_success_scorecard_markdown,
)
from max.exports.retention_cohorts import (
    build_retention_cohort_export,
    render_retention_cohort_json,
    render_retention_cohort_markdown,
)
from max.exports.api_quota_utilization import (
    build_api_quota_utilization_export,
    render_api_quota_utilization_csv,
    render_api_quota_utilization_json,
    render_api_quota_utilization_markdown,
)
from max.exports.account_health_score import (
    build_account_health_score_export,
    render_account_health_score_json,
    render_account_health_score_markdown,
)
from max.exports.buyer_committee_alignment import (
    build_buyer_committee_alignment_export,
    render_buyer_committee_alignment_json,
    render_buyer_committee_alignment_markdown,
)
from max.exports.data_residency_matrix import (
    build_data_residency_matrix_export,
    render_data_residency_matrix_csv,
    render_data_residency_matrix_json,
    render_data_residency_matrix_markdown,
)
from max.exports.data_processing_agreement_renewal_report import (
    build_data_processing_agreement_renewal_report_export,
    render_data_processing_agreement_renewal_report_json,
    render_data_processing_agreement_renewal_report_markdown,
)
from max.exports.feature_adoption_cohorts import (
    build_feature_adoption_cohorts_export,
    render_feature_adoption_cohorts_json,
    render_feature_adoption_cohorts_markdown,
)
from max.exports.feature_request_revenue_map import (
    build_feature_request_revenue_map_export,
    render_feature_request_revenue_map_json,
    render_feature_request_revenue_map_markdown,
)
from max.exports.feature_entitlement_revenue_leakage_report import (
    build_feature_entitlement_revenue_leakage_report_export,
    render_feature_entitlement_revenue_leakage_report_json,
    render_feature_entitlement_revenue_leakage_report_markdown,
)
from max.exports.incident_impact_assessment import (
    build_incident_impact_assessment_export,
    render_incident_impact_assessment_csv,
    render_incident_impact_assessment_json,
    render_incident_impact_assessment_markdown,
)
from max.exports.incident_sla_breach_trend_report import (
    build_incident_sla_breach_trend_report_export,
    render_incident_sla_breach_trend_report_json,
    render_incident_sla_breach_trend_report_markdown,
)
from max.exports.implementation_risk_heatmap import (
    build_implementation_risk_heatmap_export,
    render_implementation_risk_heatmap_json,
    render_implementation_risk_heatmap_markdown,
)
from max.exports.implementation_timeline_variance_report import (
    build_implementation_timeline_variance_report_export,
    render_implementation_timeline_variance_report_json,
    render_implementation_timeline_variance_report_markdown,
)
from max.exports.implementation_blocker_aging import (
    export_implementation_blocker_aging,
    render_implementation_blocker_aging_json,
)
from max.exports.integration_dependency_health import (
    build_integration_dependency_health_export,
    render_integration_dependency_health_csv,
    render_integration_dependency_health_json,
    render_integration_dependency_health_markdown,
)
from max.exports.integration_readiness_matrix import (
    build_integration_readiness_matrix_export,
    render_integration_readiness_matrix_csv,
    render_integration_readiness_matrix_json,
    render_integration_readiness_matrix_markdown,
)
from max.exports.integration_sla_compliance_report import (
    build_integration_sla_compliance_report_export,
    render_integration_sla_compliance_report_csv,
    render_integration_sla_compliance_report_json,
    render_integration_sla_compliance_report_markdown,
)
from max.exports.investment_case import (
    build_investment_case,
    render_investment_case_json,
    render_investment_case_markdown,
)
from max.exports.localization_readiness import (
    build_localization_readiness_export,
    render_localization_readiness_csv,
    render_localization_readiness_json,
    render_localization_readiness_markdown,
)
from max.exports.onboarding_activation_cohorts import (
    export_onboarding_activation_cohorts,
    render_onboarding_activation_cohorts_json,
)
from max.exports.partner_ecosystem_map import (
    build_partner_ecosystem_map_export,
    render_partner_ecosystem_map_json,
    render_partner_ecosystem_map_markdown,
)
from max.exports.partner_referral_pipeline_coverage_report import (
    build_partner_referral_pipeline_coverage_report_export,
    render_partner_referral_pipeline_coverage_report_json,
    render_partner_referral_pipeline_coverage_report_markdown,
)
from max.exports.partner_integration_risk_register import (
    export_partner_integration_risk_register,
    render_partner_integration_risk_register_json,
)
from max.exports.pricing_sensitivity import (
    build_pricing_sensitivity_report,
    render_pricing_sensitivity_csv,
    render_pricing_sensitivity_json,
    render_pricing_sensitivity_markdown,
)
from max.exports.pricing_discount_leakage_report import (
    build_pricing_discount_leakage_report_export,
    render_pricing_discount_leakage_report_json,
    render_pricing_discount_leakage_report_markdown,
)
from max.exports.procurement_readiness_checklist import (
    build_procurement_readiness_checklist_export,
    render_procurement_readiness_checklist_json,
    render_procurement_readiness_checklist_markdown,
)
from max.exports.procurement_cycle_friction import (
    build_procurement_cycle_friction_export,
    render_procurement_cycle_friction_json,
    render_procurement_cycle_friction_markdown,
)
from max.exports.proof_of_concept_roi import (
    build_proof_of_concept_roi_export,
    render_proof_of_concept_roi_json,
    render_proof_of_concept_roi_markdown,
)
from max.exports.competitive_landscape import (
    build_competitive_landscape,
    render_competitive_landscape_json,
    render_competitive_landscape_markdown,
)
from max.exports.competitive_win_loss import (
    build_competitive_win_loss_export,
    render_competitive_win_loss_csv,
    render_competitive_win_loss_json,
    render_competitive_win_loss_markdown,
)
from max.exports.product_usage_segmentation import (
    build_product_usage_segmentation_export,
    render_product_usage_segmentation_csv,
    render_product_usage_segmentation_json,
    render_product_usage_segmentation_markdown,
)
from max.exports.release_readiness_scorecard import (
    build_release_readiness_scorecard_export,
    render_release_readiness_scorecard_csv,
    render_release_readiness_scorecard_json,
    render_release_readiness_scorecard_markdown,
)
from max.exports.license_utilization_drift_report import (
    build_license_utilization_drift_report_export,
    render_license_utilization_drift_report_json,
    render_license_utilization_drift_report_markdown,
)
from max.exports.revenue_leakage_diagnostic import (
    build_revenue_leakage_diagnostic_export,
    render_revenue_leakage_diagnostic_csv,
    render_revenue_leakage_diagnostic_json,
    render_revenue_leakage_diagnostic_markdown,
)
from max.exports.renewal_risk_register import (
    export_renewal_risk_register,
    render_renewal_risk_register_json,
)
from max.exports.roadmap_prioritization import (
    build_roadmap_prioritization_export,
    render_roadmap_prioritization_csv,
    render_roadmap_prioritization_json,
    render_roadmap_prioritization_markdown,
)
from max.exports.roadmap_commitment_tracker import (
    export_roadmap_commitment_tracker,
    render_roadmap_commitment_tracker_json,
)
from max.exports.sales_pipeline_forecast import (
    build_sales_pipeline_forecast,
    render_sales_pipeline_forecast_csv,
    render_sales_pipeline_forecast_json,
    render_sales_pipeline_forecast_markdown,
)
from max.exports.sales_engineering_capacity_plan import (
    build_sales_engineering_capacity_plan_export,
    render_sales_engineering_capacity_plan_json,
    render_sales_engineering_capacity_plan_markdown,
)
from max.exports.security_review_intake_packet import (
    build_security_review_intake_packet_export,
    render_security_review_intake_packet_json,
    render_security_review_intake_packet_markdown,
)
from max.exports.security_questionnaire_evidence_aging_report import (
    build_security_questionnaire_evidence_aging_report_export,
    render_security_questionnaire_evidence_aging_report_json,
    render_security_questionnaire_evidence_aging_report_markdown,
)
from max.exports.customer_migration_wave_readiness_report import (
    build_customer_migration_wave_readiness_report_export,
    render_customer_migration_wave_readiness_report_json,
    render_customer_migration_wave_readiness_report_markdown,
)
from max.exports.sla_breach_risk import (
    build_sla_breach_risk_export,
    render_sla_breach_risk_csv,
    render_sla_breach_risk_json,
    render_sla_breach_risk_markdown,
)
from max.exports.support_ticket_theme_report import (
    build_support_ticket_theme_report,
    render_support_ticket_theme_report_csv,
    render_support_ticket_theme_report_json,
    render_support_ticket_theme_report_markdown,
)
from max.exports.tech_radar import (
    RadarQuadrant,
    RadarRing,
    build_tech_radar,
    build_tech_radar_export,
    classify_radar_ring,
    render_tech_radar_json,
    render_tech_radar_markdown,
)
from max.exports.trial_conversion_funnel import (
    build_trial_conversion_funnel_export,
    render_trial_conversion_funnel_json,
    render_trial_conversion_funnel_markdown,
)
from max.exports.trial_to_paid_conversion_diagnostic import (
    export_trial_to_paid_conversion_diagnostic,
    render_trial_to_paid_conversion_diagnostic_json,
)
from max.exports.vendor_evaluation import (
    EvaluationCriterion,
    build_vendor_evaluation,
    render_vendor_evaluation_csv,
    render_vendor_evaluation_json,
    render_vendor_evaluation_markdown,
)
from max.exports.source_adapter_reliability import (
    build_source_adapter_reliability_report,
    render_source_adapter_reliability_json,
    render_source_adapter_reliability_markdown,
)
from max.exports.source_adapter_coverage_gap_report import (
    build_source_adapter_coverage_gap_report,
    render_source_adapter_coverage_gap_report_json,
    render_source_adapter_coverage_gap_report_markdown,
)
from max.exports.source_adapter_version_skew_report import (
    build_source_adapter_version_skew_report,
    render_source_adapter_version_skew_report_json,
    render_source_adapter_version_skew_report_markdown,
)
from max.exports.source_oauth_scope_drift_report import (
    build_source_oauth_scope_drift_report,
    render_source_oauth_scope_drift_report_json,
    render_source_oauth_scope_drift_report_markdown,
)
from max.exports.source_cost_efficiency_report import (
    build_source_cost_efficiency_report,
    render_source_cost_efficiency_report_json,
    render_source_cost_efficiency_report_markdown,
)
from max.exports.source_auth_failure_trend_report import (
    build_source_auth_failure_trend_report,
    render_source_auth_failure_trend_report_json,
    render_source_auth_failure_trend_report_markdown,
)
from max.exports.source_backfill_gap_report import (
    build_source_backfill_gap_report,
    render_source_backfill_gap_report_json,
    render_source_backfill_gap_report_markdown,
)
from max.exports.source_circuit_breaker_churn_report import (
    build_source_circuit_breaker_churn_report,
    render_source_circuit_breaker_churn_report_json,
    render_source_circuit_breaker_churn_report_markdown,
)
from max.exports.cache_key_churn_report import (
    generate_cache_key_churn_report,
    render_cache_key_churn_report_json,
)
from max.exports.source_duplicate_signal_report import (
    build_source_duplicate_signal_report,
    render_source_duplicate_signal_report_json,
    render_source_duplicate_signal_report_markdown,
)
from max.exports.source_field_completeness_report import (
    build_source_field_completeness_report,
    render_source_field_completeness_report_json,
    render_source_field_completeness_report_markdown,
)
from max.exports.source_freshness_sla_report import (
    build_source_freshness_sla_report,
    render_source_freshness_sla_report_json,
    render_source_freshness_sla_report_markdown,
)
from max.exports.source_payload_parse_failure_report import (
    build_source_payload_parse_failure_report,
    render_source_payload_parse_failure_report_json,
    render_source_payload_parse_failure_report_markdown,
)
from max.exports.source_rate_limit_saturation_report import (
    build_source_rate_limit_saturation_report,
    render_source_rate_limit_saturation_report_json,
    render_source_rate_limit_saturation_report_markdown,
)
from max.exports.source_schema_drift_report import (
    build_source_schema_drift_report,
    render_source_schema_drift_report_json,
    render_source_schema_drift_report_markdown,
)
from max.exports.signal_freshness_sla_report import (
    build_signal_freshness_sla_report,
    render_signal_freshness_sla_report_json,
    render_signal_freshness_sla_report_markdown,
)
from max.exports.source_allocation_efficiency import (
    build_source_allocation_efficiency_report,
    render_source_allocation_efficiency_json,
    render_source_allocation_efficiency_markdown,
)
from max.exports.insight_deduplication_collision import (
    build_insight_deduplication_collision_report,
    render_insight_deduplication_collision_json,
    render_insight_deduplication_collision_markdown,
)
from max.exports.spec_evidence_trace_completeness_report import (
    build_spec_evidence_trace_completeness_report,
    render_spec_evidence_trace_completeness_report_json,
    render_spec_evidence_trace_completeness_report_markdown,
)
from max.exports.profile_weight_sensitivity_report import (
    build_profile_weight_sensitivity_report,
    render_profile_weight_sensitivity_report_json,
    render_profile_weight_sensitivity_report_markdown,
)
from max.exports.llm_budget_variance_report import (
    build_llm_budget_variance_report,
    render_llm_budget_variance_report_json,
    render_llm_budget_variance_report_markdown,
)
from max.exports.evaluation_score_drift_report import (
    build_evaluation_score_drift_report,
    render_evaluation_score_drift_report_json,
    render_evaluation_score_drift_report_markdown,
)
from max.exports.tact_spec_generation_failure_report import (
    build_tact_spec_generation_failure_report,
    render_tact_spec_generation_failure_report_json,
    render_tact_spec_generation_failure_report_markdown,
)
from max.exports.spec_review_rework_rate_report import (
    build_spec_review_rework_rate_report,
    render_spec_review_rework_rate_report_json,
    render_spec_review_rework_rate_report_markdown,
)
from max.exports.publisher_delivery_time_sla_report import (
    build_publisher_delivery_time_sla_report,
    render_publisher_delivery_time_sla_report_json,
    render_publisher_delivery_time_sla_report_markdown,
)
from max.exports.profile_constraint_violation_report import (
    build_profile_constraint_violation_report,
    render_profile_constraint_violation_report_json,
    render_profile_constraint_violation_report_markdown,
)
from max.exports.feedback_signal_quality_report import (
    build_feedback_signal_quality_report,
    render_feedback_signal_quality_report_json,
    render_feedback_signal_quality_report_markdown,
)
from max.exports.insight_attribution_completeness_report import (
    build_insight_attribution_completeness_report,
    render_insight_attribution_completeness_report_json,
    render_insight_attribution_completeness_report_markdown,
)
from max.exports.prompt_injection_attempt_trend_report import (
    build_prompt_injection_attempt_trend_report,
    render_prompt_injection_attempt_trend_report_json,
    render_prompt_injection_attempt_trend_report_markdown,
)
from max.exports.llm_provider_cost_comparison_report import (
    build_llm_provider_cost_comparison_report,
    render_llm_provider_cost_comparison_report_json,
    render_llm_provider_cost_comparison_report_markdown,
)
from max.exports.inference_latency_percentile_report import (
    build_inference_latency_percentile_report,
    render_inference_latency_percentile_report_json,
    render_inference_latency_percentile_report_markdown,
)
from max.exports.evaluation_dataset_coverage_report import (
    build_evaluation_dataset_coverage_report,
    render_evaluation_dataset_coverage_report_json,
    render_evaluation_dataset_coverage_report_markdown,
)
from max.exports.insight_to_unit_conversion_funnel_report import (
    build_insight_to_unit_conversion_funnel_report,
    render_insight_to_unit_conversion_funnel_report_json,
    render_insight_to_unit_conversion_funnel_report_markdown,
)
from max.exports.idea_recommendation_mix_report import (
    build_idea_recommendation_mix_report,
    render_idea_recommendation_mix_report_json,
    render_idea_recommendation_mix_report_markdown,
)
from max.exports.profile_idea_throughput_report import (
    build_profile_idea_throughput_report,
    render_profile_idea_throughput_report_json,
    render_profile_idea_throughput_report_markdown,
)
from max.exports.evidence_trace_depth_report import (
    build_evidence_trace_depth_report,
    render_evidence_trace_depth_report_json,
    render_evidence_trace_depth_report_markdown,
)
from max.exports.buildable_unit_readiness_blocker_report import (
    build_buildable_unit_readiness_blocker_report,
    render_buildable_unit_readiness_blocker_report_json,
    render_buildable_unit_readiness_blocker_report_markdown,
)
from max.exports.publication_destination_latency_report import (
    build_publication_destination_latency_report,
    render_publication_destination_latency_report_json,
    render_publication_destination_latency_report_markdown,
)
from max.exports.feedback_weight_shift_report import (
    build_feedback_weight_shift_report,
    render_feedback_weight_shift_report_json,
    render_feedback_weight_shift_report_markdown,
)
from max.exports.insight_contradiction_rate_report import (
    build_insight_contradiction_rate_report,
    render_insight_contradiction_rate_report_json,
    render_insight_contradiction_rate_report_markdown,
)
from max.exports.evaluation_override_frequency_report import (
    build_evaluation_override_frequency_report,
    render_evaluation_override_frequency_report_json,
    render_evaluation_override_frequency_report_markdown,
)
from max.exports.spec_generation_queue_aging_report import (
    build_spec_generation_queue_aging_report,
    render_spec_generation_queue_aging_report_json,
    render_spec_generation_queue_aging_report_markdown,
)
from max.exports.feedback_label_disagreement_report import (
    build_feedback_label_disagreement_report,
    render_feedback_label_disagreement_report_json,
    render_feedback_label_disagreement_report_markdown,
)
from max.exports.profile_signal_mix_report import (
    build_profile_signal_mix_report,
    render_profile_signal_mix_report_json,
    render_profile_signal_mix_report_markdown,
)
from max.exports.publication_channel_effectiveness_report import (
    build_publication_channel_effectiveness_report,
    render_publication_channel_effectiveness_report_json,
    render_publication_channel_effectiveness_report_markdown,
)
from max.exports.model_context_window_pressure_report import (
    build_model_context_window_pressure_report,
    render_model_context_window_pressure_report_json,
    render_model_context_window_pressure_report_markdown,
)
from max.exports.safety_mitigation_escape_report import (
    build_safety_mitigation_escape_report,
    render_safety_mitigation_escape_report_json,
    render_safety_mitigation_escape_report_markdown,
)
from max.exports.prompt_template_drift_report import (
    build_prompt_template_drift_report,
    render_prompt_template_drift_report_json,
    render_prompt_template_drift_report_markdown,
)
from max.exports.evaluation_rubric_drift_remediation_report import (
    generate_evaluation_rubric_drift_remediation_report,
    render_evaluation_rubric_drift_remediation_report_json,
    render_evaluation_rubric_drift_remediation_report_markdown,
)
from max.exports.prompt_redaction_leak_report import (
    generate_prompt_redaction_leak_report,
    render_prompt_redaction_leak_report_json,
    render_prompt_redaction_leak_report_markdown,
)
from max.exports.synthesis_insight_aging_report import (
    generate_synthesis_insight_aging_report,
    render_synthesis_insight_aging_report_json,
    render_synthesis_insight_aging_report_markdown,
)
from max.exports.publisher_auth_expiry_forecast_report import (
    generate_publisher_auth_expiry_forecast_report,
    render_publisher_auth_expiry_forecast_report_json,
    render_publisher_auth_expiry_forecast_report_markdown,
)
from max.exports.spec_approval_bottleneck_report import (
    generate_spec_approval_bottleneck_report,
    render_spec_approval_bottleneck_report_json,
    render_spec_approval_bottleneck_report_markdown,
)
from max.exports.llm_provider_cost_attribution_report import (
    build_llm_provider_cost_attribution_report_export,
    render_llm_provider_cost_attribution_report_json,
    render_llm_provider_cost_attribution_report_markdown,
)
from max.exports.signal_source_quota_burn_report import (
    build_signal_source_quota_burn_report,
    render_signal_source_quota_burn_report_json,
    render_signal_source_quota_burn_report_markdown,
)
from max.exports.source_signal_drop_reason_report import (
    build_source_signal_drop_reason_report,
    render_source_signal_drop_reason_report_json,
    render_source_signal_drop_reason_report_markdown,
)
from max.exports.spec_generation_rework_report import (
    build_spec_generation_rework_report,
    render_spec_generation_rework_report_json,
    render_spec_generation_rework_report_markdown,
)

__all__ = [
    "build_source_adapter_reliability_report",
    "build_source_adapter_coverage_gap_report",
    "build_source_adapter_version_skew_report",
    "build_source_oauth_scope_drift_report",
    "build_source_cost_efficiency_report",
    "build_source_auth_failure_trend_report",
    "build_source_backfill_gap_report",
    "build_source_circuit_breaker_churn_report",
    "generate_cache_key_churn_report",
    "generate_evaluation_rubric_drift_remediation_report",
    "render_evaluation_rubric_drift_remediation_report_json",
    "render_evaluation_rubric_drift_remediation_report_markdown",
    "generate_prompt_redaction_leak_report",
    "render_prompt_redaction_leak_report_json",
    "render_prompt_redaction_leak_report_markdown",
    "generate_synthesis_insight_aging_report",
    "render_synthesis_insight_aging_report_json",
    "render_synthesis_insight_aging_report_markdown",
    "generate_publisher_auth_expiry_forecast_report",
    "render_publisher_auth_expiry_forecast_report_json",
    "render_publisher_auth_expiry_forecast_report_markdown",
    "generate_spec_approval_bottleneck_report",
    "render_spec_approval_bottleneck_report_json",
    "render_spec_approval_bottleneck_report_markdown",
    "build_llm_provider_cost_attribution_report_export",
    "render_llm_provider_cost_attribution_report_json",
    "render_llm_provider_cost_attribution_report_markdown",
    "build_signal_source_quota_burn_report",
    "render_signal_source_quota_burn_report_json",
    "render_signal_source_quota_burn_report_markdown",
    "build_source_signal_drop_reason_report",
    "render_source_signal_drop_reason_report_json",
    "render_source_signal_drop_reason_report_markdown",
    "build_spec_generation_rework_report",
    "render_spec_generation_rework_report_json",
    "render_spec_generation_rework_report_markdown",
    "build_source_duplicate_signal_report",
    "build_source_field_completeness_report",
    "build_source_freshness_sla_report",
    "build_source_payload_parse_failure_report",
    "build_source_rate_limit_saturation_report",
    "build_source_schema_drift_report",
    "build_signal_freshness_sla_report",
    "build_source_allocation_efficiency_report",
    "build_insight_deduplication_collision_report",
    "build_spec_evidence_trace_completeness_report",
    "build_profile_weight_sensitivity_report",
    "build_llm_budget_variance_report",
    "build_evaluation_score_drift_report",
    "build_tact_spec_generation_failure_report",
    "build_spec_review_rework_rate_report",
    "build_publisher_delivery_time_sla_report",
    "build_profile_constraint_violation_report",
    "build_feedback_signal_quality_report",
    "build_insight_attribution_completeness_report",
    "build_prompt_injection_attempt_trend_report",
    "build_llm_provider_cost_comparison_report",
    "build_inference_latency_percentile_report",
    "build_evaluation_dataset_coverage_report",
    "build_insight_to_unit_conversion_funnel_report",
    "build_idea_recommendation_mix_report",
    "build_profile_idea_throughput_report",
    "build_evidence_trace_depth_report",
    "build_buildable_unit_readiness_blocker_report",
    "build_publication_destination_latency_report",
    "build_feedback_weight_shift_report",
    "build_insight_contradiction_rate_report",
    "build_evaluation_override_frequency_report",
    "build_spec_generation_queue_aging_report",
    "build_feedback_label_disagreement_report",
    "build_profile_signal_mix_report",
    "build_publication_channel_effectiveness_report",
    "build_model_context_window_pressure_report",
    "build_safety_mitigation_escape_report",
    "build_prompt_template_drift_report",
    "build_compliance_evidence_packet",
    "build_compliance_questionnaire_gap_export",
    "build_customer_adoption_risk_index_export",
    "build_customer_success_qbr_export",
    "build_customer_reference_readiness_export",
    "build_customer_escalation_risk_report_export",
    "build_customer_churn_save_playbook_export",
    "build_customer_adoption_risk_index_export",
    "build_customer_journey_friction_report_export",
    "export_customer_value_realization",
    "build_expansion_readiness_scorecard_export",
    "build_enterprise_security_questionnaire_export",
    "build_enterprise_pilot_success_scorecard_export",
    "build_retention_cohort_export",
    "build_api_quota_utilization_export",
    "build_account_health_score_export",
    "build_buyer_committee_alignment_export",
    "build_data_residency_matrix_export",
    "build_data_processing_agreement_renewal_report_export",
    "build_feature_adoption_cohorts_export",
    "build_feature_entitlement_revenue_leakage_report_export",
    "build_feature_request_revenue_map_export",
    "build_incident_impact_assessment_export",
    "build_incident_sla_breach_trend_report_export",
    "build_implementation_risk_heatmap_export",
    "build_implementation_timeline_variance_report_export",
    "build_integration_dependency_health_export",
    "build_integration_readiness_matrix_export",
    "build_integration_sla_compliance_report_export",
    "build_investment_case",
    "build_localization_readiness_export",
    "export_onboarding_activation_cohorts",
    "build_partner_ecosystem_map_export",
    "build_partner_referral_pipeline_coverage_report_export",
    "build_pricing_sensitivity_report",
    "build_pricing_discount_leakage_report_export",
    "build_procurement_readiness_checklist_export",
    "build_procurement_cycle_friction_export",
    "build_proof_of_concept_roi_export",
    "build_competitive_landscape",
    "build_competitive_win_loss_export",
    "build_product_usage_segmentation_export",
    "build_release_readiness_scorecard_export",
    "build_license_utilization_drift_report_export",
    "build_revenue_leakage_diagnostic_export",
    "build_roadmap_prioritization_export",
    "build_sales_pipeline_forecast",
    "build_sales_engineering_capacity_plan_export",
    "build_security_review_intake_packet_export",
    "build_security_questionnaire_evidence_aging_report_export",
    "build_customer_migration_wave_readiness_report_export",
    "build_sla_breach_risk_export",
    "build_support_ticket_theme_report",
    "build_tech_radar",
    "build_tech_radar_export",
    "build_trial_conversion_funnel_export",
    "build_vendor_evaluation",
    "classify_radar_ring",
    "EvaluationCriterion",
    "RadarQuadrant",
    "RadarRing",
    "render_api_quota_utilization_csv",
    "render_api_quota_utilization_json",
    "render_api_quota_utilization_markdown",
    "render_account_health_score_json",
    "render_account_health_score_markdown",
    "render_buyer_committee_alignment_json",
    "render_buyer_committee_alignment_markdown",
    "render_data_residency_matrix_csv",
    "render_data_residency_matrix_json",
    "render_data_residency_matrix_markdown",
    "render_data_processing_agreement_renewal_report_json",
    "render_data_processing_agreement_renewal_report_markdown",
    "render_feature_adoption_cohorts_json",
    "render_feature_adoption_cohorts_markdown",
    "render_feature_entitlement_revenue_leakage_report_json",
    "render_feature_entitlement_revenue_leakage_report_markdown",
    "render_feature_request_revenue_map_json",
    "render_feature_request_revenue_map_markdown",
    "render_incident_impact_assessment_csv",
    "render_incident_impact_assessment_json",
    "render_incident_impact_assessment_markdown",
    "render_incident_sla_breach_trend_report_json",
    "render_incident_sla_breach_trend_report_markdown",
    "render_implementation_risk_heatmap_json",
    "render_implementation_risk_heatmap_markdown",
    "render_implementation_timeline_variance_report_json",
    "render_implementation_timeline_variance_report_markdown",
    "export_implementation_blocker_aging",
    "render_implementation_blocker_aging_json",
    "render_integration_dependency_health_csv",
    "render_integration_dependency_health_json",
    "render_integration_dependency_health_markdown",
    "render_integration_readiness_matrix_csv",
    "render_integration_readiness_matrix_json",
    "render_integration_readiness_matrix_markdown",
    "render_integration_sla_compliance_report_csv",
    "render_integration_sla_compliance_report_json",
    "render_integration_sla_compliance_report_markdown",
    "render_investment_case_json",
    "render_investment_case_markdown",
    "render_localization_readiness_csv",
    "render_localization_readiness_json",
    "render_localization_readiness_markdown",
    "render_onboarding_activation_cohorts_json",
    "render_partner_ecosystem_map_json",
    "render_partner_ecosystem_map_markdown",
    "render_partner_referral_pipeline_coverage_report_json",
    "render_partner_referral_pipeline_coverage_report_markdown",
    "export_partner_integration_risk_register",
    "render_partner_integration_risk_register_json",
    "render_competitive_landscape_json",
    "render_competitive_landscape_markdown",
    "render_competitive_win_loss_csv",
    "render_competitive_win_loss_json",
    "render_competitive_win_loss_markdown",
    "render_compliance_evidence_packet_csv",
    "render_compliance_evidence_packet_json",
    "render_compliance_evidence_packet_markdown",
    "render_compliance_questionnaire_gap_json",
    "render_compliance_questionnaire_gap_markdown",
    "render_customer_adoption_risk_index_json",
    "render_customer_adoption_risk_index_markdown",
    "render_customer_journey_friction_report_json",
    "render_customer_journey_friction_report_markdown",
    "render_customer_value_realization_json",
    "render_expansion_readiness_scorecard_json",
    "render_expansion_readiness_scorecard_markdown",
    "render_enterprise_security_questionnaire_json",
    "render_enterprise_security_questionnaire_markdown",
    "render_enterprise_pilot_success_scorecard_json",
    "render_enterprise_pilot_success_scorecard_markdown",
    "render_customer_success_qbr_csv",
    "render_customer_success_qbr_json",
    "render_customer_success_qbr_markdown",
    "render_customer_reference_readiness_json",
    "render_customer_reference_readiness_markdown",
    "render_customer_escalation_risk_report_json",
    "render_customer_escalation_risk_report_markdown",
    "render_customer_churn_save_playbook_json",
    "render_customer_churn_save_playbook_markdown",
    "render_customer_adoption_risk_index_json",
    "render_customer_adoption_risk_index_markdown",
    "render_product_usage_segmentation_csv",
    "render_product_usage_segmentation_json",
    "render_product_usage_segmentation_markdown",
    "render_pricing_sensitivity_csv",
    "render_pricing_sensitivity_json",
    "render_pricing_sensitivity_markdown",
    "render_pricing_discount_leakage_report_json",
    "render_pricing_discount_leakage_report_markdown",
    "render_procurement_readiness_checklist_json",
    "render_procurement_readiness_checklist_markdown",
    "render_procurement_cycle_friction_json",
    "render_procurement_cycle_friction_markdown",
    "render_proof_of_concept_roi_json",
    "render_proof_of_concept_roi_markdown",
    "render_release_readiness_scorecard_csv",
    "render_release_readiness_scorecard_json",
    "render_release_readiness_scorecard_markdown",
    "render_license_utilization_drift_report_json",
    "render_license_utilization_drift_report_markdown",
    "render_revenue_leakage_diagnostic_csv",
    "render_revenue_leakage_diagnostic_json",
    "render_revenue_leakage_diagnostic_markdown",
    "export_renewal_risk_register",
    "render_renewal_risk_register_json",
    "render_retention_cohort_json",
    "render_retention_cohort_markdown",
    "render_roadmap_prioritization_csv",
    "render_roadmap_prioritization_json",
    "render_roadmap_prioritization_markdown",
    "export_roadmap_commitment_tracker",
    "render_roadmap_commitment_tracker_json",
    "render_sales_pipeline_forecast_csv",
    "render_sales_pipeline_forecast_json",
    "render_sales_pipeline_forecast_markdown",
    "render_sales_engineering_capacity_plan_json",
    "render_sales_engineering_capacity_plan_markdown",
    "render_security_review_intake_packet_json",
    "render_security_review_intake_packet_markdown",
    "render_security_questionnaire_evidence_aging_report_json",
    "render_security_questionnaire_evidence_aging_report_markdown",
    "render_customer_migration_wave_readiness_report_json",
    "render_customer_migration_wave_readiness_report_markdown",
    "render_sla_breach_risk_csv",
    "render_sla_breach_risk_json",
    "render_sla_breach_risk_markdown",
    "render_support_ticket_theme_report_csv",
    "render_support_ticket_theme_report_json",
    "render_support_ticket_theme_report_markdown",
    "render_tech_radar_json",
    "render_tech_radar_markdown",
    "render_trial_conversion_funnel_json",
    "render_trial_conversion_funnel_markdown",
    "export_trial_to_paid_conversion_diagnostic",
    "render_trial_to_paid_conversion_diagnostic_json",
    "render_vendor_evaluation_csv",
    "render_vendor_evaluation_json",
    "render_vendor_evaluation_markdown",
    "render_source_adapter_reliability_json",
    "render_source_adapter_reliability_markdown",
    "render_source_adapter_coverage_gap_report_json",
    "render_source_adapter_coverage_gap_report_markdown",
    "render_source_adapter_version_skew_report_json",
    "render_source_adapter_version_skew_report_markdown",
    "render_source_oauth_scope_drift_report_json",
    "render_source_oauth_scope_drift_report_markdown",
    "render_source_cost_efficiency_report_json",
    "render_source_cost_efficiency_report_markdown",
    "render_source_auth_failure_trend_report_json",
    "render_source_auth_failure_trend_report_markdown",
    "render_source_backfill_gap_report_json",
    "render_source_backfill_gap_report_markdown",
    "render_source_circuit_breaker_churn_report_json",
    "render_source_circuit_breaker_churn_report_markdown",
    "render_cache_key_churn_report_json",
    "render_source_duplicate_signal_report_json",
    "render_source_duplicate_signal_report_markdown",
    "render_source_field_completeness_report_json",
    "render_source_field_completeness_report_markdown",
    "render_source_freshness_sla_report_json",
    "render_source_freshness_sla_report_markdown",
    "render_source_payload_parse_failure_report_json",
    "render_source_payload_parse_failure_report_markdown",
    "render_source_rate_limit_saturation_report_json",
    "render_source_rate_limit_saturation_report_markdown",
    "render_source_schema_drift_report_json",
    "render_source_schema_drift_report_markdown",
    "render_signal_freshness_sla_report_json",
    "render_signal_freshness_sla_report_markdown",
    "render_source_allocation_efficiency_json",
    "render_source_allocation_efficiency_markdown",
    "render_insight_deduplication_collision_json",
    "render_insight_deduplication_collision_markdown",
    "render_spec_evidence_trace_completeness_report_json",
    "render_spec_evidence_trace_completeness_report_markdown",
    "render_profile_weight_sensitivity_report_json",
    "render_profile_weight_sensitivity_report_markdown",
    "render_llm_budget_variance_report_json",
    "render_llm_budget_variance_report_markdown",
    "render_evaluation_score_drift_report_json",
    "render_evaluation_score_drift_report_markdown",
    "render_tact_spec_generation_failure_report_json",
    "render_tact_spec_generation_failure_report_markdown",
    "render_spec_review_rework_rate_report_json",
    "render_spec_review_rework_rate_report_markdown",
    "render_publisher_delivery_time_sla_report_json",
    "render_publisher_delivery_time_sla_report_markdown",
    "render_profile_constraint_violation_report_json",
    "render_profile_constraint_violation_report_markdown",
    "render_feedback_signal_quality_report_json",
    "render_feedback_signal_quality_report_markdown",
    "render_insight_attribution_completeness_report_json",
    "render_insight_attribution_completeness_report_markdown",
    "render_prompt_injection_attempt_trend_report_json",
    "render_prompt_injection_attempt_trend_report_markdown",
    "render_llm_provider_cost_comparison_report_json",
    "render_llm_provider_cost_comparison_report_markdown",
    "render_inference_latency_percentile_report_json",
    "render_inference_latency_percentile_report_markdown",
    "render_evaluation_dataset_coverage_report_json",
    "render_evaluation_dataset_coverage_report_markdown",
    "render_insight_to_unit_conversion_funnel_report_json",
    "render_insight_to_unit_conversion_funnel_report_markdown",
    "render_idea_recommendation_mix_report_json",
    "render_idea_recommendation_mix_report_markdown",
    "render_profile_idea_throughput_report_json",
    "render_profile_idea_throughput_report_markdown",
    "render_evidence_trace_depth_report_json",
    "render_evidence_trace_depth_report_markdown",
    "render_buildable_unit_readiness_blocker_report_json",
    "render_buildable_unit_readiness_blocker_report_markdown",
    "render_publication_destination_latency_report_json",
    "render_publication_destination_latency_report_markdown",
    "render_feedback_weight_shift_report_json",
    "render_feedback_weight_shift_report_markdown",
    "render_insight_contradiction_rate_report_json",
    "render_insight_contradiction_rate_report_markdown",
    "render_evaluation_override_frequency_report_json",
    "render_evaluation_override_frequency_report_markdown",
    "render_spec_generation_queue_aging_report_json",
    "render_spec_generation_queue_aging_report_markdown",
    "render_feedback_label_disagreement_report_json",
    "render_feedback_label_disagreement_report_markdown",
    "render_profile_signal_mix_report_json",
    "render_profile_signal_mix_report_markdown",
    "render_publication_channel_effectiveness_report_json",
    "render_publication_channel_effectiveness_report_markdown",
    "render_model_context_window_pressure_report_json",
    "render_model_context_window_pressure_report_markdown",
    "render_safety_mitigation_escape_report_json",
    "render_safety_mitigation_escape_report_markdown",
    "render_prompt_template_drift_report_json",
    "render_prompt_template_drift_report_markdown",
    "build_budget_overrun_root_cause_report",
    "render_budget_overrun_root_cause_report_json",
    "render_budget_overrun_root_cause_report_markdown",
    "build_idea_review_cycle_time_report",
    "render_idea_review_cycle_time_report_json",
    "render_idea_review_cycle_time_report_markdown",
    "build_insight_evidence_staleness_report",
    "render_insight_evidence_staleness_report_json",
    "render_insight_evidence_staleness_report_markdown",
    "build_insight_confidence_decay_report_export",
    "render_insight_confidence_decay_report_json",
    "render_insight_confidence_decay_report_markdown",
    "build_buildable_unit_stack_diversity_report_export",
    "render_buildable_unit_stack_diversity_report_json",
    "render_buildable_unit_stack_diversity_report_markdown",
    "build_idea_aging_sla_report_export",
    "render_idea_aging_sla_report_json",
    "render_idea_aging_sla_report_markdown",
    "build_profile_coverage_drift_report",
    "render_profile_coverage_drift_report_json",
    "render_profile_coverage_drift_report_markdown",
    "build_publisher_retry_backlog_report",
    "render_publisher_retry_backlog_report_json",
    "render_publisher_retry_backlog_report_markdown",
    "build_signal_source_noise_report",
    "render_signal_source_noise_report_json",
    "render_signal_source_noise_report_markdown",
    "generate_synthesis_batch_backlog_report",
    "render_synthesis_batch_backlog_json",
    "generate_eval_goldens_coverage_gap_report",
    "generate_embedding_dimension_mismatch_report",
    "generate_profile_weight_conflict_report",
    "generate_domain_profile_constraint_violation_report",
    "generate_signal_ingestion_lag_report",
    "generate_synthesis_prompt_failure_report",
    "generate_idea_duplicate_cluster_report",
    "generate_llm_token_budget_leak_report",
    "generate_insight_evidence_source_concentration_report",
    "generate_buildable_unit_dependency_freshness_report",
    "generate_buildable_unit_scope_creep_report",
    "generate_feedback_reviewer_throughput_forecast_report",
    "generate_insight_gap_detection_precision_report",
    "generate_llm_provider_failover_drill_report",
    "generate_publication_destination_cost_spike_report",
    "generate_spec_publication_rollback_readiness_report",
    "generate_ideation_mode_conversion_funnel_report",
    "generate_retrospective_feedback_outcome_skew_report",
    "generate_feedback_recency_decay_report",
    "generate_idea_stack_concentration_report",
    "generate_insight_evidence_trace_depth_report",
    "generate_insight_novelty_collision_report",
    "generate_llm_cost_anomaly_report",
    "generate_profile_source_mix_drift_report",
    "generate_publication_target_failure_cluster_report",
    "generate_signal_annotation_gap_report",
    "generate_source_credential_scope_report",
    "generate_spec_evidence_trace_gap_report",
]
