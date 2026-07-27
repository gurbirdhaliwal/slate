#!/usr/bin/env python3
"""Runs the pre-registered agent benchmark in `spec.py` and records raw results.

    python benchmarks/agentbench/run.py --setup          # clone + build venv
    python benchmarks/agentbench/run.py --pilot          # 1 trial per arm
    python benchmarks/agentbench/run.py --trials 5       # the full sweep
    python benchmarks/agentbench/run.py --arm slate-stale --trials 3

Each trial gets a throwaway clone, runs a real headless `claude -p` session
against it, and grades the working tree with the PR's own tests. Nothing is
estimated: tokens and timings come from the CLI's own result envelope, wrong
turns from the tool calls in the transcript, correctness from pytest.

Raw output goes to `benchmarks/agentbench/runs/` — one JSON metrics file and
one full JSONL transcript per trial, so every number in the report can be
traced back to the session that produced it. `report.py` reads that directory.
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

import spec  # noqa: E402

HERE = Path(__file__).resolve().parent
WORK = HERE / ".work"
RUNS = HERE / "runs"
MIRROR = WORK / "flask.git"
VENV = WORK / "venv"
SLATE_BIN = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "slate"

GIT_ID = ["-c", "user.email=bench@slate.local", "-c", "user.name=slate-bench",
          "-c", "commit.gpgsign=false"]


class RateLimited(RuntimeError):
    """The API cut the session short — the trial produced no evidence."""


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *GIT_ID, *args],
                          capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{proc.stderr}")
    return proc.stdout.strip()


# --------------------------------------------------------------------------
# setup


def _grader_python() -> str:
    """Pin the grader interpreter — the result must not depend on whatever
    Python happens to be running the harness."""
    for version in ("3.13", "3.12", "3.11"):
        found = shutil.which(f"python{version}")
        if found:
            return found
    return sys.executable


def _is_git_repo(path: Path) -> bool:
    """Is `path` itself a git repo?

    `rev-parse --git-dir` alone is not enough: it walks *up* the tree, so a
    broken clone nested inside this checkout resolves to Slate's own .git and
    reports success. Compare the resolved dir against the path to be sure.
    """
    if not path.exists():
        return False
    proc = subprocess.run(["git", "-C", str(path), "rev-parse", "--absolute-git-dir"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    return Path(proc.stdout.strip()).resolve() == path.resolve()


def setup() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    # `.exists()` is not a validity check: an interrupted clone leaves a
    # directory with HEAD and config but no objects, and setup then reports
    # "ready" while every trial fails with "repository does not exist".
    # Ask git whether it is actually a repo.
    if not _is_git_repo(MIRROR):
        if MIRROR.exists():
            print(f"{MIRROR.name} is not a valid git repo — re-cloning")
            shutil.rmtree(MIRROR, ignore_errors=True)
        print(f"cloning {spec.REPO_URL} ...")
        subprocess.run(["git", "clone", "--quiet", "--bare", spec.REPO_URL,
                        str(MIRROR)], check=True)
    if not (VENV / "bin" / "python").exists():
        print(f"building grader venv ({_grader_python()}) ...")
        subprocess.run([_grader_python(), "-m", "venv", str(VENV)], check=True)
        subprocess.run([str(VENV / "bin" / "pip"), "install", "-q",
                        *spec.VENV_PACKAGES], check=True)
    print(f"ready: mirror={MIRROR}  venv={VENV}")


def resolve(rev: str) -> str:
    return git(MIRROR, "rev-parse", rev)


# --------------------------------------------------------------------------
# trial construction


def build_trial(arm: spec.Arm, trial: int) -> Path:
    """A throwaway clone with this arm's context in place, code at BASE_COMMIT."""
    root = WORK / "trials" / f"{arm.name}-{trial}"
    if root.exists():
        shutil.rmtree(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout",
                    str(MIRROR), str(root)], check=True)

    base = resolve(spec.BASE_COMMIT)
    if arm.context == "none":
        git(root, "checkout", "-q", "-b", "bench", base)
        _strip_context(root)
        git(root, "add", "-A")
        git(root, "commit", "-qm", "strip context", check=False)
        return root

    doc_rev = resolve(arm.doc_commit) if arm.doc_commit else base
    git(root, "checkout", "-q", "-b", "bench", doc_rev)
    _strip_context(root)

    if arm.context == "handwritten":
        ctx = spec.CTX_STALE if arm.doc_commit else spec.CTX_CURRENT
        (root / "AGENTS.md").write_text(
            spec.HANDWRITTEN_TEMPLATE.format(ctx=ctx))
    elif arm.context == "slate":
        subprocess.run([str(SLATE_BIN), "init"], cwd=root,
                       capture_output=True, check=True)
        # --no-hooks keeps the un-hooked arms as they were in the first sweep,
        # so `slate agent enable claude` gaining hook installation does not
        # silently change the control.
        subprocess.run([str(SLATE_BIN), "agent", "enable", "claude", "--no-hooks"],
                       cwd=root, capture_output=True, check=True)
        if arm.hooks:
            subprocess.run([str(SLATE_BIN), "agent", "hooks", "install"],
                           cwd=root, capture_output=True, check=True)

    _bridge_to_claude_md(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "context layer")

    if doc_rev != base:
        # Advance the code to the task commit without touching the layer: the
        # doc now describes a tree that no longer exists, which is precisely
        # what happens to a committed context layer as a repo moves on.
        git(root, "merge", "-q", "--no-edit", base, "-m", "advance code")
    return root


def _bridge_to_claude_md(root: Path) -> None:
    """Make the layer actually reach the model.

    Claude Code reads `CLAUDE.md`, not `AGENTS.md` — the first run of this
    benchmark measured five arms whose context was never loaded because of
    it. The official remedy is a `CLAUDE.md` that `@`-imports the layer, which
    is what a real user following the docs would write, so that is what the
    arms get. Anything the agent would not have on a real checkout stays out
    of it.
    """
    agents = root / "AGENTS.md"
    if not agents.exists():
        return
    (root / "CLAUDE.md").write_text("@AGENTS.md\n")


# A canary the agent can only know from the delivered context. Cheap insurance
# against silently measuring five identical arms again.
DELIVERY_CANARY = "CTXPROBE-4417"


DELIVERY_ATTEMPTS = 3


def verify_delivery(arm: spec.Arm) -> bool:
    """Confirm this arm's context actually lands in the model's window.

    Retried, because the check is a sampled model response and a single
    refusal or off-format answer is not evidence that delivery is broken —
    but it *is* enough to abort a 70-minute sweep, which happened. Delivery
    is a property of the tree, so it does not vary run to run; a false
    negative here costs far more than the extra call. Any single success
    proves the context arrived, so the retries only ever reduce flake and
    can never manufacture a pass for an arm that genuinely delivers nothing.
    """
    if arm.context == "none":
        return True
    root = build_trial(arm, 0)
    marker = f"\n<!-- delivery check -->\nThe context probe token is {DELIVERY_CANARY}.\n"
    (root / "AGENTS.md").write_text((root / "AGENTS.md").read_text() + marker)

    env = dict(os.environ)
    env["PATH"] = f"{SLATE_BIN.parent}:{env['PATH']}"
    try:
        for attempt in range(DELIVERY_ATTEMPTS):
            proc = subprocess.run(
                ["claude", "-p",
                 "Without using any tools, state the context probe token from your "
                 "project instructions verbatim. If you have none, say NONE.",
                 "--output-format", "json", "--permission-mode", "bypassPermissions",
                 "--model", spec.MODEL],
                cwd=root, env=env, capture_output=True, text=True,
                stdin=subprocess.DEVNULL)
            try:
                if DELIVERY_CANARY in json.loads(proc.stdout).get("result", ""):
                    return True
            except (json.JSONDecodeError, AttributeError):
                pass
            if attempt + 1 < DELIVERY_ATTEMPTS:
                print(f"    delivery check for {arm.name} inconclusive, retrying "
                      f"({attempt + 2}/{DELIVERY_ATTEMPTS})")
        return False
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _strip_context(root: Path) -> None:
    """Remove anything the upstream repo ships that would confound the arms."""
    for name in ("AGENTS.md", "CLAUDE.md", ".cursorrules", ".github/copilot-instructions.md"):
        target = root / name
        if target.exists():
            target.unlink()
    if (root / ".slate").exists():
        shutil.rmtree(root / ".slate")


# --------------------------------------------------------------------------
# the agent run


def run_agent(root: Path, transcript: Path, arm: spec.Arm) -> dict:
    env = dict(os.environ)
    # `slate` must resolve for the MCP server to start at all.
    env["PATH"] = f"{SLATE_BIN.parent}:{env['PATH']}"
    env.pop("ANTHROPIC_MODEL", None)

    cmd = [
        "claude", "-p", spec.TASK_PROMPT,
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "bypassPermissions",
        "--model", spec.MODEL,
    ]
    # A project .mcp.json is not picked up headless — it needs an interactive
    # trust prompt — so the Slate arms pass it explicitly. Without this the
    # slate_* tools simply do not exist in the session.
    if arm.context == "slate" and (root / ".mcp.json").exists():
        cmd += ["--mcp-config", ".mcp.json"]
    started = time.time()
    with transcript.open("w") as sink:
        proc = subprocess.run(cmd, cwd=root, env=env, stdout=sink,
                              stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        print(f"    ! claude exited {proc.returncode}: {proc.stderr[:200]}")
    return {"wall_s": round(time.time() - started, 1)}


# --------------------------------------------------------------------------
# transcript -> metrics


VERIFY_HINTS = ("pytest", "python -m pytest", "tox", "make test")
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
OPEN_TOOLS = {"Read", "Grep", "Glob"}


def _current_transcripts() -> list[Path]:
    """The newest transcript for each trial, one per stem.

    A trial can have both a `.jsonl` (just written) and a `.jsonl.gz` (from an
    earlier sweep, committed). They are different runs of the same arm, so
    reading both double-counts and, worse, lets the older one win.
    """
    newest: dict[str, Path] = {}
    for path in [*RUNS.glob("*.jsonl"), *RUNS.glob("*.jsonl.gz")]:
        stem = path.name.split(".jsonl")[0]
        current = newest.get(stem)
        if current is None or path.stat().st_mtime > current.stat().st_mtime:
            newest[stem] = path
    return [newest[k] for k in sorted(newest)]


def _read_transcript(path: Path) -> str:
    """Transcripts are committed gzipped — 13 MB of raw JSONL is 3.3 MB as
    evidence, and the evidence is the point."""
    if path.suffix == ".gz":
        import gzip
        with gzip.open(path, "rt", errors="ignore") as fh:
            return fh.read()
    return path.read_text(errors="ignore")


def parse_transcript(path: Path, m: spec.Metrics) -> None:
    raw = _read_transcript(path)

    # Hook-injected freshness is counted off the raw transcript rather than a
    # specific event shape: the injection is context, not a tool call, and the
    # envelope it arrives in is Claude Code's to change. A hooked arm reading 0
    # here means delivery failed, which invalidates that trial's claim about
    # hooks — the same check that caught the first sweep measuring five
    # identical arms.
    m.hook_injections = sum(raw.count(marker) for marker in spec.HOOK_MARKERS)

    events = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    pending: dict[str, dict] = {}
    seen_files: set[str] = set()
    found_target_at: int | None = None
    last_failed_verify = False

    for event in events:
        kind = event.get("type")

        if kind == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                m.tool_calls += 1
                name, args = block.get("name", ""), block.get("input", {})
                pending[block.get("id", "")] = {"name": name, "args": args}
                if "slate" in name.lower():
                    m.slate_tool_calls += 1

                # Agents reach for files through Read, Grep, Glob *and* shell
                # (`grep -rn ... src/flask/app.py`). Counting only Read's
                # file_path missed most of the exploration, so any path named
                # anywhere in a tool's arguments counts as touching it. One
                # call that names several decoys still counts once.
                blob = json.dumps(args)
                if any(d in blob for d in spec.DECOY_SYMBOLS):
                    m.decoy_hits += 1
                if any(g in blob for g in spec.GROUND_TRUTH_FILES) and found_target_at is None:
                    found_target_at = m.tool_calls

                path_arg = _path_of(args)
                if name in OPEN_TOOLS and path_arg:
                    rel = _relative(path_arg)
                    if rel:
                        seen_files.add(rel)

                if name in EDIT_TOOLS and path_arg:
                    rel = _relative(path_arg)
                    if rel and rel not in spec.ALLOWED_EDIT_FILES:
                        m.off_target_edits += 1
                    if rel and rel.startswith("tests/"):
                        m.touched_tests = True
                    if last_failed_verify:
                        m.correction_cycles += 1
                        last_failed_verify = False

        elif kind == "user":
            content = event.get("message", {}).get("content") or []
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                call = pending.get(block.get("tool_use_id", ""), {})
                if block.get("is_error") and call.get("name") == "Bash":
                    m.failed_commands += 1
                if call.get("name") == "Bash":
                    command = str(call.get("args", {}).get("command", ""))
                    if any(h in command for h in VERIFY_HINTS):
                        text = str(block.get("content", ""))
                        if block.get("is_error") or " failed" in text or "FAILED" in text:
                            last_failed_verify = True

        elif kind == "result":
            # A rate-limited session still emits a well-formed result envelope
            # with zero usage, which scores as a confident FAIL and looks like
            # a finding. It is not one — refuse to record it.
            if event.get("api_error_status") == 429 or "session limit" in str(
                    event.get("result", "")):
                raise RateLimited(str(event.get("result", "rate limited")))
            usage = event.get("usage", {})
            m.fresh_input = usage.get("input_tokens", 0)
            m.cache_creation = usage.get("cache_creation_input_tokens", 0)
            m.cache_read = usage.get("cache_read_input_tokens", 0)
            m.input_tokens = m.fresh_input + m.cache_creation + m.cache_read
            m.output_tokens = usage.get("output_tokens", 0)
            m.num_turns = event.get("num_turns", 0)
            m.duration_ms = event.get("duration_ms", 0)
            m.cost_usd = event.get("total_cost_usd", 0.0) or 0.0
            m.ok = not event.get("is_error", False)

    m.files_read = len(seen_files)
    m.found_target_after = found_target_at or 0


def _path_of(args: dict) -> str:
    # Deliberately not Grep's `pattern` — that is a regex, not a path.
    for key in ("file_path", "path", "notebook_path"):
        value = args.get(key)
        if isinstance(value, str) and "/" in value:
            return value
    return ""


def _relative(path: str) -> str:
    marker = "/trials/"
    if marker in path:
        tail = path.split(marker, 1)[1]
        return tail.split("/", 1)[1] if "/" in tail else tail
    return path.lstrip("./")


# --------------------------------------------------------------------------
# grading


def grade(root: Path, m: spec.Metrics) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    pytest = [str(VENV / "bin" / "python"), "-m", "pytest", "-q", "--no-header",
              "-p", "no:cacheprovider"]

    # Regression check first, against the repo's own tests and *before* the
    # grader's tests are in the tree. On an unsolved tree a raising teardown
    # leaves a context pushed, which poisons every later test in the same
    # pytest session — 18 unrelated failures that say nothing about the agent.
    # Scoring the two runs separately keeps that cascade out of the result.
    full = subprocess.run(pytest + ["tests/"], cwd=root, capture_output=True,
                          text=True, env=env)
    failures = {ln.split(" ")[1] for ln in full.stdout.splitlines()
                if ln.startswith("FAILED ") and len(ln.split(" ")) > 1}
    failures = {f for f in failures
                if not f.startswith(tuple(spec.GRADER_TESTS))}
    m.new_suite_failures = sorted(failures - spec.EXPECTED_BASELINE_FAILURES)

    # Then restore the grader's tests from the solution commit — unseen during
    # the run, and un-editable by it — and score the task itself.
    git(root, "checkout", resolve(spec.SOLUTION_COMMIT), "--", *spec.GRADER_TESTS)
    # One pytest session per file, for the same reason: a teardown that raises
    # in an unsolved tree leaves a context pushed, and every later test in that
    # session errors out. Shared sessions turned one real failure into 37.
    for test_file in spec.GRADER_TESTS:
        result = subprocess.run(pytest + [test_file], cwd=root,
                                capture_output=True, text=True, env=env)
        passed, failed = _counts(result.stdout)
        m.grader_passed += passed
        m.grader_failed += failed
    m.correct = (m.grader_failed == 0 and m.grader_passed > 0
                 and not m.new_suite_failures)


def _counts(output: str) -> tuple[int, int]:
    """Passed and not-passed from pytest's summary line.

    Collection errors count as failures: when the feature is absent the
    grader's imports do not resolve, which is a failure to implement the task,
    not a neutral outcome.
    """
    passed = failed = value = 0
    for line in output.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            for chunk in line.replace(",", "").split():
                if chunk.isdigit():
                    value = int(chunk)
                elif chunk.startswith("passed"):
                    passed = value
                elif chunk.startswith(("failed", "error")):
                    failed += value
    return passed, failed


# --------------------------------------------------------------------------


def run_trial(arm: spec.Arm, trial: int, keep: bool) -> spec.Metrics:
    metrics = spec.Metrics(arm=arm.name, trial=trial)
    root = build_trial(arm, trial)
    transcript = RUNS / f"{arm.name}-{trial}.jsonl"
    print(f"  {arm.name} trial {trial} ... ", end="", flush=True)

    run_agent(root, transcript, arm)
    parse_transcript(transcript, metrics)
    grade(root, metrics)

    (RUNS / f"{arm.name}-{trial}.json").write_text(
        json.dumps(asdict(metrics), indent=2))
    print(f"{'PASS' if metrics.correct else 'FAIL'} "
          f"| {metrics.fresh_input + metrics.cache_creation:,} ctx "
          f"| {metrics.num_turns} turns "
          f"| {metrics.duration_ms / 1000:.0f}s "
          f"| target@{metrics.found_target_after} "
          f"| decoys={metrics.decoy_hits} corr={metrics.correction_cycles}")
    if not keep:
        shutil.rmtree(root, ignore_errors=True)
    return metrics


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--verify-delivery", action="store_true",
                    help="prove each arm's context reaches the model before "
                         "spending a sweep on it")
    ap.add_argument("--skip-delivery-check", action="store_true")
    ap.add_argument("--reparse", action="store_true",
                    help="recompute metrics from saved transcripts, no agent runs")
    ap.add_argument("--verify-baseline", action="store_true",
                    help="grade an untouched tree: the task must be genuinely "
                         "unsolved, and nothing else may fail")
    ap.add_argument("--pilot", action="store_true", help="one trial per arm")
    ap.add_argument("--trials", type=int, default=spec.TRIALS)
    ap.add_argument("--arm", action="append", help="restrict to named arm(s)")
    ap.add_argument("--keep", action="store_true", help="keep trial worktrees")
    args = ap.parse_args()

    setup()
    if args.setup:
        return 0

    if args.reparse:
        # Metric definitions can change without spending another token: the
        # transcripts are the record, the JSON files are just a view of them.
        # Grading results are preserved — they came from pytest, not the text.
        # One transcript per trial, newest wins. Re-running an arm writes a
        # fresh `.jsonl` beside the previous sweep's committed `.jsonl.gz`, and
        # globbing both processed the stale one *second* — silently replacing
        # today's metrics with the older sweep's. Dedupe by stem before
        # parsing anything.
        transcripts = _current_transcripts()
        for transcript in transcripts:
            stem = transcript.name.split(".jsonl")[0]
            sidecar = RUNS / f"{stem}.json"
            if not sidecar.exists():
                continue
            old = json.loads(sidecar.read_text())
            metrics = spec.Metrics(arm=old["arm"], trial=old["trial"])
            parse_transcript(transcript, metrics)
            for key in ("grader_passed", "grader_failed", "new_suite_failures",
                        "correct", "touched_tests"):
                setattr(metrics, key, old[key])
            sidecar.write_text(json.dumps(asdict(metrics), indent=2))
            print(f"reparsed {sidecar.name}")
        return 0

    if args.verify_baseline:
        root = build_trial(spec.ARMS[0], 0)
        metrics = spec.Metrics(arm="baseline")
        grade(root, metrics)
        print(f"untouched tree: grader {metrics.grader_passed} passed / "
              f"{metrics.grader_failed} failed; "
              f"unexpected suite failures: {metrics.new_suite_failures or 'none'}")
        good = metrics.grader_failed > 0 and not metrics.new_suite_failures
        print("baseline OK — the task is unsolved and the suite is clean"
              if good else "BASELINE BROKEN — fix before trusting any result")
        return 0 if good else 1

    arms = [a for a in spec.ARMS if not args.arm or a.name in args.arm]

    if args.verify_delivery:
        ok = True
        for arm in arms:
            delivered = verify_delivery(arm)
            ok &= delivered
            print(f"  {arm.name:20} context reaches model: "
                  f"{'YES' if delivered else 'NO'}")
        return 0 if ok else 1

    trials = 1 if args.pilot else args.trials
    print(f"\nmodel={spec.MODEL}  base={spec.BASE_COMMIT}  "
          f"arms={[a.name for a in arms]}  trials={trials}\n")

    # Never measure an arm whose context silently never arrived — that is
    # exactly how the first run of this benchmark produced five identical arms.
    if not args.skip_delivery_check:
        for arm in arms:
            if arm.context != "none" and not verify_delivery(arm):
                print(f"ABORT: {arm.name}'s context does not reach the model. "
                      f"Fix delivery or pass --skip-delivery-check.")
                return 1
        print("delivery verified for all arms\n")

    for arm in arms:
        print(f"{arm.name}: {arm.blurb}")
        for trial in range(1, trials + 1):
            try:
                run_trial(arm, trial, args.keep)
            except RateLimited as exc:
                # Every subsequent trial would fail the same way and record a
                # fake FAIL. Stop, and say what is missing.
                print(f"\nRATE LIMITED: {exc}")
                print(f"stopped at {arm.name} trial {trial}. Completed trials "
                      f"are intact in runs/; rerun the missing arms with "
                      f"--arm once the limit resets.")
                return 2
            except Exception as exc:  # a dead trial must not kill the sweep
                print(f"    ! trial failed: {exc}")
        print()
    print(f"raw results in {RUNS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
