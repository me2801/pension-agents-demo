"""Operator commands.

python -m app.cli ingest     load the knowledge documents into pgvector (idempotent)
"""

import argparse
import logging

from app.config import Settings, get_settings
from app.db.engine import create_sessions
from app.db.knowledge import create_knowledge_base
from app.rag.base import SyncResult
from app.rag.documents import load_chunks

logger = logging.getLogger("app.cli")


def ingest(settings: Settings) -> SyncResult:
    """Chunk and embed the knowledge documents; only new or changed chunks are embedded."""
    engine, sessions = create_sessions(settings.database_url)
    try:
        chunks = load_chunks(settings.knowledge_dir)
        result = create_knowledge_base(settings, sessions).sync(chunks)
    finally:
        engine.dispose()
    logger.info("Knowledge base: %s chunks from %s", len(chunks), settings.knowledge_dir)
    logger.info("Added %s, removed %s, unchanged %s", result.added, result.removed, result.unchanged)
    return result


def main(argv: list[str] | None = None) -> None:
    """Parse the command line and run the command."""
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["ingest"])
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ingest(get_settings())


if __name__ == "__main__":
    main()
