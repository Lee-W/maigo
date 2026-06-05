"""Shared JSONL retry-log helper used by Maigo hooks.

Both `teammate_quality_check.py` (Soyo must-fix counts) and
`verify_completion.py` (Taki test-failure counts) need the same logic:
append a timestamped entry to a JSONL file, then return how many times each
key has been recorded across history. This module is the single source of
truth for that shape.

Failures (OSError, PermissionError) → return empty dict (fail-open, hooks
must continue). Corrupted JSON lines in the log are skipped, not raised.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path


def record_and_count(log_path: Path, keys: set[str], entry_key: str) -> dict[str, int]:
    """Append `keys` to the JSONL `log_path`; return total count per key.

    `entry_key` is the JSON field name used for the list of keys in each
    entry (e.g. `"must_fix_keys"` for Soyo, `"failures"` for Taki). Keeping
    the field name configurable preserves backward compatibility with
    existing on-disk logs written by either hook.
    """
    counts: dict[str, int] = {}
    try:
        if log_path.is_file():
            for line in log_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    for k in entry.get(entry_key, []):
                        counts[k] = counts.get(k, 0) + 1
                except json.JSONDecodeError:
                    pass  # corrupted line — skip, don't crash
        ts = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_entry = json.dumps({"ts": ts, entry_key: sorted(keys)}, ensure_ascii=False)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(new_entry + "\n")
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
    except (OSError, PermissionError):
        return {}
    return counts
