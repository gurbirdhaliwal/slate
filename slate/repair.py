"""Repair tasks — a suspect claim, scoped enough for someone to act on.

This module reads verdicts and turns them into a worklist. It computes no
trust of its own, calls no model, and writes nothing; `freshness` decides what
is suspect and `cli` decides what to print, exactly as `mcp` and `claudehook`
already do. A second opinion about whether a doc is fresh would be a second
thing that can disagree.

**Generated facts are not repair tasks.** `slate sync` rewrites the auto-block
deterministically, in milliseconds, for zero tokens — measured over this
repo's whole history, generated drift is the *only* staleness that ever
occurred, and handing it to a model would be strictly worse than the machinery
that already fixes it. Only hand-written claims land here, because they are
the only ones a rewrite is the answer to.

**A task is not proof the prose is wrong.** `scope` carries which resolution
reached the verdict:

- ``symbol`` — the referenced symbol provably moved. Strong evidence.
- ``path``   — a referenced file changed *somewhere*. The claim may be
  untouched, and on this repo's corpus most path-scoped flags were prose that
  was still accurate.

Anything consuming these tasks has to let "this claim is still correct" be an
answer, or its default action on the common case is rewriting correct prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil
from .freshness import CLAIM_FRESH, DocReport, symbol_files


@dataclass
class RepairTask:
    doc_path: str
    line: int                  # 1-based line in the file
    end_line: int
    section: str               # enclosing heading, for orientation
    text: str
    status: str                # stale | unknowable
    scope: str                 # symbol | path — how strong the evidence is
    risk: list[str] = field(default_factory=list)   # refs that put it at risk
    anchor: str = ""           # the doc's sync anchor: the diff starts here
    commits: dict[str, str] = field(default_factory=dict)  # ref -> newest commit
    # Refs whose change is not committed yet. Distinguished from "no evidence"
    # because the answer to "show me the diff" is `git diff`, not `git show`.
    uncommitted: list[str] = field(default_factory=list)

    @property
    def evidence_is_strong(self) -> bool:
        return self.scope == "symbol"

    def as_dict(self) -> dict:
        return {
            "doc_path": self.doc_path,
            "line": self.line,
            "end_line": self.end_line,
            "section": self.section,
            "text": self.text,
            "status": self.status,
            "scope": self.scope,
            "risk": self.risk,
            "anchor": self.anchor,
            "commits": self.commits,
            "uncommitted": self.uncommitted,
        }


def repair_tasks(
    root: Path, reports: list[DocReport], *, with_commits: bool = True
) -> list[RepairTask]:
    """Every hand-written claim a doc no longer vouches for.

    Ordered strongest evidence first, then by document position, so the head
    of the list is where a reader — or an agent — should start.
    """
    tasks: list[RepairTask] = []
    for report in reports:
        anchor = report.doc.synced_commit or ""
        for claim in report.claims:
            if claim.kind != "human" or claim.status == CLAIM_FRESH:
                continue
            commits, uncommitted = (
                _commits_for(root, claim.risk, report.changed_watched, anchor)
                if with_commits and anchor else ({}, [])
            )
            tasks.append(RepairTask(
                doc_path=claim.doc_path or report.rel_path,
                line=claim.line, end_line=claim.end_line,
                section=claim.section, text=claim.text,
                status=claim.status, scope=claim.scope,
                risk=list(claim.risk), anchor=anchor, commits=commits,
                uncommitted=uncommitted,
            ))
    tasks.sort(key=lambda t: (not t.evidence_is_strong, t.doc_path, t.line))
    return tasks


def _commits_for(
    root: Path, risk: list[str], hits: list[str], anchor: str
) -> tuple[dict[str, str], list[str]]:
    """Newest commit since `anchor` behind each risk ref, and the rest.

    A ref naming a path is asked about directly; a ``module.symbol`` ref is
    resolved to the changed files that could host it, the same way the
    freshness engine resolves it. This is a lookup, not a second opinion — the
    verdict was already reached before any of this runs.

    A ref with no commit is not evidence-free: the file *is* among the hits,
    so the change exists and simply is not committed yet. Saying which is
    which is the difference between `git show` and `git diff`.
    """
    commits: dict[str, str] = {}
    uncommitted: list[str] = []
    for ref in risk:
        direct = [h for h in hits if h == ref or h.startswith(ref + "/")]
        candidates = direct or symbol_files(ref, hits)
        for path in candidates:
            sha = gitutil.last_change_commit(root, path, anchor)
            if sha:
                commits[ref] = sha
                break
        else:
            if candidates:
                uncommitted.append(ref)
    return commits, uncommitted
