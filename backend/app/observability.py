"""Tracing with MLflow: every LangChain/LangGraph run, model call and retrieval becomes a trace.

Off unless MLFLOW_TRACKING_URI is set, so tests and local runs never write traces by accident.
Traces contain prompts and therefore personal data: the MLflow server must stay internal.
"""

import functools
import logging
from collections.abc import Callable

import mlflow
from mlflow.entities import SpanType

logger = logging.getLogger(__name__)
_state = {"enabled": False}


def configure_tracing(tracking_uri: str | None, experiment: str) -> None:
    """Send traces to an MLflow server, or keep tracing off when no URI is configured."""
    if not tracking_uri:
        mlflow.tracing.disable()
        return
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)
    # Never slow down a chat turn for trace uploads. (MLflow ships this function without type hints.)
    mlflow.config.enable_async_logging(True)  # type: ignore[no-untyped-call]
    mlflow.langchain.autolog()  # LangChain + LangGraph: graph, nodes, model and tool calls
    _state["enabled"] = True
    logger.info("Tracing to MLflow at %s (experiment %r)", tracking_uri, experiment)


def traced_retriever[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Record calls as RETRIEVER spans when tracing is on (autolog doesn't see our own retrieval code)."""
    traced = mlflow.trace(func, span_type=SpanType.RETRIEVER)

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return traced(*args, **kwargs) if _state["enabled"] else func(*args, **kwargs)

    return wrapper
