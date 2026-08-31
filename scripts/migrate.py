"""Run Alembic migrations against the session-mode pooler.

Supabase's transaction pooler (port 6543) is fine for the running app but not
for DDL, so deployments point DIRECT_URL at the session-mode pooler (5432) and
this script swaps it in for the duration of the upgrade.

    python scripts/migrate.py
"""

from __future__ import annotations

import os
import re

SCHEMES = ("postgresql+asyncpg://", "postgresql://", "postgres://")


def clean_url(raw: str) -> str:
    """Strip the artifacts of copying a URL out of a .env comment or a shell.

    The session-mode URL lives commented in .env, so the leading "#", wrapping
    quotes, and angle brackets all travel with it on a careless paste.
    """
    value = raw.strip().strip('"').strip("'").strip()
    value = re.sub(r"^#+\s*", "", value)
    value = value.strip("<>").strip()
    return value


def describe_bad_url(value: str) -> str:
    """Name what is wrong with a URL without ever echoing the password."""
    if not value:
        return "it is empty"
    redacted = re.sub(r"//[^@/]*@", "//<redacted>@", value)
    prefix = redacted[:40]
    if not value.startswith(SCHEMES):
        return f"it does not start with postgresql:// -- got {prefix!r}"
    return f"it could not be parsed -- got {prefix!r}"


def resolve_url() -> tuple[str, str] | None:
    direct_url = clean_url(os.environ.get("DIRECT_URL", ""))
    if direct_url:
        return direct_url, "DIRECT_URL (session-mode pooler)"
    database_url = clean_url(os.environ.get("DATABASE_URL", ""))
    if database_url:
        return database_url, "DATABASE_URL (DIRECT_URL not set)"
    return None


def main() -> int:
    resolved = resolve_url()
    if resolved is None:
        print("migrate: neither DIRECT_URL nor DATABASE_URL is set")
        return 2
    url, source = resolved
    if not url.startswith(SCHEMES):
        print(f"migrate: {source} is unusable -- {describe_bad_url(url)}")
        print("migrate: expected postgresql://USER:PASSWORD@HOST:5432/postgres")
        print("migrate: the session-mode URL is the commented line in .env;")
        print("migrate: copy the URL only, without the leading '#'.")
        return 2
    if ":6543/" in url:
        print("migrate: refusing to run DDL through the transaction pooler (:6543).")
        print("migrate: set DIRECT_URL to the session-mode URL on port 5432.")
        return 2

    # alembic/env.py reads DATABASE_URL through Settings, so override it before
    # anything imports app.config and caches the value.
    os.environ["DATABASE_URL"] = url
    print(f"migrate: using {source}")

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    print("migrate: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
