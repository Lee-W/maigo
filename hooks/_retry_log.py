"""Append retry evidence and count consecutive failures in one run/task/check.

Unscoped and legacy entries remain historical evidence, never retry-limit input.
An empty key set records a successful check and resets that scope's streaks.
Retries of the same check must be sequential; unrelated scopes may interleave.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RetryScope:
    run_id: str
    task_id: str
    check_id: str = ""


def record_and_count(
    log_path: Path,
    keys: set[str],
    entry_key: str,
    *,
    scope: RetryScope | None = None,
) -> dict[str, int]:
    """Record one complete result; return streaks for its current failure keys.

    Scope-less calls return only this attempt's counts. Corrupted records are
    ignored and I/O failure returns no counts, preserving hooks' fail-open policy.
    """
    counts: dict[str, int] = {}
    scope_data = asdict(scope) if scope is not None else None
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if scope is not None and log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict) or entry.get("scope") != scope_data:
                    continue
                values = entry.get(entry_key)
                if not isinstance(values, list) or not all(
                    isinstance(k, str) for k in values
                ):
                    continue
                counts = {key: counts.get(key, 0) + 1 for key in set(values)}
        counts = {key: counts.get(key, 0) + 1 for key in keys}
        # Standalone CLI also runs under macOS system Python 3.9.
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: UP017
        entry = {"ts": ts, "scope": scope_data, entry_key: sorted(keys)}
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, UnicodeError):
        return {}
    return counts
