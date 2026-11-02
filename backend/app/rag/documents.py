"""Load the knowledge documents (Markdown) and split them into chunks along their sections."""

from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.rag.base import Chunk

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_by_section = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "title"), ("##", "section")])
_by_size = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def split_document(source: str, markdown: str) -> list[Chunk]:
    """One chunk per section; long sections are split further by size."""
    chunks = []
    for section in _by_size.split_documents(_by_section.split_text(markdown)):
        title = " - ".join(str(section.metadata[key]) for key in ("title", "section") if key in section.metadata)
        chunks.append(Chunk(source=source, title=title or source, text=section.page_content))
    return chunks


def load_chunks(directory: Path) -> list[Chunk]:
    """All chunks of all Markdown files in a directory, in a stable order."""
    return [
        chunk
        for path in sorted(directory.glob("*.md"))
        for chunk in split_document(path.name, path.read_text(encoding="utf-8"))
    ]
