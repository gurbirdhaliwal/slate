"""Interactive dashboard for slate (`slate ui`, or bare `slate` in a TTY).

Built on the stdlib ``curses`` module — no third-party dependencies. This
module is imported lazily by the CLI so scripted commands (`status --ci`,
hooks, MCP) never pay for it.

Every slate feature is reachable here: six views (docs · verify · read ·
watches · agent · fleet, keys 1-6 or tab), a welcome screen that runs
`init` in repos without a context layer, and actions for sync (plain or
LLM-prose), mark, watch proposals, the pre-push hook, MCP client wiring
and the agent access ceiling. Press ? inside the app for the reference.
Only running the MCP server itself (`slate mcp`) and CI plumbing
(`--ci`/`--json`) stay on the command line — those exist for machines.
"""

from __future__ import annotations

import curses
import os
from pathlib import Path

from . import (
    __version__,
    agentcfg,
    banner,
    context,
    diffs,
    freshness,
    generator,
    gitutil,
    hooks,
    imports as imports_mod,
    scanner,
    verify,
)
from .context import DOC_SPECS, FRESH, NEEDS_VERIFICATION, STALE

_ICONS = {FRESH: "●", STALE: "○", NEEDS_VERIFICATION: "◐"}

_VIEWS = ("docs", "verify", "read", "watches", "agent", "fleet")

_TAIL = "1-6 views  ? help  q quit"
_KEYBARS = {
    "docs": f" ↑↓ move  ⏎ detail  s/S sync  m mark  H hook  {_TAIL}",
    "verify": f" ↑↓ move  ⏎ detail  s/S sync  m mark  {_TAIL}",
    "read": f" ↑↓ move  ⏎ detail  s/S sync  m mark  {_TAIL}",
    "watches": f" ↑↓ move  ⏎ detail  a apply  A apply all  {_TAIL}",
    "agent": f" ↑↓ move  e enable client  x toggle access  {_TAIL}",
    "fleet": f" ↑↓ move  o open repo  r rescan  {_TAIL}",
}

_MCP_READ_TOOLS = "slate_read · slate_status · slate_verify · slate_diff · slate_watches"
_MCP_WRITE_TOOLS = "slate_sync · slate_mark · slate_update_focus · slate_append_decision"

_HELP = [
    ("views (1-6, or tab to cycle)", None),
    ("  1 docs", "freshness of every doc, diff detail (slate status / diff)"),
    ("  2 verify", "verification score per doc, broken references (slate verify)"),
    ("  3 read", "the ordered first-read path for an AI session (slate read)"),
    ("  4 watches", "watch globs per doc, proposed additions (slate watches)"),
    ("  5 agent", "MCP wiring and the agent access ceiling (slate agent)"),
    ("  6 fleet", "freshness roll-up across sibling repos (slate fleet)"),
    ("", None),
    ("keys", None),
    ("  ↑/↓  j/k", "select · ⏎/d toggle detail · r refresh · q quit"),
    ("  s / S", "sync selected doc / every generated doc"),
    ("  P", "sync all with an LLM prose pass (needs ANTHROPIC_API_KEY)"),
    ("  m", "mark the selected human-owned doc accurate at HEAD"),
    ("  a / A", "watches: apply proposed watches (selected / all docs)"),
    ("  e  x", "agent: wire the selected client · toggle read-only/full"),
    ("  o", "fleet: open the selected repo in this dashboard"),
    ("  H", "install or remove the pre-push freshness gate (slate hook)"),
    ("  i", "welcome screen: initialize the context layer (slate init)"),
    ("", None),
    ("status", None),
    ("  ● fresh", "anchored at HEAD; the doc's claims check out"),
    ("  ○ stale", "watched paths changed since the doc's anchor"),
    ("  ◐ needs-verification", "freshness can't be proven — review, then sync or mark"),
    ("", None),
    ("agents (mcp)", None),
    ("  wire up", "view 5 · e — writes .mcp.json / .cursor/mcp.json (slate agent enable)"),
    ("  read tools", _MCP_READ_TOOLS),
    ("  write tools", f"{_MCP_WRITE_TOOLS} (need access: full)"),
    ("", None),
    ("automation stays on the cli", None),
    ("  slate mcp", "run the MCP server over stdio (editors launch this)"),
    ("  slate status --ci · fleet --ci", "exit 1 on freshness problems; --json everywhere"),
]


class _App:
    def __init__(self, root: Path, reports: list[freshness.DocReport]):
        self.root = root
        self.reports = reports
        self.view = "docs"
        self.sel = 0
        self.msg = ""
        self.show_detail = True
        self.show_help = False
        self._scan = None
        self._edges = None
        self._diffs: dict[str, diffs.DocDiff] = {}
        self._suggestions: dict[str, list] = {}
        self._verify: list[verify.Verification] | None = None
        self._fleet: list[dict] | None = None

    # --- data ---------------------------------------------------------

    def refresh(self) -> None:
        self.reports = freshness.evaluate_all(self.root)
        self._scan = None
        self._edges = None
        self._diffs = {}
        self._suggestions = {}
        self._verify = None
        self.clamp_sel()

    def clamp_sel(self) -> None:
        self.sel = min(self.sel, max(0, len(self.rows()) - 1))

    def scan(self):
        if self._scan is None:
            self._scan = scanner.scan(self.root)
        return self._scan

    def diff_for(self, report: freshness.DocReport) -> diffs.DocDiff:
        name = report.doc.spec.name
        if name not in self._diffs:
            self._diffs[name] = diffs.doc_diff(self.root, report.doc, self.scan())
        return self._diffs[name]

    def verify_results(self) -> list[verify.Verification]:
        if self._verify is None:
            self._verify = verify.verify_all(self.root)
        return self._verify

    def read_reports(self) -> list[tuple[int, freshness.DocReport]]:
        by_name = {r.doc.spec.name: r for r in self.reports}
        ordered = sorted(
            (s for s in DOC_SPECS if s.read_order and s.name in by_name),
            key=lambda s: s.read_order,
        )
        return [(i + 1, by_name[s.name]) for i, s in enumerate(ordered)]

    def suggestions_for(self, report: freshness.DocReport) -> list:
        name = report.doc.spec.name
        if name not in self._suggestions:
            if self._edges is None:
                self._edges = imports_mod.import_edges(self.scan())
            self._suggestions[name] = imports_mod.suggest(
                self.root, report.doc, self.scan(), self._edges)
        return self._suggestions[name]

    def agent_rows(self) -> list[tuple[str, str, bool]]:
        wired = set(agentcfg.enabled_clients(self.root))
        return [(client, cfg, client in wired)
                for client, cfg in sorted(agentcfg.CLIENTS.items())]

    def fleet_rows(self) -> list[dict]:
        if self._fleet is None:
            rows = []
            for repo in gitutil.fleet_roots([self.root.parent]):
                reports = freshness.evaluate_all(repo)
                counts = {FRESH: 0, STALE: 0, NEEDS_VERIFICATION: 0}
                for r in reports:
                    counts[r.status] += 1
                rows.append({
                    "repo": repo,
                    "layer": bool(reports),
                    "fresh": counts[FRESH],
                    "stale": counts[STALE],
                    "needs": counts[NEEDS_VERIFICATION],
                })
            self._fleet = rows
        return self._fleet

    def rows(self) -> list:
        if self.view == "verify":
            return self.verify_results()
        if self.view == "read":
            return self.read_reports()
        if self.view == "agent":
            return self.agent_rows()
        if self.view == "fleet":
            return self.fleet_rows()
        return self.reports

    def selected_report(self) -> freshness.DocReport | None:
        if self.view in ("agent", "fleet"):
            return None
        rows = self.rows()
        if not rows:
            return None
        row = rows[self.sel]
        if self.view == "verify":
            return row.report
        if self.view == "read":
            return row[1]
        return row

    # --- actions ------------------------------------------------------

    def init_layer(self) -> None:
        scan = scanner.scan(self.root)
        written = generator.generate_all(scan, force=False)
        self.msg = f"initialized {len(written)} doc(s) — fill in the human sections, then commit"
        self.refresh()

    def sync_selected(self) -> None:
        report = self.selected_report()
        if report is None:
            return
        generator.sync_doc(report.doc, self.scan())
        self.msg = f"synced {report.rel_path}"
        self.refresh()

    def sync_all(self, prose: bool = False) -> None:
        writer = None
        if prose:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                self.msg = "error: prose sync needs ANTHROPIC_API_KEY in the environment"
                return
            from . import llm  # imported only on the opt-in path
            writer = llm.prose_writer(api_key)
        scan = self.scan()
        synced = 0
        for report in self.reports:
            if report.doc.spec.generated:
                generator.sync_doc(report.doc, scan, prose=writer)
                synced += 1
        self.msg = f"synced {synced} generated doc(s)" + (" with prose" if prose else "")
        self.refresh()

    def mark_selected(self) -> None:
        report = self.selected_report()
        if report is None:
            return
        commit = gitutil.head_commit(self.root)
        context.stamp(self.root, report.doc, commit)
        context.save(self.root, report.doc)
        self.msg = f"marked {report.rel_path} at {commit[:7] if commit else 'HEAD'}"
        self.refresh()

    def apply_watches(self, everything: bool = False) -> None:
        targets = self.reports if everything else [self.selected_report()]
        applied = 0
        for report in targets:
            if report is None:
                continue
            suggestions = self.suggestions_for(report)
            if suggestions:
                doc = report.doc
                doc.meta["slate_watches"] = doc.watches + [s.pattern for s in suggestions]
                context.save(self.root, doc)
                applied += len(suggestions)
        self.msg = f"applied {applied} watch(es)" if applied else "no proposed watches"
        if applied:
            self.refresh()

    def toggle_hook(self) -> None:
        path = hooks.hook_path(self.root)
        if path.exists() and hooks.is_ours(path):
            hooks.uninstall(self.root)
            self.msg = "pre-push hook removed"
        else:
            try:
                hooks.install(self.root)
                self.msg = "pre-push hook installed"
            except hooks.HookError as exc:
                self.msg = f"error: {exc}"

    def hook_installed(self) -> bool:
        path = hooks.hook_path(self.root)
        return path.exists() and hooks.is_ours(path)

    def enable_selected_client(self) -> None:
        if self.view != "agent":
            return
        client, _, wired = self.rows()[self.sel]
        if wired:
            self.msg = f"{client} is already wired"
            return
        rel = agentcfg.enable_client(self.root, client)
        self.msg = f"wired {client}: wrote {rel} — restart that editor session"

    def toggle_access(self) -> None:
        mode = agentcfg.get_access(self.root)
        new = agentcfg.FULL if mode != agentcfg.FULL else agentcfg.READ
        agentcfg.set_access(self.root, new)
        self.msg = f"agent access set to {new} (.slate/agent-access is the committed policy)"

    def open_fleet_repo(self) -> None:
        if self.view != "fleet":
            return
        row = self.rows()[self.sel]
        if not row["layer"]:
            self.msg = f"{row['repo'].name} has no context layer — open it and press i"
        self.root = row["repo"]
        self.view = "docs"
        self.sel = 0
        self._fleet = None
        self.refresh()
        if not self.msg:
            self.msg = f"opened {self.root.name}"


class _Grays:
    """Lazily allocated curses color pairs for the gem's grayscale cells."""

    def __init__(self):
        self.ok = curses.has_colors() and curses.COLORS >= 256
        self._pairs: dict[tuple[int, int], int] = {}
        self._next = 16  # leave room for the status pairs

    def attr(self, fg: int, bg: int | None) -> int:
        if not self.ok:
            return 0
        key = (fg, -1 if bg is None else bg)
        if key not in self._pairs:
            if self._next >= curses.COLOR_PAIRS - 1:
                return 0
            curses.init_pair(self._next, key[0], key[1])
            self._pairs[key] = self._next
            self._next += 1
        return curses.color_pair(self._pairs[key])


def _put(scr, y: int, x: int, text: str, attr: int = 0) -> None:
    """addstr clipped to the window; never raises at the right edge."""
    h, w = scr.getmaxyx()
    if 0 <= y < h and x < w:
        try:
            scr.addstr(y, x, text[: max(0, w - x - 1)], attr)
        except curses.error:
            pass


def _status_attr(status: str) -> int:
    pair = {FRESH: 1, NEEDS_VERIFICATION: 2, STALE: 3}.get(status, 0)
    return curses.color_pair(pair)


_lockup_cache: tuple[list, list] | None = None


def _lockup() -> tuple[list, list]:
    global _lockup_cache
    if _lockup_cache is None:
        _lockup_cache = (banner.mark_cells(), banner.word_lines())
    return _lockup_cache


def _draw_header(scr, app: _App, grays: _Grays, rows: int) -> int:
    """Draw the header; return the row where the content below starts."""
    h, w = scr.getmaxyx()
    mark, word = _lockup()
    lockup_h = len(mark)  # 8 rows
    roomy = h >= lockup_h + rows + 10 and w >= 62 and grays.ok

    repo = str(app.root)
    home = str(Path.home())
    if repo.startswith(home):
        repo = "~" + repo[len(home):]
    wiring = f"access {agentcfg.get_access(app.root)} · hook {'✓' if app.hook_installed() else '—'}"

    if not roomy:
        _put(scr, 0, 1, "slate", curses.A_BOLD)
        _put(scr, 0, 7, f"v{__version__} · context control plane", curses.A_DIM)
        _put(scr, 0, max(40, w - len(repo) - 1), repo, curses.A_DIM)
        scr.hline(1, 0, curses.ACS_HLINE, w)
        return 2

    for r, cells in enumerate(mark):
        for c, (top, bot) in enumerate(cells):
            if top is None and bot is None:
                continue
            if bot is None:
                _put(scr, r, 2 + c, "▀", grays.attr(top, None))
            elif top is None:
                _put(scr, r, 2 + c, "▄", grays.attr(bot, None))
            else:
                _put(scr, r, 2 + c, "▀", grays.attr(top, bot))
    word_top = (lockup_h - len(word)) // 2
    for i, line in enumerate(word):
        _put(scr, word_top + i, 19, line)
    _put(scr, word_top + len(word), 19,
         f"v{__version__} · context control plane for AI-assisted repos",
         curses.A_DIM)
    _put(scr, 0, max(20, w - len(repo) - 1), repo, curses.A_DIM)
    _put(scr, 1, max(20, w - len(wiring) - 1), wiring, curses.A_DIM)
    scr.hline(lockup_h, 0, curses.ACS_HLINE, w)
    return lockup_h + 1


def _draw_tabs(scr, app: _App, y: int) -> int:
    x = 1
    for i, view in enumerate(_VIEWS, 1):
        label = f" {i} {view} "
        attr = curses.A_REVERSE if view == app.view else curses.A_DIM
        _put(scr, y, x, label, attr)
        x += len(label) + 1
    return y + 1


def _score_bar(score: float, width: int = 10) -> str:
    filled = round(score * width)
    return "█" * filled + "░" * (width - filled)


def _ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n if n < 20 else n % 10, "th")
    return f"{n}{suffix}"


def _detail_lines(app: _App) -> list[tuple[str, int]]:
    if app.view == "agent":
        client, cfg, wired = app.rows()[app.sel]
        mode = agentcfg.get_access(app.root)
        lines = [
            (f"{client} — {'wired via ' + cfg if wired else 'not wired (e to enable)'}",
             _status_attr(FRESH) if wired else curses.A_DIM),
            (f"  access ceiling: {mode}  (x toggles; the client still prompts per tool call)",
             curses.A_BOLD if mode == agentcfg.FULL else 0),
            (f"  read tools:  {_MCP_READ_TOOLS}", curses.A_DIM),
            (f"  write tools: {_MCP_WRITE_TOOLS} — exposed only with access full", curses.A_DIM),
            ("  the editor launches `slate mcp` itself once wired; restart the session after changes",
             curses.A_DIM),
        ]
        return lines

    if app.view == "fleet":
        row = app.rows()[app.sel]
        if not row["layer"]:
            return [(str(row["repo"]), 0),
                    ("  no context layer — o opens it here, then i initializes", curses.A_DIM)]
        healthy = row["stale"] + row["needs"] == 0
        return [
            (str(row["repo"]), _status_attr(FRESH if healthy else STALE)),
            (f"  fresh {row['fresh']} · stale {row['stale']} · needs-verification {row['needs']}", 0),
            ("  o opens this repo in the dashboard", curses.A_DIM),
        ]

    report = app.selected_report()
    if report is None:
        return []
    lines: list[tuple[str, int]] = []
    head_attr = _status_attr(report.status)

    if app.view == "verify":
        v = app.rows()[app.sel]
        lines.append((f"{report.rel_path} [{report.status}] — score {v.score:.2f}", head_attr))
        lines.append((f"  {v.referenced} referenced path(s), {len(v.missing)} missing",
                      curses.A_DIM))
        for ref in v.missing:
            lines.append((f"    ✗ references missing path: {ref}", _status_attr(STALE)))
        if not v.missing:
            lines.append(("  every path this doc references exists", curses.A_DIM))
        return lines

    if app.view == "read":
        order, _ = app.rows()[app.sel]
        lines.append((f"{report.rel_path} [{report.status}] — read {_ordinal(order)}", head_attr))
        lines.append((f"  {report.doc.spec.title}", 0))
        lines.append((f"  {report.reason}", curses.A_DIM))
        return lines

    if app.view == "watches":
        lines.append((f"{report.rel_path} [{report.status}]", head_attr))
        watches = report.doc.watches
        if watches:
            lines.append(("  watches:", curses.A_BOLD))
            for pattern in watches:
                lines.append((f"    {pattern}", 0))
        else:
            lines.append(("  no watch globs — freshness is attestation-based", curses.A_DIM))
        try:
            suggestions = app.suggestions_for(report)
        except Exception as exc:
            lines.append((f"  proposals unavailable: {exc}", curses.A_DIM))
            return lines
        if suggestions:
            lines.append(("  proposed (a to apply):", curses.A_BOLD))
            for s in suggestions:
                lines.append((f"    + {s.pattern}  — {s.reason}", _status_attr(NEEDS_VERIFICATION)))
        else:
            lines.append(("  no proposed additions", curses.A_DIM))
        return lines

    # docs view
    lines.append((f"{report.rel_path} [{report.status}] — {report.reason}", head_attr))
    try:
        d = app.diff_for(report)
    except Exception as exc:
        lines.append((f"  diff unavailable: {exc}", curses.A_DIM))
        return lines
    if d.changes:
        lines.append(("  watched changes:", curses.A_BOLD))
        for path, kind in d.changes.items():
            lines.append((f"    {kind}  {path}", 0))
    if d.suspect_claims:
        lines.append(("  claims at risk:", curses.A_BOLD))
        for c in d.suspect_claims:
            text = c.text if len(c.text) <= 66 else c.text[:65] + "…"
            marker = "?" if c.status == freshness.CLAIM_UNKNOWABLE else "✗"
            attr = _status_attr(NEEDS_VERIFICATION if c.status == freshness.CLAIM_UNKNOWABLE else STALE)
            lines.append((f"    {marker} {text}", attr))
            if c.risk:
                lines.append((f"        risk: {', '.join(c.risk)}", curses.A_DIM))
    if d.missing_refs:
        lines.append(("  broken claims (paths that no longer exist):", curses.A_BOLD))
        for ref in d.missing_refs:
            lines.append((f"    ✗ {ref}", _status_attr(STALE)))
    if d.sync_preview:
        lines.append(("  what sync would change:", curses.A_BOLD))
        for line in d.sync_preview:
            lines.append((f"    {line}", curses.A_DIM))
    if len(lines) == 1:
        if report.status == FRESH:
            lines.append(("  nothing to do", curses.A_DIM))
        elif report.doc.spec.generated:
            lines.append(("  auto-block matches a fresh scan — sync would just re-anchor",
                          curses.A_DIM))
        else:
            lines.append(("  human-owned doc — review it, then mark (m)", curses.A_DIM))
    return lines


def _draw_row(scr, app: _App, y: int, w: int, i: int) -> None:
    attr = curses.A_REVERSE if i == app.sel else 0
    _put(scr, y, 0, " " * (w - 1), attr)
    row = app.rows()[i]

    if app.view == "verify":
        r = row.report
        _put(scr, y, 1, _ICONS[r.status], attr | _status_attr(r.status))
        width = max(len(x.report.rel_path) for x in app.rows()) + 2
        _put(scr, y, 3, f"{r.rel_path:<{width}}", attr)
        _put(scr, y, 3 + width, f"{row.score:.2f} ", attr)
        _put(scr, y, 3 + width + 5, _score_bar(row.score), attr | _status_attr(r.status))
        if row.missing:
            _put(scr, y, 3 + width + 17, f"{len(row.missing)} missing ref(s)", attr | curses.A_DIM)
        return

    if app.view == "read":
        order, r = row
        width = max(len(x[1].rel_path) for x in app.rows()) + 2
        _put(scr, y, 1, f"{order}.", attr)
        _put(scr, y, 4, _ICONS[r.status], attr | _status_attr(r.status))
        _put(scr, y, 6, f"{r.rel_path:<{width}}", attr)
        _put(scr, y, 6 + width, r.doc.spec.title, attr | curses.A_DIM)
        return

    if app.view == "watches":
        r = row
        width = max(len(x.rel_path) for x in app.rows()) + 2
        _put(scr, y, 1, _ICONS[r.status], attr | _status_attr(r.status))
        _put(scr, y, 3, f"{r.rel_path:<{width}}", attr)
        n = len(r.doc.watches)
        summary = f"{n} watch glob(s)" if n else "attestation-based"
        _put(scr, y, 3 + width, summary, attr | curses.A_DIM)
        return

    if app.view == "agent":
        client, cfg, wired = row
        mark = "✓" if wired else "—"
        _put(scr, y, 1, mark, attr | (_status_attr(FRESH) if wired else curses.A_DIM))
        _put(scr, y, 3, f"{client:<10}", attr)
        _put(scr, y, 13, cfg, attr | curses.A_DIM)
        _put(scr, y, 13 + max(len(c) for _, c in agentcfg.CLIENTS.items()) + 3,
             "wired" if wired else "not wired — e to enable", attr | curses.A_DIM)
        return

    if app.view == "fleet":
        r = row
        width = max(len(x["repo"].name) for x in app.rows()) + 2
        if not r["layer"]:
            _put(scr, y, 1, "·", attr | curses.A_DIM)
            _put(scr, y, 3, f"{r['repo'].name:<{width}}", attr)
            _put(scr, y, 3 + width, "no context layer", attr | curses.A_DIM)
            return
        healthy = r["stale"] + r["needs"] == 0
        icon = "●" if healthy else "○"
        _put(scr, y, 1, icon, attr | _status_attr(FRESH if healthy else STALE))
        _put(scr, y, 3, f"{r['repo'].name:<{width}}", attr)
        _put(scr, y, 3 + width,
             f"fresh {r['fresh']} · stale {r['stale']} · needs-verification {r['needs']}",
             attr | (0 if healthy else curses.A_BOLD))
        return

    r = row
    width = max(len(x.rel_path) for x in app.rows()) + 2
    _put(scr, y, 1, _ICONS[r.status], attr | _status_attr(r.status))
    _put(scr, y, 3, f"{r.rel_path:<{width}}", attr)
    _put(scr, y, 3 + width, f"{r.status:<20}", attr | _status_attr(r.status))
    _put(scr, y, 3 + width + 20, r.reason, attr | curses.A_DIM)


def _draw_welcome(scr, app: _App, grays: _Grays) -> None:
    scr.erase()
    h, w = scr.getmaxyx()
    y = _draw_header(scr, app, grays, rows=0)
    _put(scr, y + 1, 2, "no context layer in this repo yet", curses.A_BOLD)
    _put(scr, y + 3, 2, "slate init writes AGENTS.md and .slate/ — a small set of Markdown", 0)
    _put(scr, y + 4, 2, "docs (architecture, modules, workflows, decisions, read-next) that", 0)
    _put(scr, y + 5, 2, "AI sessions read first, with freshness anchored to git.", 0)
    _put(scr, y + 7, 2, "i", curses.A_BOLD)
    _put(scr, y + 7, 5, "initialize the context layer now", 0)
    _put(scr, y + 8, 2, "q", curses.A_BOLD)
    _put(scr, y + 8, 5, "quit", 0)
    if app.msg:
        _put(scr, h - 1, 1, app.msg, curses.A_BOLD)
    scr.refresh()


def _draw_help(scr, app: _App, grays: _Grays) -> None:
    scr.erase()
    h, w = scr.getmaxyx()
    if h < 10 or w < 44:
        _put(scr, 0, 0, "terminal too small for slate ui — q quits")
        scr.refresh()
        return
    y = _draw_header(scr, app, grays, rows=len(_HELP))
    for label, desc in _HELP:
        if y >= h - 2:
            _put(scr, y - 1, 1, "  … (enlarge the terminal for the rest)", curses.A_DIM)
            break
        if desc is None:
            _put(scr, y, 1, label, curses.A_BOLD if label and not label.startswith(" ") else 0)
        else:
            _put(scr, y, 1, f"{label:<32}", 0)
            _put(scr, y, 34, desc, curses.A_DIM)
        y += 1
    scr.hline(h - 2, 0, curses.ACS_HLINE, w)
    _put(scr, h - 1, 1, "any key to return · q quit", curses.A_DIM)
    scr.refresh()


def _draw(scr, app: _App, grays: _Grays) -> None:
    if not app.reports:
        _draw_welcome(scr, app, grays)
        return
    if app.show_help:
        _draw_help(scr, app, grays)
        return
    scr.erase()
    h, w = scr.getmaxyx()
    if h < 12 or w < 44:
        _put(scr, 0, 0, "terminal too small for slate ui — q quits")
        scr.refresh()
        return

    rows = app.rows()
    top = _draw_header(scr, app, grays, rows=len(rows))
    top = _draw_tabs(scr, app, top)

    for i in range(len(rows)):
        _draw_row(scr, app, top + i, w, i)
    if not rows:
        _put(scr, top, 1, "nothing here", curses.A_DIM)

    footer_y = h - 1
    if app.show_detail and rows:
        sep_y = top + len(rows)
        scr.hline(sep_y, 0, curses.ACS_HLINE, w)
        avail = footer_y - sep_y - 2
        lines = _detail_lines(app)
        for j, (text, attr) in enumerate(lines[:avail]):
            _put(scr, sep_y + 1 + j, 1, text, attr)
        if len(lines) > avail > 0:
            _put(scr, sep_y + avail, 1, f"  … {len(lines) - avail} more", curses.A_DIM)

    scr.hline(footer_y - 1, 0, curses.ACS_HLINE, w)
    keybar = _KEYBARS[app.view]
    if app.msg:
        _put(scr, footer_y, 1, app.msg, curses.A_BOLD)
        _put(scr, footer_y, max(len(app.msg) + 3, w - len(keybar) - 1), keybar, curses.A_DIM)
    else:
        _put(scr, footer_y, 0, keybar, curses.A_DIM)
    scr.refresh()


def _notice(scr, text: str) -> None:
    h, _ = scr.getmaxyx()
    _put(scr, h - 1, 1, text + " …", curses.A_BOLD)
    scr.refresh()


def _loop(scr, app: _App) -> None:
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)
    curses.init_pair(3, curses.COLOR_RED, -1)
    scr.keypad(True)
    grays = _Grays()

    while True:
        _draw(scr, app, grays)
        ch = scr.getch()
        app.msg = ""

        if not app.reports:  # welcome screen
            if ch in (ord("q"), ord("Q")):
                return
            if ch == ord("i"):
                try:
                    _notice(scr, "initializing")
                    app.init_layer()
                except Exception as exc:
                    app.msg = f"error: {exc}"
            continue

        if app.show_help:
            if ch in (ord("q"), ord("Q")):
                return
            app.show_help = False
            continue

        if ch in (ord("q"), ord("Q")):
            return
        elif ch == ord("?"):
            app.show_help = True
        elif ch in tuple(ord(str(i)) for i in range(1, len(_VIEWS) + 1)):
            if _VIEWS[ch - ord("1")] == "fleet" and app._fleet is None:
                _notice(scr, "scanning sibling repos")
            app.view = _VIEWS[ch - ord("1")]
            app.clamp_sel()
        elif ch == ord("\t"):
            nxt = _VIEWS[(_VIEWS.index(app.view) + 1) % len(_VIEWS)]
            if nxt == "fleet" and app._fleet is None:
                _notice(scr, "scanning sibling repos")
            app.view = nxt
            app.clamp_sel()
        elif ch in (curses.KEY_UP, ord("k")):
            app.sel = max(0, app.sel - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            app.sel = min(len(app.rows()) - 1, app.sel + 1)
        elif ch in (curses.KEY_ENTER, 10, 13, ord("d")):
            app.show_detail = not app.show_detail
        elif ch == ord("r"):
            _notice(scr, "refreshing")
            if app.view == "fleet":
                app._fleet = None
            app.refresh()
            app.msg = "refreshed"
        elif ch == ord("H"):
            app.toggle_hook()
        elif ch == ord("e") and app.view == "agent":
            try:
                app.enable_selected_client()
            except Exception as exc:
                app.msg = f"error: {exc}"
        elif ch == ord("x") and app.view == "agent":
            app.toggle_access()
        elif ch == ord("o") and app.view == "fleet":
            _notice(scr, "opening")
            app.open_fleet_repo()
        elif ch in (ord("a"), ord("A")) and app.view == "watches":
            try:
                _notice(scr, "applying watches")
                app.apply_watches(everything=ch == ord("A"))
            except Exception as exc:
                app.msg = f"error: {exc}"
        elif ch in (ord("s"), ord("S"), ord("P"), ord("m")):
            try:
                if ch == ord("s"):
                    _notice(scr, "syncing")
                    app.sync_selected()
                elif ch == ord("S"):
                    _notice(scr, "syncing all")
                    app.sync_all()
                elif ch == ord("P"):
                    _notice(scr, "syncing all with prose")
                    app.sync_all(prose=True)
                else:
                    app.mark_selected()
            except Exception as exc:
                app.msg = f"error: {exc}"
        elif ch == curses.KEY_RESIZE:
            pass


def run(root: Path) -> int:
    """Run the dashboard (welcome screen when there is no context layer)."""
    reports = freshness.evaluate_all(root)
    try:
        curses.wrapper(_loop, _App(root, reports))
    except curses.error as exc:
        print(f"error: could not start the interactive UI ({exc})")
        return 2
    return 0
