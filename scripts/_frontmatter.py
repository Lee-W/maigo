"""Shared frontmatter parser for Maigo validators."""

from __future__ import annotations


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Return flat key→value dict from frontmatter, or None if missing/malformed."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    body = text[4:end]
    keys: dict[str, str] = {}
    for line in body.splitlines():
        if not line or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        keys[k.strip()] = v.strip()
    return keys
