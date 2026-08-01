#!/usr/bin/env python3
"""Builds a repairbench trial repo, and checks the corpus is what it claims.

    python benchmarks/repairbench/corpus.py --verify        # all 24 items
    python benchmarks/repairbench/corpus.py --verify --id t01-redirect-code
    python benchmarks/repairbench/corpus.py --build t01-redirect-code --into /tmp/x

Revision 1 mined its corpus out of history and had to guess, afterwards, which
diff was responsible for which sentence. It guessed wrong on half of them. This
module inverts that: the passage is *authored* against a known parent commit and
the falsifying diff is the commit applied on top, so the evidence is exact by
construction rather than by resolution.

One trial repo, both arms, identical mechanics:

    1. check out ``<commit>^``
    2. ``slate init`` — the layer is generated and anchored here
    3. append the authored passage to ``.slate/read-next.md``, commit it
    4. apply the ``src/`` half of ``<commit>`` and commit that

Step 3 before step 4 matters. It puts the prose *older* than the code change,
which is the only ordering ``freshness._prose_supersedes`` will flag — prose
written after its code is narrowed to fresh, correctly, and would silently drop
the item from the experiment.

Only the ``src/`` half of the commit is applied, in both arms. The full commits
carry ``CHANGES.rst`` entries, and only the falsified arm's commits do, so
applying them whole would hand the agent an answer key that exists in one arm
and not the other. The diff shown to the agent is the diff that was applied.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = HERE / "corpus_rev2.json"
MIRROR = ROOT / "benchmarks" / "agentbench" / ".work" / "flask.git"
SLATE_BIN = ROOT / ".venv" / "bin" / "slate"

# The authored passage lives alone under this heading, at the end of the doc.
# Scoring reads everything below it, so a rewrite that re-wraps or re-flows the
# paragraph is still located exactly — the failure that skipped 10 of 18
# controls in revision 1.
SECTION = "## Behaviour notes"

GIT_ID = ["-c", "user.email=bench@slate.local", "-c", "user.name=slate-bench",
          "-c", "commit.gpgsign=false"]


@dataclass
class Item:
    id: str
    arm: str               # falsified | accurate
    commit: str
    subject: str
    claim: str
    old_fact: list[str]
    new_fact: list[str]
    truth: str

    @property
    def falsified(self) -> bool:
        return self.arm == "falsified"


def load_corpus() -> list[Item]:
    return [Item(**raw) for raw in json.loads(CORPUS.read_text())]


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *GIT_ID, *args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stderr}")
    return proc.stdout


def slate(cwd: Path, *args: str) -> str:
    proc = subprocess.run([str(SLATE_BIN), *args], cwd=cwd,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"slate {' '.join(args)} failed:\n{proc.stderr}")
    return proc.stdout


def wrap(text: str, width: int = 78) -> str:
    """Fill to a doc-like width. The passage must read as prose someone wrote,
    not as one long line — a rewrite is scored against the whole section, so
    the wrapping is free to change."""
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    return "\n".join(lines)


def build_trial(item: Item, dest: Path) -> Path:
    """Construct the repo one trial runs against. Returns `dest`."""
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(["git", "clone", "--quiet", "--shared", str(MIRROR), str(dest)],
                   check=True, capture_output=True)
    git(dest, "checkout", "--quiet", "-B", "trial", f"{item.commit}^")

    slate(dest, "init")
    doc = dest / ".slate" / "read-next.md"
    doc.write_text(f"{doc.read_text().rstrip()}\n\n{SECTION}\n\n{wrap(item.claim)}\n")
    git(dest, "add", "-A")
    git(dest, "commit", "--quiet", "-m", "add context layer")

    diff = git(dest, "diff", f"{item.commit}^", item.commit, "--", "src")
    proc = subprocess.run(["git", "-C", str(dest), "apply", "--index"],
                          input=diff, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"[{item.id}] applying {item.commit} failed:\n{proc.stderr}")
    git(dest, "commit", "--quiet", "-m", item.subject)
    return dest


def evidence_diff(item: Item, repo: Path) -> str:
    """The diff the agent is shown: the code change, and nothing else."""
    return git(repo, "show", "--format=", "HEAD")


def passage(repo: Path) -> str:
    """The authored section as it currently stands on disk."""
    body = (repo / ".slate" / "read-next.md").read_text()
    _, _, after = body.partition(SECTION)
    return after.strip()


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def matches(pattern: str, text: str) -> bool:
    """Fact patterns are matched against re-flowed text.

    The passage is wrapped in the doc and a rewrite is free to re-wrap it, so a
    multi-word fact would otherwise be defeated by a line break — which is the
    same normalisation bug that skipped 10 of revision 1's 18 controls.
    """
    return re.search(pattern, normalise(text)) is not None


def asserts(patterns: list[str], text: str) -> bool:
    """Any-of. The lists are alternative phrasings of one fact, not a
    conjunction: a repair states the new fact *somehow*, and drops every way of
    stating the old one."""
    return any(matches(p, text) for p in patterns)


def task_for(repo: Path) -> dict | None:
    """The repair task Slate raises for the authored passage, if it raises one.

    An item that Slate does not flag is not a trial: the agent would never be
    handed it. Verification fails loudly rather than quietly shrinking the arm.
    """
    tasks = json.loads(slate(repo, "repair", "--json"))
    here = [t for t in tasks if t["doc_path"] == ".slate/read-next.md"
            and t["section"] == SECTION.lstrip("# ")]
    return here[0] if len(here) == 1 else None


# --------------------------------------------------------------------------
# verification


def verify(item: Item, keep: Path | None = None) -> list[str]:
    """Everything that has to be true before this item can be a trial."""
    problems = []
    dest = keep or Path("/tmp") / f"repairbench-verify-{item.id}"
    build_trial(item, dest)

    task = task_for(dest)
    if task is None:
        problems.append("slate raises no single task for the passage")
        return problems

    if normalise(task["text"]) != normalise(item.claim):
        problems.append("task text does not match the authored claim")

    head = git(dest, "rev-parse", "HEAD").strip()
    named = set(task["commits"].values())
    if named and named != {head}:
        problems.append(f"evidence names {named}, not the applied commit {head[:8]}")
    if not named:
        problems.append("task carries no commit evidence")

    text = passage(dest)
    if item.old_fact and not asserts(item.old_fact, text):
        problems.append("no old_fact pattern matches the claim as written")
    for pattern in item.new_fact:
        if matches(pattern, text):
            problems.append(f"new_fact /{pattern}/ already matches before any repair")

    if not keep:
        shutil.rmtree(dest, ignore_errors=True)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--build")
    parser.add_argument("--into")
    parser.add_argument("--id")
    args = parser.parse_args()

    items = load_corpus()
    if args.build:
        item = next(i for i in items if i.id == args.build)
        dest = Path(args.into or f"/tmp/repairbench-{item.id}")
        print(build_trial(item, dest))
        return 0

    if args.id:
        items = [i for i in items if i.id == args.id]

    failed = 0
    for item in items:
        problems = verify(item)
        mark = "ok  " if not problems else "FAIL"
        print(f"{mark} {item.id:28} {item.arm:10} {item.commit}")
        for problem in problems:
            print(f"       - {problem}")
        failed += bool(problems)
    print(f"\n{len(items) - failed}/{len(items)} items usable")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
