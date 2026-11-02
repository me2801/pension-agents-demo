"""The KnowledgeBase on PostgreSQL + pgvector: chunks and embeddings live next to the app data."""

from langchain_core.embeddings import Embeddings
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.tables import KnowledgeChunkRow
from app.rag.base import Chunk, KnowledgeBase, Passage, SyncResult
from app.rag.embeddings import LocalEmbeddings


def create_knowledge_base(settings: Settings, sessions: sessionmaker[Session]) -> "PgVectorKnowledgeBase":
    """The pgvector knowledge base with the configured local embedding model."""
    embeddings = LocalEmbeddings(settings.embedding_model, settings.embedding_cache_dir)
    return PgVectorKnowledgeBase(sessions, embeddings, settings.embedding_model)


class PgVectorKnowledgeBase(KnowledgeBase):
    """Cosine-similarity search over the knowledge_chunks table (HNSW index)."""

    def __init__(self, sessions: sessionmaker[Session], embeddings: Embeddings, embedding_model: str):
        self._sessions = sessions
        self._embeddings = embeddings
        self._model = embedding_model

    def sync(self, chunks: list[Chunk]) -> SyncResult:
        """Embed and insert new chunks, delete chunks that no longer exist; unchanged ones are kept."""
        wanted = {chunk.key(self._model): chunk for chunk in chunks}
        with self._sessions.begin() as session:
            stored = set(session.scalars(select(KnowledgeChunkRow.key)))
            new = [key for key in wanted if key not in stored]
            stale = stored - wanted.keys()
            if stale:
                session.execute(delete(KnowledgeChunkRow).where(KnowledgeChunkRow.key.in_(stale)))
            vectors = self._embeddings.embed_documents([wanted[key].embedding_text for key in new])
            session.add_all(
                KnowledgeChunkRow(
                    key=key,
                    source=wanted[key].source,
                    title=wanted[key].title,
                    content=wanted[key].text,
                    embedding=vector,
                )
                for key, vector in zip(new, vectors, strict=True)
            )
        return SyncResult(added=len(new), removed=len(stale), unchanged=len(wanted) - len(new))

    def _search(self, query: str, k: int) -> list[Passage]:
        distance = KnowledgeChunkRow.embedding.cosine_distance(self._embeddings.embed_query(query))
        statement = select(KnowledgeChunkRow, distance.label("distance")).order_by(distance).limit(k)
        with self._sessions() as session:
            return [
                Passage(source=row.source, title=row.title, text=row.content, score=1.0 - float(dist))
                for row, dist in session.execute(statement)
            ]
