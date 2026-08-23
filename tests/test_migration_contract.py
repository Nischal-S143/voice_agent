from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable


class SqlRecorder:
    """Small Alembic operation boundary that records the PostgreSQL SQL migration emits."""

    def __init__(self) -> None:
        self.sql: list[str] = []
        self.metadata = sa.MetaData()

    def execute(self, statement: object) -> None:
        self.sql.append(str(statement))

    def create_table(self, name: str, *columns: object, **kwargs: object) -> sa.Table:
        table = sa.Table(name, self.metadata, *columns, **kwargs)
        self.sql.append(str(CreateTable(table).compile(dialect=postgresql.dialect())))
        return table

    def create_index(self, name: str, table_name: str, columns: list[object], **kwargs: object) -> None:
        schema = kwargs.pop("schema", None)
        table = self.metadata.tables[f"{schema}.{table_name}" if schema else table_name]
        expressions = [table.c[column] if isinstance(column, str) else column for column in columns]
        index = sa.Index(name, *expressions, **kwargs)
        self.sql.append(str(CreateIndex(index).compile(dialect=postgresql.dialect())))


def _migration_module() -> object:
    path = Path("alembic/versions/20260822_0001_sales_backend.py")
    spec = importlib.util.spec_from_file_location("sales_backend_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_initial_migration_emits_private_schema_and_operational_postgresql_contract() -> None:
    """Catches a migration that omits private-schema, identity, index, uniqueness, or role-safety guarantees."""
    migration = _migration_module()
    recorder = SqlRecorder()
    migration.op = recorder  # type: ignore[attr-defined]

    migration.upgrade()  # type: ignore[attr-defined]
    sql = "\n".join(recorder.sql).upper()

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


def test_pooler_safe_url_disables_the_prepared_statement_cache() -> None:
    from app.database import _pooler_safe_url

    plain = "postgresql+asyncpg://u:p@host:6543/postgres"
    assert _pooler_safe_url(plain).endswith("?prepared_statement_cache_size=0")

    with_query = "postgresql+asyncpg://u:p@host:6543/postgres?ssl=require"
    assert _pooler_safe_url(with_query).endswith("&prepared_statement_cache_size=0")

    already_set = "postgresql+asyncpg://u:p@h/db?prepared_statement_cache_size=0"
    assert _pooler_safe_url(already_set) == already_set
