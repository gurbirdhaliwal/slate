"""Render the slate lockup (mark + wordmark) as ANSI half-block art.

The mark is rasterized at runtime from the same five facet triangles as
slate-mark.svg, so the terminal banner and the brand asset can't drift.
Each terminal cell holds two vertically stacked "subpixels" via the upper
half block (U+2580); facet opacity maps onto the xterm-256 grayscale ramp,
matching the light-gem-on-dark tonal order of slate-icon.png.

The wordmark is a bitmap traced from slate-lockup-sora-white.png (Sora,
lowercase). It renders in the terminal's default foreground color so it
stays legible on both light and dark themes.
"""

from __future__ import annotations

import os
import sys

from . import __version__

# ((vertices), opacity) — verbatim from slate-mark.svg
_FACETS = [
    (((40, 16), (43.4, 38), (19.6, 43)), 0.62),
    (((40, 16), (55, 31), (43.4, 38)), 1.0),
    (((55, 31), (48.4, 61), (43.4, 38)), 0.80),
    (((43.4, 38), (48.4, 61), (31.6, 57.6)), 0.45),
    (((19.6, 43), (43.4, 38), (31.6, 57.6)), 0.28),
]

# bounding box of the mark in SVG user units
_X0, _X1 = 19.6, 55.0
_Y0, _Y1 = 16.0, 61.0

_COLS = 12       # cells wide
_SUBROWS = 16    # subpixels tall (two per terminal row)
_SS = 6          # supersample grid per subpixel

_RESET = "\x1b[0m"

# "slate" wordmark, traced from slate-lockup-sora-white.png (36x12 subpixels)
_WORD = (
    "        ###            #",
    "        ###           ###",
    "         ##           ###",
    " #####   ##  ######  ######   #####",
    "#######  ##   ###### ######  #######",
    "###   #  ##       ##  ###   ##    ##",
    " ####    ##    #####  ###   ########",
    " ######  ##  #######  ###   ########",
    "     ### ##  ##   ##  ###   ##",
    "##   ### ##  ##   ##  ###   ###   ##",
    "#######  ##  #######   ####  #######",
    "  ####   ##   #### #    ###   #####",
)


def _gray(opacity: float) -> int:
    # xterm grayscale ramp runs 232 (near black) .. 255 (near white)
    return 236 + round(opacity * 19)


def _facet_at(x: float, y: float) -> float | None:
    for verts, opacity in _FACETS:
        (ax, ay), (bx, by), (cx, cy) = verts
        d1 = (x - bx) * (ay - by) - (ax - bx) * (y - by)
        d2 = (x - cx) * (by - cy) - (bx - cx) * (y - cy)
        d3 = (x - ax) * (cy - ay) - (cx - ax) * (y - ay)
        neg = d1 < 0 or d2 < 0 or d3 < 0
        pos = d1 > 0 or d2 > 0 or d3 > 0
        if not (neg and pos):
            return opacity
    return None


def _subpixel(col: int, subrow: int) -> float | None:
    """Mean facet opacity over an _SS x _SS sample grid; None if <50% covered."""
    hit, total = 0, 0.0
    for sy in range(_SS):
        for sx in range(_SS):
            u = (col + (sx + 0.5) / _SS) / _COLS
            v = (subrow + (sy + 0.5) / _SS) / _SUBROWS
            opacity = _facet_at(_X0 + u * (_X1 - _X0), _Y0 + v * (_Y1 - _Y0))
            if opacity is not None:
                hit += 1
                total += opacity
    if hit * 2 < _SS * _SS:
        return None
    return total / hit


def mark_cells() -> list[list[tuple[int | None, int | None]]]:
    """The gem as rows of (top_gray, bot_gray) xterm-256 codes per cell.

    One row per terminal line, one tuple per column; None means that half
    of the cell is empty. Shared by the ANSI banner and the curses UI.
    """
    rows = []
    for row in range(_SUBROWS // 2):
        cells = []
        for col in range(_COLS):
            top = _subpixel(col, 2 * row)
            bot = _subpixel(col, 2 * row + 1)
            cells.append((
                None if top is None else _gray(top),
                None if bot is None else _gray(bot),
            ))
        rows.append(cells)
    return rows


def _mark_lines() -> list[str]:
    lines = []
    for cells in mark_cells():
        out = []
        for top, bot in cells:
            if top is None and bot is None:
                out.append(" ")
            elif bot is None:
                out.append(f"\x1b[38;5;{top}m▀{_RESET}")
            elif top is None:
                out.append(f"\x1b[38;5;{bot}m▄{_RESET}")
            else:
                out.append(f"\x1b[38;5;{top};48;5;{bot}m▀{_RESET}")
        lines.append("".join(out).rstrip())
    return lines


def supports_color(stream=None) -> bool:
    stream = stream if stream is not None else sys.stdout
    if os.environ.get("NO_COLOR"):
        return False
    term = os.environ.get("TERM", "")
    if "256" not in term and not os.environ.get("COLORTERM"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def word_lines() -> list[str]:
    """Wordmark as half-block rows in the terminal's default foreground."""
    lines = []
    for y in range(0, len(_WORD) - 1, 2):
        top, bot = _WORD[y], _WORD[y + 1]
        width = max(len(top), len(bot))
        line = []
        for x in range(width):
            t = x < len(top) and top[x] == "#"
            b = x < len(bot) and bot[x] == "#"
            line.append("█" if t and b else "▀" if t else "▄" if b else " ")
        lines.append("".join(line).rstrip())
    return lines


def banner() -> str:
    """The slate lockup with tagline, or "" when colors are unwelcome."""
    if not supports_color():
        return ""
    lines = [f"  {line}" for line in _mark_lines()]
    text_col = _COLS + 7
    word = word_lines()
    word_top = (len(lines) - len(word)) // 2
    captions = {word_top + i: line for i, line in enumerate(word)}
    captions[word_top + len(word)] = (
        f"\x1b[2mv{__version__} · context control plane for AI-assisted repos\x1b[0m"
    )
    for i, caption in captions.items():
        gap = " " * max(1, text_col - _visible_len(lines[i]))
        lines[i] = f"{lines[i]}{gap}{caption}"
    return "\n".join(lines) + "\n"


def _visible_len(line: str) -> int:
    out, i, n = 0, 0, len(line)
    while i < n:
        if line[i] == "\x1b":
            i = line.index("m", i) + 1
        else:
            out += 1
            i += 1
    return out
