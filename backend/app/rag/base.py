"""The KnowledgeBase interface. Workflows depend on it; storage (pgvector, in-memory) implements it."""

import hashlib
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.observability import traced_retriever


class Chunk(BaseModel):
    """A piece of a source document, small enough to embed and to quote."""

    source: str  # file name, e.g. "early-retirement.md"
    title: str  # document title and section, e.g. "Early retirement - Effect on your pension"
    text: str

    @property
    def embedding_text(self) -> str:
        """What gets embedded: the title gives the text its context (e.g. what "70%" is about)."""
        return f"{self.title}\n{self.text}"

    def key(self, embedding_model: str) -> str:
        """Content hash: an unchanged chunk embedded with the same model never needs re-embedding."""
        return hashlib.sha256(f"{embedding_model}\n{self.source}\n{self.title}\n{self.text}".encode()).hexdigest()


class Passage(BaseModel):
    """A retrieved chunk with its similarity to the query (cosine, 1 = identical)."""

    source: str
    title: str
    text: str
    score: float


class SyncResult(BaseModel):
    """What a knowledge base sync changed."""

    added: int
    removed: int
    unchanged: int


class KnowledgeBase(ABC):
    """Searchable store of document chunks."""

    @traced_retriever
    def search(self, query: str, k: int = 4) -> list[Passage]:
        """The k chunks most similar to the query, best first (traced as a retrieval span)."""
        return self._search(query, k)

    @abstractmethod
    def _search(self, query: str, k: int) -> list[Passage]:
        """Implementation of search."""

    @abstractmethod
    def sync(self, chunks: list[Chunk]) -> SyncResult:
        """Make the stored chunks equal to `chunks`: embed new ones, delete stale ones."""
