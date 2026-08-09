"""Shared session-start HEAD record used by Maigo hooks.

`verify_completion.py` needs to answer "did this session change tracked
files?". A dirty working tree answers yes, but a session that *commits* its
work leaves the tree clean — and that is exactly the moment verification
matters most (the work is now in history, unverified). Comparing HEAD against
the SHA recorded by `repo_detect.py` at SessionStart closes that gap.

The record lives in `.maigo/`, which `repo_detect.ensure_maigo_ignored` keeps
out of `git status`, so writing it cannot itself make the tree look dirty.

Failures (not a git repo, git missing, OSError) → no record / no signal
(fail-quiet). Callers must treat "no record" as "unknown", never as "changed";
some harnesses disable SessionStart hooks, and turning every read-only session
into a full test run would be worse than the gap this closes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

LOG_PATH = Path(".maigo/session-head.json")
GIT_TIMEOUT_SEC = 5
# Cap the record so a long-lived checkout does not accumulate one entry per
# session forever. Only the current session's entry is ever read.
MAX_ENTRIES = 200


def current_head(cwd: Path) -> str | None:
    """Return the current HEAD SHA, or None outside a git repo / on any error.

    Also None in a freshly `git init`-ed repo with no commits yet: there is no
    HEAD to compare against, so such a session falls back to the dirty-tree
    check alone.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            timeout=GIT_TIMEOUT_SEC,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace").strip() or None


def read_records(path: Path) -> dict[str, str]:
    """Read the session → HEAD mapping; missing or corrupted file is empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


def record(cwd: Path, session_id: object) -> bool:
    """Record the HEAD this session starts at. Returns True if written."""
    if not isinstance(session_id, str) or not session_id:
        return False
    head = current_head(cwd)
    if head is None:
        return False

    path = cwd / LOG_PATH
    records = read_records(path)
    records[session_id] = head
    if len(records) > MAX_ENTRIES:
        # dicts keep insertion order, so this drops the oldest sessions
        records = dict(list(records.items())[-MAX_ENTRIES:])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(records, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError:
        return False
    return True


def head_moved(cwd: Path, session_id: object) -> bool:
    """Return True if HEAD differs from the SHA recorded at session start.

    False when there is no record for this session — "unknown", not "changed".
    """
    if not isinstance(session_id, str) or not session_id:
        return False
    start = read_records(cwd / LOG_PATH).get(session_id)
    if not start:
        return False
    head = current_head(cwd)
    if head is None:
        return False
    return head != start
