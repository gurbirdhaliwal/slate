# repairbench — revision 1

**36 trials, 2026-07-31, `claude-sonnet-5`. Verdict: FAIL — but the failure is
in the instrument, not in the hypothesis. Revision 1 is inconclusive and its
primary number should not be quoted.**

Pre-registration: [`spec.py`](spec.py), committed in `8ada299` before any agent
ran. Raw records: [`results-rev1.json`](results-rev1.json).

## What the thresholds said

| Metric | Result | Threshold | |
|---|---|---|---|
| every named symbol exists | 29% | ≥90% | **fail** |
| rewrite still names code | 100% | ≥95% | pass |
| declined on accurate claims | 88% | ≥50% | pass |

`spec.verdict()` returns FAIL, which under the pre-registration means Phases 2
and 3 of `docs/repair-and-resume-plan.md` do not get built. That conclusion
stands. The reasoning below is why it should not be read as "agents cannot
repair documentation".

## The headline the thresholds missed

**The agent declined 16 of 18 genuinely stale claims.** It edited two.

That is a valid measurement — declining is directly observed, with no
instrument in the way — and it is the most interesting number here. It also
guts the control comparison:

| arm | declined |
|---|---|
| repairs (known stale) | 16/18 — 89% |
| controls (known accurate) | 7/8 — 88% |

The control arm passed its threshold, and the pass is meaningless. The arms are
indistinguishable. The threshold was a proxy for discrimination, and identical
decline rates across arms show there is none — the agent declines almost
everything, so it would have "passed" against any control set at all.

Recording this is the point of having written the threshold down first. It
passed, and it still tells us nothing.

## Why the primary metric is void

Three independent reasons, any one sufficient:

1. **It scored unchanged text.** With 16/18 declines, most "rewrites" measured
   were the original sentences. The metric describes the docs Flask already
   ships, not anything an agent produced.
2. **The resolver cannot express Flask's API.** `flask.request`, `flask.g`,
   `flask.url_for`, `app.config` are attributes of a package, not modules, so
   looking for `flask/request.py` fails on prose that is perfectly correct.
   This is the same shallow-resolution bound the decision log already records,
   now measured at scale: 15 of the 18 unresolved refs are real Flask API.
3. **It punishes accurate prose about deletions.** The agent wrote "The
   `flask.ext` package has been removed" — true, useful, and it names something
   that by definition no longer exists. A resolve-based gate marks the correct
   sentence wrong.

Point 3 is not an implementation bug, and it matters beyond this run: it rules
out `refs_resolve` as Phase 2's gate in the form proposed. A gate that cannot
express "this API is gone" cannot verify documentation about a codebase that
deletes things.

## The corpus is weaker than it was designed to be

The treatment arm assumed *a maintainer later rewrote this sentence* implies
*this sentence was false*. Inspection says otherwise:

- `docs/views.rst` ×2 — fix commit is "rewrite class-based view docs". An
  editorial restructure. The old sentences were not wrong.
- `docs/api.rst` — `:class:`ctx._AppCtxGlobals`` became `:class:`._AppCtxGlobals``.
  A Sphinx reference-style change, not a factual correction.
- `.slate/read-next.md` — a real falsification ("renders `freshness.evaluate_all`
  and nothing else" was untrue once co-change shipped), and the agent missed it.

So an unknown fraction of the 18 "stale" claims were never stale, and the
agent's declines may be largely correct. The two readings — *too conservative*
versus *correctly conservative on a mislabelled corpus* — cannot be separated
from this data.

## Harness defects found

- **10 of 18 controls were skipped**, all "sentence not present at HEAD": the
  control corpus stores claim text normalised by the segmenter (lines joined),
  which no longer matches the file byte-for-byte. The control arm ran at n=8.
- **`.rst` is missing from `refs._FILE_EXTENSIONS`**, so `CHANGES.rst` is
  extracted as a *symbol reference* rather than a filename. A real product bug
  for any repo documenting in reStructuredText, not just a harness artifact.

## What revision 2 needs

1. **Label the corpus by falsification, not by edit.** Every pair adjudicated
   by hand as *falsified* / *editorially rewritten*, and only the first kept.
   This is the blocker; nothing else is worth doing first.
2. **Drop `refs_resolve` as a primary.** It cannot survive deletions. If a
   mechanical gate is wanted, it has to be able to say "gone".
3. **Measure discrimination as a difference between arms**, not a threshold on
   one. Identical decline rates must read as failure, not as a pass.
4. **Fix the control matching** so the arm runs at full n.

## What stands from revision 1

- The agent never stripped backticks — 18/18 kept their refs. The cheapest way
  to make a doc green and never be caught again did not happen once.
- Agents offered an explicit, well-scoped repair task mostly decline it. That
  echoes the MCP finding from the 2026-07-27 sweep: *offering* an agent a
  documentation action is not sufficient to get the action, even when the task
  is handed over pre-scoped with the diff attached.
