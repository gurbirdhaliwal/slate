"""Claim segmentation — every referencing body unit, nothing dropped.

Completeness is a trust property (freshness.py leans on it), so the key test
is that the union of segmented references equals the references of the whole
human text: a claim the segmenter loses could hide a changed symbol.
"""

from __future__ import annotations

from slate import claims
from slate.context import AUTO_BEGIN, AUTO_END
from slate.refs import extract_path_refs, extract_symbol_refs

BODY = f"""\
# Title

Intro paragraph with a ref to `pkg.helper` inside it.

## Invariants

- The `pkg.get_auto_block` call trims the block.
- A plain bullet with no code reference at all.
- See [the engine](pkg/engine.py) for details.

Some prose about `pkg/cli.py` spanning
a second line that mentions `pkg.other`.

{AUTO_BEGIN}
- generated fact about `pkg/` — 3 files
{AUTO_END}

## Notes

Nothing referential here.
"""


def test_segments_only_referencing_units() -> None:
    found = claims.human_claims(BODY)
    texts = [c.text for c in found]
    assert any("pkg.get_auto_block" in t for t in texts)
    assert any("pkg/engine.py" in t for t in texts)
    assert any("pkg.helper" in t for t in texts)
    # The no-reference bullet and the Notes prose are not claims.
    assert not any("plain bullet" in t for t in texts)
    assert not any("Nothing referential" in t for t in texts)


def test_bullets_are_separate_claims() -> None:
    found = claims.human_claims(BODY)
    bullet_texts = [c.text for c in found if c.text.startswith("- ")]
    # `get_auto_block` and the engine link are distinct bullets, not merged.
    assert any("pkg.get_auto_block" in t for t in bullet_texts)
    assert any("pkg/engine.py" in t for t in bullet_texts)
    assert all(not ("get_auto_block" in t and "engine.py" in t) for t in bullet_texts)


def test_section_is_tracked() -> None:
    found = claims.human_claims(BODY)
    invariant_claim = next(c for c in found if "get_auto_block" in c.text)
    assert invariant_claim.section == "Invariants"


def test_generated_block_is_excluded() -> None:
    # The fact inside the auto-block is not a human claim (freshness scores it
    # separately as a generated line).
    found = claims.human_claims(BODY)
    assert not any("generated fact" in c.text for c in found)


def test_multiline_paragraph_keeps_all_refs() -> None:
    found = claims.human_claims(BODY)
    para = next(c for c in found if "pkg/cli.py" in c.text)
    assert "pkg.other" in c_refs(para)  # the continuation line's ref survived


def test_no_reference_is_lost_vs_whole_text() -> None:
    # The invariant the trust path depends on: segmentation drops no reference.
    human = BODY.split(AUTO_BEGIN)[0] + BODY.split(AUTO_END)[1]
    whole = set(extract_path_refs(human)) | set(extract_symbol_refs(human))
    segmented: set[str] = set()
    for c in claims.human_claims(BODY):
        segmented.update(c.refs)
    assert whole <= segmented


def c_refs(claim: claims.Claim) -> set[str]:
    return set(claim.refs)


# --- filenames are not symbols ----------------------------------------------


def test_doc_filenames_are_not_symbol_references() -> None:
    """A filename read as a symbol is a claim about code nobody named.

    repairbench rev 1 scored `CHANGES.rst` as a symbol reference, so a doc that
    merely pointed at its own changelog was measured against a phantom. The
    extension guard has to cover the formats docs are actually written in, not
    only the ones Slate can parse.
    """
    for name in ("CHANGES.rst", "guide.mdx", "notes.adoc", "paper.tex",
                 "main.go", "Server.java", "schema.sql", "pom.xml"):
        assert extract_symbol_refs(f"see `{name}` for detail") == [], name


def test_real_symbols_still_extract() -> None:
    # The guard must not swallow genuine references that happen to end in a
    # short lowercase word.
    assert extract_symbol_refs("`context.get_auto_block` and `Doc.h`") == [
        "context.get_auto_block"
    ]
    assert extract_symbol_refs("`freshness.evaluate_all`") == ["freshness.evaluate_all"]
