"""Slate — step-graph capture for AI agent debugging.

Public surface (§11) — HAND-CODED contract, implementations may evolve freely:

    slate.init(api_key=..., project_id=...)
    run = slate.start_agent_run(agent_id=..., agent_version=...)
    step = run.step(type="retrieval", name="fetch_docs", parents=[...])
    step.set_input(...); step.set_output(...); step.end(model=..., input_tokens=...)
    run.fail(reason=...)  /  run.succeed(final_output=...)

    slate.instrument_langgraph(graph, agent_id=...)     # Tier (a) — Phase 1
    slate.from_otel_spans(spans)                        # Tier (c) — Phase 1
    slate.trace_completion(fn, metadata)                # degenerate single-step case
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence, TypedDict, TypeVar

from ._client import SlateClient
from ._models import AgentRun, Step, StepType

__all__ = [
    "SlateConfig",
    "init",
    "start_agent_run",
    "instrument_langgraph",
    "from_otel_spans",
    "trace_completion",
    "AgentRun",
    "Step",
    "StepType",
]

T = TypeVar("T")

_client: Optional[SlateClient] = None


class SlateConfig(TypedDict, total=False):
    api_key: str
    base_url: str               # default: https://api.slate.io
    project_id: str
    flush_interval_ms: int      # default: 5000
    batch_size: int             # default: 50
    enabled: bool               # default: True — set False in local dev
    sample_success_rate: float  # default: 0.05 — fraction of successful runs analyzed


def init(**config: Any) -> None:
    """Initialize the global client. Call once at process start."""
    global _client
    _client = SlateClient(**config)


def start_agent_run(
    *,
    agent_id: str,
    agent_version: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AgentRun:
    """Tier (b): manual step API for custom agents."""
    return AgentRun(_require_client(), agent_id, agent_version, metadata)


def instrument_langgraph(graph: Any, *, agent_id: str, agent_version: Optional[str] = None) -> Any:
    """Tier (a): LangGraph auto-instrumentation — 3-line setup.

    TODO(Phase 1): wrap graph node execution to emit steps automatically
    (node -> step, edges -> parents, LLM calls -> token capture).
    """
    raise NotImplementedError("instrument_langgraph ships in Phase 1 — track the repo")


def from_otel_spans(spans: Sequence[Any]) -> AgentRun:
    """Tier (c): map OTel GenAI semantic-convention spans onto a Slate step graph.

    TODO(Phase 1): span.kind + gen_ai.* attributes -> typed steps; parent span
    ids -> step edges.
    """
    raise NotImplementedError("from_otel_spans ships in Phase 1 — track the repo")


def trace_completion(fn: Callable[[], T], metadata: Optional[dict] = None) -> T:
    """Degenerate single-step case (kept from the original design): captures one
    llm step around a single completion call."""
    run = start_agent_run(agent_id=(metadata or {}).get("agent_id", "completion"),
                          metadata=metadata)
    step = run.step(type="llm", name="completion")
    try:
        result = fn()
    except Exception:
        step.end()
        run.fail(reason="exception")
        raise
    step.set_output(result)
    step.end()
    run.succeed()
    return result


def _require_client() -> SlateClient:
    if _client is None:
        raise RuntimeError("slate.init(...) must be called before starting a run")
    return _client
