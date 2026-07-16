"""Slate — context control plane for AI-assisted repos.

Keeps a small set of Markdown context files beside the code, detects which
of them a code change may have invalidated, and scores how safe each one is
to trust before the next AI action.
"""

__version__ = "0.1.0"
