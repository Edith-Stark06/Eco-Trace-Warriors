"""Alembic environment configuration for Device AI (P5.4)."""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

# Ensure current package and parent are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import device_ai.database.models  # noqa: F401 - ensure models are imported
from device_ai.database.base import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# Override URL from environment if present
db_url = os.getenv("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Revision IDs in this project follow "NNN_description" (e.g.
# "003_add_p511_external_trust_anchors", 36 characters) rather than
# Alembic's typical short hash IDs, and Alembic's own `version_num` column
# is hardcoded to VARCHAR(32) (alembic/ddl/impl.py — not the documented
# `EnvironmentContext.configure()` API; there is no supported parameter to
# widen it, despite `version_table_col_length` having once been added here
# under the mistaken belief that it was one — it is not a real Alembic
# option and was silently ignored, verified against Alembic 1.19.1's own
# `configure()` signature (P7.10)). A revision ID this long makes the very
# first `alembic upgrade head` against a genuinely fresh database fail with
# `StringDataRightTruncation` on migration 003 — confirmed by actually
# running it against a disposable database (P7.10), not assumed. The
# project's one existing shared database only "works" because its
# `alembic_version` table was widened by hand, outside of any tracked
# migration, at some undocumented point in the past.
_VERSION_TABLE_COLUMN_LENGTH = 64


def _ensure_wide_version_table(connection: object) -> None:
    """Pre-create `alembic_version` with a wide enough `version_num`.

    Runs before Alembic's own bootstrap, so it finds an existing
    (correctly-sized) table instead of creating its own VARCHAR(32) one. A
    no-op if the table already exists (this project's real database
    included) — Alembic never alters an existing version table's structure.

    Commits immediately, in its own transaction, separate from the
    migrations that follow: `context.begin_transaction()` detects an
    already-open (autobegin) transaction on this connection and, finding
    one, deliberately does *not* take ownership of committing it (returns a
    no-op context manager) — confirmed by reading
    `alembic.runtime.migration.MigrationContext.begin_transaction`. Without
    this explicit commit here, the whole run (including this table) would
    silently roll back when the connection closes, since neither this
    function nor Alembic would ever commit it (found by actually running
    the fix and discovering the table vanished after a clean, error-free
    run — P7.10).
    """
    connection.execute(  # type: ignore[attr-defined]
        text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            f"version_num VARCHAR({_VERSION_TABLE_COLUMN_LENGTH}) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ")"
        )
    )
    connection.commit()  # type: ignore[attr-defined]


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL, does not execute).

    NOTE: this project has never actually used `--sql`/offline mode
    (confirmed: no script or doc references it) — the version-table-width
    fix above only applies to the online path, since offline mode has no
    live connection to pre-create anything against. Documented here rather
    than silently left as a latent gap: offline mode against a fresh target
    database would hit the same VARCHAR(32) truncation this phase found and
    fixed for online mode.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        _ensure_wide_version_table(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
