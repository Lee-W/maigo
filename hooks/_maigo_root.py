"""Resolve the repo root a hook should write `.maigo/` under.

Hooks receive the session's `cwd` in their payload, and that cwd is wherever the
session happens to be: a repo subdirectory, or even `.maigo/` itself. Writing to
`cwd / ".maigo"` then grows a second `.maigo/` in the subdirectory (or
`.maigo/.maigo/`). Every hook that writes machine state goes through this module
instead, so the destination is always `<repo root>/.maigo/`.

Resolution: `git -C <cwd> rev-parse --show-toplevel` (inside a worktree this is
the worktree's own root). When git is unavailable or `cwd` is not in a repo, fall
back to `cwd`; if that path runs through a `.maigo` segment, the parent of the
outermost one is used so a non-git cwd inside `.maigo/` does not nest again.
Known limitation: that fallback cannot tell a `.maigo/` artifact directory from
an ancestor that merely happens to be named `.maigo`, so a non-git project that
itself lives under a `.maigo` ancestor resolves to the ancestor's parent.
A cwd that cannot be resolved at all (for example one containing a NUL byte)
falls back to the cwd as given: hooks always fail open.
No environment variable is read.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT_SEC = 5
MAIGO_DIRNAME = ".maigo"
INTERNAL_LOG_PARTS = ("_internal", "log")


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    top = result.stdout.decode("utf-8", errors="replace").strip()
    return Path(top) if top else None


def _strip_dot_maigo(path: Path) -> Path:
    parts = path.parts
    if MAIGO_DIRNAME not in parts:
        return path
    return Path(*parts[: parts.index(MAIGO_DIRNAME)])


def maigo_root(cwd: str | Path) -> Path:
    """Return the repo root for `cwd` (git toplevel, else `cwd` minus `.maigo`)."""
    try:
        start = Path(cwd).resolve()
    except (ValueError, OSError):
        return Path(cwd)
    top = _git_toplevel(start)
    if top is not None:
        return top.resolve()
    return _strip_dot_maigo(start)


def maigo_dir(cwd: str | Path) -> Path:
    return maigo_root(cwd) / MAIGO_DIRNAME


def internal_log_dir(cwd: str | Path) -> Path:
    return maigo_dir(cwd).joinpath(*INTERNAL_LOG_PARTS)


def readable_log_path(cwd: str | Path, name: str) -> Path:
    """Path to read `name` from: the `_internal/log/` copy, else the legacy top-level one.

    Only the read side falls back; when both exist the new one wins and the two
    are never merged (moving old files is `/maigo:tidy`'s job).
    """
    new = internal_log_dir(cwd) / name
    if new.exists():
        return new
    legacy = maigo_dir(cwd) / name
    return legacy if legacy.exists() else new
