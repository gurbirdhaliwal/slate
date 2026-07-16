"""`slate diff` — what changed vs. what each context doc claims.

For a stale doc, `status` says *that* it's suspect; this module says *why*
and *what sync would do about it*:

  - the watched paths that changed, with change kinds (A/M/D/R)
  - repo paths the doc references that no longer exist (broken claims)
  - for generated docs: a unified diff of the auto-block against what a
    fresh scan would generate — the reviewable preview of `slate sync`
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path

from . import context, generator, gitutil
from .context import ContextDoc
from .freshness import DocReport, evaluate_doc
from .scanner import RepoScan
from .verify import extract_path_refs


@dataclass
class DocDiff:
    report: DocReport
    changes: dict[str, str] = field(default_factory=dict)  # watched path -> A/M/D/R
    missing_refs: list[str] = field(default_factory=list)
    sync_preview: list[str] = field(default_factory=list)  # unified diff lines

    @property
    def rel_path(self) -> str:
        return self.report.rel_path

    @property
    def has_findings(self) -> bool:
        return bool(self.changes or self.missing_refs or self.sync_preview)


def doc_diff(root: Path, doc: ContextDoc, scan: RepoScan) -> DocDiff:
    report = evaluate_doc(root, doc)

    kinds = gitutil.changed_with_status(root, doc.synced_commit)
    changes = {p: kinds.get(p, "M") for p in report.changed_watched}

    missing = [r for r in extract_path_refs(doc.body) if not (root / r).exists()]

    preview: list[str] = []
    if doc.spec.generated:
        current = context.get_auto_block(doc.body) or ""
        regenerated = generator.auto_content(doc.spec, scan)
        if current != regenerated:
            preview = list(
                difflib.unified_diff(
                    current.splitlines(),
                    regenerated.splitlines(),
                    fromfile=f"{doc.spec.rel_path} (current)",
                    tofile=f"{doc.spec.rel_path} (after slate sync)",
                    lineterm="",
                )
            )
    return DocDiff(report, changes, missing, preview)
