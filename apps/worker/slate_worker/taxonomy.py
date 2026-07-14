"""Failure taxonomy v1 (§10) — hand-maintain this list.

Every verdict and diagnosis maps to exactly one class. This taxonomy powers
Phase 2 clustering and cost-per-failure analytics — resist letting the judge
invent free-text classes.
"""

FAILURE_CLASSES: tuple[str, ...] = (
    "retrieval_miss",
    "hallucinated_content",
    "malformed_tool_call",
    "tool_execution_error",
    "ignored_instruction",
    "bad_handoff",
    "planning_error",
    "context_overflow",
)
