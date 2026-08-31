from __future__ import annotations

import pytest

from scripts.migrate import clean_url, describe_bad_url, main, resolve_url

SESSION_URL = "postgresql://user:secret@aws-0.pooler.supabase.com:5432/postgres"


@pytest.mark.parametrize(
    "pasted",
    [
        f"# {SESSION_URL}",
        f'"{SESSION_URL}"',
        f"'{SESSION_URL}'",
        f"<{SESSION_URL}>",
        f"   {SESSION_URL}   ",
    ],
)
def test_a_url_copied_out_of_the_env_comment_still_works(pasted: str) -> None:
    """Catches a paste artifact surfacing as an unreadable SQLAlchemy parse error."""
    assert clean_url(pasted) == SESSION_URL


def test_a_bad_url_is_explained_without_ever_echoing_the_password() -> None:
    """Catches a diagnostic message leaking the database password into a terminal or log."""
    message = describe_bad_url("mysql://admin:hunter2@host/db")

    assert "hunter2" not in message
    assert "admin" not in message
    assert "<redacted>" in message
    assert describe_bad_url("") == "it is empty"


def test_direct_url_is_preferred_over_the_pooled_application_url(monkeypatch) -> None:
    """Catches migrations silently running through the transaction pooler."""
    monkeypatch.setenv("DIRECT_URL", SESSION_URL)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@host:6543/postgres")

    url, source = resolve_url()

    assert url == SESSION_URL
    assert "DIRECT_URL" in source


def test_running_ddl_through_the_transaction_pooler_is_refused(monkeypatch, capsys) -> None:
    """Catches DDL being attempted on port 6543, where Supabase does not support it."""
    monkeypatch.delenv("DIRECT_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@host:6543/postgres")

    assert main() == 2
    assert "transaction pooler" in capsys.readouterr().out


def test_an_unparseable_url_stops_before_alembic_runs(monkeypatch, capsys) -> None:
    """Catches a malformed URL reaching Alembic and failing with an opaque traceback."""
    monkeypatch.setenv("DIRECT_URL", "not-a-url")

    assert main() == 2
    output = capsys.readouterr().out
    assert "does not start with postgresql://" in output
    assert "without the leading '#'" in output


def test_missing_configuration_is_reported_rather_than_crashing(monkeypatch, capsys) -> None:
    """Catches a bare KeyError when neither URL is configured."""
    monkeypatch.delenv("DIRECT_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert main() == 2
    assert "neither DIRECT_URL nor DATABASE_URL" in capsys.readouterr().out
