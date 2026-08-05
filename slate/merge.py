"""`slate merge` — a git merge driver for the context layer.

Without this, concurrent branches collide in the context layer on every
merge: the documented workflow syncs and commits the docs alongside the
code, and every `slate sync` rewrites the frontmatter anchor plus the
auto-block. Two PRs that touch watched code therefore conflict in all four
generated docs — and the obvious resolution (`git checkout --ours` then
`slate sync`) produces a *correct* auto-block while silently discarding the
other side's hand-written prose. Human edits are first-class (product doc
§4); losing them to a merge is the same class of bug as clobbering them on
sync.

The driver splits the file the same way sync does and treats the halves
differently:

- **generated facts** are not merged at all. Both sides' auto-blocks are
  replaced by a placeholder before the merge and the block is restored
  afterwards, because the block is a pure function of the merged worktree —
  `slate sync` regenerates it correctly no matter which side "won".
- **human text** gets a real 3-way merge (`git merge-file`), so both sides'
  notes survive and a genuine overlap still surfaces conflict markers.

Frontmatter is taken from *ours*, except `slate_watches`, which is unioned
(both sides may have added watches via `slate watches --apply`, and dropping
one silently is the bug above in another costume; a longer watch list is
always the conservative direction).

**Why keeping ours' anchor cannot manufacture a false `fresh`** — the one
bug that would destroy the product's promise (§10). Freshness compares the
anchor's *tree* against the merged worktree (`gitutil.changed_files` uses
`git diff <anchor> HEAD`, not the `anchor..HEAD` range), so any watched path
where the merged tree differs from the anchor is reported as changed, no
matter which branch that difference arrived on or whether the anchor is an
ancestor of HEAD. The only way the merged doc reads `fresh` is if the
watched content genuinely matches the anchor — and if the anchor died in a
squash, `context.watched_digest` is recomputed against the merged tree and
mismatches, which is `stale`. Both fallbacks fail safe; neither can be
talked into vouching for content it never saw.

Installation is two halves with different lifetimes: the `.gitattributes`
lines are committed (team-wide), while `merge.slate.driver` is git config
and therefore per-clone. A teammate who has the attributes but not the
config is not broken — git falls back to its built-in text merge, i.e.
exactly today's behavior. `slate merge status` reports which half is missing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import context, frontmatter, gitutil
from .context import DOC_SPECS
from .frontmatter import Meta

DRIVER = "slate"
DRIVER_CONFIG = f"merge.{DRIVER}.driver"
NAME_CONFIG = f"merge.{DRIVER}.name"
DRIVER_COMMAND = "slate merge run %O %A %B %P"
DRIVER_DESCRIPTION = "slate context layer (human text merged, facts regenerated)"

ATTRIBUTES_FILE = ".gitattributes"
ATTR_BEGIN = "# slate context layer — added by `slate merge install`"
ATTR_END = "# end slate context layer"

# Stands in for the auto-block during the merge so generated facts never
# reach the 3-way merge. Deliberately an HTML comment: if a merge ever went
# so wrong that one leaked into a doc, it renders as nothing.
PLACEHOLDER = "<!-- slate:auto-merge-placeholder -->"


class MergeError(RuntimeError):
    pass


# --- installation -----------------------------------------------------------

def attributes_path(root: Path) -> Path:
    return root / ATTRIBUTES_FILE


def attribute_lines() -> list[str]:
    return [f"{spec.rel_path} merge={DRIVER}" for spec in DOC_SPECS]


def driver_registered(root: Path) -> bool:
    return gitutil.config_get(root, DRIVER_CONFIG) is not None


def attributes_registered(root: Path) -> bool:
    path = attributes_path(root)
    if not path.exists():
        return False
    try:
        return ATTR_BEGIN in path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False


def install(root: Path) -> None:
    """Register the driver in this clone and the attributes in the repo."""
    gitutil.config_set(root, NAME_CONFIG, DRIVER_DESCRIPTION)
    gitutil.config_set(root, DRIVER_CONFIG, DRIVER_COMMAND)
    path = attributes_path(root)
    existing = _read_attributes(path)
    block = [ATTR_BEGIN, *attribute_lines(), ATTR_END]
    kept = _without_slate_block(existing)
    lines = [*kept, *block] if kept else block
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def uninstall(root: Path) -> bool:
    """Remove both halves. Returns False if neither was present."""
    had_driver = gitutil.config_unset(root, DRIVER_CONFIG)
    gitutil.config_unset(root, NAME_CONFIG)
    path = attributes_path(root)
    had_attrs = attributes_registered(root)
    if had_attrs:
        kept = _without_slate_block(_read_attributes(path))
        if kept:
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            # We created the file; leaving an empty one behind is litter.
            path.unlink()
    return had_driver or had_attrs


def _read_attributes(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise MergeError(f"cannot read {path}: {exc}") from exc


def _without_slate_block(lines: list[str]) -> list[str]:
    """Drop our marked block, tolerating a hand-truncated end marker."""
    out: list[str] = []
    inside = False
    for line in lines:
        if line.strip() == ATTR_BEGIN:
            inside = True
            continue
        if inside:
            if line.strip() == ATTR_END:
                inside = False
            # An unterminated block ends at the first line that isn't ours.
            elif line.strip() and line.strip() not in attribute_lines():
                inside = False
                out.append(line)
            continue
        out.append(line)
    while out and not out[-1].strip():
        out.pop()
    return out


# --- the driver itself ------------------------------------------------------

def run(base: Path, ours: Path, theirs: Path, rel_path: str) -> tuple[int, str]:
    """Merge one file. Returns (exit code, message for stderr).

    Exit 0 means git can take the result as merged; non-zero leaves the path
    conflicted, with markers confined to the human-written text.
    """
    spec = context.spec_by_name(rel_path)
    if spec is None or not _all_readable(base, ours, theirs):
        # Not a context doc (or not text we can parse) — plain 3-way merge,
        # exactly what git would have done without us.
        return (1 if gitutil.merge_file(ours, base, theirs) else 0), ""

    o_meta, o_body = frontmatter.parse(ours.read_text(encoding="utf-8"))
    _, base_body = frontmatter.parse(base.read_text(encoding="utf-8"))
    t_meta, t_body = frontmatter.parse(theirs.read_text(encoding="utf-8"))

    auto = context.get_auto_block(o_body)
    if auto is None:
        auto = context.get_auto_block(t_body)

    conflicts = _merge_human_text(
        ours, base_body, o_body, t_body, union=spec.append_only
    )
    merged_human = ours.read_text(encoding="utf-8")

    meta = dict(o_meta)
    _union_watches(meta, o_meta, t_meta)
    ours.write_text(frontmatter.render(meta, _restore(merged_human, auto)),
                    encoding="utf-8")

    if conflicts:
        return 1, (
            f"slate: {rel_path}: conflict in hand-written text — resolve the "
            "markers, then `slate sync`"
        )
    if auto is not None:
        return 0, f"slate: {rel_path}: human text merged; `slate sync` regenerates the facts"
    return 0, f"slate: {rel_path}: human text merged"


def _all_readable(*paths: Path) -> bool:
    for path in paths:
        try:
            path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return False
    return True


def _merge_human_text(
    ours: Path, base_body: str, o_body: str, t_body: str, union: bool = False
) -> int:
    """3-way merge the bodies with the auto-blocks placeheld out.

    Writes the merged human text into ``ours`` (git's result file) and
    returns the conflict count.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_base = Path(tmp) / "base"
        tmp_theirs = Path(tmp) / "theirs"
        tmp_base.write_text(_placehold(base_body), encoding="utf-8")
        tmp_theirs.write_text(_placehold(t_body), encoding="utf-8")
        ours.write_text(_placehold(o_body), encoding="utf-8")
        return gitutil.merge_file(ours, tmp_base, tmp_theirs, union=union)


def _placehold(body: str) -> str:
    """Swap the auto-block for the placeholder; no markers → unchanged."""
    begin = body.find(context.AUTO_BEGIN)
    end = body.find(context.AUTO_END)
    if begin == -1 or end == -1 or end < begin:
        return body
    return body[:begin] + PLACEHOLDER + body[end + len(context.AUTO_END):]


def _restore(body: str, auto: str | None) -> str:
    """Put the auto-block back where the merge left the placeholder."""
    if auto is None:
        return body
    block = f"{context.AUTO_BEGIN}\n{auto.strip()}\n{context.AUTO_END}"
    if PLACEHOLDER not in body:
        # Both sides lost their markers, or a conflict swallowed the
        # placeholder: append rather than clobber (same rule as sync).
        return context.replace_auto_block(body, auto)
    head, _, tail = body.partition(PLACEHOLDER)
    return head + block + tail.replace(PLACEHOLDER, "")


def _union_watches(meta: Meta, ours: Meta, theirs: Meta) -> None:
    """Keep every watch either side had — never narrow the watch set."""
    a, b = _watch_list(ours), _watch_list(theirs)
    if not a and not b:
        return
    merged = a + [w for w in b if w not in a]
    meta["slate_watches"] = merged  # assignment keeps the key's position


def _watch_list(meta: Meta) -> list[str]:
    value = meta.get("slate_watches")
    if value is None:
        return []
    return list(value) if isinstance(value, list) else [str(value)]
