#!/usr/bin/env python3
"""Print a read-only token usage summary from Maigo's local metadata log."""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
from _token_usage import (  # noqa: E402
    LOG_PATH,
    breakdown,
    format_breakdown,
    format_one_line,
    summarize,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize Maigo token usage metadata."
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--session-id", help="Only include one Claude Code session.")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window when --session-id is omitted. Defaults to 7.",
    )
    args = parser.parse_args()
    if args.days <= 0:
        parser.error("--days must be positive")

    path = args.root.resolve() / LOG_PATH
    since = None
    if args.session_id is None:
        since = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=args.days)
    print(format_one_line(summarize(path, session_id=args.session_id, since=since)))
    if args.session_id is None:
        agents, models = breakdown(path, since=since)
        print(format_breakdown("依角色", agents))
        print(format_breakdown("依 model", models))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
