from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models import (
    AuditEvent,
    Base,
    Call,
    Callback,
    CallbackAttempt,
    CallbackAttemptStatus,
    CallbackStatus,
    CallDirection,
    EventType,
    Lead,
    Message,
    MessageKind,
    MessageStatus,
)


def _constraint_names(table: object, constraint_type: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def test_schema_holds_exactly_the_tables_the_architecture_publishes() -> None:
    """Catches a table drifting away from the six the architecture diagram names."""
    assert set(Base.metadata.tables) == {
        "sales_agent.leads",
        "sales_agent.calls",
        "sales_agent.callbacks",
        "sales_agent.callback_attempts",
        "sales_agent.messages",
        "sales_agent.audit_events",
    }


def test_lead_phone_is_unique_and_qualification_lists_use_jsonb() -> None:
    """Catches duplicate leads or lossy storage of structured qualification data."""
    assert "uq_leads_normalized_phone" in _constraint_names(Lead.__table__, UniqueConstraint)
    assert isinstance(Lead.__table__.c.products_sold.type, JSONB)
    assert isinstance(Lead.__table__.c.required_features.type, JSONB)
    assert isinstance(Lead.__table__.c.objections.type, JSONB)


def test_call_provider_id_is_unique_and_direction_is_limited_to_supported_values() -> None:
    """Catches duplicate Sarvam call records or unsupported call directions."""
    assert "uq_calls_sarvam_call_id" in _constraint_names(Call.__table__, UniqueConstraint)
    direction_type = Call.__table__.c.direction.type
    assert isinstance(direction_type, Text)
    assert {member.value for member in CallDirection} == {"INITIAL", "CALLBACK"}


def test_a_call_can_name_the_callback_that_placed_it() -> None:
    """Catches losing the link /tools/complete-call needs to close its callback."""
    callback_id = Call.__table__.c.callback_id
    assert callback_id.nullable is True
    assert callback_id.references(Callback.__table__.c.id)
    assert "ix_calls_callback_id" in {index.name for index in Call.__table__.indexes}


def test_callback_states_run_pending_to_in_progress_to_a_terminal_outcome() -> None:
    """Catches a worker lifecycle that cannot express a dialled-but-unfinished callback."""
    assert {member.value for member in CallbackStatus} == {
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }


def test_audit_events_cover_every_delivery_and_callback_transition() -> None:
    """Catches an action the agent takes that leaves no trace in the audit log."""
    values = {member.value for member in EventType}
    for kind in MessageKind:
        assert {
            kind.requested_event.value,
            kind.sent_event.value,
            kind.failed_event.value,
        } <= values
    assert {
        "CALL_COMPLETED",
        "CALLBACK_SCHEDULED",
        "CALLBACK_ATTEMPTED",
        "CALLBACK_TRIGGERED",
        "CALLBACK_COMPLETED",
        "CALLBACK_FAILED",
    } <= values
    assert isinstance(AuditEvent.__table__.c.payload.type, JSONB)


def test_one_message_per_call_and_kind_is_enforced_by_the_database() -> None:
    """Catches the WhatsApp idempotency key being weakened to an application check."""
    unique = next(
        constraint
        for constraint in Message.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert [column.name for column in unique.columns] == ["call_id", "kind"]
    assert unique.name == "uq_messages_call_id_kind"
    assert {member.value for member in MessageStatus} == {"RESERVED", "SENT", "FAILED"}


def test_each_callback_dial_is_recorded_once_against_its_attempt_number() -> None:
    """Catches attempt history collapsing into a single overwritten row."""
    unique = next(
        constraint
        for constraint in CallbackAttempt.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert [column.name for column in unique.columns] == ["callback_id", "attempt_number"]
    assert CallbackAttempt.__table__.c.callback_id.references(Callback.__table__.c.id)
    assert {member.value for member in CallbackAttemptStatus} == {"PLACED", "FAILED"}


def test_enum_backed_columns_use_text_and_named_checks_matching_the_migration() -> None:
    """Catches ORM VARCHAR/Enum types or check values that diverge from deployed TEXT columns."""
    assert isinstance(Call.__table__.c.direction.type, Text)
    assert isinstance(Callback.__table__.c.status.type, Text)
    assert isinstance(AuditEvent.__table__.c.event_type.type, Text)
    assert isinstance(Message.__table__.c.kind.type, Text)
    assert isinstance(CallbackAttempt.__table__.c.status.type, Text)
    checks = {
        constraint.name: str(constraint.sqltext)
        for model in (Call, Callback, CallbackAttempt, AuditEvent, Message)
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert checks["ck_calls_direction"] == "direction IN ('INITIAL', 'CALLBACK')"
    assert (
        checks["ck_callbacks_status"]
        == "status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')"
    )
    assert checks["ck_messages_status"] == "status IN ('RESERVED', 'SENT', 'FAILED')"
    assert checks["ck_callback_attempts_status"] == "status IN ('PLACED', 'FAILED')"
    assert "HIGH_INTENT_WHATSAPP_SENT" in checks["ck_audit_events_event_type"]


def test_all_foreign_keys_are_indexed_and_pending_callbacks_have_execution_index() -> None:
    """Catches missing indexes that would make lead/callback/message lookups degrade with volume."""
    expected = {
        Call: {"ix_calls_lead_id", "ix_calls_callback_id"},
        Callback: {
            "ix_callbacks_lead_id",
            "ix_callbacks_source_call_id",
            "ix_callbacks_pending_execution",
        },
        CallbackAttempt: {"ix_callback_attempts_callback_id", "ix_callback_attempts_call_id"},
        AuditEvent: {"ix_audit_events_lead_id", "ix_audit_events_call_id"},
        Message: {"ix_messages_lead_id", "ix_messages_call_id"},
    }
    for model, expected_indexes in expected.items():
        assert expected_indexes <= {index.name for index in model.__table__.indexes}
        foreign_key_columns = {
            foreign_key.parent.name
            for constraint in model.__table__.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            for foreign_key in constraint.elements
        }
        indexed_columns = {
            column.name
            for index in model.__table__.indexes
            for column in index.columns
        }
        assert foreign_key_columns <= indexed_columns

    pending_index = next(
        index
        for index in Callback.__table__.indexes
        if index.name == "ix_callbacks_pending_execution"
    )
    assert pending_index.dialect_options["postgresql"]["where"] is not None


def test_identity_keys_and_timestamps_are_postgresql_compatible() -> None:
    """Catches accidental client-generated IDs or timestamp columns without time zones."""
    for model in (Lead, Call, Callback, CallbackAttempt, AuditEvent, Message):
        assert model.__table__.c.id.identity is not None
        assert model.__table__.c.id.identity.always is True

    for column in (
        Lead.__table__.c.created_at,
        Lead.__table__.c.updated_at,
        Call.__table__.c.started_at,
        Call.__table__.c.ended_at,
        Call.__table__.c.created_at,
        Callback.__table__.c.scheduled_at,
        Callback.__table__.c.next_attempt_at,
        Callback.__table__.c.claimed_at,
        Callback.__table__.c.created_at,
        Callback.__table__.c.completed_at,
        CallbackAttempt.__table__.c.created_at,
        AuditEvent.__table__.c.created_at,
        Message.__table__.c.created_at,
        Message.__table__.c.sent_at,
    ):
        assert column.type.timezone is True
