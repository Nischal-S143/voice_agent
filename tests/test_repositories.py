from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.repositories import CallbackRepository, CallRepository, EventRepository, LeadRepository
from app.models import (
    Callback,
    CallbackStatus,
    Call,
    CallDirection,
    DeliveryReservation,
    Event,
    EventType,
    Lead,
)


class ScalarResult:
    def __init__(self, value: object | None) -> None:
        self.value = value

    def scalar_one(self) -> object:
        assert self.value is not None
        return self.value

    def scalar_one_or_none(self) -> object | None:
        return self.value


class RecordingSession:
    """AsyncSession boundary that records real SQLAlchemy statements and ORM event additions."""

    def __init__(self, *results: object | None) -> None:
        self.results = list(results)
        self.statements: list[object] = []
        self.added: list[object] = []
        self.flush_count = 0

    async def execute(self, statement: object) -> ScalarResult:
        self.statements.append(statement)
        assert self.results, "test did not provide a result for an executed statement"
        return ScalarResult(self.results.pop(0))

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


def _postgresql_sql(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


async def test_lead_upsert_uses_postgresql_conflict_update_and_refreshes_updated_at() -> None:
    """Catches duplicate lead inserts, stale qualification data, or update paths with stale timestamps."""
    expected = Lead(id=7, normalized_phone="+919999999999", business_type="Jewellery")
    session = RecordingSession(expected)

    actual = await LeadRepository(session).upsert_by_phone(
        "+919999999999",
        business_type="Jewellery",
        product_count=120,
    )

    assert actual is expected
    sql = _postgresql_sql(session.statements[0])
    assert "INSERT INTO sales_agent.leads" in sql
    assert "ON CONFLICT (normalized_phone) DO UPDATE" in sql
    assert "business_type = excluded.business_type" in sql
    assert "product_count = excluded.product_count" in sql
    assert "updated_at = now()" in sql
    assert "RETURNING" in sql


async def test_call_upsert_uses_sarvam_id_conflict_boundary_and_returns_orm_row() -> None:
    """Catches repeated completion payloads creating a second provider call record."""
    expected = Call(
        id=11,
        lead_id=7,
        sarvam_call_id="sarvam-123",
        direction=CallDirection.INITIAL,
        status="completed",
    )
    session = RecordingSession(expected)

    actual = await CallRepository(session).upsert_by_sarvam_call_id(
        "sarvam-123",
        lead_id=7,
        direction=CallDirection.INITIAL,
        status="completed",
    )

    assert actual is expected
    sql = _postgresql_sql(session.statements[0])
    assert "INSERT INTO sales_agent.calls" in sql
    assert "ON CONFLICT (sarvam_call_id) DO UPDATE" in sql
    assert "status = excluded.status" in sql
    assert "RETURNING" in sql


async def test_event_append_adds_and_flushes_an_immutable_audit_row() -> None:
    """Catches event creation being replaced by an update or deferred beyond the caller transaction."""
    session = RecordingSession()

    event = await EventRepository(session).append(
        lead_id=7,
        call_id=11,
        event_type=EventType.CALL_COMPLETED,
        payload={"status": "completed"},
    )

    assert session.added == [event]
    assert session.flush_count == 1
    assert event.lead_id == 7
    assert event.call_id == 11
    assert event.event_type is EventType.CALL_COMPLETED
    assert event.payload == {"status": "completed"}


async def test_callback_schedule_uses_unique_conflict_boundary_and_returns_existing_duplicate() -> None:
    """Catches repeated scheduling calls creating two callbacks for one source call and instant."""
    scheduled_at = datetime(2026, 8, 23, 5, 30, tzinfo=UTC)
    existing = Callback(
        id=19,
        lead_id=7,
        source_call_id=11,
        requested_expression="tomorrow at 11",
        scheduled_at=scheduled_at,
        timezone="Asia/Kolkata",
    )
    session = RecordingSession(None, existing)

    actual = await CallbackRepository(session).schedule(
        lead_id=7,
        source_call_id=11,
        requested_expression="tomorrow at 11",
        scheduled_at=scheduled_at,
        timezone="Asia/Kolkata",
    )

    assert actual is existing
    insert_sql, select_sql = map(_postgresql_sql, session.statements)
    assert "INSERT INTO sales_agent.callbacks" in insert_sql
    assert "ON CONFLICT (source_call_id, scheduled_at) DO NOTHING" in insert_sql
    assert "FROM sales_agent.callbacks" in select_sql
    assert "source_call_id" in select_sql and "scheduled_at" in select_sql


async def test_claim_due_locks_one_eligible_callback_and_updates_claim_metadata() -> None:
    """Catches workers racing on the same callback or returning it before claim metadata is flushed."""
    now = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    callback = Callback(
        id=19,
        lead_id=7,
        source_call_id=11,
        requested_expression="now",
        scheduled_at=now - timedelta(minutes=1),
        timezone="Asia/Kolkata",
        status=CallbackStatus.PENDING,
        attempt_count=2,
    )
    session = RecordingSession(callback)

    claimed = await CallbackRepository(session).claim_due(now=now)

    assert claimed is callback
    assert callback.claimed_at == now
    assert callback.attempt_count == 3
    assert session.flush_count == 1
    sql = _postgresql_sql(session.statements[0])
    assert "coalesce(sales_agent.callbacks.next_attempt_at, sales_agent.callbacks.scheduled_at)" in sql
    assert "ORDER BY coalesce" in sql
    assert "LIMIT" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "claimed_at IS NULL" in sql


async def test_callback_outcomes_clear_claim_and_preserve_retry_metadata() -> None:
    """Catches a worker leaving callbacks claimed forever or losing the bounded retry time."""
    now = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    retry_at = now + timedelta(minutes=5)
    callback = Callback(
        id=19,
        lead_id=7,
        source_call_id=11,
        requested_expression="now",
        scheduled_at=now,
        timezone="Asia/Kolkata",
        status=CallbackStatus.PENDING,
        attempt_count=1,
        claimed_at=now,
    )
    session = RecordingSession()
    repository = CallbackRepository(session)

    await repository.mark_failed(callback, error="temporary", next_attempt_at=retry_at)
    assert callback.status is CallbackStatus.PENDING
    assert callback.last_error == "temporary"
    assert callback.next_attempt_at == retry_at
    assert callback.claimed_at is None

    callback.claimed_at = now
    await repository.mark_triggered(callback, now=now)
    assert callback.status is CallbackStatus.TRIGGERED
    assert callback.completed_at == now
    assert callback.last_error is None
    assert callback.next_attempt_at is None
    assert callback.claimed_at is None
    assert session.flush_count == 2


class SharedReservationBoundary:
    def __init__(self) -> None:
        self.keys: set[tuple[int, str]] = set()
        self.lock = asyncio.Lock()


class ReservationSession:
    """Models PostgreSQL's atomic unique-key winner at the AsyncSession boundary."""

    def __init__(self, shared: SharedReservationBoundary) -> None:
        self.shared = shared
        self.added: list[object] = []
        self.statements: list[object] = []

    async def execute(self, statement: object) -> ScalarResult:
        self.statements.append(statement)
        assert getattr(statement, "table").name == "delivery_reservations"
        parameters = statement.compile(dialect=postgresql.dialect()).params  # type: ignore[attr-defined]
        key = (parameters["call_id"], parameters["target_event_type"])
        async with self.shared.lock:
            if key in self.shared.keys:
                return ScalarResult(None)
            self.shared.keys.add(key)
            return ScalarResult(key[0])

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


async def test_concurrent_delivery_reservations_have_one_owner_and_one_duplicate() -> None:
    """Catches two concurrent high-intent requests both becoming WhatsApp delivery owners."""
    shared = SharedReservationBoundary()
    sessions = [ReservationSession(shared), ReservationSession(shared)]

    results = await asyncio.gather(
        *(
            EventRepository(session).reserve_delivery(
                lead_id=7,
                call_id=11,
                target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
            )
            for session in sessions
        )
    )

    assert sorted(results) == [False, True]
    requested_events = [
        event
        for session in sessions
        for event in session.added
        if isinstance(event, Event)
    ]
    assert [event.event_type for event in requested_events] == [
        EventType.HIGH_INTENT_WHATSAPP_REQUESTED
    ]
    sql = _postgresql_sql(sessions[0].statements[0])
    assert "ON CONFLICT (call_id, target_event_type) DO NOTHING" in sql
    assert "RETURNING sales_agent.delivery_reservations.call_id" in sql


async def test_completed_delivery_is_permanently_reserved_and_audited_as_sent() -> None:
    """Catches successful delivery being released or resent after the provider result is recorded."""
    session = RecordingSession(11, 11, None)
    repository = EventRepository(session)

    assert await repository.reserve_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
    )
    assert await repository.complete_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
        payload={"provider_message_id": "wamid-1"},
    )
    assert not await repository.reserve_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
    )

    events = [value for value in session.added if isinstance(value, Event)]
    assert [event.event_type for event in events] == [
        EventType.HIGH_INTENT_WHATSAPP_REQUESTED,
        EventType.HIGH_INTENT_WHATSAPP_SENT,
    ]
    assert events[-1].payload == {"provider_message_id": "wamid-1"}
    complete_sql = _postgresql_sql(session.statements[1])
    assert "UPDATE sales_agent.delivery_reservations" in complete_sql
    assert "completed_at IS NULL" in complete_sql


async def test_released_delivery_appends_failure_audit_and_permits_retry() -> None:
    """Catches a provider failure either deleting audit history or permanently blocking a retry."""
    session = RecordingSession(11, 11, 11)
    repository = EventRepository(session)

    assert await repository.reserve_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
    )
    assert await repository.release_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
        payload={"error": "provider_failed"},
    )
    assert await repository.reserve_delivery(
        lead_id=7,
        call_id=11,
        target_event_type=EventType.HIGH_INTENT_WHATSAPP_SENT,
    )

    events = [value for value in session.added if isinstance(value, Event)]
    assert [event.event_type for event in events] == [
        EventType.HIGH_INTENT_WHATSAPP_REQUESTED,
        EventType.HIGH_INTENT_WHATSAPP_FAILED,
        EventType.HIGH_INTENT_WHATSAPP_REQUESTED,
    ]
    release_sql = _postgresql_sql(session.statements[1])
    assert "DELETE FROM sales_agent.delivery_reservations" in release_sql
    assert "completed_at IS NULL" in release_sql


def test_delivery_reservation_schema_has_postgresql_concurrency_constraint() -> None:
    """Catches the atomic reservation key being weakened to application-only duplicate checking."""
    table = DeliveryReservation.__table__
    assert [column.name for column in table.primary_key.columns] == ["call_id", "target_event_type"]
    assert table.c.call_id.references(Call.__table__.c.id)
    assert EventType.HIGH_INTENT_WHATSAPP_REQUESTED.value in {
        member.value for member in EventType
    }


class MigrationRecorder:
    def __init__(self) -> None:
        self.metadata = sa.MetaData()
        sa.Table(
            "calls",
            self.metadata,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            schema="sales_agent",
        )
        self.sql: list[str] = []

    def execute(self, statement: object) -> None:
        self.sql.append(str(statement))

    def create_table(self, name: str, *columns: object, **kwargs: object) -> sa.Table:
        table = sa.Table(name, self.metadata, *columns, **kwargs)
        self.sql.append(str(CreateTable(table).compile(dialect=postgresql.dialect())))
        return table


def test_delivery_reservation_migration_preserves_requested_audit_events() -> None:
    """Catches model-only idempotency state that cannot exist in the deployed PostgreSQL schema."""
    path = Path("alembic/versions/20260822_0002_delivery_reservations.py")
    spec = importlib.util.spec_from_file_location("delivery_reservation_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorder = MigrationRecorder()
    module.op = recorder

    module.upgrade()
    sql = "\n".join(recorder.sql).upper()

    assert "CREATE TABLE SALES_AGENT.DELIVERY_RESERVATIONS" in sql
    assert "CONSTRAINT PK_DELIVERY_RESERVATIONS PRIMARY KEY (CALL_ID, TARGET_EVENT_TYPE)" in sql
    assert "HIGH_INTENT_WHATSAPP_REQUESTED" in sql
    assert "FK_DELIVERY_RESERVATIONS_CALL_ID_CALLS" in sql
