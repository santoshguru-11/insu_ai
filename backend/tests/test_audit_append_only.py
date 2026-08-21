"""`audit_events` is append-only — at the database level and in the repository API."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, async_sessionmaker

from app.models.audit import AuditEvent
from app.models.enums import ActorType
from app.repositories.audit_event import AuditEventRepository
from app.services.audit import AuditService

pytestmark = pytest.mark.db


async def _insert_event(connection: AsyncConnection, trace_id: str) -> uuid.UUID:
    result = await connection.execute(
        text(
            "INSERT INTO audit_events "
            "(trace_id, actor_type, actor_id, event_type, event_payload_json) "
            "VALUES (:trace_id, 'system', 'seed', 'incident.detected', '{}'::jsonb) "
            "RETURNING id"
        ),
        {"trace_id": trace_id},
    )
    return result.scalar_one()


async def test_update_is_rejected_by_the_database(db_connection: AsyncConnection) -> None:
    event_id = await _insert_event(db_connection, f"trace-update-{uuid.uuid4()}")

    with pytest.raises(DBAPIError) as excinfo:
        await db_connection.execute(
            text("UPDATE audit_events SET event_type = 'tampered' WHERE id = :id"),
            {"id": event_id},
        )

    assert "append-only" in str(excinfo.value)
    await db_connection.rollback()


async def test_delete_is_rejected_by_the_database(db_connection: AsyncConnection) -> None:
    event_id = await _insert_event(db_connection, f"trace-delete-{uuid.uuid4()}")

    with pytest.raises(DBAPIError) as excinfo:
        await db_connection.execute(
            text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id}
        )

    assert "append-only" in str(excinfo.value)
    await db_connection.rollback()


async def test_bulk_delete_is_rejected(db_connection: AsyncConnection) -> None:
    await _insert_event(db_connection, f"trace-bulk-{uuid.uuid4()}")

    with pytest.raises(DBAPIError):
        await db_connection.execute(text("DELETE FROM audit_events"))

    await db_connection.rollback()


async def test_rows_survive_a_rejected_mutation(db_connection: AsyncConnection) -> None:
    trace_id = f"trace-survive-{uuid.uuid4()}"
    event_id = await _insert_event(db_connection, trace_id)
    await db_connection.commit()

    with pytest.raises(DBAPIError):
        await db_connection.execute(
            text("DELETE FROM audit_events WHERE id = :id"), {"id": event_id}
        )
    await db_connection.rollback()

    result = await db_connection.execute(
        text("SELECT event_type FROM audit_events WHERE id = :id"), {"id": event_id}
    )
    assert result.scalar_one() == "incident.detected"


def test_repository_exposes_no_mutating_methods() -> None:
    """The API surface itself offers no way to update or delete an audit event."""
    for forbidden in ("update", "delete", "delete_by_id"):
        assert not hasattr(AuditEventRepository, forbidden), (
            f"AuditEventRepository must not expose {forbidden}()"
        )
    assert hasattr(AuditEventRepository, "append")


async def test_service_can_append_and_read_back(db_engine: AsyncEngine) -> None:
    session_factory = async_sessionmaker(bind=db_engine, expire_on_commit=False)
    trace_id = f"trace-service-{uuid.uuid4()}"

    async with session_factory() as session:
        service = AuditService(session)
        await service.record(
            trace_id=trace_id,
            event_type="diagnosis.completed",
            actor_type=ActorType.AGENT,
            actor_id="diagnostic-agent",
            payload={"confidence": 0.91},
        )
        await session.commit()

    async with session_factory() as session:
        events = await AuditService(session).timeline(trace_id)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, AuditEvent)
    assert event.event_type == "diagnosis.completed"
    assert event.actor_type is ActorType.AGENT
    assert event.event_payload_json == {"confidence": 0.91}
