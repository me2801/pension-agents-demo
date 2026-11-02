# MLflow tracking server: traces of every chat turn, and evaluation runs.
# Traces contain prompts (personal data): keep this server internal.
FROM python:3.12-slim
RUN pip install --no-cache-dir mlflow==3.17.2 \
 && useradd --create-home --uid 10001 mlflow \
 && mkdir /data && chown mlflow /data
USER mlflow
EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"
CMD ["mlflow", "server", "--host", "0.0.0.0", "--port", "5000", \
     "--backend-store-uri", "sqlite:////data/mlflow.db", \
     "--artifacts-destination", "/data/artifacts", "--serve-artifacts", \
     "--allowed-hosts", "mlflow:5000,localhost:5000,127.0.0.1:5000"]
