from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects import postgresql

from app.models import (
    AuditEvent,
    Call,
    Callback,
    CallbackAttemptStatus,
    CallbackStatus,
    CallDirection,
    EventType,
    Lead,
    Message,
    MessageKind,
    MessageStatus,
)
from app.repositories import (
    AuditEventRepository,
    CallbackAttemptRepository,
    CallbackRepository,
    CallRepository,
    LeadRepository,
    MessageRepository,
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
    """AsyncSession boundary that records real SQLAlchemy statements and ORM additions."""

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


async def test_call_upsert_accepts_a_direction_read_back_from_a_stored_row() -> None:
    """Catches a completed callback crashing because TEXT columns load as plain strings."""
    session = RecordingSession(Call(id=42, lead_id=7, sarvam_call_id="cb-19-abc"))

    await CallRepository(session).upsert_by_sarvam_call_id(
        "cb-19-abc",
        lead_id=7,
        direction="CALLBACK",
        status="completed",
    )

    parameters = session.statements[0].compile(dialect=postgresql.dialect()).params
    assert parameters["direction"] == CallDirection.CALLBACK.value


async def test_call_lookup_reads_the_existing_row_for_a_provider_call_id() -> None:
    """Catches losing the stored direction and callback link a completion must preserve."""
    existing = Call(
        id=11,
        lead_id=7,
        callback_id=19,
        sarvam_call_id="cb-19-abc",
        direction=CallDirection.CALLBACK,
    )
    session = RecordingSession(existing)

    actual = await CallRepository(session).get_by_sarvam_call_id("cb-19-abc")

    assert actual is existing
    sql = _postgresql_sql(session.statements[0])
    assert "FROM sales_agent.calls" in sql
    assert "sarvam_call_id" in sql


async def test_audit_append_adds_and_flushes_an_immutable_row() -> None:
    """Catches event creation being replaced by an update or deferred beyond the caller transaction."""
    session = RecordingSession()

    event = await AuditEventRepository(session).append(
        lead_id=7,
        call_id=11,
        event_type=EventType.CALL_COMPLETED,
        payload={"status": "completed"},
    )

    assert session.added == [event]
    assert session.flush_count == 1
    assert isinstance(event, AuditEvent)
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


async def test_claim_due_locks_one_eligible_callback_and_moves_it_to_in_progress() -> None:
    """Catches workers racing on the same callback or leaving a dialled row eligible again."""
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
    assert callback.status is CallbackStatus.IN_PROGRESS
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
        status=CallbackStatus.IN_PROGRESS,
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
    await repository.mark_dialled(callback)
    assert callback.status is CallbackStatus.IN_PROGRESS
    assert callback.last_error is None
    assert callback.next_attempt_at is None
    assert callback.claimed_at is None
    assert session.flush_count == 2


async def test_a_dialled_callback_completes_and_a_settled_one_cannot_be_reopened() -> None:
    """Catches a replayed completion payload resurrecting a cancelled or failed callback."""
    now = datetime(2026, 8, 22, 10, 5, tzinfo=UTC)
    completed = Callback(
        id=19,
        lead_id=7,
        source_call_id=11,
        requested_expression="now",
        scheduled_at=now,
        timezone="Asia/Kolkata",
        status=CallbackStatus.COMPLETED,
    )
    session = RecordingSession(completed, None)
    repository = CallbackRepository(session)

    assert await repository.mark_completed(19, now=now) is completed
    assert await repository.mark_completed(19, now=now) is None

    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "UPDATE sales_agent.callbacks" in sql
    assert "WHERE sales_agent.callbacks.id = " in sql
    assert "AND sales_agent.callbacks.status = " in sql
    assert "RETURNING" in sql
    # Only an IN_PROGRESS row is eligible, so a settled callback matches nothing.
    assert CallbackStatus.IN_PROGRESS.value in compiled.params.values()
    assert compiled.params["status"] == CallbackStatus.COMPLETED.value


async def test_callback_attempt_records_one_row_per_dial() -> None:
    """Catches per-attempt provider outcomes being collapsed into the callback row."""
    session = RecordingSession()

    attempt = await CallbackAttemptRepository(session).record(
        callback_id=19,
        attempt_number=2,
        status=CallbackAttemptStatus.FAILED,
        error="sarvam_outbound_unreachable",
        retryable=True,
    )

    assert session.added == [attempt]
    assert session.flush_count == 1
    assert attempt.callback_id == 19
    assert attempt.attempt_number == 2
    assert attempt.status is CallbackAttemptStatus.FAILED
    assert attempt.error == "sarvam_outbound_unreachable"
    assert attempt.retryable is True


class SharedMessageBoundary:
    def __init__(self) -> None:
        self.rows: dict[tuple[int, str], str] = {}
        self.lock = asyncio.Lock()
        self.next_id = 1


class MessageSession:
    """Models PostgreSQL settling the (call_id, kind) unique key at the session boundary."""

    def __init__(self, shared: SharedMessageBoundary) -> None:
        self.shared = shared
        self.statements: list[object] = []

    async def execute(self, statement: object) -> ScalarResult:
        self.statements.append(statement)
        assert getattr(statement, "table").name == "messages"
        parameters = statement.compile(dialect=postgresql.dialect()).params  # type: ignore[attr-defined]
        key = (parameters["call_id"], parameters["kind"])
        async with self.shared.lock:
            existing = self.shared.rows.get(key)
            # DO UPDATE ... WHERE status = 'FAILED': anything else returns no row.
            if existing is not None and existing != MessageStatus.FAILED.value:
                return ScalarResult(None)
            self.shared.rows[key] = MessageStatus.RESERVED.value
            message = Message(
                id=self.shared.next_id,
                lead_id=parameters["lead_id"],
                call_id=key[0],
                kind=key[1],
                status=MessageStatus.RESERVED,
            )
            self.shared.next_id += 1
            return ScalarResult(message)

    async def flush(self) -> None:
        return None


async def test_concurrent_reservations_for_one_call_and_kind_have_a_single_owner() -> None:
    """Catches two concurrent high-intent tool calls both sending the lead a WhatsApp."""
    shared = SharedMessageBoundary()
    sessions = [MessageSession(shared), MessageSession(shared)]

    results = await asyncio.gather(
        *(
            MessageRepository(session).reserve(
                lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT
            )
            for session in sessions
        )
    )

    assert sorted(result is None for result in results) == [False, True]
    sql = _postgresql_sql(sessions[0].statements[0])
    assert "INSERT INTO sales_agent.messages" in sql
    assert "ON CONFLICT (call_id, kind) DO UPDATE" in sql
    assert "WHERE sales_agent.messages.status = " in sql
    assert "RETURNING" in sql


async def test_a_sent_message_is_never_resent_and_a_failed_one_can_be_retried() -> None:
    """Catches a provider failure permanently blocking a retry, or a success being resent."""
    shared = SharedMessageBoundary()
    session = MessageSession(shared)
    repository = MessageRepository(session)

    first = await repository.reserve(lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT)
    assert first is not None

    assert await repository.reserve(lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT) is None

    shared.rows[(11, MessageKind.HIGH_INTENT.value)] = MessageStatus.FAILED.value
    retry = await repository.reserve(lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT)
    assert retry is not None

    shared.rows[(11, MessageKind.HIGH_INTENT.value)] = MessageStatus.SENT.value
    assert await repository.reserve(lead_id=7, call_id=11, kind=MessageKind.HIGH_INTENT) is None


async def test_message_outcomes_record_the_provider_result_on_the_reserved_row() -> None:
    """Catches a delivery result that never reaches the row the next request reads."""
    now = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    session = RecordingSession()
    repository = MessageRepository(session)
    message = Message(id=1, lead_id=7, call_id=11, kind=MessageKind.FOLLOWUP_TEXT)

    await repository.mark_sent(message, provider_message_id="wamid-1", now=now)
    assert message.status is MessageStatus.SENT
    assert message.provider_message_id == "wamid-1"
    assert message.sent_at == now
    assert message.last_error is None

    await repository.mark_failed(message, error="whapi_send_failed")
    assert message.status is MessageStatus.FAILED
    assert message.last_error == "whapi_send_failed"
    assert session.flush_count == 2
