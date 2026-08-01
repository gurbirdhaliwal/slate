#!/usr/bin/env python3
"""Runs the pre-registered repair experiment in `spec.py` and records raw results.

    python benchmarks/repairbench/run.py --pilot            # 2 per arm
    python benchmarks/repairbench/run.py                    # all 24
    python benchmarks/repairbench/run.py --id t01-redirect-code
    python benchmarks/repairbench/run.py --report           # score what's on disk

Each trial builds a throwaway Flask clone (`corpus.py`), hands a real headless
`claude -p` session one flagged passage plus the diff behind it, and records
what came back. Nothing is estimated: whether the passage changed is read off
the file, and whether the rewrite carries the new fact is matched against
patterns fixed in the corpus before any agent ran.

Revision 1 had no committed harness — it was driven ad hoc, so its numbers could
not be reproduced or re-scored. This is that gap closed: `--report` rescores the
records on disk without spending a session.

Raw output goes to `runs/` — one JSON record and one full JSONL transcript per
trial, so every number in the report traces back to the session that produced it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus  # noqa: E402
import spec  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = HERE / "runs"
WORK = HERE / ".work"

# A trial that never completes is reported void, not counted. Three is enough
# for a dropped connection without letting a systematically failing item spend
# the whole quota.
ATTEMPTS = 3

sys.path.insert(0, str(ROOT))
from slate import refs as slate_refs  # noqa: E402


PROMPT = """\
This repository's context layer is at `.slate/`. The last section of
`.slate/read-next.md` is titled "Behaviour notes". Slate has flagged the passage
in that section, because code the passage references changed since the doc was
last verified.

The passage:

---
{text}
---

References at risk: {risk}
Changed in: {commit} — {subject}

The change:

```diff
{diff}
```

A flag means the referenced code changed. It does not tell you whether the
passage is still accurate; that is what you are being asked to decide. Read
whatever source files you need.

Then do exactly one of these:

A. If the passage no longer describes the code correctly, edit
   `.slate/read-next.md` and rewrite the passage in place. Keep the section
   heading, keep the surrounding style, and keep code references in backticks.

B. If the passage still describes the code correctly, change nothing.

Finish your reply with exactly one word on its own line: REWRITTEN if you chose
A, or UNCHANGED if you chose B.
"""


def render_prompt(item: corpus.Item, task: dict, diff: str) -> str:
    return PROMPT.format(
        text=task["text"],
        risk=", ".join(f"`{r}`" for r in task["risk"]),
        commit=item.commit,
        subject=item.subject,
        diff=diff.strip(),
    )


# --------------------------------------------------------------------------
# the agent run


class Void(RuntimeError):
    """The session failed, so the trial produced no evidence.

    A dropped connection leaves the passage untouched, which is byte-identical
    to a deliberate decline. Scoring it as one would quietly move the number
    the whole experiment turns on, in the direction that favours the null —
    the same class of defect that made revision 1 unreadable. Voided trials are
    retried, and if they never complete they are reported as void rather than
    counted.
    """


def run_agent(root: Path, prompt: str, transcript: Path) -> tuple[str, float]:
    env = dict(os.environ)
    env.pop("ANTHROPIC_MODEL", None)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "bypassPermissions",
        "--model", spec.MODEL,
    ]
    started = time.time()
    with transcript.open("w") as sink:
        proc = subprocess.run(cmd, cwd=root, env=env, stdout=sink,
                              stderr=subprocess.PIPE, text=True,
                              stdin=subprocess.DEVNULL)
    said, errored = final_text(transcript)
    if errored:
        raise Void(said[:200] or f"claude exited {proc.returncode}")
    return said, round(time.time() - started, 1)


def final_text(transcript: Path) -> tuple[str, bool]:
    """The session's result string and whether it failed, from the CLI's own
    envelope. A missing result event is itself a failure."""
    for line in reversed(transcript.read_text().splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "result":
            return str(event.get("result", "")), bool(event.get("is_error"))
    return "", True


# --------------------------------------------------------------------------
# scoring


def resolution(root: Path, text: str) -> tuple[int, int]:
    """Descriptive only — see spec.REFS_RESOLVE_IS_DESCRIPTIVE.

    A path ref resolves if the file exists; a symbol ref resolves if its
    qualifier names a module in the tree. Recorded so revision 1's primary can
    be compared against, never to decide anything.
    """
    resolved = total = 0
    for ref in slate_refs.extract_path_refs(text):
        total += 1
        resolved += (root / ref).exists()
    for ref in slate_refs.extract_symbol_refs(text):
        total += 1
        module = ref.split(".")[:-1]
        if not module:
            continue
        candidates = [
            root / "src" / Path(*module).with_suffix(".py"),
            root / Path(*module).with_suffix(".py"),
            root / "src" / Path(*module) / "__init__.py",
        ]
        resolved += any(c.exists() for c in candidates)
    return resolved, total


def is_fresh(root: Path) -> bool:
    """Recorded, and circular — never a criterion. See spec."""
    try:
        reports = json.loads(corpus.slate(root, "status", "--json"))
    except Exception:
        return False
    docs = reports["docs"] if isinstance(reports, dict) else reports
    for doc in docs:
        if doc.get("path", "").endswith("read-next.md"):
            return doc.get("status") == "fresh"
    return False


def score(item: corpus.Item, root: Path, before: str, said: str) -> dict:
    after = corpus.passage(root)
    edited = corpus.normalise(before) != corpus.normalise(after)
    resolved, total = resolution(root, after)
    result = spec.TrialResult(
        item=item.id,
        arm=item.arm,
        commit=item.commit,
        edited=edited,
        declined=said.strip().splitlines()[-1].strip().upper() == "UNCHANGED"
        if said.strip() else False,
        kept_refs=bool(slate_refs.extract_symbol_refs(after)
                       or slate_refs.extract_path_refs(after)),
        states_new_fact=edited and corpus.asserts(item.new_fact, after),
        drops_old_fact=edited and not corpus.asserts(item.old_fact, after),
        refs_resolved=resolved,
        refs_total=total,
        fresh_after=is_fresh(root),
        before=before,
        after=after,
    )
    return asdict(result)


# --------------------------------------------------------------------------
# driving


def already_done(item: corpus.Item) -> bool:
    """A record from an older revision does not count: it answers a different
    question. Same guard agentbench's TASK_REVISION gives."""
    sidecar = RUNS / f"{item.id}.json"
    if not sidecar.exists():
        return False
    try:
        return json.loads(sidecar.read_text()).get("revision") == spec.REVISION
    except (json.JSONDecodeError, OSError):
        return False


def trial(item: corpus.Item) -> dict:
    root = WORK / item.id
    corpus.build_trial(item, root)
    task = corpus.task_for(root)
    if task is None:
        raise RuntimeError(f"[{item.id}] slate raises no task — run corpus.py --verify")

    prompt = render_prompt(item, task, corpus.evidence_diff(item, root))
    before = corpus.passage(root)

    RUNS.mkdir(exist_ok=True)
    said, wall = run_agent(root, prompt, RUNS / f"{item.id}.jsonl")

    record = score(item, root, before, said)
    record |= {"revision": spec.REVISION, "model": spec.MODEL,
               "wall_s": wall, "said": said[-400:], "scope": task["scope"]}
    (RUNS / f"{item.id}.json").write_text(json.dumps(record, indent=2) + "\n")
    shutil.rmtree(root, ignore_errors=True)
    return record


def report() -> int:
    records = []
    for item in corpus.load_corpus():
        sidecar = RUNS / f"{item.id}.json"
        if sidecar.exists():
            record = json.loads(sidecar.read_text())
            if record.get("revision") == spec.REVISION:
                records.append(record)

    if not records:
        print("no records at this revision")
        return 1

    falsified = [r for r in records if r["arm"] == "falsified"]
    accurate = [r for r in records if r["arm"] == "accurate"]
    f_edited = sum(r["edited"] for r in falsified)
    a_edited = sum(r["edited"] for r in accurate)
    repaired = sum(r["edited"] and r["states_new_fact"] and r["drops_old_fact"]
                   for r in falsified)
    quality = repaired / f_edited if f_edited else 0.0
    kept = [r for r in records if r["edited"]]
    kept_rate = sum(r["kept_refs"] for r in kept) / len(kept) if kept else 1.0

    print(f"revision {spec.REVISION}, {len(records)} trials, {spec.MODEL}\n")
    for record in records:
        action = "rewrote" if record["edited"] else "declined"
        mark = ""
        if record["arm"] == "falsified":
            mark = "  ok" if record["edited"] and record["states_new_fact"] \
                and record["drops_old_fact"] else "  --"
        print(f"  {record['item']:28} {record['arm']:10} {action}{mark}")

    print(f"\n  falsified edited   {f_edited}/{len(falsified)}")
    print(f"  accurate  edited   {a_edited}/{len(accurate)}")
    print(f"  repair quality     {repaired}/{f_edited or 0} = {quality:.0%}")
    print(f"  kept refs          {kept_rate:.0%} (of {len(kept)} rewrites)")

    passed, failures = spec.verdict(
        f_edited, len(falsified), a_edited, len(accurate), quality, kept_rate)
    print(f"\n  spec.verdict() -> {'PASS' if passed else 'FAIL'}")
    for failure in failures:
        print(f"    - {failure}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", action="store_true", help="2 items per arm")
    parser.add_argument("--id", action="append")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.report:
        return report()

    items = corpus.load_corpus()
    if args.id:
        items = [i for i in items if i.id in args.id]
    elif args.pilot:
        falsified = [i for i in items if i.falsified][:2]
        accurate = [i for i in items if not i.falsified][:2]
        items = falsified + accurate

    WORK.mkdir(exist_ok=True)
    void = []
    for item in items:
        if not args.force and already_done(item):
            print(f"  {item.id:28} already recorded at revision {spec.REVISION}")
            continue
        for attempt in range(ATTEMPTS):
            try:
                record = trial(item)
            except Void as failure:
                print(f"  {item.id:28} session failed ({failure}), "
                      f"attempt {attempt + 1}/{ATTEMPTS}")
                continue
            action = "rewrote" if record["edited"] else "declined"
            print(f"  {item.id:28} {item.arm:10} {action}  ({record['wall_s']}s)")
            break
        else:
            void.append(item.id)

    if void:
        print(f"\n  void, never completed: {', '.join(void)}")
    return report()


if __name__ == "__main__":
    sys.exit(main())
