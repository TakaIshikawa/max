"""Deterministic infrastructure requirements exports for persisted design briefs."""

from __future__ import annotations

from typing import Any

from max.store.db import Store

SCHEMA_VERSION = "max.design_brief.infrastructure_requirements.v1"
KIND = "max.design_brief.infrastructure_requirements"


def build_design_brief_infrastructure_requirements(
    store: Store, brief_id: str
) -> dict[str, Any] | None:
    """Build infrastructure requirements document from a persisted design brief."""
    design_brief = store.get_design_brief(brief_id)
    if not design_brief:
        return None

    source_ideas = _source_ideas(store, design_brief)
    source_idea_ids = [idea["id"] for idea in source_ideas if not idea.get("missing")]
    if not source_idea_ids:
        source_idea_ids = list(design_brief.get("source_idea_ids") or [])

    context = _infrastructure_context(design_brief, source_ideas)
    compute_resources = _compute_resources(context, source_idea_ids)
    storage_requirements = _storage_requirements(context, source_idea_ids)
    network_config = _network_configuration(context, source_idea_ids)
    database_specs = _database_specifications(context, source_idea_ids)
    caching_layers = _caching_layers(context, source_idea_ids)
    cdn_setup = _cdn_setup(context, source_idea_ids)
    cloud_services = _cloud_service_dependencies(context, source_idea_ids)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
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
            "lead_idea_id": design_brief.get("lead_idea_id", ""),
            "source_idea_ids": source_idea_ids,
        },
        "summary": {
            "infrastructure_goal": f"Define infrastructure requirements for {design_brief['title']}.",
            "compute_tier": compute_resources.get("tier", "standard"),
            "storage_total_gb": sum(s["capacity_gb"] for s in storage_requirements),
            "database_count": len(database_specs),
            "cloud_service_count": len(cloud_services),
        },
        "compute_resources": compute_resources,
        "storage_requirements": storage_requirements,
        "network_configuration": network_config,
        "database_specifications": database_specs,
        "caching_layers": caching_layers,
        "cdn_setup": cdn_setup,
        "cloud_service_dependencies": cloud_services,
        "source_ideas": source_ideas,
    }


def render_design_brief_infrastructure_requirements_markdown(infra: dict[str, Any]) -> str:
    """Render the infrastructure requirements document as formatted markdown."""
    brief = infra["design_brief"]
    summary = infra["summary"]
    compute = infra["compute_resources"]
    storage = infra["storage_requirements"]
    network = infra["network_configuration"]
    databases = infra["database_specifications"]
    caching = infra["caching_layers"]
    cdn = infra["cdn_setup"]
    cloud_services = infra["cloud_service_dependencies"]

    lines = [
        f"# {brief['title']} Infrastructure Requirements",
        "",
        f"**Brief ID**: {brief['id']}",
        f"**Domain**: {brief['domain']}",
        f"**Theme**: {brief['theme']}",
        f"**Design Status**: {brief['design_status']}",
        f"**Readiness Score**: {brief['readiness_score']}",
        "",
        "## Summary",
        "",
        f"- **Infrastructure Goal**: {summary['infrastructure_goal']}",
        f"- **Compute Tier**: {summary['compute_tier']}",
        f"- **Total Storage**: {summary['storage_total_gb']} GB",
        f"- **Database Count**: {summary['database_count']}",
        f"- **Cloud Services**: {summary['cloud_service_count']}",
        "",
        "## Compute Resources",
        "",
        f"- **Tier**: {compute.get('tier', 'standard')}",
        f"- **CPU**: {compute.get('cpu_cores', 0)} cores",
        f"- **Memory**: {compute.get('memory_gb', 0)} GB",
        f"- **Auto-scaling**: {compute.get('auto_scaling', 'disabled')}",
        "",
    ]

    if compute.get("instance_types"):
        lines.append("### Instance Types")
        lines.append("")
        lines.append("| Type | vCPU | Memory | Storage |")
        lines.append("|------|------|--------|---------|")
        for instance in compute["instance_types"]:
            lines.append(f"| {instance['type']} | {instance['vcpu']} | {instance['memory']} | {instance['storage']} |")
        lines.append("")

    lines.extend([
        "## Storage Requirements",
        "",
    ])

    if storage:
        lines.append("| Storage Type | Purpose | Capacity (GB) | IOPS | Backup Frequency |")
        lines.append("|--------------|---------|---------------|------|------------------|")
        for stor in storage:
            lines.append(f"| {stor['type']} | {stor['purpose']} | {stor['capacity_gb']} | {stor['iops']} | {stor['backup_frequency']} |")
        lines.append("")
    else:
        lines.append("No storage requirements defined.")
        lines.append("")

    lines.extend([
        "## Network Configuration",
        "",
        f"- **VPC CIDR**: {network.get('vpc_cidr', 'N/A')}",
        f"- **Subnets**: {network.get('subnet_count', 0)}",
        f"- **Load Balancing**: {network.get('load_balancing', 'disabled')}",
        f"- **CDN**: {network.get('cdn_enabled', 'no')}",
        "",
    ])

    if network.get("security_groups"):
        lines.append("### Security Groups")
        lines.append("")
        for sg in network["security_groups"]:
            lines.extend([
                f"**{sg['name']}**:",
                f"- Protocol: {sg['protocol']}",
                f"- Port Range: {sg['port_range']}",
                f"- Source: {sg['source']}",
                "",
            ])

    lines.extend([
        "## Database Specifications",
        "",
    ])

    if databases:
        lines.append("| Database ID | Type | Engine | Size (GB) | Replicas | Backup |")
        lines.append("|-------------|------|--------|-----------|----------|--------|")
        for db in databases:
            lines.append(f"| {db['id']} | {db['type']} | {db['engine']} | {db['size_gb']} | {db['replicas']} | {db['backup_retention_days']} days |")
        lines.append("")
    else:
        lines.append("No database specifications defined.")
        lines.append("")

    lines.extend([
        "## Caching Layers",
        "",
    ])

    if caching.get("cache_services"):
        for cache in caching["cache_services"]:
            lines.extend([
                f"### {cache['name']}",
                "",
                f"- **Type**: {cache['type']}",
                f"- **Size**: {cache['size_gb']} GB",
                f"- **Eviction Policy**: {cache['eviction_policy']}",
                f"- **TTL**: {cache['default_ttl']}",
                "",
            ])
    else:
        lines.append("No caching layers defined.")
        lines.append("")

    lines.extend([
        "## CDN Setup",
        "",
    ])

    if cdn.get("enabled"):
        lines.extend([
            f"- **Provider**: {cdn.get('provider', 'N/A')}",
            f"- **Edge Locations**: {cdn.get('edge_location_count', 0)}",
            f"- **Cache TTL**: {cdn.get('cache_ttl', 'N/A')}",
            f"- **SSL/TLS**: {cdn.get('ssl_enabled', 'no')}",
            "",
        ])
    else:
        lines.append("CDN not required.")
        lines.append("")

    lines.extend([
        "## Cloud Service Dependencies",
        "",
    ])

    if cloud_services:
        lines.append("| Service ID | Name | Provider | Purpose | Cost Tier |")
        lines.append("|------------|------|----------|---------|-----------|")
        for svc in cloud_services:
            lines.append(f"| {svc['id']} | {svc['name']} | {svc['provider']} | {svc['purpose']} | {svc['cost_tier']} |")
        lines.append("")
    else:
        lines.append("No cloud service dependencies defined.")
        lines.append("")

    return "\n".join(lines)


def _source_ideas(store: Store, design_brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Load source buildable ideas from the design brief."""
    idea_ids = design_brief.get("source_idea_ids") or []
    ideas: list[dict[str, Any]] = []
    for idea_id in idea_ids:
        unit = store.get_buildable_unit(idea_id)
        if unit:
            ideas.append({
                "id": unit.id,
                "title": unit.title,
                "category": str(unit.category),
                "domain": unit.domain,
            })
        else:
            ideas.append({"id": idea_id, "missing": True})
    return ideas


def _infrastructure_context(
    design_brief: dict[str, Any], source_ideas: list[dict[str, Any]]
) -> dict[str, Any]:
    """Build context for infrastructure planning from design brief and source ideas."""
    return {
        "title": design_brief["title"],
        "theme": design_brief.get("theme", ""),
        "domain": design_brief.get("domain", ""),
        "idea_count": len([i for i in source_ideas if not i.get("missing")]),
    }


def _compute_resources(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Generate compute resource requirements."""
    return {
        "tier": "standard",
        "cpu_cores": 8,
        "memory_gb": 16,
        "auto_scaling": "enabled",
        "instance_types": [
            {
                "type": "web_server",
                "vcpu": "4",
                "memory": "8 GB",
                "storage": "100 GB SSD",
            },
            {
                "type": "app_server",
                "vcpu": "8",
                "memory": "16 GB",
                "storage": "200 GB SSD",
            },
        ],
    }


def _storage_requirements(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    """Generate storage requirements."""
    return [
        {
            "type": "SSD",
            "purpose": "Application data",
            "capacity_gb": 500,
            "iops": 3000,
            "backup_frequency": "daily",
        },
        {
            "type": "S3",
            "purpose": "Object storage",
            "capacity_gb": 1000,
            "iops": 1000,
            "backup_frequency": "weekly",
        },
    ]


def _network_configuration(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Generate network configuration."""
    return {
        "vpc_cidr": "10.0.0.0/16",
        "subnet_count": 3,
        "load_balancing": "enabled",
        "cdn_enabled": "yes",
        "security_groups": [
            {
                "name": "web_tier",
                "protocol": "HTTPS",
                "port_range": "443",
                "source": "0.0.0.0/0",
            },
            {
                "name": "app_tier",
                "protocol": "TCP",
                "port_range": "8080",
                "source": "10.0.1.0/24",
            },
        ],
    }


def _database_specifications(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    """Generate database specifications."""
    return [
        {
            "id": "primary_db",
            "type": "relational",
            "engine": "PostgreSQL 15",
            "size_gb": 100,
            "replicas": 2,
            "backup_retention_days": 7,
        },
        {
            "id": "analytics_db",
            "type": "timeseries",
            "engine": "InfluxDB",
            "size_gb": 50,
            "replicas": 1,
            "backup_retention_days": 30,
        },
    ]


def _caching_layers(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Generate caching layer specifications."""
    return {
        "cache_services": [
            {
                "name": "application_cache",
                "type": "Redis",
                "size_gb": 8,
                "eviction_policy": "LRU",
                "default_ttl": "3600s",
            },
        ],
    }


def _cdn_setup(context: dict[str, Any], source_idea_ids: list[str]) -> dict[str, Any]:
    """Generate CDN setup configuration."""
    return {
        "enabled": True,
        "provider": "CloudFront",
        "edge_location_count": 50,
        "cache_ttl": "86400s",
        "ssl_enabled": "yes",
    }


def _cloud_service_dependencies(context: dict[str, Any], source_idea_ids: list[str]) -> list[dict[str, Any]]:
    """Generate cloud service dependencies."""
    return [
        {
            "id": "svc_001",
            "name": "AWS S3",
            "provider": "AWS",
            "purpose": "Object storage",
            "cost_tier": "standard",
        },
        {
            "id": "svc_002",
            "name": "CloudWatch",
            "provider": "AWS",
            "purpose": "Monitoring and logging",
            "cost_tier": "standard",
        },
    ]
