"""The initial migration must produce the full schema."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.base import Base

pytestmark = pytest.mark.db


async def test_migration_creates_every_expected_table(
    db_connection: AsyncConnection, expected_tables: set[str]
) -> None:
    tables = await db_connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

    missing = expected_tables - tables
    assert not missing, f"migration did not create: {sorted(missing)}"
    assert "alembic_version" in tables


async def test_schema_matches_the_orm_metadata(db_connection: AsyncConnection) -> None:
    """Every table declared on the models exists in the migrated database."""
    tables = await db_connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))

    assert set(Base.metadata.tables) <= tables


async def test_every_table_has_a_uuid_primary_key(
    db_connection: AsyncConnection, expected_tables: set[str]
) -> None:
    def _pk_types(sync_conn) -> dict[str, list[tuple[str, str]]]:  # type: ignore[no-untyped-def]
        inspector = inspect(sync_conn)
        result: dict[str, list[tuple[str, str]]] = {}
        for table in sorted(expected_tables):
            pk_columns = inspector.get_pk_constraint(table)["constrained_columns"]
            columns = {c["name"]: str(c["type"]) for c in inspector.get_columns(table)}
            result[table] = [(name, columns[name]) for name in pk_columns]
        return result

    primary_keys = await db_connection.run_sync(_pk_types)

    for table, columns in primary_keys.items():
        assert columns == [("id", "UUID")], f"{table} has an unexpected primary key: {columns}"


async def test_timestamp_columns_exist(db_connection: AsyncConnection) -> None:
    def _columns(sync_conn) -> dict[str, set[str]]:  # type: ignore[no-untyped-def]
        inspector = inspect(sync_conn)
        return {
            table: {c["name"] for c in inspector.get_columns(table)}
            for table in inspector.get_table_names()
        }

    columns = await _columns_via(db_connection, _columns)

    with_updated_at = {
        "assets",
        "incidents",
        "diagnoses",
        "maintenance_proposals",
        "part_checks",
        "approval_decisions",
        "work_orders",
        "technician_outcomes",
    }
    created_at_only = {"agent_runs", "evidence_items"}

    for table in with_updated_at:
        assert {"created_at", "updated_at"} <= columns[table], table
    for table in created_at_only:
        assert "created_at" in columns[table], table
        assert "updated_at" not in columns[table], table

    # audit_events is immutable: it records when the event happened, nothing else.
    assert "occurred_at" in columns["audit_events"]
    assert "updated_at" not in columns["audit_events"]


async def test_required_indexes_exist(db_connection: AsyncConnection) -> None:
    """Indexes the console's hot queries depend on."""
    required = {
        "incidents": {
            "ix_incidents_workflow_status",
            "ix_incidents_asset_id",
            "ix_incidents_trace_id",
            "ix_incidents_detected_at",
        },
        "audit_events": {
            "ix_audit_events_trace_id",
            "ix_audit_events_occurred_at",
            "ix_audit_events_incident_id",
        },
        "approval_decisions": {
            "ix_approval_decisions_decision",
            "ix_approval_decisions_incident_id",
        },
    }

    def _indexes(sync_conn) -> dict[str, set[str]]:  # type: ignore[no-untyped-def]
        inspector = inspect(sync_conn)
        return {
            table: {index["name"] for index in inspector.get_indexes(table)} for table in required
        }

    indexes = await _columns_via(db_connection, _indexes)

    for table, names in required.items():
        missing = names - indexes[table]
        assert not missing, f"{table} is missing indexes: {sorted(missing)}"


async def test_unique_constraints_exist(db_connection: AsyncConnection) -> None:
    """asset_code and trace_id must be unique."""
    result = await db_connection.execute(
        text(
            "SELECT conrelid::regclass::text AS table_name, conname "
            "FROM pg_constraint WHERE contype = 'u'"
        )
    )
    constraints = {(row.table_name, row.conname) for row in result}

    assert ("assets", "uq_assets_asset_code") in constraints
    assert ("incidents", "uq_incidents_trace_id") in constraints


async def _columns_via(connection: AsyncConnection, fn):  # type: ignore[no-untyped-def]
    return await connection.run_sync(fn)
