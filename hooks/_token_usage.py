"""Local, metadata-only token usage storage and summaries."""

from __future__ import annotations

import datetime
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
LOG_PATH = Path(".maigo/token-usage.jsonl")


def _token_count(value: Any) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else 0
    )


def read_entries(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read valid object entries and count malformed lines; missing is empty."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], 0

    entries: list[dict[str, Any]] = []
    malformed = 0
    for line in lines:
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            malformed += 1
            continue
        if isinstance(entry, dict):
            entries.append(entry)
        else:
            malformed += 1
    return entries, malformed


def record_agent_usage(data: dict[str, Any]) -> bool:
    """Append one completed foreground Agent usage record, fail-open."""
    if data.get("hook_event_name") != "PostToolUse" or data.get("tool_name") != "Agent":
        return False

    response = data.get("tool_response")
    if not isinstance(response, dict) or response.get("status") != "completed":
        return False
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return False

    session_id = data.get("session_id")
    agent_id = response.get("agentId")
    cwd = data.get("cwd")
    if not isinstance(session_id, str) or not session_id:
        return False
    if not isinstance(agent_id, str) or not agent_id:
        return False
    if not isinstance(cwd, str) or not cwd:
        return False

    counts = {field: _token_count(usage.get(field)) for field in USAGE_FIELDS}
    if not any(counts.values()):
        return False

    log_path = Path(cwd) / LOG_PATH
    entries, _ = read_entries(log_path)
    if any(
        entry.get("session_id") == session_id and entry.get("agent_id") == agent_id
        for entry in entries
    ):
        return False

    tool_input = data.get("tool_input")
    agent_type = (
        tool_input.get("subagent_type") if isinstance(tool_input, dict) else None
    )
    record = {
        "ts": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "session_id": session_id,
        "agent_id": agent_id,
        "agent_type": agent_type if isinstance(agent_type, str) else None,
        "model": response.get("resolvedModel"),
        **counts,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return False
    return True


@dataclass(frozen=True)
class UsageSummary:
    tracked_agents: int
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    malformed_lines: int = 0


def _filter_entries(
    entries: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    since: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    if session_id is not None:
        entries = [entry for entry in entries if entry.get("session_id") == session_id]
    if since is None:
        return entries

    filtered: list[dict[str, Any]] = []
    for entry in entries:
        timestamp = entry.get("ts")
        if not isinstance(timestamp, str):
            continue
        try:
            parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.UTC)
        if parsed >= since:
            filtered.append(entry)
    return filtered


def summarize(
    path: Path,
    *,
    session_id: str | None = None,
    since: datetime.datetime | None = None,
) -> UsageSummary:
    entries, malformed = read_entries(path)
    entries = _filter_entries(entries, session_id=session_id, since=since)
    totals = {
        field: sum(_token_count(entry.get(field)) for entry in entries)
        for field in USAGE_FIELDS
    }
    return UsageSummary(len(entries), malformed_lines=malformed, **totals)


def breakdown(
    path: Path, *, since: datetime.datetime | None = None
) -> tuple[Counter[str], Counter[str]]:
    """Return total recorded tokens grouped by agent type and model."""
    entries, _ = read_entries(path)
    entries = _filter_entries(entries, since=since)
    agents: Counter[str] = Counter()
    models: Counter[str] = Counter()
    for entry in entries:
        total = sum(_token_count(entry.get(field)) for field in USAGE_FIELDS)
        agent_type = entry.get("agent_type")
        model = entry.get("model")
        agents[
            agent_type if isinstance(agent_type, str) and agent_type else "unknown"
        ] += total
        models[model if isinstance(model, str) and model else "unknown"] += total
    return agents, models


def _compact(value: int) -> str:
    if value < 1_000:
        return str(value)
    if value < 1_000_000:
        return f"{value / 1_000:.1f}k"
    return f"{value / 1_000_000:.1f}m"


def format_one_line(summary: UsageSummary) -> str:
    if summary.tracked_agents == 0:
        return "Token usage：無可用 metadata（背景 agent、Codex 或舊版 harness 可能不提供）"
    return (
        f"Token usage：input {_compact(summary.input_tokens)}｜"
        f"output {_compact(summary.output_tokens)}｜"
        f"cache write {_compact(summary.cache_creation_input_tokens)}｜"
        f"cache read {_compact(summary.cache_read_input_tokens)}｜"
        f"已追蹤 {summary.tracked_agents} agents"
    )


def format_breakdown(label: str, counts: Counter[str]) -> str:
    values = "、".join(
        f"{key} {_compact(value)}" for key, value in counts.most_common()
    )
    return f"{label}：{values or '無資料'}"
