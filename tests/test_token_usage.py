"""Tests for metadata-only token usage tracking."""

from __future__ import annotations

import json
import datetime
from pathlib import Path

from hooks import _token_usage as usage


def agent_event(cwd: Path, **overrides: object) -> dict:
    event = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "session_id": "session-1",
        "cwd": str(cwd),
        "tool_input": {"subagent_type": "maigo:Soyo"},
        "tool_response": {
            "status": "completed",
            "agentId": "agent-1",
            "resolvedModel": "claude-sonnet",
            "usage": {
                "input_tokens": 8_320,
                "output_tokens": 1_230,
                "cache_creation_input_tokens": 400,
                "cache_read_input_tokens": 2_500,
            },
        },
    }
    event.update(overrides)
    return event


def test_records_completed_agent_usage(tmp_path: Path):
    assert usage.record_agent_usage(agent_event(tmp_path))

    entries, malformed = usage.read_entries(tmp_path / usage.LOG_PATH)
    assert malformed == 0
    assert entries[0] == {
        "ts": entries[0]["ts"],
        "session_id": "session-1",
        "agent_id": "agent-1",
        "agent_type": "maigo:Soyo",
        "model": "claude-sonnet",
        "input_tokens": 8_320,
        "output_tokens": 1_230,
        "cache_creation_input_tokens": 400,
        "cache_read_input_tokens": 2_500,
    }


def test_deduplicates_session_and_agent(tmp_path: Path):
    event = agent_event(tmp_path)

    assert usage.record_agent_usage(event)
    assert not usage.record_agent_usage(event)
    assert len(usage.read_entries(tmp_path / usage.LOG_PATH)[0]) == 1


def test_background_or_missing_usage_is_ignored(tmp_path: Path):
    background = agent_event(
        tmp_path,
        tool_response={"status": "async_launched", "agentId": "agent-1"},
    )
    missing = agent_event(
        tmp_path,
        tool_response={"status": "completed", "agentId": "agent-2"},
    )

    assert not usage.record_agent_usage(background)
    assert not usage.record_agent_usage(missing)
    assert not (tmp_path / usage.LOG_PATH).exists()


def test_summary_filters_session_and_reports_malformed_lines(tmp_path: Path):
    log = tmp_path / usage.LOG_PATH
    log.parent.mkdir()
    rows = [
        {
            "session_id": "session-1",
            "input_tokens": 1_000,
            "output_tokens": 200,
            "cache_creation_input_tokens": 30,
            "cache_read_input_tokens": 400,
        },
        {
            "session_id": "session-2",
            "input_tokens": 9_000,
            "output_tokens": 800,
        },
    ]
    log.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\nnot-json\n",
        encoding="utf-8",
    )

    summary = usage.summarize(log, session_id="session-1")

    assert summary.tracked_agents == 1
    assert summary.input_tokens == 1_000
    assert summary.output_tokens == 200
    assert summary.cache_creation_input_tokens == 30
    assert summary.cache_read_input_tokens == 400
    assert summary.malformed_lines == 1
    assert usage.format_one_line(summary) == (
        "Token usage：input 1.0k｜output 200｜cache write 30｜"
        "cache read 400｜已追蹤 1 agents"
    )


def test_empty_summary_states_metadata_is_unavailable(tmp_path: Path):
    summary = usage.summarize(tmp_path / "missing.jsonl", session_id="missing")

    assert "無可用 metadata" in usage.format_one_line(summary)


def test_summary_lookback_and_breakdown(tmp_path: Path):
    log = tmp_path / usage.LOG_PATH
    log.parent.mkdir()
    now = datetime.datetime.now(datetime.UTC)
    rows = [
        {
            "ts": (now - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_type": "maigo:Soyo",
            "model": "sonnet",
            "input_tokens": 1_000,
            "output_tokens": 200,
        },
        {
            "ts": (now - datetime.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agent_type": "maigo:Raana",
            "model": "haiku",
            "input_tokens": 9_000,
            "output_tokens": 1_000,
        },
    ]
    log.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    since = now - datetime.timedelta(days=7)

    summary = usage.summarize(log, since=since)
    agents, models = usage.breakdown(log, since=since)

    assert summary.tracked_agents == 1
    assert agents == {"maigo:Soyo": 1_200}
    assert models == {"sonnet": 1_200}
    assert usage.format_breakdown("依角色", agents) == "依角色：maigo:Soyo 1.2k"
