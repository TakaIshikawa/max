"""Tests for design brief infrastructure requirements generation and markdown rendering."""

from __future__ import annotations

import pytest

from max.analysis.design_brief_infrastructure_requirements import (
    build_design_brief_infrastructure_requirements,
    render_design_brief_infrastructure_requirements_markdown,
)
from max.analysis.portfolio_synthesis import Candidate, ProjectBrief
from max.types.buildable_unit import BuildableCategory, BuildableUnit, IdeationMode


@pytest.fixture
def sample_design_brief_with_infra_data(store):
    """Create a sample design brief with infrastructure requirements data."""
    unit1 = BuildableUnit(
        id="bu-infra001",
        title="Cloud Storage Service",
        one_liner="Scalable cloud storage platform",
        category=BuildableCategory.APPLICATION,
        ideation_mode=IdeationMode.DIRECT,
        problem="Need scalable storage solution",
        solution="Cloud-native storage service with CDN",
        target_users="both",
        value_proposition="Reliable and fast storage",
        specific_user="platform engineer",
        domain="infrastructure",
    )
    store.insert_buildable_unit(unit1)

    brief = ProjectBrief(
        title="Infrastructure Requirements Test Brief",
        domain="infrastructure",
        theme="cloud-infrastructure",
        lead=Candidate(unit=unit1),
        supporting=[],
        readiness_score=88.0,
        why_this_now="Testing infrastructure requirements functionality",
    )
    brief_id = store.insert_design_brief(brief)
    return brief_id


def test_build_design_brief_infrastructure_requirements_creates_valid_structure(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)

    assert infra is not None
    assert infra["schema_version"] == "max.design_brief.infrastructure_requirements.v1"
    assert infra["kind"] == "max.design_brief.infrastructure_requirements"
    assert infra["design_brief"]["id"] == sample_design_brief_with_infra_data
    assert infra["design_brief"]["title"] == "Infrastructure Requirements Test Brief"


def test_build_design_brief_infrastructure_requirements_includes_all_sections(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)

    assert "compute_resources" in infra
    assert "storage_requirements" in infra
    assert "network_configuration" in infra
    assert "database_specifications" in infra
    assert "caching_layers" in infra
    assert "cdn_setup" in infra
    assert "cloud_service_dependencies" in infra
    assert "summary" in infra


def test_build_design_brief_infrastructure_requirements_summary_completeness(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)

    summary = infra["summary"]
    assert "infrastructure_goal" in summary
    assert "compute_tier" in summary
    assert "storage_total_gb" in summary
    assert "database_count" in summary
    assert "cloud_service_count" in summary
    assert summary["storage_total_gb"] > 0
    assert summary["database_count"] > 0


def test_render_design_brief_infrastructure_requirements_markdown_structure(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)
    markdown = render_design_brief_infrastructure_requirements_markdown(infra)

    assert "# Infrastructure Requirements Test Brief Infrastructure Requirements" in markdown
    assert "## Summary" in markdown
    assert "## Compute Resources" in markdown
    assert "## Storage Requirements" in markdown
    assert "## Network Configuration" in markdown
    assert "## Database Specifications" in markdown
    assert "## Caching Layers" in markdown
    assert "## CDN Setup" in markdown
    assert "## Cloud Service Dependencies" in markdown


def test_render_design_brief_infrastructure_requirements_markdown_tables(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)
    markdown = render_design_brief_infrastructure_requirements_markdown(infra)

    # Check for table headers
    assert "| Type | vCPU | Memory | Storage |" in markdown
    assert "| Storage Type | Purpose | Capacity (GB) | IOPS | Backup Frequency |" in markdown
    assert "| Database ID | Type | Engine | Size (GB) | Replicas | Backup |" in markdown
    assert "| Service ID | Name | Provider | Purpose | Cost Tier |" in markdown

    # Check for table separators
    assert "|------|------|--------|---------|" in markdown
    assert "|--------------|---------|---------------|------|------------------|" in markdown
    assert "|-------------|------|--------|-----------|----------|--------|" in markdown
    assert "|------------|------|----------|---------|-----------|" in markdown


def test_render_design_brief_infrastructure_requirements_markdown_completeness(
    store, sample_design_brief_with_infra_data
):
    infra = build_design_brief_infrastructure_requirements(store, sample_design_brief_with_infra_data)
    markdown = render_design_brief_infrastructure_requirements_markdown(infra)

    # Verify key data is present
    assert "Infrastructure Requirements Test Brief" in markdown
    assert "web_server" in markdown
    assert "app_server" in markdown
    assert "PostgreSQL" in markdown
    assert "Redis" in markdown
    assert "CloudFront" in markdown
    assert "AWS S3" in markdown
    assert "CloudWatch" in markdown
    assert "10.0.0.0/16" in markdown


def test_build_design_brief_infrastructure_requirements_returns_none_for_missing_brief(store):
    infra = build_design_brief_infrastructure_requirements(store, "nonexistent-brief-id")
    assert infra is None
