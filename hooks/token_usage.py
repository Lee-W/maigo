#!/usr/bin/env python3
"""Record token metadata from completed foreground Agent tool calls."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _token_usage import record_agent_usage  # noqa: E402


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
        if isinstance(data, dict):
            record_agent_usage(data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
