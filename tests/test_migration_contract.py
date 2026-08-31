from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import (
    Base,
    CallbackAttemptStatus,
    CallbackStatus,
    EventType,
    MessageKind,
    MessageStatus,
)


class SqlRecorder:
    """Small Alembic operation boundary that records the PostgreSQL SQL migration emits."""

    def __init__(self, *existing: str) -> None:
        self.sql: list[str] = []
        self.metadata = sa.MetaData()
        for name in existing:
            sa.Table(
                name,
                self.metadata,
                sa.Column("id", sa.BigInteger(), primary_key=True),
                schema="sales_agent",
            )

    def execute(self, statement: object) -> None:
        self.sql.append(str(statement))

    def create_table(self, name: str, *columns: object, **kwargs: object) -> sa.Table:
        table = sa.Table(name, self.metadata, *columns, **kwargs)
        self.sql.append(str(CreateTable(table).compile(dialect=postgresql.dialect())))
        return table

    def drop_table(self, name: str, **kwargs: object) -> None:
        self.sql.append(f"DROP TABLE {kwargs.get('schema')}.{name}")

    def add_column(self, table_name: str, column: object, **kwargs: object) -> None:
        schema = kwargs.get("schema")
        table = self.metadata.tables.get(f"{schema}.{table_name}")
        if table is not None:
            table.append_column(column)  # type: ignore[arg-type]
        self.sql.append(
            f"ALTER TABLE {schema}.{table_name} ADD COLUMN "
            f"{column.name} {column.type}"  # type: ignore[attr-defined]
        )

    def create_foreign_key(
        self, name: str, source: str, referent: str, local: list[str], remote: list[str], **kwargs: object
    ) -> None:
        self.sql.append(
            f"ALTER TABLE {kwargs.get('source_schema')}.{source} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({', '.join(local)}) REFERENCES "
            f"{kwargs.get('referent_schema')}.{referent} ({', '.join(remote)})"
        )

    def create_index(self, name: str, table_name: str, columns: list[object], **kwargs: object) -> None:
        schema = kwargs.pop("schema", None)
        key = f"{schema}.{table_name}" if schema else table_name
        table = self.metadata.tables.get(key)
        if table is None:
            self.sql.append(f"CREATE INDEX {name} ON {key} ({', '.join(map(str, columns))})")
            return
        expressions = [table.c[column] if isinstance(column, str) else column for column in columns]
        index = sa.Index(name, *expressions, **kwargs)
        self.sql.append(str(CreateIndex(index).compile(dialect=postgresql.dialect())))


def _migration(filename: str) -> object:
    path = Path("alembic/versions") / filename
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_sql(filename: str, *existing: str) -> str:
    migration = _migration(filename)
    recorder = SqlRecorder(*existing)
    migration.op = recorder  # type: ignore[attr-defined]
    migration.upgrade()  # type: ignore[attr-defined]
    return "\n".join(recorder.sql)


def test_initial_migration_emits_private_schema_and_operational_postgresql_contract() -> None:
    """Catches a migration that omits private-schema, identity, index, uniqueness, or role-safety guarantees."""
    sql = _upgrade_sql("20260822_0001_sales_backend.py").upper()

    assert "CREATE SCHEMA IF NOT EXISTS SALES_AGENT" in sql
    assert sql.count("GENERATED ALWAYS AS IDENTITY") == 4
    assert "CREATE TABLE SALES_AGENT.LEADS" in sql
    assert "CREATE TABLE SALES_AGENT.CALLS" in sql
    assert "CREATE TABLE SALES_AGENT.CALLBACKS" in sql
    assert "CREATE TABLE SALES_AGENT.EVENTS" in sql
    assert "CONSTRAINT PK_LEADS PRIMARY KEY (ID)" in sql
    assert "CONSTRAINT PK_CALLS PRIMARY KEY (ID)" in sql
    assert "CONSTRAINT PK_CALLBACKS PRIMARY KEY (ID)" in sql
    assert "CONSTRAINT PK_EVENTS PRIMARY KEY (ID)" in sql
    assert "CONSTRAINT UQ_LEADS_NORMALIZED_PHONE UNIQUE (NORMALIZED_PHONE)" in sql
    assert "CONSTRAINT UQ_CALLS_SARVAM_CALL_ID UNIQUE (SARVAM_CALL_ID)" in sql
    assert "CONSTRAINT UQ_CALLBACKS_SOURCE_CALL_SCHEDULED_AT UNIQUE (SOURCE_CALL_ID, SCHEDULED_AT)" in sql
    assert "DIRECTION TEXT NOT NULL" in sql
    assert "STATUS TEXT DEFAULT 'PENDING' NOT NULL" in sql
    assert "EVENT_TYPE TEXT NOT NULL" in sql
    assert "CREATE INDEX IX_CALLS_LEAD_ID" in sql
    assert "CREATE INDEX IX_CALLBACKS_LEAD_ID" in sql
    assert "CREATE INDEX IX_CALLBACKS_SOURCE_CALL_ID" in sql
    assert "CREATE INDEX IX_EVENTS_LEAD_ID" in sql
    assert "CREATE INDEX IX_EVENTS_CALL_ID" in sql
    assert "CREATE INDEX IX_CALLBACKS_PENDING_EXECUTION" in sql
    assert "WHERE STATUS = 'PENDING'" in sql
    assert "REVOKE ALL ON SCHEMA SALES_AGENT FROM ANON" in sql
    assert "REVOKE ALL ON SCHEMA SALES_AGENT FROM AUTHENTICATED" in sql


ARCHITECTURE_MIGRATION = "20260830_0004_architecture_data_layer.py"


def test_architecture_migration_renames_events_and_keeps_its_named_constraints() -> None:
    """Catches a rename that leaves the audit table carrying the old constraint and index names."""
    sql = _upgrade_sql(ARCHITECTURE_MIGRATION, "leads", "calls", "callbacks")

    assert "ALTER TABLE sales_agent.events RENAME TO audit_events" in sql
    for old, new in (
        ("pk_events", "pk_audit_events"),
        ("fk_events_lead_id_leads", "fk_audit_events_lead_id_leads"),
        ("fk_events_call_id_calls", "fk_audit_events_call_id_calls"),
        ("ck_events_event_type", "ck_audit_events_event_type"),
    ):
        assert f"RENAME CONSTRAINT {old} TO {new}" in sql
    assert "ALTER INDEX sales_agent.ix_events_lead_id RENAME TO ix_audit_events_lead_id" in sql
    assert "ALTER INDEX sales_agent.ix_events_call_id RENAME TO ix_audit_events_call_id" in sql


def test_architecture_migration_creates_the_tables_the_diagram_names() -> None:
    """Catches callback_attempts or messages existing only in the ORM, never in PostgreSQL."""
    sql = _upgrade_sql(ARCHITECTURE_MIGRATION, "leads", "calls", "callbacks").upper()

    assert "CREATE TABLE SALES_AGENT.CALLBACK_ATTEMPTS" in sql
    assert "CREATE TABLE SALES_AGENT.MESSAGES" in sql
    assert "CONSTRAINT UQ_MESSAGES_CALL_ID_KIND UNIQUE (CALL_ID, KIND)" in sql
    assert (
        "CONSTRAINT UQ_CALLBACK_ATTEMPTS_CALLBACK_ID_ATTEMPT_NUMBER UNIQUE "
        "(CALLBACK_ID, ATTEMPT_NUMBER)" in sql
    )
    assert "FK_MESSAGES_CALL_ID_CALLS" in sql
    assert "FK_CALLBACK_ATTEMPTS_CALLBACK_ID_CALLBACKS" in sql
    assert "DROP TABLE SALES_AGENT.DELIVERY_RESERVATIONS" in sql
    assert "INSERT INTO SALES_AGENT.MESSAGES" in sql


def test_architecture_migration_links_calls_to_callbacks_and_retires_triggered() -> None:
    """Catches a deployed schema that cannot record a callback moving to IN_PROGRESS."""
    sql = _upgrade_sql(ARCHITECTURE_MIGRATION, "leads", "calls", "callbacks")

    assert "ADD COLUMN callback_id" in sql
    assert "fk_calls_callback_id_callbacks" in sql
    assert "CREATE INDEX ix_calls_callback_id" in sql
    assert "SET status = 'IN_PROGRESS' WHERE status = 'TRIGGERED'" in sql
    assert "IN_PROGRESS" in sql and "'TRIGGERED'," not in sql


def test_architecture_migration_secures_the_new_tables() -> None:
    """Catches a new private table reachable through Supabase's anon and authenticated roles."""
    sql = _upgrade_sql(ARCHITECTURE_MIGRATION, "leads", "calls", "callbacks")

    for table in ("callback_attempts", "messages"):
        assert f"ALTER TABLE sales_agent.{table} ENABLE ROW LEVEL SECURITY" in sql


def test_deployed_check_constraints_match_the_enums_the_application_writes() -> None:
    """Catches an enum gaining a value the deployed CHECK constraint would reject."""
    sql = _upgrade_sql(ARCHITECTURE_MIGRATION, "leads", "calls", "callbacks")

    for enum in (EventType, CallbackStatus, MessageKind, MessageStatus, CallbackAttemptStatus):
        for member in enum:
            assert f"'{member.value}'" in sql, f"{enum.__name__}.{member.name} missing"


def test_every_orm_table_is_created_by_a_migration() -> None:
    """Catches a model added without the migration that would make it exist in production."""
    created = "\n".join(
        _upgrade_sql(name)
        if name == "20260822_0001_sales_backend.py"
        else _upgrade_sql(name, "leads", "calls", "callbacks")
        for name in (
            "20260822_0001_sales_backend.py",
            "20260822_0002_delivery_reservations.py",
            ARCHITECTURE_MIGRATION,
        )
    )
    for qualified in Base.metadata.tables:
        table = qualified.split(".")[-1]
        assert f"CREATE TABLE sales_agent.{table}" in created or (
            f"RENAME TO {table}" in created
        ), f"{table} is never created by a migration"


def test_pooler_safe_url_disables_the_prepared_statement_cache() -> None:
    from app.database import _pooler_safe_url

    plain = "postgresql+asyncpg://u:p@host:6543/postgres"
    assert _pooler_safe_url(plain).endswith("?prepared_statement_cache_size=0")

    with_query = "postgresql+asyncpg://u:p@host:6543/postgres?ssl=require"
    assert _pooler_safe_url(with_query).endswith("&prepared_statement_cache_size=0")

    already_set = "postgresql+asyncpg://u:p@h/db?prepared_statement_cache_size=0"
    assert _pooler_safe_url(already_set) == already_set
