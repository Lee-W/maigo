"""Run task verification without relying on any host's lifecycle hooks.

Usage: python3 /path/to/maigo/scripts/verify_task.py --cwd /path/to/project
An optional --command overrides test discovery; it is an argv string, not a shell.
stdout is a JSON evidence record. Only status=passed exits zero.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hooks.verify_completion import RetryScope, VerificationResult, run_verification  # noqa: E402

EXIT_CODES = {
    "passed": 0,
    "failed": 1,
    "unavailable": 2,
    "skipped": 3,
    "known_failures": 4,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, required=True)
    parser.add_argument("--run-id", help="Reuse with --task-id for retries of one task")
    parser.add_argument("--task-id", help="Task identity within the selected run")
    parser.add_argument(
        "--command", help="Explicit test argv, parsed with shlex (no shell)"
    )
    args = parser.parse_args()
    if (args.run_id is None) != (args.task_id is None):
        parser.error("--run-id and --task-id must be supplied together")
    if any(
        value is not None and not value.strip() for value in (args.run_id, args.task_id)
    ):
        parser.error("run and task IDs must not be empty")
    scope = RetryScope(args.run_id or uuid4().hex, args.task_id or "verification")
    cwd = args.cwd.resolve()
    # Standalone entry points may run under macOS's system Python 3.9.
    started_at = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    result = (
        run_verification(cwd, args.command, retry_scope=scope)
        if cwd.is_dir()
        else VerificationResult("unavailable", f"cwd is not a directory: {cwd}")
    )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "cwd": str(cwd),
                "run_id": scope.run_id,
                "task_id": scope.task_id,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
                **asdict(result),
            },
            ensure_ascii=False,
        )
    )
    sys.exit(EXIT_CODES[result.status])


if __name__ == "__main__":
    main()
