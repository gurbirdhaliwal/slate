"""PR bot: post (or update) a context-freshness comment on a pull request.

Runs inside the composite action at the repo root (`action.yml`). Consumers:

    - uses: actions/checkout@v4
      with: { fetch-depth: 0 }        # slate anchors freshness to history
    - uses: gurbirdhaliwal/slate@v0.4.0

Stdlib only, like everything else. The comment is idempotent: a hidden
marker identifies the bot's comment and it is edited in place on
subsequent pushes rather than stacking new comments.

Env contract (set by action.yml):
    GITHUB_TOKEN            token with pull-requests: write
    GITHUB_REPOSITORY       owner/repo
    GITHUB_EVENT_PATH       webhook payload (needs pull_request events)
    GITHUB_API_URL          default https://api.github.com
    SLATE_COMMENT           "true"/"false" — post the comment (default true)
    SLATE_FAIL_ON_STALE     "true"/"false" — exit 1 on problems (default true)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

MARKER = "<!-- slate-context-bot -->"
ICONS = {"fresh": "🟢", "stale": "🟠", "needs-verification": "🟡"}


def slate_json(*args: str) -> list[dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "slate.cli", *args, "--json"],
        capture_output=True, text=True,
    )
    if proc.returncode == 2:
        raise SystemExit(f"slate failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def build_comment(status: list[dict], scores: list[dict]) -> str:
    """The comment body. Pure function — unit-tested without a network."""
    by_path = {s["path"]: s for s in scores}
    problems = [d for d in status if d["status"] != "fresh"]

    lines = [MARKER, "## Slate context check", ""]
    if not problems:
        lines.append("All context docs are **fresh** — safe for AI sessions to trust. ✅")
    else:
        noun = "doc" if len(problems) == 1 else "docs"
        lines.append(
            f"**{len(problems)} context {noun} may be invalidated by this PR.** "
            "Run `slate sync` (generated docs) or review + `slate mark` "
            "(human-owned docs), and commit the updates to this branch."
        )
    lines += ["", "| Doc | Status | Score | Detail |", "|---|---|---|---|"]
    for d in status:
        icon = ICONS.get(d["status"], "")
        score = by_path.get(d["path"], {}).get("score")
        score_cell = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
        detail = d.get("reason", "")
        changed = d.get("changed_watched") or []
        if changed:
            shown = ", ".join(f"`{p}`" for p in changed[:3])
            more = f" +{len(changed) - 3} more" if len(changed) > 3 else ""
            detail = f"{shown}{more}"
        missing = by_path.get(d["path"], {}).get("missing_paths") or []
        if missing:
            detail += f" · ⚠ references missing paths: {', '.join(f'`{m}`' for m in missing[:3])}"
        lines.append(f"| `{d['path']}` | {icon} {d['status']} | {score_cell} | {detail} |")
    lines += [
        "",
        "<sub>Posted by <a href=\"https://github.com/gurbirdhaliwal/slate\">Slate</a> — "
        "the context control plane for AI-assisted repos. Statuses derive from git; "
        "`slate diff` shows what changed vs. what each doc claims.</sub>",
    ]
    return "\n".join(lines)


def _api(method: str, url: str, token: str, body: dict | None = None) -> list | dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "authorization": f"Bearer {token}",
            "accept": "application/vnd.github+json",
            "content-type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read() or b"null")


def upsert_comment(body: str) -> None:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    with open(os.environ["GITHUB_EVENT_PATH"]) as fh:
        event = json.load(fh)
    pr = event.get("pull_request", {}).get("number")
    if not pr:
        print("not a pull_request event — skipping comment")
        return

    comments_url = f"{api}/repos/{repo}/issues/{pr}/comments"
    existing = _api("GET", f"{comments_url}?per_page=100", token)
    mine = next((c for c in existing if MARKER in (c.get("body") or "")), None)
    if mine:
        _api("PATCH", f"{api}/repos/{repo}/issues/comments/{mine['id']}", token, {"body": body})
        print(f"updated comment {mine['id']} on PR #{pr}")
    else:
        _api("POST", comments_url, token, {"body": body})
        print(f"posted comment on PR #{pr}")


def main() -> int:
    status = slate_json("status")
    scores = slate_json("verify")
    body = build_comment(status, scores)

    if os.environ.get("SLATE_COMMENT", "true").lower() != "false":
        upsert_comment(body)
    else:
        print(body)

    problems = [d for d in status if d["status"] != "fresh"]
    if problems and os.environ.get("SLATE_FAIL_ON_STALE", "true").lower() != "false":
        print(f"{len(problems)} context doc(s) not fresh", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
