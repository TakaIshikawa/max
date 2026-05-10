"""Tests for Terraform module export — infrastructure-as-code generation."""

from __future__ import annotations

import pytest

from max.exports.terraform_modules import (
    SCHEMA_VERSION,
    SUPPORTED_PROVIDERS,
    build_terraform_module,
    render_terraform_hcl,
    _default_provider_config,
    _hcl_value,
    _validate_resource,
    _validate_variable,
    _validate_output,
    _validate_module_dep,
)


# ── Test Data ────────────────────────────────────────────────────────

AWS_INSTANCE_RESOURCE = {
    "type": "aws_instance",
    "name": "web_server",
    "attributes": {
        "ami": "ami-0c55b159cbfafe1f0",
        "instance_type": "t3.micro",
        "tags": {"Name": "web-server", "Environment": "production"},
    },
}

GCP_INSTANCE_RESOURCE = {
    "type": "google_compute_instance",
    "name": "app_server",
    "attributes": {
        "machine_type": "e2-medium",
        "zone": "us-central1-a",
        "name": "app-server",
    },
}

AZURE_RG_RESOURCE = {
    "type": "azurerm_resource_group",
    "name": "main",
    "attributes": {
        "name": "rg-main",
        "location": "eastus",
    },
}

SAMPLE_VARIABLES = [
    {
        "name": "instance_type",
        "type": "string",
        "description": "EC2 instance type",
        "default": "t3.micro",
    },
    {
        "name": "environment",
        "type": "string",
        "description": "Deployment environment",
    },
]

SAMPLE_OUTPUTS = [
    {
        "name": "instance_id",
        "value": "aws_instance.web_server.id",
        "description": "ID of the EC2 instance",
    },
    {
        "name": "public_ip",
        "value": "aws_instance.web_server.public_ip",
        "description": "Public IP of the instance",
    },
]

SAMPLE_MODULE_DEPS = [
    {
        "name": "vpc",
        "source": "terraform-aws-modules/vpc/aws",
        "version": "5.1.0",
        "inputs": {"cidr": "10.0.0.0/16"},
    },
]


# ── Unit tests: _hcl_value ───────────────────────────────────────────


def test_hcl_value_string() -> None:
    assert _hcl_value("hello") == '"hello"'


def test_hcl_value_bool() -> None:
    assert _hcl_value(True) == "true"
    assert _hcl_value(False) == "false"


def test_hcl_value_number() -> None:
    assert _hcl_value(42) == "42"
    assert _hcl_value(3.14) == "3.14"


def test_hcl_value_list() -> None:
    result = _hcl_value(["a", "b"])
    assert result == '["a", "b"]'


def test_hcl_value_dict() -> None:
    result = _hcl_value({"key": "val"})
    assert result == '{ key = "val" }'


def test_hcl_value_empty_dict() -> None:
    assert _hcl_value({}) == "{}"


# ── Unit tests: validation helpers ───────────────────────────────────


def test_validate_resource_full() -> None:
    result = _validate_resource(AWS_INSTANCE_RESOURCE)
    assert result["type"] == "aws_instance"
    assert result["name"] == "web_server"
    assert "ami" in result["attributes"]


def test_validate_resource_defaults() -> None:
    result = _validate_resource({})
    assert result["type"] == "null_resource"
    assert result["name"] == "unnamed"
    assert result["attributes"] == {}


def test_validate_variable_with_default() -> None:
    result = _validate_variable(SAMPLE_VARIABLES[0])
    assert result["name"] == "instance_type"
    assert result["type"] == "string"
    assert result["default"] == "t3.micro"


def test_validate_variable_without_default() -> None:
    result = _validate_variable(SAMPLE_VARIABLES[1])
    assert "default" not in result


def test_validate_output() -> None:
    result = _validate_output(SAMPLE_OUTPUTS[0])
    assert result["name"] == "instance_id"
    assert result["value"] == "aws_instance.web_server.id"


def test_validate_module_dep() -> None:
    result = _validate_module_dep(SAMPLE_MODULE_DEPS[0])
    assert result["name"] == "vpc"
    assert result["source"] == "terraform-aws-modules/vpc/aws"
    assert result["version"] == "5.1.0"
    assert result["inputs"]["cidr"] == "10.0.0.0/16"


# ── Unit tests: _default_provider_config ─────────────────────────────


def test_default_provider_config_aws() -> None:
    config = _default_provider_config("aws")
    assert config["region"] == "us-east-1"


def test_default_provider_config_google() -> None:
    config = _default_provider_config("google")
    assert "project" in config
    assert "region" in config


def test_default_provider_config_azurerm() -> None:
    config = _default_provider_config("azurerm")
    assert config == {}


# ── build_terraform_module tests ─────────────────────────────────────


def test_build_module_aws() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        variables=SAMPLE_VARIABLES,
        outputs=SAMPLE_OUTPUTS,
    )
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == "max.terraform_modules"
    assert doc["provider"] == "aws"
    assert len(doc["resources"]) == 1
    assert len(doc["variables"]) == 2
    assert len(doc["outputs"]) == 2


def test_build_module_google() -> None:
    doc = build_terraform_module(
        [GCP_INSTANCE_RESOURCE],
        provider="google",
    )
    assert doc["provider"] == "google"
    assert doc["provider_config"]["project"] == "my-project"


def test_build_module_azurerm() -> None:
    doc = build_terraform_module(
        [AZURE_RG_RESOURCE],
        provider="azurerm",
    )
    assert doc["provider"] == "azurerm"


def test_build_module_unsupported_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported provider"):
        build_terraform_module([AWS_INSTANCE_RESOURCE], provider="oracle")


def test_build_module_with_dependencies() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        module_dependencies=SAMPLE_MODULE_DEPS,
    )
    assert len(doc["module_dependencies"]) == 1
    assert doc["module_dependencies"][0]["name"] == "vpc"


def test_build_module_custom_provider_config() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        provider_config={"region": "eu-west-1", "profile": "production"},
    )
    assert doc["provider_config"]["region"] == "eu-west-1"
    assert doc["provider_config"]["profile"] == "production"


def test_build_module_custom_terraform_version() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        terraform_version=">= 1.7.0",
    )
    assert doc["terraform_version"] == ">= 1.7.0"


# ── render_terraform_hcl tests ───────────────────────────────────────


def test_render_hcl_contains_terraform_block() -> None:
    doc = build_terraform_module([AWS_INSTANCE_RESOURCE], provider="aws")
    hcl = render_terraform_hcl(doc)
    assert "terraform {" in hcl
    assert "required_version" in hcl
    assert "required_providers" in hcl
    assert "hashicorp/aws" in hcl


def test_render_hcl_contains_provider_block() -> None:
    doc = build_terraform_module([AWS_INSTANCE_RESOURCE], provider="aws")
    hcl = render_terraform_hcl(doc)
    assert 'provider "aws"' in hcl
    assert "us-east-1" in hcl


def test_render_hcl_contains_resource_block() -> None:
    doc = build_terraform_module([AWS_INSTANCE_RESOURCE], provider="aws")
    hcl = render_terraform_hcl(doc)
    assert 'resource "aws_instance" "web_server"' in hcl
    assert "ami-0c55b159cbfafe1f0" in hcl
    assert "t3.micro" in hcl


def test_render_hcl_contains_variables() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        variables=SAMPLE_VARIABLES,
    )
    hcl = render_terraform_hcl(doc)
    assert 'variable "instance_type"' in hcl
    assert 'variable "environment"' in hcl
    assert "EC2 instance type" in hcl
    assert 'default     = "t3.micro"' in hcl


def test_render_hcl_contains_outputs() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        outputs=SAMPLE_OUTPUTS,
    )
    hcl = render_terraform_hcl(doc)
    assert 'output "instance_id"' in hcl
    assert 'output "public_ip"' in hcl
    assert "aws_instance.web_server.id" in hcl


def test_render_hcl_contains_module_deps() -> None:
    doc = build_terraform_module(
        [AWS_INSTANCE_RESOURCE],
        provider="aws",
        module_dependencies=SAMPLE_MODULE_DEPS,
    )
    hcl = render_terraform_hcl(doc)
    assert 'module "vpc"' in hcl
    assert "terraform-aws-modules/vpc/aws" in hcl
    assert "5.1.0" in hcl
    assert "10.0.0.0/16" in hcl


def test_render_hcl_google_provider() -> None:
    doc = build_terraform_module([GCP_INSTANCE_RESOURCE], provider="google")
    hcl = render_terraform_hcl(doc)
    assert 'provider "google"' in hcl
    assert "hashicorp/google" in hcl
    assert "my-project" in hcl


def test_render_hcl_azurerm_provider() -> None:
    doc = build_terraform_module([AZURE_RG_RESOURCE], provider="azurerm")
    hcl = render_terraform_hcl(doc)
    assert 'provider "azurerm"' in hcl
    assert "hashicorp/azurerm" in hcl


def test_render_hcl_multiple_resources() -> None:
    resources = [
        AWS_INSTANCE_RESOURCE,
        {
            "type": "aws_security_group",
            "name": "web_sg",
            "attributes": {"name": "web-sg", "vpc_id": "vpc-123"},
        },
    ]
    doc = build_terraform_module(resources, provider="aws")
    hcl = render_terraform_hcl(doc)
    assert 'resource "aws_instance" "web_server"' in hcl
    assert 'resource "aws_security_group" "web_sg"' in hcl


def test_render_hcl_ends_with_newline() -> None:
    doc = build_terraform_module([AWS_INSTANCE_RESOURCE], provider="aws")
    hcl = render_terraform_hcl(doc)
    assert hcl.endswith("\n")


# ── Integration test: full module generation ─────────────────────────


def test_full_aws_module_generation() -> None:
    """End-to-end test: build + render a complete AWS module."""
    doc = build_terraform_module(
        resources=[AWS_INSTANCE_RESOURCE],
        provider="aws",
        variables=SAMPLE_VARIABLES,
        outputs=SAMPLE_OUTPUTS,
        module_dependencies=SAMPLE_MODULE_DEPS,
        provider_config={"region": "us-west-2"},
    )
    hcl = render_terraform_hcl(doc)

    # Verify all sections present
    assert "terraform {" in hcl
    assert 'provider "aws"' in hcl
    assert "us-west-2" in hcl
    assert 'variable "instance_type"' in hcl
    assert 'resource "aws_instance" "web_server"' in hcl
    assert 'module "vpc"' in hcl
    assert 'output "instance_id"' in hcl
