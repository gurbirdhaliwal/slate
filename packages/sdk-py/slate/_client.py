"""Background transport. Design principle #1 (§11): capture must NEVER block or
fail the customer's agent — errors are swallowed after logging, runs are
buffered in-process and flushed async."""

from __future__ import annotations

import json
import logging
import queue
import random
import threading
import urllib.error
import urllib.request
from typing import Optional

from ._models import AgentRun

log = logging.getLogger("slate")

_MAX_BUFFERED_RUNS = 1000  # drop (with a log line) rather than grow unbounded


class SlateClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.slate.io",
        project_id: Optional[str] = None,
        flush_interval_ms: int = 5000,
        batch_size: int = 50,
        enabled: bool = True,
        sample_success_rate: float = 0.05,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.flush_interval_ms = flush_interval_ms
        self.batch_size = batch_size
        self.enabled = enabled
        self.sample_success_rate = sample_success_rate
        self._queue: "queue.Queue[AgentRun]" = queue.Queue(maxsize=_MAX_BUFFERED_RUNS)
        self._flusher: Optional[threading.Thread] = None
        if enabled:
            self._flusher = threading.Thread(
                target=self._flush_loop, name="slate-flusher", daemon=True
            )
            self._flusher.start()

    def submit_run(self, run: AgentRun) -> None:
        if not self.enabled:
            return
        # Success-run sampling happens client-side (§11): failed runs always ship,
        # successes ship at sample_success_rate to maintain per-step baselines.
        if run.status == "succeeded" and random.random() > self.sample_success_rate:
            return
        try:
            self._queue.put_nowait(run)
        except queue.Full:
            log.warning("slate buffer full — dropping run for agent %s", run.agent_id)

    def flush(self, timeout_s: float = 10.0) -> None:
        """Best-effort synchronous drain (call before process exit)."""
        deadline = threading.Event()
        drained = threading.Thread(target=self._drain_once)
        drained.start()
        drained.join(timeout_s)
        deadline.set()

    def _flush_loop(self) -> None:
        while True:
            try:
                run = self._queue.get(timeout=self.flush_interval_ms / 1000.0)
            except queue.Empty:
                continue
            self._post_run(run)

    def _drain_once(self) -> None:
        while True:
            try:
                run = self._queue.get_nowait()
            except queue.Empty:
                return
            self._post_run(run)

    def _post_run(self, run: AgentRun) -> None:
        body = json.dumps(run._to_payload(), default=str).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1/ingest/runs",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
        except urllib.error.URLError as exc:
            # Never propagate into the customer's agent (§11 principle 1)
            log.warning("slate ingest failed (run dropped): %s", exc)
