#!/usr/bin/env python3
"""Maigo PreToolUse hook：擋下用「字面 grep 命中數」當驗收條件的交辦 prompt。

只匹配 `Agent` 工具。命中時 block（要 orchestrator 改寫驗收條件）；
放行時**不輸出任何 decision**——PreToolUse 的 `approve` 等於跳過權限系統，
這個 hook 沒有資格代替使用者做那個決定，所以放行一律靜默 exit 0。
輸入異常時一律 fail-open。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _grep_criteria import block_reason, find_literal_grep_criteria
from _hook_io import emit


def _pass_through() -> NoReturn:
    """Silent fail-open: no decision payload, so the permission flow is untouched."""
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        _pass_through()

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        _pass_through()

    prompt = tool_input.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        _pass_through()

    hits = find_literal_grep_criteria(prompt)
    if hits:
        emit("block", block_reason("交辦 prompt 的驗收條件", hits))
    _pass_through()


if __name__ == "__main__":
    main()
