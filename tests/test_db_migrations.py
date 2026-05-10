"""Tests for database migration scripts export."""

from __future__ import annotations

import pytest

from max.exports.db_migrations import (
    SCHEMA_VERSION,
    SUPPORTED_DIALECTS,
    TYPE_MAP,
    build_migration_plan,
    render_migration_sql,
    _column_definition,
    _generate_migration_pair,
)


# ── Test Data ────────────────────────────────────────────────────────

CREATE_USERS_TABLE = {
    "action": "create_table",
    "table": "users",
    "columns": [
        {"name": "id", "type": "uuid", "constraints": ["primary_key", "not_null"]},
        {"name": "email", "type": "string", "constraints": ["not_null", "unique"]},
        {"name": "name", "type": "string", "constraints": ["not_null"]},
        {"name": "created_at", "type": "datetime", "constraints": ["not_null", "default:CURRENT_TIMESTAMP"]},
        {"name": "is_active", "type": "boolean", "constraints": ["default:true"]},
    ],
}

ADD_COLUMN_CHANGE = {
    "action": "add_column",
    "table": "users",
    "column": {"name": "avatar_url", "type": "text", "constraints": []},
}

DROP_COLUMN_CHANGE = {
    "action": "drop_column",
    "table": "users",
    "column_name": "avatar_url",
}

RENAME_COLUMN_CHANGE = {
    "action": "rename_column",
    "table": "users",
    "column_name": "name",
    "new_name": "display_name",
}

ADD_INDEX_CHANGE = {
    "action": "add_index",
    "table": "users",
    "index": {
        "name": "idx_users_email",
        "columns": ["email"],
        "unique": True,
    },
}

DROP_TABLE_CHANGE = {
    "action": "drop_table",
    "table": "legacy_sessions",
}


# ── Unit tests: _column_definition ───────────────────────────────────


def test_column_definition_postgresql() -> None:
    col = {"name": "email", "type": "string", "constraints": ["not_null", "unique"]}
    result = _column_definition(col, "postgresql")
    assert result == "email TEXT NOT NULL UNIQUE"


def test_column_definition_mysql() -> None:
    col = {"name": "email", "type": "string", "constraints": ["not_null"]}
    result = _column_definition(col, "mysql")
    assert result == "email VARCHAR(255) NOT NULL"


def test_column_definition_sqlite() -> None:
    col = {"name": "count", "type": "integer", "constraints": []}
    result = _column_definition(col, "sqlite")
    assert result == "count INTEGER"


def test_column_definition_with_default() -> None:
    col = {"name": "active", "type": "boolean", "constraints": ["default:true"]}
    result = _column_definition(col, "postgresql")
    assert "DEFAULT true" in result


def test_column_definition_primary_key() -> None:
    col = {"name": "id", "type": "uuid", "constraints": ["primary_key"]}
    result = _column_definition(col, "postgresql")
    assert "UUID PRIMARY KEY" in result


# ── Unit tests: _generate_migration_pair ─────────────────────────────


def test_gen_create_table() -> None:
    up, down = _generate_migration_pair(CREATE_USERS_TABLE, "postgresql")
    assert "CREATE TABLE users" in up
    assert "id UUID PRIMARY KEY NOT NULL" in up
    assert "email TEXT NOT NULL UNIQUE" in up
    assert "DROP TABLE IF EXISTS users" in down


def test_gen_add_column() -> None:
    up, down = _generate_migration_pair(ADD_COLUMN_CHANGE, "postgresql")
    assert "ALTER TABLE users ADD COLUMN avatar_url TEXT" in up
    assert "ALTER TABLE users DROP COLUMN avatar_url" in down


def test_gen_drop_column() -> None:
    up, down = _generate_migration_pair(DROP_COLUMN_CHANGE, "postgresql")
    assert "ALTER TABLE users DROP COLUMN avatar_url" in up
    assert "TODO" in down  # rollback not fully possible


def test_gen_rename_column() -> None:
    up, down = _generate_migration_pair(RENAME_COLUMN_CHANGE, "postgresql")
    assert "RENAME COLUMN name TO display_name" in up
    assert "RENAME COLUMN display_name TO name" in down


def test_gen_add_index() -> None:
    up, down = _generate_migration_pair(ADD_INDEX_CHANGE, "postgresql")
    assert "CREATE UNIQUE INDEX idx_users_email ON users (email)" in up
    assert "DROP INDEX IF EXISTS idx_users_email" in down


def test_gen_drop_table() -> None:
    up, down = _generate_migration_pair(DROP_TABLE_CHANGE, "postgresql")
    assert "DROP TABLE IF EXISTS legacy_sessions" in up
    assert "TODO" in down


def test_gen_unsupported_action() -> None:
    up, down = _generate_migration_pair({"action": "unknown", "table": "t"}, "postgresql")
    assert "TODO" in up
    assert "TODO" in down


# ── build_migration_plan tests ───────────────────────────────────────


def test_build_plan_postgresql() -> None:
    plan = build_migration_plan(
        [CREATE_USERS_TABLE, ADD_INDEX_CHANGE],
        dialect="postgresql",
        version="20240310120000",
        description="Create users table with email index",
    )
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["kind"] == "max.db_migrations"
    assert plan["dialect"] == "postgresql"
    assert plan["version"] == "20240310120000"
    assert len(plan["up_statements"]) == 2
    assert len(plan["down_statements"]) == 2


def test_build_plan_mysql() -> None:
    plan = build_migration_plan(
        [CREATE_USERS_TABLE],
        dialect="mysql",
        version="001",
    )
    assert plan["dialect"] == "mysql"
    assert "VARCHAR(255)" in plan["up_statements"][0]


def test_build_plan_sqlite() -> None:
    plan = build_migration_plan(
        [CREATE_USERS_TABLE],
        dialect="sqlite",
        version="001",
    )
    assert plan["dialect"] == "sqlite"
    # SQLite maps uuid to TEXT
    assert "TEXT PRIMARY KEY" in plan["up_statements"][0]


def test_build_plan_unsupported_dialect() -> None:
    with pytest.raises(ValueError, match="Unsupported dialect"):
        build_migration_plan([CREATE_USERS_TABLE], dialect="oracle")


def test_build_plan_auto_version() -> None:
    plan = build_migration_plan([CREATE_USERS_TABLE])
    assert len(plan["version"]) == 14  # YYYYMMDDHHMMSS format


def test_build_plan_down_reversed() -> None:
    """Down statements should be in reverse order of up statements."""
    plan = build_migration_plan(
        [CREATE_USERS_TABLE, ADD_INDEX_CHANGE],
        dialect="postgresql",
        version="001",
    )
    # Down[0] should be the rollback for ADD_INDEX (last up action)
    assert "DROP INDEX" in plan["down_statements"][0]
    # Down[1] should be the rollback for CREATE TABLE (first up action)
    assert "DROP TABLE" in plan["down_statements"][1]


# ── render_migration_sql tests ───────────────────────────────────────


def test_render_up_migration() -> None:
    plan = build_migration_plan(
        [CREATE_USERS_TABLE],
        dialect="postgresql",
        version="20240310120000",
        description="Create users table",
    )
    sql = render_migration_sql(plan, direction="up")
    assert "-- Migration: 20240310120000" in sql
    assert "-- Description: Create users table" in sql
    assert "-- Direction: UP" in sql
    assert "INSERT INTO schema_migrations" in sql
    assert "CREATE TABLE users" in sql


def test_render_down_migration() -> None:
    plan = build_migration_plan(
        [CREATE_USERS_TABLE],
        dialect="postgresql",
        version="20240310120000",
        description="Create users table",
    )
    sql = render_migration_sql(plan, direction="down")
    assert "-- Direction: DOWN" in sql
    assert "DELETE FROM schema_migrations" in sql
    assert "DROP TABLE IF EXISTS users" in sql


def test_render_invalid_direction() -> None:
    plan = build_migration_plan([CREATE_USERS_TABLE], version="001")
    with pytest.raises(ValueError, match="Invalid direction"):
        render_migration_sql(plan, direction="sideways")


def test_render_ends_with_newline() -> None:
    plan = build_migration_plan([CREATE_USERS_TABLE], version="001")
    sql = render_migration_sql(plan)
    assert sql.endswith("\n")


def test_render_no_description() -> None:
    plan = build_migration_plan([CREATE_USERS_TABLE], version="001")
    sql = render_migration_sql(plan)
    assert "-- (no description)" in sql


# ── Integration test: full migration flow ────────────────────────────


def test_full_migration_flow() -> None:
    """End-to-end: multiple changes, render both directions."""
    changes = [
        CREATE_USERS_TABLE,
        ADD_COLUMN_CHANGE,
        ADD_INDEX_CHANGE,
    ]
    plan = build_migration_plan(
        changes,
        dialect="postgresql",
        version="20240310120000",
        description="Initial user schema",
    )

    up_sql = render_migration_sql(plan, direction="up")
    down_sql = render_migration_sql(plan, direction="down")

    # Up should create table, add column, create index
    assert "CREATE TABLE users" in up_sql
    assert "ADD COLUMN avatar_url" in up_sql
    assert "CREATE UNIQUE INDEX" in up_sql

    # Down should reverse: drop index, drop column, drop table
    assert "DROP INDEX" in down_sql
    assert "DROP COLUMN avatar_url" in down_sql
    assert "DROP TABLE IF EXISTS users" in down_sql


def test_dialect_type_mapping_coverage() -> None:
    """Verify all dialects have mappings for common types."""
    common_types = ["string", "integer", "boolean", "datetime", "json"]
    for dialect in SUPPORTED_DIALECTS:
        for col_type in common_types:
            assert col_type in TYPE_MAP[dialect], (
                f"Missing type '{col_type}' in dialect '{dialect}'"
            )
