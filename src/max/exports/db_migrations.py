"""Database migration scripts export for schema management.

Generates SQL migration scripts from data model specifications with up/down
migrations supporting PostgreSQL, MySQL, and SQLite dialects. Includes schema
versioning and rollback procedures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "max.db_migrations.v1"
KIND = "max.db_migrations"

SUPPORTED_DIALECTS = {"postgresql", "mysql", "sqlite"}

# Dialect-specific type mappings
TYPE_MAP: dict[str, dict[str, str]] = {
    "postgresql": {
        "string": "TEXT",
        "text": "TEXT",
        "integer": "INTEGER",
        "bigint": "BIGINT",
        "float": "DOUBLE PRECISION",
        "boolean": "BOOLEAN",
        "datetime": "TIMESTAMP WITH TIME ZONE",
        "date": "DATE",
        "json": "JSONB",
        "uuid": "UUID",
        "binary": "BYTEA",
    },
    "mysql": {
        "string": "VARCHAR(255)",
        "text": "TEXT",
        "integer": "INT",
        "bigint": "BIGINT",
        "float": "DOUBLE",
        "boolean": "TINYINT(1)",
        "datetime": "DATETIME",
        "date": "DATE",
        "json": "JSON",
        "uuid": "CHAR(36)",
        "binary": "BLOB",
    },
    "sqlite": {
        "string": "TEXT",
        "text": "TEXT",
        "integer": "INTEGER",
        "bigint": "INTEGER",
        "float": "REAL",
        "boolean": "INTEGER",
        "datetime": "TEXT",
        "date": "TEXT",
        "json": "TEXT",
        "uuid": "TEXT",
        "binary": "BLOB",
    },
}


def build_migration_plan(
    changes: list[dict[str, Any]],
    *,
    dialect: str = "postgresql",
    version: str | None = None,
    description: str = "",
) -> dict[str, Any]:
    """Build a migration plan from schema changes.

    Args:
        changes: List of schema change dicts. Each has:
            - action: str ("create_table", "drop_table", "add_column",
                          "drop_column", "rename_column", "add_index")
            - table: str (table name)
            - columns: list[dict] (for create_table, each with name/type/constraints)
            - column: dict (for add_column: name/type/constraints)
            - column_name: str (for drop_column, rename_column)
            - new_name: str (for rename_column)
            - index: dict (for add_index: name/columns/unique)
        dialect: SQL dialect ("postgresql", "mysql", "sqlite")
        version: Migration version string (auto-generated if None)
        description: Human-readable description of the migration

    Returns:
        Migration plan document dict with up/down SQL scripts.
    """
    if dialect not in SUPPORTED_DIALECTS:
        raise ValueError(
            f"Unsupported dialect: {dialect}. "
            f"Supported: {sorted(SUPPORTED_DIALECTS)}"
        )

    if version is None:
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

    up_statements = []
    down_statements = []

    for change in changes:
        up, down = _generate_migration_pair(change, dialect)
        up_statements.append(up)
        down_statements.append(down)

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "dialect": dialect,
        "version": version,
        "description": description,
        "up_statements": up_statements,
        "down_statements": list(reversed(down_statements)),
    }


def render_migration_sql(plan: dict[str, Any], *, direction: str = "up") -> str:
    """Render migration plan as SQL script.

    Args:
        plan: Migration plan from build_migration_plan
        direction: "up" for forward migration, "down" for rollback

    Returns:
        SQL script string.
    """
    if direction not in ("up", "down"):
        raise ValueError(f"Invalid direction: {direction}. Use 'up' or 'down'.")

    statements = plan[f"{direction}_statements"]
    version = plan["version"]
    description = plan["description"]
    dialect = plan["dialect"]

    lines = [
        f"-- Migration: {version}",
        f"-- Description: {description}" if description else "-- (no description)",
        f"-- Dialect: {dialect}",
        f"-- Direction: {direction.upper()}",
        "",
    ]

    # Version tracking (up inserts, down deletes)
    if direction == "up":
        lines.append(_version_tracking_up(version, dialect))
    else:
        lines.append(_version_tracking_down(version, dialect))
    lines.append("")

    for stmt in statements:
        lines.append(stmt + ";")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _generate_migration_pair(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate up/down SQL pair for a single schema change."""
    action = change.get("action", "")
    table = change.get("table", "unnamed")

    if action == "create_table":
        return _gen_create_table(change, dialect)
    elif action == "drop_table":
        return _gen_drop_table(change, dialect)
    elif action == "add_column":
        return _gen_add_column(change, dialect)
    elif action == "drop_column":
        return _gen_drop_column(change, dialect)
    elif action == "rename_column":
        return _gen_rename_column(change, dialect)
    elif action == "add_index":
        return _gen_add_index(change, dialect)
    else:
        return (
            f"-- TODO: unsupported action '{action}' on table '{table}'",
            f"-- TODO: rollback unsupported action '{action}' on table '{table}'",
        )


def _gen_create_table(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate CREATE TABLE / DROP TABLE pair."""
    table = change["table"]
    columns = change.get("columns", [])

    col_defs = []
    for col in columns:
        col_def = _column_definition(col, dialect)
        col_defs.append(col_def)

    cols_sql = ",\n  ".join(col_defs)
    up = f"CREATE TABLE {table} (\n  {cols_sql}\n)"
    down = f"DROP TABLE IF EXISTS {table}"
    return up, down


def _gen_drop_table(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate DROP TABLE / recreate stub pair."""
    table = change["table"]
    up = f"DROP TABLE IF EXISTS {table}"
    # Down cannot fully recreate without original schema
    down = f"-- TODO: recreate table '{table}' (original schema not available)"
    return up, down


def _gen_add_column(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate ADD COLUMN / DROP COLUMN pair."""
    table = change["table"]
    column = change.get("column", {})
    col_name = column.get("name", "unnamed")
    col_def = _column_definition(column, dialect)

    up = f"ALTER TABLE {table} ADD COLUMN {col_def}"
    down = f"ALTER TABLE {table} DROP COLUMN {col_name}"
    return up, down


def _gen_drop_column(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate DROP COLUMN / stub pair."""
    table = change["table"]
    col_name = change.get("column_name", "unnamed")

    up = f"ALTER TABLE {table} DROP COLUMN {col_name}"
    down = f"-- TODO: re-add column '{col_name}' to '{table}' (type not available)"
    return up, down


def _gen_rename_column(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate RENAME COLUMN pair."""
    table = change["table"]
    old_name = change.get("column_name", "unnamed")
    new_name = change.get("new_name", "unnamed")

    if dialect == "mysql":
        # MySQL requires CHANGE with type, use RENAME COLUMN (MySQL 8+)
        up = f"ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}"
        down = f"ALTER TABLE {table} RENAME COLUMN {new_name} TO {old_name}"
    else:
        up = f"ALTER TABLE {table} RENAME COLUMN {old_name} TO {new_name}"
        down = f"ALTER TABLE {table} RENAME COLUMN {new_name} TO {old_name}"
    return up, down


def _gen_add_index(
    change: dict[str, Any], dialect: str
) -> tuple[str, str]:
    """Generate CREATE INDEX / DROP INDEX pair."""
    table = change["table"]
    index = change.get("index", {})
    index_name = index.get("name", f"idx_{table}")
    columns = index.get("columns", [])
    unique = index.get("unique", False)

    unique_kw = "UNIQUE " if unique else ""
    cols_sql = ", ".join(columns)

    up = f"CREATE {unique_kw}INDEX {index_name} ON {table} ({cols_sql})"
    down = f"DROP INDEX IF EXISTS {index_name}"
    return up, down


def _column_definition(column: dict[str, Any], dialect: str) -> str:
    """Build a SQL column definition string."""
    name = column.get("name", "unnamed")
    col_type = column.get("type", "string")
    constraints = column.get("constraints", [])

    sql_type = TYPE_MAP.get(dialect, TYPE_MAP["postgresql"]).get(col_type, col_type.upper())

    parts = [name, sql_type]

    for constraint in constraints:
        if constraint == "primary_key":
            parts.append("PRIMARY KEY")
        elif constraint == "not_null":
            parts.append("NOT NULL")
        elif constraint == "unique":
            parts.append("UNIQUE")
        elif constraint.startswith("default:"):
            default_val = constraint[len("default:"):]
            parts.append(f"DEFAULT {default_val}")

    return " ".join(parts)


def _version_tracking_up(version: str, dialect: str) -> str:
    """Generate version tracking INSERT for up migration."""
    return (
        f"INSERT INTO schema_migrations (version, applied_at) "
        f"VALUES ('{version}', CURRENT_TIMESTAMP)"
    )


def _version_tracking_down(version: str, dialect: str) -> str:
    """Generate version tracking DELETE for down migration."""
    return f"DELETE FROM schema_migrations WHERE version = '{version}'"
