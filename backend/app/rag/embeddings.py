"""Embedding models, behind LangChain's Embeddings interface.

LocalEmbeddings runs an open-source model inside the backend (ONNX via fastembed): no API key, and
documents and questions never leave our infrastructure. HashingEmbeddings is a deterministic,
lexical stand-in for tests.
"""

import hashlib
import math
import re

from fastembed import TextEmbedding
from langchain_core.embeddings import Embeddings

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # Dutch + English
EMBEDDING_DIM = 384  # must match the model and the knowledge_chunks.embedding column


class LocalEmbeddings(Embeddings):
    """A local multilingual sentence-embedding model."""

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: str | None = None):
        self.model_name = model_name
        self._model = TextEmbedding(model_name, cache_dir=cache_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed document chunks."""
        return [vector.tolist() for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query."""
        return self.embed_documents([text])[0]


class HashingEmbeddings(Embeddings):
    """Bag-of-words vectors via the hashing trick: similar wording -> similar vectors. For tests only."""

    model_name = "hashing"

    def __init__(self, dim: int = EMBEDDING_DIM):
        self._dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed texts."""
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Embed a query."""
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for word in re.findall(r"[a-z0-9]{3,}", text.lower()):
            vector[int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16) % self._dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
