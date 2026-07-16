"""Opt-in LLM prose for auto-blocks (`slate sync --prose`).

Boundary rules (decision log, product doc §8):

  - Strictly opt-in: requires the flag AND ``ANTHROPIC_API_KEY``. Plain
    ``slate sync`` never makes a network call.
  - The LLM only *phrases* an orientation paragraph from the scanned facts
    it is handed; the deterministic facts always remain in the block below
    it, and freshness/score math never sees LLM output.
  - Zero dependencies: raw Messages API over ``urllib``. The HTTP transport
    is injectable so tests exercise everything but the socket.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

from .context import DocSpec

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5"

# transport(url, headers, body_bytes) -> parsed JSON response
Transport = Callable[[str, dict[str, str], bytes], dict]


class ProseError(RuntimeError):
    pass


def _urllib_transport(url: str, headers: dict[str, str], body: bytes) -> dict:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="ignore")[:300]
        raise ProseError(f"Anthropic API error {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProseError(f"could not reach the Anthropic API: {exc}") from exc


_SYSTEM = """You write one short orientation paragraph for a repo context document
read by AI coding tools. You are given the document's purpose and a Markdown
block of facts produced by a deterministic repo scan.

Rules:
- 2 to 4 sentences, plain prose, no headings, no lists, no code fences.
- Use ONLY the provided facts. Never invent files, directories, commands,
  or claims that are not literally present in the facts.
- If the facts are thin, say less rather than padding."""


def prose_writer(api_key: str, model: str | None = None,
                 transport: Transport | None = None) -> Callable[[DocSpec, str], str]:
    """Build the ``prose`` callback that generator.sync_doc accepts."""
    model = model or os.environ.get("SLATE_LLM_MODEL", DEFAULT_MODEL)
    send = transport or _urllib_transport

    def write(spec: DocSpec, facts: str) -> str:
        payload = {
            "model": model,
            "max_tokens": 300,
            "system": _SYSTEM,
            "messages": [{
                "role": "user",
                "content": (
                    f"Document: {spec.title} ({spec.rel_path})\n\n"
                    f"Scanned facts:\n\n{facts}"
                ),
            }],
        }
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        response = send(API_URL, headers, json.dumps(payload).encode())
        try:
            text = "".join(
                block["text"] for block in response["content"] if block.get("type") == "text"
            ).strip()
        except (KeyError, TypeError) as exc:
            raise ProseError(f"unexpected API response shape: {response}") from exc
        if not text:
            raise ProseError("the model returned no text")
        # Attribution is part of the block so readers can weight it correctly.
        return f"{text}\n\n*(orientation drafted by {model} from the scanned facts below)*"

    return write
