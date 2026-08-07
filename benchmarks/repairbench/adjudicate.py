#!/usr/bin/env python3
"""Freezes the revision 3 records into one file, with the hand pass beside them.

    python benchmarks/repairbench/adjudicate.py > /dev/null   # writes the JSON

Two kinds of judgement live in the output and they are kept apart on purpose.
``mechanical`` is what ``spec.verdict()`` saw — computed by the scorer that was
committed before any agent ran, and the only thing the pre-registered verdict
rests on. ``adjudicated`` is a human reading of the same text afterwards, which
no threshold consumes.

Revision 1 did this the other way round: it adjudicated its corpus after the
fact and discovered the labels were wrong, which is what voided the run. Here
the labels were fixed at construction, so adjudication can only find scorer
error — and it found two, both of which cost the agent credit it had earned.
Neither can have manufactured the PASS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus  # noqa: E402
import spec  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
OUT = HERE / "results-rev3.json"

# One line per trial, written after reading the rewrite and the code it
# describes. `correct` is the answer to a single question: did the agent do the
# right thing for this passage — rewrite it truthfully, or leave it alone?
ADJUDICATION = {
    "t01-redirect-code": (True, "302 -> 303, nothing else touched."),
    "t02-autoescape-case": (True, "Names the lowercasing and flips the INDEX.HTML example."),
    "t03-copy-request-context": (True, "Keeps decoration-time capture, corrects the per-call copy."),
    "t04-methodview-metaclass": (
        True,
        "SCORER ERROR. Names `__init_subclass__` correctly. `states_new_fact` "
        "read False because the trailing '(no longer a separate MethodViewType "
        "metaclass)' put a negation cue inside the window around the new fact. "
        "Negation-awareness belongs to the old-fact question only; applying it "
        "to the new fact turns a well-written contrast into a miss."),
    "t05-session-expiry-naive": (True, "naive utcnow -> datetime.now(timezone.utc)."),
    "t06-blueprint-empty-name": (True, "Adds the empty-name rejection, keeps the dot rule."),
    "t07-teardown-first-error": (
        True,
        "Went past the diff to `_CollectErrors` and named the grouped re-raise."),
    "t08-subdomain-matching": (
        True,
        "CORPUS ERROR. The rewrite is accurate and more precise than the "
        "authored `truth` note, which claimed the subdomain is now derived from "
        "SERVER_NAME. It is not: the commit gates the default_subdomain branch "
        "on `host_matching` and changes its fallback from None to \"\". The "
        "`old_fact` pattern named a clause the commit never falsified, so "
        "`drops_old_fact` read False for keeping a sentence that is still true."),
    "t09-open-resource-encoding": (True, "Adds `encoding`, including the binary-mode caveat."),
    "t10-config-pathlike": (True, "str -> str | os.PathLike."),
    "t11-cookie-domain-fallback": (True, "Removes the fallback and says so explicitly."),
    "t12-generator-response": (True, "Adds generator/iterator and the streaming conversion."),
    "c01-send-file": (True, "Declined; identified the annotation-only change."),
    "c02-send-from-directory": (True, "Declined; identified the docstring-only security note."),
    "c03-stream-with-context": (True, "Declined; identified the mypy suppression."),
    "c04-make-response-headers": (True, "Declined; identified the type: ignore."),
    "c05-process-response": (True, "Declined; traced `_get_session` and found behaviour unchanged."),
    "c06-sansio-app-init": (True, "Declined; identified the -> None annotation."),
    "c07-jinja-loader": (True, "Declined; noted the passage never named the return type."),
    "c08-separated-path-type": (True, "Declined; identified the super() hoist as a pure refactor."),
    "c09-save-session": (True, "Declined; identified the type-ignore change."),
    "c10-request-endpoint": (True, "Declined; identified the type: ignore."),
    "c11-config-from-mapping": (True, "Declined; identified the docstring rewrap."),
    "c12-null-session": (True, "Declined; identified the noqa removal."),
}


def main() -> int:
    records = []
    for item in corpus.load_corpus():
        record = json.loads((RUNS / f"{item.id}.json").read_text(encoding="utf-8"))
        assert record["revision"] == spec.REVISION, item.id
        correct, note = ADJUDICATION[item.id]
        record["mechanical"] = {
            "edited": record["edited"],
            "states_new_fact": record["states_new_fact"],
            "drops_old_fact": record["drops_old_fact"],
            "repaired": (record["edited"] and record["states_new_fact"]
                         and record["drops_old_fact"]),
        }
        record["adjudicated"] = {"correct": correct, "note": note}
        records.append(record)

    OUT.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    falsified = [r for r in records if r["arm"] == "falsified"]
    accurate = [r for r in records if r["arm"] == "accurate"]
    mech = sum(r["mechanical"]["repaired"] for r in falsified)
    hand = sum(r["adjudicated"]["correct"] for r in falsified)
    print(f"falsified: {sum(r['edited'] for r in falsified)}/{len(falsified)} edited, "
          f"mechanical {mech}/{len(falsified)}, adjudicated {hand}/{len(falsified)}")
    print(f"accurate:  {sum(r['edited'] for r in accurate)}/{len(accurate)} edited, "
          f"adjudicated {sum(r['adjudicated']['correct'] for r in accurate)}/{len(accurate)} correct")
    print(f"wrote {OUT.relative_to(HERE.parents[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
