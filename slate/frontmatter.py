"""Freshness metadata as Markdown frontmatter.

Every Slate context doc opens with a small frontmatter block that carries
its freshness anchor. The format is a deliberately tiny YAML subset —
flat ``key: value`` pairs plus one level of ``- item`` lists — parsed and
rendered by hand so the CLI stays dependency-free. Anything Slate did not
write (unknown keys) round-trips untouched.

Example:

    ---
    slate_doc: modules
    slate_generated: true
    slate_synced_commit: 3f2c91a
    slate_synced_at: 2026-07-15T10:00:00+00:00
    slate_synced_digest: 9f2ab6c1d4e0837a
    slate_watches:
      - slate/**
      - tests/**
    ---
"""

from __future__ import annotations

FENCE = "---"

Meta = dict[str, "str | bool | list[str]"]


def parse(text: str) -> tuple[Meta, str]:
    """Split a document into (frontmatter dict, body). No frontmatter → ({}, text)."""
    if not text.startswith(FENCE + "\n"):
        return {}, text
    end = text.find("\n" + FENCE + "\n", len(FENCE))
    if end == -1:
        return {}, text
    block = text[len(FENCE) + 1 : end]
    body = text[end + len(FENCE) + 2 :]
    if body.startswith("\n"):
        body = body[1:]

    meta: Meta = {}
    current_list_key: str | None = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("- ") and current_list_key is not None:
            values = meta.setdefault(current_list_key, [])
            assert isinstance(values, list)
            values.append(line.lstrip()[2:].strip().strip('"'))
            continue
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key, raw = key.strip(), raw.strip()
        if raw == "":
            meta[key] = []
            current_list_key = key
        else:
            current_list_key = None
            if raw in ("true", "false"):
                meta[key] = raw == "true"
            else:
                meta[key] = raw.strip('"')
    return meta, body


def render(meta: Meta, body: str) -> str:
    lines = [FENCE]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append(FENCE)
    return "\n".join(lines) + "\n\n" + body.lstrip("\n")
