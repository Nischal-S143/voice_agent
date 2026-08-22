from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Callback, Call, CallbackStatus, CallDirection, Event, EventType, Lead


def _constraint_names(table: object, constraint_type: type[object]) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, constraint_type) and constraint.name is not None
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


def test_callback_and_event_enums_have_the_durable_state_values() -> None:
    """Catches callback/event state changes that would break worker and idempotency contracts."""
    assert {member.value for member in CallbackStatus} == {
        "PENDING",
        "TRIGGERED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert {
        "HIGH_INTENT_WHATSAPP_SENT",
        "CALL_COMPLETED",
        "CALLBACK_SCHEDULED",
        "CALLBACK_ATTEMPTED",
        "CALLBACK_TRIGGERED",
        "FOLLOWUP_TEXT_SENT",
        "FOLLOWUP_RESUME_SENT",
        "FOLLOWUP_ARCHITECTURE_SENT",
    } <= {member.value for member in EventType}
    assert isinstance(Event.__table__.c.payload.type, JSONB)
    assert "ck_calls_direction" in _constraint_names(Call.__table__, CheckConstraint)
    assert "ck_callbacks_status" in _constraint_names(Callback.__table__, CheckConstraint)
    assert "ck_events_event_type" in _constraint_names(Event.__table__, CheckConstraint)


def test_enum_backed_columns_use_text_and_named_checks_matching_the_migration() -> None:
    """Catches ORM VARCHAR/Enum types or check values that diverge from deployed TEXT columns."""
    assert isinstance(Call.__table__.c.direction.type, Text)
    assert isinstance(Callback.__table__.c.status.type, Text)
    assert isinstance(Event.__table__.c.event_type.type, Text)
    checks = {
        constraint.name: str(constraint.sqltext)
        for model in (Call, Callback, Event)
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert checks["ck_calls_direction"] == "direction IN ('INITIAL', 'CALLBACK')"
    assert checks["ck_callbacks_status"] == "status IN ('PENDING', 'TRIGGERED', 'COMPLETED', 'FAILED', 'CANCELLED')"
    assert "HIGH_INTENT_WHATSAPP_SENT" in checks["ck_events_event_type"]


def test_all_foreign_keys_are_indexed_and_pending_callbacks_have_execution_index() -> None:
    """Catches missing indexes that would make lead/callback/event lookups degrade with volume."""
    expected = {
        "calls": {"ix_calls_lead_id"},
        "callbacks": {"ix_callbacks_lead_id", "ix_callbacks_source_call_id", "ix_callbacks_pending_execution"},
        "events": {"ix_events_lead_id", "ix_events_call_id"},
    }
    for model, expected_indexes in ((Call, expected["calls"]), (Callback, expected["callbacks"]), (Event, expected["events"])):
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

    pending_index = next(index for index in Callback.__table__.indexes if index.name == "ix_callbacks_pending_execution")
    assert pending_index.dialect_options["postgresql"]["where"] is not None


def test_identity_keys_and_timestamps_are_postgresql_compatible() -> None:
    """Catches accidental client-generated IDs or timestamp columns without time zones."""
    for model in (Lead, Call, Callback, Event):
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
        Event.__table__.c.created_at,
    ):
        assert column.type.timezone is True
