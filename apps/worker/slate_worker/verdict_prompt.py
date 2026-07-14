"""Verdict prompt build + parse — HAND-CODED (§10/§13).

Small wording changes produce large changes in score distribution; treat the
system prompt as versioned IP. Parsing is strict: an unparseable verdict is an
error (retried by the queue), never a silent pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .contracts import StepContract
from .taxonomy import FAILURE_CLASSES


class VerdictParseError(Exception):
    pass


@dataclass(frozen=True)
class StepPayload:
    name: str
    step_type: str
    inputs: str
    output: str


@dataclass(frozen=True)
class Verdict:
    score: float
    failure_class: str | None
    reasoning: str


def build_verdict_prompt(contract: StepContract, step: StepPayload) -> tuple[str, str]:
    """Returns (system, user). The system prompt is shared by all steps of the
    same type in a run — mark it for Anthropic prompt caching (§8 COGS control #1)."""
    system = f"""You are a step-level agent debugger. Judge this single step in
isolation: evaluate the output ONLY against the inputs the step received.
Do not penalize the step for upstream mistakes visible in its inputs.

{contract.prompt}

Respond with ONLY a JSON object in this exact format:
{{"score": <float 0.0-1.0>, "failure_class": <string from the allowed list, or null if passing>, "reasoning": "<one sentence>"}}

Allowed failure classes: {", ".join(FAILURE_CLASSES)}.
Do not include any other text. Score must be between 0.0 and 1.0 inclusive."""

    user = f"""Step: {step.name} ({step.step_type})

Inputs this step received:
{step.inputs}

Output this step produced:
{step.output}"""
    return system, user


def parse_verdict_response(raw: str) -> Verdict:
    # Strip any markdown fences the model might add
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise VerdictParseError(f"Verdict is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise VerdictParseError(f"Verdict is not a JSON object: {type(parsed).__name__}")

    score = parsed.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0.0 <= score <= 1.0:
        raise VerdictParseError(f"Invalid score: {score}")

    failure_class = parsed.get("failure_class")
    if failure_class is not None and failure_class not in FAILURE_CLASSES:
        raise VerdictParseError(f"Unknown failure class: {failure_class}")

    return Verdict(
        score=round(float(score), 3),
        failure_class=failure_class,
        reasoning=str(parsed.get("reasoning", "")),
    )
