"""The PR bot's comment builder is a pure function — test it directly."""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "pr_comment",
    Path(__file__).resolve().parent.parent / "integrations" / "github" / "pr_comment.py",
)
pr_comment = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pr_comment)


STATUS = [
    {"doc": "agents", "path": "AGENTS.md", "status": "fresh",
     "reason": "synced at abc123", "changed_watched": []},
    {"doc": "modules", "path": ".slate/modules.md", "status": "stale",
     "reason": "2 watched path(s) changed since abc123",
     "changed_watched": ["src/a.py", "src/b.py"]},
]
SCORES = [
    {"doc": "agents", "path": "AGENTS.md", "status": "fresh",
     "score": 1.0, "missing_paths": []},
    {"doc": "modules", "path": ".slate/modules.md", "status": "stale",
     "score": 0.62, "missing_paths": ["src/gone.py"]},
]


def test_comment_flags_stale_docs():
    body = pr_comment.build_comment(STATUS, SCORES)
    assert pr_comment.MARKER in body  # idempotency anchor
    assert "1 context doc may be invalidated" in body
    assert "`.slate/modules.md`" in body
    assert "`src/a.py`" in body
    assert "0.62" in body
    assert "`src/gone.py`" in body
    assert "slate sync" in body


def test_comment_all_fresh():
    fresh = [dict(STATUS[0])]
    body = pr_comment.build_comment(fresh, [dict(SCORES[0])])
    assert "All context docs are **fresh**" in body
    assert pr_comment.MARKER in body


def test_comment_truncates_long_change_lists():
    status = [dict(STATUS[1])]
    status[0]["changed_watched"] = [f"src/f{i}.py" for i in range(8)]
    body = pr_comment.build_comment(status, SCORES)
    assert "+5 more" in body
