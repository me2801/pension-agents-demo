"""An in-memory KnowledgeBase: for tests and offline evaluation (same chunking and embeddings as pgvector)."""

import math

from langchain_core.embeddings import Embeddings

from app.rag.base import Chunk, KnowledgeBase, Passage, SyncResult


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryKnowledgeBase(KnowledgeBase):
    """Keeps chunks and their vectors in a list; exhaustive search."""

    def __init__(self, embeddings: Embeddings, embedding_model: str):
        self._embeddings = embeddings
        self._model = embedding_model
        self._items: dict[str, tuple[Chunk, list[float]]] = {}

    def sync(self, chunks: list[Chunk]) -> SyncResult:
        """Replace the contents, embedding only chunks that are new."""
        wanted = {chunk.key(self._model): chunk for chunk in chunks}
        new = [key for key in wanted if key not in self._items]
        removed = [key for key in self._items if key not in wanted]
        vectors = self._embeddings.embed_documents([wanted[key].embedding_text for key in new])
        for key in removed:
            del self._items[key]
        for key, vector in zip(new, vectors, strict=True):
            self._items[key] = (wanted[key], vector)
        return SyncResult(added=len(new), removed=len(removed), unchanged=len(wanted) - len(new))

    def _search(self, query: str, k: int) -> list[Passage]:
        query_vector = self._embeddings.embed_query(query)
        scored = [
            Passage(source=chunk.source, title=chunk.title, text=chunk.text, score=cosine(query_vector, vector))
            for chunk, vector in self._items.values()
        ]
        return sorted(scored, key=lambda passage: passage.score, reverse=True)[:k]
