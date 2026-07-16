from slate import globs


def test_double_star_spans_directories():
    assert globs.matches("demo/**", "demo/a.py")
    assert globs.matches("demo/**", "demo/sub/deep/a.py")
    assert not globs.matches("demo/**", "other/a.py")


def test_leading_double_star():
    assert globs.matches("**/conftest.py", "conftest.py")
    assert globs.matches("**/conftest.py", "tests/unit/conftest.py")


def test_single_star_stays_in_segment():
    assert globs.matches("docker-compose*", "docker-compose.yml")
    assert globs.matches("demo/*.py", "demo/cli.py")
    assert not globs.matches("demo/*.py", "demo/sub/cli.py")


def test_exact_file_watch():
    assert globs.matches("Makefile", "Makefile")
    assert not globs.matches("Makefile", "sub/Makefile")


def test_question_mark():
    assert globs.matches("v?.md", "v1.md")
    assert not globs.matches("v?.md", "v12.md")


def test_filter_paths():
    hits = globs.filter_paths(
        ["demo/**", "Makefile"],
        ["demo/cli.py", "Makefile", "README.md", "tests/test_x.py"],
    )
    assert hits == ["demo/cli.py", "Makefile"]
