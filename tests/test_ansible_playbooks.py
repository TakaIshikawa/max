"""Tests for Ansible playbook export."""

from __future__ import annotations

import yaml

from max.exports.ansible_playbooks import (
    KIND,
    SCHEMA_VERSION,
    app_server_play,
    build_ansible_playbook,
    database_play,
    default_inventory,
    load_balancer_play,
    render_inventory_yaml,
    render_playbook_yaml,
    render_roles_yaml,
)


def test_build_ansible_playbook_structure() -> None:
    doc = build_ansible_playbook(
        [app_server_play()],
        roles=[{"name": "app_server", "tasks": [{"name": "Create app user", "ansible.builtin.user": {"name": "max"}}]}],
        handlers=[{"name": "Restart application", "ansible.builtin.service": {"name": "max", "state": "restarted"}}],
    )

    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["kind"] == KIND
    assert "app_servers" in doc["inventory"]["all"]["children"]
    assert doc["roles"][0]["name"] == "app_server"
    assert doc["plays"][0]["handlers"][0]["name"] == "Restart application"
    assert doc["plays"][0]["tasks"][0]["retries"] == 3
    assert doc["plays"][0]["tasks"][0]["failed_when"] is False


def test_common_deployment_patterns() -> None:
    doc = build_ansible_playbook([app_server_play(), database_play(), load_balancer_play()])
    assert [play["hosts"] for play in doc["plays"]] == [
        "app_servers",
        "databases",
        "load_balancers",
    ]
    assert doc["plays"][1]["tasks"][1]["ansible.builtin.service"]["enabled"] is True
    assert doc["plays"][2]["tasks"][1]["notify"] == ["Reload nginx"]


def test_render_playbook_yaml_is_valid() -> None:
    doc = build_ansible_playbook([app_server_play()])
    rendered = render_playbook_yaml(doc)
    parsed = yaml.safe_load(rendered)

    assert parsed[0]["name"] == "Configure application servers"
    assert parsed[0]["tasks"][1]["ansible.builtin.template"]["dest"] == "/etc/max/app.conf"


def test_render_inventory_and_roles_yaml() -> None:
    doc = build_ansible_playbook(
        [database_play()],
        inventory=default_inventory(),
        roles=[{"name": "database", "defaults": {"postgres_version": 16}}],
    )

    inventory = yaml.safe_load(render_inventory_yaml(doc))
    roles = yaml.safe_load(render_roles_yaml(doc))

    assert inventory["all"]["children"]["databases"]["hosts"]["db1"]["ansible_host"] == "10.0.2.10"
    assert roles[0]["defaults"]["postgres_version"] == 16
