from slate import frontmatter


def test_round_trip_preserves_meta_and_body():
    meta = {
        "slate_doc": "modules",
        "slate_generated": True,
        "slate_synced_commit": "abc1234",
        "slate_watches": ["demo/**", "tests/**"],
    }
    body = "# Module map\n\nsome content\n"
    text = frontmatter.render(meta, body)
    parsed_meta, parsed_body = frontmatter.parse(text)
    assert parsed_meta == meta
    assert parsed_body == body


def test_no_frontmatter_returns_full_text():
    meta, body = frontmatter.parse("# Just a doc\n")
    assert meta == {}
    assert body == "# Just a doc\n"


def test_unknown_keys_survive():
    text = "---\ncustom_key: hello\nslate_doc: agents\n---\n\nbody\n"
    meta, _ = frontmatter.parse(text)
    assert meta["custom_key"] == "hello"
    rendered = frontmatter.render(meta, "body\n")
    meta2, _ = frontmatter.parse(rendered)
    assert meta2["custom_key"] == "hello"


def test_empty_list():
    meta, _ = frontmatter.parse("---\nslate_watches:\n---\n\nbody\n")
    assert meta["slate_watches"] == []


def test_dashes_in_body_not_treated_as_fence():
    body = "# Title\n\n---\n\nafter the rule\n"
    text = frontmatter.render({"slate_doc": "x"}, body)
    meta, parsed_body = frontmatter.parse(text)
    assert meta == {"slate_doc": "x"}
    assert "after the rule" in parsed_body
