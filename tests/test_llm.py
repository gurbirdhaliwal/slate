import json
from pathlib import Path

import pytest

from slate import context, generator, llm, scanner
from slate.cli import main
from slate.context import get_auto_block

from .conftest import commit_all


def init_layer(repo: Path) -> None:
    generator.generate_all(scanner.scan(repo))
    commit_all(repo, "add context layer")


def fake_transport(responses: list[dict], calls: list[dict]):
    def send(url: str, headers: dict, body: bytes) -> dict:
        calls.append({"url": url, "headers": headers, "payload": json.loads(body)})
        return responses.pop(0)
    return send


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def test_prose_writer_sends_facts_and_formats_attribution() -> None:
    calls: list[dict] = []
    write = llm.prose_writer(
        "key-123", model="test-model",
        transport=fake_transport([_ok("This repo is a demo.")], calls),
    )
    spec = context.spec_by_name("modules")
    result = write(spec, "| Module | Files |\n| `demo/` | 3 |")
    assert result.startswith("This repo is a demo.")
    assert "drafted by test-model" in result

    call = calls[0]
    assert call["headers"]["x-api-key"] == "key-123"
    assert call["payload"]["model"] == "test-model"
    assert "| `demo/` | 3 |" in call["payload"]["messages"][0]["content"]
    assert "Never invent" in call["payload"]["system"]


def test_prose_writer_rejects_bad_response_shape() -> None:
    write = llm.prose_writer(
        "k", model="m", transport=fake_transport([{"error": "nope"}], []),
    )
    with pytest.raises(llm.ProseError):
        write(context.spec_by_name("modules"), "facts")


def test_sync_doc_places_prose_above_facts(repo: Path) -> None:
    init_layer(repo)
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("modules"))
    generator.sync_doc(doc, scan, prose=lambda spec, facts: "PROSE-HERE")
    block = get_auto_block(context.spec_by_name("modules").path(repo).read_text(encoding="utf-8"))
    assert block.startswith("PROSE-HERE")
    assert "| Module |" in block  # deterministic facts still present below


def test_plain_sync_never_adds_prose(repo: Path) -> None:
    init_layer(repo)
    scan = scanner.scan(repo)
    doc = context.load(repo, context.spec_by_name("modules"))
    generator.sync_doc(doc, scan)
    block = get_auto_block(context.spec_by_name("modules").path(repo).read_text(encoding="utf-8"))
    assert block.startswith("| Module |")


def test_cli_prose_requires_api_key(repo: Path, capsys, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    init_layer(repo)
    code = main(["-C", str(repo), "sync", "--prose"])
    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
