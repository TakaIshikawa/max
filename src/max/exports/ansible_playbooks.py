"""Ansible playbook export for configuration management automation."""

from __future__ import annotations

from typing import Any

import yaml

SCHEMA_VERSION = "max.ansible_playbooks.v1"
KIND = "max.ansible_playbooks"


def build_ansible_playbook(
    plays: list[dict[str, Any]],
    *,
    inventory: dict[str, Any] | None = None,
    roles: list[dict[str, Any]] | None = None,
    handlers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a structured Ansible playbook document."""
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "inventory": inventory or default_inventory(),
        "roles": [_normalize_role(role) for role in (roles or [])],
        "handlers": [_normalize_task(handler) for handler in (handlers or [])],
        "plays": [_normalize_play(play, handlers or []) for play in plays],
    }


def default_inventory() -> dict[str, Any]:
    return {
        "all": {
            "children": {
                "app_servers": {"hosts": {"app1": {"ansible_host": "10.0.1.10"}}},
                "databases": {"hosts": {"db1": {"ansible_host": "10.0.2.10"}}},
                "load_balancers": {"hosts": {"lb1": {"ansible_host": "10.0.0.10"}}},
            }
        }
    }


def app_server_play(hosts: str = "app_servers") -> dict[str, Any]:
    return {
        "name": "Configure application servers",
        "hosts": hosts,
        "become": True,
        "roles": ["app_server"],
        "tasks": [
            {
                "name": "Install application packages",
                "ansible.builtin.package": {"name": ["git", "python3"], "state": "present"},
            },
            {
                "name": "Deploy application config",
                "ansible.builtin.template": {
                    "src": "app.conf.j2",
                    "dest": "/etc/max/app.conf",
                    "mode": "0644",
                },
                "notify": ["Restart application"],
            },
        ],
    }


def database_play(hosts: str = "databases") -> dict[str, Any]:
    return {
        "name": "Configure database servers",
        "hosts": hosts,
        "become": True,
        "roles": ["database"],
        "tasks": [
            {
                "name": "Install PostgreSQL",
                "ansible.builtin.package": {"name": "postgresql", "state": "present"},
            },
            {
                "name": "Ensure database service is running",
                "ansible.builtin.service": {"name": "postgresql", "state": "started", "enabled": True},
            },
        ],
    }


def load_balancer_play(hosts: str = "load_balancers") -> dict[str, Any]:
    return {
        "name": "Configure load balancers",
        "hosts": hosts,
        "become": True,
        "roles": ["load_balancer"],
        "tasks": [
            {
                "name": "Install nginx",
                "ansible.builtin.package": {"name": "nginx", "state": "present"},
            },
            {
                "name": "Render upstream configuration",
                "ansible.builtin.template": {
                    "src": "upstream.conf.j2",
                    "dest": "/etc/nginx/conf.d/upstream.conf",
                    "mode": "0644",
                },
                "notify": ["Reload nginx"],
            },
        ],
    }


def render_playbook_yaml(document: dict[str, Any]) -> str:
    """Render the play list as Ansible-compatible YAML."""
    return yaml.safe_dump(document["plays"], sort_keys=False)


def render_inventory_yaml(document: dict[str, Any]) -> str:
    """Render inventory as YAML."""
    return yaml.safe_dump(document["inventory"], sort_keys=False)


def render_roles_yaml(document: dict[str, Any]) -> str:
    """Render role definitions as YAML."""
    return yaml.safe_dump(document["roles"], sort_keys=False)


def _normalize_play(play: dict[str, Any], inherited_handlers: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = {
        "name": play.get("name", "Configure hosts"),
        "hosts": play.get("hosts", "all"),
        "become": bool(play.get("become", True)),
        "roles": play.get("roles", []),
        "tasks": [_normalize_task(task) for task in play.get("tasks", [])],
    }
    handlers = play.get("handlers", inherited_handlers)
    if handlers:
        normalized["handlers"] = [_normalize_task(handler) for handler in handlers]
    return normalized


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task)
    normalized.setdefault("name", "Unnamed task")
    normalized.setdefault("retries", 3)
    normalized.setdefault("delay", 5)
    normalized.setdefault("failed_when", False)
    return normalized


def _normalize_role(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": role.get("name", "unnamed"),
        "description": role.get("description", ""),
        "defaults": role.get("defaults", {}),
        "vars": role.get("vars", {}),
        "tasks": [_normalize_task(task) for task in role.get("tasks", [])],
        "handlers": [_normalize_task(handler) for handler in role.get("handlers", [])],
    }
