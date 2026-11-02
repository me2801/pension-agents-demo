FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.10 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    EMBEDDING_CACHE_DIR=/app/models MLFLOW_DISABLE_AGENT_HINT=1
WORKDIR /app

# Never run as root.
RUN useradd --create-home --uid 10001 appuser

# Dependencies first (cached layer), then the code.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

# Bake the embedding model into the image: containers start offline and identical.
RUN python -c "from fastembed import TextEmbedding; \
TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/app/models')" \
 && chown -R appuser /app/models

COPY alembic.ini ./
COPY alembic ./alembic
COPY knowledge ./knowledge
COPY app ./app

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
# Migrate, sync the knowledge base (only new or changed chunks are embedded), then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m app.cli ingest && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
