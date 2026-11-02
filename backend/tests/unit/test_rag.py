"""Chunking, embeddings and the in-memory knowledge base."""

from app.rag.base import Chunk
from app.rag.documents import split_document
from app.rag.embeddings import HashingEmbeddings
from app.rag.memory import InMemoryKnowledgeBase, cosine
from tests.conftest import KNOWLEDGE_DIR

DOC = """# Partner pension

## Amount
The partner receives 70% of the retirement pension.

## Orphan's pension
Children receive 14% per child.
"""


def test_documents_are_split_per_section_with_titles() -> None:
    chunks = split_document("partner-pension.md", DOC)
    assert [c.title for c in chunks] == ["Partner pension - Amount", "Partner pension - Orphan's pension"]
    assert chunks[0].text == "The partner receives 70% of the retirement pension."
    assert {c.source for c in chunks} == {"partner-pension.md"}


def test_long_sections_are_split_by_size() -> None:
    long_section = "# Doc\n\n## Long\n" + " ".join(f"Sentence number {i} about pensions." for i in range(100))
    chunks = split_document("doc.md", long_section)
    assert len(chunks) > 1
    assert all(len(c.text) <= 800 for c in chunks)


def test_every_knowledge_document_produces_chunks() -> None:
    sources = {path.name for path in KNOWLEDGE_DIR.glob("*.md")}
    chunks = [c for path in KNOWLEDGE_DIR.glob("*.md") for c in split_document(path.name, path.read_text("utf-8"))]
    assert {c.source for c in chunks} == sources


def test_chunk_key_changes_with_content_and_model() -> None:
    chunk = Chunk(source="a.md", title="A", text="text")
    assert chunk.key("model-1") == Chunk(source="a.md", title="A", text="text").key("model-1")
    assert chunk.key("model-1") != chunk.key("model-2")
    assert chunk.key("model-1") != Chunk(source="a.md", title="A", text="changed").key("model-1")


def test_hashing_embeddings_are_normalised_and_lexical() -> None:
    embeddings = HashingEmbeddings()
    a, b, c = embeddings.embed_documents(["partner pension amount", "partner pension", "weather in Paris"])
    assert abs(cosine(a, a) - 1.0) < 1e-9
    assert cosine(a, b) > cosine(a, c)
    assert embeddings.embed_query("") == [0.0] * 384
    assert cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_sync_is_idempotent_and_removes_stale_chunks() -> None:
    knowledge = InMemoryKnowledgeBase(HashingEmbeddings(), "hashing")
    chunks = split_document("partner-pension.md", DOC)
    assert knowledge.sync(chunks).added == 2
    assert knowledge.sync(chunks).model_dump() == {"added": 0, "removed": 0, "unchanged": 2}
    result = knowledge.sync(chunks[:1])
    assert (result.removed, result.unchanged) == (1, 1)


def test_search_returns_the_most_similar_chunks_first() -> None:
    knowledge = InMemoryKnowledgeBase(HashingEmbeddings(), "hashing")
    knowledge.sync(split_document("partner-pension.md", DOC))
    hits = knowledge.search("How much do children receive per child?", k=2)
    assert hits[0].title == "Partner pension - Orphan's pension"
    assert hits[0].score > hits[1].score
