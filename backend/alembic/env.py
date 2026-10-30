"""Alembic environment: runs migrations against DATABASE_URL (or a URL set by the caller)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.db.tables import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """URL passed in by tests, else the app's DATABASE_URL."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from app.config import get_settings  # noqa: PLC0415 - only needed when no URL was given

    return get_settings().database_url


def run_migrations_online() -> None:
    """Apply migrations inside one transaction."""
    engine = create_engine(_database_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
