"""Retrieval evaluation: does the right policy document come back, and are off-topic questions declined?

Uses the production chunking, embedding model and relevance threshold (in memory, so no database is
needed), logs parameters, metrics and per-question results as an MLflow run, and exits with code 1
when a metric is below the threshold, so CI can block a change that makes retrieval worse.

    uv run python -m evals.rag_eval                     # logs to a local MLflow file store
    MLFLOW_TRACKING_URI=http://localhost:5000 uv run python -m evals.rag_eval   # to the MLflow server
"""

import argparse
import json
import os
import sys
from pathlib import Path

import mlflow
from pydantic import BaseModel

from app.config import Settings
from app.rag.documents import CHUNK_OVERLAP, CHUNK_SIZE, load_chunks
from app.rag.embeddings import DEFAULT_MODEL, LocalEmbeddings
from app.rag.memory import InMemoryKnowledgeBase

HERE = Path(__file__).parent
QUESTIONS = HERE / "policy_questions.jsonl"
KNOWLEDGE_DIR = HERE.parent / "knowledge"
MIN_SCORE: float = Settings.model_fields["rag_min_score"].default  # the threshold production uses


class Case(BaseModel):
    """One question and the document that answers it (None: off-topic, should be declined)."""

    question: str
    expected_source: str | None


class CaseResult(Case):
    """What retrieval returned for a case."""

    retrieved: list[str]
    best_score: float
    rank: int  # position of the expected document among the relevant hits; 0 = not found

    @property
    def declined(self) -> bool:
        """Nothing scored above the relevance threshold, so the assistant would not answer."""
        return self.best_score < MIN_SCORE


def evaluate(knowledge: InMemoryKnowledgeBase, cases: list[Case], k: int) -> list[CaseResult]:
    """Search every question and record where the expected document ended up."""
    results = []
    for case in cases:
        hits = knowledge.search(case.question, k=k)
        relevant = [hit.source for hit in hits if hit.score >= MIN_SCORE]
        rank = relevant.index(case.expected_source) + 1 if case.expected_source in relevant else 0
        best = hits[0].score if hits else 0.0
        results.append(CaseResult(**case.model_dump(), retrieved=relevant, best_score=best, rank=rank))
    return results


def metrics(results: list[CaseResult]) -> dict[str, float]:
    """Hit rate@k and MRR over answerable questions; decline rate over off-topic questions."""
    answerable = [r for r in results if r.expected_source]
    off_topic = [r for r in results if not r.expected_source]
    return {
        "hit_rate": sum(r.rank > 0 for r in answerable) / len(answerable),
        "mrr": sum(1 / r.rank for r in answerable if r.rank) / len(answerable),
        "off_topic_declined": sum(r.declined for r in off_topic) / len(off_topic) if off_topic else 1.0,
    }


def log_to_mlflow(model: str, k: int, threshold: float, results: list[CaseResult], scores: dict[str, float]) -> None:
    """Record the run: parameters, metrics and every question's result."""
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{HERE / 'mlflow.db'}"))
    mlflow.set_experiment("rag-retrieval-eval")
    with mlflow.start_run():
        mlflow.log_params({"embedding_model": model, "k": k, "min_score": MIN_SCORE, "threshold": threshold})
        mlflow.log_params({"chunk_size": CHUNK_SIZE, "chunk_overlap": CHUNK_OVERLAP, "questions": len(results)})
        mlflow.log_metrics(scores)
        mlflow.log_dict({"results": [r.model_dump() for r in results]}, "results.json")


def report(results: list[CaseResult]) -> None:
    """Print one line per question."""
    for r in results:
        if r.expected_source:
            outcome = f"rank {r.rank}" if r.rank else "MISS  "
        else:
            outcome = "declined" if r.declined else "ANSWERED"
        print(f"{outcome:8}  {r.best_score:.2f}  {r.question}  (expected {r.expected_source}, got {r.retrieved})")


def main() -> None:
    """Run the evaluation, log it to MLflow and enforce the threshold."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=0.85, help="minimum for every metric")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    cases = [Case.model_validate_json(line) for line in QUESTIONS.read_text("utf-8").splitlines() if line]
    knowledge = InMemoryKnowledgeBase(LocalEmbeddings(args.model), args.model)
    knowledge.sync(load_chunks(KNOWLEDGE_DIR))
    results = evaluate(knowledge, cases, args.k)
    scores = metrics(results)
    log_to_mlflow(args.model, args.k, args.threshold, results, scores)

    report(results)
    print(json.dumps(scores))
    failing = {name: value for name, value in scores.items() if value < args.threshold}
    if failing:
        print(f"FAIL: below the threshold {args.threshold:.2f}: {failing}")
        sys.exit(1)


if __name__ == "__main__":
    main()
