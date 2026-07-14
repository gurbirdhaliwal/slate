"""Deterministic walk edge cases — a wrong origin step destroys the core promise (§10)."""

from decimal import Decimal
from uuid import uuid4

from slate_worker.localization import StepNode, _wasted_cost, localize


def node(id, seq, parents=(), passed=True, failure_class=None, cost="0.01"):
    return StepNode(
        id=id, seq=seq, parent_ids=tuple(parents), step_type="llm", name=f"step{seq}",
        cost_usd=Decimal(cost), passed=passed,
        failure_class=failure_class, reasoning="r",
    )


def test_single_origin_with_propagation():
    a, b, c = uuid4(), uuid4(), uuid4()
    steps = [
        node(a, 1, passed=True),
        node(b, 2, [a], passed=False, failure_class="retrieval_miss"),
        node(c, 3, [b], passed=False, failure_class="hallucinated_content"),
    ]
    d = localize(steps)
    assert d is not None
    assert d.method == "deterministic"
    assert d.origin_step_id == b
    assert d.propagated_step_ids == (c,)
    assert d.failure_class == "retrieval_miss"


def test_all_steps_pass_is_ambiguous():
    a, b = uuid4(), uuid4()
    assert localize([node(a, 1), node(b, 2, [a])]) is None


def test_two_independent_origins_is_ambiguous():
    a, b, c = uuid4(), uuid4(), uuid4()
    steps = [
        node(a, 1, passed=False, failure_class="planning_error"),
        node(b, 2, passed=False, failure_class="retrieval_miss"),  # no shared ancestry
        node(c, 3, [a, b], passed=False),
    ]
    assert localize(steps) is None


def test_propagation_through_passing_intermediate():
    # origin -> (passing step) -> faulted descendant: descendant is still propagated
    a, b, c = uuid4(), uuid4(), uuid4()
    steps = [
        node(a, 1, passed=False, failure_class="retrieval_miss"),
        node(b, 2, [a], passed=True),
        node(c, 3, [b], passed=False, failure_class="hallucinated_content"),
    ]
    d = localize(steps)
    assert d is not None
    assert d.origin_step_id == a
    assert d.propagated_step_ids == (c,)


def test_wasted_cost_covers_origin_and_downstream_only():
    a, b, c, d_ = uuid4(), uuid4(), uuid4(), uuid4()
    steps = [
        node(a, 1, cost="0.10"),                # upstream — not wasted
        node(b, 2, [a], cost="0.20"),           # origin
        node(c, 3, [b], cost="0.30"),           # downstream
        node(d_, 4, [a], cost="0.40"),          # sibling branch — not downstream of origin
    ]
    assert _wasted_cost(steps, b) == Decimal("0.50")
