"""Database engine, sessions and the LangGraph checkpointer."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_sessions(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    """Engine plus session factory. expire_on_commit=False lets repositories return data after commit."""
    engine = create_engine(database_url, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)


def create_postgres_checkpointer(psycopg_url: str) -> tuple[BaseCheckpointSaver[Any], ConnectionPool[Any]]:
    """A Postgres-backed LangGraph checkpointer; creates its tables if needed.

    Returns the pool too, so the caller can close it on shutdown.
    """
    pool: ConnectionPool[Connection[DictRow]] = ConnectionPool(
        psycopg_url,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    saver = PostgresSaver(pool)
    saver.setup()
    return saver, pool
