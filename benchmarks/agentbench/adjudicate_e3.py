#!/usr/bin/env python3
"""Dump every E3 repair beside the code it describes, for hand adjudication.

    python benchmarks/agentbench/adjudicate_e3.py

`claims_repaired` counts claims that stopped being flagged. It does not — and
`repair.verify_repair` deliberately does not — say the new prose is *true*. The
gate checks that an edit is well-formed and confined; truth needs a human, the
same split repairbench revision 3 used.

Trial 1 is why this exists. The agent implemented `_session` as a property
returning `self.session`, which is the inverse of the real PR, and then wrote a
doc sentence that describes its own implementation accurately. Mechanically that
is a repair; the layer now tracks the code. Whether the code is *right* is the
grader's question, and the two must not be conflated in the write-up.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import spec  # noqa: E402

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TRIALS = HERE / ".work" / "trials"


def seeded_prefixes() -> list[str]:
    return [claim.split("`")[1] for claim in spec.SEEDED_CLAIMS]


def main() -> int:
    arms = [a.name for a in spec.REPAIR_ARMS]
    for sidecar in sorted(RUNS.glob("*.json")):
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if record.get("arm") not in arms:
            continue
        if not record.get("claims_repaired"):
            continue
        print("=" * 78)
        print(f"{record['arm']} trial {record['trial']} — "
              f"repaired {record['claims_repaired']}/"
              f"{record['suspect_claims_unrepaired']}, "
              f"apply {record['repair_apply_accepted']}ok/"
              f"{record['repair_apply_rejected']}rej, "
              f"solution {'correct' if record['correct'] else 'INCORRECT'}")

        doc = RUNS / f"{record['arm']}-{record['trial']}.read-next.md"
        if doc.exists():
            body = doc.read_text(encoding="utf-8")
            _, _, after = body.partition(spec.SEEDED_SECTION)
            print("\n--- prose as the agent left it ---")
            print(after.split("## ")[0].strip()[:1200])

        root = TRIALS / f"{record['arm']}-{record['trial']}"
        if root.exists():
            print("\n--- the code it is describing ---")
            diff = subprocess.run(
                ["git", "-C", str(root), "diff", "--", "src"],
                capture_output=True, text=True).stdout
            for line in diff.splitlines():
                if line.startswith(("+++", "---", "@@")) or line[:1] in "+-":
                    print(line[:120])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
