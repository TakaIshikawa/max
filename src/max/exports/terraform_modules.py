"""Terraform module export for infrastructure-as-code generation.

Generates Terraform HCL configurations from infrastructure specs including
provider configurations, resource definitions, variable declarations, and
output definitions. Supports AWS, GCP, and Azure providers.
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "max.terraform_modules.v1"
KIND = "max.terraform_modules"

SUPPORTED_PROVIDERS = {"aws", "google", "azurerm"}

# Default provider source mappings
PROVIDER_SOURCES = {
    "aws": "hashicorp/aws",
    "google": "hashicorp/google",
    "azurerm": "hashicorp/azurerm",
}

PROVIDER_VERSIONS = {
    "aws": "~> 5.0",
    "google": "~> 5.0",
    "azurerm": "~> 3.0",
}


def build_terraform_module(
    resources: list[dict[str, Any]],
    *,
    provider: str = "aws",
    variables: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    module_dependencies: list[dict[str, Any]] | None = None,
    provider_config: dict[str, Any] | None = None,
    terraform_version: str = ">= 1.5.0",
) -> dict[str, Any]:
    """Build a Terraform module document from infrastructure specs.

    Args:
        resources: List of resource dicts with keys:
            - type: str (e.g. "aws_instance", "google_compute_instance")
            - name: str (logical name for the resource)
            - attributes: dict of resource attributes
        provider: Provider name ("aws", "google", "azurerm")
        variables: Optional list of variable dicts with keys:
            - name: str
            - type: str (e.g. "string", "number", "list(string)")
            - description: str
            - default: Any (optional)
        outputs: Optional list of output dicts with keys:
            - name: str
            - value: str (HCL expression)
            - description: str
        module_dependencies: Optional list of module dependency dicts with keys:
            - name: str
            - source: str (module source path/URL)
            - version: str (optional)
            - inputs: dict (optional, input variable mappings)
        provider_config: Optional provider-specific configuration overrides
        terraform_version: Required terraform version constraint

    Returns:
        Structured Terraform module document dict.
    """
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider: {provider}. "
            f"Supported: {sorted(SUPPORTED_PROVIDERS)}"
        )

    validated_resources = [_validate_resource(r) for r in resources]
    validated_variables = [_validate_variable(v) for v in (variables or [])]
    validated_outputs = [_validate_output(o) for o in (outputs or [])]
    validated_modules = [_validate_module_dep(m) for m in (module_dependencies or [])]

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "provider": provider,
        "terraform_version": terraform_version,
        "provider_config": provider_config or _default_provider_config(provider),
        "resources": validated_resources,
        "variables": validated_variables,
        "outputs": validated_outputs,
        "module_dependencies": validated_modules,
    }


def render_terraform_hcl(document: dict[str, Any]) -> str:
    """Render Terraform module as HCL configuration.

    Args:
        document: Terraform module document from build_terraform_module

    Returns:
        HCL formatted Terraform configuration string.
    """
    lines: list[str] = []

    # Terraform block
    provider = document["provider"]
    lines.extend([
        "terraform {",
        f'  required_version = "{document["terraform_version"]}"',
        "",
        "  required_providers {",
        f"    {provider} = {{",
        f'      source  = "{PROVIDER_SOURCES[provider]}"',
        f'      version = "{PROVIDER_VERSIONS[provider]}"',
        "    }",
        "  }",
        "}",
        "",
    ])

    # Provider block
    lines.append(f"provider \"{provider}\" {{")
    for key, value in document["provider_config"].items():
        lines.append(f"  {key} = {_hcl_value(value)}")
    lines.extend(["}", ""])

    # Variables
    for var in document["variables"]:
        lines.append(f"variable \"{var['name']}\" {{")
        lines.append(f"  type        = {var['type']}")
        lines.append(f"  description = {_hcl_value(var['description'])}")
        if "default" in var:
            lines.append(f"  default     = {_hcl_value(var['default'])}")
        lines.extend(["}", ""])

    # Resources
    for resource in document["resources"]:
        lines.append(f"resource \"{resource['type']}\" \"{resource['name']}\" {{")
        for attr_key, attr_value in resource["attributes"].items():
            lines.append(f"  {attr_key} = {_hcl_value(attr_value)}")
        lines.extend(["}", ""])

    # Module dependencies
    for mod in document["module_dependencies"]:
        lines.append(f"module \"{mod['name']}\" {{")
        lines.append(f"  source = {_hcl_value(mod['source'])}")
        if mod.get("version"):
            lines.append(f"  version = {_hcl_value(mod['version'])}")
        for input_key, input_value in mod.get("inputs", {}).items():
            lines.append(f"  {input_key} = {_hcl_value(input_value)}")
        lines.extend(["}", ""])

    # Outputs
    for output in document["outputs"]:
        lines.append(f"output \"{output['name']}\" {{")
        lines.append(f"  value       = {output['value']}")
        lines.append(f"  description = {_hcl_value(output['description'])}")
        lines.extend(["}", ""])

    return "\n".join(lines).rstrip() + "\n"


def _default_provider_config(provider: str) -> dict[str, Any]:
    """Return default provider configuration."""
    if provider == "aws":
        return {"region": "us-east-1"}
    elif provider == "google":
        return {"project": "my-project", "region": "us-central1"}
    elif provider == "azurerm":
        return {}
    return {}


def _hcl_value(value: Any) -> str:
    """Convert a Python value to HCL representation."""
    if isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, list):
        items = ", ".join(_hcl_value(v) for v in value)
        return f"[{items}]"
    elif isinstance(value, dict):
        if not value:
            return "{}"
        inner = ", ".join(f"{k} = {_hcl_value(v)}" for k, v in value.items())
        return f"{{ {inner} }}"
    return f'"{value}"'


def _validate_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a resource definition."""
    return {
        "type": resource.get("type", "null_resource"),
        "name": resource.get("name", "unnamed"),
        "attributes": resource.get("attributes", {}),
    }


def _validate_variable(variable: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a variable definition."""
    result: dict[str, Any] = {
        "name": variable.get("name", "unnamed"),
        "type": variable.get("type", "string"),
        "description": variable.get("description", ""),
    }
    if "default" in variable:
        result["default"] = variable["default"]
    return result


def _validate_output(output: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an output definition."""
    return {
        "name": output.get("name", "unnamed"),
        "value": output.get("value", '""'),
        "description": output.get("description", ""),
    }


def _validate_module_dep(module: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a module dependency."""
    return {
        "name": module.get("name", "unnamed"),
        "source": module.get("source", ""),
        "version": module.get("version"),
        "inputs": module.get("inputs", {}),
    }
