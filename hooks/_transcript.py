"""Fail-open reader for subagent transcript JSONL files (undocumented format)."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

T = TypeVar("T")


def _token_count(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def iter_assistant_messages(path: Path) -> list[dict[str, Any]]:
    """Return assistant rows (type == "assistant", dict message); never raises."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
            continue
        if (
            isinstance(row, dict)
            and row.get("type") == "assistant"
            and isinstance(row.get("message"), dict)
        ):
            rows.append(row)
    return rows


def sum_usage(path: Path) -> tuple[dict[str, int], str | None] | None:
    """Sum usage across assistant rows, counting each message.id once."""
    seen: set[str] = set()
    totals = dict.fromkeys(USAGE_FIELDS, 0)
    model: str | None = None
    found = False
    for row in iter_assistant_messages(path):
        message = row["message"]
        message_id = message.get("id")
        usage = message.get("usage")
        if not isinstance(message_id, str) or not isinstance(usage, dict):
            continue
        found = True
        row_model = row.get("requestedModel")
        if not isinstance(row_model, str):
            row_model = message.get("model")
        model = row_model if isinstance(row_model, str) else None
        if message_id in seen:
            continue
        seen.add(message_id)
        for field in USAGE_FIELDS:
            totals[field] += _token_count(usage.get(field))
    return (totals, model) if found else None


def _content(row: dict[str, Any]) -> list[Any]:
    content = row["message"].get("content")
    return content if isinstance(content, list) else []


def _texts(row: dict[str, Any]) -> list[str]:
    return [
        block["text"]
        for block in _content(row)
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block["text"].strip()
    ]


def final_report(path: Path) -> str | None:
    """Last SubagentHandback input.message, else the text of the last message.

    The text fallback finds the last row holding a non-empty text block, then
    joins (newline) the text blocks of every row sharing its message.id, in
    file order, since transcripts split one message into one row per block.
    """
    rows = iter_assistant_messages(path)
    for row in reversed(rows):
        for block in reversed(_content(row)):
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "SubagentHandback"
                and isinstance(block.get("input"), dict)
                and isinstance(block["input"].get("message"), str)
                and block["input"]["message"].strip()
            ):
                return block["input"]["message"]
    for index in range(len(rows) - 1, -1, -1):
        if not _texts(rows[index]):
            continue
        message_id = rows[index]["message"].get("id")
        group = (
            [r for r in rows if r["message"].get("id") == message_id]
            if isinstance(message_id, str)
            else [rows[index]]
        )
        return "\n".join(text for r in group for text in _texts(r))
    return None


def read_with_retry(
    fn: Callable[[Path], T | None],
    path: Path,
    *,
    attempts: int = 3,
    delay: float = 0.15,
    sleep: Callable[[float], Any] = time.sleep,
) -> T | None:
    """Call fn(path) until it returns non-None; a missing file is not retried."""
    for attempt in range(attempts):
        if not path.exists():
            return None
        result = fn(path)
        if result is not None:
            return result
        if attempt < attempts - 1:
            sleep(delay)
    return None
