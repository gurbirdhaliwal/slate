"""Pre-registered experiment definitions.

Everything a skeptic would accuse us of tuning after the fact lives here and is
fixed before any agent runs: the repo, the commits, the task text, the arms,
the grader, and the definition of every metric. `run.py` only executes it.

The design isolates one variable. Both experiments use the *same* repo state,
the *same* task, and the *same* grader; the arms differ only in what context
sits in the working tree:

    E1 cold-start   context describes the code as it is    -> orientation cost
    E2 stale-trap   context describes the code as it was   -> cost of rot

so E1-vs-E2 within an arm prices staleness, and arm-vs-arm within E2 prices
the freshness signal.

Three design constraints came out of failed attempts, and all three matter:

0. **The prompt must state the contract the grader enforces.** Revised
   2026-07-27, after 35 trials scored exactly 49 passed / 2 failed — a figure
   an *untouched tree* also scores. Every agent's work moved the grader by
   zero. The cause was not difficulty: agents wrote good fixes that collected
   errors from every callback and re-raised them chained through
   ``__context__``, which satisfies the old prompt exactly. The grader test
   requires a nested ``ExceptionGroup`` with specific message strings, and the
   prompt never said so. That grades "did you guess the maintainers' API
   choice", which **no context layer can help with** — the answer is not in the
   repo, it is in a PR that does not exist yet. Correctness was therefore
   pinned at 0 for every arm including a hypothetical perfect one, so the
   benchmark could not detect a context effect on correctness even if one
   existed. The prompt now states the observable contract and still withholds
   *where* to implement it, which is the part repo context is supposed to
   supply. Results from before this revision are not comparable on
   `correct`; their cost metrics are unaffected, since the prompt is identical
   across arms within any one sweep.

1. **The task must not be greppable.** The first task asked for a change to
   `template_filter`, which already existed — every arm's agent simply grepped
   the feature name, landed in the right file within two tool calls, and no
   context could have helped. This task adds behaviour that has no name in the
   tree yet, so the agent has to work out *where* teardown callbacks are run.

2. **The context must actually reach the model.** Claude Code reads
   `CLAUDE.md`, not `AGENTS.md` (confirmed by canary runs and by the official
   docs). The first attempt measured five arms that were all secretly `bare`.
   `run.py` now bridges the layer into `CLAUDE.md` and asserts delivery before
   any trial counts.

Why this task: `c17f3793` ("request context tracks session access") is a real
merged commit shipping its own tests. It spans four files across three
concerns — `sessions.py` (the session object learns `accessed`), `ctx.py`
(the request context holds the real session behind `_session`), `app.py`
(the `Vary: Cookie` decision) and `templating.py`. Nothing in the tree names
the feature beforehand, so it cannot be reached by grepping a feature name.

Why revision 3 exists: revision 2 was solved by every arm on every trial.
`bare` scored 6/6 with no context at all and found a ground-truth file in
exactly two tool calls every time, so correctness, wrong turns and
orientation cost were all pinned. A benchmark that cannot separate "no
context" from "perfect context" cannot answer the question it was built for,
whichever direction it fails in.

Why the grader is not the whole story here: `templating.py` is in the real PR
and skipping it breaks no test — verified by applying the solution minus that
file and running the full suite (489 passed; the one failure is the known
baseline). Upstream test suites routinely fail to cover the secondary file,
so completeness is measured directly from the transcript via
`ground_truth_touched` rather than inferred from a pass/fail that cannot
express it. That metric is the one a co-change fact should move: it is the
difference between "I found where to start" and "I found everything this
change touches".
"""

from __future__ import annotations

from dataclasses import dataclass, field

REPO_URL = "https://github.com/pallets/flask.git"

# The commit the task is implemented against (the real PR's parent).
BASE_COMMIT = "c17f3793^"
# The commit whose tests grade the result (the real PR).
SOLUTION_COMMIT = "c17f3793"
# What the stale arms' context describes. Unset for revision 3: the previous
# value (`c2705ffd^`) is three commits *after* this task, so it cannot
# describe a past the task's base ever had. `0ec7f713` ("Split the App and
# Blueprint into Sansio and IO parts", 2,975 lines churned) is the identified
# candidate and does precede the base, but designing an honest stale arm from
# it needs archaeology the E1 question does not.
STALE_DOC_COMMIT: str | None = None

MODEL = "claude-sonnet-5"
TRIALS = 5

# Bumped whenever the task, grader or arms change in a way that makes older
# records incomparable. Stamped into every result so a report can refuse to
# average two different experiments — the failure this exists to prevent is
# quieter than a crash: `runs/` holds one file per arm+trial, a re-run
# overwrites in place, and nothing else would notice that half the directory
# answers a different question.
#   1 — original prompt: behaviour only, no contract. Correctness floored at 0
#       for every arm (see the module docstring); cost metrics still valid.
#   2 — prompt states the ExceptionGroup contract the grader enforces.
#       Overcorrected: `bare` scored 6/6 and every metric ceilinged, so a
#       context effect was undetectable in the other direction.
#   3 — new task (session access tracking) chosen for a difficulty band, plus
#       `ground_truth_touched` to measure scope discovery directly rather
#       than relying on upstream tests to cover the secondary file.
TASK_REVISION = 3

# Identical for every arm. Describes the behaviour, never the file layout or
# the shape of the fix — naming those would hand over the very thing the
# context is supposed to supply. Taken from the real changelog entry.
TASK_PROMPT = """\
Flask sends `Vary: Cookie` on every response that has a session, whether or
not the view actually looked at the session. That makes responses less
cacheable than they need to be.

Make it conditional, to the following contract.

- A session object reports whether it has been read and whether it has been
  changed, via `accessed` and `modified` attributes.
- Merely handling a request does not count as reading the session. Reading a
  key, or writing one, does.
- A response gets `Vary: Cookie` only when the session was read or changed
  during that request. A request that never touches the session must not get
  it.
- Writing to the session still saves the cookie, exactly as before.
- The request context exposes the underlying session object as `_session`, so
  it can be inspected without that inspection itself counting as a read.

Do not modify anything under tests/.
"""

# The source files the real PR changed — the ones a correct solution touches.
GROUND_TRUTH_FILES = frozenset({
    "src/flask/ctx.py",
    "src/flask/sessions.py",
    "src/flask/app.py",
    "src/flask/templating.py",
})

# The subset the grader's tests actually exercise. `templating.py` is in the
# real PR and is *not* here, because skipping it fails nothing: verified by
# applying the full solution minus that file and running the whole suite —
# 489 passed, and the single failure was the known-baseline one. Upstream
# tests routinely miss the secondary file (the `open_resource` candidate had
# the same hole in `blueprints.py`), which is why scope discovery is measured
# from the transcript by `ground_truth_touched` rather than inferred from a
# pass/fail the tests cannot produce.
GRADED_FILES = frozenset({
    "src/flask/ctx.py",
    "src/flask/sessions.py",
    "src/flask/app.py",
})

# Everything the real PR touched. Editing the changelog or the docs is
# legitimate, so only writes outside this set count as off-target.
ALLOWED_EDIT_FILES = GROUND_TRUTH_FILES | {
    "CHANGES.rst",
    "docs/api.rst",
}

# Names the pre-refactor doc uses that no longer describe how Flask works.
# `_cv_request` is gone entirely; `RequestContext` survives only as a few
# vestigial mentions, so searching for it returns just enough to mislead.
# Reaching for either is the measurable wrong turn.
# Revision 3 runs E1 only, so there is no stale doc and nothing to be misled
# by. Kept empty rather than deleted: the metric still records, and a
# non-empty value here would silently count names this experiment never
# planted.
DECOY_SYMBOLS: tuple[str, ...] = ()

# The PR's own tests, restored from SOLUTION_COMMIT after the agent stops so
# they cannot be read during the run or edited to pass.
GRADER_TESTS = (
    "tests/test_basic.py",
)

# Runtime deps pinned once so every trial grades in an identical environment.
# Flask itself is never installed; PYTHONPATH points at the trial's own src/,
# so the agent's edits are what gets tested.
VENV_PACKAGES = (
    "pytest<9", "werkzeug>=3.1", "jinja2>=3.1.2", "click>=8.1.3",
    "blinker", "itsdangerous", "markupsafe", "asgiref", "greenlet",
    "python-dotenv",
)

# Known-failing at BASE_COMMIT with these dep versions and unrelated to the
# task: werkzeug changed how a malformed environ is reported, and the version
# check needs Flask installed as a distribution rather than imported off
# PYTHONPATH. Both fail identically in every arm, so they are baselined and
# graded as a delta. Asserted by `--verify-baseline`.
EXPECTED_BASELINE_FAILURES = frozenset({
    "tests/test_reqctx.py::test_bad_environ_raises_bad_request",
    "tests/test_cli.py::test_get_version",
})


@dataclass(frozen=True)
class Arm:
    name: str
    experiment: str
    # "none" | "handwritten" | "slate"
    context: str
    # Commit the context describes. None means BASE_COMMIT (i.e. accurate).
    doc_commit: str | None = None
    blurb: str = ""
    # Install Slate's Claude Code hooks, so freshness is injected rather than
    # offered as an MCP tool the agent may decline to call.
    hooks: bool = False


ARMS: tuple[Arm, ...] = (
    Arm(
        name="bare",
        experiment="E1",
        context="none",
        blurb="No context layer. The agent rediscovers the repo every session.",
    ),
    Arm(
        name="handwritten-fresh",
        experiment="E1",
        context="handwritten",
        blurb="A good-faith hand-written context doc, accurate right now.",
    ),
    Arm(
        name="slate-fresh",
        experiment="E1",
        context="slate",
        blurb="`slate init` at the task commit; every doc reports fresh.",
    ),
    Arm(
        name="slate-fresh-hooked",
        experiment="E1",
        context="slate",
        hooks=True,
        blurb="`slate init` plus hook delivery, so freshness is injected "
              "rather than offered as a tool the agent may decline to call.",
    ),
)

# Revision 3 is E1 only. The E2 arms are omitted rather than carried forward
# with a broken commit: `STALE_DOC_COMMIT` has no valid value for this base
# (see above), and an arm whose "stale" doc is actually fresh would look like
# a null result for staleness rather than a missing experiment.

# Text only Slate's hooks emit. Used to measure delivery from the transcript
# itself rather than assuming the hook fired — the same discipline that caught
# the first sweep measuring five identical arms.
#
# KNOWN BLIND SPOT, measured not assumed: only the SessionStart marker is
# observable. Claude Code records SessionStart's injected context in the
# stream-json transcript but does *not* record PreToolUse's, so a PreToolUse
# warning that genuinely fired and genuinely reached the model leaves no trace
# here. Verified by instrumenting the hook command itself to log every
# invocation: in a session that read a covered file, both `SessionStart` and
# `PreToolUse Read` fired and both returned additionalContext, while the
# transcript for the same session contained only the SessionStart marker.
#
# So `hook_injections` is a floor on delivery, never a ceiling, and it cannot
# separate "SessionStart only" from "SessionStart plus PreToolUse". Do not read
# a zero PreToolUse count as the hook not firing.
HOOK_MARKERS = ("Slate context layer",)
HOOK_MARKERS_UNOBSERVABLE = ("context doc(s) that are not fresh",)


# The hand-written baseline. Written to be genuinely useful — this is the
# honest alternative Slate has to beat, so a strawman here would invalidate
# the whole comparison. Both variants are the same document; only the context
# model they describe differs, which is exactly what going stale means.
HANDWRITTEN_TEMPLATE = """\
# Flask — repo context

Flask is a WSGI web application framework. Read this before changing code.

## Layout

- `src/flask/` — the package.
  - `app.py` — the `Flask` class: the WSGI application and request dispatch.
  - `sansio/` — I/O-independent base classes shared with Quart. `sansio/app.py`
    holds `App` (config, blueprint registration, template decorators);
    `sansio/scaffold.py` holds `Scaffold`, the common base including `route`.
  - `ctx.py` — execution contexts.{ctx}
  - `globals.py` — the `current_app`, `g`, `request` and `session` proxies,
    bound to the context vars declared here.
  - `helpers.py` — small shared utilities used across the package.
  - `templating.py`, `sessions.py`, `wrappers.py`, `config.py`, `cli.py` —
    supporting modules.
- `tests/` — pytest suite, one module per area.

## How to test

```
pytest tests/
```

The suite is fast (a couple of seconds). Run it before finishing.

## Conventions

- Type annotations everywhere; the package ships `py.typed`.
- Public behaviour changes need an entry in `CHANGES.rst`.
- Shared helper classes and functions belong in `helpers.py` rather than being
  defined inline in `app.py` or `ctx.py`.
"""

# Accurate at BASE_COMMIT (`c17f3793^`): two execution contexts, and the
# session living on the request context. Written as a good-faith orientation
# doc — it describes structure, never the change being asked for.
CTX_CURRENT = """
    Two execution contexts. `AppContext` carries the application and `g`,
    tracked by the `_cv_app` context var. `RequestContext` carries the request
    and the session, tracked by `_cv_request`. Each has its own `push()`/
    `pop()` pair, and the session is set up when the request context is
    pushed."""

# Unused in revision 3 (E1 only — there is no valid STALE_DOC_COMMIT for this
# base). Kept so the template still formats and so the E2 arms can be
# restored without rewriting it.
CTX_STALE = CTX_CURRENT


@dataclass
class Metrics:
    """Every number `run.py` records, defined once.

    Token counts are broken out rather than summed: a multi-turn session
    re-reads its whole context every turn, so a single total is dominated by
    cache reads and tracks turn count more than context size.
    """

    arm: str = ""
    trial: int = 0
    # Which task revision produced this record. Records written before the
    # field existed are revision 1 by absence.
    task_revision: int = TASK_REVISION
    # SHA-256 of the transcript these metrics were derived from. `--reparse`
    # refuses to rewrite a record from a transcript that does not match,
    # because the failure is silent and total: `runs/` keys on arm+trial, a
    # re-run replaces a sidecar but can leave an older sweep's transcript
    # beside it, and reparsing then rewrites today's metrics from last week's
    # session while keeping today's label. Observed, not hypothesised.
    transcript_sha: str = ""
    ok: bool = False

    input_tokens: int = 0          # fresh + cache-creation + cache-read
    fresh_input: int = 0
    cache_creation: int = 0
    cache_read: int = 0
    output_tokens: int = 0
    num_turns: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0

    tool_calls: int = 0
    # Calls to Slate's own MCP tools (slate_read / slate_status / ...). The
    # freshness signal is only worth anything if the agent consults it, so
    # this is the metric that decides whether the mechanism is reachable at
    # all — separately from whether it is correct.
    slate_tool_calls: int = 0
    # Times Slate's hook injected freshness into the window. Unlike
    # slate_tool_calls this does not depend on the agent choosing anything, so
    # a hooked arm reading 0 here means the delivery mechanism failed and the
    # trial says nothing about hooks.
    hook_injections: int = 0
    # How many of GROUND_TRUTH_FILES the agent actually opened or edited.
    # Scope discovery, measured directly. The grader cannot express this —
    # `templating.py` is in the real PR and skipping it fails no test — so a
    # pass/fail says only "the part that is covered works". This is the
    # metric a co-change fact should move, since co-change answers "what else
    # does this change touch?" and nothing else in the layer does.
    ground_truth_touched: int = 0
    # How many of GROUND_TRUTH_FILES the agent actually *edited*. `touched`
    # counts any mention in a tool call, so it saturates at 4/4 the moment the
    # agent reads around — the revision-3 pilot scored 4/4 on trials that
    # never edited `sessions.py` at all, which is precisely the omission that
    # failed them. Edits are the scope signal; reads are curiosity.
    ground_truth_edited: int = 0
    files_read: int = 0            # unique paths opened
    decoy_hits: int = 0            # reaches for a name the refactor removed
    found_target_after: int = 0    # tool calls before first ground-truth touch
    off_target_edits: int = 0      # edits outside ALLOWED_EDIT_FILES
    failed_commands: int = 0       # shell calls that exited non-zero
    correction_cycles: int = 0     # failed verification -> further editing

    grader_passed: int = 0
    grader_failed: int = 0
    new_suite_failures: list[str] = field(default_factory=list)
    correct: bool = False          # all grader tests pass, no new failures
    touched_tests: bool = False    # tried to edit the grader's own tests
