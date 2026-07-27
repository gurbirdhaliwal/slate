"""Repo scanner — the deterministic facts the context layer is built from.

The scanner never guesses: everything it reports (languages, module map,
entry points, dev commands) is derived from files actually present in the
repo. LLM-written prose is a Phase 2 layer on top of this scan, never a
replacement for it (product doc §8).
"""

from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil

LANGUAGES: dict[str, str] = {
    ".py": "Python",
    ".java": "Java",
    ".kt": "Kotlin",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".sql": "SQL",
    ".sh": "Shell",
    ".css": "CSS",
    ".html": "HTML",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".json": "JSON",
}

# Extensions that count as "code" when deciding which directories are modules.
CODE_EXTENSIONS = {
    ".py", ".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs",
    ".rb", ".c", ".h", ".cpp", ".cs", ".swift", ".sql", ".sh",
}

_SKIP_DIRS = {".slate", "docs", "doc", ".github", ".git"}

# A sub-package earns its own row once it holds this many code files; below
# that it is noise and stays folded into its parent.
_MIN_MODULE_FILES = 2

# Upper bound on rows in the module map. The map is an orientation aid, not an
# inventory — a repo with 200 test directories must not bury its source tree.
_MAX_MODULE_ROWS = 14

# Trees that exist to exercise or illustrate the code rather than be it. They
# still get rows, but they yield to real source when the cap bites.
_SUPPORTING_ROOTS = {
    "tests", "test", "testing", "examples", "example", "docs_src",
    "benchmarks", "bench", "e2e", "fixtures", "integration", "spec",
}


@dataclass
class Module:
    name: str  # module path ("src/flask", "src/flask/json"), or "." for root
    file_count: int
    primary_language: str | None
    entry_hints: list[str] = field(default_factory=list)


@dataclass
class RepoScan:
    root: Path
    files: list[str]
    languages: Counter  # language name -> file count (code files only)
    modules: list[Module]
    commands: dict[str, list[str]]  # tool -> invocations, e.g. "make" -> ["make test"]
    ci_workflows: list[str]
    readme_title: str | None
    # Module-level dependency graph: module path -> module paths it imports
    # from. A tracked fact (rendered into the auto-block), not just a watch hint.
    edges: dict[str, set[str]] = field(default_factory=dict)

    @property
    def source_dirs(self) -> list[str]:
        """Top-level code directories — the unit watch globs are derived from.

        Deliberately *coarser* than ``modules``: a watch glob that descended to
        ``src/flask/**`` would stop watching anything else that later appears
        under ``src/``, and an unwatched change is a false ``fresh`` — the one
        failure mode §10 says must never happen. Narrow the map, never the net.
        """
        return sorted({m.name.split("/", 1)[0] for m in self.modules if m.name != "."})

    @property
    def module_paths(self) -> list[str]:
        """Full module paths — the granularity of the map and the edge graph."""
        return [m.name for m in self.modules if m.name != "."]


def scan(root: Path) -> RepoScan:
    files = gitutil.list_files(root)
    languages: Counter = Counter()

    for path in files:
        suffix = Path(path).suffix.lower()
        if suffix in CODE_EXTENSIONS:
            languages[LANGUAGES.get(suffix, suffix)] += 1

    modules = _build_modules(files)
    commands = _detect_commands(root, files)
    ci = sorted(
        Path(p).stem for p in files
        if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))
    )
    module_paths = [m.name for m in modules if m.name != "."]
    # Lazy import breaks the scanner<->imports cycle (imports needs RepoScan).
    from . import imports
    edges = imports.compute_edges(root, files, module_paths)
    return RepoScan(
        root=root,
        files=files,
        languages=languages,
        modules=modules,
        commands=commands,
        ci_workflows=ci,
        readme_title=_readme_title(root),
        edges=edges,
    )


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def _build_modules(files: list[str]) -> list[Module]:
    """The module map, at package granularity rather than top-level directory.

    Keying on the first path segment collapses the near-universal
    ``src/<package>/`` layout into a single uninformative row — the map ends up
    reporting the same 2-5 rows whether the repo has 40 files or 1,100, which
    answers none of the "where does X live" questions the doc exists for. So:
    descend through pass-through directories that merely wrap a package, then
    give the package's substantial sub-packages their own rows.
    """
    direct_code: Counter = Counter()  # dir -> code files directly in it
    for path in files:
        if Path(path).suffix.lower() in CODE_EXTENSIONS:
            direct_code[_dirname(path)] += 1

    # Code files anywhere at or below each directory, so a wrapper dir with no
    # code of its own still knows whether it leads anywhere.
    subtree: Counter = Counter()
    for directory, count in direct_code.items():
        parts = [] if directory == "." else directory.split("/")
        for depth in range(len(parts) + 1):
            subtree["/".join(parts[:depth]) or "."] += count

    def children(parent: str) -> list[str]:
        depth = 0 if parent == "." else len(parent.split("/"))
        prefix = "" if parent == "." else parent + "/"
        return sorted({
            "/".join(d.split("/")[: depth + 1])
            for d in subtree
            if d != "." and d.startswith(prefix) and d != parent and subtree[d] > 0
        })

    def descend(directory: str) -> str:
        """`src/` -> `src/flask/`: follow a dir that holds no code and one child."""
        while direct_code[directory] == 0:
            kids = children(directory)
            if len(kids) != 1:
                return directory
            directory = kids[0]
        return directory

    names: list[str] = []
    tops = sorted({p.split("/", 1)[0] for p in files if "/" in p})
    for top in tops:
        if top in _SKIP_DIRS or top.startswith(".") or subtree[top] == 0:
            continue
        base = descend(top)
        rows = [base] if direct_code[base] else []
        rows += [c for c in children(base) if subtree[c] >= _MIN_MODULE_FILES]
        names.extend(rows or [base])
    if direct_code["."]:
        names.append(".")

    # Every file belongs to exactly one row — its most specific enclosing
    # module. So a row's count covers its whole subtree *except* the parts
    # broken out into their own rows: no double counting, and a file added
    # deep inside a package still moves the row it belongs to (which is what
    # makes the map go `stale` when the layout really changed).
    chosen = _cap(names, subtree)
    owned: dict[str, list[str]] = {name: [] for name in chosen}
    ranked = sorted(chosen, key=len, reverse=True)
    for path in files:
        parent = _dirname(path)
        for name in ranked:
            if parent == name or parent.startswith(name + "/"):
                owned[name].append(path)
                break
    return [_module(name, owned[name]) for name in chosen]


def _cap(names: list[str], subtree: Counter) -> list[str]:
    """Trim to the row budget, dropping supporting trees before real source."""
    def rank(name: str) -> tuple[int, int, str]:
        top = name.split("/", 1)[0]
        return (1 if top in _SUPPORTING_ROOTS else 0, -subtree[name], name)

    return sorted(sorted(dict.fromkeys(names), key=rank)[:_MAX_MODULE_ROWS])


def _module(name: str, paths: list[str]) -> Module:
    code = [p for p in paths if Path(p).suffix.lower() in CODE_EXTENSIONS]
    lang_counts = Counter(LANGUAGES.get(Path(p).suffix.lower(), "other") for p in code)
    hints = sorted(
        p for p in paths
        if Path(p).name in (
            "__main__.py", "main.py", "cli.py", "index.ts", "main.ts",
            "App.tsx", "Application.java",
        )
    )
    return Module(
        name=name,
        file_count=len(paths),
        primary_language=lang_counts.most_common(1)[0][0] if lang_counts else None,
        entry_hints=hints[:3],
    )


def _detect_commands(root: Path, files: list[str]) -> dict[str, list[str]]:
    commands: dict[str, list[str]] = {}

    if "Makefile" in files:
        targets = re.findall(
            r"^([A-Za-z0-9_.-]+):(?!=)", (root / "Makefile").read_text(), re.M
        )
        seen = [t for t in dict.fromkeys(targets) if t != ".PHONY"]
        if seen:
            commands["make"] = [f"make {t}" for t in seen]

    if "package.json" in files:
        try:
            pkg = json.loads((root / "package.json").read_text())
            scripts = list(pkg.get("scripts", {}))
            if scripts:
                commands["npm"] = [f"npm run {s}" for s in scripts]
        except (json.JSONDecodeError, OSError):
            pass

    if "pyproject.toml" in files:
        try:
            data = tomllib.loads((root / "pyproject.toml").read_text())
            entry_points = list(data.get("project", {}).get("scripts", {}))
            if entry_points:
                commands["console scripts"] = entry_points
            if _has_tests(files):
                commands.setdefault("pytest", ["pytest"])
        except (tomllib.TOMLDecodeError, OSError):
            pass

    if "pom.xml" in files:
        commands["maven"] = ["mvn test", "mvn package"]
    if any(p.startswith("docker-compose") for p in files):
        commands["docker"] = ["docker compose up -d"]
    return commands


def _has_tests(files: list[str]) -> bool:
    return any(p.startswith(("tests/", "test/")) or "/tests/" in p for p in files)


def _readme_title(root: Path) -> str | None:
    readme = root / "README.md"
    if not readme.exists():
        return None
    for line in readme.read_text().splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None
