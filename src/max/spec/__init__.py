"""Tact-compatible spec preview generation."""

from max.spec.experiment_card import generate_experiment_card
from max.spec.acceptance_criteria import (
    generate_acceptance_criteria,
    render_acceptance_criteria_markdown,
)
from max.spec.api_contract_test_plan import (
    KIND as API_CONTRACT_TEST_PLAN_KIND,
    SCHEMA_VERSION as API_CONTRACT_TEST_PLAN_SCHEMA_VERSION,
    generate_api_contract_test_plan,
    render_api_contract_test_plan_markdown,
)
from max.spec.adr import (
    generate_architecture_decision_record,
    render_architecture_decision_record_markdown,
)
from max.spec.bundle import (
    generate_spec_bundle,
    render_spec_bundle_markdown,
    render_spec_bundle_yaml,
)
from max.spec.compliance_checklist import (
    generate_compliance_checklist,
    render_compliance_checklist_json,
    render_compliance_checklist_markdown,
)
from max.spec.cost_estimate import generate_cost_estimate, render_cost_estimate_markdown
from max.spec.customer_onboarding_plan import (
    generate_customer_onboarding_plan,
    render_customer_onboarding_plan_csv,
    render_customer_onboarding_plan_markdown,
)
from max.spec.data_classification import (
    generate_data_classification,
    render_data_classification_markdown,
)
from max.spec.data_retention_schedule import (
    generate_data_retention_schedule,
    render_data_retention_schedule_markdown,
)
from max.spec.dependency_inventory import (
    generate_dependency_inventory,
    render_dependency_inventory_markdown,
)
from max.spec.deployment_topology import (
    generate_deployment_topology,
    render_deployment_topology_csv,
    render_deployment_topology_markdown,
)
from max.spec.disaster_recovery_plan import (
    generate_disaster_recovery_plan,
    render_disaster_recovery_plan_csv,
    render_disaster_recovery_plan_markdown,
)
from max.spec.generator import generate_spec_preview
from max.spec.implementation_plan import (
    generate_implementation_plan,
    render_implementation_plan_markdown,
)
from max.spec.incident_response_plan import (
    generate_incident_response_plan,
    render_incident_response_plan_csv,
    render_incident_response_plan_markdown,
)
from max.spec.launch_checklist import generate_launch_checklist
from max.spec.migration_checklist import (
    generate_migration_checklist,
    render_migration_checklist_markdown,
)
from max.spec.observability_plan import (
    generate_observability_plan,
    render_observability_plan_markdown,
)
from max.spec.operational_runbook import (
    generate_operational_runbook,
    render_operational_runbook_markdown,
)
from max.spec.post_launch_monitoring_plan import (
    generate_post_launch_monitoring_plan,
    render_post_launch_monitoring_plan_csv,
    render_post_launch_monitoring_plan_markdown,
)
from max.spec.privacy_impact_assessment import (
    generate_privacy_impact_assessment,
    render_privacy_impact_assessment_markdown,
)
from max.spec.readiness import evaluate_spec_readiness
from max.spec.release_readiness_gate import (
    generate_release_readiness_gate,
    render_release_readiness_gate_csv,
    render_release_readiness_gate_markdown,
)
from max.spec.rollback_plan import generate_rollback_plan, render_rollback_plan_markdown
from max.spec.risk_register import (
    generate_risk_register,
    render_risk_register_csv,
    render_risk_register_markdown,
)
from max.spec.security_review import (
    generate_security_review,
    render_security_review_csv,
    render_security_review_markdown,
)
from max.spec.slo_plan import generate_slo_plan, render_slo_plan_csv, render_slo_plan_markdown
from max.spec.smoke_test_plan import (
    generate_smoke_test_plan,
    render_smoke_test_plan_csv,
    render_smoke_test_plan_markdown,
)
from max.spec.stakeholder_handoff import (
    generate_stakeholder_handoff,
    render_stakeholder_handoff_markdown,
)
from max.spec.support_playbook import (
    generate_support_playbook,
    render_support_playbook_csv,
    render_support_playbook_markdown,
)
from max.spec.threat_model import (
    generate_threat_model,
    render_threat_model_csv,
    render_threat_model_markdown,
)
from max.spec.vendor_risk_assessment import (
    generate_vendor_risk_assessment,
    render_vendor_risk_assessment_csv,
    render_vendor_risk_assessment_markdown,
)

__all__ = [
    "evaluate_spec_readiness",
    "API_CONTRACT_TEST_PLAN_KIND",
    "API_CONTRACT_TEST_PLAN_SCHEMA_VERSION",
    "generate_acceptance_criteria",
    "render_acceptance_criteria_markdown",
    "generate_api_contract_test_plan",
    "generate_architecture_decision_record",
    "generate_compliance_checklist",
    "generate_cost_estimate",
    "generate_customer_onboarding_plan",
    "generate_data_classification",
    "generate_data_retention_schedule",
    "generate_dependency_inventory",
    "generate_deployment_topology",
    "generate_disaster_recovery_plan",
    "generate_experiment_card",
    "generate_implementation_plan",
    "render_implementation_plan_markdown",
    "generate_incident_response_plan",
    "generate_launch_checklist",
    "generate_migration_checklist",
    "generate_observability_plan",
    "generate_operational_runbook",
    "generate_post_launch_monitoring_plan",
    "generate_privacy_impact_assessment",
    "generate_release_readiness_gate",
    "generate_rollback_plan",
    "generate_spec_bundle",
    "generate_security_review",
    "generate_slo_plan",
    "generate_smoke_test_plan",
    "generate_stakeholder_handoff",
    "generate_support_playbook",
    "generate_risk_register",
    "generate_threat_model",
    "generate_vendor_risk_assessment",
    "render_rollback_plan_markdown",
    "render_risk_register_csv",
    "render_risk_register_markdown",
    "render_security_review_csv",
    "render_security_review_markdown",
    "render_slo_plan_csv",
    "render_slo_plan_markdown",
    "render_smoke_test_plan_csv",
    "render_smoke_test_plan_markdown",
    "render_support_playbook_csv",
    "render_support_playbook_markdown",
    "render_threat_model_csv",
    "render_threat_model_markdown",
    "render_vendor_risk_assessment_csv",
    "render_vendor_risk_assessment_markdown",
    "render_architecture_decision_record_markdown",
    "render_api_contract_test_plan_markdown",
    "render_compliance_checklist_json",
    "render_compliance_checklist_markdown",
    "render_cost_estimate_markdown",
    "render_customer_onboarding_plan_csv",
    "render_customer_onboarding_plan_markdown",
    "render_data_classification_markdown",
    "render_data_retention_schedule_markdown",
    "render_dependency_inventory_markdown",
    "render_deployment_topology_csv",
    "render_deployment_topology_markdown",
    "render_disaster_recovery_plan_markdown",
    "render_disaster_recovery_plan_csv",
    "render_incident_response_plan_markdown",
    "render_incident_response_plan_csv",
    "render_migration_checklist_markdown",
    "render_observability_plan_markdown",
    "render_operational_runbook_markdown",
    "render_post_launch_monitoring_plan_csv",
    "render_post_launch_monitoring_plan_markdown",
    "render_privacy_impact_assessment_markdown",
    "render_release_readiness_gate_csv",
    "render_release_readiness_gate_markdown",
    "render_spec_bundle_yaml",
    "generate_spec_preview",
    "render_spec_bundle_markdown",
    "render_stakeholder_handoff_markdown",
]
