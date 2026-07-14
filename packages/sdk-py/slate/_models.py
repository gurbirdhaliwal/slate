"""Step-graph capture primitives. The public shapes here are part of the SDK's
public contract (§11/§13) — breaking changes churn early adopters."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Sequence

StepType = Literal["llm", "tool", "retrieval", "handoff"]


class Step:
    """One typed node in the run's step graph."""

    def __init__(
        self,
        run: "AgentRun",
        type: StepType,  # noqa: A002 — public API name fixed by the doc
        name: str,
        parents: Optional[Sequence["Step"]] = None,
    ) -> None:
        self._run = run
        self.client_step_id = uuid.uuid4().hex
        self.type: StepType = type
        self.name = name
        self.parent_client_step_ids = [p.client_step_id for p in (parents or [])]
        self.seq = run._next_seq()
        self._started = time.monotonic()
        self.input: Any = None
        self.output: Any = None
        self.model: Optional[str] = None
        self.input_tokens: Optional[int] = None
        self.output_tokens: Optional[int] = None
        self.latency_ms: Optional[int] = None
        self.ended = False

    def set_input(self, data: Any) -> None:
        self.input = data

    def set_output(self, data: Any) -> None:
        self.output = data

    def end(
        self,
        *,
        model: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> None:
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = int((time.monotonic() - self._started) * 1000)
        self.ended = True

    def _to_payload(self) -> dict[str, Any]:
        return {
            "client_step_id": self.client_step_id,
            "seq": self.seq,
            "parent_client_step_ids": self.parent_client_step_ids,
            "step_type": self.type,
            "name": self.name,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "input": self.input,
            "output": self.output,
        }


class AgentRun:
    """One end-to-end agent execution. fail()/succeed() finalizes the graph and
    hands it to the background flusher — never blocks the caller."""

    def __init__(
        self,
        client: Any,  # slate._client.SlateClient (untyped to avoid a cycle)
        agent_id: str,
        agent_version: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        self._client = client
        self.agent_id = agent_id
        self.agent_version = agent_version
        self.metadata = metadata or {}
        self.steps: list[Step] = []
        self.status: str = "running"
        self.failure_source: Optional[str] = None
        self.started_at = datetime.now(timezone.utc)
        self.ended_at: Optional[datetime] = None
        self._seq_lock = threading.Lock()
        self._seq = 0

    def step(
        self,
        *,
        type: StepType,  # noqa: A002
        name: str,
        parents: Optional[Sequence[Step]] = None,
    ) -> Step:
        s = Step(self, type, name, parents)
        self.steps.append(s)
        return s

    def fail(self, reason: Optional[str] = None) -> None:
        """Marks the run failed — this is what triggers a diagnosis."""
        if reason is not None:
            self.metadata.setdefault("failure_reason", reason)
        self._finalize("failed", failure_source="explicit")

    def succeed(self, final_output: Any = None) -> None:
        if final_output is not None:
            self.metadata.setdefault("final_output", final_output)
        self._finalize("succeeded")

    def _finalize(self, status: str, failure_source: Optional[str] = None) -> None:
        if self.status != "running":
            return  # idempotent — double fail/succeed is a no-op
        self.status = status
        self.failure_source = failure_source
        self.ended_at = datetime.now(timezone.utc)
        self._client.submit_run(self)

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _to_payload(self) -> dict[str, Any]:
        return {
            "run": {
                "agent_id": self.agent_id,
                "agent_version": self.agent_version,
                "status": self.status,
                "failure_source": self.failure_source,
                "started_at": self.started_at.isoformat(),
                "ended_at": self.ended_at.isoformat() if self.ended_at else None,
                "metadata": self.metadata,
            },
            "steps": [s._to_payload() for s in self.steps],
        }
