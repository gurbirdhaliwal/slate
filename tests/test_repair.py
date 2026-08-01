"""Repair tasks — the worklist behind the pivot, and what it must not claim.

These pin two things the rest of the arc depends on: that a task points at a
place someone can open, and that a task is never mistaken for proof the prose
is wrong. Most flagged claims on real history were still accurate.

The second half pins the verification gate. Those are written as adversarial
cases on purpose: the interesting failures of a repair loop are the ones where
the doc ends up *looking* healthier than it is.
"""

from __future__ import annotations

from pathlib import Path

from slate import context, freshness, generator, repair, scanner

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def claim(repo: Path, text: str) -> None:
    read_next = repo / ".slate" / "read-next.md"
    read_next.write_text(read_next.read_text() + f"\n{text}\n")


def tasks(repo: Path) -> list[repair.RepairTask]:
    return repair.repair_tasks(repo, freshness.evaluate_all(repo))


def test_a_fresh_layer_has_nothing_to_repair(repo: Path) -> None:
    init_layer(repo)
    assert tasks(repo) == []


def test_generated_drift_is_not_a_repair_task(repo: Path) -> None:
    # `slate sync` rewrites the auto-block deterministically for zero tokens.
    # Routing that to a model would be strictly worse than the machinery that
    # already fixes it — measured over this repo's history, generated drift
    # was the *only* staleness that ever occurred.
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    commit_all(repo, "new file changes the module map")
    assert any(r.status != "fresh" for r in freshness.evaluate_all(repo))
    assert all(t.doc_path != ".slate/modules.md" for t in tasks(repo))


def test_task_points_at_a_line_someone_can_open(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    lines = (repo / task.doc_path).read_text().splitlines()
    assert "engine.run" in lines[task.line - 1]  # 1-based, and into the *file*
    assert task.section
    assert task.anchor


def test_symbol_evidence_outranks_file_evidence(repo: Path) -> None:
    # A path ref only says a file changed somewhere; a symbol ref says the
    # named thing moved. The strong evidence has to come first, because that
    # is where a reader should start.
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    claim(repo, "Helpers live in `demo/helper.py`.")
    (repo / "demo" / "helper.py").write_text("def a():\n    return 1\n")
    commit_all(repo, "describe both")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    (repo / "demo" / "helper.py").write_text("def a():\n    return 2\n")
    commit_all(repo, "change both")

    got = tasks(repo)
    assert [t.scope for t in got] == ["symbol", "path"]
    assert got[0].evidence_is_strong and not got[1].evidence_is_strong


def test_a_task_carries_the_commit_behind_it(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    sha = commit_all(repo, "change run")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    assert task.commits["engine.run"].startswith(sha)
    assert task.uncommitted == []


def test_an_uncommitted_change_says_so_rather_than_going_silent(repo: Path) -> None:
    # "No commit" is not "no evidence" — the file is among the hits either
    # way. The distinction is whether the diff is `git show` or `git diff`.
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")

    (task,) = [t for t in tasks(repo) if "engine.run" in t.risk]
    assert task.commits == {}
    assert task.uncommitted == ["engine.run"]


def test_json_shape_is_complete(repo: Path) -> None:
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run")

    payload = tasks(repo)[0].as_dict()
    assert set(payload) == {
        "doc_path", "line", "end_line", "section", "text", "status",
        "scope", "risk", "anchor", "commits", "uncommitted",
    }


def test_claim_verdicts_stay_backward_compatible(repo: Path) -> None:
    # status/verify/diff and the MCP surface all read this shape; the new
    # fields are additive, exactly as the Part B rollout was.
    init_layer(repo)
    (repo / "demo" / "widget.py").write_text("x = 1\n")
    report = next(r for r in freshness.evaluate_all(repo) if r.claims)
    payload = report.claims[0].as_dict()
    assert {"text", "section", "kind", "status", "refs", "risk"} <= set(payload)


# --------------------------------------------------------------------------
# the verification gate


BODY = """# Notes

## Engine

`engine.run` returns 42.

## Helpers

`helper.a` returns 1.
"""


def verify(after: str, target: str = "`engine.run` returns 42.") -> repair.Verdict:
    return repair.verify_repair(BODY, after, target)


def test_an_honest_repair_is_accepted() -> None:
    after = BODY.replace("`engine.run` returns 42.", "`engine.run` returns 43.")
    verdict = verify(after)
    assert verdict.outcome == repair.REPAIRED
    assert verdict.ok and verdict.reasons == []


def test_stripping_the_refs_is_rejected() -> None:
    # The cheapest way to make a doc green, and the most damaging: with no
    # backticks the sentence stops being a claim, so nothing can ever catch it
    # being wrong again.
    after = BODY.replace("`engine.run` returns 42.", "The engine returns 43.")
    verdict = verify(after)
    assert verdict.outcome == repair.REJECTED
    assert any("never be checked again" in reason for reason in verdict.reasons)


def test_fluent_prose_with_nothing_checkable_is_rejected() -> None:
    after = BODY.replace(
        "`engine.run` returns 42.",
        "The engine has been carefully reworked and now behaves as expected.")
    assert verify(after).outcome == repair.REJECTED


def test_deleting_the_claim_outright_is_rejected() -> None:
    after = BODY.replace("`engine.run` returns 42.\n", "")
    verdict = verify(after)
    assert verdict.outcome == repair.REJECTED
    assert verdict.claims_after < verdict.claims_before


def test_breaking_another_claim_while_fixing_this_one_is_rejected() -> None:
    after = (BODY
             .replace("`engine.run` returns 42.", "`engine.run` returns 43.")
             .replace("`helper.a` returns 1.", "`helper.a` returns 99."))
    verdict = verify(after)
    assert verdict.outcome == repair.REJECTED
    assert any("other claim" in reason for reason in verdict.reasons)


def test_editing_a_different_claim_instead_is_rejected() -> None:
    after = BODY.replace("`helper.a` returns 1.", "`helper.a` returns 99.")
    verdict = verify(after)
    assert verdict.outcome == repair.REJECTED
    assert any("left alone" in reason for reason in verdict.reasons)


def test_no_change_needed_is_an_accepted_outcome() -> None:
    # It was the correct action in 12 of repairbench rev 3's 24 trials. A gate
    # that only recognises a successful rewrite scores the right answer wrong.
    verdict = verify(BODY)
    assert verdict.outcome == repair.UNCHANGED
    assert verdict.ok


def test_rewrapping_the_same_claim_is_not_an_edit() -> None:
    after = BODY.replace("`engine.run` returns 42.", "`engine.run`\nreturns 42.")
    assert verify(after).outcome == repair.UNCHANGED


def test_moving_the_repair_to_another_section_is_rejected() -> None:
    after = BODY.replace("`engine.run` returns 42.\n", "").replace(
        "`helper.a` returns 1.", "`helper.a` returns 1.\n\n`engine.run` returns 43.")
    verdict = verify(after)
    assert verdict.outcome == repair.REJECTED
    assert any("not 'Engine'" in reason for reason in verdict.reasons)


def test_a_target_that_is_not_in_the_document_verifies_nothing() -> None:
    verdict = repair.verify_repair(BODY, BODY, "`engine.run` returns 7.")
    assert verdict.outcome == repair.REJECTED
    assert any("nothing to verify" in reason for reason in verdict.reasons)


def test_verdict_json_shape_is_complete() -> None:
    payload = verify(BODY).as_dict()
    assert set(payload) == {
        "outcome", "ok", "reasons", "claims_before", "claims_after"}


def test_repair_cannot_manufacture_fresh(repo: Path) -> None:
    """The exit criterion for Phase 2, in the spirit of
    `test_merged_layer_is_not_falsely_fresh`.

    The trap is demonstrated, not assumed: the doc really does go green when
    the refs are deleted, because `_claims_still_check_out` reads references
    out of the human text and a sentence without backticks has none. The gate
    is what stands between that edit and the layer.
    """
    init_layer(repo)
    claim(repo, "`engine.run` returns 42.")
    commit_all(repo, "describe run")
    (repo / "demo" / "engine.py").write_text("def run():\n    return 43\n")
    commit_all(repo, "change run")

    doc_path = repo / ".slate" / "read-next.md"
    stale = next(r for r in freshness.evaluate_all(repo)
                 if r.rel_path == ".slate/read-next.md")
    assert stale.status != context.FRESH

    before = context.load(repo, stale.doc.spec).body
    doc_path.write_text(doc_path.read_text().replace(
        "`engine.run` returns 42.", "The engine returns something."))

    # The trap is real: freshness alone now calls this doc fresh, on prose that
    # says strictly less than the sentence it replaced.
    healed = next(r for r in freshness.evaluate_all(repo)
                  if r.rel_path == ".slate/read-next.md")
    assert healed.status == context.FRESH

    # The gate refuses it, and says why.
    after = context.load(repo, stale.doc.spec).body
    verdict = repair.verify_repair(before, after, "`engine.run` returns 42.")
    assert verdict.outcome == repair.REJECTED
    assert not verdict.ok
    assert any("never be checked again" in reason for reason in verdict.reasons)


def test_replace_claim_finds_a_wrapped_paragraph() -> None:
    # The claim text is normalised by the segmenter, so it never appears in the
    # file verbatim once the paragraph wraps. A plain string replace misses it
    # silently — the same normalisation bug that dropped 10 of repairbench
    # rev 1's 18 controls.
    body = "# Notes\n\n## Engine\n\n`engine.run`\nreturns 42.\n"
    out = repair.replace_claim(body, "`engine.run` returns 42.", "`engine.run` returns 43.")
    assert "returns 43." in out and "returns 42." not in out
    assert repair.verify_repair(body, out, "`engine.run` returns 42.").outcome == repair.REPAIRED


def test_replace_claim_leaves_the_body_alone_when_the_target_is_absent() -> None:
    # Failing into "no edit" lets verify_repair reject it; guessing which claim
    # was meant would be the unsafe direction.
    body = "# Notes\n\n## Engine\n\n`engine.run` returns 42.\n"
    assert repair.replace_claim(body, "`engine.run` returns 7.", "anything") == body
