"""The version is declared twice, so something has to hold them together.

`pyproject.toml` feeds the built artifact's metadata; `slate.__version__`
feeds `slate --version`. Nothing in the packaging machinery relates them, and
the release workflow's tag guard only reads `pyproject.toml` — so a bump that
misses `slate/__init__.py` publishes a package whose own CLI reports the
previous version, and the release passes every check on the way out.

Consolidating onto one source (`importlib.metadata`) is the usual fix, but it
reads the *installed* distribution, which is wrong for a repo run from a
checkout — Slate is frequently used that way. Two declarations plus this test
is the cheaper trade.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import slate

ROOT = Path(__file__).resolve().parent.parent


def test_the_two_version_declarations_agree() -> None:
    declared = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    assert slate.__version__ == declared, (
        f"slate.__version__ is {slate.__version__} but pyproject.toml says "
        f"{declared}; `slate --version` would lie about the published package"
    )


def test_the_license_text_ships_beside_the_metadata_that_claims_it() -> None:
    """Apache-2.0 requires the text travel with the distribution."""
    licence = ROOT / "LICENSE"
    assert licence.is_file(), "pyproject declares Apache-2.0 with no LICENSE file"
    body = licence.read_text(encoding="utf-8")
    assert "Apache License" in body and "Version 2.0" in body
