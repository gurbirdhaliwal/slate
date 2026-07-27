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

Two design constraints came out of a failed first attempt, and both matter:

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

Why this task: `fbb6f0bc` ("all teardown callbacks are called despite errors",
Flask PR #5928) is a real merged commit that ships its own tests and spans
three files in two concerns — `helpers.py` (a new `_CollectErrors` helper),
`ctx.py` and `app.py` (the teardown loops that use it). Nothing in the tree
names the feature beforehand.

Why this staleness: `c2705ffd` ("merge app and request context") rewrote
`ctx.py` — 467 lines — and deleted `RequestContext` and `_cv_request`
outright, folding request handling into `AppContext`. A doc written before it
describes two context objects with two teardown paths; at the task commit
there is one. The old names still appear vestigially in the tree, so grepping
them returns just enough to look plausible. That is 50 commits and five months
of drift, not a contrived scenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REPO_URL = "https://github.com/pallets/flask.git"

# The commit the task is implemented against (the real PR's parent).
BASE_COMMIT = "fbb6f0bc^"
# The commit whose tests grade the result (the real PR).
SOLUTION_COMMIT = "fbb6f0bc"
# What the stale arms' context describes: the last tree before Flask merged
# the request context into the application context.
STALE_DOC_COMMIT = "c2705ffd^"

MODEL = "claude-sonnet-5"
TRIALS = 5

# Identical for every arm. Describes the behaviour, never the file layout or
# the shape of the fix — naming those would hand over the very thing the
# context is supposed to supply. Taken from the real changelog entry.
TASK_PROMPT = """\
In Flask, teardown callbacks (those registered with `teardown_appcontext` and
`teardown_request`) are not all guaranteed to run: if one of them raises, the
remaining callbacks are skipped.

Fix this. Every teardown callback must be called, even when an earlier one
raises. If any of them raised, the error must still surface to the caller
after they have all run — and if more than one raised, none of those errors
may be silently discarded.

Do not modify anything under tests/.
"""

# The source files the real PR changed — the ones a correct solution touches.
GROUND_TRUTH_FILES = frozenset({
    "src/flask/app.py",
    "src/flask/ctx.py",
    "src/flask/helpers.py",
})

# Everything the real PR touched. Editing the changelog or the docs is
# legitimate, so only writes outside this set count as off-target.
ALLOWED_EDIT_FILES = GROUND_TRUTH_FILES | {
    "CHANGES.rst",
    "docs/appcontext.rst",
}

# Names the pre-refactor doc uses that no longer describe how Flask works.
# `_cv_request` is gone entirely; `RequestContext` survives only as a few
# vestigial mentions, so searching for it returns just enough to mislead.
# Reaching for either is the measurable wrong turn.
DECOY_SYMBOLS = ("RequestContext", "_cv_request")

# The PR's own tests, restored from SOLUTION_COMMIT after the agent stops so
# they cannot be read during the run or edited to pass.
GRADER_TESTS = (
    "tests/test_appctx.py",
    "tests/test_helpers.py",
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
        name="handwritten-stale",
        experiment="E2",
        context="handwritten",
        doc_commit=STALE_DOC_COMMIT,
        blurb="The same doc, written before the context refactor and never "
              "updated. Nothing in the repo says it is out of date.",
    ),
    Arm(
        name="slate-stale",
        experiment="E2",
        context="slate",
        doc_commit=STALE_DOC_COMMIT,
        blurb="A Slate layer generated before the context refactor; the code "
              "then advanced. `slate status` reports the docs stale.",
    ),
    # --- hook delivery (added 2026-07-27) ----------------------------------
    # The first sweep's load-bearing finding was that the agent made 0 calls to
    # any slate_* tool in 320 tool calls, so the freshness signal was never
    # consulted and E2-vs-E1 measured nothing about freshness. These arms are
    # identical to the two above except that freshness is *injected* by a
    # SessionStart/PreToolUse hook instead of being offered as a tool call.
    #
    # The decisive comparison is slate-stale vs slate-stale-hooked, and the
    # metric that should move is `decoy_hits` — reaching for RequestContext or
    # _cv_request is what being misled by the stale doc looks like. `correct`
    # was 0/25 across every arm last time and is unlikely to be the metric that
    # discriminates; treat it as a control, not the hypothesis.
    Arm(
        name="slate-fresh-hooked",
        experiment="E1",
        context="slate",
        hooks=True,
        blurb="`slate init` at the task commit plus hook delivery. Control for "
              "the cost of injecting a signal when nothing is wrong.",
    ),
    Arm(
        name="slate-stale-hooked",
        experiment="E2",
        context="slate",
        doc_commit=STALE_DOC_COMMIT,
        hooks=True,
        blurb="The stale Slate layer, with freshness injected by hooks rather "
              "than offered as a tool. The agent is told the docs are stale "
              "whether or not it asks.",
    ),
)

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

# Accurate at BASE_COMMIT: one context object, one teardown path.
CTX_CURRENT = """
    `AppContext` is the single execution context — it carries the application,
    `g`, and (when handling a request) the request and session. `push()` and
    `pop()` manage it, and `pop()` is where teardown callbacks are invoked.
    It is tracked by the `_cv_app` context var in `globals.py`."""

# Accurate at STALE_DOC_COMMIT, wrong at BASE_COMMIT: `RequestContext` and
# `_cv_request` no longer exist.
CTX_STALE = """
    Two separate contexts. `AppContext` carries the application and `g`, and
    is tracked by the `_cv_app` context var. `RequestContext` carries the
    request and session, and is tracked by `_cv_request`. Each has its own
    `push()`/`pop()` pair, and each one's `pop()` invokes its own teardown
    callbacks — application teardown in `AppContext.pop()`, request teardown
    in `RequestContext.pop()`."""


@dataclass
class Metrics:
    """Every number `run.py` records, defined once.

    Token counts are broken out rather than summed: a multi-turn session
    re-reads its whole context every turn, so a single total is dominated by
    cache reads and tracks turn count more than context size.
    """

    arm: str = ""
    trial: int = 0
    ok: bool = False
    context_delivered: bool = False  # the layer reached the model

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
