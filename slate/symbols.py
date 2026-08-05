"""Symbol-level change resolution — which *definitions* a change touched.

The freshness engine narrows a file-granularity signal to a symbol one: given
a changed file and the line ranges that changed inside it, report the set of
top-level definitions (functions, classes, methods, module-level assignments)
whose bodies overlap those ranges. A doc that claims something about
``context.get_auto_block`` should only go stale when *that function's* body
changed — not when a docstring typo two functions over touches the same file.

Two parsers, both deliberately shallow and dependency-free:

- **Python** via the stdlib ``ast`` — exact line spans per definition, so a
  change is attributed to the precise def/class/method it lands in.
- **JS/TS** via regex in the spirit of ``imports.py`` — top-level ``function``/
  ``class``/``const`` declarations, each owning the lines from its declaration
  to the next one.

Every ambiguity resolves *toward* staleness. Anything unparseable returns
``None`` (opaque): the caller treats an opaque file as "every referenced
symbol might have changed", which is always safe. A false "fresh" is the one
catastrophic bug (product doc §10), and this module never risks one — it only
ever *narrows* stale→fresh when it can prove a symbol's lines were untouched.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

Range = tuple[int, int]

_JS_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}

# Top-level JS/TS declarations: function / class / const|let|var NAME. Shallow
# by design — no scope tracking, no method bodies. `imports.py` sets the bar.
_JS_DECL = re.compile(
    r"^[ \t]*(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:function\*?\s+(?P<fn>[A-Za-z_$][\w$]*)"
    r"|class\s+(?P<cls>[A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+(?P<var>[A-Za-z_$][\w$]*))",
    re.M,
)


def changed_symbols(path: Path, ranges: list[Range]) -> set[str] | None:
    """Top-level symbols in ``path`` whose bodies overlap any changed range.

    Returns ``None`` (opaque) when the file can't be read or parsed — the
    conservative fallback the freshness engine reads as "assume touched".
    Names are reported both bare (``method``) and qualified (``Class.method``),
    and an overlapped method also reports its enclosing class, so a claim can
    match whichever form it references.
    """
    try:
        source = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _python_changed(source, ranges)
    if suffix in _JS_SUFFIXES:
        return _js_changed(source, ranges)
    return None  # a code language we can't parse — opaque, so conservative


def _overlaps(ranges: list[Range], start: int, end: int) -> bool:
    return any(r_start <= end and r_end >= start for r_start, r_end in ranges)


def _python_changed(source: str, ranges: list[Range]) -> set[str] | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    defs: list[tuple[list[str], str, Range]] = []
    _collect_python(tree.body, [], defs)
    changed: set[str] = set()
    for stack, name, (start, end) in defs:
        if not _overlaps(ranges, start, end):
            continue
        changed.add(name)
        if stack:
            changed.add(".".join([*stack, name]))
            changed.update(stack)  # the enclosing class(es) changed too
    return changed


def _collect_python(
    body: list[ast.stmt], stack: list[str], out: list[tuple[list[str], str, Range]]
) -> None:
    """Record (enclosing-names, name, line-span) for each definition.

    Recurses into classes (methods, class-level assignments) but not into
    function bodies: a nested helper changing is already attributed to the
    enclosing function via its line span, and locals aren't referenceable as
    ``module.symbol`` anyway.
    """
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((stack, node.name, _span(node)))
        elif isinstance(node, ast.ClassDef):
            out.append((stack, node.name, _span(node)))
            _collect_python(node.body, [*stack, node.name], out)
        elif isinstance(node, ast.Assign):
            span = _span(node)
            for name in _assign_names(node.targets):
                out.append((stack, name, span))
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                out.append((stack, node.target.id, _span(node)))


def _span(node: ast.stmt) -> Range:
    # Include any decorator lines above `lineno` so a decorator edit counts as
    # touching the symbol. end_lineno is always set on parsed statements (3.8+).
    start = node.lineno
    for dec in getattr(node, "decorator_list", []):
        start = min(start, dec.lineno)
    end = node.end_lineno or node.lineno
    return start, end


def _assign_names(targets: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    names.append(elt.id)
    return names


def _js_changed(source: str, ranges: list[Range]) -> set[str] | None:
    """Shallow JS/TS: each top-level declaration owns lines up to the next one.

    No parser, so when the file has changes but yields no recognizable
    declaration we return None (opaque) rather than guess a symbol didn't move.
    """
    decls: list[tuple[str, int]] = []
    for match in _JS_DECL.finditer(source):
        name = match.group("fn") or match.group("cls") or match.group("var")
        line = source.count("\n", 0, match.start()) + 1
        decls.append((name, line))
    if not decls:
        return None
    decls.sort(key=lambda d: d[1])
    total_lines = source.count("\n") + 1
    changed: set[str] = set()
    for index, (name, start) in enumerate(decls):
        end = decls[index + 1][1] - 1 if index + 1 < len(decls) else total_lines
        if _overlaps(ranges, start, end):
            changed.add(name)
    return changed
