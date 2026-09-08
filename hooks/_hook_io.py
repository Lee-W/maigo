"""Shared I/O helpers for Maigo hooks.

Decision encoding depends on the hook event. PreToolUse supports the legacy
decision payload; Stop/SubagentStop omit decision when allowing completion.
"""

from __future__ import annotations

import json
import sys
from typing import NoReturn


def emit(decision: str, reason: str) -> NoReturn:
    """Write the standard hook decision payload to stdout and exit 0."""
    payload = {"decision": decision, "reason": reason, "systemMessage": reason}
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)


def emit_stop(decision: str, reason: str) -> NoReturn:
    """Stop/SubagentStop: omit decision to allow; block asks the agent to continue."""
    payload = {"reason": reason, "systemMessage": reason}
    if decision == "block":
        payload["decision"] = "block"
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.exit(0)
