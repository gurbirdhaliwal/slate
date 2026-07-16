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


@dataclass
class Module:
    name: str  # top-level directory, or "." for root-level files
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

    @property
    def source_dirs(self) -> list[str]:
        return [m.name for m in self.modules if m.name != "."]


def scan(root: Path) -> RepoScan:
    files = gitutil.list_files(root)
    languages: Counter = Counter()
    per_dir_files: dict[str, list[str]] = {}

    for path in files:
        suffix = Path(path).suffix.lower()
        if suffix in CODE_EXTENSIONS:
            languages[LANGUAGES.get(suffix, suffix)] += 1
        top = path.split("/", 1)[0] if "/" in path else "."
        per_dir_files.setdefault(top, []).append(path)

    modules = _build_modules(per_dir_files)
    commands = _detect_commands(root, files)
    ci = sorted(
        Path(p).stem for p in files
        if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))
    )
    return RepoScan(
        root=root,
        files=files,
        languages=languages,
        modules=modules,
        commands=commands,
        ci_workflows=ci,
        readme_title=_readme_title(root),
    )


def _build_modules(per_dir_files: dict[str, list[str]]) -> list[Module]:
    modules: list[Module] = []
    for top, paths in sorted(per_dir_files.items()):
        if top in _SKIP_DIRS or top.startswith("."):
            continue
        code = [p for p in paths if Path(p).suffix.lower() in CODE_EXTENSIONS]
        if top != "." and not code:
            continue
        lang_counts = Counter(
            LANGUAGES.get(Path(p).suffix.lower(), "other") for p in code
        )
        primary = lang_counts.most_common(1)[0][0] if lang_counts else None
        hints = [
            p for p in paths
            if Path(p).name in (
                "__main__.py", "main.py", "cli.py", "index.ts", "main.ts",
                "App.tsx", "Application.java",
            )
        ]
        modules.append(Module(top, len(paths), primary, hints[:3]))
    return modules


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
