"""Run Alembic migrations against the session-mode pooler.

Supabase's transaction pooler (port 6543) is fine for the running app but not
for DDL, so deployments point DIRECT_URL at the session-mode pooler (5432) and
this script swaps it in for the duration of the upgrade.

    python scripts/migrate.py
"""

from __future__ import annotations

import os


def main() -> int:
    direct_url = os.environ.get("DIRECT_URL", "").strip()
    if direct_url:
        # alembic/env.py reads DATABASE_URL through Settings, so override it
        # before anything imports app.config and caches the value.
        os.environ["DATABASE_URL"] = direct_url
        print("migrate: using DIRECT_URL (session-mode pooler)")
    elif os.environ.get("DATABASE_URL", "").strip():
        print("migrate: DIRECT_URL not set, falling back to DATABASE_URL")
    else:
        print("migrate: neither DIRECT_URL nor DATABASE_URL is set")
        return 2

    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")
    print("migrate: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
