from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

import app.db.tables  # noqa: F401  (registers the tables on Base.metadata)
from app.config import get_settings
from app.db.base import Base
from app.db.session import make_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Tests pass a URL through the Alembic config; otherwise DATABASE_URL from the settings.
url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # SQLite batch mode rebuilds a table by dropping it; with the app engine's foreign keys on,
    # that drop cascades and deletes every child row (0002 lost all teams that way). Migrations
    # therefore run with SQLite's default, foreign keys off.
    engine = create_engine(url) if url.startswith("sqlite") else make_engine(url)
    with engine.connect() as connection:
        # Batch mode lets later ALTERs work on SQLite.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
