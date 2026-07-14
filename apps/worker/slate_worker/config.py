"""Worker configuration from environment (§7)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    anthropic_api_key: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    concurrency: int
    max_calls_per_10s: int
    verdict_model: str
    escalation_model: str
    log_level: str


def load_config() -> Config:
    return Config(
        database_url=_require("DATABASE_URL"),
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        minio_endpoint=os.environ.get("MINIO_ENDPOINT", "http://localhost:9000"),
        minio_access_key=os.environ.get("MINIO_ROOT_USER", "slate-minio"),
        minio_secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "change-me"),
        minio_bucket=os.environ.get("MINIO_BUCKET", "slate-payloads"),
        concurrency=int(os.environ.get("WORKER_CONCURRENCY", "10")),
        max_calls_per_10s=int(os.environ.get("ANTHROPIC_MAX_CALLS_PER_10S", "50")),
        # Two-tier judging (§18): Haiku for verdicts, Sonnet only on escalation
        verdict_model=os.environ.get("VERDICT_MODEL", "claude-haiku-4-5"),
        escalation_model=os.environ.get("ESCALATION_MODEL", "claude-sonnet-5"),
        log_level=os.environ.get("LOG_LEVEL", "info").upper(),
    )


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
