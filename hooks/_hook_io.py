"""Shared I/O helpers for Maigo hooks.

All hooks emit a JSON `{decision, reason, systemMessage}` payload to stdout
then `sys.exit(0)`. Single source of truth lives here so the payload shape
stays identical across hooks.
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
