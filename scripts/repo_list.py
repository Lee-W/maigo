"""
Shared reader for the `--repo-list` text file (one absolute repo path per line,
blank lines and `#` comments ignored) used by `board_index.py`,
`migrate_legacy_artifacts.py` and `rewrite_note_paths.py`.
"""

from __future__ import annotations

from pathlib import Path


def parse_repo_list(text: str) -> list[str]:
    """Non-blank, non-comment lines of `text`, stripped."""
    repos = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        repos.append(line)
    return repos


def read_repo_list(path: Path) -> list[str] | None:
    """
    Read the list file; a missing or unreadable file (permission denied, a
    directory, ...) returns `None` so callers can print an explicit error and
    exit non-zero — a mistyped path must not look the same as "the list is
    really empty".
    """
    try:
        if not path.is_file():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_repo_list(text)
