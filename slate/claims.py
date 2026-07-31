"""Claim segmentation — the human body units that carry code references.

Part A resolved *which symbol* a change touched. Part B attributes that to
*which claim*: a body unit (a bullet, a table row, a paragraph, a heading)
that names a code path or a ``module.symbol``. Claims are re-derived from the
body on every evaluation, exactly like ``refs.py`` — nothing is persisted in
frontmatter.

Only the human-owned prose is segmented here. Auto-block facts are claims too,
but their verdict is a line-level diff against a fresh scan, which the
freshness engine owns; this module never reaches inside the generated block.

Completeness matters for the trust path: every non-blank human line lands in
exactly one unit, so the union of the units' references equals the references
of the whole human text. A claim the segmenter dropped could otherwise let a
changed symbol pass unnoticed — so the walk below is deliberately total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import context
from .refs import extract_path_refs, extract_symbol_refs

_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_ROW = re.compile(r"^\s*\|")


@dataclass
class Claim:
    text: str
    section: str
    path_refs: list[str] = field(default_factory=list)
    symbol_refs: list[str] = field(default_factory=list)
    line: int = 0      # 1-based start line in the body
    end_line: int = 0  # 1-based last line in the body (== line for one-liners)

    @property
    def refs(self) -> list[str]:
        return [*self.path_refs, *self.symbol_refs]

    @property
    def lines(self) -> list[int]:
        return list(range(self.line, max(self.line, self.end_line) + 1))


def human_claims(body: str) -> list[Claim]:
    """Every human body unit that carries at least one code reference."""
    skip = _auto_block_lines(body)
    lines = body.splitlines()
    claims: list[Claim] = []
    section = ""
    buffer: list[str] = []
    buffer_start = 0

    def flush() -> None:
        nonlocal buffer, buffer_start
        if buffer:
            text = " ".join(part.strip() for part in buffer).strip()
            _emit(claims, text, section, buffer_start, buffer_start + len(buffer) - 1)
            buffer = []

    for index, line in enumerate(lines):
        lineno = index + 1
        if index in skip:
            flush()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            section = heading.group(2).strip()
            _emit(claims, section, section, lineno)  # a heading may name code too
            continue
        if not line.strip():
            flush()
            continue
        if _BULLET.match(line) or _TABLE_ROW.match(line):
            flush()
            buffer, buffer_start = [line], lineno
            # A bullet/row is a unit on its own; a following indented line
            # continues it, a following bullet/blank starts fresh (handled above).
            continue
        if not buffer:
            buffer_start = lineno
        buffer.append(line)
    flush()
    return claims


def _emit(
    claims: list[Claim], text: str, section: str, line: int, end_line: int | None = None
) -> None:
    if not text:
        return
    path_refs = extract_path_refs(text)
    symbol_refs = extract_symbol_refs(text)
    if path_refs or symbol_refs:
        claims.append(
            Claim(text, section, path_refs, symbol_refs, line, end_line or line)
        )


def _auto_block_lines(body: str) -> set[int]:
    """0-based line indices covered by the generated block (markers included)."""
    lines = body.splitlines()
    begin = end = None
    for index, line in enumerate(lines):
        if context.AUTO_BEGIN in line:
            begin = index
        if context.AUTO_END in line:
            end = index
    if begin is None or end is None or end < begin:
        return set()
    return set(range(begin, end + 1))
