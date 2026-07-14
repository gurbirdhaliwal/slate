"""Built-in step contracts (§10). Phase 1 ships built-ins only; custom YAML
contracts (stored in the repurposed rubrics table) arrive in Phase 2.

Contracts are matched by step_type; `tool:*` style wildcards reduce to the
prefix before ':' in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

import yaml


@dataclass(frozen=True)
class StepContract:
    match: str
    prompt: str
    fault_threshold: float


_cache: dict[str, StepContract] | None = None


def load_builtin_contracts() -> dict[str, StepContract]:
    """Parse the packaged YAML once; cached in worker memory (§10 pipeline)."""
    global _cache
    if _cache is None:
        raw = resources.files("slate_worker").joinpath("contracts/builtin.yaml").read_text()
        doc = yaml.safe_load(raw)
        threshold = float(doc.get("fault_threshold", 0.5))
        _cache = {
            c["match"]: StepContract(c["match"], c["prompt"].strip(), threshold)
            for c in doc["contracts"]
        }
    return _cache


def contract_for(step_type: str) -> StepContract:
    contracts = load_builtin_contracts()
    if step_type in contracts:
        return contracts[step_type]
    base = step_type.split(":", 1)[0]
    if f"{base}:*" in contracts:
        return contracts[f"{base}:*"]
    # Every typed step must be judgeable; fall back to the generic llm contract
    return contracts["llm"]
